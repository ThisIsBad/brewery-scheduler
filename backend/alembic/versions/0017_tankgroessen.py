"""Tankgrößen nachgemessen: Resenscheck, Kitzmann vorne/hinten

Stefan, 2026-08-07: Resenscheck fasst 73,5 hl, Kitzmann vorne 51,8 hl,
Kitzmann hinten 90 hl. Frische Datenbanken bekommen die Werte direkt aus
dem Seed; hier ziehen bestehende Bestände nach.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

KAPAZITAETEN = {
    "Resenscheck": 73.5,
    "Kitzmann vorne": 51.8,
    "Kitzmann hinten": 90,
}


def upgrade() -> None:
    conn = op.get_bind()
    for name, hl in KAPAZITAETEN.items():
        conn.execute(
            sa.text("UPDATE tanks SET capacity_hl = :hl WHERE name = :name"),
            {"hl": hl, "name": name},
        )


def downgrade() -> None:
    # Die alten Werte waren Schätzungen — es gibt keinen Grund, zu ihnen
    # zurückzukehren; die Spalte selbst bleibt unangetastet.
    pass
