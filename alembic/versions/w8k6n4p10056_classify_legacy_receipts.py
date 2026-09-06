"""Classify receipts created before outcome tracking was deployed."""

from __future__ import annotations

from alembic import op


revision = "w8k6n4p10056"
down_revision = "v6r4t2y10055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The first outcome migration added a non-null default, so existing rows
    # were necessarily backfilled as ``claimed`` even though the old runtime
    # never recorded an outcome. Keep only very recent rows eligible for an
    # in-flight interpretation; classify older rows as historical/unknown.
    op.execute(
        """
        UPDATE inbound_message_receipts
        SET state = 'legacy'
        WHERE state = 'claimed'
          AND completed_at IS NULL
          AND created_at < (CURRENT_TIMESTAMP - INTERVAL '10 minutes')
        """,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE inbound_message_receipts SET state = 'claimed' WHERE state = 'legacy'",
    )
