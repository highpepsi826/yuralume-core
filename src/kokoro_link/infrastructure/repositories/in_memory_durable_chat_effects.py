"""In-memory effect-ledger twin for durable chat tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from kokoro_link.contracts.durable_chat_effects import (
    ChatTurnEffect,
    ChatTurnEffectState,
    DurableChatEffectLedgerPort,
)


def _utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class InMemoryDurableChatEffectLedger(DurableChatEffectLedgerPort):
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], ChatTurnEffect] = {}
        self._by_key: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    async def ensure(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        idempotency_key: str,
        payload_json: str,
        now: datetime | None = None,
    ) -> ChatTurnEffect:
        async with self._lock:
            key = (turn_id, effect_kind)
            existing = self._rows.get(key)
            if existing is not None:
                if existing.idempotency_key != idempotency_key:
                    raise ValueError("effect idempotency key conflict")
                return existing
            owner = self._by_key.get(idempotency_key)
            if owner is not None and owner != key:
                raise ValueError("effect idempotency key already belongs to another turn")
            current = _utc(now)
            effect = ChatTurnEffect(
                turn_id=turn_id,
                effect_kind=effect_kind,
                idempotency_key=idempotency_key,
                state=ChatTurnEffectState.PENDING,
                payload_json=payload_json,
                attempt_count=0,
                last_error=None,
                created_at=current,
                updated_at=current,
                completed_at=None,
            )
            self._rows[key] = effect
            self._by_key[idempotency_key] = key
            return effect

    async def get(self, *, turn_id: str, effect_kind: str) -> ChatTurnEffect | None:
        async with self._lock:
            return self._rows.get((turn_id, effect_kind))

    async def mark_enqueued(
        self, *, turn_id: str, effect_kind: str, now: datetime | None = None,
    ) -> bool:
        return await self._mark(
            turn_id=turn_id, effect_kind=effect_kind,
            state=ChatTurnEffectState.ENQUEUED, now=now,
            allowed_states={ChatTurnEffectState.PENDING},
        )

    async def mark_running(
        self, *, turn_id: str, effect_kind: str, now: datetime | None = None,
    ) -> bool:
        return await self._mark(
            turn_id=turn_id,
            effect_kind=effect_kind,
            state=ChatTurnEffectState.RUNNING,
            now=now,
            allowed_states={
                ChatTurnEffectState.PENDING,
                ChatTurnEffectState.ENQUEUED,
            },
        )

    async def mark_completed(
        self, *, turn_id: str, effect_kind: str, now: datetime | None = None,
    ) -> bool:
        return await self._mark(
            turn_id=turn_id, effect_kind=effect_kind,
            state=ChatTurnEffectState.COMPLETED, now=now,
            completed_at=_utc(now),
            allowed_states={
                ChatTurnEffectState.PENDING,
                ChatTurnEffectState.ENQUEUED,
                ChatTurnEffectState.RUNNING,
            },
        )

    async def mark_failed(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        error: str,
        recovery_required: bool = False,
        now: datetime | None = None,
    ) -> bool:
        return await self._mark(
            turn_id=turn_id,
            effect_kind=effect_kind,
            state=(
                ChatTurnEffectState.RECOVERY_REQUIRED
                if recovery_required else ChatTurnEffectState.FAILED
            ),
            now=now,
            last_error=(error or "effect failed")[:500],
        )

    async def _mark(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        state: ChatTurnEffectState,
        now: datetime | None,
        completed_at: datetime | None = None,
        last_error: str | None = None,
        allowed_states: set[ChatTurnEffectState] | None = None,
    ) -> bool:
        async with self._lock:
            key = (turn_id, effect_kind)
            row = self._rows.get(key)
            if (
                row is None
                or row.state is ChatTurnEffectState.COMPLETED
                or (
                    allowed_states is not None
                    and row.state not in allowed_states
                )
            ):
                return False
            self._rows[key] = replace(
                row,
                state=state,
                attempt_count=row.attempt_count + 1,
                last_error=last_error,
                updated_at=_utc(now),
                completed_at=completed_at,
            )
            return True


__all__ = ["InMemoryDurableChatEffectLedger"]
