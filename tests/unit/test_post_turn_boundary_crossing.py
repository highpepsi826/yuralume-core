"""I-21 phase 2, Part A: post-turn re-derives "the interaction crossed a
schedule boundary" and asks the processor to reconcile the schedule.

The derivation lives in ``ChatService._do_post_turn`` (T1), is reachable from
the hosted worker's id-only entry (T2), renders an extra prompt block only
when the facts are present (T3), converges once the activity is shared (T4),
reaches the stored schedule through the existing apply path (T5) and is
reversed by turn undo (T8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import pytest

from kokoro_link.application.dto.chat import SendChatMessageRequest
from kokoro_link.application.services.chat_service import ChatService
from kokoro_link.application.services.schedule_service import ScheduleService
from kokoro_link.application.services.turn_undo_service import TurnUndoService
from kokoro_link.contracts.post_turn import PostTurnResult, ScheduleAdjustment
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import (
    Conversation,
    Message,
    MessageRole,
)
from kokoro_link.domain.entities.schedule import (
    OPERATOR_CONFIRMED_SHARED_ROLE,
    DailySchedule,
    ScheduleActivity,
)
from kokoro_link.domain.value_objects.actor import ParticipantRef
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.llm.fake import FakeChatModel
from kokoro_link.infrastructure.llm.registry import InMemoryChatModelRegistry
from kokoro_link.infrastructure.memory.in_memory import InMemoryMemoryRepository
from kokoro_link.infrastructure.post_turn.llm_processor import (
    LLMPostTurnProcessor,
    _build_prompt,
)
from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder
from kokoro_link.infrastructure.repositories.in_memory_characters import (
    InMemoryCharacterRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_schedules import (
    InMemoryScheduleRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_turn_journals import (
    InMemoryTurnJournalRepository,
)
from kokoro_link.infrastructure.state.simple import SimpleStateEngine

UTC = timezone.utc
U, A = MessageRole.USER, MessageRole.ASSISTANT
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def _m(role: MessageRole, minutes_ago: float, text: str = "hi") -> Message:
    return Message(
        role=role, content=text, created_at=NOW - timedelta(minutes=minutes_ago),
    )


def _character() -> Character:
    return Character.create(
        name="Mio", summary="", personality=[], interests=[],
        speaking_style="", boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )


def _activity(
    start_minutes_ago: float, end_minutes_ahead: float, *, shared: bool = False,
    description: str = "洗澡",
) -> ScheduleActivity:
    refs = (
        (ParticipantRef(
            actor_kind="operator", actor_id=None, display_name="你",
            role=OPERATOR_CONFIRMED_SHARED_ROLE,
        ),)
        if shared else ()
    )
    return ScheduleActivity.create(
        start_at=NOW - timedelta(minutes=start_minutes_ago),
        end_at=NOW + timedelta(minutes=end_minutes_ahead),
        description=description, category="hygiene", busy_score=0.9,
        participant_refs=refs,
    )


class _SpyProcessor:
    def __init__(self) -> None:
        self.seen: dict = {}

    async def process(self, **kwargs):  # noqa: ANN003
        self.seen = kwargs
        return PostTurnResult()


@dataclass
class _World:
    chat: ChatService
    processor: _SpyProcessor
    schedules: InMemoryScheduleRepository
    conversations: InMemoryConversationRepository
    characters: InMemoryCharacterRepository
    character: Character = field(default=None)  # type: ignore[assignment]


async def _world(
    activities: list[ScheduleActivity], *, processor=None,
) -> _World:
    schedules = InMemoryScheduleRepository()
    conversations = InMemoryConversationRepository()
    characters = InMemoryCharacterRepository()
    character = _character()
    await characters.save(character)
    await schedules.save(DailySchedule.create(
        character_id=character.id, date_=NOW.date(), activities=activities,
    ))
    registry = InMemoryChatModelRegistry(default_provider_id="fake")
    registry.register(FakeChatModel(provider_id="fake"))
    spy = processor or _SpyProcessor()
    chat = ChatService(
        character_repository=characters,
        conversation_repository=conversations,
        memory_repository=InMemoryMemoryRepository(),
        post_turn_processor=spy,
        prompt_context_builder=DefaultPromptContextBuilder(),
        model_registry=registry,
        state_engine=SimpleStateEngine(),
        schedule_service=ScheduleService(
            repository=schedules, planner=None, local_tz=UTC,  # type: ignore[arg-type]
        ),
    )
    return _World(chat, spy, schedules, conversations, characters, character)


async def _run(world: _World, *, prior, turn) -> dict:
    return await world.chat._do_post_turn(
        character=world.character,
        conversation_id="conv-1",
        turn_record_id="turn-1",
        user_text="u", assistant_text="a",
        prior_messages=prior,
        turn_messages=turn,
    )


pytestmark = pytest.mark.asyncio


# ---- T1 -----------------------------------------------------------------


async def test_crossing_is_passed_when_the_activity_came_due_mid_interaction() -> None:
    earlier = _activity(120, -4, description="看書")  # ended 4 minutes ago
    bath = _activity(3, 30)
    world = await _world([earlier, bath])
    # The earlier activity covers the streak start only if it spans it.
    earlier = ScheduleActivity.create(
        start_at=NOW - timedelta(minutes=120), end_at=NOW - timedelta(minutes=3),
        description="看書", category="leisure",
    )
    await world.schedules.save(DailySchedule.create(
        character_id=world.character.id, date_=NOW.date(),
        activities=[earlier, bath],
    ))
    prior = [_m(U, 8), _m(A, 6)]
    turn = (_m(U, 1), _m(A, 0))

    await _run(world, prior=prior, turn=turn)

    crossing = world.processor.seen["boundary_crossing"]
    # Streak start is the oldest prior message, not this turn's own player
    # message: the history handed to the resolver is prior + turn.
    assert crossing.streak_started_at == NOW - timedelta(minutes=8)
    assert crossing.current_activity.id == bath.id
    assert crossing.activity_at_streak_start.id == earlier.id
    # Judged at the turn's own instant.
    assert crossing.judged_at == NOW


async def test_crossing_uses_the_turn_instant_not_the_job_wall_clock() -> None:
    """The fixed 2026 turn is long past by the time this test runs; a
    wall-clock judgement would find no ongoing interaction at all."""
    world = await _world([_activity(3, 30)])
    await _run(
        world, prior=[_m(U, 8), _m(A, 6)], turn=(_m(U, 1), _m(A, 0)),
    )
    assert "boundary_crossing" in world.processor.seen


async def test_no_crossing_when_activity_began_before_the_interaction() -> None:
    world = await _world([_activity(20, 30)])
    await _run(world, prior=[_m(U, 8), _m(A, 6)], turn=(_m(U, 1), _m(A, 0)))
    assert "boundary_crossing" not in world.processor.seen


async def test_no_crossing_when_the_gap_before_the_turn_broke_the_streak() -> None:
    # Prior exchange 60 minutes ago: this turn's own pair is the whole
    # streak, so an activity that began 30 minutes ago began BEFORE it.
    world = await _world([_activity(30, 30)])
    await _run(world, prior=[_m(U, 62), _m(A, 60)], turn=(_m(U, 1), _m(A, 0)))
    assert "boundary_crossing" not in world.processor.seen


async def test_no_crossing_without_the_turn_messages_or_a_player_message() -> None:
    world = await _world([_activity(3, 30)])
    await _run(world, prior=[_m(U, 8), _m(A, 6)], turn=())
    assert "boundary_crossing" not in world.processor.seen
    await _run(
        world, prior=[_m(U, 8), _m(A, 6)], turn=(_m(A, 1), _m(A, 0)),
    )
    assert "boundary_crossing" not in world.processor.seen


async def test_wider_read_finds_a_streak_start_outside_the_prior_window() -> None:
    world = await _world([_activity(3, 30)])
    older = [
        _m(U if i % 2 == 0 else A, 30 - 5 * i) for i in range(5)
    ]  # -30 .. -10, every 5 minutes
    turn = (_m(U, 1), _m(A, 0))
    later = _m(U, -5, "a later queued turn")
    await world.conversations.save(Conversation(
        id="conv-1", character_id=world.character.id,
        messages=[*older, *turn, later],
    ))
    # Only the newest pair of the older run is in the prior window, so the
    # run is still unbroken at its oldest message and must be read wider.
    await _run(world, prior=older[-2:], turn=turn)

    crossing = world.processor.seen["boundary_crossing"]
    assert crossing.streak_started_at == NOW - timedelta(minutes=30)


# ---- T2 -----------------------------------------------------------------


async def test_worker_entry_derives_the_same_crossing() -> None:
    world = await _world([_activity(3, 30)])
    messages = [_m(U, 8), _m(A, 6), _m(U, 1), _m(A, 0)]
    await world.conversations.save(Conversation(
        id="conv-1", character_id=world.character.id, messages=messages,
    ))

    result = await world.chat.run_post_turn_for_record(
        turn_record_id="turn-1", conversation_id="conv-1",
        character_id=world.character.id, assistant_index=3, now=NOW,
    )

    assert "post_turn_skipped" not in result
    crossing = world.processor.seen["boundary_crossing"]
    assert crossing.streak_started_at == NOW - timedelta(minutes=8)
    assert crossing.judged_at == NOW


# ---- T4 -----------------------------------------------------------------


async def test_a_shared_current_activity_converges() -> None:
    world = await _world([_activity(3, 30, shared=True)])
    await _run(world, prior=[_m(U, 8), _m(A, 6)], turn=(_m(U, 1), _m(A, 0)))
    assert "boundary_crossing" not in world.processor.seen


# ---- T3 -----------------------------------------------------------------


def _prompt(crossing=None, *, tz=UTC) -> str:
    return _build_prompt(
        character=_character(), user_message="u", assistant_message="a",
        recent_messages=[], local_tz=tz, now=NOW, boundary_crossing=crossing,
    )


async def test_prompt_is_unchanged_without_a_crossing() -> None:
    from kokoro_link.infrastructure.post_turn import llm_processor as mod

    prompt = _prompt()
    assert "互動跨越行程邊界" not in prompt
    assert "例外：" not in prompt
    # The two new placeholders occupy no characters when the facts are
    # absent: rendering with the placeholders stripped is the same string.
    template = mod.get_default_loader().raw("post_turn/processor")
    assert template.count("${boundary_section}") == 1
    assert template.count("${boundary_rule}") == 1
    assert "${schedule_section}${boundary_section}${promise_section}\n" in template


async def test_prompt_renders_the_block_with_local_times_and_the_id() -> None:
    from kokoro_link.domain.value_objects.ongoing_interaction import (
        BoundaryCrossing,
    )

    tz = timezone(timedelta(hours=8))
    earlier = _activity(120, -3, description="看書")
    bath = _activity(3, 30)
    crossing = BoundaryCrossing(
        streak_started_at=NOW - timedelta(minutes=8),
        activity_at_streak_start=earlier,
        current_activity=bath,
        judged_at=NOW,
    )
    prompt = _prompt(crossing, tz=tz)

    assert "互動跨越行程邊界：" in prompt
    assert "你們從 19:52 起一直在互動，當時的活動是「看書」" in prompt
    assert f"（id={bath.id}）" in prompt
    assert "19:57–20:30" in prompt and "現在是 20:00" in prompt
    assert "現在之後 30 分鐘" in prompt
    assert "operator_confirmed_shared" in prompt
    assert "例外：上方出現「互動跨越行程邊界」區段時" in prompt
    # Placed right after the schedule section, before the arc section.
    assert prompt.index("今日行程") < prompt.index("互動跨越行程邊界：")


async def test_real_processor_receives_and_renders_the_crossing() -> None:
    from kokoro_link.domain.value_objects.ongoing_interaction import (
        BoundaryCrossing,
    )

    class _Model:
        provider_id = "scripted"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def generate(self, prompt: str) -> str:
            self.prompts.append(prompt)
            return "{}"

        async def generate_stream(self, prompt: str):  # pragma: no cover
            if False:
                yield ""

    model = _Model()
    processor = LLMPostTurnProcessor(model=model)  # type: ignore[arg-type]
    bath = _activity(3, 30)
    await processor.process(
        character=_character(), conversation_id="c", user_message="u",
        assistant_message="a", now=NOW,
        boundary_crossing=BoundaryCrossing(
            streak_started_at=NOW - timedelta(minutes=8),
            activity_at_streak_start=None, current_activity=bath, judged_at=NOW,
        ),
    )
    assert "當時行程上沒有安排活動" in model.prompts[0]


# ---- T5 -----------------------------------------------------------------


class _FrozenSchedules(ScheduleService):
    def today(self, now: datetime | None = None) -> date:
        return NOW.date()


def _shared_add() -> ScheduleAdjustment:
    return ScheduleAdjustment(
        action="add", start="12:00", end="12:40", description="一起聊天",
        category="social", operator_involvement="operator_confirmed_shared",
    )


async def test_add_plus_modify_keeps_a_shared_activity_and_delays_the_plan() -> None:
    repo = InMemoryScheduleRepository()
    character = _character()
    bath = ScheduleActivity.create(
        start_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
        end_at=datetime(2026, 11, 22, 12, 30, tzinfo=UTC),
        description="洗澡", category="hygiene",
    )
    await repo.save(DailySchedule.create(
        character_id=character.id, date_=NOW.date(), activities=[bath],
    ))
    service = _FrozenSchedules(
        repository=repo, planner=None, local_tz=UTC,  # type: ignore[arg-type]
    )
    await service.apply_adjustments(
        character_id=character.id,
        adjustments=[
            _shared_add(),
            ScheduleAdjustment(
                action="modify", activity_id=bath.id, start="12:40", end="13:10",
            ),
        ],
    )
    stored = await repo.get(character.id, NOW.date())
    by_desc = {a.description: a for a in stored.activities}
    shared = by_desc["一起聊天"]
    assert any(
        r.actor_kind == "operator" and r.role == OPERATOR_CONFIRMED_SHARED_ROLE
        for r in shared.participant_refs
    )
    assert by_desc["洗澡"].start_at == datetime(2026, 11, 22, 12, 40, tzinfo=UTC)
    assert by_desc["洗澡"].end_at == datetime(2026, 11, 22, 13, 10, tzinfo=UTC)


async def test_add_plus_remove_drops_the_plan() -> None:
    repo = InMemoryScheduleRepository()
    character = _character()
    bath = ScheduleActivity.create(
        start_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
        end_at=datetime(2026, 11, 22, 12, 30, tzinfo=UTC),
        description="洗澡", category="hygiene",
    )
    await repo.save(DailySchedule.create(
        character_id=character.id, date_=NOW.date(), activities=[bath],
    ))
    service = _FrozenSchedules(
        repository=repo, planner=None, local_tz=UTC,  # type: ignore[arg-type]
    )
    await service.apply_adjustments(
        character_id=character.id,
        adjustments=[
            _shared_add(),
            ScheduleAdjustment(action="remove", activity_id=bath.id),
        ],
    )
    stored = await repo.get(character.id, NOW.date())
    assert [a.description for a in stored.activities] == ["一起聊天"]


# ---- T8 -----------------------------------------------------------------


class _AddingProcessor:
    async def process(self, **kwargs):  # noqa: ANN003
        return PostTurnResult(schedule_adjustments=[
            ScheduleAdjustment(
                action="add", start="23:00", end="23:30", description="一起聊天",
                category="social",
                operator_involvement="operator_confirmed_shared",
            ),
        ])


async def test_turn_undo_restores_schedule_written_by_the_post_turn() -> None:
    today = datetime.now(UTC).date()
    schedules = InMemoryScheduleRepository()
    conversations = InMemoryConversationRepository()
    characters = InMemoryCharacterRepository()
    journals = InMemoryTurnJournalRepository()
    character = _character()
    await characters.save(character)
    base = ScheduleActivity.create(
        start_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(hour=9),
        end_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(hour=10),
        description="早上的事", category="work",
    )
    await schedules.save(DailySchedule.create(
        character_id=character.id, date_=today, activities=[base],
    ))
    registry = InMemoryChatModelRegistry(default_provider_id="fake")
    registry.register(FakeChatModel(provider_id="fake"))
    memory = InMemoryMemoryRepository()
    chat = ChatService(
        character_repository=characters,
        conversation_repository=conversations,
        memory_repository=memory,
        post_turn_processor=_AddingProcessor(),
        prompt_context_builder=DefaultPromptContextBuilder(),
        model_registry=registry,
        state_engine=SimpleStateEngine(),
        schedule_service=ScheduleService(
            repository=schedules, planner=None, local_tz=UTC,  # type: ignore[arg-type]
        ),
        journal_repository=journals,
    )
    undo = TurnUndoService(
        journal_repository=journals,
        conversation_repository=conversations,
        character_repository=characters,
        memory_repository=memory,
        schedule_repository=schedules,
    )

    reply = await chat.send_message(SendChatMessageRequest(
        character_id=character.id, message="嗨",
    ))
    await chat.wait_for_pending()
    after_turn = await schedules.get(character.id, today)
    assert [a.description for a in after_turn.activities] == [
        "早上的事", "一起聊天",
    ]

    result = await undo.undo_last_turn(reply.conversation_id)

    assert result.restored_schedule is True
    restored = await schedules.get(character.id, today)
    assert [a.description for a in restored.activities] == ["早上的事"]
