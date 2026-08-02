"""withdrawals: partial volume leaving a tank (keg fills, issue #15)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Confirmed 2026-08 (issue #15): part of a tank's content can be filled
    # into kegs — volume leaves a tank without entering another one. The
    # remaining content of a tank allocation is allocation volume minus the
    # sum of its withdrawals; that number is what the Kellerblick card shows.
    op.create_table(
        "withdrawals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sud_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sude.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tank_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tanks.id"),
            nullable=False,
        ),
        sa.Column("volume_hl", sa.Numeric(6, 2), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="keg_fill"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("volume_hl > 0", name="ck_withdrawals_positive_volume"),
    )
    op.create_index("ix_withdrawals_sud_id", "withdrawals", ["sud_id"])
    op.create_index("ix_withdrawals_tank_id", "withdrawals", ["tank_id"])


def downgrade() -> None:
    op.drop_index("ix_withdrawals_tank_id", table_name="withdrawals")
    op.drop_index("ix_withdrawals_sud_id", table_name="withdrawals")
    op.drop_table("withdrawals")
