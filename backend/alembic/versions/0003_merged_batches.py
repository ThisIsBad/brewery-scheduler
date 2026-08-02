"""merged batches: volume_hl + merged_into_sud_id on sude

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Confirmed 2026-08 (issue #3): the same recipe is brewed twice within
    # 48 h and merged into one 30-hl tank. Model: the first brew is the
    # "lead" Sud and owns the tank occupancies; the second brew is a
    # "partner" Sud pointing at the lead via merged_into_sud_id. Partners
    # never carry occupancies of their own — the physical tank content is
    # tracked exactly once. volume_hl feeds the combined-volume-vs-tank-
    # capacity validation (standard Sud = 15 hl, ROADMAP §2.1).
    op.add_column(
        "sude",
        sa.Column("volume_hl", sa.Numeric(6, 2), nullable=False, server_default="15"),
    )
    op.add_column(
        "sude",
        sa.Column(
            "merged_into_sud_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sude.id", name="fk_sude_merged_into"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_sude_no_self_merge", "sude", "merged_into_sud_id != id"
    )
    op.create_index("ix_sude_merged_into_sud_id", "sude", ["merged_into_sud_id"])


def downgrade() -> None:
    op.drop_index("ix_sude_merged_into_sud_id", table_name="sude")
    op.drop_constraint("ck_sude_no_self_merge", "sude", type_="check")
    op.drop_constraint("fk_sude_merged_into", "sude", type_="foreignkey")
    op.drop_column("sude", "merged_into_sud_id")
    op.drop_column("sude", "volume_hl")
