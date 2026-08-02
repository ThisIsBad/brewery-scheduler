"""style_year_number uniqueness via denormalized beer_style + brew_year

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The brewmaster-facing Sud-Nr is unique per (beer style, brew year).
    # Migration 0002 deferred the DB-level guarantee because expressing it
    # requires beer_style on the row itself. beer_style is denormalized here
    # (written by the application at create time — a Sud's style never
    # changes, recipe versions share their style) and brew_year is generated
    # from brew_date, so the unique constraint is enforceable without
    # triggers.
    op.add_column("sude", sa.Column("beer_style", sa.String(32), nullable=True))
    op.execute(
        "UPDATE sude SET beer_style = r.beer_style "
        "FROM recipes r WHERE r.id = sude.recipe_id"
    )
    op.alter_column("sude", "beer_style", nullable=False)

    op.execute(
        """
        ALTER TABLE sude
        ADD COLUMN brew_year integer
        GENERATED ALWAYS AS ((EXTRACT(YEAR FROM brew_date))::int) STORED
        """
    )
    op.create_unique_constraint(
        "uq_sude_style_year_number",
        "sude",
        ["beer_style", "brew_year", "style_year_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sude_style_year_number", "sude", type_="unique")
    op.drop_column("sude", "brew_year")
    op.drop_column("sude", "beer_style")
