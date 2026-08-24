"""In-memory outbound delivery ledger used by tests and no-DB runs."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from kokoro_link.contracts.clock import ensure_utc
from kokoro_link.contracts.outbound_deliveries import (
    OutboundDelivery,
    OutboundDeliveryDraft,
    OutboundDeliveryRepositoryPort,
    OutboundDeliveryState,
    delivery_from_values,
)


@dataclass(slots=True)
class _Record:
    id: str
    platform: str
    account_id: str
    chat_ref: str
    batch_id: str | None
    sequence_no: int
    payload_json: str
    state: OutboundDeliveryState
    attempt_count: int
    next_attempt_at: datetime
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None
    lease_owner: str | None = None
    lease_until: datetime | None = None


class InMemoryOutboundDeliveryRepository(OutboundDeliveryRepositoryPort):
    def __init__(self) -> None:
        self._records: dict[str, _Record] = {}
        self._lock = asyncio.Lock()

    async def create_pending_batch(
        self, drafts: Sequence[OutboundDeliveryDraft],
    ) -> list[OutboundDelivery]:
        if not drafts:
            return []
        async with self._lock:
            ids = [draft.id for draft in drafts]
            if len(ids) != len(set(ids)):
                raise ValueError("outbound delivery batch contains duplicate ids")
            for draft in drafts:
                existing = self._records.get(draft.id)
                if existing is not None and (
                    existing.payload_json != draft.payload_json
                    or existing.batch_id != draft.batch_id
                    or existing.sequence_no != draft.sequence_no
                ):
                    raise ValueError("outbound delivery id payload conflict")
            created: list[_Record] = []
            for draft in drafts:
                existing = self._records.get(draft.id)
                if existing is not None:
                    created.append(existing)
                    continue
                when = ensure_utc(draft.now)
                record = _Record(
                    id=draft.id,
                    platform=draft.platform,
                    account_id=draft.account_id,
                    chat_ref=draft.chat_ref,
                    batch_id=draft.batch_id,
                    sequence_no=draft.sequence_no,
                    payload_json=draft.payload_json,
                    state=OutboundDeliveryState.PENDING,
                    attempt_count=0,
                    next_attempt_at=when,
                    last_error=None,
                    created_at=when,
                    updated_at=when,
                )
                self._records[draft.id] = record
                created.append(record)
            return [_view(record) for record in created]

    async def create_pending(self, *, delivery_id: str, platform: str,
                             account_id: str, chat_ref: str,
                             payload_json: str, now: datetime) -> OutboundDelivery:
        saved = await self.create_pending_batch((
            OutboundDeliveryDraft(
                id=delivery_id,
                platform=platform,
                account_id=account_id,
                chat_ref=chat_ref,
                payload_json=payload_json,
                now=now,
            ),
        ))
        return saved[0]

    async def claim(self, delivery_id: str, *, owner_id: str, now: datetime,
                    lease_seconds: float) -> bool:
        when = ensure_utc(now)
        async with self._lock:
            record = self._records.get(delivery_id)
            if record is None or record.state is not OutboundDeliveryState.PENDING:
                return False
            if record.next_attempt_at > when:
                return False
            if (record.lease_owner is not None and record.lease_owner != owner_id
                    and record.lease_until is not None and record.lease_until > when):
                return False
            if record.batch_id is not None and any(
                other.batch_id == record.batch_id
                and other.sequence_no < record.sequence_no
                and other.state is not OutboundDeliveryState.DELIVERED
                for other in self._records.values()
            ):
                return False
            record.lease_owner = owner_id
            record.lease_until = when + timedelta(seconds=max(1.0, lease_seconds))
            record.attempt_count += 1
            record.updated_at = when
            return True

    async def mark_delivered(self, delivery_id: str, *, owner_id: str,
                             now: datetime) -> bool:
        return await self._transition(
            delivery_id, owner_id=owner_id, now=now,
            state=OutboundDeliveryState.DELIVERED, delivered_at=ensure_utc(now),
        )

    async def mark_retryable(self, delivery_id: str, *, owner_id: str,
                             error: str, next_attempt_at: datetime,
                             now: datetime) -> bool:
        return await self._transition(
            delivery_id, owner_id=owner_id, now=now,
            state=OutboundDeliveryState.PENDING,
            last_error=error[:1000], next_attempt_at=ensure_utc(next_attempt_at),
        )

    async def mark_terminal(self, delivery_id: str, *, owner_id: str,
                            reason: str, now: datetime) -> bool:
        return await self._transition(
            delivery_id, owner_id=owner_id, now=now,
            state=OutboundDeliveryState.TERMINAL, last_error=reason[:1000],
        )

    async def list_pending_due(self, *, now: datetime, limit: int = 100) -> list[OutboundDelivery]:
        when = ensure_utc(now)
        async with self._lock:
            rows = [
                _view(record) for record in self._records.values()
                if record.state is OutboundDeliveryState.PENDING
                and record.next_attempt_at <= when
                and (
                    record.lease_until is None
                    or record.lease_until <= when
                )
                and (
                    record.batch_id is None
                    or not any(
                        other.batch_id == record.batch_id
                        and other.sequence_no < record.sequence_no
                        and other.state is not OutboundDeliveryState.DELIVERED
                        for other in self._records.values()
                    )
                )
            ]
        rows.sort(key=lambda row: (row.next_attempt_at, row.created_at, row.id))
        return rows[:max(0, limit)]

    async def _transition(self, delivery_id: str, *, owner_id: str,
                          now: datetime, state: OutboundDeliveryState,
                          last_error: str | None = None,
                          next_attempt_at: datetime | None = None,
                          delivered_at: datetime | None = None) -> bool:
        when = ensure_utc(now)
        async with self._lock:
            record = self._records.get(delivery_id)
            if (record is None or record.state is not OutboundDeliveryState.PENDING
                    or record.lease_owner != owner_id):
                return False
            record.state = state
            record.last_error = last_error
            if next_attempt_at is not None:
                record.next_attempt_at = next_attempt_at
            record.delivered_at = delivered_at
            record.lease_owner = None
            record.lease_until = None
            record.updated_at = when
            if state is OutboundDeliveryState.TERMINAL and record.batch_id is not None:
                for other in self._records.values():
                    if (
                        other.batch_id == record.batch_id
                        and other.sequence_no > record.sequence_no
                        and other.state is OutboundDeliveryState.PENDING
                    ):
                        other.state = OutboundDeliveryState.TERMINAL
                        other.last_error = last_error
                        other.lease_owner = None
                        other.lease_until = None
                        other.updated_at = when
            return True


def _view(record: _Record) -> OutboundDelivery:
    return delivery_from_values(
        id=record.id, platform=record.platform, account_id=record.account_id,
        chat_ref=record.chat_ref, batch_id=record.batch_id,
        sequence_no=record.sequence_no, payload_json=record.payload_json,
        state=record.state.value, attempt_count=record.attempt_count,
        next_attempt_at=record.next_attempt_at, last_error=record.last_error,
        created_at=record.created_at, updated_at=record.updated_at,
        delivered_at=record.delivered_at,
    )
