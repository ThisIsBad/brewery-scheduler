from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Location, Tank
from ..schemas import LocationCreateIn, LocationOut, LocationUpdateIn

router = APIRouter(prefix="/api/locations", tags=["locations"])


@router.get("", response_model=list[LocationOut])
def list_locations(session: Session = Depends(get_session)) -> list[Location]:
    return list(
        session.scalars(select(Location).order_by(Location.position, Location.name))
    )


@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreateIn, session: Session = Depends(get_session)
) -> Location:
    _ensure_free_name(session, payload.name)
    next_position = (
        session.scalar(select(func.coalesce(func.max(Location.position), 0))) or 0
    ) + 1
    location = Location(name=payload.name, position=next_position)
    session.add(location)
    session.commit()
    session.refresh(location)
    return location


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: uuid.UUID,
    payload: LocationUpdateIn,
    session: Session = Depends(get_session),
) -> Location:
    location = session.get(Location, location_id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden."
        )
    if payload.name != location.name:
        _ensure_free_name(session, payload.name)
        location.name = payload.name
    session.commit()
    session.refresh(location)
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: uuid.UUID, session: Session = Depends(get_session)
) -> None:
    location = session.get(Location, location_id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden."
        )
    tank_count = (
        session.scalar(
            select(func.count()).select_from(Tank).where(Tank.location_id == location.id)
        )
        or 0
    )
    if tank_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Standort „{location.name}“ hat noch {tank_count} Tanks — "
                "erst verschieben oder entfernen."
            ),
        )
    session.delete(location)
    session.commit()


def _ensure_free_name(session: Session, name: str) -> None:
    if session.scalar(select(Location).where(Location.name == name)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Der Standortname „{name}“ ist bereits vergeben.",
        )
