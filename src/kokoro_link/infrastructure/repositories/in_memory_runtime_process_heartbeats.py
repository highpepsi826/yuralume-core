"""In-memory twin for the fleet heartbeat repository."""

from __future__ import annotations

from datetime import datetime

from kokoro_link.contracts.clock import ensure_utc
from kokoro_link.contracts.runtime_process_heartbeats import (
    RuntimeProcessHeartbeat,
    RuntimeProcessHeartbeatRepositoryPort,
)


class InMemoryRuntimeProcessHeartbeatRepository(RuntimeProcessHeartbeatRepositoryPort):
    def __init__(self) -> None:
        self._rows: dict[str, RuntimeProcessHeartbeat] = {}

    async def upsert(self, heartbeat: RuntimeProcessHeartbeat) -> None:
        self._rows[heartbeat.instance_id] = heartbeat

    async def get(self, instance_id: str) -> RuntimeProcessHeartbeat | None:
        return self._rows.get(instance_id)

    async def list_all(self) -> list[RuntimeProcessHeartbeat]:
        return sorted(
            self._rows.values(),
            key=lambda row: (row.process_role, row.last_seen_at, row.instance_id),
        )

    async def prune(self, *, before: datetime) -> int:
        cutoff = ensure_utc(before)
        stale = [
            key for key, row in self._rows.items()
            if row.last_seen_at < cutoff
        ]
        for key in stale:
            del self._rows[key]
        return len(stale)
