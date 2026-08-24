"""Retry worker for durable outbound channel bubbles."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from kokoro_link.contracts.clock import ClockPort, ensure_utc
from kokoro_link.contracts.messaging import (
    ChannelAdapterPort,
    MessagingAccountRepositoryPort,
)
from kokoro_link.contracts.outbound_deliveries import (
    OutboundDelivery,
    OutboundDeliveryRepositoryPort,
    OutboundDeliveryState,
    deserialize_outbound_message,
)
from kokoro_link.domain.value_objects.platform import Platform

_LOGGER = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 5.0
_DEFAULT_LEASE_SECONDS = 60.0
_DEFAULT_MAX_ATTEMPTS = 8
_DEFAULT_BATCH_LIMIT = 100
_BACKOFF_SECONDS = (5.0, 30.0, 300.0, 900.0, 1800.0)


class OutboundDeliveryRetryWorker:
    """Re-send stored payloads without re-running ``ChatService``."""

    def __init__(
        self,
        *,
        ledger: OutboundDeliveryRepositoryPort,
        account_repository: MessagingAccountRepositoryPort,
        adapters: dict[Platform, ChannelAdapterPort],
        clock: ClockPort | None = None,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        lease_seconds: float = _DEFAULT_LEASE_SECONDS,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        batch_limit: int = _DEFAULT_BATCH_LIMIT,
    ) -> None:
        self._ledger = ledger
        self._accounts = account_repository
        self._adapters = {platform.value: adapter for platform, adapter in adapters.items()}
        self._clock = clock
        self._interval_seconds = max(0.5, interval_seconds)
        self._lease_seconds = max(1.0, lease_seconds)
        self._max_attempts = max(1, max_attempts)
        self._batch_limit = max(1, batch_limit)
        self._owner_id = f"outbound-retry-{uuid4().hex}"
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(
            self._run(), name="outbound-delivery-retry-worker",
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        task = self._task
        self._task = None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def tick(self, *, now: datetime | None = None) -> None:
        when = self._resolve_now(now)
        try:
            due = await self._ledger.list_pending_due(
                now=when, limit=self._batch_limit,
            )
        except Exception:
            _LOGGER.exception("outbound delivery retry: listing pending rows failed")
            return
        for delivery in due:
            await self._retry_one(delivery, now=when)

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("outbound delivery retry sweep failed")
            await asyncio.sleep(self._interval_seconds)

    async def _retry_one(self, delivery: OutboundDelivery, *, now: datetime) -> None:
        if not await self._ledger.claim(
            delivery.id,
            owner_id=self._owner_id,
            now=now,
            lease_seconds=self._lease_seconds,
        ):
            return
        # Claim first even when the row was left at the attempt ceiling. The
        # transition methods are lease-guarded, so marking terminal without a
        # claim would silently leave this row pending forever.
        if delivery.attempt_count >= self._max_attempts:
            await self._mark_terminal(delivery.id, "max_attempts_exceeded", now=now)
            return

        account = await self._accounts.get(delivery.account_id)
        if account is None or not account.enabled:
            await self._mark_terminal(
                delivery.id, "account_missing_or_disabled", now=now,
            )
            return
        adapter = self._adapters.get(delivery.platform)
        if adapter is None or account.platform.value != delivery.platform:
            await self._mark_terminal(delivery.id, "adapter_unavailable", now=now)
            return
        try:
            message = deserialize_outbound_message(
                delivery.payload_json, credentials=account.credentials,
            )
        except Exception:
            _LOGGER.exception(
                "outbound delivery retry: malformed payload id=%s", delivery.id,
            )
            await self._mark_terminal(delivery.id, "malformed_payload", now=now)
            return
        try:
            await adapter.send(message)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:240]}"
            if delivery.attempt_count + 1 >= self._max_attempts:
                await self._mark_terminal(
                    delivery.id, "max_attempts_exceeded:" + type(exc).__name__,
                    now=now,
                )
                return
            delay = _BACKOFF_SECONDS[
                min(delivery.attempt_count, len(_BACKOFF_SECONDS) - 1)
            ]
            try:
                await self._ledger.mark_retryable(
                    delivery.id,
                    owner_id=self._owner_id,
                    error=error,
                    next_attempt_at=now + timedelta(seconds=delay),
                    now=now,
                )
            except Exception:
                _LOGGER.exception(
                    "outbound delivery retry: failed to keep row pending id=%s",
                    delivery.id,
                )
            _LOGGER.warning(
                "outbound delivery retry failed id=%s error_type=%s; next_attempt_in=%ss",
                delivery.id, type(exc).__name__, int(delay),
            )
            return
        try:
            await self._ledger.mark_delivered(
                delivery.id, owner_id=self._owner_id, now=now,
            )
        except Exception:
            _LOGGER.exception(
                "outbound delivery retry: mark delivered failed id=%s",
                delivery.id,
            )

    async def _mark_terminal(self, delivery_id: str, reason: str, *, now: datetime) -> None:
        try:
            await self._ledger.mark_terminal(
                delivery_id, owner_id=self._owner_id, reason=reason, now=now,
            )
        except Exception:
            _LOGGER.exception(
                "outbound delivery retry: mark terminal failed id=%s", delivery_id,
            )

    def _resolve_now(self, now: datetime | None) -> datetime:
        if now is not None:
            return ensure_utc(now)
        if self._clock is not None:
            return ensure_utc(self._clock.now())
        return datetime.now(timezone.utc)
