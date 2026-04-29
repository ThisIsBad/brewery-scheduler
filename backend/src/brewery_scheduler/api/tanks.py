from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Tank
from ..schemas import TankOut

router = APIRouter(prefix="/api/tanks", tags=["tanks"])


@router.get("", response_model=list[TankOut])
def list_tanks(session: Session = Depends(get_session)) -> list[Tank]:
    """List all tanks, ordered for stable display in the Gantt view.

    Phase 1 returns tanks without their occupancies — the frontend joins them
    against /api/sude on the client. Adding a `Tank.occupancies` relationship
    would create a second materialization path for the same data and risk
    inconsistency; we'll revisit if profiling shows it matters.
    """
    stmt = select(Tank).order_by(Tank.cellar, Tank.stage, Tank.name)
    return list(session.scalars(stmt))
