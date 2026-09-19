"""durable chat effect ledger

Revision ID: u9e7b2a11059
Revises: t8d6f1a10058
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "u9e7b2a11059"
down_revision = "t8d6f1a10058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_turn_effects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("effect_kind", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column(
            "state", sa.String(length=32), nullable=False,
            server_default="pending",
        ),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False,
            server_default="0",
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "turn_id", "effect_kind",
            name="uq_chat_turn_effects_turn_kind",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_chat_turn_effects_idempotency_key",
        ),
    )
    op.create_index(
        "ix_chat_turn_effects_turn_id",
        "chat_turn_effects",
        ["turn_id"],
    )
    op.create_index(
        "ix_chat_turn_effects_turn_state",
        "chat_turn_effects",
        ["turn_id", "state", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_turn_effects_turn_state",
        table_name="chat_turn_effects",
    )
    op.drop_index(
        "ix_chat_turn_effects_turn_id",
        table_name="chat_turn_effects",
    )
    op.drop_table("chat_turn_effects")
