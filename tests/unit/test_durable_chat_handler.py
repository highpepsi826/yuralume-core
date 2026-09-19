"""Tests for the durable command to ChatService adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from kokoro_link.application.services.chat_turn_lease import ConversationBusyError
from kokoro_link.application.services.durable_chat_handler import (
    ChatServiceDurableCommandHandler,
)
from kokoro_link.application.services.post_turn_runner import (
    PostTurnEnqueueOutcome,
)
from kokoro_link.contracts.durable_chat_commands import (
    AcceptedCommand,
    ChatTurnPhase,
    ChatTurnCommandSubmission,
    canonical_payload_hash,
    canonical_payload_json,
)
from kokoro_link.contracts.durable_chat_execution import (
    DurableChatExecutionOutcome,
    DurableChatRetryableError,
)
from kokoro_link.contracts.durable_chat_effects import ChatTurnEffectState
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_effects import (
    InMemoryDurableChatEffectLedger,
)
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_commands import (
    InMemoryDurableChatCommandRepository,
)


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _submission() -> ChatTurnCommandSubmission:
    payload = {
        "character_id": "character-1",
        "conversation_id": "conversation-1",
        "message": "hello",
    }
    return ChatTurnCommandSubmission(
        owner_id="user-1",
        client_message_id="client-1",
        character_id="character-1",
        conversation_id="conversation-1",
        payload_hash=canonical_payload_hash(payload),
        payload_json=canonical_payload_json(payload),
        accepted_at=NOW,
    )


@pytest.mark.asyncio
async def test_handler_rehydrates_payload_and_injects_server_turn_id() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)
    claim = await repository.claim_next("worker-1", lease_seconds=30, now=NOW)
    assert claim is not None
    captured: list[tuple[object, str | None]] = []
    phases: list[ChatTurnPhase] = []

    class _ChatService:
        async def send_message(self, payload, *, current_user_id):  # noqa: ANN001
            captured.append((payload, current_user_id))
            return SimpleNamespace(
                model_dump=lambda mode="json": {
                    "conversation_id": "conversation-1",
                    "assistant_message": {"content": "ok"},
                },
            )

    async def heartbeat(phase: ChatTurnPhase) -> bool:
        phases.append(phase)
        return True

    handler = ChatServiceDurableCommandHandler(_ChatService())
    result = await handler(claim.command, heartbeat=heartbeat)

    assert isinstance(result, DurableChatExecutionOutcome)
    assert len(captured) == 1
    payload, owner_id = captured[0]
    assert payload.durable_turn_id == claim.command.turn_id
    assert payload.message == "hello"
    assert owner_id == "user-1"
    assert phases == [
        ChatTurnPhase.PREPARING,
        ChatTurnPhase.WAITING_MODEL,
        ChatTurnPhase.COMMITTING,
    ]


@pytest.mark.asyncio
async def test_handler_maps_conversation_busy_to_safe_retry() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)
    claim = await repository.claim_next("worker-1", lease_seconds=30, now=NOW)
    assert claim is not None

    class _ChatService:
        async def send_message(self, payload, *, current_user_id):  # noqa: ANN001, ARG002
            raise ConversationBusyError("conversation-1")

    async def heartbeat(phase: ChatTurnPhase) -> bool:  # noqa: ARG001
        return True

    handler = ChatServiceDurableCommandHandler(_ChatService())
    with pytest.raises(DurableChatRetryableError) as caught:
        await handler(claim.command, heartbeat=heartbeat)

    assert caught.value.failure_code == "conversation_busy"
    assert caught.value.retry_after_seconds == 2


@pytest.mark.asyncio
async def test_committed_recovery_requeues_pending_effect_without_replaying_body() -> None:
    effects = InMemoryDurableChatEffectLedger()
    await effects.ensure(
        turn_id="turn-1",
        effect_kind="post_turn",
        idempotency_key="turn-1:post_turn",
        payload_json="{}",
        now=NOW,
    )
    enqueue_calls = 0

    class _ChatService:
        async def enqueue_post_turn_for_record(self, **kwargs):  # noqa: ANN003
            nonlocal enqueue_calls
            enqueue_calls += 1
            return PostTurnEnqueueOutcome.INSERTED

    handler = ChatServiceDurableCommandHandler(
        _ChatService(),
        effects=effects,
    )
    command = SimpleNamespace(
        turn_id="turn-1",
        conversation_id="conversation-1",
        character_id="character-1",
        owner_id="user-1",
        assistant_message_position=1,
        payload_json=json.dumps({
            "message": "hello",
            "operator_persona_enabled": True,
        }),
    )

    await handler._recover_committed_effect(command)  # noqa: SLF001

    assert enqueue_calls == 1
    effect = await effects.get(turn_id="turn-1", effect_kind="post_turn")
    assert effect is not None
    assert effect.state is ChatTurnEffectState.ENQUEUED
