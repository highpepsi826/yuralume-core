"""Focused regression coverage for exact-key post-turn reconciliation."""

from datetime import date, datetime, timezone

import pytest

from kokoro_link.application.dto.goal import CreateGoalRequest, UpdateGoalRequest
from kokoro_link.application.services.goal_service import GoalService
from kokoro_link.application.services.schedule_service import ScheduleService
from kokoro_link.application.services.story_arc_service import ArcAdjustment, StoryArcService
from kokoro_link.contracts.post_turn import GoalAdjustmentSignal, ScheduleAdjustment
from kokoro_link.domain.entities.character_goal import CharacterGoal
from kokoro_link.domain.entities.schedule import DailySchedule, ScheduleActivity
from kokoro_link.domain.entities.story_arc import (
    ARC_ACTIVE,
    BEAT_PENDING,
    BEAT_REALIZED,
    StoryArc,
    StoryArcBeat,
)
from kokoro_link.infrastructure.repositories.in_memory_goals import InMemoryGoalRepository
from kokoro_link.infrastructure.repositories.in_memory_schedules import InMemoryScheduleRepository
from kokoro_link.infrastructure.repositories.in_memory_story_arcs import InMemoryStoryArcRepository


UTC = timezone.utc


class _Planner:
    async def plan_day(self, **_: object) -> DailySchedule:  # pragma: no cover
        raise AssertionError("reconciliation must not invoke planner")


def _activity(day: date, hour: int, *, key: str | None = None, first: bool = False, memorialized: bool = False) -> ScheduleActivity:
    return ScheduleActivity.create(
        start_at=datetime(day.year, day.month, day.day, hour, tzinfo=UTC),
        end_at=datetime(day.year, day.month, day.day, hour + 1, tzinfo=UTC),
        description=f"activity {hour}", category="social", commitment_key=key,
        is_first_meeting=first, memorialized=memorialized,
    )


def _schedule(character_id: str, day: date, activities: list[ScheduleActivity]) -> DailySchedule:
    return DailySchedule.create(character_id=character_id, date_=day, activities=activities)


@pytest.mark.asyncio
async def test_schedule_key_only_move_and_first_meeting_uniqueness() -> None:
    repo = InMemoryScheduleRepository()
    old_day = date(2026, 8, 30)
    new_day = date(2026, 8, 31)
    old_first = _activity(old_day, 16, key="old", first=True)
    moving = _activity(old_day, 15, key="meet", first=False)
    existing_1630 = _activity(new_day, 16)
    await repo.save(_schedule("c1", old_day, [old_first, moving]))
    await repo.save(_schedule("c1", new_day, [existing_1630]))
    service = ScheduleService(repository=repo, planner=_Planner(), local_tz=UTC)

    await service.reconcile_commitment_adjustments(
        character_id="c1",
        adjustments=[ScheduleAdjustment(
            action="modify", commitment_key="meet", is_first_meeting=True,
            target_date_iso="2026-08-31", start="18:00", end="19:00",
        )],
    )

    source = await repo.get("c1", old_day)
    destination = await repo.get("c1", new_day)
    assert source is not None and destination is not None
    assert [a.commitment_key for a in source.activities] == ["old"]
    assert old_first.is_first_meeting is True  # original object was not mutated
    stored_old = source.activities[0]
    assert stored_old.is_first_meeting is False
    assert sorted((a.start_at.hour, a.commitment_key) for a in destination.activities) == [(16, None), (18, "meet")]
    assert [a.is_first_meeting for a in destination.activities] == [False, True]


@pytest.mark.asyncio
async def test_schedule_does_not_modify_memorialized_or_ambiguous_keys() -> None:
    repo = InMemoryScheduleRepository()
    day = date(2026, 8, 31)
    memorialized = _activity(day, 10, key="locked", memorialized=True)
    first = _activity(day, 11, key="duplicate")
    second = _activity(day, 12, key="duplicate")
    await repo.save(_schedule("c1", day, [memorialized, first, second]))
    service = ScheduleService(repository=repo, planner=_Planner(), local_tz=UTC)
    await service.reconcile_commitment_adjustments(
        character_id="c1",
        adjustments=[
            ScheduleAdjustment(action="modify", commitment_key="locked", description="changed"),
            ScheduleAdjustment(action="modify", commitment_key="duplicate", description="changed"),
        ],
    )
    stored = await repo.get("c1", day)
    assert stored is not None
    assert stored.activities[0].description == "activity 10"
    assert [a.description for a in stored.activities[1:]] == ["activity 11", "activity 12"]


@pytest.mark.asyncio
async def test_story_reconciliation_updates_only_live_unique_key() -> None:
    repo = InMemoryStoryArcRepository()
    arc = StoryArc.create(character_id="c1", title="arc", premise="p", theme="custom", start_date=date(2026, 8, 1), end_date=date(2026, 9, 1))
    live = StoryArcBeat.create(arc_id=arc.id, sequence=0, scheduled_date=date(2026, 8, 30), title="old", summary="old", commitment_key="meet")
    realized = StoryArcBeat.create(arc_id=arc.id, sequence=1, scheduled_date=date(2026, 8, 31), title="done", summary="done", status=BEAT_REALIZED, commitment_key="locked")
    await repo.add(arc.with_beats([live, realized]))
    service = StoryArcService(repository=repo, planner=_Planner())
    await service.reconcile_commitment_adjustments(character_id="c1", adjustments=[
        ArcAdjustment(action="modify_beat", commitment_key="meet", title="new", summary="new", scheduled_date=date(2026, 8, 31), is_first_meeting=True),
        ArcAdjustment(action="modify_beat", commitment_key="locked", title="bad", summary="bad"),
    ])
    stored = await repo.get(arc.id)
    assert stored is not None
    assert stored.beats[0].title == "new"
    assert stored.beats[0].scheduled_date == date(2026, 8, 31)
    assert stored.beats[0].is_first_meeting is True
    assert stored.beats[1].title == "done"


@pytest.mark.asyncio
async def test_goal_reconciliation_requires_one_active_key() -> None:
    repo = InMemoryGoalRepository()
    service = GoalService(repo)
    active = CharacterGoal.create(character_id="c1", content="old", commitment_key="meet")
    done = CharacterGoal.create(character_id="c1", content="done", commitment_key="locked")
    await repo.add(active)
    await repo.add(done)
    await service.update_goal(done.id, UpdateGoalRequest(status="done"))
    await service.reconcile_commitment_adjustments(character_id="c1", adjustments=[
        GoalAdjustmentSignal(commitment_key="meet", content="updated", target_date_iso="2026-08-31"),
        GoalAdjustmentSignal(commitment_key="locked", content="must stay"),
    ])
    stored_active = await repo.get(active.id)
    stored_done = await repo.get(done.id)
    assert stored_active is not None and stored_active.content == "updated"
    assert stored_active.review_notes == "target_date_iso=2026-08-31"
    assert stored_done is not None and stored_done.content == "done"
