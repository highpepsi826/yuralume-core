"""Add durable outbound message delivery ledger."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "t9q4v7x10045"
down_revision = "s9l2c5m10044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_message_deliveries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("chat_ref", sa.String(length=256), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbound_message_deliveries_state_due",
        "outbound_message_deliveries",
        ["state", "next_attempt_at"],
    )
    op.create_index(
        "ix_outbound_message_deliveries_account",
        "outbound_message_deliveries",
        ["account_id"],
    )
    op.create_index(
        "ix_outbound_message_deliveries_batch_sequence",
        "outbound_message_deliveries",
        ["batch_id", "sequence_no"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbound_message_deliveries_account",
        table_name="outbound_message_deliveries",
    )
    op.drop_index(
        "ix_outbound_message_deliveries_state_due",
        table_name="outbound_message_deliveries",
    )
    op.drop_index(
        "ix_outbound_message_deliveries_batch_sequence",
        table_name="outbound_message_deliveries",
    )
    op.drop_table("outbound_message_deliveries")
