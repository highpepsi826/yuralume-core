"""Add shared commitment identity projections."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "u2c6m8p10046"
down_revision = "t9q4v7x10045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "schedule_activities",
        "story_arc_beats",
        "character_goals",
        "pending_follow_ups",
    ):
        op.add_column(
            table,
            sa.Column("commitment_key", sa.String(length=120), nullable=True),
        )
        op.create_index(
            f"ix_{table}_commitment_key",
            table,
            ["commitment_key"],
        )
    for table in ("schedule_activities", "story_arc_beats"):
        op.add_column(
            table,
            sa.Column(
                "is_first_meeting",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    op.add_column("character_goals", sa.Column("target_date_iso", sa.Date(), nullable=True))


def downgrade() -> None:
    for table in ("schedule_activities", "story_arc_beats"):
        op.drop_column(table, "is_first_meeting")
    op.drop_column("character_goals", "target_date_iso")
    for table in (
        "pending_follow_ups",
        "character_goals",
        "story_arc_beats",
        "schedule_activities",
    ):
        op.drop_index(f"ix_{table}_commitment_key", table_name=table)
        op.drop_column(table, "commitment_key")
