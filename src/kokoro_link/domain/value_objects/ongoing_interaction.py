"""Value object for the derived "ongoing interaction" state (I-21).

Pure data; derivation lives in
``application.services.ongoing_interaction``. Never persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kokoro_link.domain.entities.schedule import (
    ScheduleActivity,
    has_live_operator_commitment,
)


@dataclass(frozen=True, slots=True)
class OngoingInteraction:
    last_exchange_at: datetime
    """When the character last replied to the player."""
    minutes_since: int
    streak_started_at: datetime
    """Start of the unbroken run of chat messages ending at that reply."""
    activity_started_during_streak: bool
    """The current activity only began after ``streak_started_at``."""
    streak_reaches_window_start: bool = False
    """Internal: the run was still unbroken at the oldest message supplied,
    so a wider read could move ``streak_started_at`` earlier."""
    activity_at_streak_start: ScheduleActivity | None = None
    """What the schedule said at ``streak_started_at`` (filled by the caller
    from a read-only schedule lookup; ``None`` when unknown)."""
    last_reply_excerpt: str = ""
    """Short quote of the character's last reply, only when it is NORMAL
    content (empty otherwise, so restricted text never reaches a decider
    that may not be routed to an NSFW-capable model)."""


def schedule_yields_to_conversation(
    ongoing: "OngoingInteraction | None",
    current: ScheduleActivity | None,
) -> bool:
    """``True`` for the "case two" rendering: the current activity only came
    due while the interaction was already running, so the conversation, not
    the plan, decides where the character is.

    An activity that already carries the player as a participant is the
    *outcome* of the conversation (for example a shared plan the post-turn
    just wrote), not a plan competing with it, so it never yields."""
    if ongoing is None or current is None:
        return False
    if not ongoing.activity_started_during_streak:
        return False
    return not has_live_operator_commitment(current)


@dataclass(frozen=True, slots=True)
class BoundaryCrossing:
    """Facts for a turn whose interaction ran across a schedule boundary
    (I-21 phase 2, Part A).

    Derived inside ``ChatService._do_post_turn`` -- never persisted, never
    carried in the post-turn job payload -- and handed to the post-turn
    processor so it can be asked, explicitly, whether the schedule should be
    rewritten to match what actually happened in the conversation.
    """

    streak_started_at: datetime
    """Start of the unbroken run of chat messages ending at this turn."""
    activity_at_streak_start: ScheduleActivity | None
    """What the schedule said at ``streak_started_at`` (``None`` = nothing)."""
    current_activity: ScheduleActivity
    """The planned activity that came due during the interaction."""
    judged_at: datetime
    """The turn's own instant, not the post-turn job's wall clock."""
