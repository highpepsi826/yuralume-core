"""Add bounded processing outcomes to inbound delivery receipts."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "v6r4t2y10055"
down_revision = "u2c6m8p10046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_message_receipts",
        sa.Column("state", sa.String(length=32), nullable=False, server_default="claimed"),
    )
    op.add_column("inbound_message_receipts", sa.Column("failure_code", sa.String(length=64), nullable=True))
    op.add_column("inbound_message_receipts", sa.Column("failure_message", sa.Text(), nullable=True))
    op.add_column("inbound_message_receipts", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("inbound_message_receipts", "completed_at")
    op.drop_column("inbound_message_receipts", "failure_message")
    op.drop_column("inbound_message_receipts", "failure_code")
    op.drop_column("inbound_message_receipts", "state")
