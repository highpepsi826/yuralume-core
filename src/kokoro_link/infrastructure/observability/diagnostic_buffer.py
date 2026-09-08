"""Bounded, redacted in-process diagnostics for admin incident exports."""

from __future__ import annotations

import copy
import logging
import re
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_MAX_RECORDS = 2000
_SECRET_KEY = re.compile(r"(?:token|secret|password|authorization|api[_-]?key|connection[_-]?string)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+|sk-[A-Za-z0-9_-]{12,}|bot\d+:[A-Za-z0-9_-]{20,})")


def redact(value: Any) -> Any:
    """Return a JSON-safe copy with secret-shaped fields and values removed."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact(child) for child in value[:2000]]
    if isinstance(value, tuple):
        return [redact(child) for child in value[:2000]]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1[REDACTED]", value)[:16000]
    return value


class _DiagnosticHandler(logging.Handler):
    def __init__(self, buffer: "DiagnosticBuffer") -> None:
        super().__init__(level=logging.WARNING)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(record)
        except Exception:
            # Diagnostics must never interfere with application logging.
            return


class DiagnosticBuffer:
    def __init__(self, max_records: int = _MAX_RECORDS) -> None:
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._max_records = max_records
        self._dropped = 0
        self._lock = Lock()
        self._handler: logging.Handler | None = None

    def install(self) -> None:
        with self._lock:
            root = logging.getLogger()
            if self._handler is None:
                self._handler = _DiagnosticHandler(self)
            if self._handler not in root.handlers:
                root.addHandler(self._handler)

    def append(self, record: logging.LogRecord) -> None:
        item = {
            "created_at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name[:160],
            "message": redact(record.getMessage()),
        }
        with self._lock:
            if len(self._records) == self._max_records:
                self._dropped += 1
            self._records.append(item)

    def snapshot(self, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        with self._lock:
            rows = copy.deepcopy(list(self._records))
            dropped = self._dropped
        selected = [
            row for row in rows
            if start <= datetime.fromisoformat(row["created_at"]) <= end
        ]
        oldest = datetime.fromisoformat(rows[0]["created_at"]) if rows else None
        return selected, {
            "status": "partial" if dropped and oldest and start < oldest else "complete",
            "source": "in_process_ring_buffer",
            "row_count": len(selected),
            "max_rows": self._max_records,
            "dropped_before_snapshot": dropped,
            "truncated": bool(dropped and oldest and start < oldest),
        }


_BUFFER = DiagnosticBuffer()


def get_diagnostic_buffer() -> DiagnosticBuffer:
    return _BUFFER


def install_diagnostic_buffer() -> None:
    _BUFFER.install()
