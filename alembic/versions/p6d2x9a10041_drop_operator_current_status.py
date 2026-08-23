"""Archive then drop operator_profiles.current_status / current_status_set_at

Revision ID: p6d2x9a10041
Revises: n5c1w8z10040
Create Date: 2026-08-17

PP series — "我現在的狀態" current_status is retired in favour of the
per-(character, operator) ``player_persona_notes`` declaration
(``n5c1w8z10040``). This field only ever fed the now-retired Scene
Access judge and, after D4, a plain narrative status line; both are
gone, so the columns are dead weight. Local self-host upgrades preserve any
pre-existing values in ``operator_profile_current_status_archive`` before
removing the retired columns.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p6d2x9a10041"
down_revision: Union[str, None] = "n5c1w8z10040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ARCHIVE_TABLE = "operator_profile_current_status_archive"


def upgrade() -> None:
    op.create_table(
        _ARCHIVE_TABLE,
        sa.Column("operator_id", sa.String(length=64), primary_key=True),
        sa.Column("current_status", sa.Text(), nullable=True),
        sa.Column(
            "current_status_set_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        sa.text(
            f"INSERT INTO {_ARCHIVE_TABLE} "
            "(operator_id, current_status, current_status_set_at) "
            "SELECT id, current_status, current_status_set_at "
            "FROM operator_profiles "
            "WHERE current_status IS NOT NULL "
            "OR current_status_set_at IS NOT NULL"
        )
    )
    with op.batch_alter_table("operator_profiles") as batch_op:
        batch_op.drop_column("current_status_set_at")
        batch_op.drop_column("current_status")


def downgrade() -> None:
    with op.batch_alter_table("operator_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("current_status", sa.Text(), nullable=True),
        )
        batch_op.add_column(
            sa.Column(
                "current_status_set_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
    op.execute(
        sa.text(
            "UPDATE operator_profiles "
            "SET current_status = ("
            f"SELECT archived.current_status FROM {_ARCHIVE_TABLE} AS archived "
            "WHERE archived.operator_id = operator_profiles.id"
            "), current_status_set_at = ("
            f"SELECT archived.current_status_set_at FROM {_ARCHIVE_TABLE} AS archived "
            "WHERE archived.operator_id = operator_profiles.id"
            ") "
            f"WHERE id IN (SELECT operator_id FROM {_ARCHIVE_TABLE})"
        )
    )
    op.drop_table(_ARCHIVE_TABLE)
