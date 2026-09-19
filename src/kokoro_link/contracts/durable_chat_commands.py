"""Durable acceptance contract for foreground web/native chat turns.

This contract deliberately stops at *acceptance*.  It does not claim that an
LLM call has started or that a reply will be available until a foreground
worker claims the command.  The separation gives the client an honest ACK even
when the request that carried it is disconnected immediately afterwards.

The command is the idempotency and ownership spine for one logical user send:

* ``(owner_id, client_message_id)`` is immutable and unique;
* the canonical payload hash rejects reuse of an id for different content;
* one active command is admitted per conversation;
* terminal rows remain queryable so an ACK can be recovered after a timeout.

The SQL adapter and the in-memory adapter must implement the same decisions.
The in-memory version is intentionally used by unit tests and local harnesses;
it is not a substitute for the PostgreSQL migration in a hosted deployment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable


COMMAND_CONTRACT_VERSION = 1


class ChatTurnCommandState(StrEnum):
    """Durable lifecycle of a foreground command.

    P1-1 creates ``QUEUED`` rows only.  The later worker slice owns the
    claimed/processing/generated/committed transitions; keeping the full state
    vocabulary here prevents a second, incompatible state machine later.
    """

    QUEUED = "queued"
    CLAIMED = "claimed"
    PROCESSING = "processing"
    GENERATED = "generated"
    COMMITTED = "committed"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatTurnPhase(StrEnum):
    """Observable execution phase inside a durable command state."""

    ACCEPTED = "accepted"
    CLAIMING = "claiming"
    PREPARING = "preparing"
    WAITING_MODEL = "waiting_model"
    PROCESSING_TOOLS = "processing_tools"
    GENERATED = "generated"
    COMMITTING = "committing"
    COMMITTED = "committed"
    RETRY_WAIT = "retry_wait"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE_COMMAND_STATES = frozenset(
    {
        ChatTurnCommandState.QUEUED,
        ChatTurnCommandState.CLAIMED,
        ChatTurnCommandState.PROCESSING,
        ChatTurnCommandState.GENERATED,
        ChatTurnCommandState.COMMITTED,
        ChatTurnCommandState.RETRY_WAIT,
        ChatTurnCommandState.RECOVERY_REQUIRED,
    },
)
TERMINAL_COMMAND_STATES = frozenset(
    {
        ChatTurnCommandState.COMPLETED,
        ChatTurnCommandState.FAILED,
        ChatTurnCommandState.CANCELLED,
    },
)


def canonical_payload_json(payload: Mapping[str, Any]) -> str:
    """Serialize a command payload deterministically for hashing and storage."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    """Return the SHA-256 hash of :func:`canonical_payload_json`."""

    return hashlib.sha256(
        canonical_payload_json(payload).encode("utf-8"),
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ChatTurnCommand:
    """Immutable read model for one accepted foreground command."""

    turn_id: str
    owner_id: str
    client_message_id: str
    character_id: str
    conversation_id: str
    payload_hash: str
    payload_version: int
    payload_json: str
    state: ChatTurnCommandState
    phase: ChatTurnPhase
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    conversation_revision: int | None
    user_message_id: int | None
    user_message_position: int | None
    assistant_message_id: int | None
    assistant_message_position: int | None
    result_message_id: int | None
    generated_snapshot_json: str | None
    generated_snapshot_hash: str | None
    failure_code: str | None
    failure_message: str | None
    lease_owner: str | None
    lease_until: datetime | None
    lease_generation: int
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime
    last_heartbeat_at: datetime | None


@dataclass(frozen=True, slots=True)
class ChatTurnCommandSubmission:
    """Validated input needed to create an accepted command."""

    owner_id: str
    client_message_id: str
    character_id: str
    conversation_id: str
    payload_hash: str
    payload_json: str
    payload_version: int = COMMAND_CONTRACT_VERSION
    conversation_revision: int | None = None
    max_attempts: int = 3
    accepted_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        if not self.client_message_id.strip():
            raise ValueError("client_message_id must not be empty")
        if len(self.client_message_id) > 128:
            raise ValueError("client_message_id is too long")
        if not self.character_id.strip():
            raise ValueError("character_id must not be empty")
        if not self.conversation_id.strip():
            raise ValueError("conversation_id must not be empty")
        if len(self.payload_hash) != 64:
            raise ValueError("payload_hash must be a SHA-256 hex digest")
        try:
            int(self.payload_hash, 16)
        except ValueError as exc:
            raise ValueError("payload_hash must be hexadecimal") from exc
        if self.payload_version < 1:
            raise ValueError("payload_version must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")


@dataclass(frozen=True, slots=True)
class AcceptedCommand:
    command: ChatTurnCommand
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class IdempotencyConflict:
    command: ChatTurnCommand


@dataclass(frozen=True, slots=True)
class ConversationBusy:
    command: ChatTurnCommand


@dataclass(frozen=True, slots=True)
class ClaimedCommand:
    """A worker owns the command lease until its generation changes."""

    command: ChatTurnCommand


CommandSubmissionResult = AcceptedCommand | IdempotencyConflict | ConversationBusy


@runtime_checkable
class DurableChatCommandRepositoryPort(Protocol):
    """Persistence port for the P1-1 acceptance receipt."""

    async def submit(
        self,
        submission: ChatTurnCommandSubmission,
    ) -> CommandSubmissionResult:
        """Accept once, replay a duplicate, or report active conversation busy."""
        ...

    async def get(
        self,
        turn_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        """Return a command only inside the authenticated owner's scope."""
        ...

    async def get_by_client_message_id(
        self,
        client_message_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        """Resolve an ACK timeout without creating a new logical command."""
        ...

    async def active_for_conversation(
        self,
        conversation_id: str,
        *,
        owner_id: str,
    ) -> ChatTurnCommand | None:
        """Return the current active command, if this owner has one."""
        ...

    async def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> ClaimedCommand | None:
        """Claim one queued command, fencing an expired lease first.

        An expired ``claimed``/``processing`` command becomes
        ``recovery_required``. It is deliberately not returned for automatic
        replay because the provider and billing outcome may be unknown.
        """
        ...

    async def mark_processing(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        phase: ChatTurnPhase,
        now: datetime | None = None,
    ) -> bool:
        """Move a live claim to processing under owner/generation fencing."""
        ...

    async def heartbeat(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        lease_seconds: int,
        phase: ChatTurnPhase,
        now: datetime | None = None,
    ) -> bool:
        """Extend a live lease and publish the current phase."""
        ...

    async def record_user_turn(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        user_message_id: int,
        user_message_position: int,
        now: datetime | None = None,
    ) -> bool:
        """Record the idempotently appended user row under the live fence."""
        ...

    async def record_assistant_turn(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        assistant_message_id: int,
        assistant_message_position: int,
        now: datetime | None = None,
    ) -> bool:
        """Record the idempotently appended assistant row under the fence."""
        ...

    async def mark_completed(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        result_message_id: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Fenced terminal completion; clears the worker lease."""
        ...

    async def mark_generated(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        snapshot_json: str,
        snapshot_hash: str,
        now: datetime | None = None,
    ) -> bool:
        """Persist a generated reply snapshot before terminal bookkeeping."""
        ...

    async def mark_committed(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        result_message_id: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Fence the canonical history/effect commit checkpoint."""
        ...

    async def mark_failed(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        failure_code: str,
        failure_message: str,
        retryable: bool,
        retry_after_seconds: int = 0,
        now: datetime | None = None,
    ) -> bool:
        """Record a known failure; retry only before an unknown provider effect."""
        ...

    async def mark_recovery_required(
        self,
        *,
        turn_id: str,
        worker_id: str,
        lease_generation: int,
        failure_code: str,
        failure_message: str,
        now: datetime | None = None,
    ) -> bool:
        """Fence a command into manual/provider reconciliation."""
        ...
