from __future__ import annotations

from datetime import date

import pytest

from kokoro_link.application.services.story_beat_reassessment_service import (
    REASSESSMENT_ANCHOR_ERROR,
    REASSESSMENT_COMPLETED,
    REASSESSMENT_PENDING,
    StoryBeatReassessmentService,
)
from kokoro_link.application.services.story_event_service import (
    ArcBeatRealizationReadiness,
)
from kokoro_link.contracts.story_arc import StoryBeatRecheckDecision
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.story_event import StoryEvent
from kokoro_link.domain.value_objects.character_state import CharacterState


class _ArcService:
    def __init__(self, decision: StoryBeatRecheckDecision | None) -> None:
        self.decision = decision
        self.calls: list[tuple[str, date | None]] = []

    async def reassess_pending_beat(self, character, *, beat_id, today=None):  # noqa: ANN001
        self.calls.append((beat_id, today))
        return self.decision


class _EventService:
    def __init__(
        self,
        readiness: ArcBeatRealizationReadiness,
        *,
        event: StoryEvent | None = None,
        existing: StoryEvent | None = None,
    ) -> None:
        self.readiness = readiness
        self.event = event
        self.existing = existing
        self.check_calls: list[tuple[str, bool]] = []
        self.record_calls: list[tuple[str, str, bool]] = []

    async def check_arc_beat_realization(
        self, character, *, beat_id, now=None, player_present=False,  # noqa: ANN001
    ) -> ArcBeatRealizationReadiness:
        self.check_calls.append((beat_id, player_present))
        return self.readiness

    async def record_arc_beat_realization(
        self, character, *, beat_id, narrative, now=None, player_present=False,  # noqa: ANN001
    ) -> StoryEvent | None:
        self.record_calls.append((beat_id, narrative, player_present))
        return self.event

    async def find_arc_beat_event(self, character_id: str, beat_id: str) -> StoryEvent | None:
        return self.existing


def _character() -> Character:
    return Character.create(
        name="Mio",
        summary="",
        personality=[],
        interests=[],
        speaking_style="",
        boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )


def _ready() -> ArcBeatRealizationReadiness:
    return ArcBeatRealizationReadiness(
        allowed=True,
        reason="ready",
        today=date(2026, 8, 30),
    )


@pytest.mark.asyncio
async def test_preview_returns_confirmable_realization_without_writing() -> None:
    arcs = _ArcService(StoryBeatRecheckDecision(
        action="mark_realized",
        reason="近期互動已清楚完成見面",
        narrative="2026-08-30 我們在會場入口見面並交付卡片。",
    ))
    events = _EventService(_ready())
    service = StoryBeatReassessmentService(
        story_arc_service=arcs,  # type: ignore[arg-type]
        story_event_service=events,  # type: ignore[arg-type]
    )

    result = await service.preview(_character(), beat_id="beat-1")

    assert result.status == REASSESSMENT_COMPLETED
    assert result.can_confirm is True
    assert result.narrative == "2026-08-30 我們在會場入口見面並交付卡片。"
    assert arcs.calls == [("beat-1", date(2026, 8, 30))]
    assert events.record_calls == []


@pytest.mark.asyncio
async def test_preview_stops_before_model_when_anchor_is_invalid() -> None:
    arcs = _ArcService(StoryBeatRecheckDecision(action="mark_realized"))
    events = _EventService(ArcBeatRealizationReadiness(
        allowed=False,
        reason="first_meeting_anchor_unavailable",
    ))
    service = StoryBeatReassessmentService(
        story_arc_service=arcs,  # type: ignore[arg-type]
        story_event_service=events,  # type: ignore[arg-type]
    )

    result = await service.preview(_character(), beat_id="beat-1")

    assert result.status == REASSESSMENT_ANCHOR_ERROR
    assert result.reason == "first_meeting_anchor_unavailable"
    assert result.can_confirm is False
    assert arcs.calls == []


@pytest.mark.asyncio
async def test_preview_keeps_non_realization_actions_read_only() -> None:
    arcs = _ArcService(StoryBeatRecheckDecision(
        action="delay_beat", reason="等待更自然的時機", days=2,
    ))
    events = _EventService(_ready())
    service = StoryBeatReassessmentService(
        story_arc_service=arcs,  # type: ignore[arg-type]
        story_event_service=events,  # type: ignore[arg-type]
    )

    result = await service.preview(_character(), beat_id="beat-1")

    assert result.status == REASSESSMENT_PENDING
    assert result.reason == "等待更自然的時機"
    assert result.can_confirm is False


@pytest.mark.asyncio
async def test_confirm_uses_player_present_story_event_path_and_is_idempotent() -> None:
    character = _character()
    existing = StoryEvent.create(
        character_id=character.id,
        date="2026-08-30",
        arc_beat_id="beat-1",
        narrative="2026-08-30 我們見面了。",
    )
    service = StoryBeatReassessmentService(
        story_arc_service=_ArcService(None),  # type: ignore[arg-type]
        story_event_service=_EventService(_ready(), existing=existing),  # type: ignore[arg-type]
    )

    event = await service.confirm(
        character,
        beat_id="beat-1",
        narrative="2026-08-30 我們見面了。",
    )

    assert event == existing
