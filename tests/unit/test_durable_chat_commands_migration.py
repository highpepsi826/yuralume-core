"""Smoke tests for the additive durable-chat command migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "t8d6f1a10058_durable_chat_commands.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_durable_chat_commands_migration_module", MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOp:
    def __init__(self) -> None:
        self.created_tables: list[str] = []
        self.dropped_tables: list[str] = []
        self.created_indexes: list[tuple[str, str, dict[str, Any]]] = []
        self.dropped_indexes: list[str] = []

    def create_table(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.created_tables.append(name)

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)

    def create_index(
        self, name: str, table: str, columns: Any, **kwargs: Any,
    ) -> None:
        self.created_indexes.append((name, table, kwargs))

    def drop_index(self, name: str, **kwargs: Any) -> None:
        self.dropped_indexes.append(name)


def test_revision_chains_after_turn_lifecycle() -> None:
    migration = _load_migration()

    assert migration.revision == "t8d6f1a10058"
    assert migration.down_revision == "s7h3k9m10057"


def test_upgrade_creates_receipt_table_and_admission_index(monkeypatch) -> None:  # noqa: ANN001
    migration = _load_migration()
    recorder = _RecordingOp()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert recorder.created_tables == ["chat_turn_commands"]
    indexes = {name: kwargs for name, _table, kwargs in recorder.created_indexes}
    assert indexes["uq_chat_turn_commands_active_conversation"]["unique"] is True
    assert "postgresql_where" in indexes[
        "uq_chat_turn_commands_active_conversation"
    ]
    assert "sqlite_where" in indexes[
        "uq_chat_turn_commands_active_conversation"
    ]


def test_downgrade_drops_receipt_table(monkeypatch) -> None:  # noqa: ANN001
    migration = _load_migration()
    recorder = _RecordingOp()
    monkeypatch.setattr(migration, "op", recorder)

    migration.downgrade()

    assert recorder.dropped_tables == ["chat_turn_commands"]
