from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
import importlib.util

import pytest

from kokoro_link.contracts.runtime_process_heartbeats import (
    RuntimeProcessHeartbeat,
)
from kokoro_link.infrastructure.repositories.in_memory_runtime_process_heartbeats import (
    InMemoryRuntimeProcessHeartbeatRepository,
)


UTC = timezone.utc
BASE = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
MIGRATION_PATH = (
    Path(__file__).parents[1]
    / ".."
    / "alembic"
    / "versions"
    / "w2k7m9n10060_runtime_process_heartbeats.py"
).resolve()


def _heartbeat(
    *,
    instance_id: str = "api-1",
    process_role: str = "api",
    seen: datetime = BASE,
) -> RuntimeProcessHeartbeat:
    return RuntimeProcessHeartbeat(
        instance_id=instance_id,
        process_role=process_role,
        service_name="app",
        build_commit_sha="abc123",
        build_tag="2026-09-20",
        started_at=BASE - timedelta(minutes=5),
        last_seen_at=seen,
        health_state="healthy",
        durable_acceptance_enabled=True,
        details={"queue_depth": 2, "active_jobs": 1},
    )


def _load_migration():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("heartbeat_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contract_rejects_unknown_detail_and_invalid_role() -> None:
    with pytest.raises(ValueError, match="unsupported heartbeat detail"):
        replace(_heartbeat(), details={"secret": "no"})
    with pytest.raises(ValueError, match="invalid heartbeat process_role"):
        replace(_heartbeat(), process_role="scheduler")


@pytest.mark.asyncio
async def test_in_memory_upsert_list_and_retention() -> None:
    repo = InMemoryRuntimeProcessHeartbeatRepository()
    await repo.upsert(_heartbeat())
    await repo.upsert(_heartbeat(seen=BASE + timedelta(minutes=1)))
    await repo.upsert(_heartbeat(instance_id="worker-1", process_role="worker"))

    rows = await repo.list_all()
    assert [row.instance_id for row in rows] == ["api-1", "worker-1"]
    assert rows[0].last_seen_at == BASE + timedelta(minutes=1)
    assert await repo.prune(before=BASE + timedelta(seconds=30)) == 1
    assert await repo.prune(before=BASE + timedelta(minutes=2)) == 1
    assert await repo.list_all() == []


class _RecordingOp:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.dropped: list[str] = []
        self.indexes: list[str] = []

    def create_table(self, name: str, *args: object, **kwargs: object) -> None:
        self.created.append(name)

    def create_index(self, name: str, *args: object, **kwargs: object) -> None:
        self.indexes.append(name)

    def drop_index(self, name: str, *args: object, **kwargs: object) -> None:
        self.dropped.append(name)

    def drop_table(self, name: str) -> None:
        self.dropped.append(name)


def test_migration_is_additive_and_reversible(monkeypatch: pytest.MonkeyPatch) -> None:
    migration = _load_migration()
    assert migration.revision == "w2k7m9n10060"
    assert migration.down_revision == "v1w2x3y40001"
    recorder = _RecordingOp()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()
    assert recorder.created == ["runtime_process_heartbeats"]
    assert recorder.indexes == [
        "ix_runtime_process_heartbeats_role_seen",
        "ix_runtime_process_heartbeats_seen",
    ]

    migration.downgrade()
    assert recorder.dropped == [
        "ix_runtime_process_heartbeats_seen",
        "ix_runtime_process_heartbeats_role_seen",
        "runtime_process_heartbeats",
    ]


def test_model_keeps_role_and_health_values_bounded() -> None:
    from kokoro_link.infrastructure.persistence.models import RuntimeProcessHeartbeatRow

    checks = {constraint.name for constraint in RuntimeProcessHeartbeatRow.__table__.constraints}
    assert checks == {
        "ck_runtime_process_heartbeats_role",
        "ck_runtime_process_heartbeats_health",
        None,
    }
