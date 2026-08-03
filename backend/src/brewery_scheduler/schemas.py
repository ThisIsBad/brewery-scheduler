"""Pydantic response/request schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import BeerStyle, SudStatus, TankStage, WithdrawalKind


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    position: int


class LocationCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class LocationUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class OccupancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sud_id: uuid.UUID
    tank_id: uuid.UUID
    stage: TankStage
    start_at: datetime
    end_at: datetime | None
    volume_hl: float | None


class TankOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location_id: uuid.UUID
    stage: TankStage
    capacity_hl: float
    active: bool
    locked: bool


class TankCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    location_id: uuid.UUID
    stage: TankStage
    capacity_hl: float = Field(gt=0)


class TankUpdateIn(BaseModel):
    """Partial update; omitted fields stay untouched. Guards live in the
    endpoint: stage and capacity only change when no running or planned
    occupancy contradicts them."""

    name: str | None = Field(default=None, min_length=1, max_length=32)
    location_id: uuid.UUID | None = None
    stage: TankStage | None = None
    capacity_hl: float | None = Field(default=None, gt=0)
    active: bool | None = None
    locked: bool | None = None


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    beer_style: BeerStyle
    version: int
    name: str
    fermentation_duration_days: float
    open_fermentation_required: bool
    open_fermentation_duration_days: float | None
    storage_duration_days: float
    max_storage_duration_days: float


class WithdrawalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sud_id: uuid.UUID
    tank_id: uuid.UUID
    volume_hl: float
    at: datetime
    kind: WithdrawalKind
    notes: str | None


class SudOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipe_id: uuid.UUID
    recipe: RecipeOut
    brew_at: datetime
    brew_date: date
    status: SudStatus
    notes: str | None
    brewmaster: str | None
    style_year_number: int
    volume_hl: float
    merged_into_sud_id: uuid.UUID | None
    occupancies: list[OccupancyOut] = []
    withdrawals: list[WithdrawalOut] = []
    # Non-blocking process hints (e.g. "active yeast entering Ausschank").
    # Mutating endpoints fill this; it is never persisted.
    warnings: list[str] = []


class ScheduleOccupancyIn(BaseModel):
    tank_id: uuid.UUID
    stage: TankStage
    start_at: datetime
    end_at: datetime | None = None
    volume_hl: float | None = Field(default=None, gt=0)


class ScheduleIn(BaseModel):
    """Request body for PUT /api/sude/{id}/schedule.

    Phase 1: replaces the Sud's full set of tank occupancies. No validation.
    """

    occupancies: list[ScheduleOccupancyIn]


class SudCreateIn(BaseModel):
    """Request body for POST /api/sude.

    The brewmaster supplies the recipe and brew date; the server computes
    style_year_number and global_number. The initial occupancy is optional
    so a Sud can be created and parked in "Ungeplant" until the brewmaster
    decides which fermentation tank it goes into.
    """

    recipe_id: uuid.UUID
    # The brew moment with time — several Sude share a brew day. The server
    # derives brew_date (numbering bucket) from this timestamp's date part.
    brew_at: datetime
    notes: str | None = Field(default=None, max_length=10_000)
    brewmaster: str | None = Field(default=None, max_length=128)
    initial_occupancy: ScheduleOccupancyIn | None = None

    # Merged batches (issue #3): pass the lead Sud's id to create this Sud
    # as its partner — same recipe, brewed within 48 h, sharing the lead's
    # tank. Mutually exclusive with initial_occupancy: partners never carry
    # occupancies of their own.
    merge_into_sud_id: uuid.UUID | None = None


class WithdrawIn(BaseModel):
    """Request body for POST /api/sude/{id}/withdraw.

    Covers both movement kinds that take volume out of a tank without a
    transfer: keg fills (Fassabfüllung) and pours to customers (Ausschank,
    beer-tax relevant). The client supplies `at` so offline-queued
    withdrawals keep their real timestamp when replayed after reconnect.
    """

    tank_id: uuid.UUID
    volume_hl: float = Field(gt=0)
    at: datetime
    kind: WithdrawalKind = WithdrawalKind.KEG_FILL
    notes: str | None = Field(default=None, max_length=10_000)


class TransferAllocationIn(BaseModel):
    tank_id: uuid.UUID
    # Required when splitting across several Ausschank tanks; omitted for a
    # whole-batch move (the server uses the combined batch volume).
    volume_hl: float | None = Field(default=None, gt=0)


class TransferIn(BaseModel):
    """Request body for POST /api/sude/{id}/transfer (Umdrücken).

    Moves the batch (lead + merged partners) to any other tank — the usual
    Gärtank → Lagertank → Ausschank order is convention, not a constraint.
    A single target tank outside the Ausschank stage, one or more targets
    with explicit volume shares at the Ausschank stage (issue #13).
    """

    start_at: datetime
    end_at: datetime | None = None
    allocations: list[TransferAllocationIn] = Field(min_length=1)
