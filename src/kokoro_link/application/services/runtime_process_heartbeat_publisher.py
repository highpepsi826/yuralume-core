"""Best-effort durable liveness publisher for one process incarnation."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import socket
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from uuid import uuid4

from kokoro_link.contracts.runtime_process_heartbeats import (
    RuntimeProcessHeartbeat,
    RuntimeProcessHeartbeatRepositoryPort,
)

_LOGGER = logging.getLogger(__name__)
_DEFAULT_INTERVAL_SECONDS = 15.0

HeartbeatSnapshot = Callable[[], Mapping[str, object] | Awaitable[Mapping[str, object]]]


class RuntimeProcessHeartbeatPublisher:
    """Publish bounded process state without becoming a boot/shutdown dependency.

    A publisher owns one identity for its whole process lifetime.  Repository
    errors are logged and swallowed because diagnostics must never take the
    serving process down.
    """

    def __init__(
        self,
        *,
        repository: RuntimeProcessHeartbeatRepositoryPort | None,
        process_role: str,
        build_commit_sha: str = "",
        build_tag: str = "",
        service_name: str = "yuralume-core",
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        snapshot: HeartbeatSnapshot | None = None,
    ) -> None:
        self._repository = repository
        self._process_role = _diagnostic_role(process_role)
        self._service_name = service_name
        self._build_commit_sha = build_commit_sha
        self._build_tag = build_tag
        self._snapshot = snapshot
        self._interval_seconds = max(0.5, float(interval_seconds))
        self._instance_id = _instance_id(self._process_role)
        self._started_at = datetime.now(timezone.utc)
        self._task: asyncio.Task[None] | None = None

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._repository is None or self.running:
            return
        await self._publish("starting")
        self._task = asyncio.create_task(
            self._run(), name="runtime-process-heartbeat",
        )

    async def stop(self) -> None:
        if self._repository is None:
            return
        await self._publish("stopping")
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def publish_now(self, health_state: str = "healthy") -> None:
        """Publish one observation; useful for tests and lifecycle checkpoints."""
        await self._publish(health_state)

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval_seconds)
                await self._publish(None)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive loop guard
                _LOGGER.exception("runtime heartbeat loop failed")

    async def _publish(self, health_state: str | None) -> None:
        if self._repository is None:
            return
        try:
            values: Mapping[str, object] = {}
            if self._snapshot is not None:
                result = self._snapshot()
                values = await result if inspect.isawaitable(result) else result
            if health_state is None:
                health_state = (
                    "degraded" if values.get("degraded", False) else "healthy"
                )
            details = values.get("details", {})
            if not isinstance(details, Mapping):
                details = {}
            heartbeat = RuntimeProcessHeartbeat(
                instance_id=self._instance_id,
                process_role=self._process_role,
                service_name=self._service_name,
                build_commit_sha=self._build_commit_sha,
                build_tag=self._build_tag,
                started_at=self._started_at,
                last_seen_at=datetime.now(timezone.utc),
                health_state=health_state,
                durable_acceptance_enabled=bool(
                    values.get("durable_acceptance_enabled", False),
                ),
                durable_worker_enabled=bool(
                    values.get("durable_worker_enabled", False),
                ),
                durable_worker_alive=bool(
                    values.get("durable_worker_alive", False),
                ),
                background_coordinator_alive=bool(
                    values.get("background_coordinator_alive", False),
                ),
                connector_runtime_state=str(
                    values.get("connector_runtime_state", ""),
                )[:32],
                details=details,
            )
            await self._repository.upsert(heartbeat)
        except Exception:
            _LOGGER.exception("runtime heartbeat publish failed; continuing")


def _diagnostic_role(role: str) -> str:
    # D1 intentionally constrains persisted roles to the four dedicated roles.
    return {"all": "api", "background": "coordinator"}.get(role, role)


def _instance_id(role: str) -> str:
    host = socket.gethostname().strip() or "host"
    pid = os.getpid()
    return f"{role}-{host}-{pid}-{uuid4().hex[:12]}"[:128]
