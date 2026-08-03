"""tank lock: protect master data against accidental edits

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Decided 2026-08-03: the lock protects a tank's master data (name,
    # location, type, capacity, removal) against accidental taps — it does
    # NOT block occupancies; beer keeps flowing into locked tanks.
    op.add_column(
        "tanks",
        sa.Column("locked", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("tanks", "locked")
