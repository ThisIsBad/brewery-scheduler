import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Sud, TankOccupancy
from ..schemas import ScheduleIn, SudOut

router = APIRouter(prefix="/api/sude", tags=["sude"])


@router.get("", response_model=list[SudOut])
def list_sude(session: Session = Depends(get_session)) -> list[Sud]:
    stmt = (
        select(Sud)
        .options(selectinload(Sud.occupancies))
        .order_by(Sud.brew_date)
    )
    return list(session.scalars(stmt))


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
