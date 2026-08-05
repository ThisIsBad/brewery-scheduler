"""Pydantic response/request schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import SudStatus, TankStage, WithdrawalKind


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


class MalzIn(BaseModel):
    """One grain-bill line; kg per 15-hl standard Sud (decided 2026-08-04).
    The maltster (BM, Weyermann, Steinbach …) rides along as on the paper
    brew sheet."""

    name: str = Field(min_length=1, max_length=128)
    kg: float = Field(gt=0)
    maelzerei: str | None = Field(default=None, max_length=128)


class HopfengabeIn(BaseModel):
    """One hop addition; grams per 15-hl Sud. Timing is free text exactly
    as on the brew sheet — „Kochbeginn", „nach 55 min", „Vorderwürze",
    „Whirlpool", „Kalthopfung 2 Tage nach Gärbeginn" (Bierrezepte.xlsx,
    2026-08-04). Alpha acid rides along for bitterness math later."""

    name: str = Field(min_length=1, max_length=128)
    gramm: float = Field(gt=0)
    zeitpunkt: str = Field(min_length=1, max_length=128)
    alpha_prozent: float | None = Field(default=None, ge=0)


class MaischrastIn(BaseModel):
    """One mash step (Einmaischen, Rast, Abmaischen …): target temperature
    and how long it is held. Heating ramps carry no duration."""

    schritt: str = Field(min_length=1, max_length=64)
    temp_c: float | None = Field(default=None, gt=0)
    dauer_min: float | None = Field(default=None, gt=0)


class WasserIn(BaseModel):
    """Brewing water in hl: the Hauptguss plus the Nachgüsse in order."""

    hauptguss_hl: float | None = Field(default=None, gt=0)
    nachguss_hl: list[float] = []


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    beer_style: str
    version: int
    name: str
    active: bool = True
    farbe: str | None = None
    fermentation_duration_days: float
    open_fermentation_required: bool
    open_fermentation_duration_days: float | None
    storage_duration_days: float
    max_storage_duration_days: float
    created_at: datetime
    created_by: str | None
    notes: str | None
    malts: list[MalzIn] = []
    hop_gaben: list[HopfengabeIn] = []
    maischplan: list[MaischrastIn] = []
    wasser: WasserIn | None = None
    yeast: str | None = None
    original_gravity_plato: float | None = None
    ibu: float | None = None
    color_ebc: float | None = None
    kochzeit_min: float | None = None
    karbonisierung_g_l: float | None = None
    anstellhinweis: str | None = None


class RecipeCreateIn(BaseModel):
    """Request body for POST /api/recipes.

    Recipes are versioned and immutable: this always creates a NEW version
    for the beer style (server assigns max(version)+1). Already-scheduled
    Sude keep their original recipe link (decided 2026-08, issue #4).
    """

    beer_style: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    fermentation_duration_days: float = Field(gt=0)
    open_fermentation_required: bool = False
    open_fermentation_duration_days: float | None = Field(default=None, gt=0)
    storage_duration_days: float = Field(gt=0)
    max_storage_duration_days: float = Field(gt=0)
    notes: str | None = Field(default=None, max_length=10_000)
    created_by: str | None = Field(default=None, max_length=128)
    malts: list[MalzIn] = []
    hop_gaben: list[HopfengabeIn] = []
    maischplan: list[MaischrastIn] = []
    wasser: WasserIn | None = None
    yeast: str | None = Field(default=None, max_length=128)
    original_gravity_plato: float | None = Field(default=None, gt=0)
    ibu: float | None = Field(default=None, ge=0)
    color_ebc: float | None = Field(default=None, ge=0)
    kochzeit_min: float | None = Field(default=None, gt=0)
    karbonisierung_g_l: float | None = Field(default=None, gt=0)
    anstellhinweis: str | None = Field(default=None, max_length=256)


class RecipeStyleActiveIn(BaseModel):
    """Archive or reactivate a beer — applies to all versions of the
    style. Archived beers move to „Frühere Biere" and take no new Sude."""

    beer_style: str = Field(min_length=1, max_length=64)
    active: bool


class RecipeStyleFarbeIn(BaseModel):
    """Display color of a beer (hex), style-wide like the archive flag —
    paints the Sude in the Zeitplan."""

    beer_style: str = Field(min_length=1, max_length=64)
    farbe: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class RecipeOverridesIn(BaseModel):
    """Per-Sud deviations from the recipe (Phase 3): stored on the Sud,
    never touching the recipe table. Only duration fields are overridable —
    they drive the derived end dates and the process warnings."""

    fermentation_duration_days: float | None = Field(default=None, gt=0)
    storage_duration_days: float | None = Field(default=None, gt=0)
    open_fermentation_duration_days: float | None = Field(default=None, gt=0)


class KegCountIn(BaseModel):
    """Barrels of one size in a keg fill; the hl volume is computed as
    size_l x count / 100 (decided 2026-08-04)."""

    size_l: float = Field(gt=0)
    count: int = Field(gt=0)


class WithdrawalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sud_id: uuid.UUID
    tank_id: uuid.UUID
    volume_hl: float
    at: datetime
    kind: WithdrawalKind
    keg_counts: list[KegCountIn] | None = None
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
    recipe_overrides: dict | None = None
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
    # Per-Sud deviations from the recipe (Phase 3) — recorded on the Sud,
    # used for derived end dates and process warnings.
    recipe_overrides: RecipeOverridesIn | None = None

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
    # Either a direct volume OR keg counts (keg fills only) — the server
    # computes the volume from the counts when they are given.
    volume_hl: float | None = Field(default=None, gt=0)
    kegs: list[KegCountIn] | None = None
    at: datetime
    kind: WithdrawalKind = WithdrawalKind.KEG_FILL
    notes: str | None = Field(default=None, max_length=10_000)


class TankWithdrawIn(BaseModel):
    """Tank-level Ausschank booking (Blending, 2026-08-04): the volume —
    direct or as keg counts — leaves the TANK; the server distributes it
    proportionally across the contained Sud shares."""

    volume_hl: float | None = Field(default=None, gt=0)
    kegs: list[KegCountIn] | None = None
    at: datetime
    kind: WithdrawalKind = WithdrawalKind.KEG_FILL
    notes: str | None = Field(default=None, max_length=10_000)


class TransferAllocationIn(BaseModel):
    tank_id: uuid.UUID
    # Required when splitting across several tanks; omitted for a
    # whole-batch move (the server uses the combined batch volume).
    volume_hl: float | None = Field(default=None, gt=0)


class TransferIn(BaseModel):
    """Request body for POST /api/sude/{id}/transfer (Umdrücken).

    Moves beer to any other tank — the usual Gärtank → Lagertank →
    Ausschank order is convention, not a constraint. One or more same-stage
    targets; several targets carry explicit volume shares (splitting is
    allowed at every stage since 2026-08-04).
    """

    start_at: datetime
    end_at: datetime | None = None
    # The tank the beer is pushed out of. Scopes the transfer to that
    # tank's share when the batch is split across tanks — without it the
    # whole batch moves (pre-split behaviour, kept for older clients).
    from_tank_id: uuid.UUID | None = None
    allocations: list[TransferAllocationIn] = Field(min_length=1)
