"""locations: user-defined Standorte replace the fixed cellar enum

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The two hardcoded cellars become rows so the brewery can add sites
    # (e.g. a festival tent) without a schema change.
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("name", name="uq_locations_name"),
    )

    main_id, secondary_id = uuid.uuid4(), uuid.uuid4()
    op.execute(
        sa.text(
            "INSERT INTO locations (id, name, position) VALUES "
            "(:main, 'Hauptkeller', 1), (:secondary, 'Nebenkeller', 2)"
        ).bindparams(main=main_id, secondary=secondary_id)
    )

    op.add_column(
        "tanks",
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text("UPDATE tanks SET location_id = :main WHERE cellar = 'main'").bindparams(
            main=main_id
        )
    )
    op.execute(
        sa.text(
            "UPDATE tanks SET location_id = :secondary WHERE cellar = 'secondary'"
        ).bindparams(secondary=secondary_id)
    )
    op.alter_column("tanks", "location_id", nullable=False)
    op.create_foreign_key(
        "fk_tanks_location", "tanks", "locations", ["location_id"], ["id"]
    )
    op.drop_column("tanks", "cellar")


def downgrade() -> None:
    op.add_column("tanks", sa.Column("cellar", sa.String(16), nullable=True))
    op.execute(
        "UPDATE tanks SET cellar = CASE"
        " WHEN location_id = (SELECT id FROM locations WHERE name = 'Nebenkeller')"
        " THEN 'secondary' ELSE 'main' END"
    )
    op.alter_column("tanks", "cellar", nullable=False)
    op.drop_constraint("fk_tanks_location", "tanks", type_="foreignkey")
    op.drop_column("tanks", "location_id")
    op.drop_table("locations")
