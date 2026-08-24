"""SQLAlchemy adapter for the outbound channel delivery ledger."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, sessionmaker

from kokoro_link.contracts.clock import ensure_utc
from kokoro_link.contracts.outbound_deliveries import (
    OutboundDelivery,
    OutboundDeliveryDraft,
    OutboundDeliveryRepositoryPort,
    OutboundDeliveryState,
    delivery_from_values,
)
from kokoro_link.infrastructure.persistence.models import OutboundMessageDeliveryRow

_Row = OutboundMessageDeliveryRow
_PENDING = OutboundDeliveryState.PENDING.value


class SAOutboundDeliveryRepository(OutboundDeliveryRepositoryPort):
    def __init__(self, session_factory: sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_pending_batch(
        self, drafts: Sequence[OutboundDeliveryDraft],
    ) -> list[OutboundDelivery]:
        if not drafts:
            return []
        rows = [
            _Row(
                id=draft.id,
                platform=draft.platform,
                account_id=draft.account_id,
                chat_ref=draft.chat_ref,
                batch_id=draft.batch_id,
                sequence_no=draft.sequence_no,
                payload_json=draft.payload_json,
                state=_PENDING,
                attempt_count=0,
                next_attempt_at=ensure_utc(draft.now),
                last_error=None,
                created_at=ensure_utc(draft.now),
                updated_at=ensure_utc(draft.now),
            )
            for draft in drafts
        ]
        # Build DTOs before commit. This remains safe even if a deployment
        # supplies a session factory with expire_on_commit=True: reading an
        # expired ORM attribute outside SQLAlchemy's greenlet would otherwise
        # raise MissingGreenlet.
        saved = [_to_delivery(row) for row in rows]
        async with self._session_factory() as session:
            session.add_all(rows)
            await session.commit()
        return saved

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
        lease_until = when + timedelta(seconds=max(1.0, lease_seconds))
        predecessor = aliased(_Row)
        unfulfilled_predecessor = select(predecessor.id).where(
            predecessor.batch_id == _Row.batch_id,
            predecessor.sequence_no < _Row.sequence_no,
            predecessor.state != OutboundDeliveryState.DELIVERED.value,
        ).exists()
        async with self._session_factory() as session:
            result = await session.execute(
                update(_Row)
                .where(
                    _Row.id == delivery_id,
                    _Row.state == _PENDING,
                    _Row.next_attempt_at <= when,
                    or_(_Row.lease_until.is_(None), _Row.lease_until <= when),
                    or_(_Row.batch_id.is_(None), ~unfulfilled_predecessor),
                )
                .values(
                    lease_owner=owner_id,
                    lease_until=lease_until,
                    attempt_count=_Row.attempt_count + 1,
                    updated_at=when,
                ),
            )
            await session.commit()
            return result.rowcount == 1

    async def mark_delivered(self, delivery_id: str, *, owner_id: str,
                             now: datetime) -> bool:
        when = ensure_utc(now)
        return await self._transition(
            delivery_id, owner_id=owner_id, now=when,
            values={
                "state": OutboundDeliveryState.DELIVERED.value,
                "delivered_at": when,
                "lease_owner": None,
                "lease_until": None,
            },
        )

    async def mark_retryable(self, delivery_id: str, *, owner_id: str,
                             error: str, next_attempt_at: datetime,
                             now: datetime) -> bool:
        return await self._transition(
            delivery_id, owner_id=owner_id, now=ensure_utc(now),
            values={
                "state": _PENDING,
                "last_error": error[:1000],
                "next_attempt_at": ensure_utc(next_attempt_at),
                "lease_owner": None,
                "lease_until": None,
            },
        )

    async def mark_terminal(self, delivery_id: str, *, owner_id: str,
                            reason: str, now: datetime) -> bool:
        when = ensure_utc(now)
        async with self._session_factory() as session:
            current = (
                await session.execute(
                    select(_Row.batch_id, _Row.sequence_no)
                    .where(
                        _Row.id == delivery_id,
                        _Row.state == _PENDING,
                        _Row.lease_owner == owner_id,
                    )
                )
            ).one_or_none()
            if current is None:
                return False
            batch_id, sequence_no = current
            if batch_id is None:
                predicate = _Row.id == delivery_id
            else:
                predicate = and_(
                    _Row.batch_id == batch_id,
                    _Row.sequence_no >= sequence_no,
                    _Row.state == _PENDING,
                )
            result = await session.execute(
                update(_Row)
                .where(predicate)
                .values(
                    state=OutboundDeliveryState.TERMINAL.value,
                    last_error=reason[:1000],
                    lease_owner=None,
                    lease_until=None,
                    updated_at=when,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def list_pending_due(self, *, now: datetime, limit: int = 100) -> list[OutboundDelivery]:
        when = ensure_utc(now)
        predecessor = aliased(_Row)
        unfulfilled_predecessor = select(predecessor.id).where(
            predecessor.batch_id == _Row.batch_id,
            predecessor.sequence_no < _Row.sequence_no,
            predecessor.state != OutboundDeliveryState.DELIVERED.value,
        ).exists()
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(_Row)
                    .where(
                        _Row.state == _PENDING,
                        _Row.next_attempt_at <= when,
                        or_(_Row.lease_until.is_(None), _Row.lease_until <= when),
                        or_(_Row.batch_id.is_(None), ~unfulfilled_predecessor),
                    )
                    .order_by(_Row.next_attempt_at, _Row.created_at, _Row.id)
                    .limit(max(0, limit)),
                )
            ).scalars().all()
            return [_to_delivery(row) for row in rows]

    async def _transition(self, delivery_id: str, *, owner_id: str,
                          now: datetime, values: dict[str, object]) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                update(_Row)
                .where(
                    _Row.id == delivery_id,
                    _Row.state == _PENDING,
                    _Row.lease_owner == owner_id,
                )
                .values(updated_at=ensure_utc(now), **values),
            )
            await session.commit()
            return result.rowcount == 1


def _to_delivery(row: OutboundMessageDeliveryRow) -> OutboundDelivery:
    return delivery_from_values(
        id=row.id, platform=row.platform, account_id=row.account_id,
        chat_ref=row.chat_ref, batch_id=row.batch_id,
        sequence_no=row.sequence_no, payload_json=row.payload_json,
        state=row.state, attempt_count=row.attempt_count,
        next_attempt_at=row.next_attempt_at, last_error=row.last_error,
        created_at=row.created_at, updated_at=row.updated_at,
        delivered_at=row.delivered_at,
    )
