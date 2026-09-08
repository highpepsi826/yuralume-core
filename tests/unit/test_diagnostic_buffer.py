from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from kokoro_link.infrastructure.observability.diagnostic_buffer import (
    DiagnosticBuffer,
    redact,
)


def test_redact_removes_secret_shaped_fields_and_values() -> None:
    value = redact({
        "api_key": "sk-test-secret-value",
        "access_token": "hidden",
        "prompt_tokens": 123,
        "nested": {"ok": "visible"},
    })
    assert value == {
        "api_key": "[REDACTED]",
        "access_token": "[REDACTED]",
        "prompt_tokens": 123,
        "nested": {"ok": "visible"},
    }


def test_buffer_snapshots_bounded_warning_records() -> None:
    buffer = DiagnosticBuffer(max_records=2)
    buffer.append(logging.LogRecord("app", logging.WARNING, __file__, 1, "first", (), None))
    buffer.append(logging.LogRecord("app", logging.ERROR, __file__, 2, "second", (), None))
    rows, coverage = buffer.snapshot(
        datetime.now(timezone.utc) - timedelta(minutes=1),
        datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    assert [row["message"] for row in rows] == ["first", "second"]
    assert coverage["source"] == "in_process_ring_buffer"
    assert coverage["truncated"] is False
