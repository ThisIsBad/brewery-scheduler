"""SQLAlchemy 2.x ORM models.

Mirrors the schema sketched in ROADMAP.md §4. Phase 1 omits the sales and
demand_forecasts tables (they belong to Phase 6+).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BeerStyle(str, enum.Enum):
    KELLERBIER = "kellerbier"
    WHEAT = "wheat"
    FESTBIER = "festbier"
    SPECIAL = "special"


class TankCellar(str, enum.Enum):
    MAIN = "main"
    SECONDARY = "secondary"


class TankStage(str, enum.Enum):
    FERMENTATION_OPEN = "fermentation_open"
    FERMENTATION_CLOSED = "fermentation_closed"
    STORAGE = "storage"
    AUSSCHANK = "ausschank"


class SudStatus(str, enum.Enum):
    PLANNED = "planned"
    BREWING = "brewing"
    FERMENTING = "fermenting"
    STORING = "storing"
    IN_AUSSCHANK = "in_ausschank"
    SERVED = "served"
    DISCARDED = "discarded"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("beer_style", "version", name="uq_recipes_style_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    beer_style: Mapped[BeerStyle] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ingredients: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    mash_schedule: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hop_additions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fermentation_temp_c: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    fermentation_duration_days: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    open_fermentation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    open_fermentation_duration_days: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    storage_duration_days: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_storage_duration_days: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Tank(Base):
    __tablename__ = "tanks"
    __table_args__ = (UniqueConstraint("name", name="uq_tanks_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    cellar: Mapped[TankCellar] = mapped_column(String(16), nullable=False)
    stage: Mapped[TankStage] = mapped_column(String(32), nullable=False)
    capacity_hl: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


SUD_GLOBAL_SEQ = Sequence("sud_global_seq")


class Sud(Base):
    __tablename__ = "sude"

    id: Mapped[uuid.UUID] = _uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id"), nullable=False
    )
    recipe_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    brew_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[SudStatus] = mapped_column(String(32), nullable=False, default=SudStatus.PLANNED)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brewmaster: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Sequential across all years and styles. Internal-only — the brewmaster
    # sets the go-live offset via the set_global_seq CLI; subsequent values
    # come from the sud_global_seq Postgres sequence.
    global_number: Mapped[int] = mapped_column(
        SUD_GLOBAL_SEQ, server_default=SUD_GLOBAL_SEQ.next_value(), nullable=False
    )

    # Sequential per (recipe.beer_style, year(brew_date)). This is the
    # "Sud-Nr." shown on the Gantt — "Kellerbier 17/2026" means the 17th
    # Kellerbier brewed in 2026. Application logic assigns this on insert.
    style_year_number: Mapped[int] = mapped_column(nullable=False)

    recipe: Mapped[Recipe] = relationship(lazy="joined")
    occupancies: Mapped[list[TankOccupancy]] = relationship(
        back_populates="sud", cascade="all, delete-orphan", order_by="TankOccupancy.start_at"
    )


class TankOccupancy(Base):
    """A time window during which a Sud occupies a Tank for one stage.

    The exclusion constraint `tank_occupancy_no_overlap` is added in the Alembic
    migration (SQLAlchemy 2.x doesn't have first-class support for `EXCLUDE USING gist`).
    """

    __tablename__ = "tank_occupancy"
    __table_args__ = (
        CheckConstraint(
            "end_at IS NULL OR end_at > start_at", name="ck_tank_occupancy_time_order"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sude.id", ondelete="CASCADE"), nullable=False
    )
    tank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tanks.id"), nullable=False
    )
    stage: Mapped[TankStage] = mapped_column(String(32), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sud: Mapped[Sud] = relationship(back_populates="occupancies")
    tank: Mapped[Tank] = relationship(lazy="joined")
