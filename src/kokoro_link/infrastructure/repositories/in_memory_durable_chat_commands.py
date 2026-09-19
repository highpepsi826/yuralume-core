"""In-memory twin of the durable foreground chat command repository."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

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


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class InMemoryDurableChatCommandRepository(DurableChatCommandRepositoryPort):
    """Parity implementation used by unit tests and DB-less local rigs."""

    def __init__(self) -> None:
        self._commands: dict[str, ChatTurnCommand] = {}
        self._by_client_id: dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        submission: ChatTurnCommandSubmission,
    ) -> CommandSubmissionResult:
        async with self._lock:
            key = (submission.owner_id, submission.client_message_id)
            existing_id = self._by_client_id.get(key)
            if existing_id is not None:
                existing = self._commands[existing_id]
                if existing.payload_hash != submission.payload_hash:
                    return IdempotencyConflict(existing)
                return AcceptedCommand(existing, duplicate=True)

            busy = self._active_for_conversation_unlocked(
                submission.conversation_id,
                submission.owner_id,
            )
            if busy is not None:
                return ConversationBusy(busy)

            now = _utc(submission.accepted_at or datetime.now(timezone.utc))
            command = ChatTurnCommand(
                turn_id=uuid4().hex,
                owner_id=submission.owner_id,
                client_message_id=submission.client_message_id,
                character_id=submission.character_id,
                conversation_id=submission.conversation_id,
                payload_hash=submission.payload_hash,
                payload_version=submission.payload_version,
                payload_json=submission.payload_json,
                state=ChatTurnCommandState.QUEUED,
                phase=ChatTurnPhase.ACCEPTED,
                attempt_count=0,
                max_attempts=submission.max_attempts,
                next_attempt_at=None,
                conversation_revision=submission.conversation_revision,
                user_message_id=None,
                user_message_position=None,
                assistant_message_id=None,
                assistant_message_position=None,
                result_message_id=None,
                generated_snapshot_json=None,
                generated_snapshot_hash=None,
                failure_code=None,
                failure_message=None,
                lease_owner=None,
                lease_until=None,
                lease_generation=0,
                created_at=now,
                updated_at=now,
                accepted_at=now,
                last_heartbeat_at=None,
            )
            self._commands[command.turn_id] = command
            self._by_client_id[key] = command.turn_id
            return AcceptedCommand(command)

    async def get(
        self,
        turn_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        async with self._lock:
            command = self._commands.get(turn_id)
            if command is None or command.owner_id != owner_id:
                return None
            return command

    async def get_by_client_message_id(
        self,
        client_message_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        async with self._lock:
            command_id = self._by_client_id.get((owner_id, client_message_id))
            return self._commands.get(command_id) if command_id is not None else None

    async def active_for_conversation(
        self,
        conversation_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        async with self._lock:
            return self._active_for_conversation_unlocked(conversation_id, owner_id)

    async def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> ClaimedCommand | None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            for command in self._commands.values():
                if (
                    command.state in {
                        ChatTurnCommandState.CLAIMED,
                        ChatTurnCommandState.PROCESSING,
                    }
                    and (
                        command.lease_until is None
                        or command.lease_until <= current
                    )
                ):
                    self._commands[command.turn_id] = replace(
                        command,
                        state=ChatTurnCommandState.RECOVERY_REQUIRED,
                        phase=ChatTurnPhase.RECOVERY_REQUIRED,
                        failure_code="worker_lease_expired",
                        failure_message=(
                            "Worker lease expired; provider and billing outcome "
                            "requires reconciliation"
                        ),
                        lease_owner=None,
                        lease_until=None,
                        updated_at=current,
                        last_heartbeat_at=current,
                    )
            candidates = [
                command
                for command in self._commands.values()
                if command.state in {
                    ChatTurnCommandState.QUEUED,
                    ChatTurnCommandState.RETRY_WAIT,
                    ChatTurnCommandState.GENERATED,
                    ChatTurnCommandState.COMMITTED,
                }
                and (
                    command.next_attempt_at is None
                    or command.next_attempt_at <= current
                )
                and (
                    command.state in {
                        ChatTurnCommandState.QUEUED,
                        ChatTurnCommandState.RETRY_WAIT,
                    }
                    or command.lease_until is None
                    or command.lease_until <= current
                )
            ]
            candidates.sort(key=lambda command: command.accepted_at)
            if not candidates:
                return None
            command = candidates[0]
            updated = replace(
                command,
                state=ChatTurnCommandState.CLAIMED,
                phase=ChatTurnPhase.CLAIMING,
                attempt_count=command.attempt_count + 1,
                lease_owner=worker_id,
                lease_until=current + timedelta(seconds=lease_seconds),
                lease_generation=command.lease_generation + 1,
                updated_at=current,
                last_heartbeat_at=current,
            )
            if command.state in {
                ChatTurnCommandState.GENERATED,
                ChatTurnCommandState.COMMITTED,
            }:
                updated = replace(updated, state=command.state)
            self._commands[command.turn_id] = updated
            return ClaimedCommand(updated)

    async def mark_processing(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        phase: ChatTurnPhase,
        now: datetime | None = None,
    ) -> bool:
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state is not ChatTurnCommandState.CLAIMED:
                return False
            self._commands[turn_id] = replace(
                command,
                state=ChatTurnCommandState.PROCESSING,
                phase=phase,
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state not in {
                ChatTurnCommandState.CLAIMED,
                ChatTurnCommandState.PROCESSING,
                ChatTurnCommandState.GENERATED,
                ChatTurnCommandState.COMMITTED,
            }:
                return False
            self._commands[turn_id] = replace(
                command,
                phase=phase,
                lease_until=current + timedelta(seconds=lease_seconds),
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state not in {
                ChatTurnCommandState.PROCESSING,
                ChatTurnCommandState.GENERATED,
            }:
                return False
            if (
                command.user_message_id is not None
                and command.user_message_id != user_message_id
            ):
                return False
            self._commands[turn_id] = replace(
                command,
                user_message_id=user_message_id,
                user_message_position=user_message_position,
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state is not ChatTurnCommandState.GENERATED:
                return False
            if (
                command.assistant_message_id is not None
                and command.assistant_message_id != assistant_message_id
            ):
                return False
            self._commands[turn_id] = replace(
                command,
                assistant_message_id=assistant_message_id,
                assistant_message_position=assistant_message_position,
                result_message_id=assistant_message_id,
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state not in {
                ChatTurnCommandState.CLAIMED,
                ChatTurnCommandState.PROCESSING,
                ChatTurnCommandState.GENERATED,
                ChatTurnCommandState.COMMITTED,
            }:
                return False
            self._commands[turn_id] = replace(
                command,
                state=ChatTurnCommandState.COMPLETED,
                phase=ChatTurnPhase.COMPLETED,
                result_message_id=(
                    result_message_id
                    if result_message_id is not None
                    else command.assistant_message_id
                ),
                lease_owner=None,
                lease_until=None,
                next_attempt_at=None,
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state is not ChatTurnCommandState.PROCESSING:
                return False
            self._commands[turn_id] = replace(
                command,
                state=ChatTurnCommandState.GENERATED,
                phase=ChatTurnPhase.GENERATED,
                generated_snapshot_json=snapshot_json,
                generated_snapshot_hash=snapshot_hash,
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state is not ChatTurnCommandState.GENERATED:
                return False
            self._commands[turn_id] = replace(
                command,
                state=ChatTurnCommandState.COMMITTED,
                phase=ChatTurnPhase.COMMITTED,
                result_message_id=(
                    result_message_id
                    if result_message_id is not None
                    else command.assistant_message_id
                ),
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state not in {
                ChatTurnCommandState.CLAIMED,
                ChatTurnCommandState.PROCESSING,
            }:
                return False
            retry = retryable and command.attempt_count < command.max_attempts
            self._commands[turn_id] = replace(
                command,
                state=(
                    ChatTurnCommandState.RETRY_WAIT
                    if retry else ChatTurnCommandState.FAILED
                ),
                phase=(
                    ChatTurnPhase.RETRY_WAIT
                    if retry else ChatTurnPhase.FAILED
                ),
                failure_code=failure_code,
                failure_message=failure_message,
                lease_owner=None,
                lease_until=None,
                next_attempt_at=(
                    current + timedelta(seconds=max(0, retry_after_seconds))
                    if retry else None
                ),
                updated_at=current,
                last_heartbeat_at=current,
            )
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
        async with self._lock:
            current = _utc(now or datetime.now(timezone.utc))
            command = self._fenced_live_command(
                turn_id, worker_id, lease_generation, current,
            )
            if command is None or command.state not in {
                ChatTurnCommandState.CLAIMED,
                ChatTurnCommandState.PROCESSING,
                ChatTurnCommandState.GENERATED,
                ChatTurnCommandState.COMMITTED,
            }:
                return False
            self._commands[turn_id] = replace(
                command,
                state=ChatTurnCommandState.RECOVERY_REQUIRED,
                phase=ChatTurnPhase.RECOVERY_REQUIRED,
                failure_code=failure_code,
                failure_message=failure_message,
                lease_owner=None,
                lease_until=None,
                next_attempt_at=None,
                updated_at=current,
                last_heartbeat_at=current,
            )
            return True

    async def set_state_for_test(
        self,
        turn_id: str,
        *,
        state: ChatTurnCommandState,
        owner_id: str,
        now: datetime | None = None,
    ) -> ChatTurnCommand | None:
        """Small test-only transition hook; worker transitions land later."""

        async with self._lock:
            command = self._commands.get(turn_id)
            if command is None or command.owner_id != owner_id:
                return None
            updated = replace(
                command,
                state=state,
                phase=(
                    ChatTurnPhase.COMPLETED
                    if state is ChatTurnCommandState.COMPLETED
                    else command.phase
                ),
                updated_at=_utc(now or datetime.now(timezone.utc)),
            )
            self._commands[turn_id] = updated
        return updated

    def _fenced_live_command(
        self,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        now: datetime,
    ) -> ChatTurnCommand | None:
        command = self._commands.get(turn_id)
        if command is None:
            return None
        if (
            command.lease_owner != worker_id
            or command.lease_generation != lease_generation
            or command.lease_until is None
            or command.lease_until <= now
            or command.state not in {
                ChatTurnCommandState.CLAIMED,
                ChatTurnCommandState.PROCESSING,
                ChatTurnCommandState.GENERATED,
                ChatTurnCommandState.COMMITTED,
            }
        ):
            return None
        return command

    def _active_for_conversation_unlocked(
        self,
        conversation_id: str,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        for command in self._commands.values():
            if (
                command.owner_id == owner_id
                and command.conversation_id == conversation_id
                and command.state in ACTIVE_COMMAND_STATES
            ):
                return command
        return None


__all__ = ["InMemoryDurableChatCommandRepository"]
