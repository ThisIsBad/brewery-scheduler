import uuid
from datetime import timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import (
    Recipe,
    Sud,
    SudStatus,
    Tank,
    TankOccupancy,
    TankStage,
    Withdrawal,
)
from ..schemas import ScheduleIn, SudCreateIn, SudOut, TransferIn, WithdrawIn

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
        beer_style=recipe.beer_style,
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

        tank = session.get(Tank, occ.tank_id)
        if tank is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tank {occ.tank_id} not found",
            )
        planned = [
            SimpleNamespace(stage=occ.stage, start_at=occ.start_at, end_at=end_at)
        ]
        _rule_wheat_open_fermentation(recipe, planned)
        _rule_yeast_free_ausschank(recipe, planned)
        if occ.stage != TankStage.AUSSCHANK and float(sud.volume_hl) > float(
            tank.capacity_hl
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Batch volume of {float(sud.volume_hl):g} hl exceeds the "
                    f"{float(tank.capacity_hl):g} hl capacity of tank {tank.name}."
                ),
            )

        sud.occupancies.append(
            TankOccupancy(
                tank_id=occ.tank_id,
                stage=occ.stage,
                start_at=occ.start_at,
                end_at=end_at,
                volume_hl=occ.volume_hl,
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

    partner_volumes = list(
        session.scalars(
            select(Sud.volume_hl).where(Sud.merged_into_sud_id == sud.id)
        )
    )
    combined_hl = float(sud.volume_hl) + sum(float(v) for v in partner_volumes)

    if payload.occupancies:
        tank_ids = {occ.tank_id for occ in payload.occupancies}
        tanks = {
            t.id: t
            for t in session.scalars(select(Tank).where(Tank.id.in_(tank_ids)))
        }
        for occ in payload.occupancies:
            tank = tanks.get(occ.tank_id)
            if tank is None:
                continue
            # Batch volume (lead + merged partners) must fit every
            # non-Ausschank tank in the new schedule.
            if (
                occ.stage != TankStage.AUSSCHANK
                and combined_hl > float(tank.capacity_hl)
            ):
                described = (
                    f"This Sud leads a merged batch of {combined_hl:g} hl"
                    if partner_volumes
                    else f"Batch volume of {combined_hl:g} hl"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"{described}, which exceeds the "
                        f"{float(tank.capacity_hl):g} hl capacity of tank "
                        f"{tank.name}."
                    ),
                )
            # Ausschank tanks blend batches; the DB EXCLUDE constraint is
            # scoped away from that stage, so the headroom rule applies here
            # exactly as in the transfer endpoint.
            if occ.stage == TankStage.AUSSCHANK:
                _check_ausschank_headroom(
                    session,
                    tank,
                    float(occ.volume_hl) if occ.volume_hl is not None else combined_hl,
                    occ.start_at,
                    occ.end_at,
                    exclude_sud_id=sud.id,
                )

        _rule_stage_order(payload.occupancies)
        _rule_wheat_open_fermentation(sud.recipe, payload.occupancies)
        _rule_yeast_free_ausschank(sud.recipe, payload.occupancies)

    sud.occupancies.clear()
    session.flush()

    for occ in payload.occupancies:
        sud.occupancies.append(
            TankOccupancy(
                tank_id=occ.tank_id,
                stage=occ.stage,
                start_at=occ.start_at,
                end_at=occ.end_at,
                volume_hl=occ.volume_hl,
            )
        )

    session.commit()
    session.refresh(sud)
    return sud


STAGE_ORDER: dict[TankStage, int] = {
    TankStage.FERMENTATION_OPEN: 0,
    TankStage.FERMENTATION_CLOSED: 1,
    TankStage.STORAGE: 2,
    TankStage.AUSSCHANK: 3,
}

STAGE_TO_STATUS: dict[TankStage, SudStatus] = {
    TankStage.FERMENTATION_OPEN: SudStatus.FERMENTING,
    TankStage.FERMENTATION_CLOSED: SudStatus.FERMENTING,
    TankStage.STORAGE: SudStatus.STORING,
    TankStage.AUSSCHANK: SudStatus.IN_AUSSCHANK,
}


@router.post("/{sud_id}/transfer", response_model=SudOut)
def transfer_sud(
    sud_id: uuid.UUID,
    payload: TransferIn,
    session: Session = Depends(get_session),
) -> Sud:
    """Umdrücken: move the batch (lead + merged partners) to its next stage.

    Before the Ausschank stage the batch stays together (exactly one target
    tank). At the Ausschank stage it can be split across several tanks with
    explicit volume shares, and Ausschank tanks may blend several batches —
    guarded by the sum-of-allocations ≤ capacity rule (issue #13).
    """
    sud = session.scalar(
        select(Sud).options(selectinload(Sud.occupancies)).where(Sud.id == sud_id)
    )
    if sud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sud not found")
    if sud.merged_into_sud_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This Sud is a partner in a merged batch and shares its lead's "
                "tank — transfer the lead Sud instead."
            ),
        )
    if not sud.occupancies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This Sud has no tank occupancy yet — schedule it before transferring.",
        )

    current = max(sud.occupancies, key=lambda o: o.start_at)
    # Stage columns are plain String(32); coerce so enum comparisons and
    # .value in messages behave regardless of how the row was loaded.
    current_stage = TankStage(current.stage)
    current_rank = STAGE_ORDER[current_stage]

    tank_ids = [a.tank_id for a in payload.allocations]
    if len(set(tank_ids)) != len(tank_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duplicate target tank in allocations.",
        )
    tanks = {
        t.id: t for t in session.scalars(select(Tank).where(Tank.id.in_(tank_ids)))
    }
    missing = [str(tid) for tid in tank_ids if tid not in tanks]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target tank(s) not found: {', '.join(missing)}",
        )

    target_stages = {TankStage(tanks[tid].stage) for tid in tank_ids}
    if len(target_stages) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All target tanks must belong to the same stage.",
        )
    target_stage = target_stages.pop()
    if STAGE_ORDER[target_stage] <= current_rank:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"A Sud only moves forward in the pipeline — it is currently in "
                f"{current_stage.value} and cannot transfer to {target_stage.value}."
            ),
        )

    partner_volumes = list(
        session.scalars(select(Sud.volume_hl).where(Sud.merged_into_sud_id == sud.id))
    )
    combined_hl = float(sud.volume_hl) + sum(float(v) for v in partner_volumes)

    if target_stage != TankStage.AUSSCHANK:
        if len(payload.allocations) != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Batches stay together before the Ausschank stage — "
                    "exactly one target tank is allowed."
                ),
            )
        target = tanks[tank_ids[0]]
        if combined_hl > float(target.capacity_hl):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Batch volume of {combined_hl:g} hl exceeds the "
                    f"{float(target.capacity_hl):g} hl capacity of tank {target.name}."
                ),
            )
        volumes: list[float | None] = [None]
    else:
        volumes = [
            a.volume_hl if a.volume_hl is not None else combined_hl
            for a in payload.allocations
        ]
        total = sum(volumes)
        if abs(total - combined_hl) > 0.01:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Allocated volumes sum to {total:g} hl but the batch "
                    f"holds {combined_hl:g} hl."
                ),
            )
        for allocation, volume in zip(payload.allocations, volumes):
            tank = tanks[allocation.tank_id]
            _check_ausschank_headroom(
                session,
                tank,
                volume,
                payload.start_at,
                payload.end_at,
                exclude_sud_id=sud.id,
            )

    end_at = payload.end_at
    if end_at is None and target_stage != TankStage.AUSSCHANK:
        duration_days = _default_duration_days(sud.recipe, target_stage)
        end_at = payload.start_at + timedelta(days=duration_days)

    # The beer physically leaves its current tank at the transfer start, so
    # every occupancy still running at that moment — open-ended OR with a
    # planned future end — is truncated to it. Without this, an early
    # transfer left the batch nominally in two tanks at once: the stale
    # occupancy blocked the old tank, misdirected keg withdrawals, and made
    # the wheat rule reject legitimate open→closed moves.
    def effective_end(o: TankOccupancy):
        if o.end_at is None or o.end_at > payload.start_at:
            return payload.start_at
        return o.end_at

    for occ in sud.occupancies:
        if (
            occ.end_at is None or occ.end_at > payload.start_at
        ) and payload.start_at <= occ.start_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Transfer starts before an existing occupancy begins — "
                    "adjust the plan first."
                ),
            )

    # Evaluate the pipeline rules against the future picture: the existing
    # occupancies as they will look after truncation, plus the new
    # allocations.
    future = [
        SimpleNamespace(stage=o.stage, start_at=o.start_at, end_at=effective_end(o))
        for o in sud.occupancies
    ] + [
        SimpleNamespace(stage=target_stage, start_at=payload.start_at, end_at=end_at)
    ]
    _rule_wheat_open_fermentation(sud.recipe, future)
    _rule_yeast_free_ausschank(sud.recipe, future)

    for occ in sud.occupancies:
        if occ.end_at is None or occ.end_at > payload.start_at:
            occ.end_at = payload.start_at

    for allocation, volume in zip(payload.allocations, volumes):
        sud.occupancies.append(
            TankOccupancy(
                tank_id=allocation.tank_id,
                stage=target_stage,
                start_at=payload.start_at,
                end_at=end_at,
                volume_hl=volume,
            )
        )

    new_status = STAGE_TO_STATUS[target_stage]
    sud.status = new_status
    for partner in session.scalars(
        select(Sud).where(Sud.merged_into_sud_id == sud.id)
    ):
        partner.status = new_status

    session.commit()
    session.refresh(sud)
    return sud


@router.post("/{sud_id}/withdraw", response_model=SudOut)
def withdraw(
    sud_id: uuid.UUID,
    payload: WithdrawIn,
    session: Session = Depends(get_session),
) -> Sud:
    """Fassabfüllung: volume leaves a tank into kegs (issue #15).

    Validated hard: the Sud must actually occupy the tank at the given
    time, and the withdrawn volume must not exceed what is left of this
    batch's allocation in that tank.
    """
    sud = session.scalar(
        select(Sud)
        .options(selectinload(Sud.occupancies), selectinload(Sud.withdrawals))
        .where(Sud.id == sud_id)
    )
    if sud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sud not found")
    if sud.merged_into_sud_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This Sud is a partner in a merged batch and shares its lead's "
                "tank — withdraw from the lead Sud instead."
            ),
        )

    occupancy = next(
        (
            o
            for o in sud.occupancies
            if o.tank_id == payload.tank_id
            and o.start_at <= payload.at
            and (o.end_at is None or payload.at < o.end_at)
        ),
        None,
    )
    if occupancy is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This Sud does not occupy that tank at the given time.",
        )

    partner_volumes = list(
        session.scalars(select(Sud.volume_hl).where(Sud.merged_into_sud_id == sud.id))
    )
    combined_hl = float(sud.volume_hl) + sum(float(v) for v in partner_volumes)
    allocation_hl = (
        float(occupancy.volume_hl) if occupancy.volume_hl is not None else combined_hl
    )
    already_withdrawn = sum(
        float(w.volume_hl) for w in sud.withdrawals if w.tank_id == payload.tank_id
    )
    remaining_hl = allocation_hl - already_withdrawn
    if payload.volume_hl > remaining_hl + 1e-9:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only {remaining_hl:g} hl of this batch remain in the tank — "
                f"cannot withdraw {payload.volume_hl:g} hl."
            ),
        )

    sud.withdrawals.append(
        Withdrawal(
            tank_id=payload.tank_id,
            volume_hl=payload.volume_hl,
            at=payload.at,
            notes=payload.notes,
        )
    )
    session.commit()
    session.refresh(sud)
    return sud


def _check_ausschank_headroom(
    session: Session,
    tank: Tank,
    volume_hl: float,
    start_at,
    end_at,
    exclude_sud_id: uuid.UUID | None = None,
) -> None:
    """Ausschank tanks blend several batches; the DB EXCLUDE constraint is
    scoped away from this stage, so the capacity rule lives here: the sum of
    time-overlapping allocations plus the new one must fit the tank.
    """
    stmt = (
        select(TankOccupancy)
        .options(selectinload(TankOccupancy.sud))
        .where(
            TankOccupancy.tank_id == tank.id,
            TankOccupancy.end_at.is_(None) | (TankOccupancy.end_at > start_at),
        )
    )
    if end_at is not None:
        stmt = stmt.where(TankOccupancy.start_at < end_at)
    if exclude_sud_id is not None:
        stmt = stmt.where(TankOccupancy.sud_id != exclude_sud_id)

    allocated = 0.0
    for occ in session.scalars(stmt):
        if occ.volume_hl is not None:
            allocated += float(occ.volume_hl)
        else:
            partner_volumes = session.scalars(
                select(Sud.volume_hl).where(Sud.merged_into_sud_id == occ.sud_id)
            )
            allocated += float(occ.sud.volume_hl) + sum(
                float(v) for v in partner_volumes
            )

    if allocated + volume_hl > float(tank.capacity_hl):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Tank {tank.name} holds {allocated:g} hl in this window — "
                f"adding {volume_hl:g} hl exceeds its "
                f"{float(tank.capacity_hl):g} hl capacity."
            ),
        )


def _rule_stage_order(occs) -> None:
    """§2.4 rule 4: a Sud only moves forward through the pipeline."""
    ordered = sorted(occs, key=lambda o: o.start_at)
    ranks = [STAGE_ORDER[TankStage(o.stage)] for o in ordered]
    if any(later < earlier for earlier, later in zip(ranks, ranks[1:])):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A Sud only moves forward in the pipeline — the occupancies "
                "regress to an earlier stage over time."
            ),
        )


def _rule_wheat_open_fermentation(recipe: Recipe, occs) -> None:
    """§2.4 rule 3: wheat beer must spend its open-fermentation days in the
    open fermentation tank before entering a closed fermenter."""
    if not recipe.open_fermentation_required:
        return
    required = timedelta(days=float(recipe.open_fermentation_duration_days or 4))
    opens = [o for o in occs if TankStage(o.stage) == TankStage.FERMENTATION_OPEN]
    for closed in occs:
        if TankStage(closed.stage) != TankStage.FERMENTATION_CLOSED:
            continue
        satisfied = any(
            o.end_at is not None
            and o.end_at <= closed.start_at
            and (o.end_at - o.start_at) >= required
            for o in opens
        )
        if not satisfied:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"'{recipe.name}' requires {required.days} days in the open "
                    "fermentation tank before entering a closed fermenter."
                ),
            )


def _rule_yeast_free_ausschank(recipe: Recipe, occs) -> None:
    """§2.4 rule 2: no beer with active yeast enters an Ausschank tank —
    approximated as: a completed closed fermentation of at least the
    recipe's fermentation duration must precede the Ausschank start."""
    ferm = timedelta(days=float(recipe.fermentation_duration_days))
    closed = [o for o in occs if TankStage(o.stage) == TankStage.FERMENTATION_CLOSED]
    for a in occs:
        if TankStage(a.stage) != TankStage.AUSSCHANK:
            continue
        satisfied = any(
            c.end_at is not None
            and c.end_at <= a.start_at
            and (c.end_at - c.start_at) >= ferm
            for c in closed
        )
        if not satisfied:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Beer may not enter an Ausschank tank with active yeast — "
                    f"'{recipe.name}' needs a completed closed fermentation of "
                    f"at least {ferm.days} days before the Ausschank start."
                ),
            )


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
