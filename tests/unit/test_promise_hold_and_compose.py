"""I-19 Part 3a / 3c: hold a due promise while the pair are talking, and give
the held-then-released compose the facts that stop it reading as lateness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kokoro_link.application.services.ongoing_interaction import (
    minutes_since_active_conversation,
)
from kokoro_link.application.services.pending_follow_up_dispatcher import (
    PendingFollowUpDispatcher,
)
from kokoro_link.contracts.scheduled_promise_composer import (
    ScheduledPromiseComposeInput,
)
from kokoro_link.domain.entities.conversation import (
    Conversation,
    Message,
    MessageKind,
    MessageRole,
)
from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    PendingFollowUpStatus,
)
from kokoro_link.domain.entities.schedule import (
    OPERATOR_CONFIRMED_SHARED_ROLE,
    ScheduleActivity,
)
from kokoro_link.domain.value_objects.actor import ParticipantRef
from kokoro_link.infrastructure.busy.llm_scheduled_promise_composer import (
    _build_prompt,
)
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_pending_follow_ups import (
    InMemoryPendingFollowUpRepository,
)
from tests.unit.test_pending_follow_up_dispatcher_promise import (
    _StubBusyComposer,
    _StubCharacterRepo,
    _StubProactiveDispatcher,
    _StubPromiseComposer,
    _StubScheduleService,
    _character,
    _now,
    _promise_row,
)

UTC = timezone.utc
U, A = MessageRole.USER, MessageRole.ASSISTANT
NOW = _now()


def _m(role, minutes_ago, *, kind=MessageKind.CHAT) -> Message:
    return Message(
        role=role, content="hi", kind=kind,
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


# ---- minutes_since_active_conversation ---------------------------------


def test_active_after_a_recent_reply() -> None:
    assert minutes_since_active_conversation(
        [_m(U, 8), _m(A, 6)], now=NOW,
    ) == 6


def test_active_when_the_latest_player_message_is_unanswered() -> None:
    assert minutes_since_active_conversation([_m(U, 3)], now=NOW) == 3
    assert minutes_since_active_conversation(
        [_m(U, 30), _m(A, 29), _m(U, 2)], now=NOW,
    ) == 2


def test_inactive_when_quiet_or_empty() -> None:
    assert minutes_since_active_conversation([], now=NOW) is None
    assert minutes_since_active_conversation(
        [_m(U, 40), _m(A, 38)], now=NOW,
    ) is None
    # A stale unanswered player message does not count either.
    assert minutes_since_active_conversation([_m(U, 40)], now=NOW) is None
    # A character-only message (proactive push) is not a conversation.
    assert minutes_since_active_conversation([_m(A, 2)], now=NOW) is None


def test_answers_for_a_past_instant_and_ignores_the_future() -> None:
    history = [_m(U, 70), _m(A, 68), _m(U, 5), _m(A, 3)]
    at_then = NOW - timedelta(minutes=60)
    assert minutes_since_active_conversation(history, now=at_then) == 8
    # Same call from the present sees the later exchange only.
    assert minutes_since_active_conversation(history, now=NOW) == 3


def test_tool_only_messages_are_not_conversation() -> None:
    assert minutes_since_active_conversation(
        [_m(U, 2, kind=MessageKind.TOOL_ONLY)], now=NOW,
    ) is None


# ---- dispatcher: 3a ----------------------------------------------------


async def _setup(messages, *, unreadable=False):
    repo = InMemoryPendingFollowUpRepository()
    row = await repo.add(_promise_row())
    char = _character()
    conversations = InMemoryConversationRepository()
    if messages is not None:
        await conversations.save(Conversation(
            id="conv-1", character_id=char.id, messages=list(messages),
        ))
    if unreadable:
        async def boom(*a, **k):
            raise RuntimeError("db down")
        conversations.recent_messages_for_character = boom  # type: ignore[method-assign]
    composer = _StubPromiseComposer()
    proactive = _StubProactiveDispatcher()
    dispatcher = PendingFollowUpDispatcher(
        repository=repo,
        composer=_StubBusyComposer(),
        proactive_dispatcher=proactive,
        character_repository=_StubCharacterRepo({char.id: char}),
        conversation_repository=conversations,
        schedule_service=_StubScheduleService(current_activity=None),
        scheduled_promise_composer=composer,
    )
    return dispatcher, repo, row, composer, proactive


@pytest.mark.asyncio
async def test_a_live_conversation_holds_the_promise_unchanged() -> None:
    dispatcher, repo, row, composer, proactive = await _setup(
        [_m(U, 8), _m(A, 6)],
    )
    assert await dispatcher.tick(now=_now()) == 0
    assert composer.calls == [] and proactive.calls == []
    assert await repo.get(row.id) == row  # untouched: status, scheduled_for


@pytest.mark.asyncio
async def test_an_unanswered_player_message_also_holds() -> None:
    dispatcher, repo, row, composer, _ = await _setup([_m(U, 2)])
    assert await dispatcher.tick(now=_now()) == 0
    assert composer.calls == []
    assert await repo.get(row.id) == row


@pytest.mark.asyncio
async def test_a_quiet_conversation_releases_as_before() -> None:
    dispatcher, repo, row, composer, proactive = await _setup(
        [_m(U, 60), _m(A, 58)],
    )
    assert await dispatcher.tick(now=_now()) == 1
    assert len(composer.calls) == 1 and len(proactive.calls) == 1
    # Quiet at the promised instant too: nothing special for the composer.
    assert composer.calls[0].conversation_minutes_at_scheduled is None
    assert (await repo.get(row.id)).status == PendingFollowUpStatus.RESOLVED


@pytest.mark.asyncio
async def test_unreadable_history_releases_as_before() -> None:
    dispatcher, repo, row, composer, _ = await _setup(None, unreadable=True)
    assert await dispatcher.tick(now=_now()) == 1
    assert len(composer.calls) == 1


@pytest.mark.asyncio
async def test_no_conversation_repository_releases_as_before() -> None:
    repo = InMemoryPendingFollowUpRepository()
    await repo.add(_promise_row())
    char = _character()
    composer = _StubPromiseComposer()
    dispatcher = PendingFollowUpDispatcher(
        repository=repo, composer=_StubBusyComposer(),
        proactive_dispatcher=_StubProactiveDispatcher(),
        character_repository=_StubCharacterRepo({char.id: char}),
        schedule_service=_StubScheduleService(current_activity=None),
        scheduled_promise_composer=composer,
    )
    assert await dispatcher.tick(now=_now()) == 1


@pytest.mark.asyncio
async def test_busy_defer_rows_are_not_held() -> None:
    repo = InMemoryPendingFollowUpRepository()
    char = _character()
    from kokoro_link.domain.entities.pending_follow_up import (
        PendingFollowUpMessage,
    )
    row = PendingFollowUp.new(
        character_id=char.id, conversation_id="conv-1",
        first_message=PendingFollowUpMessage.new(content="晚餐?", queued_at=_now()),
        brief_reply="等等", defer_reason="會議",
        scheduled_for=_now() - timedelta(minutes=1), now=_now(),
    )
    await repo.add(row)
    conversations = InMemoryConversationRepository()
    await conversations.save(Conversation(
        id="conv-1", character_id=char.id, messages=[_m(U, 8), _m(A, 6)],
    ))
    busy = _StubBusyComposer()

    class _Busy:
        calls = 0

        async def compose(self, payload):
            from kokoro_link.contracts.pending_follow_up_composer import (
                PendingFollowUpComposeOutput,
            )
            _Busy.calls += 1
            return PendingFollowUpComposeOutput(content_text="好了")

    dispatcher = PendingFollowUpDispatcher(
        repository=repo, composer=_Busy(),
        proactive_dispatcher=_StubProactiveDispatcher(),
        character_repository=_StubCharacterRepo({char.id: char}),
        conversation_repository=conversations,
        schedule_service=_StubScheduleService(current_activity=None),
    )
    assert await dispatcher.tick(now=_now()) == 1
    assert _Busy.calls == 1 and busy.calls == 0


@pytest.mark.asyncio
async def test_released_after_a_held_conversation_carries_the_new_input() -> None:
    """Pair was talking at the promised instant (T), then went quiet; the
    next release (T+40) goes out with the minutes-at-T fact."""
    dispatcher, repo, row, composer, _ = await _setup(
        [_m(U, 22), _m(A, 20)],
    )
    # The row is due 1 minute before NOW; at that instant the last reply was
    # 19 minutes earlier (outside hold) -> not held, not flagged. Build the
    # held-then-quiet shape by releasing 40 minutes after the promised time.
    later = NOW + timedelta(minutes=40)
    row2 = await repo.add(_promise_row(promise_intent="提醒吃藥", offset_min=0))
    # exchange around the promised instant (NOW): 5 minutes before it
    conversations = dispatcher._conversations
    conv = await conversations.get("conv-1")
    conv.messages.extend([_m(U, 7), _m(A, 5)])
    await conversations.save(conv)
    await repo.save(row.cancelled())
    assert await dispatcher.tick(now=later) == 1
    sent = [c for c in composer.calls if c.promise_intent == "提醒吃藥"]
    assert sent and sent[0].conversation_minutes_at_scheduled == 5


@pytest.mark.asyncio
async def test_summary_reads_the_unified_timeline_not_only_the_row_conversation() -> None:
    from kokoro_link.contracts.dialogue_summarizer import DialogueSummarizerPort

    seen: list[list[Message]] = []

    class _Summ(DialogueSummarizerPort):
        async def summarize(self, *, character, messages, now, local_tz=None, **kw):
            seen.append(list(messages))
            return "摘要"

    repo = InMemoryPendingFollowUpRepository()
    await repo.add(_promise_row())
    char = _character()
    conversations = InMemoryConversationRepository()
    # The row's conversation is empty; the chat happened on another channel.
    await conversations.save(Conversation(
        id="conv-1", character_id=char.id, messages=[],
    ))
    await conversations.save(Conversation(
        id="conv-tg", character_id=char.id,
        messages=[_m(U, 120), _m(A, 118)],
    ))
    composer = _StubPromiseComposer()
    dispatcher = PendingFollowUpDispatcher(
        repository=repo, composer=_StubBusyComposer(),
        proactive_dispatcher=_StubProactiveDispatcher(),
        character_repository=_StubCharacterRepo({char.id: char}),
        conversation_repository=conversations,
        dialogue_summarizer=_Summ(),
        schedule_service=_StubScheduleService(current_activity=None),
        scheduled_promise_composer=composer,
    )
    assert await dispatcher.tick(now=_now()) == 1
    assert len(seen) == 1 and len(seen[0]) == 2
    assert composer.calls[0].recent_dialogue_summary == "摘要"


# ---- composer: 3c ------------------------------------------------------


def _payload(**kw) -> ScheduledPromiseComposeInput:
    base = dict(
        character=_character(), promise_intent="叫對方起床",
        promise_text="明天十點叫我起床", scheduled_for=NOW,
        current_activity=None, just_finished_activity=None,
        recent_dialogue_summary=None, now=NOW,
    )
    base.update(kw)
    return ScheduledPromiseComposeInput(**base)


def test_prompt_is_unchanged_when_the_new_inputs_are_absent() -> None:
    plain = _build_prompt(_payload())
    assert "正在對話" not in plain
    assert "不算遲到" not in plain
    assert "約好一起的活動" not in plain
    assert any(
        line.startswith("- 約定時間：") and line.endswith("（剛到）")
        for line in plain.splitlines()
    )
    # An ordinary (non-shared) activity adds no marker line either.
    plain_act = _build_prompt(_payload(current_activity=_activity(False)))
    assert "約好一起的活動" not in plain_act


def _activity(shared: bool) -> ScheduleActivity:
    refs = (
        (ParticipantRef(
            actor_kind="operator", actor_id=None, display_name="你",
            role=OPERATOR_CONFIRMED_SHARED_ROLE,
        ),) if shared else ()
    )
    return ScheduleActivity.create(
        start_at=NOW - timedelta(minutes=30), end_at=NOW + timedelta(minutes=30),
        description="一起看電影", category="social", busy_score=0.3,
        participant_refs=refs,
    )


def test_prompt_states_the_conversation_and_drops_the_arrived_just_now_cue() -> None:
    prompt = _build_prompt(_payload(
        conversation_minutes_at_scheduled=7,
        now=NOW + timedelta(minutes=40),
    ))
    assert "你們正在對話中，最後一次來回在那之前約 7 分鐘" in prompt
    assert "不算遲到" in prompt
    time_line = next(
        line for line in prompt.splitlines() if line.startswith("- 約定時間：")
    )
    assert "（剛到）" not in time_line
    assert "你晚了" not in time_line
    assert "正在對話中" in time_line


def test_prompt_marks_a_shared_current_activity() -> None:
    prompt = _build_prompt(_payload(current_activity=_activity(True)))
    assert "這個時段是你們約好一起的活動" in prompt
