import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Recipe, Sud, Tank, TankOccupancy, TankStage
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

    If `merge_into_sud_id` is provided, this Sud becomes a partner of that
    lead Sud (merged batch, issue #3): same recipe, brewed within 48 h,
    sharing the lead's tank — validated hard, no override.
    """
    recipe = session.get(Recipe, payload.recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recipe {payload.recipe_id} not found",
        )

    lead: Sud | None = None
    if payload.merge_into_sud_id is not None:
        lead = _validated_merge_lead(session, payload, recipe)

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
        merged_into_sud_id=lead.id if lead is not None else None,
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

    if sud.merged_into_sud_id is not None and payload.occupancies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This Sud is a partner in a merged batch and shares its lead's "
                "tank — schedule the lead Sud instead."
            ),
        )

    # A lead with merged partners must keep the combined batch volume inside
    # every tank it is being scheduled into — otherwise the POST-time merge
    # validation could be undone by a later reschedule.
    partner_volumes = list(
        session.scalars(
            select(Sud.volume_hl).where(Sud.merged_into_sud_id == sud.id)
        )
    )
    if partner_volumes and payload.occupancies:
        combined_hl = float(sud.volume_hl) + sum(float(v) for v in partner_volumes)
        tank_ids = {occ.tank_id for occ in payload.occupancies}
        tanks = {
            t.id: t
            for t in session.scalars(select(Tank).where(Tank.id.in_(tank_ids)))
        }
        for occ in payload.occupancies:
            tank = tanks.get(occ.tank_id)
            if tank is not None and combined_hl > float(tank.capacity_hl):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"This Sud leads a merged batch of {combined_hl:g} hl, "
                        f"which exceeds the {float(tank.capacity_hl):g} hl "
                        f"capacity of tank {tank.name}."
                    ),
                )

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


MERGE_MAX_BREW_GAP = timedelta(days=2)


def _validated_merge_lead(session: Session, payload: SudCreateIn, recipe: Recipe) -> Sud:
    """Hard-block validation for creating a merged-batch partner (issue #3).

    Rules confirmed 2026-08: same recipe, brewed within 48 h, merged into
    one tank. The partner never carries occupancies; the combined volume of
    lead + partners must fit every tank the lead occupies.
    """
    if payload.initial_occupancy is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A merged-batch partner shares its lead's tank — "
                "initial_occupancy and merge_into_sud_id are mutually exclusive."
            ),
        )

    lead = session.scalar(
        select(Sud)
        .options(selectinload(Sud.occupancies), selectinload(Sud.merged_partners))
        .where(Sud.id == payload.merge_into_sud_id)
    )
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead Sud {payload.merge_into_sud_id} not found",
        )
    if lead.merged_into_sud_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The chosen Sud is itself a partner in a merged batch — "
                "merge into its lead instead."
            ),
        )
    if lead.recipe_id != payload.recipe_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Merged batches must share the same recipe "
                f"(lead uses '{lead.recipe.name}' v{lead.recipe.version})."
            ),
        )

    gap = abs(payload.brew_date - lead.brew_date)
    if gap > MERGE_MAX_BREW_GAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Merged batches must be brewed within 48 h of each other "
                f"(2 calendar days) — the gap to the lead's brew date is "
                f"{gap.days} days."
            ),
        )

    combined_hl = (
        float(lead.volume_hl)
        + sum(float(p.volume_hl) for p in lead.merged_partners)
        + 15.0  # the new partner; standard Sud volume, ROADMAP §2.1
    )

    # Conservative by design (hard-block philosophy): every tank the lead is
    # or was booked into must fit the combined volume — a false rejection on
    # stale history beats silently recording an impossible batch.
    for occ in lead.occupancies:
        capacity = float(occ.tank.capacity_hl)
        if combined_hl > capacity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Combined batch volume of {combined_hl:g} hl exceeds the "
                    f"{capacity:g} hl capacity of tank {occ.tank.name}."
                ),
            )

    # An unscheduled lead has no occupancies to check against, so cap the
    # combined volume at the largest active fermentation tank — the merge
    # physically happens in the fermenter (issue #3: "in einem 30-hl-Tank
    # zusammengeführt"), so a batch bigger than every fermenter can never
    # exist regardless of later scheduling.
    largest_ferm_hl = float(
        session.scalar(
            select(func.max(Tank.capacity_hl)).where(
                Tank.active,
                Tank.stage.in_(
                    (TankStage.FERMENTATION_OPEN, TankStage.FERMENTATION_CLOSED)
                ),
            )
        )
        or 0
    )
    if combined_hl > largest_ferm_hl:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Combined batch volume of {combined_hl:g} hl exceeds the "
                f"largest fermentation tank ({largest_ferm_hl:g} hl) — no "
                "fermenter could ever hold this merged batch."
            ),
        )
    return lead


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
