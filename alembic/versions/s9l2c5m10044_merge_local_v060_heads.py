"""Merge the local pending-follow-up branch with upstream v0.6.0.

The local customizations branch and upstream both continued from the same
pre-v0.6.0 revision. This schema-neutral merge node gives ``alembic upgrade
head`` one unambiguous target while preserving both migration histories.

Revision ID: s9l2c5m10044
Revises: m5d2r8q10042, r8f4z1c10043
Create Date: 2026-08-23
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "s9l2c5m10044"
down_revision: Union[str, Sequence[str], None] = (
    "m5d2r8q10042",
    "r8f4z1c10043",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No schema change; joins the two independently applied branches."""


def downgrade() -> None:
    """No schema change; Alembic restores the two parent heads."""
