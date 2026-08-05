"""Bierfarben: je Sorte eine Anzeigefarbe für den Zeitplan

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-06
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Startpalette für die gesäten Biere (biertypische, unterscheidbare Töne).
# Bestehende Datenbestände bekommen sie nachgereicht; Stefan/Vincenz können
# jede Farbe im Rezepte-Tab ändern.
DEFAULT_FARBEN = {
    "Keller Hell": "#e0a92e",
    "Weizen": "#d98e2b",
    "Festbier": "#b06c1a",
    "Spezialsud": "#8e5ba6",
    "bay. Dunkel": "#6b4226",
    "Rauchbier": "#4a2f1d",
    "Weizenbock": "#a05c17",
    "Collab Widder": "#2e8b8b",
    "Wit": "#cfc06a",
    "Leichtbier": "#c0392b",
}


def upgrade() -> None:
    op.add_column("recipes", sa.Column("farbe", sa.String(16), nullable=True))
    conn = op.get_bind()
    for style, farbe in DEFAULT_FARBEN.items():
        conn.execute(
            sa.text(
                "UPDATE recipes SET farbe = :f "
                "WHERE beer_style = :s AND farbe IS NULL"
            ),
            {"f": farbe, "s": style},
        )


def downgrade() -> None:
    op.drop_column("recipes", "farbe")
