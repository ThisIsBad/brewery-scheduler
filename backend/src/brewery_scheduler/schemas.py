"""Pydantic response/request schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .models import BeerStyle, SudStatus, TankCellar, TankStage


class OccupancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sud_id: uuid.UUID
    tank_id: uuid.UUID
    stage: TankStage
    start_at: datetime
    end_at: datetime | None


class TankOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    cellar: TankCellar
    stage: TankStage
    capacity_hl: float
    active: bool


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


class SudOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipe_id: uuid.UUID
    recipe: RecipeOut
    brew_date: date
    status: SudStatus
    notes: str | None
    brewmaster: str | None
    style_year_number: int
    occupancies: list[OccupancyOut] = []


class ScheduleOccupancyIn(BaseModel):
    tank_id: uuid.UUID
    stage: TankStage
    start_at: datetime
    end_at: datetime | None = None


class ScheduleIn(BaseModel):
    """Request body for PUT /api/sude/{id}/schedule.

    Phase 1: replaces the Sud's full set of tank occupancies. No validation.
    """

    occupancies: list[ScheduleOccupancyIn]
