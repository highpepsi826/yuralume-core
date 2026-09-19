"""SQLAlchemy durable effect ledger for foreground chat commands."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from kokoro_link.contracts.durable_chat_effects import (
    ChatTurnEffect,
    ChatTurnEffectState,
    DurableChatEffectLedgerPort,
)
from kokoro_link.infrastructure.persistence.models import ChatTurnEffectRow


def _utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_effect(row: ChatTurnEffectRow) -> ChatTurnEffect:
    return ChatTurnEffect(
        turn_id=row.turn_id,
        effect_kind=row.effect_kind,
        idempotency_key=row.idempotency_key,
        state=ChatTurnEffectState(row.state),
        payload_json=row.payload_json,
        attempt_count=row.attempt_count,
        last_error=row.last_error,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        completed_at=_utc(row.completed_at) if row.completed_at else None,
    )


class SADurableChatEffectLedger(DurableChatEffectLedgerPort):
    def __init__(self, session_factory: sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ensure(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        idempotency_key: str,
        payload_json: str,
        now: datetime | None = None,
    ) -> ChatTurnEffect:
        current = _utc(now)
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ChatTurnEffectRow).where(
                    ChatTurnEffectRow.turn_id == turn_id,
                    ChatTurnEffectRow.effect_kind == effect_kind,
                ),
            )
            if row is not None:
                if row.idempotency_key != idempotency_key:
                    raise ValueError("effect idempotency key conflict")
                return _to_effect(row)
            row = ChatTurnEffectRow(
                turn_id=turn_id,
                effect_kind=effect_kind,
                idempotency_key=idempotency_key,
                state=ChatTurnEffectState.PENDING.value,
                payload_json=payload_json,
                attempt_count=0,
                created_at=current,
                updated_at=current,
            )
            session.add(row)
            try:
                await session.commit()
                await session.refresh(row)
            except IntegrityError:
                await session.rollback()
                row = await session.scalar(
                    select(ChatTurnEffectRow).where(
                        ChatTurnEffectRow.idempotency_key == idempotency_key,
                    ),
                )
                if row is None or row.turn_id != turn_id or row.effect_kind != effect_kind:
                    raise
            return _to_effect(row)

    async def get(self, *, turn_id: str, effect_kind: str) -> ChatTurnEffect | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ChatTurnEffectRow).where(
                    ChatTurnEffectRow.turn_id == turn_id,
                    ChatTurnEffectRow.effect_kind == effect_kind,
                ),
            )
            return _to_effect(row) if row is not None else None

    async def mark_enqueued(self, *, turn_id: str, effect_kind: str, now: datetime | None = None) -> bool:
        return await self._mark(
            turn_id,
            effect_kind,
            ChatTurnEffectState.ENQUEUED,
            now=now,
            allowed_states={ChatTurnEffectState.PENDING},
        )

    async def mark_running(self, *, turn_id: str, effect_kind: str, now: datetime | None = None) -> bool:
        return await self._mark(
            turn_id,
            effect_kind,
            ChatTurnEffectState.RUNNING,
            now=now,
            allowed_states={
                ChatTurnEffectState.PENDING,
                ChatTurnEffectState.ENQUEUED,
            },
        )

    async def mark_completed(self, *, turn_id: str, effect_kind: str, now: datetime | None = None) -> bool:
        return await self._mark(
            turn_id, effect_kind, ChatTurnEffectState.COMPLETED,
            now=now, completed_at=_utc(now),
            allowed_states={
                ChatTurnEffectState.PENDING,
                ChatTurnEffectState.ENQUEUED,
                ChatTurnEffectState.RUNNING,
            },
        )

    async def mark_failed(
        self, *, turn_id: str, effect_kind: str, error: str,
        recovery_required: bool = False, now: datetime | None = None,
    ) -> bool:
        return await self._mark(
            turn_id,
            effect_kind,
            ChatTurnEffectState.RECOVERY_REQUIRED if recovery_required else ChatTurnEffectState.FAILED,
            now=now,
            last_error=(error or "effect failed")[:500],
        )

    async def _mark(
        self,
        turn_id: str,
        effect_kind: str,
        state: ChatTurnEffectState,
        *,
        now: datetime | None,
        completed_at: datetime | None = None,
        last_error: str | None = None,
        allowed_states: set[ChatTurnEffectState] | None = None,
    ) -> bool:
        current = _utc(now)
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ChatTurnEffectRow).where(
                    ChatTurnEffectRow.turn_id == turn_id,
                    ChatTurnEffectRow.effect_kind == effect_kind,
                ).with_for_update(),
            )
            if (
                row is None
                or row.state == ChatTurnEffectState.COMPLETED.value
                or (
                    allowed_states is not None
                    and ChatTurnEffectState(row.state) not in allowed_states
                )
            ):
                return False
            row.state = state.value
            row.attempt_count += 1
            row.last_error = last_error
            row.updated_at = current
            row.completed_at = completed_at
            await session.commit()
            return True


__all__ = ["SADurableChatEffectLedger"]
