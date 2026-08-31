"""StoryArcService forwards recent-dialogue summary into the planner.

Mirrors ``test_schedule_dialogue_summary`` for the arc pipeline:
``start_new_arc`` should run the summarizer against a bounded, merged
web + Telegram + LINE timeline (tool-only turns filtered) and pass the
output to ``plan_arc``. Missing history / unwired summarizer / summarizer
failure all degrade to ``recent_dialogue_summary=""`` without breaking
arc creation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from kokoro_link.application.services.story_arc_service import StoryArcService
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import (
    Conversation,
    Message,
    MessageKind,
    MessageRole,
)
from kokoro_link.domain.entities.story_arc import (
    TENSION_SETUP,
    StoryArc,
    StoryArcBeat,
)
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_story_arcs import (
    InMemoryStoryArcRepository,
)


UTC = timezone.utc


class _RecordingPlanner:
    def __init__(self) -> None:
        self.last_summary: str | None = None

    async def plan_arc(
        self,
        *,
        character: Character,
        start_date: date,
        duration_days: int = 21,
        beat_count_hint: int = 5,
        hint: str | None = None,
        recent_dialogue_summary: str = "",
    ) -> StoryArc:
        self.last_summary = recent_dialogue_summary
        arc = StoryArc.create(
            character_id=character.id,
            title=hint or "test arc",
            premise="premise",
            theme="custom",
            start_date=start_date,
            end_date=start_date + timedelta(days=duration_days),
        )
        beat = StoryArcBeat.create(
            arc_id=arc.id, sequence=0,
            scheduled_date=start_date,
            title="beat", summary="first",
            tension=TENSION_SETUP,
        )
        return arc.with_beats([beat])


class _RecordingSummarizer:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[list[Message]] = []

    async def summarize(self, *, character, messages, now=None, local_tz=None):  # noqa: ANN001
        self.calls.append(list(messages))
        return self.output


class _ExplodingSummarizer:
    async def summarize(self, *, character, messages, now=None, local_tz=None):  # noqa: ANN001
        raise RuntimeError("summary down")


def _character() -> Character:
    return Character.create(
        name="Mio", summary="", personality=[], interests=[],
        speaking_style="", boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=0, trust=50, energy=100,
        ),
    )


async def _seed_conversation(
    repo: InMemoryConversationRepository, character_id: str,
) -> None:
    convo = Conversation.start(character_id=character_id)
    convo = convo.append(Message(role=MessageRole.USER, content="最近有點煩"))
    convo = convo.append(Message(
        role=MessageRole.ASSISTANT, content="陪你聊聊，別憋著",
    ))
    convo = convo.append(Message(
        role=MessageRole.ASSISTANT, content="",
        kind=MessageKind.TOOL_ONLY,
    ))
    await repo.save(convo)


async def _seed_channel(
    repo: InMemoryConversationRepository,
    character_id: str,
    *,
    source: str,
    messages: list[tuple[MessageRole, str, MessageKind]],
) -> None:
    """Persist a deterministic channel tail for the planner merge test."""
    convo = Conversation.start(character_id=character_id, source=source)
    for index, (role, content, kind) in enumerate(messages):
        convo = convo.append(Message(
            role=role,
            content=content,
            kind=kind,
            created_at=datetime(2026, 4, 18, 12, index, tzinfo=UTC),
        ))
    await repo.save(convo)


@pytest.mark.asyncio
async def test_arc_start_forwards_summary_into_planner() -> None:
    repo = InMemoryStoryArcRepository()
    convos = InMemoryConversationRepository()
    planner = _RecordingPlanner()
    summarizer = _RecordingSummarizer(output="最近你在陪對方處理煩悶")
    service = StoryArcService(
        repository=repo, planner=planner, local_tz=UTC,
        conversation_repository=convos, dialogue_summarizer=summarizer,
    )
    character = _character()
    await _seed_channel(
        convos,
        character.id,
        source="web",
        messages=[(MessageRole.USER, "web context", MessageKind.CHAT)],
    )
    await _seed_channel(
        convos,
        character.id,
        source="telegram",
        messages=[(MessageRole.USER, "telegram context", MessageKind.CHAT)],
    )
    await _seed_channel(
        convos,
        character.id,
        source="line",
        messages=[
            (MessageRole.ASSISTANT, "line context", MessageKind.CHAT),
            (MessageRole.ASSISTANT, "tool artifact", MessageKind.TOOL_ONLY),
        ],
    )

    await service.start_new_arc(character, today=date(2026, 4, 18))

    assert planner.last_summary == "最近你在陪對方處理煩悶"
    assert len(summarizer.calls) == 1
    assert [message.content for message in summarizer.calls[0]] == [
        "web context", "telegram context", "line context",
    ]
    assert all(m.kind is MessageKind.CHAT for m in summarizer.calls[0])


@pytest.mark.asyncio
async def test_arc_start_without_conversation_feeds_empty_summary() -> None:
    repo = InMemoryStoryArcRepository()
    convos = InMemoryConversationRepository()
    planner = _RecordingPlanner()
    summarizer = _RecordingSummarizer(output="should not appear")
    service = StoryArcService(
        repository=repo, planner=planner, local_tz=UTC,
        conversation_repository=convos, dialogue_summarizer=summarizer,
    )

    await service.start_new_arc(_character(), today=date(2026, 4, 18))

    assert planner.last_summary == ""
    assert summarizer.calls == []


@pytest.mark.asyncio
async def test_arc_start_survives_summarizer_failure() -> None:
    repo = InMemoryStoryArcRepository()
    convos = InMemoryConversationRepository()
    planner = _RecordingPlanner()
    service = StoryArcService(
        repository=repo, planner=planner, local_tz=UTC,
        conversation_repository=convos,
        dialogue_summarizer=_ExplodingSummarizer(),
    )
    character = _character()
    await _seed_conversation(convos, character.id)

    arc = await service.start_new_arc(character, today=date(2026, 4, 18))

    assert planner.last_summary == ""
    assert arc.title == "test arc"
