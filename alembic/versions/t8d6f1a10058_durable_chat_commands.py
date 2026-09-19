"""Add durable foreground chat command receipts (P1-1)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "t8d6f1a10058"
down_revision = "s7h3k9m10057"
branch_labels = None
depends_on = None


_ACTIVE_STATES = (
    "'queued', 'claimed', 'processing', 'generated', "
    "'committed', 'retry_wait', 'recovery_required'"
)


def upgrade() -> None:
    op.create_table(
        "chat_turn_commands",
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("client_message_id", sa.String(length=128), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "phase",
            sa.String(length=32),
            nullable=False,
            server_default="accepted",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conversation_revision", sa.Integer(), nullable=True),
        sa.Column("user_message_id", sa.Integer(), nullable=True),
        sa.Column("user_message_position", sa.Integer(), nullable=True),
        sa.Column("assistant_message_id", sa.Integer(), nullable=True),
        sa.Column("assistant_message_position", sa.Integer(), nullable=True),
        sa.Column("result_message_id", sa.Integer(), nullable=True),
        sa.Column("generated_snapshot_json", sa.Text(), nullable=True),
        sa.Column("generated_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "lease_generation",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("turn_id"),
        sa.UniqueConstraint(
            "owner_id",
            "client_message_id",
            name="uq_chat_turn_commands_owner_client_message",
        ),
    )
    op.create_index(
        "ix_chat_turn_commands_character_id",
        "chat_turn_commands",
        ["character_id"],
    )
    op.create_index(
        "uq_chat_turn_commands_active_conversation",
        "chat_turn_commands",
        ["owner_id", "conversation_id"],
        unique=True,
        postgresql_where=sa.text(f"state IN ({_ACTIVE_STATES})"),
        sqlite_where=sa.text(f"state IN ({_ACTIVE_STATES})"),
    )
    op.create_index(
        "ix_chat_turn_commands_owner_state_updated",
        "chat_turn_commands",
        ["owner_id", "state", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_turn_commands_owner_state_updated",
        table_name="chat_turn_commands",
    )
    op.drop_index(
        "uq_chat_turn_commands_active_conversation",
        table_name="chat_turn_commands",
    )
    op.drop_index(
        "ix_chat_turn_commands_character_id",
        table_name="chat_turn_commands",
    )
    op.drop_table("chat_turn_commands")
