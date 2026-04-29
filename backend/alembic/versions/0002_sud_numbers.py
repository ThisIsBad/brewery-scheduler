"""add sud numbers (global + per-style-per-year)

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # global_number — sequential across all years and styles, internal-only.
    # The brewmaster sets the go-live offset via the set_global_seq CLI;
    # this migration just creates the sequence so dev/test work has stable
    # numbers.
    op.execute("CREATE SEQUENCE IF NOT EXISTS sud_global_seq START WITH 1")

    op.add_column("sude", sa.Column("global_number", sa.Integer(), nullable=True))
    op.add_column("sude", sa.Column("style_year_number", sa.Integer(), nullable=True))

    # Backfill: number existing rows by brew_date (then id for determinism).
    # The per-style-per-year number partitions on recipe.beer_style joined
    # through recipe_id and the year part of brew_date.
    op.execute(
        """
        WITH numbered AS (
            SELECT s.id,
                   ROW_NUMBER() OVER (ORDER BY s.brew_date, s.id) AS gn,
                   ROW_NUMBER() OVER (
                       PARTITION BY r.beer_style, EXTRACT(YEAR FROM s.brew_date)
                       ORDER BY s.brew_date, s.id
                   ) AS syn
            FROM sude s
            JOIN recipes r ON r.id = s.recipe_id
        )
        UPDATE sude
        SET global_number = numbered.gn,
            style_year_number = numbered.syn
        FROM numbered
        WHERE sude.id = numbered.id
        """
    )

    # Advance the sequence past the backfilled values so the next nextval()
    # returns max(global_number) + 1.
    op.execute(
        "SELECT setval('sud_global_seq', "
        "COALESCE((SELECT MAX(global_number) FROM sude), 0) + 1, false)"
    )

    op.alter_column(
        "sude",
        "global_number",
        nullable=False,
        server_default=sa.text("nextval('sud_global_seq')"),
    )
    op.alter_column("sude", "style_year_number", nullable=False)

    op.create_unique_constraint("uq_sude_global_number", "sude", ["global_number"])

    # Per-style-per-year uniqueness is handled in application code for
    # Phase 1 — single brewmaster, no concurrent inserts. Phase 2 will add
    # a database-level guarantee once we know whether to denormalise
    # beer_style or use a separate batches-per-year table.


def downgrade() -> None:
    op.drop_constraint("uq_sude_global_number", "sude", type_="unique")
    op.alter_column("sude", "global_number", server_default=None)
    op.drop_column("sude", "style_year_number")
    op.drop_column("sude", "global_number")
    op.execute("DROP SEQUENCE IF EXISTS sud_global_seq")
