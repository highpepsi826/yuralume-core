"""Operator-triggered, confirmation-gated reassessment of pending beats."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kokoro_link.application.services.story_arc_service import StoryArcService
from kokoro_link.application.services.story_event_service import StoryEventService
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.story_event import StoryEvent


REASSESSMENT_COMPLETED = "completed"
REASSESSMENT_PENDING = "pending"
REASSESSMENT_ANCHOR_ERROR = "anchor_error"


@dataclass(frozen=True, slots=True)
class StoryBeatReassessment:
    """Read-only proposal shown to the operator before any write occurs."""

    status: str
    reason: str
    narrative: str | None = None
    can_confirm: bool = False


class StoryBeatReassessmentService:
    """Compose evidence review with the established StoryEvent write path."""

    def __init__(
        self,
        *,
        story_arc_service: StoryArcService,
        story_event_service: StoryEventService,
    ) -> None:
        self._arcs = story_arc_service
        self._events = story_event_service

    async def preview(
        self,
        character: Character,
        *,
        beat_id: str,
        now: datetime | None = None,
    ) -> StoryBeatReassessment:
        """Produce an evidence-only proposal for a pending beat.

        Readiness is checked before the model call so an invalid first-meeting
        schedule cannot be papered over by an attractive model narrative.
        """
        readiness = await self._events.check_arc_beat_realization(
            character,
            beat_id=beat_id,
            now=now,
            player_present=True,
        )
        if not readiness.allowed:
            return StoryBeatReassessment(
                status=REASSESSMENT_ANCHOR_ERROR,
                reason=readiness.reason,
            )
        decision = await self._arcs.reassess_pending_beat(
            character,
            beat_id=beat_id,
            today=readiness.today,
        )
        if decision is None:
            return StoryBeatReassessment(
                status=REASSESSMENT_PENDING,
                reason="recheck_unavailable",
            )
        if decision.action == "mark_realized" and decision.narrative:
            return StoryBeatReassessment(
                status=REASSESSMENT_COMPLETED,
                reason=decision.reason or "interaction_evidence_confirmed",
                narrative=decision.narrative,
                can_confirm=True,
            )
        return StoryBeatReassessment(
            status=REASSESSMENT_PENDING,
            reason=decision.reason or decision.action or "keep_pending",
        )

    async def confirm(
        self,
        character: Character,
        *,
        beat_id: str,
        narrative: str,
        now: datetime | None = None,
    ) -> StoryEvent | None:
        """Persist an operator-confirmed proposal through the normal path."""
        event = await self._events.record_arc_beat_realization(
            character,
            beat_id=beat_id,
            narrative=narrative,
            now=now,
            player_present=True,
        )
        if event is not None:
            return event
        # A simultaneous normal chat completion is not an error to the
        # operator; return its existing StoryEvent instead of duplicating it.
        return await self._events.find_arc_beat_event(character.id, beat_id)
