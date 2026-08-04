from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import (
    Location,
    Sud,
    SudStatus,
    Tank,
    TankOccupancy,
    TankStage,
    Withdrawal,
)
from ..schemas import SudOut, TankCreateIn, TankOut, TankUpdateIn, TankWithdrawIn

router = APIRouter(prefix="/api/tanks", tags=["tanks"])


@router.get("", response_model=list[TankOut])
def list_tanks(session: Session = Depends(get_session)) -> list[Tank]:
    """List all tanks, ordered for stable display in the Gantt view.

    Includes deactivated tanks (`active: false`) so historical occupancies
    keep rendering; pickers filter on `active` client-side.

    Phase 1 returns tanks without their occupancies — the frontend joins them
    against /api/sude on the client. Adding a `Tank.occupancies` relationship
    would create a second materialization path for the same data and risk
    inconsistency; we'll revisit if profiling shows it matters.
    """
    stmt = (
        select(Tank)
        .join(Location)
        .order_by(Location.position, Location.name, Tank.stage, Tank.name)
    )
    return list(session.scalars(stmt))


@router.post("", response_model=TankOut, status_code=status.HTTP_201_CREATED)
def create_tank(payload: TankCreateIn, session: Session = Depends(get_session)) -> Tank:
    _ensure_free_name(session, payload.name)
    _ensure_location(session, payload.location_id)
    tank = Tank(
        name=payload.name,
        location_id=payload.location_id,
        stage=payload.stage,
        capacity_hl=payload.capacity_hl,
    )
    session.add(tank)
    session.commit()
    session.refresh(tank)
    return tank


@router.patch("/{tank_id}", response_model=TankOut)
def update_tank(
    tank_id: uuid.UUID,
    payload: TankUpdateIn,
    session: Session = Depends(get_session),
) -> Tank:
    tank = session.get(Tank, tank_id)
    if tank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tank not found")

    data = payload.model_dump(exclude_unset=True)

    # The lock guards master data against accidental taps; toggling the
    # lock itself is always allowed, occupancies are unaffected.
    if tank.locked and any(field != "locked" for field in data):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tank {tank.name} ist gesperrt — erst entsperren, dann ändern.",
        )

    busy = _active_or_future_occupancies(session, tank.id)

    if "name" in data and data["name"] != tank.name:
        _ensure_free_name(session, data["name"])
    if "location_id" in data:
        _ensure_location(session, data["location_id"])
    if (
        "stage" in data
        and TankStage(data["stage"]) != TankStage(tank.stage)
        and busy > 0
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Der Typ von Tank {tank.name} kann nicht geändert werden, "
                "solange Belegungen laufen oder geplant sind."
            ),
        )
    if "capacity_hl" in data and busy > 0:
        needed = _max_load_hl(session, tank)
        if needed > float(data["capacity_hl"]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Tank {tank.name} trägt laufend oder geplant {needed:g} hl — "
                    f"die Kapazität kann nicht auf {float(data['capacity_hl']):g} hl "
                    "gesenkt werden."
                ),
            )

    for field, value in data.items():
        setattr(tank, field, value)
    session.commit()
    session.refresh(tank)
    return tank


@router.delete("/{tank_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tank(tank_id: uuid.UUID, session: Session = Depends(get_session)) -> None:
    """Remove a tank. With running or planned occupancies: refused. With
    past history: deactivated, so the Kellerbuch keeps rendering. Never
    used: really deleted."""
    tank = session.get(Tank, tank_id)
    if tank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tank not found")

    if tank.locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tank {tank.name} ist gesperrt — erst entsperren, dann entfernen.",
        )

    if _active_or_future_occupancies(session, tank.id) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Tank {tank.name} hat laufende oder geplante Belegungen — "
                "erst umdrücken bzw. umplanen, dann entfernen."
            ),
        )

    has_history = (
        (
            session.scalar(
                select(func.count())
                .select_from(TankOccupancy)
                .where(TankOccupancy.tank_id == tank.id)
            )
            or 0
        )
        + (
            session.scalar(
                select(func.count())
                .select_from(Withdrawal)
                .where(Withdrawal.tank_id == tank.id)
            )
            or 0
        )
    ) > 0

    if has_history:
        tank.active = False
    else:
        session.delete(tank)
    session.commit()


def _ensure_free_name(session: Session, name: str) -> None:
    if session.scalar(select(Tank).where(Tank.name == name)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Der Tankname „{name}“ ist bereits vergeben.",
        )


def _ensure_location(session: Session, location_id: uuid.UUID) -> None:
    if session.get(Location, location_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden."
        )


def _active_or_future_occupancies(session: Session, tank_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    return (
        session.scalar(
            select(func.count())
            .select_from(TankOccupancy)
            .where(
                TankOccupancy.tank_id == tank_id,
                or_(
                    TankOccupancy.end_at.is_(None),
                    TankOccupancy.end_at > now,
                    TankOccupancy.start_at > now,
                ),
            )
        )
        or 0
    )


def _max_load_hl(session: Session, tank: Tank) -> float:
    """Largest volume the tank must hold across its running and planned
    occupancies. Outside the Ausschank stage occupancies are exclusive, so
    the max over single occupancies suffices; Ausschank tanks blend batches,
    so time-overlapping allocations add up."""
    from .sude import _batch_volumes

    now = datetime.now(timezone.utc)
    occs = list(
        session.scalars(
            select(TankOccupancy)
            .options(selectinload(TankOccupancy.sud))
            .where(
                TankOccupancy.tank_id == tank.id,
                or_(
                    TankOccupancy.end_at.is_(None),
                    TankOccupancy.end_at > now,
                    TankOccupancy.start_at > now,
                ),
            )
        )
    )
    if not occs:
        return 0.0

    def occ_volume(o: TankOccupancy) -> float:
        if o.volume_hl is not None:
            return float(o.volume_hl)
        _, remaining = _batch_volumes(session, o.sud)
        return remaining

    volumes = {o.id: occ_volume(o) for o in occs}
    if TankStage(tank.stage) != TankStage.AUSSCHANK:
        return max(volumes.values())

    def overlaps(a: TankOccupancy, b: TankOccupancy) -> bool:
        a_end = a.end_at or datetime.max.replace(tzinfo=timezone.utc)
        b_end = b.end_at or datetime.max.replace(tzinfo=timezone.utc)
        return a.start_at < b_end and b.start_at < a_end

    return max(
        sum(volumes[other.id] for other in occs if overlaps(occ, other))
        for occ in occs
    )


@router.post("/{tank_id}/withdraw", response_model=list[SudOut])
def tank_withdraw(
    tank_id: uuid.UUID,
    payload: TankWithdrawIn,
    session: Session = Depends(get_session),
) -> list[Sud]:
    """Blending (2026-08-04): Ausschank tanks mix several batches, so kegs,
    pours and Schwund are booked on the TANK and distributed proportionally
    across the contained Sud shares. A Sud whose batch thereby reaches zero
    is finished — status `served`, its running occupancies end.
    """
    from .sude import _batch_volumes, _resolve_withdraw_volume

    tank = session.get(Tank, tank_id)
    if tank is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tank not found")
    if TankStage(tank.stage) != TankStage.AUSSCHANK:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Tank-Buchungen gibt es nur am Ausschanktank — "
                "vorher wird am Sud gebucht."
            ),
        )
    volume_hl = _resolve_withdraw_volume(payload)

    occs = list(
        session.scalars(
            select(TankOccupancy)
            .options(selectinload(TankOccupancy.sud))
            .where(
                TankOccupancy.tank_id == tank.id,
                TankOccupancy.start_at <= payload.at,
                TankOccupancy.end_at.is_(None) | (TankOccupancy.end_at > payload.at),
            )
        )
    )
    if not occs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Zu diesem Zeitpunkt liegt kein Sud in diesem Tank.",
        )

    # What each batch still holds IN THIS TANK: explicit shares (summed —
    # sequential consolidation can leave several rows) minus this tank's
    # withdrawals; a NULL share means the whole batch sits here and its
    # batch remaining already accounts for every withdrawal.
    suds: dict[uuid.UUID, Sud] = {}
    shares: dict[uuid.UUID, float] = {}
    whole_batch: set[uuid.UUID] = set()
    for occ in occs:
        suds[occ.sud_id] = occ.sud
        if occ.volume_hl is None:
            whole_batch.add(occ.sud_id)
        else:
            shares[occ.sud_id] = shares.get(occ.sud_id, 0.0) + float(occ.volume_hl)

    remaining: dict[uuid.UUID, float] = {}
    for sud_id, sud in suds.items():
        if sud_id in whole_batch:
            _, rem = _batch_volumes(session, sud)
        else:
            withdrawn = sum(
                float(v)
                for v in session.scalars(
                    select(Withdrawal.volume_hl).where(
                        Withdrawal.sud_id == sud_id,
                        Withdrawal.tank_id == tank.id,
                    )
                )
            )
            rem = shares[sud_id] - withdrawn
        remaining[sud_id] = max(rem, 0.0)

    total = sum(remaining.values())
    if volume_hl > total + 1e-9:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Im Tank {tank.name} sind nur {total:g} hl — "
                f"{volume_hl:g} hl können nicht gebucht werden."
            ),
        )

    # Largest share first: it absorbs the rounding residual and carries the
    # keg counts (they belong to the tank booking as a whole; keeping them
    # on one row keeps totals summable).
    order = sorted(remaining, key=lambda sid: remaining[sid], reverse=True)
    allocated: dict[uuid.UUID, float] = {}
    for sud_id in order[1:]:
        allocated[sud_id] = round(volume_hl * remaining[sud_id] / total, 4)
    allocated[order[0]] = round(volume_hl - sum(allocated.values()), 4)

    affected: list[Sud] = []
    for sud_id in order:
        share = allocated[sud_id]
        if share <= 1e-9:
            continue
        sud = suds[sud_id]
        sud.withdrawals.append(
            Withdrawal(
                tank_id=tank.id,
                volume_hl=share,
                at=payload.at,
                kind=payload.kind,
                keg_counts=(
                    [k.model_dump() for k in payload.kegs]
                    if payload.kegs and sud_id == order[0]
                    else None
                ),
                notes=payload.notes,
            )
        )
        affected.append(sud)

    # Auto-complete (Blending decision): a batch with nothing left anywhere
    # is done — no manual archiving in the cellar. The session runs with
    # autoflush=False, so the fresh withdrawals must be flushed before
    # _batch_volumes can see them.
    session.flush()
    for sud in affected:
        _, rem = _batch_volumes(session, sud)
        if rem <= 0.01:
            sud.status = SudStatus.SERVED
            for occ in sud.occupancies:
                if occ.end_at is None or occ.end_at > payload.at:
                    occ.end_at = payload.at
            for partner in session.scalars(
                select(Sud).where(Sud.merged_into_sud_id == sud.id)
            ):
                partner.status = SudStatus.SERVED

    session.commit()
    ids = [s.id for s in affected]
    by_id = {
        s.id: s
        for s in session.scalars(
            select(Sud)
            .options(selectinload(Sud.occupancies), selectinload(Sud.withdrawals))
            .where(Sud.id.in_(ids))
        )
    }
    return [by_id[i] for i in ids]
