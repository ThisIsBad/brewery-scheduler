"""keg counts: record barrel sizes and counts on keg-fill withdrawals

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-04
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Decided 2026-08-04: keg fills are entered as counts per barrel size
    # (10/20/30/50 l) and the hl volume is computed from them. The counts
    # are kept for later stock/sales reconciliation (Phase 6).
    op.add_column(
        "withdrawals",
        sa.Column("keg_counts", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("withdrawals", "keg_counts")
