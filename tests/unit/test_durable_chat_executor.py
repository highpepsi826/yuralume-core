"""Isolated run-once tests for the durable foreground chat executor."""

from __future__ import annotations

import hashlib
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from kokoro_link.application.services.durable_chat_executor import (
    DurableChatCommandExecutor,
    DurableChatWorker,
)
from kokoro_link.application.services.durable_chat_handler import (
    ChatServiceDurableCommandHandler,
)
from kokoro_link.application.services.external_chat.turn_support import (
    generated_snapshot_to_json,
)
from kokoro_link.application.services.post_turn_runner import (
    PostTurnEnqueueOutcome,
)
from kokoro_link.contracts.external_chat_execution import GeneratedTurnSnapshot
from kokoro_link.domain.entities.conversation import Conversation, MessageRole
from kokoro_link.domain.entities.conversation import Message
from kokoro_link.infrastructure.repositories.in_memory_conversations import (
    InMemoryConversationRepository,
)
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_effects import (
    InMemoryDurableChatEffectLedger,
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
    DurableChatExecutionStatus,
    DurableChatRecoveryRequiredError,
    DurableChatRetryableError,
)
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_commands import (
    InMemoryDurableChatCommandRepository,
)


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _submission(*, max_attempts: int = 3) -> ChatTurnCommandSubmission:
    payload = {"message": "hello"}
    return ChatTurnCommandSubmission(
        owner_id="user-1",
        client_message_id="client-1",
        character_id="character-1",
        conversation_id="conversation-1",
        payload_hash=canonical_payload_hash(payload),
        payload_json=canonical_payload_json(payload),
        max_attempts=max_attempts,
        accepted_at=NOW,
    )


@pytest.mark.asyncio
async def test_run_once_marks_preparing_heartbeats_and_completes() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)
    seen_phases: list[ChatTurnPhase] = []

    async def handler(command, *, heartbeat):  # noqa: ANN001
        seen_phases.append(command.phase)
        assert await heartbeat(ChatTurnPhase.WAITING_MODEL)
        return DurableChatExecutionOutcome(
            result_message_id=17,
            generated_snapshot_json='{"assistant":"ok"}',
            generated_snapshot_hash=hashlib.sha256(
                b'{"assistant":"ok"}',
            ).hexdigest(),
        )

    executor = DurableChatCommandExecutor(
        repository=repository,
        handler=handler,
        worker_id="chat-worker-1",
        lease_seconds=30,
    )
    result = await executor.run_once(now=NOW)

    assert result.status is DurableChatExecutionStatus.COMPLETED
    assert seen_phases == [ChatTurnPhase.PREPARING]
    command = await repository.get(accepted.command.turn_id, owner_id="user-1")
    assert command is not None
    assert command.state.value == "completed"
    assert command.generated_snapshot_json == '{"assistant":"ok"}'
    assert command.generated_snapshot_hash is not None
    assert command.result_message_id == 17


@pytest.mark.asyncio
async def test_retryable_handler_error_enters_retry_wait() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)

    async def handler(command, *, heartbeat):  # noqa: ANN001, ARG001
        raise DurableChatRetryableError(
            "conversation_busy",
            "conversation lease is temporarily busy",
            retry_after_seconds=8,
        )

    executor = DurableChatCommandExecutor(
        repository=repository,
        handler=handler,
        worker_id="chat-worker-1",
        lease_seconds=30,
    )
    result = await executor.run_once(now=NOW)

    assert result.status is DurableChatExecutionStatus.RETRY_WAIT
    command = await repository.get(accepted.command.turn_id, owner_id="user-1")
    assert command is not None
    assert command.state.value == "retry_wait"
    assert command.next_attempt_at == NOW.replace(second=8)


@pytest.mark.asyncio
async def test_unknown_handler_error_requires_recovery_without_retry() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)

    async def handler(command, *, heartbeat):  # noqa: ANN001, ARG001
        raise RuntimeError("provider response was interrupted")

    executor = DurableChatCommandExecutor(
        repository=repository,
        handler=handler,
        worker_id="chat-worker-1",
        lease_seconds=30,
    )
    result = await executor.run_once(now=NOW)

    assert result.status is DurableChatExecutionStatus.RECOVERY_REQUIRED
    command = await repository.get(accepted.command.turn_id, owner_id="user-1")
    assert command is not None
    assert command.state.value == "recovery_required"
    assert command.next_attempt_at is None
    assert command.failure_code == "executor_unhandled_error"


@pytest.mark.asyncio
async def test_idle_pass_does_not_invoke_handler() -> None:
    repository = InMemoryDurableChatCommandRepository()
    called = False

    async def handler(command, *, heartbeat):  # noqa: ANN001, ARG001
        nonlocal called
        called = True
        return DurableChatExecutionOutcome()

    executor = DurableChatCommandExecutor(
        repository=repository,
        handler=handler,
        worker_id="chat-worker-1",
        lease_seconds=30,
    )
    result = await executor.run_once(now=NOW)

    assert result.status is DurableChatExecutionStatus.IDLE
    assert called is False


@pytest.mark.asyncio
async def test_worker_loop_starts_runs_and_stops_cleanly() -> None:
    calls = 0

    class _Executor:
        async def run_once(self, *, now=None):  # noqa: ANN001, ARG002
            nonlocal calls
            calls += 1
            return DurableChatExecutionStatus.IDLE

    worker = DurableChatWorker(executor=_Executor(), loop_seconds=0.01)
    await worker.start()
    assert worker.started is True
    await asyncio.sleep(0.03)
    await worker.stop()

    assert calls >= 1
    assert worker.started is False


@pytest.mark.asyncio
async def test_generated_recovery_finalizes_without_recalling_chat_service() -> None:
    base_now = datetime.now(timezone.utc).replace(microsecond=0)
    repository = InMemoryDurableChatCommandRepository()
    conversations = InMemoryConversationRepository()
    conversation = Conversation.start(character_id="character-1")
    await conversations.save(conversation)
    accepted = await repository.submit(
        ChatTurnCommandSubmission(
            owner_id="user-1",
            client_message_id="client-1",
            character_id="character-1",
            conversation_id=conversation.id,
            payload_hash=canonical_payload_hash({
                "character_id": "character-1",
                "conversation_id": conversation.id,
                "message": "hello",
            }),
            payload_json=canonical_payload_json({
                "character_id": "character-1",
                "conversation_id": conversation.id,
                "message": "hello",
            }),
            accepted_at=base_now,
        ),
    )
    assert isinstance(accepted, AcceptedCommand)
    first = await repository.claim_next("worker-1", lease_seconds=10, now=base_now)
    assert first is not None
    assert await repository.mark_processing(
        turn_id=first.command.turn_id,
        worker_id="worker-1",
        lease_generation=first.command.lease_generation,
        phase=ChatTurnPhase.PREPARING,
        now=base_now,
    )
    snapshot = generated_snapshot_to_json(
        GeneratedTurnSnapshot(
            turn_id=first.command.turn_id,
            assistant_text="recovered reply",
        ),
    )
    assert await repository.mark_generated(
        turn_id=first.command.turn_id,
        worker_id="worker-1",
        lease_generation=first.command.lease_generation,
        snapshot_json=snapshot,
        snapshot_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
        now=base_now,
    )
    calls = 0

    class _ChatService:
        async def send_message(self, *args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal calls
            calls += 1
            raise AssertionError("generated recovery must not call ChatService")

    executor = DurableChatCommandExecutor(
        repository=repository,
        handler=ChatServiceDurableCommandHandler(
            _ChatService(),
            repository=repository,
            conversation_repository=conversations,
            lease_seconds=10,
        ),
        worker_id="worker-2",
        lease_seconds=10,
    )
    result = await executor.run_once(
        now=base_now + timedelta(seconds=11),
    )

    assert result.status is DurableChatExecutionStatus.COMPLETED
    assert calls == 0
    recovered = await repository.get(first.command.turn_id, owner_id="user-1")
    assert recovered is not None
    assert recovered.state.value == "completed"
    assert recovered.assistant_message_id is not None
    saved = await conversations.get(conversation.id)
    assert saved is not None
    assert saved.messages[-1].role is MessageRole.ASSISTANT
    assert saved.messages[-1].content == "recovered reply"


@pytest.mark.asyncio
async def test_committed_recovery_enqueues_missing_effect_without_model() -> None:
    base_now = datetime.now(timezone.utc).replace(microsecond=0)
    repository = InMemoryDurableChatCommandRepository()
    effects = InMemoryDurableChatEffectLedger()
    conversations = InMemoryConversationRepository()
    conversation = Conversation.start(character_id="character-1")
    await conversations.save(conversation)
    payload = {
        "character_id": "character-1",
        "conversation_id": conversation.id,
        "message": "hello",
        "operator_persona_enabled": True,
    }
    accepted = await repository.submit(
        ChatTurnCommandSubmission(
            owner_id="user-1",
            client_message_id="client-1",
            character_id="character-1",
            conversation_id=conversation.id,
            payload_hash=canonical_payload_hash(payload),
            payload_json=canonical_payload_json(payload),
            accepted_at=base_now,
        ),
    )
    assert isinstance(accepted, AcceptedCommand)
    claim = await repository.claim_next("worker-1", lease_seconds=10, now=base_now)
    assert claim is not None
    assert await repository.mark_processing(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        phase=ChatTurnPhase.PREPARING,
        now=base_now,
    )
    user_result = await conversations.append_messages(
        conversation.id,
        expected_next_position=0,
        messages=[Message(role=MessageRole.USER, content="hello")],
        idempotency_key=f"{claim.command.turn_id}:user",
    )
    assert user_result.ok
    assert await repository.record_user_turn(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        user_message_id=user_result.row_ids[0],
        user_message_position=user_result.positions[0],
        now=base_now,
    )
    snapshot = generated_snapshot_to_json(
        GeneratedTurnSnapshot(
            turn_id=claim.command.turn_id,
            assistant_text="committed reply",
        ),
    )
    assert await repository.mark_generated(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        snapshot_json=snapshot,
        snapshot_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
        now=base_now,
    )
    assistant_result = await conversations.append_messages(
        conversation.id,
        expected_next_position=1,
        messages=[Message(role=MessageRole.ASSISTANT, content="committed reply")],
        idempotency_key=f"{claim.command.turn_id}:assistant",
    )
    assert assistant_result.ok
    assert await repository.record_assistant_turn(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        assistant_message_id=assistant_result.row_ids[0],
        assistant_message_position=assistant_result.positions[0],
        now=base_now,
    )
    assert await repository.mark_committed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        result_message_id=assistant_result.row_ids[0],
        now=base_now,
    )
    calls = 0

    class _ChatService:
        async def send_message(self, *args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal calls
            calls += 1
            raise AssertionError("committed recovery must not call ChatService")

        async def enqueue_post_turn_for_record(self, **kwargs):  # noqa: ANN003
            return PostTurnEnqueueOutcome.INSERTED

    executor = DurableChatCommandExecutor(
        repository=repository,
        handler=ChatServiceDurableCommandHandler(
            _ChatService(),
            repository=repository,
            conversation_repository=conversations,
            lease_seconds=10,
            effects=effects,
        ),
        worker_id="worker-2",
        lease_seconds=10,
    )
    result = await executor.run_once(now=base_now + timedelta(seconds=11))

    assert result.status is DurableChatExecutionStatus.COMPLETED
    assert calls == 0
    effect = await effects.get(
        turn_id=claim.command.turn_id, effect_kind="post_turn",
    )
    assert effect is not None
    assert effect.state.value == "enqueued"
