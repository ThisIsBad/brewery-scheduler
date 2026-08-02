import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Recipe, Sud, TankOccupancy, TankStage
from ..schemas import ScheduleIn, SudCreateIn, SudOut

router = APIRouter(prefix="/api/sude", tags=["sude"])


@router.get("", response_model=list[SudOut])
def list_sude(session: Session = Depends(get_session)) -> list[Sud]:
    stmt = (
        select(Sud)
        .options(selectinload(Sud.occupancies))
        .order_by(Sud.brew_date)
    )
    return list(session.scalars(stmt))


@router.post("", response_model=SudOut, status_code=status.HTTP_201_CREATED)
def create_sud(payload: SudCreateIn, session: Session = Depends(get_session)) -> Sud:
    """Create a Sud. The server picks the next style_year_number for the
    recipe's beer_style and the brew_date's year; global_number flows from
    the sud_global_seq sequence default.

    If `initial_occupancy` is provided, its `end_at` defaults to
    `start_at + recipe.{open_,}fermentation_duration_days` when omitted —
    saves the brewmaster typing the duration twice.
    """
    recipe = session.get(Recipe, payload.recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe {payload.recipe_id} not found",
        )

    brew_year = payload.brew_date.year
    next_style_year_number = (
        session.scalar(
            select(func.coalesce(func.max(Sud.style_year_number), 0))
            .join(Recipe, Recipe.id == Sud.recipe_id)
            .where(Recipe.beer_style == recipe.beer_style)
            .where(extract("year", Sud.brew_date) == brew_year)
        )
        + 1
    )

    sud = Sud(
        recipe_id=recipe.id,
        brew_date=payload.brew_date,
        notes=payload.notes,
        brewmaster=payload.brewmaster,
        style_year_number=next_style_year_number,
    )
    session.add(sud)
    session.flush()

    if payload.initial_occupancy is not None:
        occ = payload.initial_occupancy
        end_at = occ.end_at
        if end_at is None:
            duration_days = _default_duration_days(recipe, occ.stage)
            end_at = occ.start_at + timedelta(days=float(duration_days))
        sud.occupancies.append(
            TankOccupancy(
                tank_id=occ.tank_id,
                stage=occ.stage,
                start_at=occ.start_at,
                end_at=end_at,
            )
        )

    session.commit()
    session.refresh(sud)
    return sud


@router.put("/{sud_id}/schedule", response_model=SudOut)
def update_schedule(
    sud_id: uuid.UUID,
    payload: ScheduleIn,
    session: Session = Depends(get_session),
) -> Sud:
    """Replace a Sud's tank occupancies wholesale.

    Phase 1: no application validation. The database still rejects overlapping
    occupancies on the same tank (EXCLUDE constraint from migration 0001) — that's
    intentional defense-in-depth, not Phase 2 work leaking in.
    """
    sud = session.scalar(
        select(Sud).options(selectinload(Sud.occupancies)).where(Sud.id == sud_id)
    )
    if sud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sud not found")

    sud.occupancies.clear()
    session.flush()

    for occ in payload.occupancies:
        sud.occupancies.append(
            TankOccupancy(
                tank_id=occ.tank_id,
                stage=occ.stage,
                start_at=occ.start_at,
                end_at=occ.end_at,
            )
        )

    session.commit()
    session.refresh(sud)
    return sud


def _default_duration_days(recipe: Recipe, stage: TankStage) -> float:
    if stage == TankStage.FERMENTATION_OPEN:
        if recipe.open_fermentation_duration_days is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Recipe '{recipe.name}' has no open_fermentation_duration_days "
                    "but the initial occupancy is fermentation_open."
                ),
            )
        return float(recipe.open_fermentation_duration_days)
    if stage == TankStage.FERMENTATION_CLOSED:
        return float(recipe.fermentation_duration_days)
    if stage == TankStage.STORAGE:
        return float(recipe.storage_duration_days)
    # ausschank: no recipe-derived default; require explicit end_at.
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"end_at is required for stage {stage.value}",
    )
