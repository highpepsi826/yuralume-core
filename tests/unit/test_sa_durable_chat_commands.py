"""SQLite smoke tests for the SQL durable-command adapter.

The production adapter targets PostgreSQL; SQLite keeps this test local and
still exercises ORM expiry, unique admission and owner-scoped reads.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kokoro_link.contracts.durable_chat_commands import (
    AcceptedCommand,
    ChatTurnCommandState,
    ChatTurnPhase,
    ChatTurnCommandSubmission,
    ConversationBusy,
    IdempotencyConflict,
    canonical_payload_hash,
    canonical_payload_json,
)
from kokoro_link.infrastructure.persistence.models import ChatTurnCommandRow
from kokoro_link.infrastructure.persistence.sa_durable_chat_commands import (
    SADurableChatCommandRepository,
)


def _submission(
    *,
    client_message_id: str,
    message: str,
) -> ChatTurnCommandSubmission:
    payload = {"message": message}
    return ChatTurnCommandSubmission(
        owner_id="user-1",
        client_message_id=client_message_id,
        character_id="character-1",
        conversation_id="conversation-1",
        payload_hash=canonical_payload_hash(payload),
        payload_json=canonical_payload_json(payload),
        accepted_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_sql_adapter_returns_snapshots_before_rollback_expiry() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ChatTurnCommandRow.__table__.create)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    repository = SADurableChatCommandRepository(session_factory)

    first = await repository.submit(
        _submission(client_message_id="client-1", message="hello"),
    )
    duplicate = await repository.submit(
        _submission(client_message_id="client-1", message="hello"),
    )
    conflict = await repository.submit(
        _submission(client_message_id="client-1", message="changed"),
    )
    busy = await repository.submit(
        _submission(client_message_id="client-2", message="second"),
    )

    assert isinstance(first, AcceptedCommand)
    assert isinstance(duplicate, AcceptedCommand)
    assert duplicate.duplicate is True
    assert duplicate.command.turn_id == first.command.turn_id
    assert isinstance(conflict, IdempotencyConflict)
    assert isinstance(busy, ConversationBusy)
    assert busy.command.turn_id == first.command.turn_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_adapter_claims_and_fences_lifecycle() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ChatTurnCommandRow.__table__.create)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    repository = SADurableChatCommandRepository(session_factory)
    accepted_at = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)

    accepted = await repository.submit(
        ChatTurnCommandSubmission(
            owner_id="user-1",
            client_message_id="client-1",
            character_id="character-1",
            conversation_id="conversation-1",
            payload_hash=canonical_payload_hash({"message": "hello"}),
            payload_json=canonical_payload_json({"message": "hello"}),
            accepted_at=accepted_at,
        ),
    )
    assert isinstance(accepted, AcceptedCommand)
    claim = await repository.claim_next(
        "worker-1", lease_seconds=30, now=accepted_at,
    )
    assert claim is not None
    assert claim.command.state is ChatTurnCommandState.CLAIMED
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
        now=accepted_at.replace(second=5),
    )
    snapshot = '{"assistant":"ok"}'
    assert await repository.mark_generated(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=1,
        snapshot_json=snapshot,
        snapshot_hash=hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
        now=accepted_at.replace(second=5),
    )
    assert await repository.mark_committed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=1,
        result_message_id=99,
        now=accepted_at.replace(second=6),
    )
    assert not await repository.mark_completed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=0,
        now=accepted_at.replace(second=5),
    )
    assert await repository.mark_completed(
        turn_id=claim.command.turn_id,
        worker_id="worker-1",
        lease_generation=1,
        result_message_id=99,
        now=accepted_at.replace(second=6),
    )
    completed = await repository.get(claim.command.turn_id, owner_id="user-1")
    assert completed is not None
    assert completed.state is ChatTurnCommandState.COMPLETED
    assert completed.phase is ChatTurnPhase.COMPLETED
    assert completed.result_message_id == 99
    assert completed.generated_snapshot_json == snapshot

    await engine.dispose()


@pytest.mark.asyncio
async def test_sql_adapter_expired_claim_becomes_recovery_required() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ChatTurnCommandRow.__table__.create)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    repository = SADurableChatCommandRepository(session_factory)
    accepted_at = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    accepted = await repository.submit(
        _submission(client_message_id="client-1", message="hello"),
    )
    assert isinstance(accepted, AcceptedCommand)
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
    await engine.dispose()
