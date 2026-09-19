from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kokoro_link.contracts.durable_chat_effects import ChatTurnEffectState
from kokoro_link.infrastructure.persistence.models import ChatTurnEffectRow
from kokoro_link.infrastructure.persistence.sa_durable_chat_effects import (
    SADurableChatEffectLedger,
)


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_sql_effect_ledger_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ChatTurnEffectRow.__table__.create)
    ledger = SADurableChatEffectLedger(
        async_sessionmaker(engine, class_=AsyncSession),
    )

    first = await ledger.ensure(
        turn_id="turn-1",
        effect_kind="post_turn",
        idempotency_key="turn-1:post_turn",
        payload_json="{}",
        now=NOW,
    )
    duplicate = await ledger.ensure(
        turn_id="turn-1",
        effect_kind="post_turn",
        idempotency_key="turn-1:post_turn",
        payload_json="{}",
        now=NOW,
    )
    assert duplicate == first
    assert await ledger.mark_enqueued(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    assert await ledger.mark_running(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    assert await ledger.mark_completed(
        turn_id="turn-1", effect_kind="post_turn", now=NOW,
    )
    current = await ledger.get(turn_id="turn-1", effect_kind="post_turn")
    assert current is not None
    assert current.state is ChatTurnEffectState.COMPLETED
    assert current.attempt_count == 3
    await engine.dispose()
