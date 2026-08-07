"""Änderungsprotokoll: wer hat wann was geändert

Stefan, 2026-08-07: Mit eigenen Konten je Person soll nachvollziehbar
sein, wer eine Änderung ausgelöst hat — für Rückfragen im Betrieb und
für die Fehlersuche.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        # Ohne Fremdschlüssel: ein gelöschter Sud soll seinen Verlauf nicht
        # mitnehmen — gerade der ist dann interessant.
        sa.Column("sud_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "changes",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_sud_id", "audit_log", ["sud_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
