"""Deduplicate open scheduled-promise follow-up rows.

Post-turn extraction can run more than once for the same completed turn.  A
random follow-up id used to let each retry create another future release.  This
adds a stable key and a partial unique index for open scheduled promises only.

Existing rows keep an empty key and are deliberately left untouched: this is
an additive integrity guard, not a destructive cleanup migration.

Revision ID: l4c8p9z10040
Revises: k3b0v7y10039
Create Date: 2026-08-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "l4c8p9z10040"
down_revision = "k3b0v7y10039"
branch_labels = None
depends_on = None


_OPEN_PROMISE_PREDICATE = sa.text(
    "kind = 'scheduled_promise' "
    "AND status IN ('queued', 'resolving') "
    "AND dedupe_key <> ''",
)


def upgrade() -> None:
    op.add_column(
        "pending_follow_ups",
        sa.Column(
            "dedupe_key",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "uq_pending_follow_ups_open_scheduled_promise_dedupe",
        "pending_follow_ups",
        ["dedupe_key"],
        unique=True,
        postgresql_where=_OPEN_PROMISE_PREDICATE,
        sqlite_where=_OPEN_PROMISE_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pending_follow_ups_open_scheduled_promise_dedupe",
        table_name="pending_follow_ups",
    )
    op.drop_column("pending_follow_ups", "dedupe_key")
