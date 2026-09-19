from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kokoro_link.contracts.durable_chat_effects import ChatTurnEffectState
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_effects import (
    InMemoryDurableChatEffectLedger,
)


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_effect_ensure_is_idempotent_and_terminal_completion_is_sticky() -> None:
    ledger = InMemoryDurableChatEffectLedger()
    first = await ledger.ensure(
        turn_id="turn-1",
        effect_kind="post_turn",
        idempotency_key="turn-1:post_turn",
        payload_json='{"assistant_position":1}',
        now=NOW,
    )
    duplicate = await ledger.ensure(
        turn_id="turn-1",
        effect_kind="post_turn",
        idempotency_key="turn-1:post_turn",
        payload_json='{"assistant_position":1}',
        now=NOW,
    )

    assert first == duplicate
    assert first.state is ChatTurnEffectState.PENDING
    assert await ledger.mark_enqueued(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    assert await ledger.mark_running(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    assert not await ledger.mark_running(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    assert await ledger.mark_completed(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    assert not await ledger.mark_failed(
        turn_id="turn-1", effect_kind="post_turn", error="late failure", now=NOW,
    )
    current = await ledger.get(turn_id="turn-1", effect_kind="post_turn")
    assert current is not None
    assert current.state is ChatTurnEffectState.COMPLETED
    assert current.completed_at == NOW


@pytest.mark.asyncio
async def test_running_effect_is_not_automatically_reclaimed() -> None:
    ledger = InMemoryDurableChatEffectLedger()
    await ledger.ensure(
        turn_id="turn-1",
        effect_kind="post_turn",
        idempotency_key="turn-1:post_turn",
        payload_json="{}",
        now=NOW,
    )
    assert await ledger.mark_running(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )

    assert not await ledger.mark_enqueued(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    current = await ledger.get(turn_id="turn-1", effect_kind="post_turn")
    assert current is not None
    assert current.state is ChatTurnEffectState.RUNNING


@pytest.mark.asyncio
async def test_effect_idempotency_key_cannot_cross_turns() -> None:
    ledger = InMemoryDurableChatEffectLedger()
    await ledger.ensure(
        turn_id="turn-1",
        effect_kind="usage",
        idempotency_key="shared-key",
        payload_json="{}",
        now=NOW,
    )
    with pytest.raises(ValueError, match="already belongs"):
        await ledger.ensure(
            turn_id="turn-2",
            effect_kind="usage",
            idempotency_key="shared-key",
            payload_json="{}",
            now=NOW,
        )
