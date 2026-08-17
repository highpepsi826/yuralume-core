"""SQL repository coverage for scheduled-promise deduplication."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from kokoro_link.domain.entities.pending_follow_up import PendingFollowUp
from kokoro_link.infrastructure.persistence.engine import build_session_factory
from kokoro_link.infrastructure.persistence.models import PendingFollowUpRow
from kokoro_link.infrastructure.persistence.sa_pending_follow_up_repository import (
    SaPendingFollowUpRepository,
)


UTC = timezone.utc


def _promise(
    *,
    conversation_id: str = "conv-1",
    source_message_content: str = "",
    promise_intent: str = "提醒使用者準備晚上活動",
    scheduled_for: datetime | None = None,
) -> PendingFollowUp:
    return PendingFollowUp.new_promise(
        character_id="char-1",
        conversation_id=conversation_id,
        promise_intent=promise_intent,
        scheduled_for=scheduled_for or datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        source_message_content=source_message_content,
        now=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )


@pytest_asyncio.fixture
async def sql_repo(tmp_path):  # noqa: ANN001
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'promise-dedupe.db'}",
    )
    async with engine.begin() as conn:
        await conn.run_sync(PendingFollowUpRow.__table__.create)
    try:
        yield SaPendingFollowUpRepository(build_session_factory(engine))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_repository_returns_existing_open_promise(sql_repo) -> None:  # noqa: ANN001
    original = _promise(
        conversation_id="conv-original", source_message_content="original source",
    )
    retry = _promise(
        conversation_id="conv-retry", source_message_content="retry source",
    )

    first = await sql_repo.add(original)
    canonical = await sql_repo.add(retry)

    assert first.id == original.id
    assert canonical.id == original.id
    assert [message.content for message in canonical.messages] == [
        "original source", "retry source",
    ]
    rows = await sql_repo.list_open_for_character("char-1")
    assert [row.id for row in rows] == [original.id]
    assert [message.content for message in rows[0].messages] == [
        "original source", "retry source",
    ]


@pytest.mark.asyncio
async def test_sql_repository_merges_different_intents_in_one_delivery_window(
    sql_repo,
) -> None:  # noqa: ANN001
    first = _promise(
        promise_intent="晚上邀請使用者一起慶生",
        source_message_content="晚上八點一起慶生吧",
    )
    second = _promise(
        conversation_id="conv-other",
        promise_intent="晚上主動確認生日約定",
        scheduled_for=datetime(2026, 8, 18, 12, 9, tzinfo=UTC),
        source_message_content="八點左右再找你慶祝",
    )

    canonical = await sql_repo.add(first)
    merged = await sql_repo.add(second)

    assert merged.id == canonical.id
    assert [obligation.intent for obligation in merged.obligations] == [
        "晚上邀請使用者一起慶生",
        "晚上主動確認生日約定",
    ]
    rows = await sql_repo.list_open_for_character("char-1")
    assert [row.id for row in rows] == [canonical.id]


@pytest.mark.asyncio
async def test_sql_repository_allows_same_promise_after_resolution(sql_repo) -> None:  # noqa: ANN001
    original = _promise()
    await sql_repo.add(original)
    await sql_repo.save(original.marked_resolved(
        message_text="done",
        now=datetime(2026, 8, 18, 12, 1, tzinfo=UTC),
    ))

    later = _promise()
    canonical = await sql_repo.add(later)

    assert canonical.id == later.id
    assert canonical.id != original.id


@pytest.mark.asyncio
async def test_sql_repository_concurrent_adds_converge_on_one_row(
    sql_repo,
    monkeypatch,
) -> None:  # noqa: ANN001
    """Both workers pass the pre-insert read; the DB index resolves the race."""
    import kokoro_link.infrastructure.persistence.sa_pending_follow_up_repository as module

    real_find = module._find_open_by_delivery_slot_key
    barrier = asyncio.Barrier(2)

    async def synchronized_find(session, delivery_slot_key):  # noqa: ANN001
        result = await real_find(session, delivery_slot_key)
        if result is None:
            await barrier.wait()
        return result

    monkeypatch.setattr(
        module,
        "_find_open_by_delivery_slot_key",
        synchronized_find,
    )
    first, second = await asyncio.gather(
        sql_repo.add(_promise(conversation_id="conv-a")),
        sql_repo.add(_promise(conversation_id="conv-b")),
    )

    assert first.id == second.id
    rows = await sql_repo.list_open_for_character("char-1")
    assert len(rows) == 1
