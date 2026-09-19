"""P1-1 contract tests for durable foreground chat acceptance."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from kokoro_link.contracts.durable_chat_commands import (
    AcceptedCommand,
    ChatTurnPhase,
    ChatTurnCommandState,
    ChatTurnCommandSubmission,
    ConversationBusy,
    IdempotencyConflict,
    canonical_payload_hash,
    canonical_payload_json,
)
from kokoro_link.infrastructure.repositories.in_memory_durable_chat_commands import (
    InMemoryDurableChatCommandRepository,
)

def _submission(
    *,
    client_message_id: str = "client-1",
    owner_id: str = "user-1",
    conversation_id: str = "conversation-1",
    message: str = "hello",
    max_attempts: int = 3,
) -> ChatTurnCommandSubmission:
    payload = {
        "character_id": "character-1",
        "conversation_id": conversation_id,
        "message": message,
        "presence_frame": {"surface": "web_stage"},
    }
    return ChatTurnCommandSubmission(
        owner_id=owner_id,
        client_message_id=client_message_id,
        character_id="character-1",
        conversation_id=conversation_id,
        payload_hash=canonical_payload_hash(payload),
        payload_json=canonical_payload_json(payload),
        max_attempts=max_attempts,
        accepted_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )


def test_canonical_payload_is_order_independent() -> None:
    left = {"message": "hello", "nested": {"b": 2, "a": 1}}
    right = {"nested": {"a": 1, "b": 2}, "message": "hello"}

    assert canonical_payload_json(left) == canonical_payload_json(right)
    assert canonical_payload_hash(left) == canonical_payload_hash(right)


@pytest.mark.asyncio
async def test_first_submission_is_queued_and_has_stable_turn_id() -> None:
    repository = InMemoryDurableChatCommandRepository()

    result = await repository.submit(_submission())

    assert isinstance(result, AcceptedCommand)
    assert result.duplicate is False
    assert result.command.state is ChatTurnCommandState.QUEUED
    assert result.command.client_message_id == "client-1"
    assert result.command.conversation_id == "conversation-1"
    assert result.command.accepted_at == datetime(2026, 9, 19, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_retry_with_same_id_and_hash_replays_original_command() -> None:
    repository = InMemoryDurableChatCommandRepository()
    first = await repository.submit(_submission())

    duplicate = await repository.submit(_submission())

    assert isinstance(first, AcceptedCommand)
    assert isinstance(duplicate, AcceptedCommand)
    assert duplicate.duplicate is True
    assert duplicate.command.turn_id == first.command.turn_id


@pytest.mark.asyncio
async def test_reusing_id_for_different_payload_is_a_conflict() -> None:
    repository = InMemoryDurableChatCommandRepository()
    await repository.submit(_submission())

    conflict = await repository.submit(_submission(message="different"))

    assert isinstance(conflict, IdempotencyConflict)
    assert conflict.command.client_message_id == "client-1"


@pytest.mark.asyncio
async def test_second_active_command_for_conversation_is_busy() -> None:
    repository = InMemoryDurableChatCommandRepository()
    first = await repository.submit(_submission())

    busy = await repository.submit(
        _submission(client_message_id="client-2", message="second"),
    )

    assert isinstance(first, AcceptedCommand)
    assert isinstance(busy, ConversationBusy)
    assert busy.command.turn_id == first.command.turn_id


@pytest.mark.asyncio
async def test_terminal_command_releases_conversation_admission() -> None:
    repository = InMemoryDurableChatCommandRepository()
    first = await repository.submit(_submission())
    assert isinstance(first, AcceptedCommand)

    completed = await repository.set_state_for_test(
        first.command.turn_id,
        owner_id="user-1",
        state=ChatTurnCommandState.COMPLETED,
    )
    second = await repository.submit(
        _submission(client_message_id="client-2", message="second"),
    )

    assert completed is not None
    assert isinstance(second, AcceptedCommand)
    assert second.command.turn_id != first.command.turn_id


@pytest.mark.asyncio
async def test_lookup_is_owner_scoped_for_turn_and_client_id() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)

    assert await repository.get(
        accepted.command.turn_id,
        owner_id="another-user",
    ) is None
    assert await repository.get_by_client_message_id(
        "client-1",
        owner_id="another-user",
    ) is None


@pytest.mark.asyncio
async def test_claim_heartbeat_and_generation_fence_the_worker() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted_at = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    accepted = await repository.submit(
        _submission(),
    )
    assert isinstance(accepted, AcceptedCommand)

    claim = await repository.claim_next(
        "worker-1",
        lease_seconds=30,
        now=accepted_at,
    )
    assert claim is not None
    assert claim.command.state is ChatTurnCommandState.CLAIMED
    assert claim.command.phase is ChatTurnPhase.CLAIMING
    assert claim.command.attempt_count == 1
    assert claim.command.lease_generation == 1

    assert await repository.mark_processing(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=1,
        phase=ChatTurnPhase.PREPARING,
        now=accepted_at,
    )
    assert await repository.heartbeat(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=1,
        lease_seconds=30,
        phase=ChatTurnPhase.WAITING_MODEL,
        now=accepted_at.replace(second=10),
    )
    assert not await repository.heartbeat(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=0,
        lease_seconds=30,
        phase=ChatTurnPhase.WAITING_MODEL,
        now=accepted_at.replace(second=10),
    )

    current = await repository.get(claim.command.turn_id, owner_id="user-1")
    assert current is not None
    assert current.phase is ChatTurnPhase.WAITING_MODEL
    assert current.lease_generation == 1


@pytest.mark.asyncio
async def test_retryable_failure_obeys_max_attempts() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(
        _submission(max_attempts=2),
    )
    assert isinstance(accepted, AcceptedCommand)
    accepted_at = accepted.command.accepted_at

    first = await repository.claim_next(
        "worker-1", lease_seconds=30, now=accepted_at,
    )
    assert first is not None
    assert await repository.mark_failed(
        turn_id=first.command.turn_id,
        worker_id="worker-1",
        lease_generation=first.command.lease_generation,
        failure_code="temporary_provider_error",
        failure_message="try again",
        retryable=True,
        retry_after_seconds=10,
        now=accepted_at,
    )
    waiting = await repository.get(first.command.turn_id, owner_id="user-1")
    assert waiting is not None
    assert waiting.state is ChatTurnCommandState.RETRY_WAIT
    assert waiting.next_attempt_at == accepted_at.replace(second=10)

    second = await repository.claim_next(
        "worker-2",
        lease_seconds=30,
        now=accepted_at.replace(second=10),
    )
    assert second is not None
    assert second.command.attempt_count == 2
    assert await repository.mark_failed(
        turn_id=second.command.turn_id,
        worker_id="worker-2",
        lease_generation=second.command.lease_generation,
        failure_code="temporary_provider_error",
        failure_message="still failing",
        retryable=True,
        now=accepted_at.replace(second=11),
    )
    failed = await repository.get(second.command.turn_id, owner_id="user-1")
    assert failed is not None
    assert failed.state is ChatTurnCommandState.FAILED
    assert failed.phase is ChatTurnPhase.FAILED
    assert await repository.claim_next(
        "worker-3", lease_seconds=30, now=accepted_at.replace(second=12),
    ) is None


@pytest.mark.asyncio
async def test_expired_lease_requires_recovery_and_is_not_replayed() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)
    accepted_at = accepted.command.accepted_at
    claim = await repository.claim_next(
        "worker-1", lease_seconds=10, now=accepted_at,
    )
    assert claim is not None

    assert await repository.claim_next(
        "worker-2", lease_seconds=10, now=accepted_at.replace(second=10),
    ) is None
    recovered = await repository.get(claim.command.turn_id, owner_id="user-1")
    assert recovered is not None
    assert recovered.state is ChatTurnCommandState.RECOVERY_REQUIRED
    assert recovered.phase is ChatTurnPhase.RECOVERY_REQUIRED
    assert recovered.failure_code == "worker_lease_expired"
    assert not await repository.mark_completed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        now=accepted_at.replace(second=10),
    )


@pytest.mark.asyncio
async def test_completed_command_clears_lease_and_releases_admission() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)
    claim = await repository.claim_next(
        "worker-1", lease_seconds=30, now=accepted.command.accepted_at,
    )
    assert claim is not None
    assert await repository.mark_completed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        result_message_id=42,
        now=accepted.command.accepted_at,
    )

    completed = await repository.get(claim.command.turn_id, owner_id="user-1")
    assert completed is not None
    assert completed.state is ChatTurnCommandState.COMPLETED
    assert completed.result_message_id == 42
    assert completed.lease_owner is None
    assert await repository.active_for_conversation(
        "conversation-1", owner_id="user-1",
    ) is None


@pytest.mark.asyncio
async def test_generated_and_committed_checkpoints_are_fenced() -> None:
    repository = InMemoryDurableChatCommandRepository()
    accepted = await repository.submit(_submission())
    assert isinstance(accepted, AcceptedCommand)
    claim = await repository.claim_next(
        "worker-1", lease_seconds=30, now=accepted.command.accepted_at,
    )
    assert claim is not None
    assert await repository.mark_processing(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        phase=ChatTurnPhase.WAITING_MODEL,
        now=accepted.command.accepted_at,
    )
    snapshot = '{"assistant":"ok"}'
    snapshot_hash = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    assert await repository.mark_generated(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        snapshot_json=snapshot,
        snapshot_hash=snapshot_hash,
        now=accepted.command.accepted_at,
    )
    assert await repository.mark_committed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=claim.command.lease_generation,
        result_message_id=7,
        now=accepted.command.accepted_at,
    )
    current = await repository.get(claim.command.turn_id, owner_id="user-1")
    assert current is not None
    assert current.state is ChatTurnCommandState.COMMITTED
    assert current.phase is ChatTurnPhase.COMMITTED
    assert current.generated_snapshot_json == snapshot
    assert current.generated_snapshot_hash == snapshot_hash
    assert current.result_message_id == 7
