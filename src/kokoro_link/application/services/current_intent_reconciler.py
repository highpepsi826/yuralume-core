"""Background lifecycle checks for a character's short-lived current intent.

This service deliberately owns no delivery path.  It can mark, replace, or
clear the small player-visible state field, but it never sends a proactive
message and never turns a private thought into a shared appointment.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from hashlib import sha256
from unicodedata import normalize

from kokoro_link.contracts.clock import ClockPort, ensure_utc
from kokoro_link.contracts.current_intent_reviewer import (
    CurrentIntentReviewerPort,
)
from kokoro_link.contracts.repositories import CharacterRepositoryPort
from kokoro_link.contracts.schedule_repository import ScheduleRepositoryPort
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.schedule import ScheduleActivity
from kokoro_link.domain.value_objects.character_state import (
    CURRENT_INTENT_STATUS_CLEARED,
    CURRENT_INTENT_STATUS_CANDIDATE,
    CURRENT_INTENT_STATUS_EXPIRED,
    CURRENT_INTENT_STATUS_FRESH,
    CURRENT_INTENT_STATUS_NEEDS_REVIEW,
    CURRENT_INTENT_STATUS_NEEDS_SCHEDULE,
    CURRENT_INTENT_STATUS_REVIEWING,
    CURRENT_INTENT_STATUS_UPDATED,
    CURRENT_INTENT_STATUS_VALID,
    CharacterState,
)
from kokoro_link.infrastructure.time.system_clock import SystemClock


_LOGGER = logging.getLogger(__name__)

_AUTO_CHECK_INTERVAL = timedelta(minutes=30)
_AUTO_REVIEW_MIN_AGE = timedelta(hours=12)
_AUTO_REVIEW_COOLDOWN = timedelta(hours=6)
_MANUAL_REVIEW_COOLDOWN = timedelta(minutes=5)
_STALE_SLEEP_INTENT_AGE = timedelta(hours=8)
_REVIEW_TIMEOUT_SECONDS = 15.0
_MAX_CONCURRENT_REVIEWS = 2
_SLEEP_WAKE_TERMS = (
    "睡醒", "入睡", "想睡", "去睡", "睡覺", "睡眠", "安眠", "就寢",
    "wake up", "asleep", "sleep", "nap",
)
_SLEEP_ACTIVITY_TERMS = (
    "睡", "就寢", "安眠", "sleep", "asleep", "nap",
)
_CLOCK_RE = re.compile(
    r"(?:\b(?:[01]?\d|2[0-3])[:：][0-5]\d\b|(?:[01]?\d|2[0-3])\s*點)",
    re.IGNORECASE,
)
_CLOCK_VALUE_RE = re.compile(
    r"(?<!\d)(?P<hour>[01]?\d|2[0-3])\s*(?:"
    r"[:：]\s*(?P<minute>[0-5]\d)|"
    r"點(?:\s*(?P<minute_chinese>[0-5]?\d)\s*分?)?"
    r")(?!\d)",
    re.IGNORECASE,
)
_LATIN_WORD_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_COMMON_CJK_TERMS = frozenset({
    "現在", "之後", "然後", "使用者", "角色", "自己", "今天", "明天", "等等",
    "一下", "這個", "那個", "準備", "想要", "可以", "應該", "再找",
})


@dataclass(frozen=True, slots=True)
class CurrentIntentReconcileResult:
    action: str
    status: str
    queued: bool = False


class CurrentIntentReconciler:
    """Cheap schedule-aware checks plus a bounded asynchronous LLM fallback."""

    def __init__(
        self,
        *,
        character_repository: CharacterRepositoryPort,
        schedule_repository: ScheduleRepositoryPort,
        reviewer: CurrentIntentReviewerPort | None = None,
        schedule_service=None,  # noqa: ANN001 - optional language facade
        clock: ClockPort | None = None,
        auto_check_interval: timedelta = _AUTO_CHECK_INTERVAL,
        auto_review_min_age: timedelta = _AUTO_REVIEW_MIN_AGE,
        auto_review_cooldown: timedelta = _AUTO_REVIEW_COOLDOWN,
        manual_review_cooldown: timedelta = _MANUAL_REVIEW_COOLDOWN,
        review_timeout_seconds: float = _REVIEW_TIMEOUT_SECONDS,
        max_concurrent_reviews: int = _MAX_CONCURRENT_REVIEWS,
    ) -> None:
        self._characters = character_repository
        self._schedules = schedule_repository
        self._reviewer = reviewer
        self._schedule_service = schedule_service
        self._clock = clock or SystemClock()
        self._auto_check_interval = max(timedelta(0), auto_check_interval)
        self._auto_review_min_age = max(timedelta(0), auto_review_min_age)
        self._auto_review_cooldown = max(timedelta(0), auto_review_cooldown)
        self._manual_review_cooldown = max(timedelta(0), manual_review_cooldown)
        self._review_timeout_seconds = max(0.1, review_timeout_seconds)
        self._review_semaphore = asyncio.Semaphore(max(1, max_concurrent_reviews))
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def reconcile(
        self,
        character_id: str,
        *,
        now: datetime | None = None,
        manual: bool = False,
    ) -> CurrentIntentReconcileResult:
        character = await self._characters.get(character_id)
        if character is None:
            return CurrentIntentReconcileResult("not_found", "unknown")
        return await self.reconcile_character(character, now=now, manual=manual)

    async def reconcile_character(
        self,
        character: Character,
        *,
        now: datetime | None = None,
        manual: bool = False,
    ) -> CurrentIntentReconcileResult:
        """Re-read and reconcile one character so stale tick snapshots cannot win."""
        current = await self._characters.get(character.id)
        if current is None:
            return CurrentIntentReconcileResult("not_found", "unknown")
        ref = ensure_utc(now or self._clock.now())
        state = current.state
        intent = (state.current_intent or "").strip()
        if not intent:
            return CurrentIntentReconcileResult("unchanged", CURRENT_INTENT_STATUS_CLEARED)
        if not manual and self._checked_recently(state, ref):
            return CurrentIntentReconcileResult("unchanged", state.current_intent_status)

        activities = await self._load_activities(current.id)
        local_tz = await self._local_timezone(current)
        action, status, candidate_at = _deterministic_verdict(
            intent=intent,
            state=state,
            activities=activities,
            now=ref,
            local_tz=local_tz,
        )
        schedule_summary = _render_schedule_summary(activities, now=ref)

        if action == "clear":
            applied = await self._compare_and_set(
                current,
                current_intent=None,
                updated_at=ref,
                checked_at=ref,
                reviewed_at=None,
                status=status,
                source="reconciler",
                candidate_at=None,
                candidate_key="",
            )
            return CurrentIntentReconcileResult(
                "cleared" if applied else "superseded", status,
            )

        candidate_key = state.current_intent_candidate_key
        if action == "candidate" and candidate_at is not None:
            candidate_key = _candidate_key(
                character_id=current.id,
                intent=intent,
                candidate_at=candidate_at,
            )
        elif action == "keep" and candidate_at is None:
            candidate_key = ""

        applied = await self._compare_and_set(
            current,
            current_intent=intent,
            updated_at=state.current_intent_updated_at,
            checked_at=ref,
            reviewed_at=state.current_intent_reviewed_at,
            status=status,
            source=state.current_intent_source,
            candidate_at=candidate_at,
            candidate_key=candidate_key,
        )
        if not applied:
            return CurrentIntentReconcileResult("superseded", status)
        if action == "candidate":
            return CurrentIntentReconcileResult("scheduled", status)
        if action != "review":
            return CurrentIntentReconcileResult(
                "updated" if status != state.current_intent_status else "unchanged",
                status,
            )
        return await self._queue_review_if_allowed(
            current,
            now=ref,
            manual=manual,
            schedule_summary=schedule_summary,
        )

    async def _queue_review_if_allowed(
        self,
        character: Character,
        *,
        now: datetime,
        manual: bool,
        schedule_summary: str,
    ) -> CurrentIntentReconcileResult:
        if self._reviewer is None:
            return CurrentIntentReconcileResult("needs_review", CURRENT_INTENT_STATUS_NEEDS_REVIEW)
        existing_task = self._tasks.get(character.id)
        if existing_task is not None and not existing_task.done():
            return CurrentIntentReconcileResult(
                "already_running", CURRENT_INTENT_STATUS_REVIEWING, queued=True,
            )
        state = character.state
        intent = (state.current_intent or "").strip()
        if not intent:
            return CurrentIntentReconcileResult("superseded", CURRENT_INTENT_STATUS_CLEARED)
        previous_review = state.current_intent_reviewed_at
        cooldown = (
            self._manual_review_cooldown if manual else self._auto_review_cooldown
        )
        if previous_review is not None and now - ensure_utc(previous_review) < cooldown:
            return CurrentIntentReconcileResult("rate_limited", CURRENT_INTENT_STATUS_NEEDS_REVIEW)
        if not manual:
            age = _intent_age(state, now)
            if age is None or age < self._auto_review_min_age:
                return CurrentIntentReconcileResult("needs_review", CURRENT_INTENT_STATUS_NEEDS_REVIEW)

        claimed = await self._compare_and_set(
            character,
            current_intent=intent,
            updated_at=state.current_intent_updated_at,
            checked_at=now,
            reviewed_at=now,
            status=CURRENT_INTENT_STATUS_REVIEWING,
            source=state.current_intent_source,
            candidate_at=state.current_intent_candidate_at,
            candidate_key=state.current_intent_candidate_key,
        )
        if not claimed:
            return CurrentIntentReconcileResult("superseded", CURRENT_INTENT_STATUS_NEEDS_REVIEW)

        task = asyncio.create_task(
            self._run_review(
                character_id=character.id,
                expected_intent=intent,
                expected_updated_at=state.current_intent_updated_at,
                reviewed_at=now,
                schedule_summary=schedule_summary,
            ),
            name=f"current-intent-reconcile-{character.id}",
        )
        self._tasks[character.id] = task
        task.add_done_callback(
            lambda completed, cid=character.id: self._discard_task(cid, completed),
        )
        return CurrentIntentReconcileResult(
            "queued_for_llm", CURRENT_INTENT_STATUS_REVIEWING, queued=True,
        )

    def _discard_task(self, character_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(character_id) is task:
            self._tasks.pop(character_id, None)

    async def _run_review(
        self,
        *,
        character_id: str,
        expected_intent: str,
        expected_updated_at: datetime | None,
        reviewed_at: datetime,
        schedule_summary: str,
    ) -> None:
        current = await self._characters.get(character_id)
        if current is None:
            return
        state = current.state
        if (
            state.current_intent != expected_intent
            or state.current_intent_updated_at != expected_updated_at
        ):
            return
        # A queued review belongs to the tick that claimed it. The wall clock
        # normally advances past that point, but never let a skewed replica (or
        # a deterministic scheduler test) move its lifecycle decision back in
        # time and preserve a candidate that was already due.
        now = max(ensure_utc(self._clock.now()), reviewed_at)
        try:
            async with self._review_semaphore:
                review = await asyncio.wait_for(
                    self._reviewer.review(
                        character=current,
                        current_intent=expected_intent,
                        intent_age_minutes=_intent_age_minutes(state, now),
                        now=now,
                        schedule_summary=schedule_summary,
                        operator_primary_language=await self._operator_language(current),
                    ),
                    timeout=self._review_timeout_seconds,
                )
        except TimeoutError:
            _LOGGER.warning(
                "current-intent reviewer timed out character=%s after %.1fs",
                character_id,
                self._review_timeout_seconds,
            )
            review = None
        except Exception:  # pragma: no cover - reviewer contract is fail-soft
            _LOGGER.exception("current-intent reviewer crashed character=%s", character_id)
            review = None
        if review is None:
            await self._compare_and_set(
                current,
                current_intent=expected_intent,
                updated_at=expected_updated_at,
                checked_at=now,
                reviewed_at=reviewed_at,
                status=CURRENT_INTENT_STATUS_NEEDS_REVIEW,
                source=state.current_intent_source,
                candidate_at=state.current_intent_candidate_at,
                candidate_key=state.current_intent_candidate_key,
            )
            return

        action = review.normalized_action
        if action == "replace":
            await self._compare_and_set(
                current,
                current_intent=review.replacement,
                updated_at=now,
                checked_at=now,
                reviewed_at=reviewed_at,
                status=CURRENT_INTENT_STATUS_UPDATED,
                source="reconciler",
                candidate_at=None,
                candidate_key="",
            )
            return
        if action == "clear":
            await self._compare_and_set(
                current,
                current_intent=None,
                updated_at=now,
                checked_at=now,
                reviewed_at=reviewed_at,
                status=CURRENT_INTENT_STATUS_CLEARED,
                source="reconciler",
                candidate_at=None,
                candidate_key="",
            )
            return
        candidate_is_stale = (
            state.current_intent_candidate_at is not None
            and ensure_utc(state.current_intent_candidate_at) <= now
        )
        await self._compare_and_set(
            current,
            current_intent=expected_intent,
            updated_at=expected_updated_at,
            checked_at=now,
            reviewed_at=reviewed_at,
            status=CURRENT_INTENT_STATUS_VALID,
            source=state.current_intent_source,
            candidate_at=(
                None if candidate_is_stale else state.current_intent_candidate_at
            ),
            candidate_key=(
                "" if candidate_is_stale else state.current_intent_candidate_key
            ),
        )

    async def _compare_and_set(
        self,
        character: Character,
        *,
        current_intent: str | None,
        updated_at: datetime | None,
        checked_at: datetime,
        reviewed_at: datetime | None,
        status: str,
        source: str,
        candidate_at: datetime | None,
        candidate_key: str,
    ) -> bool:
        state = character.state
        return await self._characters.update_current_intent_if_unchanged(
            character.id,
            expected_intent=state.current_intent,
            expected_updated_at=state.current_intent_updated_at,
            expected_reviewed_at=state.current_intent_reviewed_at,
            expected_candidate_at=state.current_intent_candidate_at,
            expected_candidate_key=state.current_intent_candidate_key,
            current_intent=current_intent,
            updated_at=updated_at,
            checked_at=checked_at,
            reviewed_at=reviewed_at,
            status=status,
            source=source,
            candidate_at=candidate_at,
            candidate_key=candidate_key,
        )

    async def _load_activities(self, character_id: str) -> list[ScheduleActivity]:
        try:
            schedules = await self._schedules.list_for_character(
                character_id, limit=7,
            )
        except Exception:
            _LOGGER.exception(
                "current-intent schedule lookup failed character=%s", character_id,
            )
            return []
        activities = [activity for schedule in schedules for activity in schedule.activities]
        return sorted(activities, key=lambda activity: activity.start_at)

    async def _operator_language(self, character: Character) -> str:
        service = self._schedule_service
        if service is None or not hasattr(service, "operator_for_character"):
            return "zh-TW"
        try:
            operator = await service.operator_for_character(character)
        except Exception:
            _LOGGER.exception(
                "current-intent operator language resolve failed character=%s",
                character.id,
            )
            return "zh-TW"
        return (getattr(operator, "primary_language", "") or "zh-TW").strip()

    async def _local_timezone(self, character: Character) -> tzinfo:
        service = self._schedule_service
        if service is None or not hasattr(service, "timezone_for_character"):
            return timezone.utc
        try:
            return await service.timezone_for_character(character)
        except Exception:
            _LOGGER.exception(
                "current-intent timezone resolve failed character=%s",
                character.id,
            )
            return timezone.utc

    def _checked_recently(self, state: CharacterState, now: datetime) -> bool:
        checked = state.current_intent_checked_at
        return (
            checked is not None
            and now - ensure_utc(checked) < self._auto_check_interval
        )


def _deterministic_verdict(
    *,
    intent: str,
    state: CharacterState,
    activities: list[ScheduleActivity],
    now: datetime,
    local_tz: tzinfo,
) -> tuple[str, str, datetime | None]:
    matching = [
        activity for activity in activities
        if _intent_matches_activity(intent, activity)
        and activity.end_at >= now - timedelta(hours=2)
    ]
    if matching:
        return "keep", CURRENT_INTENT_STATUS_VALID, None

    existing_candidate_at = state.current_intent_candidate_at
    if existing_candidate_at is not None and state.current_intent_candidate_key:
        candidate_at = ensure_utc(existing_candidate_at)
        if candidate_at > now:
            return "keep", CURRENT_INTENT_STATUS_CANDIDATE, candidate_at
        if now - candidate_at < _AUTO_REVIEW_MIN_AGE:
            return "keep", CURRENT_INTENT_STATUS_NEEDS_REVIEW, candidate_at
        return "review", CURRENT_INTENT_STATUS_NEEDS_REVIEW, candidate_at

    normalized = intent.casefold()
    if any(term in normalized for term in _SLEEP_WAKE_TERMS):
        wake_candidate_at = _wake_candidate_at(intent, activities, now=now)
        if wake_candidate_at is not None:
            return "candidate", CURRENT_INTENT_STATUS_CANDIDATE, wake_candidate_at
        sleep_blocks = [
            activity for activity in activities if _is_sleep_activity(activity)
        ]
        if any(activity.end_at >= now - timedelta(hours=2) for activity in sleep_blocks):
            return "keep", CURRENT_INTENT_STATUS_VALID, None
        age = _intent_age(state, now)
        if age is None or age >= _STALE_SLEEP_INTENT_AGE:
            return "clear", CURRENT_INTENT_STATUS_EXPIRED, None
        return "review", CURRENT_INTENT_STATUS_NEEDS_REVIEW, None

    if _CLOCK_RE.search(intent):
        # A pre-lifecycle value has no trustworthy reference date for
        # "today" / "tomorrow". Do not turn an old sentence into a new
        # candidate; let the bounded reviewer retain, replace, or clear it.
        if state.current_intent_updated_at is None:
            return "review", CURRENT_INTENT_STATUS_NEEDS_REVIEW, None
        candidate_at = _explicit_candidate_at(
            intent,
            now=now,
            local_tz=local_tz,
            written_at=state.current_intent_updated_at,
        )
        if candidate_at is not None:
            # Never create a second "candidate" for a time that has already
            # passed. It needs the bounded reviewer to replace or clear it,
            # otherwise a literal "today 18:30" can revive indefinitely on
            # every later tick.
            if candidate_at <= now:
                return "review", CURRENT_INTENT_STATUS_NEEDS_REVIEW, None
            return "candidate", CURRENT_INTENT_STATUS_CANDIDATE, candidate_at
        return "review", CURRENT_INTENT_STATUS_NEEDS_SCHEDULE, None
    age = _intent_age(state, now)
    if age is None or age >= _AUTO_REVIEW_MIN_AGE:
        return "review", CURRENT_INTENT_STATUS_NEEDS_REVIEW, None
    return "keep", CURRENT_INTENT_STATUS_VALID, None


def _wake_candidate_at(
    intent: str,
    activities: list[ScheduleActivity],
    *,
    now: datetime,
) -> datetime | None:
    normalized = intent.casefold()
    wake_phrases = ("睡醒後", "醒來後", "起床後", "wake up", "after waking")
    if not any(phrase in normalized for phrase in wake_phrases):
        return None
    candidates = [
        activity for activity in activities
        if _is_sleep_activity(activity)
        and activity.end_at >= now - timedelta(hours=2)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda activity: activity.end_at).end_at


def _explicit_candidate_at(
    intent: str,
    *,
    now: datetime,
    local_tz: tzinfo,
    written_at: datetime | None,
) -> datetime | None:
    match = _CLOCK_VALUE_RE.search(intent)
    if match is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or match.group("minute_chinese") or 0)
    # Relative phrases are relative to the moment this intent was written,
    # not every later reconciliation tick. Otherwise a stale "今天 18:30"
    # would incorrectly become a new appointment every midnight.
    anchor = ensure_utc(written_at or now).astimezone(local_tz)
    normalized = intent.casefold()
    days = 2 if "後天" in normalized else 1 if (
        "明天" in normalized or "明日" in normalized or "tomorrow" in normalized
    ) else 0
    target_date = anchor.date() + timedelta(days=days)
    return datetime.combine(target_date, time(hour, minute), tzinfo=local_tz).astimezone(
        timezone.utc,
    )


def _candidate_key(*, character_id: str, intent: str, candidate_at: datetime) -> str:
    normalized_intent = " ".join(normalize("NFKC", intent).casefold().split())
    minute = ensure_utc(candidate_at).replace(second=0, microsecond=0).isoformat()
    payload = "\x1f".join((character_id, normalized_intent, minute))
    return sha256(payload.encode("utf-8")).hexdigest()


def _intent_matches_activity(intent: str, activity: ScheduleActivity) -> bool:
    terms = _meaningful_terms(intent)
    if not terms:
        return False
    activity_terms = _meaningful_terms(
        f"{activity.description} {activity.category}",
    )
    return bool(terms.intersection(activity_terms))


def _meaningful_terms(text: str) -> set[str]:
    lowered = (text or "").casefold()
    terms = {match.group(0) for match in _LATIN_WORD_RE.finditer(lowered)}
    for match in _CJK_RUN_RE.finditer(lowered):
        run = match.group(0)
        terms.update(
            run[index:index + 2]
            for index in range(len(run) - 1)
            if run[index:index + 2] not in _COMMON_CJK_TERMS
        )
    return terms


def _is_sleep_activity(activity: ScheduleActivity) -> bool:
    text = f"{activity.description} {activity.category}".casefold()
    return any(term in text for term in _SLEEP_ACTIVITY_TERMS)


def _intent_age(state: CharacterState, now: datetime) -> timedelta | None:
    if state.current_intent_updated_at is None:
        return None
    return max(timedelta(0), now - ensure_utc(state.current_intent_updated_at))


def _intent_age_minutes(state: CharacterState, now: datetime) -> float | None:
    age = _intent_age(state, now)
    return age.total_seconds() / 60.0 if age is not None else None


def _render_schedule_summary(
    activities: list[ScheduleActivity],
    *,
    now: datetime,
) -> str:
    relevant = [
        activity for activity in activities
        if activity.end_at >= now - timedelta(hours=2)
    ][:8]
    if not relevant:
        return "（沒有可用行程）"
    return "\n".join(
        f"- {activity.start_at.isoformat()} 至 {activity.end_at.isoformat()}："
        f"{activity.description}（{activity.category}）"
        for activity in relevant
    )
