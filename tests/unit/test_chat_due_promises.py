"""I-19 Part 3b: a due, still-queued promise reaches the chat prompt.

The block is rendered only when a promise is due; the media promise and a
turn that took the busy-defer short-circuit never carry it; both chat entry
points (non-streaming and streaming) read it; nothing is written by the
read (closing the promise is the turn's post-turn's job).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kokoro_link.application.dto.character import CreateCharacterRequest
from kokoro_link.application.dto.chat import SendChatMessageRequest
from kokoro_link.application.services.character_service import CharacterService
from kokoro_link.application.services.chat_service import ChatService
from kokoro_link.contracts.busy_reply_decider import BusyDecision, BusyReplyMode
from kokoro_link.contracts.prompt import DuePromise
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.domain.entities.pending_follow_up import PendingFollowUp
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.llm.fake import FakeChatModel
from kokoro_link.infrastructure.llm.registry import InMemoryChatModelRegistry
from kokoro_link.infrastructure.memory.in_memory import InMemoryMemoryRepository
from kokoro_link.infrastructure.post_turn.null_processor import (
    NullPostTurnProcessor,
)
from kokoro_link.infrastructure.prompt.default import DefaultPromptContextBuilder
from kokoro_link.infrastructure.prompt.sections.order import SECTION_ORDER
from kokoro_link.infrastructure.prompt.sections.schedule import (
    _render_due_promises_block,
)
from kokoro_link.infrastructure.repositories.in_memory_characters import (
    InMemoryCharacterRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_pending_follow_ups import (
    InMemoryPendingFollowUpRepository,
)
from kokoro_link.infrastructure.state.simple import SimpleStateEngine
from tests.unit.busy_defer_harness import (
    ScriptedDecider,
    StubScheduleService,
    busy_activity,
)

UTC = timezone.utc
pytestmark = pytest.mark.asyncio


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def build(self, **kwargs) -> str:  # noqa: ANN003
        self.calls.append(dict(kwargs))
        return f"最新使用者訊息：{kwargs.get('latest_user_message', '')}"


def _wire(*, decider=None, schedule_service=None):
    characters = InMemoryCharacterRepository()
    conversations = InMemoryConversationRepository()
    pending = InMemoryPendingFollowUpRepository()
    recorder = _Recorder()
    registry = InMemoryChatModelRegistry(default_provider_id="fake")
    registry.register(FakeChatModel(provider_id="fake"))
    chat = ChatService(
        character_repository=characters,
        conversation_repository=conversations,
        memory_repository=InMemoryMemoryRepository(),
        post_turn_processor=NullPostTurnProcessor(),
        prompt_context_builder=recorder,
        model_registry=registry,
        state_engine=SimpleStateEngine(),
        pending_follow_up_repository=pending,
        busy_reply_decider=decider,
        schedule_service=schedule_service,
    )
    return chat, CharacterService(characters, conversation_repository=conversations), pending, recorder


async def _promise(pending, character_id, *, minutes: float, intent="提醒吃藥"):
    now = datetime.now(UTC)
    row = PendingFollowUp.new_promise(
        character_id=character_id, conversation_id="other",
        promise_intent=intent,
        scheduled_for=now + timedelta(minutes=minutes),
        source_message_content="記得提醒我", now=now - timedelta(hours=1),
    )
    return await pending.add(row)


async def _send(chat, created, *, stream: bool) -> None:
    request = SendChatMessageRequest(character_id=created.id, message="在嗎")
    if stream:
        token_stream, finalizer = await chat.send_message_stream(request)
        text = ""
        async for chunk in token_stream:
            text += chunk
        await finalizer.finish(text)
    else:
        await chat.send_message(request)
    await chat.wait_for_pending()


@pytest.mark.parametrize("stream", [False, True])
async def test_due_promise_reaches_the_prompt_builder_on_both_entries(stream) -> None:
    chat, characters, pending, recorder = _wire()
    created = await characters.create_character(CreateCharacterRequest(name="Mio"))
    due = await _promise(pending, created.id, minutes=-3)
    await _promise(pending, created.id, minutes=90, intent="還沒到")
    await _send(chat, created, stream=stream)

    seen = recorder.calls[-1]["due_promises"]
    assert [p.intent for p in seen] == ["提醒吃藥"]
    assert all(isinstance(p, DuePromise) for p in seen)
    # Read only: the row is untouched by the chat turn.
    assert await pending.get(due.id) == due


@pytest.mark.parametrize("stream", [False, True])
async def test_nothing_due_passes_an_empty_tuple(stream) -> None:
    chat, characters, pending, recorder = _wire()
    created = await characters.create_character(CreateCharacterRequest(name="Mio"))
    await _promise(pending, created.id, minutes=90)
    await _send(chat, created, stream=stream)
    assert recorder.calls[-1]["due_promises"] == ()


@pytest.mark.parametrize("stream", [False, True])
async def test_media_and_repair_and_resolving_promises_are_not_injected(stream) -> None:
    chat, characters, pending, recorder = _wire()
    created = await characters.create_character(CreateCharacterRequest(name="Mio"))
    await _promise(pending, created.id, minutes=-3, intent="晚點傳照片給你")
    resolving = await _promise(pending, created.id, minutes=-4, intent="處理中的事")
    await pending.save(resolving.marked_resolving())
    repair = PendingFollowUp.new_promise(
        character_id=created.id, conversation_id="other",
        promise_intent="修復", scheduled_for=datetime.now(UTC) - timedelta(minutes=2),
        defer_reason="honesty_repair",
    )
    await pending.add(repair)
    await _send(chat, created, stream=stream)
    assert recorder.calls[-1]["due_promises"] == ()


@pytest.mark.parametrize("stream", [False, True])
async def test_a_deferred_turn_builds_no_prompt_and_carries_nothing(stream) -> None:
    activity = busy_activity()
    chat, characters, pending, recorder = _wire(
        decider=ScriptedDecider([BusyDecision(
            mode=BusyReplyMode.BRIEF_DEFER, brief_reply="等等回你",
            defer_until=activity.end_at, defer_reason="會議",
        )]),
        schedule_service=StubScheduleService(current_activity=activity),
    )
    created = await characters.create_character(CreateCharacterRequest(name="Mio"))
    due = await _promise(pending, created.id, minutes=-3)
    await _send(chat, created, stream=stream)
    # Short-circuited before any prompt was built.
    assert recorder.calls == []
    assert await pending.get(due.id) == due


# ---- rendering ----------------------------------------------------------


async def test_block_is_empty_without_due_promises_and_renders_with_one() -> None:
    assert _render_due_promises_block((), local_tz=UTC) == []
    when = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)
    text = "\n".join(_render_due_promises_block(
        (DuePromise(scheduled_for=when, intent="提醒吃藥"),), local_tz=UTC,
    ))
    assert "到期的約定" in text
    assert "原定 14:00：提醒吃藥" in text
    assert "不要另外開" in text


async def test_default_builder_prompt_is_unchanged_without_due_promises() -> None:
    builder = DefaultPromptContextBuilder()
    character = Character.create(
        name="Mio", summary="", personality=[], interests=[],
        speaking_style="", boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )
    conversation = Conversation.start(character_id=character.id)
    kwargs = dict(
        character=character, conversation=conversation, recent_messages=[],
        memories=[], pending_state=character.state, latest_user_message="嗨",
        now=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
    )
    plain = builder.build(**kwargs)
    assert builder.build(**kwargs, due_promises=()) == plain
    assert "到期的約定" not in plain
    with_due = builder.build(**kwargs, due_promises=(
        DuePromise(
            scheduled_for=datetime(2026, 11, 22, 11, 55, tzinfo=UTC),
            intent="提醒吃藥",
        ),
    ))
    assert "到期的約定" in with_due
    # Sits in the per-turn zone above the turn's tail, below the transcript.
    assert with_due.index("到期的約定") < with_due.index("嗨")
    assert SECTION_ORDER.index("due_promises") < SECTION_ORDER.index("stage_nudge")
