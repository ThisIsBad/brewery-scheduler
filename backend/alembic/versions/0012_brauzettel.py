"""brew sheet alignment with the paper Bierrezepte: water, boil, timing text

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-04
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Stefans Bierrezepte.xlsx (2026-08-04) is the reference: recipes gain
    # brewing water (Haupt-/Nachgüsse), the boil time, a carbonation target
    # and free-text pitching notes. Hop timings become free text as on the
    # paper sheet („Kochbeginn", „nach 55 min", „Whirlpool") instead of
    # boil minutes — existing entries are rewritten losslessly.
    op.add_column("recipes", sa.Column("wasser", JSONB, nullable=True))
    op.add_column("recipes", sa.Column("kochzeit_min", sa.Numeric(4, 0), nullable=True))
    op.add_column(
        "recipes", sa.Column("karbonisierung_g_l", sa.Numeric(3, 1), nullable=True)
    )
    op.add_column("recipes", sa.Column("anstellhinweis", sa.String(256), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, hop_additions FROM recipes")).fetchall()
    for recipe_id, hop_additions in rows:
        gaben = (hop_additions or {}).get("gaben") or []
        changed = False
        for gabe in gaben:
            if "zeitpunkt" in gabe:
                continue
            minutes = gabe.pop("kochzeit_min", None)
            if minutes is None:
                continue
            gabe["zeitpunkt"] = (
                "Whirlpool" if minutes == 0 else f"{minutes:g} min vor Kochende"
            )
            changed = True
        if changed:
            conn.execute(
                sa.text(
                    "UPDATE recipes SET hop_additions = CAST(:h AS JSONB) WHERE id = :i"
                ),
                {"h": json.dumps({**hop_additions, "gaben": gaben}), "i": recipe_id},
            )


def downgrade() -> None:
    op.drop_column("recipes", "anstellhinweis")
    op.drop_column("recipes", "karbonisierung_g_l")
    op.drop_column("recipes", "kochzeit_min")
    op.drop_column("recipes", "wasser")
