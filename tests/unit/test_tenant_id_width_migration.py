"""Schema contract for the hosted tenant-id width migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "v1w2x3y40001_tenant_id_width.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tenant_width", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def alter_column(self, table: str, column: str, **kwargs: Any) -> None:
        self.calls.append((table, column, kwargs))


def test_revision_chains_to_current_durable_chat_head() -> None:
    migration = _load()
    assert migration.revision == "v1w2x3y40001"
    assert migration.down_revision == "u9e7b2a11059"


def test_upgrade_widens_every_tenant_storage_column(monkeypatch) -> None:  # noqa: ANN001
    migration = _load()
    recorder = _RecordingOp()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert [table for table, _column, _kwargs in recorder.calls] == [
        "background_jobs",
        "realtime_events",
        "external_chat_turn_receipts",
        "external_proactive_events",
    ]
    assert all(call[2]["type_"].length == 128 for call in recorder.calls)


def test_models_use_authoritative_tenant_width() -> None:
    from kokoro_link.infrastructure.persistence.models import (
        BackgroundJobRow,
        ExternalChatTurnReceiptRow,
        ExternalProactiveEventRow,
        RealtimeEventRow,
    )

    for model in (
        BackgroundJobRow,
        RealtimeEventRow,
        ExternalChatTurnReceiptRow,
        ExternalProactiveEventRow,
    ):
        assert model.__table__.c.tenant_id.type.length == 128
