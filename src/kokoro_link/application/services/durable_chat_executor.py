"""One-shot executor for durable foreground chat command receipts."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime

from kokoro_link.contracts.durable_chat_commands import (
    ChatTurnPhase,
    ChatTurnCommandState,
    DurableChatCommandRepositoryPort,
)
from kokoro_link.contracts.durable_chat_execution import (
    DurableChatCommandHandler,
    DurableChatExecutionOutcome,
    DurableChatExecutionResult,
    DurableChatExecutionStatus,
    DurableChatFailedError,
    DurableChatRecoveryRequiredError,
    DurableChatRetryableError,
)

_LOGGER = logging.getLogger(__name__)


class DurableChatCommandExecutor:
    """Claim and execute at most one foreground command per pass.

    The executor never guesses whether an unclassified exception is safe to
    replay.  It fences such failures into ``recovery_required`` so a later
    reconciliation action can inspect provider/billing evidence first.
    """

    def __init__(
        self,
        *,
        repository: DurableChatCommandRepositoryPort,
        handler: DurableChatCommandHandler,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self._repository = repository
        self._handler = handler
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds

    async def run_once(
        self,
        *,
        now: datetime | None = None,
    ) -> DurableChatExecutionResult:
        claimed = await self._repository.claim_next(
            self._worker_id,
            lease_seconds=self._lease_seconds,
            now=now,
        )
        if claimed is None:
            return DurableChatExecutionResult(DurableChatExecutionStatus.IDLE)

        command = claimed.command
        transition_now = now
        recovery_state = command.state in {
            ChatTurnCommandState.GENERATED,
            ChatTurnCommandState.COMMITTED,
        }
        if not recovery_state:
            if not await self._repository.mark_processing(
                turn_id=command.turn_id,
                worker_id=self._worker_id,
                lease_generation=command.lease_generation,
                phase=ChatTurnPhase.PREPARING,
                now=transition_now,
            ):
                return self._result(command, DurableChatExecutionStatus.FENCED)
            command = replace(
                command,
                state=ChatTurnCommandState.PROCESSING,
                phase=ChatTurnPhase.PREPARING,
            )

        async def heartbeat(
            phase: ChatTurnPhase,
            *,
            at: datetime | None = None,
        ) -> bool:
            result = await self._repository.heartbeat(
                turn_id=command.turn_id,
                worker_id=self._worker_id,
                lease_generation=command.lease_generation,
                lease_seconds=self._lease_seconds,
                phase=phase,
                now=at if at is not None else transition_now,
            )
            return result

        try:
            outcome = await self._handler(command, heartbeat=heartbeat)
            if not isinstance(outcome, DurableChatExecutionOutcome):
                raise TypeError(
                    "durable chat handler must return "
                    "DurableChatExecutionOutcome",
                )
            if not outcome.generated_already_persisted:
                if (
                    outcome.generated_snapshot_json is None
                    or outcome.generated_snapshot_hash is None
                ):
                    raise TypeError(
                        "durable chat handler must return a generated snapshot",
                    )
                if not await self._repository.mark_generated(
                    turn_id=command.turn_id,
                    worker_id=self._worker_id,
                    lease_generation=command.lease_generation,
                    snapshot_json=outcome.generated_snapshot_json,
                    snapshot_hash=outcome.generated_snapshot_hash,
                    now=transition_now,
                ):
                    return self._result(command, DurableChatExecutionStatus.FENCED)
            if not outcome.committed_already_persisted:
                if not await self._repository.mark_committed(
                    turn_id=command.turn_id,
                    worker_id=self._worker_id,
                    lease_generation=command.lease_generation,
                    result_message_id=outcome.result_message_id,
                    now=transition_now,
                ):
                    return self._result(command, DurableChatExecutionStatus.FENCED)
        except DurableChatRetryableError as exc:
            changed = await self._repository.mark_failed(
                turn_id=command.turn_id,
                worker_id=self._worker_id,
                lease_generation=command.lease_generation,
                failure_code=exc.failure_code,
                failure_message=exc.failure_message,
                retryable=True,
                retry_after_seconds=exc.retry_after_seconds,
                now=transition_now,
            )
            return self._result(
                command,
                DurableChatExecutionStatus.RETRY_WAIT
                if changed else DurableChatExecutionStatus.FENCED,
            )
        except DurableChatFailedError as exc:
            changed = await self._repository.mark_failed(
                turn_id=command.turn_id,
                worker_id=self._worker_id,
                lease_generation=command.lease_generation,
                failure_code=exc.failure_code,
                failure_message=exc.failure_message,
                retryable=False,
                now=transition_now,
            )
            return self._result(
                command,
                DurableChatExecutionStatus.FAILED
                if changed else DurableChatExecutionStatus.FENCED,
            )
        except DurableChatRecoveryRequiredError as exc:
            changed = await self._repository.mark_recovery_required(
                turn_id=command.turn_id,
                worker_id=self._worker_id,
                lease_generation=command.lease_generation,
                failure_code=exc.failure_code,
                failure_message=exc.failure_message,
                now=transition_now,
            )
            return self._result(
                command,
                DurableChatExecutionStatus.RECOVERY_REQUIRED
                if changed else DurableChatExecutionStatus.FENCED,
            )
        except Exception:  # noqa: BLE001 - unknown effect must not replay
            _LOGGER.exception(
                "durable chat handler failed; fencing for reconciliation "
                "turn=%s worker=%s",
                command.turn_id,
                self._worker_id,
            )
            changed = await self._repository.mark_recovery_required(
                turn_id=command.turn_id,
                worker_id=self._worker_id,
                lease_generation=command.lease_generation,
                failure_code="executor_unhandled_error",
                failure_message=(
                    "Worker failed after execution began; provider and billing "
                    "outcome requires reconciliation"
                ),
                now=transition_now,
            )
            return self._result(
                command,
                DurableChatExecutionStatus.RECOVERY_REQUIRED
                if changed else DurableChatExecutionStatus.FENCED,
            )

        changed = await self._repository.mark_completed(
            turn_id=command.turn_id,
            worker_id=self._worker_id,
            lease_generation=command.lease_generation,
            result_message_id=outcome.result_message_id,
            now=transition_now,
        )
        return self._result(
            command,
            DurableChatExecutionStatus.COMPLETED
            if changed else DurableChatExecutionStatus.FENCED,
        )

    @staticmethod
    def _result(command, status: DurableChatExecutionStatus):  # noqa: ANN001
        return DurableChatExecutionResult(
            status=status,
            turn_id=command.turn_id,
            attempt_count=command.attempt_count,
        )


class DurableChatWorker:
    """Long-lived process-role loop around :class:`DurableChatCommandExecutor`.

    The loop is deliberately thin: claim, fencing, error classification and
    terminal writes remain in the executor so a test can drive ``run_once``
    without starting an asyncio task.
    """

    def __init__(
        self,
        *,
        executor: DurableChatCommandExecutor,
        loop_seconds: float = 2.0,
    ) -> None:
        if loop_seconds <= 0:
            raise ValueError("loop_seconds must be positive")
        self._executor = executor
        self._loop_seconds = loop_seconds
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(),
            name="durable-chat-worker",
        )

    async def stop(self) -> None:
        if self._task is None or self._stop_event is None:
            return
        self._stop_event.set()
        task = self._task
        try:
            await asyncio.wait_for(task, timeout=30.0)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "durable chat worker did not stop within 30s; cancelling "
                "the loop and leaving lease expiry as the recovery backstop",
            )
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            self._task = None
            self._stop_event = None

    @property
    def started(self) -> bool:
        return self._task is not None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def run_once(
        self,
        *,
        now: datetime | None = None,
    ) -> DurableChatExecutionResult:
        return await self._executor.run_once(now=now)

    async def _run(self) -> None:
        assert self._stop_event is not None
        _LOGGER.info("durable chat worker started")
        try:
            while not self._stop_event.is_set():
                try:
                    await self._executor.run_once()
                except Exception:  # noqa: BLE001 - keep claim loop alive
                    _LOGGER.exception("durable chat worker pass failed")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._loop_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        _LOGGER.info("durable chat worker stopped")


__all__ = ["DurableChatCommandExecutor", "DurableChatWorker"]
