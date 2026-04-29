"""Seed the database with the real tank inventory from ROADMAP.md §2.2.

Volumes are in hectoliters (1 hl = 100 l). Recipe durations are placeholders
flagged TBD in ROADMAP.md §2.7 — they MUST be confirmed with the brewmaster
before Phase 2 validation logic depends on them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    BeerStyle,
    Recipe,
    Sud,
    SudStatus,
    Tank,
    TankCellar,
    TankOccupancy,
    TankStage,
)

TANKS: list[dict] = [
    # Main cellar — fermentation (180 hl total)
    {"name": "F-30-1", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "F-30-2", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "F-30-3", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "F-30-4", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "F-30-5", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "F-15-1", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 15},
    {"name": "F-15-2", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 15},
    {"name": "F-OPEN-15", "cellar": TankCellar.MAIN, "stage": TankStage.FERMENTATION_OPEN, "capacity_hl": 15},
    # Main cellar — storage (150 hl total)
    {"name": "S-30-1", "cellar": TankCellar.MAIN, "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "S-30-2", "cellar": TankCellar.MAIN, "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "S-30-3", "cellar": TankCellar.MAIN, "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "S-30-4", "cellar": TankCellar.MAIN, "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "S-30-5", "cellar": TankCellar.MAIN, "stage": TankStage.STORAGE, "capacity_hl": 30},
    # Main cellar — Ausschank (350 hl total)
    {"name": "A-120", "cellar": TankCellar.MAIN, "stage": TankStage.AUSSCHANK, "capacity_hl": 120},
    {"name": "A-100", "cellar": TankCellar.MAIN, "stage": TankStage.AUSSCHANK, "capacity_hl": 100},
    {"name": "A-80", "cellar": TankCellar.MAIN, "stage": TankStage.AUSSCHANK, "capacity_hl": 80},
    {"name": "A-50", "cellar": TankCellar.MAIN, "stage": TankStage.AUSSCHANK, "capacity_hl": 50},
    # Secondary cellar
    {"name": "A2-35-1", "cellar": TankCellar.SECONDARY, "stage": TankStage.AUSSCHANK, "capacity_hl": 35},
    {"name": "A2-35-2", "cellar": TankCellar.SECONDARY, "stage": TankStage.AUSSCHANK, "capacity_hl": 35},
    {"name": "S2-10-1", "cellar": TankCellar.SECONDARY, "stage": TankStage.STORAGE, "capacity_hl": 10},
    {"name": "S2-10-2", "cellar": TankCellar.SECONDARY, "stage": TankStage.STORAGE, "capacity_hl": 10},
]

# Placeholder durations — TBD per ROADMAP.md §2.7. Wheat beer's 4-day open
# fermentation is the only firm number we have so far.
RECIPES: list[dict] = [
    {
        "beer_style": BeerStyle.KELLERBIER,
        "name": "Kellerbier (Standard)",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
    },
    {
        "beer_style": BeerStyle.WHEAT,
        "name": "Weizen (Standard)",
        "fermentation_duration_days": 7,
        "open_fermentation_required": True,
        "open_fermentation_duration_days": 4,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
    },
    {
        "beer_style": BeerStyle.FESTBIER,
        "name": "Festbier (Pfingsten)",
        "fermentation_duration_days": 8,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 28,
        "max_storage_duration_days": 70,
    },
    {
        "beer_style": BeerStyle.SPECIAL,
        "name": "Special #1",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
    },
]


def seed(session: Session) -> None:
    if session.scalar(select(Tank).limit(1)) is not None:
        print("Database already seeded — skipping.")
        return

    tanks = [Tank(**t) for t in TANKS]
    session.add_all(tanks)

    recipes = [Recipe(**r) for r in RECIPES]
    session.add_all(recipes)
    session.flush()

    by_style = {r.beer_style: r for r in recipes}
    by_tank = {t.name: t for t in tanks}

    today = date.today()
    midnight_utc = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

    # Sample plan that exercises the full pipeline so the Gantt isn't empty
    # on first launch. The numbers don't reflect real brewing schedules —
    # they're just plausible enough that the brewmaster can drag them around
    # to get a feel for the UX. style_year_number is 1 for each because each
    # is the first of its style in this brew_date's year. global_number is
    # left to the sud_global_seq default.
    kellerbier = Sud(
        recipe_id=by_style[BeerStyle.KELLERBIER].id,
        brew_date=today - timedelta(days=14),
        status=SudStatus.STORING,
        brewmaster="seed",
        style_year_number=1,
    )
    weizen = Sud(
        recipe_id=by_style[BeerStyle.WHEAT].id,
        brew_date=today - timedelta(days=7),
        status=SudStatus.FERMENTING,
        brewmaster="seed",
        style_year_number=1,
    )
    festbier = Sud(
        recipe_id=by_style[BeerStyle.FESTBIER].id,
        brew_date=today + timedelta(days=7),
        status=SudStatus.PLANNED,
        brewmaster="seed",
        style_year_number=1,
    )
    session.add_all([kellerbier, weizen, festbier])
    session.flush()

    occupancies = [
        # Kellerbier: finished fermenting, currently in storage.
        TankOccupancy(
            sud_id=kellerbier.id,
            tank_id=by_tank["F-30-1"].id,
            stage=TankStage.FERMENTATION_CLOSED,
            start_at=midnight_utc - timedelta(days=14),
            end_at=midnight_utc - timedelta(days=7),
        ),
        TankOccupancy(
            sud_id=kellerbier.id,
            tank_id=by_tank["S-30-1"].id,
            stage=TankStage.STORAGE,
            start_at=midnight_utc - timedelta(days=7),
            end_at=midnight_utc + timedelta(days=14),
        ),
        # Weizen: open ferm done, now in closed fermentation.
        TankOccupancy(
            sud_id=weizen.id,
            tank_id=by_tank["F-OPEN-15"].id,
            stage=TankStage.FERMENTATION_OPEN,
            start_at=midnight_utc - timedelta(days=7),
            end_at=midnight_utc - timedelta(days=3),
        ),
        TankOccupancy(
            sud_id=weizen.id,
            tank_id=by_tank["F-15-1"].id,
            stage=TankStage.FERMENTATION_CLOSED,
            start_at=midnight_utc - timedelta(days=3),
            end_at=midnight_utc + timedelta(days=4),
        ),
        # Festbier: planned ferm + storage in the future.
        TankOccupancy(
            sud_id=festbier.id,
            tank_id=by_tank["F-30-2"].id,
            stage=TankStage.FERMENTATION_CLOSED,
            start_at=midnight_utc + timedelta(days=7),
            end_at=midnight_utc + timedelta(days=15),
        ),
        TankOccupancy(
            sud_id=festbier.id,
            tank_id=by_tank["S-30-2"].id,
            stage=TankStage.STORAGE,
            start_at=midnight_utc + timedelta(days=15),
            end_at=midnight_utc + timedelta(days=43),
        ),
    ]
    session.add_all(occupancies)

    session.commit()
    sude = [kellerbier, weizen, festbier]
    print(
        f"Seeded: {len(tanks)} tanks, {len(recipes)} recipes, "
        f"{len(sude)} Süde, {len(occupancies)} tank occupancies."
    )


def main() -> None:
    with SessionLocal() as session:
        seed(session)


if __name__ == "__main__":
    main()
