"""Direct route tests for the dark-by-default durable acceptance API."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from kokoro_link.api.routes.chat import (
    get_active_durable_chat_turn,
    get_chat_turn_status,
    resolve_durable_chat_recovery,
    submit_durable_chat_turn,
)
from kokoro_link.application.dto.chat import SendChatMessageRequest
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_commands import (
    InMemoryDurableChatCommandRepository,
)


class _CharacterService:
    async def get_character_entity(self, character_id: str, *, user_id: str = ""):
        return SimpleNamespace(id=character_id, user_id=user_id or "default")


def _container() -> SimpleNamespace:
    return SimpleNamespace(
        character_service=_CharacterService(),
        conversation_repository=InMemoryConversationRepository(),
        durable_chat_command_repository=InMemoryDurableChatCommandRepository(),
    )


@pytest.mark.asyncio
async def test_durable_acceptance_is_disabled_by_default(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.delenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", raising=False)

    with pytest.raises(HTTPException) as caught:
        await submit_durable_chat_turn(
            SendChatMessageRequest(
                character_id="character-1",
                message="hello",
                client_message_id="client-1",
            ),
            container=_container(),
            current_user_id="default",
            _drain_gate=None,
        )

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "durable_chat_acceptance_disabled"


@pytest.mark.asyncio
async def test_enabled_route_returns_durable_ack_and_replays_duplicate(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", "true")
    container = _container()
    payload = SendChatMessageRequest(
        character_id="character-1",
        message="hello",
        client_message_id="client-1",
    )

    first = await submit_durable_chat_turn(
        payload,
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )
    duplicate = await submit_durable_chat_turn(
        payload,
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )

    assert first.status == "queued"
    assert first.phase == "accepted"
    assert first.attempt_count == 0
    assert first.max_attempts == 3
    assert first.lease_until is None
    assert first.lease_generation == 0
    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert duplicate.turn_id == first.turn_id
    assert duplicate.conversation_id == first.conversation_id

    status = await get_chat_turn_status(
        first.turn_id,
        container=container,
        current_user_id="default",
    )
    assert status.status == "queued"
    assert status.client_message_id == "client-1"


@pytest.mark.asyncio
async def test_duplicate_without_conversation_reuses_original_target(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", "true")
    container = _container()
    payload = SendChatMessageRequest(
        character_id="character-1",
        message="hello",
        client_message_id="client-1",
    )

    first = await submit_durable_chat_turn(
        payload,
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )
    newer_conversation = Conversation.start(character_id="character-1")
    await container.conversation_repository.save(newer_conversation)

    duplicate = await submit_durable_chat_turn(
        payload,
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )

    assert duplicate.duplicate is True
    assert duplicate.turn_id == first.turn_id
    assert duplicate.conversation_id == first.conversation_id
    assert duplicate.conversation_id != newer_conversation.id


@pytest.mark.asyncio
async def test_duplicate_ack_is_recoverable_when_character_lookup_now_fails(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", "true")
    container = _container()
    payload = SendChatMessageRequest(
        character_id="character-1",
        message="hello",
        client_message_id="client-1",
    )
    first = await submit_durable_chat_turn(
        payload,
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )
    async def missing_character(character_id: str, *, user_id: str = ""):
        return None

    container.character_service.get_character_entity = missing_character  # type: ignore[method-assign]

    duplicate = await submit_durable_chat_turn(
        payload,
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )

    assert duplicate.duplicate is True
    assert duplicate.turn_id == first.turn_id


@pytest.mark.asyncio
async def test_active_turn_lookup_is_owner_scoped_for_a_second_device(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", "true")
    container = _container()
    accepted = await submit_durable_chat_turn(
        SendChatMessageRequest(
            character_id="character-1",
            message="hello",
            client_message_id="client-1",
        ),
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )

    found = await get_active_durable_chat_turn(
        accepted.conversation_id,
        container=container,
        current_user_id="default",
    )
    hidden = await get_active_durable_chat_turn(
        accepted.conversation_id,
        container=container,
        current_user_id="another-user",
    )

    assert found is not None
    assert found.turn_id == accepted.turn_id
    assert found.status == "queued"
    assert hidden is None


@pytest.mark.asyncio
async def test_owner_can_end_recovery_and_reopen_conversation(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", "true")
    container = _container()
    accepted = await submit_durable_chat_turn(
        SendChatMessageRequest(
            character_id="character-1",
            message="hello",
            client_message_id="client-1",
        ),
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )
    repository = container.durable_chat_command_repository
    claim_time = datetime.now(timezone.utc)
    claim = await repository.claim_next(
        "worker-1", lease_seconds=30,
        now=claim_time,
    )
    assert claim is not None
    assert await repository.mark_recovery_required(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        failure_code="executor_unhandled_error",
        failure_message="unknown provider outcome",
        now=claim_time,
    )

    resolved = await resolve_durable_chat_recovery(
        accepted.turn_id,
        container=container,
        current_user_id="default",
    )

    assert resolved.status == "cancelled"
    assert resolved.failure_code == "recovery_abandoned"
    assert await get_active_durable_chat_turn(
        accepted.conversation_id,
        container=container,
        current_user_id="default",
    ) is None


@pytest.mark.asyncio
async def test_owner_cannot_end_a_live_worker_turn(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setenv("YURALUME_DURABLE_CHAT_ACCEPTANCE_ENABLED", "true")
    container = _container()
    accepted = await submit_durable_chat_turn(
        SendChatMessageRequest(
            character_id="character-1",
            message="hello",
            client_message_id="client-1",
        ),
        container=container,
        current_user_id="default",
        _drain_gate=None,
    )
    claim_time = datetime.now(timezone.utc)
    claim = await container.durable_chat_command_repository.claim_next(
        "worker-1", lease_seconds=30, now=claim_time,
    )
    assert claim is not None

    with pytest.raises(HTTPException) as caught:
        await resolve_durable_chat_recovery(
            accepted.turn_id,
            container=container,
            current_user_id="default",
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "chat_turn_not_recoverable"
