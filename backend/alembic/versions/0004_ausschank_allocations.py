"""ausschank allocations: occupancy volume + stage-scoped EXCLUDE

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Confirmed 2026-08 (issue #13): Ausschank tanks hold a blend of several
    # batches at once (6x 30 hl consolidated into 100 + 80 hl), and a batch
    # can be split across two Ausschank tanks. Two consequences:
    #
    # 1. Occupancies need a volume share. NULL means "the full combined
    #    volume of the occupying batch" — the common case for fermentation
    #    and storage, where batches stay together.
    op.add_column(
        "tank_occupancy",
        sa.Column("volume_hl", sa.Numeric(6, 2), nullable=True),
    )

    # 2. "One tank, one occupant" only holds before the Ausschank stage.
    #    The EXCLUDE constraint keeps guarding fermentation and storage at
    #    the database level; Ausschank coexistence is legal and guarded by
    #    the application-level sum-of-allocations <= capacity rule.
    op.drop_constraint("ex_tank_occupancy_no_overlap", "tank_occupancy", type_=None)
    op.execute(
        """
        ALTER TABLE tank_occupancy
        ADD CONSTRAINT ex_tank_occupancy_no_overlap
        EXCLUDE USING gist (
            tank_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        ) WHERE (stage != 'ausschank')
        """
    )


def downgrade() -> None:
    op.drop_constraint("ex_tank_occupancy_no_overlap", "tank_occupancy", type_=None)
    op.execute(
        """
        ALTER TABLE tank_occupancy
        ADD CONSTRAINT ex_tank_occupancy_no_overlap
        EXCLUDE USING gist (
            tank_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        """
    )
    op.drop_column("tank_occupancy", "volume_hl")
