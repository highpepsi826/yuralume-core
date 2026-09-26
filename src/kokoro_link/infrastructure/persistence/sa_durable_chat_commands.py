"""SQLAlchemy adapter for durable foreground chat command acceptance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from kokoro_link.contracts.durable_chat_commands import (
    ACTIVE_COMMAND_STATES,
    AcceptedCommand,
    ClaimedCommand,
    ChatTurnCommand,
    ChatTurnPhase,
    ChatTurnCommandState,
    ChatTurnCommandSubmission,
    CommandSubmissionResult,
    ConversationBusy,
    DurableChatCommandRepositoryPort,
    IdempotencyConflict,
)
from kokoro_link.infrastructure.persistence.models import ChatTurnCommandRow


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _row_to_command(row: ChatTurnCommandRow) -> ChatTurnCommand:
    return ChatTurnCommand(
        turn_id=row.turn_id,
        owner_id=row.owner_id,
        client_message_id=row.client_message_id,
        character_id=row.character_id,
        conversation_id=row.conversation_id,
        payload_hash=row.payload_hash,
        payload_version=row.payload_version,
        payload_json=row.payload_json,
        state=ChatTurnCommandState(row.state),
        phase=ChatTurnPhase(row.phase),
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        next_attempt_at=(
            _utc(row.next_attempt_at) if row.next_attempt_at else None
        ),
        conversation_revision=row.conversation_revision,
        user_message_id=row.user_message_id,
        user_message_position=row.user_message_position,
        assistant_message_id=row.assistant_message_id,
        assistant_message_position=row.assistant_message_position,
        result_message_id=row.result_message_id,
        generated_snapshot_json=row.generated_snapshot_json,
        generated_snapshot_hash=row.generated_snapshot_hash,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
        lease_owner=row.lease_owner,
        lease_until=_utc(row.lease_until) if row.lease_until else None,
        lease_generation=row.lease_generation,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        accepted_at=_utc(row.accepted_at),
        last_heartbeat_at=(
            _utc(row.last_heartbeat_at) if row.last_heartbeat_at else None
        ),
    )


class SADurableChatCommandRepository(DurableChatCommandRepositoryPort):
    """PostgreSQL-backed P1-1 receipt store.

    The transaction is intentionally short: it only performs idempotency and
    admission checks plus the insert.  It never waits for an LLM or a worker.
    """

    def __init__(self, session_factory: sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def submit(
        self,
        submission: ChatTurnCommandSubmission,
    ) -> CommandSubmissionResult:
        now = _utc(submission.accepted_at or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            existing = await self._find_by_client_id(
                session,
                owner_id=submission.owner_id,
                client_message_id=submission.client_message_id,
                lock=True,
            )
            if existing is not None:
                command = _row_to_command(existing)
                await session.rollback()
                if command.payload_hash != submission.payload_hash:
                    return IdempotencyConflict(command)
                return AcceptedCommand(command, duplicate=True)

            busy = await self._find_active_for_conversation(
                session,
                owner_id=submission.owner_id,
                conversation_id=submission.conversation_id,
                lock=True,
            )
            if busy is not None:
                busy_command = _row_to_command(busy)
                await session.rollback()
                return ConversationBusy(busy_command)

            row = ChatTurnCommandRow(
                turn_id=uuid4().hex,
                owner_id=submission.owner_id,
                client_message_id=submission.client_message_id,
                character_id=submission.character_id,
                conversation_id=submission.conversation_id,
                payload_hash=submission.payload_hash,
                payload_version=submission.payload_version,
                payload_json=submission.payload_json,
                state=ChatTurnCommandState.QUEUED.value,
                phase=ChatTurnPhase.ACCEPTED.value,
                attempt_count=0,
                max_attempts=submission.max_attempts,
                next_attempt_at=None,
                conversation_revision=submission.conversation_revision,
                user_message_id=None,
                user_message_position=None,
                assistant_message_id=None,
                assistant_message_position=None,
                generated_snapshot_json=None,
                generated_snapshot_hash=None,
                lease_generation=0,
                created_at=now,
                updated_at=now,
                accepted_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                # The unique client key or active-conversation index won a
                # concurrent race. Re-read after rollback and return the same
                # semantic result instead of leaking a dialect-specific error.
                await session.rollback()
                existing = await self._find_by_client_id(
                    session,
                    owner_id=submission.owner_id,
                    client_message_id=submission.client_message_id,
                    lock=False,
                )
                if existing is not None:
                    command = _row_to_command(existing)
                    if command.payload_hash != submission.payload_hash:
                        return IdempotencyConflict(command)
                    return AcceptedCommand(command, duplicate=True)
                busy = await self._find_active_for_conversation(
                    session,
                    owner_id=submission.owner_id,
                    conversation_id=submission.conversation_id,
                    lock=False,
                )
                if busy is not None:
                    return ConversationBusy(_row_to_command(busy))
                raise
            await session.refresh(row)
            return AcceptedCommand(_row_to_command(row))

    async def get(
        self,
        turn_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ChatTurnCommandRow).where(
                    ChatTurnCommandRow.turn_id == turn_id,
                    ChatTurnCommandRow.owner_id == owner_id,
                ),
            )
            return _row_to_command(row) if row is not None else None

    async def get_by_client_message_id(
        self,
        client_message_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        async with self._session_factory() as session:
            row = await self._find_by_client_id(
                session,
                owner_id=owner_id,
                client_message_id=client_message_id,
                lock=False,
            )
            return _row_to_command(row) if row is not None else None

    async def active_for_conversation(
        self,
        conversation_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        async with self._session_factory() as session:
            row = await self._find_active_for_conversation(
                session,
                owner_id=owner_id,
                conversation_id=conversation_id,
                lock=False,
            )
            return _row_to_command(row) if row is not None else None

    async def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> ClaimedCommand | None:
        """Atomically claim the oldest due command.

        Expired claims are fenced into ``recovery_required`` in the same
        transaction before a new row is selected.  A row whose provider or
        billing effect may already have happened is therefore never replayed
        automatically just because its worker disappeared.
        """

        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            await session.execute(
                update(ChatTurnCommandRow)
                .where(
                    ChatTurnCommandRow.state.in_(
                        [
                            ChatTurnCommandState.CLAIMED.value,
                            ChatTurnCommandState.PROCESSING.value,
                        ],
                    ),
                    or_(
                        ChatTurnCommandRow.lease_until.is_(None),
                        ChatTurnCommandRow.lease_until <= current,
                    ),
                )
                .values(
                    state=ChatTurnCommandState.RECOVERY_REQUIRED.value,
                    phase=ChatTurnPhase.RECOVERY_REQUIRED.value,
                    failure_code="worker_lease_expired",
                    failure_message=(
                        "Worker lease expired; provider and billing outcome "
                        "requires reconciliation"
                    ),
                    lease_owner=None,
                    lease_until=None,
                    next_attempt_at=None,
                    updated_at=current,
                    last_heartbeat_at=current,
                ),
            )
            candidate = await session.scalar(
                select(ChatTurnCommandRow)
                .where(
                    ChatTurnCommandRow.state.in_(
                        [
                            ChatTurnCommandState.QUEUED.value,
                            ChatTurnCommandState.RETRY_WAIT.value,
                            ChatTurnCommandState.GENERATED.value,
                            ChatTurnCommandState.COMMITTED.value,
                        ],
                    ),
                    or_(
                        ChatTurnCommandRow.next_attempt_at.is_(None),
                        ChatTurnCommandRow.next_attempt_at <= current,
                    ),
                    or_(
                        ChatTurnCommandRow.state.in_([
                            ChatTurnCommandState.QUEUED.value,
                            ChatTurnCommandState.RETRY_WAIT.value,
                        ]),
                        ChatTurnCommandRow.lease_until.is_(None),
                        ChatTurnCommandRow.lease_until <= current,
                    ),
                )
                .order_by(
                    ChatTurnCommandRow.accepted_at.asc(),
                    ChatTurnCommandRow.turn_id.asc(),
                )
                .limit(1)
                .with_for_update(skip_locked=True),
            )
            if candidate is None:
                await session.commit()
                return None
            previous_state = candidate.state
            candidate.state = (
                previous_state
                if previous_state in {
                    ChatTurnCommandState.GENERATED.value,
                    ChatTurnCommandState.COMMITTED.value,
                }
                else ChatTurnCommandState.CLAIMED.value
            )
            candidate.phase = ChatTurnPhase.CLAIMING.value
            candidate.attempt_count += 1
            candidate.lease_owner = worker_id
            candidate.lease_until = current + timedelta(seconds=lease_seconds)
            candidate.lease_generation += 1
            candidate.updated_at = current
            candidate.last_heartbeat_at = current
            await session.commit()
            await session.refresh(candidate)
            return ClaimedCommand(_row_to_command(candidate))

    async def mark_processing(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        phase: ChatTurnPhase,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
            )
            if row is None or row.state != ChatTurnCommandState.CLAIMED.value:
                return False
            row.state = ChatTurnCommandState.PROCESSING.value
            row.phase = phase.value
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def heartbeat(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        lease_seconds: int,
        phase: ChatTurnPhase,
        now: datetime | None = None,
    ) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
            )
            if row is None or row.state not in {
                ChatTurnCommandState.CLAIMED.value,
                ChatTurnCommandState.PROCESSING.value,
                ChatTurnCommandState.GENERATED.value,
                ChatTurnCommandState.COMMITTED.value,
            }:
                return False
            row.phase = phase.value
            row.lease_until = current + timedelta(seconds=lease_seconds)
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def record_user_turn(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        user_message_id: int,
        user_message_position: int,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
                states=[
                    ChatTurnCommandState.PROCESSING.value,
                    ChatTurnCommandState.GENERATED.value,
                ],
            )
            if row is None:
                return False
            if row.user_message_id is not None and row.user_message_id != user_message_id:
                return False
            row.user_message_id = user_message_id
            row.user_message_position = user_message_position
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def record_assistant_turn(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        assistant_message_id: int,
        assistant_message_position: int,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
                states=[ChatTurnCommandState.GENERATED.value],
            )
            if row is None:
                return False
            if (
                row.assistant_message_id is not None
                and row.assistant_message_id != assistant_message_id
            ):
                return False
            row.assistant_message_id = assistant_message_id
            row.assistant_message_position = assistant_message_position
            row.result_message_id = assistant_message_id
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def mark_generated(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        snapshot_json: str,
        snapshot_hash: str,
        now: datetime | None = None,
    ) -> bool:
        if (
            not snapshot_json.strip()
            or len(snapshot_hash) != 64
            or hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
            != snapshot_hash
        ):
            raise ValueError("generated snapshot must include JSON and SHA-256 hash")
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
                states=[ChatTurnCommandState.PROCESSING.value],
            )
            if row is None:
                return False
            row.state = ChatTurnCommandState.GENERATED.value
            row.phase = ChatTurnPhase.GENERATED.value
            row.generated_snapshot_json = snapshot_json
            row.generated_snapshot_hash = snapshot_hash
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def mark_committed(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        result_message_id: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
                states=[ChatTurnCommandState.GENERATED.value],
            )
            if row is None:
                return False
            row.state = ChatTurnCommandState.COMMITTED.value
            row.phase = ChatTurnPhase.COMMITTED.value
            row.result_message_id = (
                result_message_id
                if result_message_id is not None
                else row.assistant_message_id
            )
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def mark_completed(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        result_message_id: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
            )
            if row is None or row.state not in {
                ChatTurnCommandState.CLAIMED.value,
                ChatTurnCommandState.PROCESSING.value,
                ChatTurnCommandState.GENERATED.value,
                ChatTurnCommandState.COMMITTED.value,
            }:
                return False
            row.state = ChatTurnCommandState.COMPLETED.value
            row.phase = ChatTurnPhase.COMPLETED.value
            row.result_message_id = (
                result_message_id
                if result_message_id is not None
                else row.assistant_message_id
            )
            row.lease_owner = None
            row.lease_until = None
            row.next_attempt_at = None
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def mark_failed(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        failure_code: str,
        failure_message: str,
        retryable: bool,
        retry_after_seconds: int = 0,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
            )
            if row is None or row.state not in {
                ChatTurnCommandState.CLAIMED.value,
                ChatTurnCommandState.PROCESSING.value,
            }:
                return False
            retry = retryable and row.attempt_count < row.max_attempts
            row.state = (
                ChatTurnCommandState.RETRY_WAIT.value
                if retry else ChatTurnCommandState.FAILED.value
            )
            row.phase = (
                ChatTurnPhase.RETRY_WAIT.value
                if retry else ChatTurnPhase.FAILED.value
            )
            row.failure_code = failure_code
            row.failure_message = failure_message
            row.lease_owner = None
            row.lease_until = None
            row.next_attempt_at = (
                current + timedelta(seconds=max(0, retry_after_seconds))
                if retry else None
            )
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def mark_recovery_required(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        failure_code: str,
        failure_message: str,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await self._select_fenced_live(
                session,
                turn_id=turn_id,
                worker_id=worker_id,
                lease_generation=lease_generation,
                now=current,
            )
            if row is None or row.state not in {
                ChatTurnCommandState.CLAIMED.value,
                ChatTurnCommandState.PROCESSING.value,
                ChatTurnCommandState.GENERATED.value,
                ChatTurnCommandState.COMMITTED.value,
            }:
                return False
            row.state = ChatTurnCommandState.RECOVERY_REQUIRED.value
            row.phase = ChatTurnPhase.RECOVERY_REQUIRED.value
            row.failure_code = failure_code
            row.failure_message = failure_message
            row.lease_owner = None
            row.lease_until = None
            row.next_attempt_at = None
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    async def resolve_recovery(
        self,
        *,
        turn_id: str,
        owner_id: str,
        failure_code: str,
        failure_message: str,
        now: datetime | None = None,
    ) -> bool:
        current = _utc(now or datetime.now(timezone.utc))
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ChatTurnCommandRow)
                .where(
                    ChatTurnCommandRow.turn_id == turn_id,
                    ChatTurnCommandRow.owner_id == owner_id,
                )
                .with_for_update(),
            )
            if row is None:
                return False
            if row.state == ChatTurnCommandState.RECOVERY_REQUIRED.value:
                eligible = True
            else:
                eligible = (
                    row.state in {
                        ChatTurnCommandState.CLAIMED.value,
                        ChatTurnCommandState.PROCESSING.value,
                        ChatTurnCommandState.GENERATED.value,
                        ChatTurnCommandState.COMMITTED.value,
                    }
                    and (
                        row.lease_until is None
                        or _utc(row.lease_until) <= current
                    )
                )
            if not eligible:
                await session.rollback()
                return False
            row.state = ChatTurnCommandState.CANCELLED.value
            row.phase = ChatTurnPhase.RECOVERY_REQUIRED.value
            row.failure_code = failure_code
            row.failure_message = failure_message
            row.lease_owner = None
            row.lease_until = None
            row.next_attempt_at = None
            row.lease_generation += 1
            row.updated_at = current
            row.last_heartbeat_at = current
            await session.commit()
            return True

    @staticmethod
    async def _select_fenced_live(
        session: AsyncSession,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        now: datetime,
        states: list[str] | None = None,
    ) -> ChatTurnCommandRow | None:
        """Lock a live claim only while its owner/generation lease is valid."""

        return await session.scalar(
            select(ChatTurnCommandRow)
            .where(
                ChatTurnCommandRow.turn_id == turn_id,
                ChatTurnCommandRow.lease_owner == worker_id,
                ChatTurnCommandRow.lease_generation == lease_generation,
                ChatTurnCommandRow.lease_until > now,
                ChatTurnCommandRow.state.in_(states or [
                    ChatTurnCommandState.CLAIMED.value,
                    ChatTurnCommandState.PROCESSING.value,
                    ChatTurnCommandState.GENERATED.value,
                    ChatTurnCommandState.COMMITTED.value,
                ]),
            )
            .with_for_update(),
        )

    @staticmethod
    async def _find_by_client_id(
        session: AsyncSession,
        *,
        owner_id: str,
        client_message_id: str,
        lock: bool,
    ) -> ChatTurnCommandRow | None:
        stmt = select(ChatTurnCommandRow).where(
            ChatTurnCommandRow.owner_id == owner_id,
            ChatTurnCommandRow.client_message_id == client_message_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return await session.scalar(stmt)

    @staticmethod
    async def _find_active_for_conversation(
        session: AsyncSession,
        *,
        owner_id: str,
        conversation_id: str,
        lock: bool,
    ) -> ChatTurnCommandRow | None:
        stmt = select(ChatTurnCommandRow).where(
            ChatTurnCommandRow.owner_id == owner_id,
            ChatTurnCommandRow.conversation_id == conversation_id,
            ChatTurnCommandRow.state.in_(
                [state.value for state in ACTIVE_COMMAND_STATES],
            ),
        )
        if lock:
            stmt = stmt.with_for_update()
        return await session.scalar(stmt)


__all__ = ["SADurableChatCommandRepository"]
