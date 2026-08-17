"""Merge scheduled promises by delivery window.

Adds an appointment-window identity plus the individual obligations that share
one visible callback.  Existing rows deliberately retain blank new keys: this
is an additive guard, while historical cleanup stays an explicit, reviewed
operation.

Revision ID: m5d2r8q10042
Revises: m5d2r8q10041
Create Date: 2026-08-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m5d2r8q10042"
down_revision = "m5d2r8q10041"
branch_labels = None
depends_on = None


_OPEN_DELIVERY_SLOT_PREDICATE = sa.text(
    "kind = 'scheduled_promise' "
    "AND status IN ('queued', 'resolving') "
    "AND delivery_slot_key <> ''",
)

_OPEN_EXACT_DEDUPE_PREDICATE = sa.text(
    "kind = 'scheduled_promise' "
    "AND status IN ('queued', 'resolving') "
    "AND dedupe_key <> ''",
)


def upgrade() -> None:
    op.add_column(
        "pending_follow_ups",
        sa.Column(
            "delivery_slot_key",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "pending_follow_ups",
        sa.Column(
            "source_turn_key",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "pending_follow_ups",
        sa.Column(
            "obligations_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.drop_index(
        "uq_pending_follow_ups_open_scheduled_promise_dedupe",
        table_name="pending_follow_ups",
    )
    op.create_index(
        "uq_pending_follow_ups_open_scheduled_promise_delivery_slot",
        "pending_follow_ups",
        ["delivery_slot_key"],
        unique=True,
        postgresql_where=_OPEN_DELIVERY_SLOT_PREDICATE,
        sqlite_where=_OPEN_DELIVERY_SLOT_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pending_follow_ups_open_scheduled_promise_delivery_slot",
        table_name="pending_follow_ups",
    )
    op.create_index(
        "uq_pending_follow_ups_open_scheduled_promise_dedupe",
        "pending_follow_ups",
        ["dedupe_key"],
        unique=True,
        postgresql_where=_OPEN_EXACT_DEDUPE_PREDICATE,
        sqlite_where=_OPEN_EXACT_DEDUPE_PREDICATE,
    )
    op.drop_column("pending_follow_ups", "obligations_json")
    op.drop_column("pending_follow_ups", "source_turn_key")
    op.drop_column("pending_follow_ups", "delivery_slot_key")
