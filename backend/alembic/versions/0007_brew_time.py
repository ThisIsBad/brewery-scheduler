"""brew_at: brew timestamp — several Sude per day need ordering

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-03
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # There will be several Sude on one brew day (confirmed 2026-08), so the
    # brew moment needs a time, not just a date. brew_date stays: it feeds
    # the generated brew_year and the per-style/year numbering constraint,
    # and is now derived from brew_at by the application at create time.
    op.add_column(
        "sude", sa.Column("brew_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Backfill existing rows at 08:00 UTC of their brew day — a plausible
    # morning brew start; the exact time of historic seeds is cosmetic.
    op.execute(
        "UPDATE sude SET brew_at = (brew_date::timestamp AT TIME ZONE 'UTC')"
        " + interval '8 hours'"
    )
    op.alter_column("sude", "brew_at", nullable=False)


def downgrade() -> None:
    op.drop_column("sude", "brew_at")
