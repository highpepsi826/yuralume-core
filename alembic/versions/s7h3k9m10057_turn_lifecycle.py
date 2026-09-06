"""Add durable foreground turn lifecycle fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "s7h3k9m10057"
down_revision = "w8k6n4p10056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "turn_records",
        sa.Column("status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "turn_records",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "turn_records",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "turn_records",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "turn_records",
        sa.Column("failure_code", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE turn_records SET status = 'completed' WHERE status IS NULL")
    op.alter_column(
        "turn_records", "status", nullable=False, server_default="completed",
    )
    op.create_index("ix_turn_records_status", "turn_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_turn_records_status", table_name="turn_records")
    op.drop_column("turn_records", "failure_code")
    op.drop_column("turn_records", "last_heartbeat_at")
    op.drop_column("turn_records", "updated_at")
    op.drop_column("turn_records", "started_at")
    op.drop_column("turn_records", "status")
