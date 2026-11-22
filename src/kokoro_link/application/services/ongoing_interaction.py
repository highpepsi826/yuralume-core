"""Derived "ongoing interaction" state (I-21, phase 1).

Whether the character and the player are mid-conversation is *derived* from
structured message timestamps, roles and kinds -- never from reading message
text -- and never persisted. It expires on its own once ``hold`` has passed
since the character's last reply, so a player who vanishes leaves the
character free to follow its own schedule again.

A busy-defer brief acknowledgement counts as an ordinary character reply:
it is indistinguishable from one in stored data, and it cannot chain a second
deferral because ``ChatService._maybe_defer_reply`` cancels any open defer row
before the decider is consulted (see ``ONGOING_INTERACTION_HOLD_REFERENCE.md``
§4.1 and §10).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from kokoro_link.domain.entities.conversation import (
    Message,
    MessageContentMode,
    MessageKind,
    MessageRole,
)
from kokoro_link.domain.entities.schedule import ScheduleActivity
from kokoro_link.domain.value_objects.ongoing_interaction import (
    OngoingInteraction,
)

ONGOING_INTERACTION_HOLD = timedelta(minutes=15)
"""How long after the character's last reply the interaction still counts as
ongoing. One value for every surface (stage and messaging)."""

ONGOING_INTERACTION_MAX_LOOKBACK = timedelta(hours=6)
"""A streak is never traced further back than this before the last reply."""

ONGOING_INTERACTION_REPLY_EXCERPT_CHARS = 80

ONGOING_INTERACTION_STREAK_SCAN_LIMIT = 200
"""How many recent messages to read when the streak start lies outside the
ordinary prompt window (timestamps and kinds only are consulted)."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def resolve_ongoing_interaction(
    *,
    recent_messages: Sequence[Message],
    current_activity: ScheduleActivity | None,
    now: datetime,
    hold: timedelta = ONGOING_INTERACTION_HOLD,
    max_lookback: timedelta = ONGOING_INTERACTION_MAX_LOOKBACK,
) -> OngoingInteraction | None:
    """Return the ongoing interaction at ``now`` or ``None``.

    ``recent_messages`` must be chronological and must not include the turn
    currently being answered; a trailing player message is harmless because
    only the latest character reply that follows a player message counts.
    """
    chat = [m for m in recent_messages if m.kind is MessageKind.CHAT]
    seen_user = False
    last_reply_candidate: int | None = None
    for index, message in enumerate(chat):
        if message.role is MessageRole.USER:
            seen_user = True
        elif message.role is MessageRole.ASSISTANT and seen_user:
            last_reply_candidate = index
    reply_index = last_reply_candidate
    if reply_index is None:
        return None
    reply = chat[reply_index]
    now_utc = _aware(now)
    last_exchange_at = _aware(reply.created_at)
    elapsed = now_utc - last_exchange_at
    if elapsed > hold:
        return None

    floor = last_exchange_at - max_lookback
    start_index = reply_index
    reaches_window_start = False
    capped = False
    while True:
        if start_index == 0:
            reaches_window_start = True
            break
        earlier = _aware(chat[start_index - 1].created_at)
        later = _aware(chat[start_index].created_at)
        if later - earlier > hold:
            break
        if earlier < floor:
            capped = True
            break
        start_index -= 1
    streak_started_at = _aware(chat[start_index].created_at)
    if capped or streak_started_at < floor:
        streak_started_at = floor
        reaches_window_start = False

    started_during = (
        current_activity is not None
        and _aware(current_activity.start_at) > streak_started_at
    )
    excerpt = ""
    if reply.content_mode is MessageContentMode.NORMAL:
        excerpt = " ".join((reply.content or "").split())
        if len(excerpt) > ONGOING_INTERACTION_REPLY_EXCERPT_CHARS:
            excerpt = excerpt[:ONGOING_INTERACTION_REPLY_EXCERPT_CHARS].rstrip() + "…"
    return OngoingInteraction(
        last_reply_excerpt=excerpt,
        last_exchange_at=last_exchange_at,
        minutes_since=max(0, int(elapsed.total_seconds() // 60)),
        streak_started_at=streak_started_at,
        activity_started_during_streak=started_during,
        streak_reaches_window_start=reaches_window_start,
    )


def minutes_since_active_conversation(
    recent_messages: Sequence[Message],
    *,
    now: datetime,
    hold: timedelta = ONGOING_INTERACTION_HOLD,
) -> int | None:
    """Minutes since the last chat exchange, when the pair is mid-conversation.

    "Mid-conversation" is either of two structural facts, both read from
    roles, kinds and timestamps only (never text):

    * :func:`resolve_ongoing_interaction` -- the character replied to the
      player within ``hold``; or
    * the latest chat message is the player's own and is within ``hold``
      (a reply may still be generating, so no character reply exists yet).

    ``None`` when neither holds. ``recent_messages`` must be chronological;
    messages stamped after ``now`` are ignored, so the same call answers
    "were they talking at instant T" for a past T (I-19 Part 3c).
    """
    now_utc = _aware(now)
    chat = [
        m for m in recent_messages
        if m.kind is MessageKind.CHAT and _aware(m.created_at) <= now_utc
    ]
    ongoing = resolve_ongoing_interaction(
        recent_messages=chat, current_activity=None, now=now_utc, hold=hold,
    )
    if ongoing is not None:
        return ongoing.minutes_since
    if not chat:
        return None
    latest = chat[-1]
    if latest.role is MessageRole.USER:
        elapsed = now_utc - _aware(latest.created_at)
        if elapsed <= hold:
            return max(0, int(elapsed.total_seconds() // 60))
    return None


__all__ = [
    "minutes_since_active_conversation",
    "ONGOING_INTERACTION_HOLD",
    "ONGOING_INTERACTION_MAX_LOOKBACK",
    "ONGOING_INTERACTION_STREAK_SCAN_LIMIT",
    "OngoingInteraction",
    "resolve_ongoing_interaction",
]
