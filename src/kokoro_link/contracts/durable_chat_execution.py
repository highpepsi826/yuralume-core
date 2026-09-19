"""Execution-side contracts for durable foreground chat commands.

The receipt repository owns persistence and fencing.  This module defines the
small boundary a worker handler must implement so the worker can distinguish a
known, safe-to-retry failure from an outcome that may already have reached the
model or billing provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable, Protocol

from kokoro_link.contracts.durable_chat_commands import (
    ChatTurnCommand,
    ChatTurnPhase,
)


class DurableChatExecutionStatus(StrEnum):
    IDLE = "idle"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"
    FENCED = "fenced"


class DurableChatRetryableError(RuntimeError):
    """The handler knows no external effect happened and may retry safely."""

    def __init__(
        self,
        failure_code: str,
        failure_message: str,
        *,
        retry_after_seconds: int = 0,
    ) -> None:
        super().__init__(failure_message)
        self.failure_code = failure_code
        self.failure_message = failure_message
        self.retry_after_seconds = max(0, retry_after_seconds)


class DurableChatFailedError(RuntimeError):
    """A known terminal failure whose command must not be retried."""

    def __init__(self, failure_code: str, failure_message: str) -> None:
        super().__init__(failure_message)
        self.failure_code = failure_code
        self.failure_message = failure_message


class DurableChatRecoveryRequiredError(RuntimeError):
    """The outcome is ambiguous and needs reconciliation before replay."""

    def __init__(self, failure_code: str, failure_message: str) -> None:
        super().__init__(failure_message)
        self.failure_code = failure_code
        self.failure_message = failure_message


@dataclass(frozen=True, slots=True)
class DurableChatExecutionOutcome:
    """Handler output that can be safely attached to a completed receipt."""

    result_message_id: int | None = None
    generated_snapshot_json: str | None = None
    generated_snapshot_hash: str | None = None
    generated_already_persisted: bool = False
    committed_already_persisted: bool = False


@dataclass(frozen=True, slots=True)
class DurableChatExecutionResult:
    """Observable result of one worker ``run_once`` pass."""

    status: DurableChatExecutionStatus
    turn_id: str | None = None
    attempt_count: int | None = None


DurableChatHeartbeat = Callable[
    [ChatTurnPhase], Awaitable[bool]
]


class DurableChatCommandHandler(Protocol):
    async def __call__(
        self,
        command: ChatTurnCommand,
        *,
        heartbeat: DurableChatHeartbeat,
    ) -> DurableChatExecutionOutcome:
        """Execute one command without owning receipt state transitions."""
        ...


__all__ = [
    "DurableChatCommandHandler",
    "DurableChatExecutionOutcome",
    "DurableChatExecutionResult",
    "DurableChatExecutionStatus",
    "DurableChatFailedError",
    "DurableChatHeartbeat",
    "DurableChatRecoveryRequiredError",
    "DurableChatRetryableError",
]
