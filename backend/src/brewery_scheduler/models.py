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
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Postgres sequence backing the Sud.global_number column. Bound to
# Base.metadata so create_all picks it up in tests; production goes through
# the Alembic migration.
SUD_GLOBAL_SEQ = Sequence("sud_global_seq", metadata=Base.metadata)


def _enum(enum_cls: type[enum.Enum], length: int) -> SAEnum:
    """VARCHAR-backed enum storing member *values*, so rows loaded from the
    database come back as enum members instead of bare strings (the str-enum
    equality that papered over this went as far as `.value` crashing)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class BeerStyle(str, enum.Enum):
    KELLERBIER = "kellerbier"
    WHEAT = "wheat"
    FESTBIER = "festbier"
    SPECIAL = "special"


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
    beer_style: Mapped[BeerStyle] = mapped_column(_enum(BeerStyle, 32), nullable=False)
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


class Location(Base):
    """A physical site holding tanks (Hauptkeller, Nebenkeller, Festzelt …).

    User-defined: the brewery adds sites in the Tankverwaltung; `position`
    keeps the display order stable regardless of alphabet.
    """

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("name", name="uq_locations_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Tank(Base):
    __tablename__ = "tanks"
    __table_args__ = (UniqueConstraint("name", name="uq_tanks_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", name="fk_tanks_location"),
        nullable=False,
    )
    location: Mapped[Location] = relationship(lazy="joined")
    stage: Mapped[TankStage] = mapped_column(_enum(TankStage, 32), nullable=False)
    capacity_hl: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Sud(Base):
    __tablename__ = "sude"
    __table_args__ = (
        UniqueConstraint("global_number", name="uq_sude_global_number"),
        UniqueConstraint(
            "beer_style",
            "brew_year",
            "style_year_number",
            name="uq_sude_style_year_number",
        ),
        CheckConstraint("merged_into_sud_id != id", name="ck_sude_no_self_merge"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recipes.id"), nullable=False
    )
    recipe_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The brew moment. brew_date is derived from it at create time and kept
    # because the generated brew_year / numbering constraint depend on it.
    brew_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    brew_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[SudStatus] = mapped_column(
        _enum(SudStatus, 32), nullable=False, default=SudStatus.PLANNED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brewmaster: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Standard Sud is 15 hl (ROADMAP §2.1); drives combined-volume vs. tank
    # capacity validation for merged batches.
    volume_hl: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=15, server_default="15"
    )

    # Merged batches (confirmed 2026-08, issue #3): the same recipe brewed
    # twice within 48 h shares one tank. The first brew is the "lead" and
    # owns the occupancies; partners point here and never carry occupancies
    # of their own.
    merged_into_sud_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sude.id", name="fk_sude_merged_into"),
        nullable=True,
        index=True,
    )

    # Sequential across all years and styles. Internal-only — the brewmaster
    # sets the go-live offset via the set_global_seq CLI; subsequent values
    # come from the sud_global_seq Postgres sequence.
    global_number: Mapped[int] = mapped_column(
        SUD_GLOBAL_SEQ, server_default=SUD_GLOBAL_SEQ.next_value(), nullable=False
    )

    # Sequential per (beer_style, year(brew_date)). This is the "Sud-Nr."
    # shown on the Gantt — "Kellerbier 17/2026" means the 17th Kellerbier
    # brewed in 2026. Application logic assigns this on insert; the unique
    # constraint over (beer_style, brew_year, style_year_number) turns a
    # concurrent-create race into a rejected request instead of a silent
    # duplicate number.
    style_year_number: Mapped[int] = mapped_column(nullable=False)

    # Denormalized from the recipe at create time — a Sud's style never
    # changes (recipe versions share their style); exists to back the
    # unique constraint above.
    beer_style: Mapped[BeerStyle] = mapped_column(_enum(BeerStyle, 32), nullable=False)
    brew_year: Mapped[int] = mapped_column(
        Integer,
        Computed("(EXTRACT(YEAR FROM brew_date))::int", persisted=True),
        nullable=False,
    )

    recipe: Mapped[Recipe] = relationship(lazy="joined")
    occupancies: Mapped[list[TankOccupancy]] = relationship(
        back_populates="sud", cascade="all, delete-orphan", order_by="TankOccupancy.start_at"
    )
    merged_partners: Mapped[list[Sud]] = relationship(
        "Sud", foreign_keys=[merged_into_sud_id], viewonly=True
    )
    withdrawals: Mapped[list[Withdrawal]] = relationship(
        back_populates="sud", cascade="all, delete-orphan", order_by="Withdrawal.at"
    )


class WithdrawalKind(str, enum.Enum):
    KEG_FILL = "keg_fill"
    # Poured to customers — from Ausschank tanks in normal operation, and at
    # the Bergkirchweih directly from a fermentation tank near the Schänke
    # (confirmed 2026-08). Kept as its own kind: beer-tax reporting needs
    # poured volumes separable from keg fills.
    AUSSCHANK = "ausschank"


class Withdrawal(Base):
    """Volume leaving a tank without entering another one (issue #15) —
    keg fills for festival stands and secondary serving points."""

    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint("volume_hl > 0", name="ck_withdrawals_positive_volume"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sude.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tanks.id"), nullable=False, index=True
    )
    volume_hl: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[WithdrawalKind] = mapped_column(
        _enum(WithdrawalKind, 32),
        nullable=False,
        default=WithdrawalKind.KEG_FILL,
        server_default="keg_fill",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sud: Mapped[Sud] = relationship(back_populates="withdrawals")


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
    stage: Mapped[TankStage] = mapped_column(_enum(TankStage, 32), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Volume share of this allocation in hl. NULL = the full combined volume
    # of the occupying batch — the normal case before the Ausschank stage,
    # where batches can be split across tanks (issue #13).
    volume_hl: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    sud: Mapped[Sud] = relationship(back_populates="occupancies")
    tank: Mapped[Tank] = relationship(lazy="joined")
