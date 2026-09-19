"""Durable effect ledger for a foreground chat turn.

The command receipt answers whether the canonical assistant message exists.
This ledger answers the separate question of whether a post-turn or delivery
effect has been registered and applied.  Effect keys are stable for the life
of a command, so retrying a worker cannot create a second logical effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping, Protocol, runtime_checkable


class ChatTurnEffectState(StrEnum):
    PENDING = "pending"
    ENQUEUED = "enqueued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True, slots=True)
class ChatTurnEffect:
    turn_id: str
    effect_kind: str
    idempotency_key: str
    state: ChatTurnEffectState
    payload_json: str
    attempt_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@runtime_checkable
class DurableChatEffectLedgerPort(Protocol):
    async def ensure(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        idempotency_key: str,
        payload_json: str,
        now: datetime | None = None,
    ) -> ChatTurnEffect:
        """Create once or return the existing effect for the stable key."""
        ...

    async def get(
        self,
        *,
        turn_id: str,
        effect_kind: str,
    ) -> ChatTurnEffect | None:
        ...

    async def mark_enqueued(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        now: datetime | None = None,
    ) -> bool:
        ...

    async def mark_running(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        now: datetime | None = None,
    ) -> bool:
        """Claim execution before any non-idempotent effect is applied."""
        ...

    async def mark_completed(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        now: datetime | None = None,
    ) -> bool:
        ...

    async def mark_failed(
        self,
        *,
        turn_id: str,
        effect_kind: str,
        error: str,
        recovery_required: bool = False,
        now: datetime | None = None,
    ) -> bool:
        ...


__all__ = ["ChatTurnEffect", "ChatTurnEffectState", "DurableChatEffectLedgerPort"]
