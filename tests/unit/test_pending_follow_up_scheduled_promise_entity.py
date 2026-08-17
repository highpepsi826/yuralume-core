"""Entity-level tests for the scheduled-promise PendingFollowUp variant."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    PendingFollowUpKind,
    PendingFollowUpStatus,
    group_open_scheduled_promise_duplicates,
)
from kokoro_link.domain.entities.conversation import MessageContentMode


UTC = timezone.utc


def test_new_promise_creates_scheduled_kind() -> None:
    row = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="叫使用者起床",
        scheduled_for=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        source_message_content="明天 10 點叫我起床",
        source_content_mode=MessageContentMode.NSFW,
    )
    assert row.kind == PendingFollowUpKind.SCHEDULED_PROMISE
    assert row.is_scheduled_promise is True
    assert row.promise_intent == "叫使用者起床"
    assert len(row.dedupe_key) == 64
    assert len(row.delivery_slot_key) == 64
    assert len(row.source_turn_key) == 64
    assert [obligation.intent for obligation in row.obligations] == ["叫使用者起床"]
    assert row.status == PendingFollowUpStatus.QUEUED
    # source text becomes the entity's first (and only) message
    assert row.messages[0].content == "明天 10 點叫我起床"
    assert row.messages[0].content_mode is MessageContentMode.NSFW


def test_new_promise_requires_intent() -> None:
    with pytest.raises(ValueError):
        PendingFollowUp.new_promise(
            character_id="c1",
            conversation_id="conv1",
            promise_intent="   ",
            scheduled_for=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        )


def test_new_promise_requires_tz_aware_time() -> None:
    with pytest.raises(ValueError):
        PendingFollowUp.new_promise(
            character_id="c1",
            conversation_id="conv1",
            promise_intent="叫起床",
            scheduled_for=datetime(2026, 5, 18, 10, 0),  # naive
        )


def test_new_promise_synthesises_message_when_source_blank() -> None:
    """Entity invariant requires at least one queued message, even when
    the post-turn LLM didn't capture the user's exact wording."""
    row = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="提醒喝水",
        scheduled_for=datetime(2026, 5, 18, 14, 0, tzinfo=UTC),
        source_message_content="",
    )
    assert len(row.messages) == 1
    # Falls back to intent so the dispatcher still has something to log.
    assert row.messages[0].content == "提醒喝水"


def test_promise_dedupe_key_normalizes_case_and_scheduled_minute() -> None:
    first = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="Send   a photo",
        scheduled_for=datetime(2026, 5, 18, 10, 0, 1, tzinfo=UTC),
    )
    retry = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv-other",
        promise_intent="send a photo",
        scheduled_for=datetime(2026, 5, 18, 10, 0, 59, tzinfo=UTC),
    )
    changed_time = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="send a photo",
        scheduled_for=datetime(2026, 5, 18, 10, 1, tzinfo=UTC),
    )

    assert retry.dedupe_key == first.dedupe_key
    assert changed_time.dedupe_key != first.dedupe_key


def test_delivery_slot_groups_differently_worded_promises_in_same_window() -> None:
    first = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="晚上邀請使用者一起慶生",
        scheduled_for=datetime(2026, 5, 18, 20, 0, tzinfo=UTC),
        source_message_content="晚上八點一起慶生吧",
    )
    retry = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv-other",
        promise_intent="晚上主動確認生日約定",
        scheduled_for=datetime(2026, 5, 18, 20, 9, tzinfo=UTC),
        source_message_content="八點左右再找你慶祝",
    )
    later = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="晚上主動確認生日約定",
        scheduled_for=datetime(2026, 5, 18, 20, 15, tzinfo=UTC),
    )

    assert retry.delivery_slot_key == first.delivery_slot_key
    assert later.delivery_slot_key != first.delivery_slot_key


def test_legacy_busy_defer_default_unchanged() -> None:
    """The legacy busy-defer constructor must still produce kind=BUSY_DEFER."""
    from kokoro_link.domain.entities.pending_follow_up import (
        PendingFollowUpMessage,
    )

    row = PendingFollowUp.new(
        character_id="c1",
        conversation_id="conv1",
        first_message=PendingFollowUpMessage.new(content="msg"),
        brief_reply="等我忙完",
        defer_reason="會議中",
        scheduled_for=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
    )
    assert row.kind == PendingFollowUpKind.BUSY_DEFER
    assert row.is_scheduled_promise is False
    assert row.promise_intent == ""
    assert row.dedupe_key == ""
    assert row.delivery_slot_key == ""
    assert row.obligations == ()


def test_duplicate_report_groups_legacy_open_promises_without_mutating_them() -> None:
    from dataclasses import replace

    first = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv-a",
        promise_intent="提醒喝水",
        scheduled_for=datetime(2026, 5, 18, 14, 0, tzinfo=UTC),
        now=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
    )
    second = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv-b",
        promise_intent="提醒喝水",
        scheduled_for=datetime(2026, 5, 18, 14, 0, tzinfo=UTC),
        now=datetime(2026, 5, 18, 10, 5, tzinfo=UTC),
    )
    # Blank keys model old rows imported before the unique-index migration.
    legacy_rows = (
        replace(first, dedupe_key="", delivery_slot_key=""),
        replace(second, dedupe_key="", delivery_slot_key=""),
    )

    groups = group_open_scheduled_promise_duplicates(legacy_rows)

    assert len(groups) == 1
    assert groups[0].canonical.id == first.id
    assert [row.id for row in groups[0].rows] == [first.id, second.id]
    assert all(row.dedupe_key == "" for row in legacy_rows)
    assert all(row.delivery_slot_key == "" for row in legacy_rows)


def test_same_slot_merges_distinct_obligations_into_one_callback() -> None:
    first = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv1",
        promise_intent="晚上邀請使用者一起慶生",
        scheduled_for=datetime(2026, 5, 18, 20, 0, tzinfo=UTC),
        source_message_content="晚上八點一起慶生吧",
    )
    second = PendingFollowUp.new_promise(
        character_id="c1",
        conversation_id="conv2",
        promise_intent="晚上主動確認生日約定",
        scheduled_for=datetime(2026, 5, 18, 20, 7, tzinfo=UTC),
        source_message_content="八點左右再找你慶祝",
    )

    merged = first.merged_scheduled_promise_context(second)

    assert merged.scheduled_for == first.scheduled_for
    assert [obligation.intent for obligation in merged.obligations] == [
        "晚上邀請使用者一起慶生",
        "晚上主動確認生日約定",
    ]
    assert "；" in merged.promise_intent
