"""SQLAlchemy adapter for the fleet diagnostic heartbeat rows."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from kokoro_link.contracts.clock import ensure_utc
from kokoro_link.contracts.runtime_process_heartbeats import (
    RuntimeProcessHeartbeat,
    RuntimeProcessHeartbeatRepositoryPort,
)
from kokoro_link.infrastructure.persistence.models import RuntimeProcessHeartbeatRow


class SARuntimeProcessHeartbeatRepository(RuntimeProcessHeartbeatRepositoryPort):
    def __init__(self, session_factory: sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert(self, heartbeat: RuntimeProcessHeartbeat) -> None:
        values = _values(heartbeat)
        async with self._session_factory() as session:
            row = await session.get(
                RuntimeProcessHeartbeatRow,
                heartbeat.instance_id,
                with_for_update=True,
            )
            if row is None:
                session.add(RuntimeProcessHeartbeatRow(**values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # Cold-start inserts can race on the primary key.  Retry as a
                # normal update so the publisher remains idempotent.
                async with self._session_factory() as retry:
                    row = await retry.get(
                        RuntimeProcessHeartbeatRow,
                        heartbeat.instance_id,
                        with_for_update=True,
                    )
                    if row is None:
                        raise
                    for key, value in values.items():
                        setattr(row, key, value)
                    await retry.commit()

    async def get(self, instance_id: str) -> RuntimeProcessHeartbeat | None:
        async with self._session_factory() as session:
            row = await session.get(RuntimeProcessHeartbeatRow, instance_id)
            return _to_domain(row) if row is not None else None

    async def list_all(self) -> list[RuntimeProcessHeartbeat]:
        stmt = select(RuntimeProcessHeartbeatRow).order_by(
            RuntimeProcessHeartbeatRow.process_role.asc(),
            RuntimeProcessHeartbeatRow.last_seen_at.asc(),
            RuntimeProcessHeartbeatRow.instance_id.asc(),
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(row) for row in rows]

    async def prune(self, *, before: datetime) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(RuntimeProcessHeartbeatRow).where(
                    RuntimeProcessHeartbeatRow.last_seen_at < ensure_utc(before),
                ),
            )
            await session.commit()
            return int(result.rowcount or 0)


def _values(heartbeat: RuntimeProcessHeartbeat) -> dict[str, object]:
    return {
        "instance_id": heartbeat.instance_id,
        "process_role": heartbeat.process_role,
        "service_name": heartbeat.service_name,
        "build_commit_sha": heartbeat.build_commit_sha,
        "build_tag": heartbeat.build_tag,
        "started_at": heartbeat.started_at,
        "last_seen_at": heartbeat.last_seen_at,
        "health_state": heartbeat.health_state,
        "durable_acceptance_enabled": heartbeat.durable_acceptance_enabled,
        "durable_worker_enabled": heartbeat.durable_worker_enabled,
        "durable_worker_alive": heartbeat.durable_worker_alive,
        "background_coordinator_alive": heartbeat.background_coordinator_alive,
        "connector_runtime_state": heartbeat.connector_runtime_state,
        "details_json": heartbeat.details_json,
    }


def _to_domain(row: RuntimeProcessHeartbeatRow) -> RuntimeProcessHeartbeat:
    try:
        details = json.loads(row.details_json or "{}")
    except (TypeError, ValueError):
        details = {}
    return RuntimeProcessHeartbeat(
        instance_id=row.instance_id,
        process_role=row.process_role,
        service_name=row.service_name,
        build_commit_sha=row.build_commit_sha,
        build_tag=row.build_tag,
        started_at=ensure_utc(row.started_at),
        last_seen_at=ensure_utc(row.last_seen_at),
        health_state=row.health_state,
        durable_acceptance_enabled=row.durable_acceptance_enabled,
        durable_worker_enabled=row.durable_worker_enabled,
        durable_worker_alive=row.durable_worker_alive,
        background_coordinator_alive=row.background_coordinator_alive,
        connector_runtime_state=row.connector_runtime_state,
        details=details if isinstance(details, dict) else {},
    )
