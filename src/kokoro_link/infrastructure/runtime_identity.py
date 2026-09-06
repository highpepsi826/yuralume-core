"""Non-sensitive process identity used to label diagnostic exports."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

PROCESS_STARTED_AT = datetime.now(timezone.utc)


def instance_id() -> str:
    """Return a stable process/pod label without exposing deployment secrets."""
    for key in ("HOSTNAME", "POD_NAME", "ZEABUR_POD_NAME"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:128]
    return f"process-{uuid4().hex[:12]}"
