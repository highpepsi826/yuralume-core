"""Widen tenant identifiers to match the cloud projection contract.

Cloud tenant IDs are authoritative at 128 characters. Queue, realtime outbox,
and external delivery receipt tables previously used 64-character columns,
which only failed for long hosted IDs at PostgreSQL commit time.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "v1w2x3y40001"
down_revision = "u9e7b2a11059"
branch_labels = None
depends_on = None

_TABLES = (
    "background_jobs",
    "realtime_events",
    "external_chat_turn_receipts",
    "external_proactive_events",
)


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(
            table,
            "tenant_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=128),
            existing_nullable=(
                True
                if table in {"background_jobs", "realtime_events"}
                else False
            ),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.alter_column(
            table,
            "tenant_id",
            existing_type=sa.String(length=128),
            type_=sa.String(length=64),
            existing_nullable=(
                True
                if table in {"background_jobs", "realtime_events"}
                else False
            ),
        )
