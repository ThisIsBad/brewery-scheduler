"""free beer styles + active flag: recipes carry the brewery's real beers

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-04
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The four fixed dev styles give way to the brewery's real beer names
# (Bierrezepte.xlsx, 2026-08-04). Renaming keeps the per-(style, year)
# Sud numbering consistent across the switch.
RENAMES = [
    ("kellerbier", "Keller Hell"),
    ("wheat", "Weizen"),
    ("festbier", "Festbier"),
    ("special", "Spezialsud"),
]


def upgrade() -> None:
    # beer_style becomes a free label — the brewery names its beers
    # (Rauchbier Waltraut, Collab Widder …); a fixed enum cannot keep up.
    op.alter_column(
        "recipes",
        "beer_style",
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=False,
    )
    op.alter_column(
        "sude",
        "beer_style",
        type_=sa.String(64),
        existing_type=sa.String(32),
        existing_nullable=False,
    )
    # Former beers stay on file („frühere Biere" in the Excel) but are not
    # offered for new Sude.
    op.add_column(
        "recipes",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    for old, new in RENAMES:
        op.execute(
            sa.text("UPDATE recipes SET beer_style = :new WHERE beer_style = :old")
            .bindparams(old=old, new=new)
        )
        op.execute(
            sa.text("UPDATE sude SET beer_style = :new WHERE beer_style = :old")
            .bindparams(old=old, new=new)
        )


def downgrade() -> None:
    for old, new in RENAMES:
        op.execute(
            sa.text("UPDATE recipes SET beer_style = :old WHERE beer_style = :new")
            .bindparams(old=old, new=new)
        )
        op.execute(
            sa.text("UPDATE sude SET beer_style = :old WHERE beer_style = :new")
            .bindparams(old=old, new=new)
        )
    op.drop_column("recipes", "active")
    op.alter_column(
        "sude",
        "beer_style",
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=False,
    )
    op.alter_column(
        "recipes",
        "beer_style",
        type_=sa.String(32),
        existing_type=sa.String(64),
        existing_nullable=False,
    )
