"""SQL adapter coverage for conditional admin queue writes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from kokoro_link.domain.entities.pending_follow_up import PendingFollowUp
from kokoro_link.infrastructure.persistence.engine import build_session_factory
from kokoro_link.infrastructure.persistence.models import PendingFollowUpRow
from kokoro_link.infrastructure.persistence.sa_pending_follow_up_repository import (
    SaPendingFollowUpRepository,
)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _row(
    *,
    intent: str = "提醒帶卡",
    hours: int = 1,
) -> PendingFollowUp:
    return PendingFollowUp.new_promise(
        character_id="char-1",
        conversation_id="conv-1",
        promise_intent=intent,
        scheduled_for=NOW + timedelta(hours=hours),
        source_message_content="來源約定",
        now=NOW,
    )


@pytest_asyncio.fixture
async def sql_repo(tmp_path):  # noqa: ANN001
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pending-admin.db'}",
    )
    async with engine.begin() as conn:
        await conn.run_sync(PendingFollowUpRow.__table__.create)
    try:
        yield SaPendingFollowUpRepository(build_session_factory(engine))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_strict_admin_insert_rejects_occupied_slot(sql_repo) -> None:  # noqa: ANN001
    first = _row()
    second = _row(intent="另一個意圖")
    assert await sql_repo.add_admin_scheduled_promise(first) is True
    assert await sql_repo.add_admin_scheduled_promise(second) is False
    rows = await sql_repo.list_open_scheduled_promises()
    assert [row.id for row in rows] == [first.id]


@pytest.mark.asyncio
async def test_conditional_admin_edit_and_delete_respect_lifecycle(sql_repo) -> None:  # noqa: ANN001
    row = _row()
    assert await sql_repo.add_admin_scheduled_promise(row) is True

    edited = row.with_admin_edit(
        scheduled_for=NOW + timedelta(hours=2),
        promise_intent="改成兩小時後提醒",
        now=NOW + timedelta(minutes=1),
    )
    assert await sql_repo.save_admin_edit(
        edited,
        expected_updated_at=row.updated_at,
    ) is True
    stored = await sql_repo.get(row.id)
    assert stored is not None
    assert stored.promise_intent == "改成兩小時後提醒"
    assert stored.scheduled_for == NOW + timedelta(hours=2)

    # A stale snapshot cannot overwrite the newer row.
    stale = edited.with_admin_edit(
        scheduled_for=NOW + timedelta(hours=3),
        promise_intent="過期編輯",
        now=NOW + timedelta(minutes=2),
    )
    assert await sql_repo.save_admin_edit(
        stale,
        expected_updated_at=row.updated_at,
    ) is False

    assert await sql_repo.delete_admin_queued_scheduled_promise(
        row.id,
        expected_updated_at=stored.updated_at,
    ) is True
    assert await sql_repo.delete_admin_queued_scheduled_promise(
        row.id,
        expected_updated_at=stored.updated_at,
    ) is False
