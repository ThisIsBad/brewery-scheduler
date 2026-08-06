"""Verbrauchsrate je Tank: Ø-Ausschank hl/Woche als Planungsgröße

Biergartensaison (Stefan, 2026-08-06): ~15 hl Kellerbier pro Woche aus
Kitzmann vorne, alles andere aus Fässern. Die Rate treibt nur die
Reichweiten-Prognose — das Ist bleibt in den Withdrawals. NULL = keine
Prognose (Bergkirchweih-Tanks laufen manuell).

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tanks",
        sa.Column("verbrauch_hl_pro_woche", sa.Numeric(6, 2), nullable=True),
    )
    # Bestehende Datenbanken bekommen den bekannten Biergarten-Wert.
    op.execute(
        "UPDATE tanks SET verbrauch_hl_pro_woche = 15 "
        "WHERE name = 'Kitzmann vorne'"
    )


def downgrade() -> None:
    op.drop_column("tanks", "verbrauch_hl_pro_woche")
