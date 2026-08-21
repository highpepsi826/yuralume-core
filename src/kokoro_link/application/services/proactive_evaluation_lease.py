"""Per-character single-flight lease for proactive evaluation.

The scheduler and the manual evaluate route can enter the same character at
the same time. A process-local lock is not enough when API workers share a
database, and reusing the studio lease owner would incorrectly allow two
same-process evaluations to renew one another. Each evaluation therefore gets
its own owner id while sharing the existing lease backend.
"""

from __future__ import annotations

from uuid import uuid4

from kokoro_link.application.services.studio_execution_lease import (
    StudioExecutionLease,
    StudioLeaseSession,
)


PROACTIVE_EVALUATION_LEASE_TTL_SECONDS = 180
"""Longer than a normal model call, while still bounding a crashed worker."""

PROACTIVE_EVALUATION_LEASE_MAX_LIFETIME_SECONDS = 900
"""A dropped task must not renew a character forever."""

_LEASE_NAME_PREFIX = "proactive:character:"


class ProactiveEvaluationLease:
    """Mint a fresh, non-waiting lease session for each character evaluation."""

    __slots__ = ("_port", "_ttl", "_interval", "_max_lifetime")

    def __init__(
        self,
        port,
        *,
        ttl_seconds: int = PROACTIVE_EVALUATION_LEASE_TTL_SECONDS,
        heartbeat_interval_seconds: float | None = None,
        max_lifetime_seconds: float | None = (
            PROACTIVE_EVALUATION_LEASE_MAX_LIFETIME_SECONDS
        ),
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ProactiveEvaluationLease.ttl_seconds must be > 0")
        self._port = port
        self._ttl = ttl_seconds
        self._interval = heartbeat_interval_seconds
        self._max_lifetime = max_lifetime_seconds

    @classmethod
    def from_studio_lease(
        cls,
        lease: StudioExecutionLease | None,
        *,
        ttl_seconds: int = PROACTIVE_EVALUATION_LEASE_TTL_SECONDS,
    ) -> "ProactiveEvaluationLease | None":
        if lease is None:
            return None
        return cls(lease.port, ttl_seconds=ttl_seconds)

    def session(self, character_id: str) -> StudioLeaseSession:
        holder = StudioExecutionLease(
            self._port,
            owner_id=f"proactive-eval-{uuid4().hex}",
            ttl_seconds=self._ttl,
            name_prefix=_LEASE_NAME_PREFIX,
        )
        return StudioLeaseSession(
            holder,
            character_id,
            heartbeat_interval_seconds=self._interval,
            max_lifetime_seconds=self._max_lifetime,
        )
