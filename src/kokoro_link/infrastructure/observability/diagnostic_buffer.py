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
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|bot[_-]?token|"
    r"authorization|password|secret|connection[_-]?string|cookie|headers)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[^\s,;]+|sk-[A-Za-z0-9_-]{12,}|bot\d+:[A-Za-z0-9_-]{20,}|"
    r"(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+)"
)


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
        value = re.sub(r"https?://[^\s<>]+", "[REDACTED_URL]", value, flags=re.I)
        return _SECRET_VALUE.sub("[REDACTED]", value)[:16000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[UNSUPPORTED]"


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
        self._installed_at: datetime | None = None
        self._first_observed_at: datetime | None = None

    def install(self) -> None:
        with self._lock:
            root = logging.getLogger()
            if self._handler is None:
                self._handler = _DiagnosticHandler(self)
            if self._handler not in root.handlers:
                root.addHandler(self._handler)
                self._installed_at = datetime.now(timezone.utc)

    def append(self, record: logging.LogRecord) -> None:
        from .persistent_diagnostics import safe_log_metadata

        safe = safe_log_metadata(record)
        item = {
            "created_at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": safe["logger"],
            "message": "application log (body omitted)",
            **safe,
        }
        with self._lock:
            if self._first_observed_at is None:
                self._first_observed_at = datetime.fromtimestamp(record.created, timezone.utc)
            if len(self._records) == self._max_records:
                self._dropped += 1
            self._records.append(item)

    def snapshot(self, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        with self._lock:
            rows = copy.deepcopy(list(self._records))
            dropped = self._dropped
            installed_at = self._installed_at
            first_observed_at = self._first_observed_at
        selected = [
            row for row in rows
            if start <= datetime.fromisoformat(row["created_at"]) <= end
        ]
        oldest = datetime.fromisoformat(rows[0]["created_at"]) if rows else None
        return selected, {
            "status": "partial" if not installed_at or start < installed_at or (
                dropped and oldest and start < oldest
            ) else "complete",
            "source": "in_process_ring_buffer",
            "row_count": len(selected),
            "max_rows": self._max_records,
            "dropped_before_snapshot": dropped,
            "truncated": bool(dropped and oldest and start < oldest),
            "installed_at": installed_at.isoformat() if installed_at else None,
            "first_observed_at": first_observed_at.isoformat() if first_observed_at else None,
            "coverage_start": installed_at.isoformat() if installed_at else None,
            "message_bodies": "omitted",
        }


_BUFFER = DiagnosticBuffer()


def get_diagnostic_buffer() -> DiagnosticBuffer:
    return _BUFFER


def install_diagnostic_buffer() -> None:
    _BUFFER.install()
