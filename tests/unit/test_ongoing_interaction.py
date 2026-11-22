"""Derived ongoing-interaction state (I-21 phase 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kokoro_link.application.services.ongoing_interaction import (
    ONGOING_INTERACTION_HOLD,
    resolve_ongoing_interaction,
)
from kokoro_link.domain.entities.conversation import (
    Message,
    MessageContentMode,
    MessageKind,
    MessageRole,
)
from kokoro_link.domain.entities.schedule import ScheduleActivity

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def _msg(role, minutes_ago, *, kind=MessageKind.CHAT, mode=MessageContentMode.NORMAL, text="hi"):
    return Message(
        role=role, content=text, kind=kind, content_mode=mode,
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


U, A = MessageRole.USER, MessageRole.ASSISTANT


def _activity(start_minutes_ago, busy=0.9):
    return ScheduleActivity.create(
        start_at=NOW - timedelta(minutes=start_minutes_ago),
        end_at=NOW + timedelta(minutes=30),
        description="洗澡", category="hygiene", busy_score=busy,
    )


def _resolve(messages, activity=None, **kw):
    return resolve_ongoing_interaction(
        recent_messages=messages, current_activity=activity, now=NOW, **kw,
    )


def test_exchange_within_hold_is_ongoing() -> None:
    r = _resolve([_msg(U, 5), _msg(A, 3)])
    assert r is not None
    assert r.minutes_since == 3


def test_exchange_past_hold_is_none() -> None:
    assert _resolve([_msg(U, 40), _msg(A, 30)]) is None
    edge = int(ONGOING_INTERACTION_HOLD.total_seconds() // 60) + 1
    assert _resolve([_msg(U, edge + 2), _msg(A, edge)]) is None


def test_only_assistant_proactive_messages_is_none() -> None:
    assert _resolve([_msg(A, 3)]) is None


def test_player_without_reply_is_none() -> None:
    assert _resolve([_msg(U, 3)]) is None


def test_tool_only_and_scene_narration_do_not_count() -> None:
    msgs = [
        _msg(U, 5),
        _msg(A, 3, kind=MessageKind.TOOL_ONLY),
        _msg(A, 2, kind=MessageKind.SCENE_NARRATION),
    ]
    assert _resolve(msgs) is None


def test_brief_ack_counts_as_ordinary_reply() -> None:
    # A busy-defer ack is stored as a plain assistant CHAT message.
    r = _resolve([_msg(U, 4), _msg(A, 3, text="等我一下")])
    assert r is not None


def test_current_turn_user_message_not_counted() -> None:
    # Trailing player message (this turn) does not create or break the pair.
    r = _resolve([_msg(U, 6), _msg(A, 5), _msg(U, 0)])
    assert r is not None and r.minutes_since == 5
    assert _resolve([_msg(U, 0)]) is None


def test_streak_walks_back_to_first_gap_over_hold() -> None:
    msgs = [
        _msg(U, 90), _msg(A, 89),          # old, separate streak
        _msg(U, 30), _msg(A, 25), _msg(U, 12), _msg(A, 10),
    ]
    r = _resolve(msgs)
    assert r is not None
    assert r.streak_started_at == NOW - timedelta(minutes=30)
    assert r.streak_reaches_window_start is False


def test_streak_reaching_window_start_is_flagged() -> None:
    r = _resolve([_msg(U, 12), _msg(A, 10)])
    assert r is not None and r.streak_reaches_window_start is True


def test_lookback_cap() -> None:
    msgs = []
    for k in range(0, 8 * 60, 10):  # 8 hours of 10-minute steps
        msgs.append(_msg(U if (k // 10) % 2 else A, 480 - k))
    msgs.append(_msg(U, 11))
    msgs.append(_msg(A, 10))
    r = _resolve(msgs)
    assert r is not None
    assert r.streak_started_at >= NOW - timedelta(minutes=10) - timedelta(hours=6)
    assert r.streak_reaches_window_start is False


def test_activity_started_during_streak_holds_on_later_turns() -> None:
    activity = _activity(start_minutes_ago=8)
    first = _resolve([_msg(U, 12), _msg(A, 10)], activity)
    second = _resolve([_msg(U, 12), _msg(A, 10), _msg(U, 6), _msg(A, 5)], activity)
    third = _resolve(
        [_msg(U, 12), _msg(A, 10), _msg(U, 6), _msg(A, 5), _msg(U, 2), _msg(A, 1)],
        activity,
    )
    assert all(r is not None and r.activity_started_during_streak for r in (first, second, third))


def test_activity_before_streak_is_not_flagged() -> None:
    r = _resolve([_msg(U, 12), _msg(A, 10)], _activity(start_minutes_ago=60))
    assert r is not None and r.activity_started_during_streak is False


def test_excerpt_only_for_normal_content() -> None:
    r = _resolve([_msg(U, 5), _msg(A, 3, text="a" * 200)])
    assert r is not None and len(r.last_reply_excerpt) <= 81 and r.last_reply_excerpt
    n = _resolve([_msg(U, 5), _msg(A, 3, mode=MessageContentMode.NSFW)])
    assert n is not None and n.last_reply_excerpt == ""
