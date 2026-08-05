"""Vincenz' Tankwelt: Rufnamen, Keller-Standorte, Resenscheck, 10-hl-Ausschank

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-06
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Bestätigte Liste (Stefan, 2026-08-06). Gär-/Lagertanks tragen Rufnamen,
# Ausschanktanks heißen nach ihrem Keller. Alles hier ist idempotent und
# no-op auf frischen Datenbanken — dort seedet seed.py direkt die neuen
# Namen; hier werden nur BESTEHENDE (alt benannte) Bestände umgezogen.

TANK_RENAMES = {
    "F-30-1": "Lisa",
    "F-30-2": "Wanda",
    "F-30-3": "Greta",
    "F-30-4": "Anouk",
    "F-30-5": "Yuri",
    "F-15-1": "Alva",
    "F-15-2": "Lovis",
    "F-OPEN-15": "Offener Gärbottich",
    "S-30-1": "Vincenz",
    "S-30-2": "Xaver",
    "S-30-3": "Benjamin",
    "S-30-4": "Evelyn",
    "S-30-5": "Fritz",
    "A-120": "Bergtank 120 hl",
    "A-100": "Bergtank 100 hl",
    "A-80": "Kitzmann hinten",
    "A-50": "Kitzmann vorne",
    "A2-35-1": "Striezi Keller 1",
    "A2-35-2": "Striezi Keller 2",
    "S2-10-1": "Striezi Keller 3",
    "S2-10-2": "Striezi Keller 4",
}

LOCATION_RENAMES = {"Hauptkeller": "Schänke 4", "Nebenkeller": "Striezi Keller"}

LOCATIONS = ["Schänke 4", "Kitzmann Keller", "Resenscheck Keller", "Striezi Keller"]

TANK_LOCATIONS = {
    "Kitzmann hinten": "Kitzmann Keller",
    "Kitzmann vorne": "Kitzmann Keller",
    "Resenscheck": "Resenscheck Keller",
    "Striezi Keller 1": "Striezi Keller",
    "Striezi Keller 2": "Striezi Keller",
    "Striezi Keller 3": "Striezi Keller",
    "Striezi Keller 4": "Striezi Keller",
}


def upgrade() -> None:
    conn = op.get_bind()

    def scalar(sql: str, **params):
        return conn.execute(sa.text(sql), params).scalar()

    for old, new in LOCATION_RENAMES.items():
        if scalar("SELECT 1 FROM locations WHERE name = :n", n=new) is None:
            conn.execute(
                sa.text("UPDATE locations SET name = :new WHERE name = :old"),
                {"old": old, "new": new},
            )
    for position, name in enumerate(LOCATIONS, start=1):
        if scalar("SELECT 1 FROM locations WHERE name = :n", n=name) is None:
            conn.execute(
                sa.text(
                    "INSERT INTO locations (id, name, position) VALUES (:i, :n, :p)"
                ),
                {"i": str(uuid.uuid4()), "n": name, "p": position},
            )
        else:
            conn.execute(
                sa.text("UPDATE locations SET position = :p WHERE name = :n"),
                {"n": name, "p": position},
            )

    for old, new in TANK_RENAMES.items():
        if scalar("SELECT 1 FROM tanks WHERE name = :n", n=new) is None:
            conn.execute(
                sa.text("UPDATE tanks SET name = :new WHERE name = :old"),
                {"old": old, "new": new},
            )

    for tank, location in TANK_LOCATIONS.items():
        conn.execute(
            sa.text(
                "UPDATE tanks SET location_id = "
                "(SELECT id FROM locations WHERE name = :l) WHERE name = :t"
            ),
            {"l": location, "t": tank},
        )

    # Die beiden 10-hl-Tanks sind Ausschanktanks (Sortenrein-Regel gilt dort
    # ohnehin; außerhalb des Ausschanks erzwingt EXCLUDE Exklusivität).
    conn.execute(
        sa.text(
            "UPDATE tanks SET stage = 'ausschank' "
            "WHERE name IN ('Striezi Keller 3', 'Striezi Keller 4')"
        )
    )

    # Resenscheck (80 hl) ist ein ZUSÄTZLICHER Tank — nur Bergkirchweih.
    if (
        scalar("SELECT 1 FROM tanks WHERE name = 'Resenscheck'") is None
        and scalar("SELECT 1 FROM tanks LIMIT 1") is not None
    ):
        conn.execute(
            sa.text(
                "INSERT INTO tanks (id, name, location_id, stage, capacity_hl, active, locked) "
                "VALUES (:i, 'Resenscheck', "
                "(SELECT id FROM locations WHERE name = 'Resenscheck Keller'), "
                "'ausschank', 80, true, false)"
            ),
            {"i": str(uuid.uuid4())},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for old, new in TANK_RENAMES.items():
        conn.execute(
            sa.text("UPDATE tanks SET name = :old WHERE name = :new"),
            {"old": old, "new": new},
        )
    for old, new in LOCATION_RENAMES.items():
        conn.execute(
            sa.text("UPDATE locations SET name = :old WHERE name = :new"),
            {"old": old, "new": new},
        )
