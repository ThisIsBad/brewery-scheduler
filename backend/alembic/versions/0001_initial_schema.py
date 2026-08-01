"""initial schema: recipes, tanks, sude, tank_occupancy

Revision ID: 0001
Revises:
Create Date: 2026-04-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # btree_gist is required for the EXCLUDE constraint on tank_occupancy:
    # we mix equality on tank_id (uuid, btree) with overlap on tstzrange (gist).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "recipes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("beer_style", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("ingredients", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("mash_schedule", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("hop_additions", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("fermentation_temp_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("fermentation_duration_days", sa.Numeric(5, 2), nullable=False),
        sa.Column("open_fermentation_required", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("open_fermentation_duration_days", sa.Numeric(5, 2), nullable=True),
        sa.Column("storage_duration_days", sa.Numeric(5, 2), nullable=False),
        sa.Column("max_storage_duration_days", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.UniqueConstraint("beer_style", "version", name="uq_recipes_style_version"),
    )

    op.create_table(
        "tanks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("cellar", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("capacity_hl", sa.Numeric(6, 2), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("name", name="uq_tanks_name"),
    )

    op.create_table(
        "sude",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id"),
            nullable=False,
        ),
        sa.Column("recipe_overrides", postgresql.JSONB, nullable=True),
        sa.Column("brew_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("brewmaster", sa.String(128), nullable=True),
    )

    op.create_table(
        "tank_occupancy",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sud_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sude.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tank_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tanks.id"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_tank_occupancy_time_order"
        ),
    )

    # Database-level guarantee that no two occupancies of the same tank overlap in time.
    # This is intentional defense-in-depth: even if Phase 2 application validation has
    # a bug, the database refuses to insert overlapping rows.
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

    op.create_index("ix_tank_occupancy_sud_id", "tank_occupancy", ["sud_id"])
    op.create_index("ix_tank_occupancy_tank_id", "tank_occupancy", ["tank_id"])


def downgrade() -> None:
    op.drop_index("ix_tank_occupancy_tank_id", table_name="tank_occupancy")
    op.drop_index("ix_tank_occupancy_sud_id", table_name="tank_occupancy")
    op.drop_table("tank_occupancy")
    op.drop_table("sude")
    op.drop_table("tanks")
    op.drop_table("recipes")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
