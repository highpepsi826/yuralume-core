"""Regression coverage for background current-intent lifecycle checks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from kokoro_link.application.services.current_intent_reconciler import (
    CurrentIntentReconciler,
)
from kokoro_link.contracts.current_intent_reviewer import CurrentIntentReview
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.repositories.in_memory_characters import (
    InMemoryCharacterRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_schedules import (
    InMemoryScheduleRepository,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


class _StaticReviewer:
    def __init__(self, result: CurrentIntentReview) -> None:
        self._result = result
        self.calls = 0

    async def review(self, **_kwargs) -> CurrentIntentReview:  # noqa: ANN003
        self.calls += 1
        return self._result


class _BlockingReviewer:
    def __init__(self, result: CurrentIntentReview) -> None:
        self._result = result
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def review(self, **_kwargs) -> CurrentIntentReview:  # noqa: ANN003
        self.started.set()
        await self.release.wait()
        return self._result


class _HangingReviewer:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def review(self, **_kwargs) -> CurrentIntentReview:  # noqa: ANN003
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def _character(*, state: CharacterState) -> Character:
    return Character.create(
        name="Mio",
        summary="",
        personality=[],
        interests=[],
        speaking_style="",
        boundaries=[],
        state=state,
    )


async def _wire(
    *,
    state: CharacterState,
    reviewer=None,  # noqa: ANN001
    **reconciler_kwargs,
) -> tuple[CurrentIntentReconciler, InMemoryCharacterRepository, Character]:
    characters = InMemoryCharacterRepository()
    character = _character(state=state)
    await characters.save(character)
    reconciler = CurrentIntentReconciler(
        character_repository=characters,
        schedule_repository=InMemoryScheduleRepository(),
        reviewer=reviewer,
        clock=_Clock(NOW),
        **reconciler_kwargs,
    )
    return reconciler, characters, character


@pytest.mark.asyncio
async def test_stale_sleep_intent_is_cleared_when_no_sleep_context_remains() -> None:
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="tired",
            affection=50,
            fatigue=50,
            trust=50,
            energy=20,
            current_intent="我想睡醒後再找你。",
            current_intent_updated_at=NOW - timedelta(hours=9),
            current_intent_source="post_turn",
        ),
    )

    result = await reconciler.reconcile(character.id, now=NOW)

    assert result.action == "cleared"
    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent is None
    assert updated.state.current_intent_status == "expired"


@pytest.mark.asyncio
async def test_untimestamped_timed_intent_is_reviewed_not_scheduled() -> None:
    reviewer = _StaticReviewer(CurrentIntentReview(action="keep"))
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="focused",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="今天 18:30 再找桃桃。",
        ),
        reviewer=reviewer,
    )

    result = await reconciler.reconcile(character.id, now=NOW, manual=True)

    assert result.action == "queued_for_llm"
    await reconciler._tasks[character.id]
    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent_candidate_at is None
    assert reviewer.calls == 1


@pytest.mark.asyncio
async def test_fresh_intent_remains_valid_without_spending_an_llm_review() -> None:
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="focused",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="午飯後整理筆記。",
            current_intent_updated_at=NOW - timedelta(minutes=10),
            current_intent_source="post_turn",
        ),
    )

    result = await reconciler.reconcile(character.id, now=NOW)

    assert result.action == "updated"
    assert result.status == "valid"
    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent == "午飯後整理筆記。"
    assert updated.state.current_intent_status == "valid"


@pytest.mark.asyncio
async def test_explicit_time_intent_creates_one_stable_internal_candidate() -> None:
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="focused",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="今天 18:30 再找桃桃。",
            current_intent_updated_at=NOW - timedelta(minutes=10),
            current_intent_source="post_turn",
        ),
    )

    first = await reconciler.reconcile(character.id, now=NOW, manual=True)
    assert first.action == "scheduled"
    assert first.status == "candidate"
    stored = await characters.get(character.id)
    assert stored is not None
    candidate_at = stored.state.current_intent_candidate_at
    candidate_key = stored.state.current_intent_candidate_key
    assert candidate_at == datetime(2026, 8, 17, 18, 30, tzinfo=UTC)
    assert len(candidate_key) == 64

    second = await reconciler.reconcile(
        character.id,
        now=NOW + timedelta(minutes=10),
        manual=True,
    )
    assert second.action == "unchanged"
    repeated = await characters.get(character.id)
    assert repeated is not None
    assert repeated.state.current_intent_candidate_at == candidate_at
    assert repeated.state.current_intent_candidate_key == candidate_key


@pytest.mark.asyncio
async def test_due_internal_candidate_remains_a_fact_not_an_llm_or_send_trigger() -> None:
    reviewer = _StaticReviewer(CurrentIntentReview(action="keep"))
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="focused",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="今天 12:30 再找桃桃。",
            current_intent_updated_at=NOW - timedelta(minutes=10),
            current_intent_source="post_turn",
        ),
        reviewer=reviewer,
    )

    await reconciler.reconcile(character.id, now=NOW, manual=True)
    result = await reconciler.reconcile(
        character.id,
        now=NOW + timedelta(minutes=31),
    )

    assert result.action == "updated"
    assert result.status == "needs_review"
    assert reviewer.calls == 0
    stored = await characters.get(character.id)
    assert stored is not None
    assert stored.state.current_intent_candidate_at == datetime(
        2026, 8, 17, 12, 30, tzinfo=UTC,
    )


@pytest.mark.asyncio
async def test_past_explicit_time_is_reviewed_instead_of_requeued() -> None:
    reviewer = _StaticReviewer(CurrentIntentReview(action="keep"))
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="focused",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="今天 12:30 再找桃桃。",
            current_intent_updated_at=NOW - timedelta(minutes=10),
            current_intent_source="post_turn",
        ),
        reviewer=reviewer,
    )

    await reconciler.reconcile(character.id, now=NOW, manual=True)
    result = await reconciler.reconcile(
        character.id,
        now=NOW + timedelta(hours=12, minutes=31),
    )

    assert result.action == "queued_for_llm"
    await reconciler._tasks[character.id]
    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent == "今天 12:30 再找桃桃。"
    assert updated.state.current_intent_candidate_at is None

    # On the next day, the original "今天" must remain anchored to the
    # writing date. It can be reviewed again, but it must not create a new
    # future candidate for the new calendar day.
    retry = await reconciler.reconcile(
        character.id,
        now=NOW + timedelta(hours=18, minutes=32),
    )
    assert retry.action == "queued_for_llm"
    await reconciler._tasks[character.id]
    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent_candidate_at is None
    assert reviewer.calls == 2


@pytest.mark.asyncio
async def test_stale_generic_intent_queues_background_review() -> None:
    reviewer = _BlockingReviewer(CurrentIntentReview(action="keep"))
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="pensive",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="找個合適的時候聊聊。",
            current_intent_updated_at=NOW - timedelta(hours=13),
            current_intent_source="post_turn",
        ),
        reviewer=reviewer,
    )

    result = await reconciler.reconcile(character.id, now=NOW)

    assert result.action == "queued_for_llm"
    assert result.queued is True
    await reviewer.started.wait()
    active = await characters.get(character.id)
    assert active is not None
    assert active.state.current_intent_status == "reviewing"

    task = reconciler._tasks[character.id]
    reviewer.release.set()
    await task

    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent_status == "valid"


@pytest.mark.asyncio
async def test_manual_review_respects_per_character_cooldown() -> None:
    reviewer = _StaticReviewer(CurrentIntentReview(action="keep"))
    reconciler, _characters, character = await _wire(
        state=CharacterState(
            emotion="pensive",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="有件事想理清。",
            current_intent_updated_at=NOW - timedelta(hours=13),
            current_intent_source="post_turn",
        ),
        reviewer=reviewer,
    )

    first = await reconciler.reconcile(character.id, now=NOW, manual=True)
    assert first.action == "queued_for_llm"
    await reconciler._tasks[character.id]

    second = await reconciler.reconcile(
        character.id,
        now=NOW + timedelta(minutes=1),
        manual=True,
    )

    assert second.action == "rate_limited"
    assert reviewer.calls == 1


@pytest.mark.asyncio
async def test_timed_out_review_leaves_intent_for_a_later_retry() -> None:
    reviewer = _HangingReviewer()
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="pensive",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="有件事想理清。",
            current_intent_updated_at=NOW - timedelta(hours=13),
            current_intent_source="post_turn",
        ),
        reviewer=reviewer,
        review_timeout_seconds=0.01,
    )

    result = await reconciler.reconcile(character.id, now=NOW, manual=True)
    assert result.action == "queued_for_llm"
    await reviewer.started.wait()
    await reconciler._tasks[character.id]

    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent == "有件事想理清。"
    assert updated.state.current_intent_status == "needs_review"


@pytest.mark.asyncio
async def test_late_review_cannot_overwrite_newer_intent() -> None:
    reviewer = _BlockingReviewer(
        CurrentIntentReview(action="replace", replacement="換一件較貼近今天的事。"),
    )
    reconciler, characters, character = await _wire(
        state=CharacterState(
            emotion="pensive",
            affection=50,
            fatigue=10,
            trust=50,
            energy=70,
            current_intent="有件事想理清。",
            current_intent_updated_at=NOW - timedelta(hours=13),
            current_intent_source="post_turn",
        ),
        reviewer=reviewer,
    )

    result = await reconciler.reconcile(character.id, now=NOW, manual=True)
    assert result.action == "queued_for_llm"
    await reviewer.started.wait()
    task = reconciler._tasks[character.id]

    current = await characters.get(character.id)
    assert current is not None
    await characters.save(current.with_state(current.state.with_current_intent(
        "剛剛收到的新想法。",
        updated_at=NOW + timedelta(minutes=1),
        source="post_turn",
    )))
    reviewer.release.set()
    await task

    updated = await characters.get(character.id)
    assert updated is not None
    assert updated.state.current_intent == "剛剛收到的新想法。"
    assert updated.state.current_intent_source == "post_turn"
