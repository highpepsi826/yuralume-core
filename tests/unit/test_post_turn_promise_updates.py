"""I-19 Parts 1-2: the post-turn sees open promises and can settle them.

Covers the prompt block (absent => byte-identical), the ``promise_updates``
parser, the ``ChatService`` application (queued-only writes, re-keying,
worker entry, fail-soft), the schedule alignment instructions, turn undo of
all three actions, and Part 2 (a ``remove`` of a future-day activity).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from kokoro_link.application.dto.chat import SendChatMessageRequest
from kokoro_link.application.services.chat_service import ChatService
from kokoro_link.application.services.schedule_service import ScheduleService
from kokoro_link.contracts.post_turn import (
    MessagePromise,
    OpenPromise,
    PostTurnResult,
    PromiseUpdate,
    ScheduleAdjustment,
)
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import (
    Conversation,
    Message,
    MessageRole,
)
from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    PendingFollowUpStatus,
    scheduled_promise_delivery_slot_key,
)
from kokoro_link.domain.entities.schedule import DailySchedule, ScheduleActivity
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.llm.fake import FakeChatModel
from kokoro_link.infrastructure.llm.registry import InMemoryChatModelRegistry
from kokoro_link.infrastructure.memory.in_memory import InMemoryMemoryRepository
from kokoro_link.infrastructure.post_turn import llm_processor as mod
from kokoro_link.infrastructure.post_turn.llm_processor import (
    LLMPostTurnProcessor,
    _build_prompt,
    _parse_adjustments,
    _parse_promise_updates,
    _parse_response,
)
from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder
from kokoro_link.infrastructure.repositories.in_memory_characters import (
    InMemoryCharacterRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_pending_follow_ups import (
    InMemoryPendingFollowUpRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_schedules import (
    InMemoryScheduleRepository,
)
from kokoro_link.infrastructure.state.simple import SimpleStateEngine
from tests.unit.busy_defer_harness import StubScheduleService
from tests.unit.test_turn_undo_follow_ups import _Wiring
from tests.unit.busy_defer_harness import ScriptedDecider

UTC = timezone.utc
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.asyncio


def _character() -> Character:
    return Character.create(
        name="Mio", summary="", personality=[], interests=[],
        speaking_style="", boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )


def _open(pid: str = "abcdef12-0000-0000-0000-000000000001", *, media=False):
    return OpenPromise(
        id=pid, scheduled_for=NOW + timedelta(hours=2),
        intent="到時候來找你", has_media_obligation=media,
    )


def _prompt(**kw) -> str:
    return _build_prompt(
        character=_character(), user_message="u", assistant_message="a",
        recent_messages=[], local_tz=UTC, now=NOW, **kw,
    )


# ---- prompt block -------------------------------------------------------


async def test_prompt_is_unchanged_without_open_promises() -> None:
    baseline = _prompt()
    assert _prompt(open_promises=()) == baseline
    assert "promise_updates" not in baseline
    assert "尚未發送的約定訊息" not in baseline
    template = mod.get_default_loader().raw("post_turn/processor")
    assert template.count("${promise_section}") == 1
    # The placeholder adds no characters when empty.
    assert mod._render_open_promise_section((), local_tz=UTC) == []


async def test_prompt_lists_open_promises_with_short_id_and_local_time() -> None:
    prompt = _prompt(open_promises=(_open(), _open(
        "ffffffff-0000-0000-0000-000000000002", media=True,
    )))
    assert "id=abcdef12 2026-11-22 14:00｜到時候來找你" in prompt
    assert "id=ffffffff" in prompt
    assert "含需要真的送出的照片／圖片" in prompt
    assert "promise_updates" in prompt
    # Part 1 schedule-alignment instructions live in the same block.
    assert "operator_confirmed_shared" in prompt
    assert "行程對齊" in prompt


# ---- parser -------------------------------------------------------------


async def test_parser_accepts_three_actions_and_expands_short_ids() -> None:
    a = _open("aaaaaaaa-1")
    b = _open("bbbbbbbb-2")
    c = _open("cccccccc-3")
    out = _parse_promise_updates([
        {"promise_id": "aaaaaaaa", "action": "fulfilled", "reason": "到了"},
        {"promise_id": "bbbbbbbb-2", "action": "cancelled"},
        {"promise_id": "cccccccc", "action": "rescheduled",
         "scheduled_for_iso": "2026-11-24T15:00"},
    ], open_promises=(a, b, c))
    assert [(u.promise_id, u.action) for u in out] == [
        ("aaaaaaaa-1", "fulfilled"),
        ("bbbbbbbb-2", "cancelled"),
        ("cccccccc-3", "rescheduled"),
    ]
    assert out[2].scheduled_for_iso == "2026-11-24T15:00"
    assert out[0].reason == "到了"


async def test_parser_drops_unknown_ids_bad_actions_and_bad_reschedules() -> None:
    a = _open("aaaaaaaa-1")
    out = _parse_promise_updates([
        {"promise_id": "zzzzzzzz", "action": "cancelled"},
        {"promise_id": "aaaaaaaa", "action": "teleport"},
        {"promise_id": "aaaaaaaa", "action": "rescheduled"},
        {"promise_id": "aaaaaaaa", "action": "rescheduled",
         "scheduled_for_iso": "tomorrow"},
        "junk",
    ], open_promises=(a,))
    assert out == []


async def test_parser_without_shown_promises_accepts_nothing() -> None:
    assert _parse_promise_updates(
        [{"promise_id": "aaaaaaaa", "action": "cancelled"}], open_promises=(),
    ) == []


async def test_parser_rejects_fulfilled_for_media_promise_only() -> None:
    media = _open("mmmmmmmm-1", media=True)
    out = _parse_promise_updates([
        {"promise_id": "mmmmmmmm", "action": "fulfilled"},
    ], open_promises=(media,))
    assert out == []
    out = _parse_promise_updates([
        {"promise_id": "mmmmmmmm", "action": "cancelled"},
    ], open_promises=(media,))
    assert [u.action for u in out] == ["cancelled"]


async def test_parser_keeps_first_verdict_per_promise() -> None:
    a = _open("aaaaaaaa-1")
    out = _parse_promise_updates([
        {"promise_id": "aaaaaaaa", "action": "cancelled"},
        {"promise_id": "aaaaaaaa", "action": "fulfilled"},
    ], open_promises=(a,))
    assert [u.action for u in out] == ["cancelled"]


async def test_full_response_carries_updates_and_keeps_message_promises() -> None:
    a = _open("aaaaaaaa-1")
    raw = json.dumps({
        "memories": [], "schedule_adjustments": [],
        "promise_updates": [{"promise_id": "aaaaaaaa", "action": "cancelled"}],
        "message_promises": [],
    })
    result = _parse_response(
        raw, character_id="c", conversation_id="x", open_promises=(a,),
    )
    assert [u.action for u in result.promise_updates] == ["cancelled"]
    # Without shown promises the field is ignored entirely.
    result = _parse_response(raw, character_id="c", conversation_id="x")
    assert result.promise_updates == []


async def test_processor_only_shows_and_accepts_what_it_was_given() -> None:
    seen: list[str] = []

    class _Model:
        provider_id = "scripted"

        async def generate(self, prompt: str) -> str:
            seen.append(prompt)
            return json.dumps({
                "promise_updates": [
                    {"promise_id": "abcdef12", "action": "cancelled"},
                ],
            })

    processor = LLMPostTurnProcessor(model=_Model())
    kwargs = dict(
        character=_character(), conversation_id="c", user_message="u",
        assistant_message="a", now=NOW,
    )
    result = await processor.process(**kwargs, open_promises=[_open()])
    assert [u.action for u in result.promise_updates] == ["cancelled"]
    assert "id=abcdef12" in seen[0]
    result = await processor.process(**kwargs)
    assert result.promise_updates == []


# ---- Part 2 -------------------------------------------------------------


async def test_remove_of_future_activity_keeps_its_day() -> None:
    out = _parse_adjustments(
        [{"action": "remove", "activity_id": "fut-1",
          "target_date_iso": "2030-01-01"}],
        known_activity_ids={"fut-1"},
        future_activity_dates={"fut-1": "2026-11-23"},
    )
    # The day comes from the schedule the model was shown, not from the model.
    assert [(a.action, a.target_date_iso) for a in out] == [
        ("remove", "2026-11-23"),
    ]


async def test_modify_and_today_remove_still_lose_their_date() -> None:
    out = _parse_adjustments(
        [
            {"action": "modify", "activity_id": "fut-1", "start": "10:00",
             "target_date_iso": "2026-11-23"},
            {"action": "remove", "activity_id": "today-1",
             "target_date_iso": "2026-11-23"},
        ],
        known_activity_ids={"fut-1", "today-1"},
        future_activity_dates={"fut-1": "2026-11-23"},
    )
    assert [(a.action, a.target_date_iso) for a in out] == [
        ("modify", None), ("remove", None),
    ]


async def test_schedule_service_removes_a_future_day_activity() -> None:
    repo = InMemoryScheduleRepository()
    service = ScheduleService(repository=repo, planner=None, local_tz=UTC)  # type: ignore[arg-type]
    char = _character()
    tomorrow = (datetime.now(UTC) + timedelta(days=2)).date()
    start = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC).replace(hour=10)
    kept = ScheduleActivity.create(
        start_at=start + timedelta(hours=3), end_at=start + timedelta(hours=4),
        description="別的事", category="work",
    )
    gone = ScheduleActivity.create(
        start_at=start, end_at=start + timedelta(hours=1),
        description="舊約會", category="social",
    )
    memo = ScheduleActivity.create(
        start_at=start + timedelta(hours=5), end_at=start + timedelta(hours=6),
        description="已記憶", category="work",
    )
    from dataclasses import replace
    memo = replace(memo, memorialized=True)
    await repo.save(DailySchedule.create(
        character_id=char.id, date_=tomorrow, activities=[kept, gone, memo],
    ))

    await service.apply_adjustments(
        character_id=char.id,
        adjustments=[
            ScheduleAdjustment(
                action="remove", activity_id=gone.id,
                target_date_iso=tomorrow.isoformat(),
            ),
            ScheduleAdjustment(
                action="remove", activity_id=memo.id,
                target_date_iso=tomorrow.isoformat(),
            ),
        ],
    )

    left = await repo.get(char.id, tomorrow)
    assert {a.description for a in left.activities} == {"別的事", "已記憶"}


# ---- ChatService application -------------------------------------------


class _Processor:
    """Returns whatever result it is told to, recording what it was shown."""

    def __init__(self) -> None:
        self.result = PostTurnResult()
        self.seen: dict = {}
        self.calls = 0

    async def process(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        self.seen = kwargs
        return self.result


class _World:
    def __init__(self) -> None:
        self.pending = InMemoryPendingFollowUpRepository()
        self.processor = _Processor()
        self.conversations = InMemoryConversationRepository()
        self.characters = InMemoryCharacterRepository()
        self.character = _character()
        registry = InMemoryChatModelRegistry(default_provider_id="fake")
        registry.register(FakeChatModel(provider_id="fake"))
        self.chat = ChatService(
            character_repository=self.characters,
            conversation_repository=self.conversations,
            memory_repository=InMemoryMemoryRepository(),
            post_turn_processor=self.processor,
            prompt_context_builder=DefaultPromptContextBuilder(),
            model_registry=registry,
            state_engine=SimpleStateEngine(),
            pending_follow_up_repository=self.pending,
        )

    async def row(
        self, *, hours: float = 2, intent: str = "到時候來找你",
        conversation_id: str = "conv-1",
    ) -> PendingFollowUp:
        now = datetime.now(UTC)
        row = PendingFollowUp.new_promise(
            character_id=self.character.id, conversation_id=conversation_id,
            promise_intent=intent,
            scheduled_for=now + timedelta(hours=hours),
            source_message_content="約好了", now=now,
        )
        return await self.pending.add(row)

    async def run(self, **kw) -> dict:
        return await self.chat._do_post_turn(
            character=self.character, conversation_id="conv-1",
            turn_record_id="turn-1", user_text="u", assistant_text="a",
            prior_messages=[], **kw,
        )


async def test_open_promises_are_loaded_inside_the_post_turn_body() -> None:
    world = _World()
    queued = await world.row(hours=2)
    other = await world.row(hours=3, intent="別的", conversation_id="conv-9")
    resolving = await world.row(hours=4, intent="處理中")
    await world.pending.save(resolving.marked_resolving())
    repair = PendingFollowUp.new_promise(
        character_id=world.character.id, conversation_id="conv-1",
        promise_intent="修復", scheduled_for=datetime.now(UTC) + timedelta(hours=1),
        defer_reason="honesty_repair",
    )
    await world.pending.add(repair)

    await world.run()

    shown = world.processor.seen["open_promises"]
    # Every conversation of the character, queued only, no repair rows,
    # soonest first.
    assert [p.id for p in shown] == [queued.id, other.id]
    assert all(isinstance(p, OpenPromise) for p in shown)


async def test_no_open_promises_means_the_kwarg_is_absent() -> None:
    world = _World()
    await world.run()
    assert "open_promises" not in world.processor.seen


async def test_fulfilled_resolves_the_row_in_place() -> None:
    world = _World()
    row = await world.row()
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(promise_id=row.id, action="fulfilled", reason="到了"),
    ])
    await world.run()
    saved = await world.pending.get(row.id)
    assert saved.status == PendingFollowUpStatus.RESOLVED
    assert saved.resolved_message.startswith("在對話中履行")
    assert "turn-1" in saved.resolved_message
    assert saved.scheduled_for == row.scheduled_for


async def test_cancelled_cancels_the_row() -> None:
    world = _World()
    row = await world.row()
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(promise_id=row.id, action="cancelled"),
    ])
    await world.run()
    assert (await world.pending.get(row.id)).status == PendingFollowUpStatus.CANCELLED


async def test_rescheduled_moves_the_same_row_and_rekeys_it() -> None:
    world = _World()
    row = await world.row(hours=2)
    new_time = (datetime.now(UTC) + timedelta(days=2)).replace(
        second=0, microsecond=0,
    )
    enqueued: list = []

    class _Enq:
        async def enqueue(self, r, *, now):  # noqa: ANN001
            enqueued.append(r)

    world.chat.set_pending_follow_up_release_enqueuer(_Enq())
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(
            promise_id=row.id, action="rescheduled",
            scheduled_for_iso=new_time.isoformat(),
        ),
    ])
    await world.run()

    saved = await world.pending.get(row.id)
    assert saved.status == PendingFollowUpStatus.QUEUED
    assert saved.scheduled_for == new_time
    assert saved.delivery_slot_key == scheduled_promise_delivery_slot_key(
        character_id=world.character.id, scheduled_for=new_time,
    )
    assert saved.delivery_slot_key != row.delivery_slot_key
    assert saved.dedupe_key != row.dedupe_key
    assert saved.id == row.id and saved.obligations == row.obligations
    # Re-enqueued for the new instant.
    assert [r.id for r in enqueued] == [row.id]
    assert enqueued[0].scheduled_for == new_time
    assert len(await world.pending.list_open_for_character(world.character.id)) == 1


async def test_rescheduled_into_the_past_is_ignored() -> None:
    world = _World()
    row = await world.row()
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(
            promise_id=row.id, action="rescheduled",
            scheduled_for_iso=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        ),
    ])
    await world.run()
    assert await world.pending.get(row.id) == row


async def test_rows_the_dispatcher_already_took_are_never_written() -> None:
    world = _World()
    resolving = await world.row()
    await world.pending.save(resolving.marked_resolving())
    delivered = await world.row(hours=3, intent="已發")
    delivered = delivered.marked_resolved(message_text="sent")
    await world.pending.save(delivered)
    before = {
        r.id: await world.pending.get(r.id) for r in (resolving, delivered)
    }
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(promise_id=resolving.id, action="cancelled"),
        PromiseUpdate(promise_id=delivered.id, action="cancelled"),
        PromiseUpdate(promise_id="nonexistent", action="cancelled"),
    ])
    await world.run()
    for rid, row in before.items():
        assert await world.pending.get(rid) == row


async def test_a_failing_update_does_not_block_the_next_one(monkeypatch) -> None:
    world = _World()
    first = await world.row()
    second = await world.row(hours=3, intent="第二個")
    real_get = world.pending.get
    calls = {"n": 0}

    async def flaky_get(rid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db hiccup")
        return await real_get(rid)

    monkeypatch.setattr(world.pending, "get", flaky_get)
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(promise_id=first.id, action="cancelled"),
        PromiseUpdate(promise_id=second.id, action="cancelled"),
    ])
    out = await world.run()
    assert "post_turn_error" not in out
    assert (await real_get(first.id)).status == PendingFollowUpStatus.QUEUED
    assert (await real_get(second.id)).status == PendingFollowUpStatus.CANCELLED


async def test_loader_failure_leaves_the_old_behaviour(monkeypatch) -> None:
    world = _World()
    await world.row()

    async def boom(_cid):
        raise RuntimeError("down")

    monkeypatch.setattr(world.pending, "list_open_for_character", boom)
    out = await world.run()
    assert "post_turn_error" not in out
    assert "open_promises" not in world.processor.seen


async def test_update_and_same_slot_message_promise_leave_one_row() -> None:
    world = _World()
    row = await world.row(hours=2)
    new_time = (datetime.now(UTC) + timedelta(days=1)).replace(
        second=0, microsecond=0,
    )
    world.processor.result = PostTurnResult(
        promise_updates=[PromiseUpdate(
            promise_id=row.id, action="rescheduled",
            scheduled_for_iso=new_time.isoformat(),
        )],
        # The model also restates the same promise in message_promises.
        message_promises=[MessagePromise(
            scheduled_for_iso=new_time.isoformat(),
            intent="到時候來找你", source_text="改到明天",
        )],
    )
    await world.run()
    rows = await world.pending.list_open_for_character(world.character.id)
    assert len(rows) == 1
    assert rows[0].id == row.id and rows[0].scheduled_for == new_time


async def test_worker_entry_applies_updates_too() -> None:
    world = _World()
    await world.characters.save(world.character)
    row = await world.row()
    # The worker rebuilds the turn from stored messages.
    created = datetime.now(UTC)
    await world.conversations.save(Conversation(
        id="conv-1", character_id=world.character.id, messages=[
            Message(role=MessageRole.USER, content="我起床了", created_at=created),
            Message(role=MessageRole.ASSISTANT, content="早安", created_at=created),
        ],
    ))
    world.processor.result = PostTurnResult(promise_updates=[
        PromiseUpdate(promise_id=row.id, action="cancelled"),
    ])
    result = await world.chat.run_post_turn_for_record(
        turn_record_id="turn-1", conversation_id="conv-1",
        character_id=world.character.id, assistant_index=1, now=created,
    )
    assert "post_turn_skipped" not in result
    assert world.processor.seen["open_promises"][0].id == row.id
    assert (await world.pending.get(row.id)).status == PendingFollowUpStatus.CANCELLED


async def test_media_promise_is_flagged_for_the_processor() -> None:
    world = _World()
    await world.row(intent="晚點傳照片給你")
    await world.row(hours=3, intent="叫你起床")
    await world.run()
    flags = {p.intent: p.has_media_obligation for p in world.processor.seen["open_promises"]}
    assert flags == {"晚點傳照片給你": True, "叫你起床": False}


# ---- turn undo ----------------------------------------------------------


async def _undo_world():
    wiring = _Wiring(
        decider=ScriptedDecider([]),
        schedule_service=StubScheduleService(current_activity=None),
    )
    created = await wiring.create_character()
    # A promise made on a DIFFERENT conversation than the one the turn runs on.
    now = datetime.now(UTC)
    row = PendingFollowUp.new_promise(
        character_id=created.id, conversation_id="other-conv",
        promise_intent="到時候來找你",
        scheduled_for=now + timedelta(hours=3),
        source_message_content="約好了", now=now,
    )
    row = await wiring.follow_ups.add(row)
    reply = await wiring.chat.send_message(
        SendChatMessageRequest(character_id=created.id, message="我起床了"),
    )
    return wiring, created, row, reply


@pytest.mark.parametrize("action", ["fulfilled", "cancelled", "rescheduled"])
async def test_undo_restores_a_promise_on_another_conversation(action) -> None:
    wiring, created, row, reply = await _undo_world()
    journal = await wiring.journals.get_latest(reply.conversation_id)
    # The snapshot names the character's promise even though the turn's
    # conversation is a different one.
    assert any(d["id"] == row.id for d in journal.prev_open_follow_ups)

    update = PromiseUpdate(
        promise_id=row.id, action=action,
        scheduled_for_iso=(
            (datetime.now(UTC) + timedelta(days=2)).isoformat()
            if action == "rescheduled" else None
        ),
    )
    await wiring.chat._apply_promise_updates(
        character_id=created.id, updates=[update], operator=None,
        turn_record_id=journal.turn_record_id,
    )
    changed = await wiring.follow_ups.get(row.id)
    assert changed != row

    result = await wiring.undo.undo_last_turn(reply.conversation_id)

    assert result.restored_follow_ups >= 1
    restored = await wiring.follow_ups.get(row.id)
    assert restored.status == PendingFollowUpStatus.QUEUED
    assert restored.scheduled_for == row.scheduled_for
    assert restored.delivery_slot_key == row.delivery_slot_key
    assert restored.resolved_message is None


async def test_undo_never_deletes_the_other_conversations_promise() -> None:
    wiring, created, row, reply = await _undo_world()
    result = await wiring.undo.undo_last_turn(reply.conversation_id)
    assert result.deleted_follow_ups == 0
    assert await wiring.follow_ups.get(row.id) == row


async def test_undo_does_not_reopen_a_row_the_dispatcher_has_since_delivered() -> None:
    wiring, created, row, reply = await _undo_world()
    delivered = (await wiring.follow_ups.get(row.id)).marked_resolved(
        message_text="早安，起床囉",
    )
    await wiring.follow_ups.save(delivered)
    await wiring.undo.undo_last_turn(reply.conversation_id)
    assert (await wiring.follow_ups.get(row.id)).status == PendingFollowUpStatus.RESOLVED
