"""recipe ingredients: yeast and target brew values as first-class columns

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-04
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Decided 2026-08-04: recipes carry malts (ingredients JSONB), hop
    # additions with boil minutes (hop_additions JSONB), the yeast choice
    # and target brew values. Yeast and the targets are typed columns —
    # they are single values the UI diffs and future calculations read.
    op.add_column("recipes", sa.Column("yeast", sa.String(128), nullable=True))
    op.add_column(
        "recipes", sa.Column("original_gravity_plato", sa.Numeric(4, 1), nullable=True)
    )
    op.add_column("recipes", sa.Column("ibu", sa.Numeric(5, 1), nullable=True))
    op.add_column("recipes", sa.Column("color_ebc", sa.Numeric(5, 1), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "color_ebc")
    op.drop_column("recipes", "ibu")
    op.drop_column("recipes", "original_gravity_plato")
    op.drop_column("recipes", "yeast")
