"""Track current-intent lifecycle metadata.

The intent text historically had no timestamp, review status, or writer
provenance, so a sentence such as "睡醒後再找你" could look live forever after
its context had passed.  These additive state columns let the background
reconciler distinguish a fresh intent from a legacy/stale one without altering
any existing character, schedule, promise, or conversation data.

Revision ID: m5d2r8q10041
Revises: l4c8p9z10040
Create Date: 2026-08-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m5d2r8q10041"
down_revision = "l4c8p9z10040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("state_current_intent_updated_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "characters",
        sa.Column("state_current_intent_checked_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "characters",
        sa.Column("state_current_intent_reviewed_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "characters",
        sa.Column(
            "state_current_intent_status",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "state_current_intent_source",
            sa.String(length=32),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "state_current_intent_candidate_at",
            sa.DateTime(timezone=True),
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "state_current_intent_candidate_key",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("characters", "state_current_intent_candidate_key")
    op.drop_column("characters", "state_current_intent_candidate_at")
    op.drop_column("characters", "state_current_intent_source")
    op.drop_column("characters", "state_current_intent_status")
    op.drop_column("characters", "state_current_intent_reviewed_at")
    op.drop_column("characters", "state_current_intent_checked_at")
    op.drop_column("characters", "state_current_intent_updated_at")
