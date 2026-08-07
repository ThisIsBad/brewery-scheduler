"""Änderungsprotokoll: wer hat wann was geändert.

Die Einträge entstehen automatisch beim Flush, damit kein Endpunkt es
vergessen kann — ein Protokoll mit Lücken wäre schlimmer als keines.

Ohne angemeldeten Benutzer wird nichts geschrieben: Seed und Import
legen hunderte Sude an, die niemand „geändert" hat.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from .models import AuditAction, AuditLog, Sud

BENUTZER = "audit_benutzer"

# Technische Felder tragen nichts zur Nachvollziehbarkeit bei.
UNINTERESSANT = frozenset({"id", "created_at", "updated_at"})

# Wovon ein Verlauf geführt wird. Locations bleiben draußen: reine
# Stammdaten ohne Bezug zu einem Braugang.
PROTOKOLLIERT = frozenset(
    {"sude", "tank_occupancy", "withdrawals", "tanks", "recipes"}
)


def benutzer_setzen(session: Session, benutzer: str | None) -> None:
    """Hängt den angemeldeten Benutzer an die Session — von dort holt ihn
    der Flush-Listener."""
    session.info[BENUTZER] = benutzer


def _wert(wert: Any) -> Any:
    """JSON-fähige Darstellung. Decimal wird zu float, damit „51.8" im
    Protokoll als Zahl steht und nicht als Objektabbild."""
    if wert is None or isinstance(wert, (str, int, float, bool)):
        return wert
    if isinstance(wert, Decimal):
        return float(wert)
    if isinstance(wert, uuid.UUID):
        return str(wert)
    if isinstance(wert, (datetime, date)):
        return wert.isoformat()
    if isinstance(wert, enum.Enum):
        return wert.value
    if isinstance(wert, (list, dict)):
        return wert
    return str(wert)


def _sud_id(objekt: Any) -> uuid.UUID | None:
    if isinstance(objekt, Sud):
        return objekt.id
    sud_id = getattr(objekt, "sud_id", None)
    if sud_id is None:
        # Über die Beziehung angelegt (`sud.occupancies.append(...)`): den
        # Fremdschlüssel setzt erst der Flush. `.dict` liefert nur bereits
        # Gesetztes und löst kein Nachladen aus.
        sud = inspect(objekt).dict.get("sud")
        sud_id = getattr(sud, "id", None)
    return sud_id


def _felder(objekt: Any) -> list[str]:
    return [
        attr.key
        for attr in inspect(objekt).mapper.column_attrs
        if attr.key not in UNINTERESSANT
    ]


def _eintrag(objekt: Any, aktion: AuditAction, benutzer: str, changes: dict) -> AuditLog:
    return AuditLog(
        actor=benutzer,
        action=aktion,
        entity=objekt.__tablename__,
        entity_id=objekt.id,
        sud_id=_sud_id(objekt),
        changes=changes,
    )


@event.listens_for(Session, "before_flush")
def _protokollieren(session: Session, flush_context: Any, instances: Any) -> None:
    benutzer = session.info.get(BENUTZER)
    if not benutzer:
        return

    eintraege: list[AuditLog] = []
    neue = [o for o in session.new if o.__tablename__ in PROTOKOLLIERT]

    # UUIDs vergibt sonst erst das INSERT — der Protokolleintrag braucht
    # sie aber schon jetzt, um auf die Zeile zeigen zu können. Das Vorziehen
    # ist unschädlich: der Spaltenvorgabewert greift nur ohne gesetzten Wert.
    for objekt in neue:
        if objekt.id is None:
            objekt.id = uuid.uuid4()

    for objekt in neue:
        werte = {
            feld: _wert(getattr(objekt, feld))
            for feld in _felder(objekt)
            if getattr(objekt, feld) is not None
        }
        eintraege.append(_eintrag(objekt, AuditAction.CREATE, benutzer, werte))

    for objekt in session.dirty:
        if objekt.__tablename__ not in PROTOKOLLIERT:
            continue
        changes: dict[str, dict[str, Any]] = {}
        for feld in _felder(objekt):
            verlauf = get_history(objekt, feld)
            if not verlauf.has_changes():
                continue
            changes[feld] = {
                "alt": _wert(verlauf.deleted[0]) if verlauf.deleted else None,
                "neu": _wert(verlauf.added[0]) if verlauf.added else None,
            }
        if changes:
            eintraege.append(_eintrag(objekt, AuditAction.UPDATE, benutzer, changes))

    for objekt in session.deleted:
        if objekt.__tablename__ not in PROTOKOLLIERT:
            continue
        werte = {
            feld: _wert(getattr(objekt, feld))
            for feld in _felder(objekt)
            if getattr(objekt, feld) is not None
        }
        eintraege.append(_eintrag(objekt, AuditAction.DELETE, benutzer, werte))

    session.add_all(eintraege)
