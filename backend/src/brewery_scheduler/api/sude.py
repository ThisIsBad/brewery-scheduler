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
    WithdrawalKind,
)
from ..schemas import (
    ScheduleIn,
    SudCreateIn,
    SudOut,
    TankWithdrawIn,
    TransferIn,
    WithdrawIn,
)

router = APIRouter(prefix="/api/sude", tags=["sude"])


@router.get("", response_model=list[SudOut])
def list_sude(session: Session = Depends(get_session)) -> list[SudOut]:
    """List all Sude, each with its current process warnings.

    Warnings are evaluated on read (not only after mutations) so the
    Kellerblick can mark deviating Sude — e.g. beer sitting in an
    Ausschank tank without a completed fermentation stays flagged.
    """
    stmt = (
        select(Sud)
        .options(selectinload(Sud.occupancies))
        .order_by(Sud.brew_date)
    )
    return [
        _with_warnings(
            sud,
            _process_warnings(
                _effective_recipe(sud.recipe, sud.recipe_overrides), sud.occupancies
            ),
        )
        for sud in session.scalars(stmt)
    ]


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

    warnings: list[str] = []
    overrides = (
        payload.recipe_overrides.model_dump(exclude_none=True)
        if payload.recipe_overrides
        else None
    ) or None
    effective = _effective_recipe(recipe, overrides)

    # The numbering bucket is the brew day as sent by the client (its
    # wall-clock date is encoded in the timestamp's offset).
    brew_date = payload.brew_at.date()
    brew_year = brew_date.year
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
        brew_at=payload.brew_at,
        brew_date=brew_date,
        notes=payload.notes,
        brewmaster=payload.brewmaster,
        style_year_number=next_style_year_number,
        beer_style=recipe.beer_style,
        merged_into_sud_id=lead.id if lead is not None else None,
        recipe_overrides=overrides,
    )
    session.add(sud)
    session.flush()

    if payload.initial_occupancy is not None:
        occ = payload.initial_occupancy
        end_at = occ.end_at
        if end_at is None:
            duration_days = _default_duration_days(effective, occ.stage)
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
        warnings += _process_warnings(effective, planned)
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
    return _with_warnings(sud, warnings)


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

    has_partners = (
        session.scalar(
            select(func.count()).where(Sud.merged_into_sud_id == sud.id)
        )
        or 0
    ) > 0
    _, remaining_hl = _batch_volumes(session, sud)
    warnings: list[str] = []

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
            # The physically remaining batch volume (lead + merged partners
            # minus withdrawals) must fit every non-Ausschank tank in the
            # new schedule.
            if (
                occ.stage != TankStage.AUSSCHANK
                and remaining_hl > float(tank.capacity_hl)
            ):
                described = (
                    f"This Sud leads a merged batch of {remaining_hl:g} hl"
                    if has_partners
                    else f"Batch volume of {remaining_hl:g} hl"
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
                    float(occ.volume_hl) if occ.volume_hl is not None else remaining_hl,
                    occ.start_at,
                    occ.end_at,
                    beer_style=sud.beer_style,
                    exclude_sud_id=sud.id,
                )

        warnings += _process_warnings(
            _effective_recipe(sud.recipe, sud.recipe_overrides), payload.occupancies
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
                volume_hl=occ.volume_hl,
            )
        )

    session.commit()
    session.refresh(sud)
    return _with_warnings(sud, warnings)


def _with_warnings(sud: Sud, warnings: list[str]) -> SudOut:
    out = SudOut.model_validate(sud)
    out.warnings = warnings
    return out


def _batch_volumes(session: Session, sud: Sud) -> tuple[float, float]:
    """(combined, remaining) in hl for the batch led by `sud`.

    combined = lead + merged partners as brewed; remaining subtracts every
    withdrawal (kegs and pours) — the volume that physically still exists
    and is what capacity checks and transfers must work with.
    """
    partner_volumes = session.scalars(
        select(Sud.volume_hl).where(Sud.merged_into_sud_id == sud.id)
    )
    combined = float(sud.volume_hl) + sum(float(v) for v in partner_volumes)
    withdrawn = sum(
        float(v)
        for v in session.scalars(
            select(Withdrawal.volume_hl).where(Withdrawal.sud_id == sud.id)
        )
    )
    return combined, combined - withdrawn


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
    """Umdrücken: move beer (lead + merged partners) to any other tank.

    The usual Gärtank → Lagertank → Ausschank order is convention, not a
    constraint. The batch may split across several same-stage tanks with
    explicit volume shares at every stage (Stefan, 2026-08-04) — e.g. one
    30-hl fermenter into two smaller storage tanks. Once split,
    `from_tank_id` scopes a transfer to that tank's share; the sibling
    shares stay where they are (the Sud's status then reflects the latest
    move). Outside the Ausschank stage each target must be free (DB
    EXCLUDE) and fit its share; Ausschank tanks blend several batches —
    guarded by the sum-of-allocations ≤ capacity rule (issue #13).
    Process rules (wheat open fermentation, yeast-free Ausschank) surface
    as warnings, they do not block.
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
                "tank — transfer the lead Sud instead."
            ),
        )
    if not sud.occupancies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This Sud has no tank occupancy yet — schedule it before transferring.",
        )

    # When the client names the tank the beer is pushed out of and the
    # batch is split (explicit share), only that share moves; the sibling
    # tanks stay untouched. Older clients omit from_tank_id and move the
    # whole batch.
    source_occ = None
    if payload.from_tank_id is not None:
        source_occ = next(
            (
                o
                for o in sud.occupancies
                if o.tank_id == payload.from_tank_id
                and o.start_at <= payload.start_at
                and (o.end_at is None or payload.start_at < o.end_at)
            ),
            None,
        )
        if source_occ is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This Sud does not occupy that tank at the transfer start.",
            )

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

    _, remaining_hl = _batch_volumes(session, sud)
    if source_occ is not None and source_occ.volume_hl is not None:
        # Split batch: what moves is this tank's share minus what already
        # left it (mirrors the withdraw endpoint's per-tank remaining).
        tank_withdrawn = sum(
            float(w.volume_hl)
            for w in sud.withdrawals
            if w.tank_id == payload.from_tank_id
        )
        moving_hl = float(source_occ.volume_hl) - tank_withdrawn
    else:
        moving_hl = remaining_hl

    # A single allocation without an explicit volume moves the whole batch
    # (occupancy volume NULL = full-batch convention, outside Ausschank —
    # a share stays explicit so its new tank keeps the right remaining).
    # Everything else carries explicit shares that must add up to what is
    # physically moving — kegs and pours already taken out don't move on.
    if (
        target_stage != TankStage.AUSSCHANK
        and (source_occ is None or source_occ.volume_hl is None)
        and len(payload.allocations) == 1
        and payload.allocations[0].volume_hl is None
    ):
        volumes: list[float | None] = [None]
    else:
        volumes = [
            a.volume_hl if a.volume_hl is not None else moving_hl
            for a in payload.allocations
        ]
        total = sum(volumes)
        if abs(total - moving_hl) > 0.01:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Allocated volumes sum to {total:g} hl but "
                    f"{moving_hl:g} hl are being moved."
                ),
            )

    # What ends at the transfer start: the named source tank's occupancy —
    # or, for a whole-batch move, every occupancy still running then.
    truncating = (
        [source_occ]
        if source_occ is not None
        else [
            o
            for o in sud.occupancies
            if o.end_at is None or o.end_at > payload.start_at
        ]
    )
    truncating_ids = {o.id for o in truncating}

    for allocation, volume in zip(payload.allocations, volumes):
        tank = tanks[allocation.tank_id]
        share = moving_hl if volume is None else volume
        if target_stage == TankStage.AUSSCHANK:
            # Ausschank tanks blend same-style batches; the headroom rule
            # decides. Only the occupancies that end now are excluded — a
            # sibling share already sitting in the target tank keeps
            # counting.
            _check_ausschank_headroom(
                session,
                tank,
                share,
                payload.start_at,
                payload.end_at,
                beer_style=sud.beer_style,
                exclude_occupancy_ids=truncating_ids,
            )
        elif share > float(tank.capacity_hl):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Batch volume of {share:g} hl exceeds the "
                    f"{float(tank.capacity_hl):g} hl capacity of tank {tank.name}."
                ),
            )

    end_at = payload.end_at
    if end_at is None and target_stage != TankStage.AUSSCHANK:
        duration_days = _default_duration_days(
            _effective_recipe(sud.recipe, sud.recipe_overrides), target_stage
        )
        end_at = payload.start_at + timedelta(days=duration_days)

    # The beer physically leaves its source tank(s) at the transfer start,
    # so those occupancies — open-ended OR with a planned future end — are
    # truncated to it. Without this, an early transfer left the batch
    # nominally in two tanks at once: the stale occupancy blocked the old
    # tank, misdirected keg withdrawals, and made the wheat rule reject
    # legitimate open→closed moves.
    def effective_end(o: TankOccupancy):
        if o.id in truncating_ids and (
            o.end_at is None or o.end_at > payload.start_at
        ):
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

    # Evaluate the process rules against the future picture: the existing
    # occupancies as they will look after truncation, plus the new
    # allocations.
    future = [
        SimpleNamespace(stage=o.stage, start_at=o.start_at, end_at=effective_end(o))
        for o in sud.occupancies
    ] + [
        SimpleNamespace(stage=target_stage, start_at=payload.start_at, end_at=end_at)
    ]
    warnings = _process_warnings(
        _effective_recipe(sud.recipe, sud.recipe_overrides), future
    )

    for occ in truncating:
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
    return _with_warnings(sud, warnings)


def _resolve_withdraw_volume(payload: WithdrawIn | TankWithdrawIn) -> float:
    """Direct volume — or, for keg fills, the volume computed from the
    counts per barrel size (2026-08-04). Shared by the per-Sud and the
    tank-level (Blending) withdraw endpoints."""
    if payload.kegs:
        if payload.kind != WithdrawalKind.KEG_FILL:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Fass-Stückzahlen gelten nur für Fassabfüllungen.",
            )
        if payload.volume_hl is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Entweder Menge (hl) oder Fass-Stückzahlen angeben — nicht beides.",
            )
        return sum(k.size_l * k.count for k in payload.kegs) / 100.0
    if payload.volume_hl is not None:
        return payload.volume_hl
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Menge (hl) oder Fass-Stückzahlen angeben.",
    )


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

    volume_hl = _resolve_withdraw_volume(payload)

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

    if occupancy.volume_hl is not None:
        # Explicit allocation (split transfer): this tank's share minus
        # what already left it.
        tank_withdrawn = sum(
            float(w.volume_hl) for w in sud.withdrawals if w.tank_id == payload.tank_id
        )
        remaining_hl = float(occupancy.volume_hl) - tank_withdrawn
    else:
        # Whole batch in one tank: everything withdrawn anywhere in its
        # lifetime is gone from it.
        _, remaining_hl = _batch_volumes(session, sud)
    if volume_hl > remaining_hl + 1e-9:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only {remaining_hl:g} hl of this batch remain in the tank — "
                f"cannot withdraw {volume_hl:g} hl."
            ),
        )

    sud.withdrawals.append(
        Withdrawal(
            tank_id=payload.tank_id,
            volume_hl=volume_hl,
            at=payload.at,
            kind=payload.kind,
            keg_counts=[k.model_dump() for k in payload.kegs] if payload.kegs else None,
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
    beer_style: str | None = None,
    exclude_sud_id: uuid.UUID | None = None,
    exclude_occupancy_ids: set[uuid.UUID] | None = None,
) -> None:
    """Ausschank tanks blend several batches OF THE SAME BEER — styles are
    never mixed (Stefan, 2026-08-05). The DB EXCLUDE constraint is scoped
    away from this stage, so both rules live here: no foreign style in the
    window, and the sum of time-overlapping allocations plus the new one
    must fit the tank.

    Exclusions cover what the caller is about to replace: the whole Sud
    when re-scheduling, or exactly the occupancies a transfer truncates —
    a split batch's sibling share must keep counting.
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
    if exclude_occupancy_ids:
        stmt = stmt.where(TankOccupancy.id.not_in(list(exclude_occupancy_ids)))

    allocated = 0.0
    for occ in session.scalars(stmt):
        if beer_style is not None and occ.sud.beer_style != beer_style:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Im Ausschanktank {tank.name} liegt in diesem Zeitraum "
                    f"bereits {occ.sud.beer_style} — Sorten werden nicht "
                    "gemischt."
                ),
            )
        if occ.volume_hl is not None:
            allocated += float(occ.volume_hl)
        else:
            _, occ_remaining = _batch_volumes(session, occ.sud)
            allocated += occ_remaining

    if allocated + volume_hl > float(tank.capacity_hl):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Tank {tank.name} holds {allocated:g} hl in this window — "
                f"adding {volume_hl:g} hl exceeds its "
                f"{float(tank.capacity_hl):g} hl capacity."
            ),
        )


def _process_warnings(recipe, occs) -> list[str]:
    """§2.4 process rules, downgraded to warnings (decided 2026-08-03):
    the brewmaster may deviate from the usual process; the tool points it
    out but records what actually happens. Only physical limits (capacity,
    double-booking, Ausschank headroom) still block."""
    warnings = []
    w = _warn_wheat_open_fermentation(recipe, occs)
    if w is not None:
        warnings.append(w)
    w = _warn_yeast_free_ausschank(recipe, occs)
    if w is not None:
        warnings.append(w)
    return warnings


def _warn_wheat_open_fermentation(recipe, occs) -> str | None:
    """§2.4 rule 3: wheat beer should spend its open-fermentation days in
    the open fermentation tank before entering a closed fermenter."""
    if not recipe.open_fermentation_required:
        return None
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
            return (
                f"„{recipe.name}“ braucht üblicherweise {required.days} Tage "
                "offene Gärung, bevor es in einen geschlossenen Gärtank kommt "
                "— dieser Plan unterschreitet das."
            )
    return None


def _warn_yeast_free_ausschank(recipe, occs) -> str | None:
    """§2.4 rule 2: beer should not enter an Ausschank tank with active
    yeast — approximated as: a completed closed fermentation of at least
    the recipe's fermentation duration before the Ausschank start."""
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
            return (
                f"Gärzeit evtl. zu kurz — „{recipe.name}“ braucht "
                f"{ferm.days} Tage geschlossene Gärung vor dem Ausschank."
            )
    return None


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

    gap = abs(payload.brew_at.date() - lead.brew_date)
    if gap > MERGE_MAX_BREW_GAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Merged batches must be brewed within 48 h of each other "
                f"(2 calendar days) — the gap to the lead's brew date is "
                f"{gap.days} days."
            ),
        )

    # The new partner adds 15 hl of fresh wort (ROADMAP §2.1) to what
    # physically remains of the lead batch.
    _, lead_remaining = _batch_volumes(session, lead)
    combined_hl = lead_remaining + 15.0

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


OVERRIDABLE_DURATIONS = (
    "fermentation_duration_days",
    "storage_duration_days",
    "open_fermentation_duration_days",
)


def _effective_recipe(recipe: Recipe, overrides: dict | None) -> SimpleNamespace:
    """Recipe values with the Sud's per-batch overrides applied (Phase 3).

    Only the duration fields are overridable; everything downstream
    (derived end dates, process warnings) reads from this view so a
    deviating Sud is judged against its own numbers, not the recipe's.
    """
    effective = SimpleNamespace(
        name=recipe.name,
        open_fermentation_required=recipe.open_fermentation_required,
        open_fermentation_duration_days=recipe.open_fermentation_duration_days,
        fermentation_duration_days=recipe.fermentation_duration_days,
        storage_duration_days=recipe.storage_duration_days,
    )
    for field in OVERRIDABLE_DURATIONS:
        if overrides and overrides.get(field) is not None:
            setattr(effective, field, float(overrides[field]))
    return effective


def _default_duration_days(recipe, stage: TankStage) -> float:
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
