from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import AuditLog
from ..schemas import AuditOut

router = APIRouter(prefix="/api/verlauf", tags=["verlauf"])


@router.get("", response_model=list[AuditOut])
def list_verlauf(
    sud_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AuditLog]:
    """Änderungen, neueste zuerst. Mit `sud_id` der Verlauf eines Suds —
    inklusive der Änderungen an seinen Belegungen und Abgängen."""
    stmt = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id).limit(limit)
    if sud_id is not None:
        stmt = stmt.filter(AuditLog.sud_id == sud_id)
    return list(session.execute(stmt).scalars())
