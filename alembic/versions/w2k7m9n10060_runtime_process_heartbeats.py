"""Add durable, bounded process heartbeats for diagnostic fleet snapshots."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "w2k7m9n10060"
down_revision = "v1w2x3y40001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_process_heartbeats",
        sa.Column("instance_id", sa.String(length=128), nullable=False),
        sa.Column("process_role", sa.String(length=16), nullable=False),
        sa.Column("service_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("build_commit_sha", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("build_tag", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("health_state", sa.String(length=16), nullable=False),
        sa.Column("durable_acceptance_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("durable_worker_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("durable_worker_alive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("background_coordinator_alive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("connector_runtime_state", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "process_role IN ('api', 'coordinator', 'worker', 'connector')",
            name="ck_runtime_process_heartbeats_role",
        ),
        sa.CheckConstraint(
            "health_state IN ('starting', 'healthy', 'degraded', 'stopping')",
            name="ck_runtime_process_heartbeats_health",
        ),
        sa.PrimaryKeyConstraint("instance_id"),
    )
    op.create_index(
        "ix_runtime_process_heartbeats_role_seen",
        "runtime_process_heartbeats",
        ["process_role", "last_seen_at"],
    )
    op.create_index(
        "ix_runtime_process_heartbeats_seen",
        "runtime_process_heartbeats",
        ["last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_process_heartbeats_seen",
        table_name="runtime_process_heartbeats",
    )
    op.drop_index(
        "ix_runtime_process_heartbeats_role_seen",
        table_name="runtime_process_heartbeats",
    )
    op.drop_table("runtime_process_heartbeats")
