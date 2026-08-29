"""Focused tests for manual scheduled-promise queue maintenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from kokoro_link.application.services.pending_follow_up_admin_service import (
    PendingFollowUpConflictError,
    PendingFollowUpNotFoundError,
    PendingFollowUpAdminService,
    PendingFollowUpStateError,
    PendingFollowUpValidationError,
)
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.domain.entities.pending_follow_up import (
    PendingFollowUp,
    PendingFollowUpKind,
    PendingFollowUpMessage,
)
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.repositories.in_memory_characters import (
    InMemoryCharacterRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_pending_follow_ups import (
    InMemoryPendingFollowUpRepository,
)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class ReleaseSpy:
    calls: list[tuple[str, str]]

    async def enqueue(self, row, *, now):  # noqa: ANN001
        self.calls.append(("enqueue", row.id))
        return True


@dataclass
class WithdrawSpy:
    calls: list[tuple[str, str]]

    async def withdraw(self, row, *, now):  # noqa: ANN001
        self.calls.append(("withdraw", row.id))
        return 1


async def _service(
    *,
    with_hooks: bool = False,
) -> tuple[
    PendingFollowUpAdminService,
    InMemoryPendingFollowUpRepository,
    InMemoryConversationRepository,
    ReleaseSpy | None,
    WithdrawSpy | None,
]:
    characters = InMemoryCharacterRepository()
    await characters.save(Character.create(
        name="桃桃",
        summary="",
        personality=[],
        interests=[],
        speaking_style="",
        boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=10, trust=50, energy=80,
        ),
    ))
    character = (await characters.list())[0]
    conversations = InMemoryConversationRepository()
    conversation = Conversation.start(character_id=character.id, source="telegram")
    await conversations.save(conversation)
    pending = InMemoryPendingFollowUpRepository()
    enqueue = ReleaseSpy([]) if with_hooks else None
    withdraw = WithdrawSpy([]) if with_hooks else None
    service = PendingFollowUpAdminService(
        repository=pending,
        character_repository=characters,
        conversation_repository=conversations,
        clock=FixedClock(),
        release_enqueuer=enqueue,
        release_withdrawer=withdraw,
    )
    return service, pending, conversations, enqueue, withdraw


@pytest.mark.asyncio
async def test_create_uses_latest_existing_conversation_and_enqueues() -> None:
    service, repo, _conversations, enqueue, _withdraw = await _service(
        with_hooks=True,
    )
    row = await service.create_scheduled_promise(
        character_id=(await service._characters.list())[0].id,  # noqa: SLF001
        scheduled_for=NOW + timedelta(hours=2),
        promise_intent="明天提醒我帶卡",
    )

    assert row.kind == PendingFollowUpKind.SCHEDULED_PROMISE
    assert row.conversation_id == (await _conversations.latest_for_character(
        row.character_id, source=None,
    )).id
    assert row.turn_record_id is None
    assert row.commitment_key is None
    assert enqueue is not None and enqueue.calls == [("enqueue", row.id)]


@pytest.mark.asyncio
async def test_create_requires_existing_conversation() -> None:
    characters = InMemoryCharacterRepository()
    character = Character.create(
        name="桃桃", summary="", personality=[], interests=[],
        speaking_style="", boundaries=[],
        state=CharacterState(
            emotion="neutral", affection=50, fatigue=10, trust=50, energy=80,
        ),
    )
    await characters.save(character)
    service = PendingFollowUpAdminService(
        repository=InMemoryPendingFollowUpRepository(),
        character_repository=characters,
        conversation_repository=InMemoryConversationRepository(),
        clock=FixedClock(),
    )

    with pytest.raises(PendingFollowUpNotFoundError, match="conversation"):
        await service.create_scheduled_promise(
            character_id=character.id,
            scheduled_for=NOW + timedelta(hours=1),
            promise_intent="提醒喝水",
        )


@pytest.mark.asyncio
async def test_edit_rebuilds_derived_fields_and_preserves_source_anchor() -> None:
    service, repo, _conversations, _enqueue, withdraw = await _service(
        with_hooks=True,
    )
    character_id = (await service._characters.list())[0].id  # noqa: SLF001
    original = PendingFollowUp.new_promise(
        character_id=character_id,
        conversation_id="conv-manual",
        promise_intent="原本提醒帶卡",
        scheduled_for=NOW + timedelta(hours=1),
        source_message_content="玩家原始約定",
        turn_record_id="turn-1",
        commitment_key="commitment-1",
        now=NOW,
    )
    # The service only needs the conversation id to be valid when editing.
    await repo.add(original)
    edited = await service.update_scheduled_promise(
        original.id,
        scheduled_for=NOW + timedelta(hours=3),
        promise_intent="改成提醒交卡",
    )

    assert edited.scheduled_for == NOW + timedelta(hours=3)
    assert edited.promise_intent == "改成提醒交卡"
    assert edited.dedupe_key != original.dedupe_key
    assert edited.delivery_slot_key != original.delivery_slot_key
    assert edited.messages == original.messages
    assert edited.turn_record_id == "turn-1"
    assert edited.commitment_key == "commitment-1"
    assert [o.intent for o in edited.obligations] == ["改成提醒交卡"]
    assert withdraw is not None and withdraw.calls == [("withdraw", original.id)]


@pytest.mark.asyncio
async def test_edit_rejects_non_queued_past_and_occupied_slot() -> None:
    service, repo, _conversations, _enqueue, _withdraw = await _service()
    character_id = (await service._characters.list())[0].id  # noqa: SLF001
    queued = PendingFollowUp.new_promise(
        character_id=character_id,
        conversation_id="conv-1",
        promise_intent="第一個",
        scheduled_for=NOW + timedelta(hours=1),
        now=NOW,
    )
    other = PendingFollowUp.new_promise(
        character_id=character_id,
        conversation_id="conv-1",
        promise_intent="第二個",
        scheduled_for=NOW + timedelta(hours=3),
        now=NOW,
    )
    await repo.add(queued)
    await repo.add(other)

    with pytest.raises(PendingFollowUpValidationError, match="future"):
        await service.update_scheduled_promise(
            queued.id,
            scheduled_for=NOW - timedelta(minutes=1),
        )
    with pytest.raises(PendingFollowUpConflictError, match="delivery slot"):
        await service.update_scheduled_promise(
            queued.id,
            scheduled_for=other.scheduled_for,
        )

    await repo.save(queued.marked_resolving(now=NOW))
    with pytest.raises(PendingFollowUpStateError, match="queued"):
        await service.update_scheduled_promise(
            queued.id,
            promise_intent="不可編輯",
        )


@pytest.mark.asyncio
async def test_delete_only_removes_queued_scheduled_promise() -> None:
    service, repo, _conversations, _enqueue, withdraw = await _service(
        with_hooks=True,
    )
    character_id = (await service._characters.list())[0].id  # noqa: SLF001
    row = PendingFollowUp.new_promise(
        character_id=character_id,
        conversation_id="conv-1",
        promise_intent="刪除我",
        scheduled_for=NOW + timedelta(hours=1),
        now=NOW,
    )
    await repo.add(row)
    assert await service.delete_scheduled_promise(row.id) is True
    assert await repo.get(row.id) is None
    assert withdraw is not None and withdraw.calls == [("withdraw", row.id)]

    with pytest.raises(PendingFollowUpNotFoundError):
        await service.delete_scheduled_promise(row.id)


@pytest.mark.asyncio
async def test_delete_rejects_busy_defer() -> None:
    service, repo, _conversations, _enqueue, _withdraw = await _service()
    character_id = (await service._characters.list())[0].id  # noqa: SLF001
    busy = PendingFollowUp.new(
        character_id=character_id,
        conversation_id="conv-1",
        first_message=PendingFollowUpMessage.new(content="忙碌"),
        brief_reply="稍後回覆",
        defer_reason="busy",
        scheduled_for=NOW + timedelta(hours=1),
        now=NOW,
    )
    await repo.add(busy)
    with pytest.raises(PendingFollowUpStateError, match="scheduled"):
        await service.delete_scheduled_promise(busy.id)
