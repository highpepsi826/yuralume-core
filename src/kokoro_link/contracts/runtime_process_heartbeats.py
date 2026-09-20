"""Durable, redacted process-heartbeat contract for fleet diagnostics.

The row is an observation, not an ownership or health verdict.  Keep this
contract deliberately small: process identity, build identity, liveness flags,
and allow-listed aggregate counters only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable

from kokoro_link.contracts.clock import ensure_utc

PROCESS_ROLES = frozenset({"api", "coordinator", "worker", "connector"})
HEALTH_STATES = frozenset({"starting", "healthy", "degraded", "stopping"})

# These are intentionally aggregate and non-sensitive.  New keys require a
# contract change so a future publisher cannot accidentally export payloads.
HEARTBEAT_DETAIL_KEYS = frozenset({
    "active_jobs",
    "completed_jobs",
    "connector_accounts_enabled",
    "failed_jobs",
    "outbound_deliveries_pending",
    "queue_depth",
    "realtime_queue_depth",
})
_MAX_DETAILS = 32
_MAX_DETAIL_VALUE_CHARS = 256


def _clean_details(details: Mapping[str, Any] | None) -> dict[str, int | float | str | bool | None]:
    if not details:
        return {}
    if len(details) > _MAX_DETAILS:
        raise ValueError("heartbeat details exceed the maximum key count")
    cleaned: dict[str, int | float | str | bool | None] = {}
    for key, value in details.items():
        if key not in HEARTBEAT_DETAIL_KEYS:
            raise ValueError(f"unsupported heartbeat detail key: {key!r}")
        if not isinstance(value, (int, float, str, bool)) and value is not None:
            raise ValueError(f"heartbeat detail {key!r} is not scalar")
        if isinstance(value, str) and len(value) > _MAX_DETAIL_VALUE_CHARS:
            raise ValueError(f"heartbeat detail {key!r} exceeds 256 characters")
        cleaned[key] = value
    return cleaned


@dataclass(frozen=True, slots=True)
class RuntimeProcessHeartbeat:
    instance_id: str
    process_role: str
    service_name: str
    build_commit_sha: str
    build_tag: str
    started_at: datetime
    last_seen_at: datetime
    health_state: str
    durable_acceptance_enabled: bool = False
    durable_worker_enabled: bool = False
    durable_worker_alive: bool = False
    background_coordinator_alive: bool = False
    connector_runtime_state: str = ""
    details: Mapping[str, int | float | str | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.instance_id.strip():
            raise ValueError("heartbeat instance_id must be non-empty")
        if self.process_role not in PROCESS_ROLES:
            raise ValueError(f"invalid heartbeat process_role: {self.process_role!r}")
        if self.health_state not in HEALTH_STATES:
            raise ValueError(f"invalid heartbeat health_state: {self.health_state!r}")
        if len(self.instance_id) > 128 or len(self.service_name) > 128:
            raise ValueError("heartbeat identity exceeds 128 characters")
        if len(self.build_commit_sha) > 128 or len(self.build_tag) > 128:
            raise ValueError("heartbeat build identity exceeds 128 characters")
        if len(self.connector_runtime_state) > 32:
            raise ValueError("heartbeat connector_runtime_state exceeds 32 characters")
        object.__setattr__(self, "started_at", ensure_utc(self.started_at))
        object.__setattr__(self, "last_seen_at", ensure_utc(self.last_seen_at))
        object.__setattr__(self, "details", _clean_details(self.details))

    @property
    def details_json(self) -> str:
        return json.dumps(dict(self.details), ensure_ascii=False, separators=(",", ":"))


@runtime_checkable
class RuntimeProcessHeartbeatRepositoryPort(Protocol):
    async def upsert(self, heartbeat: RuntimeProcessHeartbeat) -> None: ...

    async def get(self, instance_id: str) -> RuntimeProcessHeartbeat | None: ...

    async def list_all(self) -> list[RuntimeProcessHeartbeat]: ...

    async def prune(self, *, before: datetime) -> int: ...
