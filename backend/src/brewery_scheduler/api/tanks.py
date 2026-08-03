from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Location, Tank, TankOccupancy, TankStage, Withdrawal
from ..schemas import TankCreateIn, TankOut, TankUpdateIn

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
