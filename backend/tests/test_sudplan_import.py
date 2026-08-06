"""Import der Sudplanung 2026 (Sude 210-300).

Die Import-Tests pinnen `today` auf den Übernahme-Stichtag 2026-08-05 —
Status-Ableitungen (served/planned/fermenting) hängen am Kalender und
sollen nicht mit der realen CI-Uhr driften. Die übrige Suite läuft auf
der kleinen Demo-Welt (conftest); nur hier wird der echte Plan geladen.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from brewery_scheduler import db as db_module
from brewery_scheduler.main import app
from brewery_scheduler.models import Base, Sud, Tank, TankOccupancy
from brewery_scheduler.seed import seed
from brewery_scheduler.sudplan_2026 import import_sudplan

STICHTAG = date(2026, 8, 5)


@pytest.fixture()
def plan_session(engine):
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as s:
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        s.execute(text("ALTER SEQUENCE sud_global_seq RESTART WITH 1"))
        s.commit()
        seed(s, demo_sude=False, sudplan=False)
        s.stats = import_sudplan(s, today=STICHTAG)
        s.commit()
        yield s


@pytest.fixture()
def plan_client(engine, plan_session, monkeypatch) -> TestClient:
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(db_module, "engine", engine)
    return TestClient(app)


def _sud(session, global_number: int) -> Sud:
    return session.query(Sud).filter(Sud.global_number == global_number).one()


def _tank(session, name: str) -> Tank:
    return session.query(Tank).filter(Tank.name == name).one()


def test_import_umfang_und_nummern(plan_session) -> None:
    assert plan_session.stats["sude"] == 91
    assert plan_session.stats["paare"] == 37

    globals_ = [g for (g,) in plan_session.query(Sud.global_number).order_by(Sud.global_number)]
    assert globals_ == list(range(210, 301))

    # Neuanlagen zählen hinter dem Plan weiter.
    last, is_called = plan_session.execute(
        text("SELECT last_value, is_called FROM sud_global_seq")
    ).one()
    assert (last, is_called) == (301, False)

    # Sortennummern zählen je Sorte — wie Vincenz' Saison-Tabelle.
    per_style = {
        style: n
        for style, n in plan_session.execute(
            text("SELECT beer_style, max(style_year_number) FROM sude GROUP BY beer_style")
        )
    }
    assert per_style["Festbier"] == 34  # Bergbier (Gisela)
    assert per_style["Kellerbier Hell"] == 38
    assert per_style["Kellerbier Hell Sven"] == 2


def test_import_statusverteilung_am_stichtag(plan_session) -> None:
    counts = {
        status: n
        for status, n in plan_session.execute(
            text("SELECT status, count(*) FROM sude GROUP BY status")
        )
    }
    assert counts == {"served": 67, "planned": 14, "fermenting": 5, "storing": 5}


def test_sud_210_uebernimmt_protokoll_und_mapping(plan_session) -> None:
    sud = _sud(plan_session, 210)
    # Bergbier (Gisela) ist das Festbier; Menge aus dem Sudblatt (16,2 hl).
    assert sud.beer_style == "Festbier"
    assert float(sud.volume_hl) == 16.2
    assert sud.brewmaster == "Vincenz"
    assert sud.status.value == "served"
    chain = (
        plan_session.query(TankOccupancy)
        .filter(TankOccupancy.sud_id == sud.id)
        .order_by(TankOccupancy.start_at)
        .all()
    )
    # Lovis (Gärung) → "Kitzmann groß" = Kitzmann hinten; abgeschlossen,
    # also kein offenes Ende mehr.
    assert [o.tank_id for o in chain] == [
        _tank(plan_session, "Lovis").id,
        _tank(plan_session, "Kitzmann hinten").id,
    ]
    assert all(o.end_at is not None for o in chain)


def test_striezitank_ist_bergtank_120(plan_session) -> None:
    bergtank = _tank(plan_session, "Bergtank 120 hl")
    occs = (
        plan_session.query(TankOccupancy)
        .filter(TankOccupancy.tank_id == bergtank.id)
        .all()
    )
    # Vier Doppelsude (224/225 … 230/231) ziehen am 4.4. in den Striezitank um.
    assert len(occs) == 4
    assert {o.start_at.date() for o in occs} == {date(2026, 4, 4)}


def test_doppelsud_288_289_als_lead_und_partner(plan_session) -> None:
    lead, partner = _sud(plan_session, 288), _sud(plan_session, 289)
    assert partner.merged_into_sud_id == lead.id
    assert partner.occupancies == []
    assert lead.status.value == "planned"
    assert partner.style_year_number == lead.style_year_number + 1


def test_split_213_214_bedient_zwei_ausschanktanks(plan_session) -> None:
    lead, partner = _sud(plan_session, 213), _sud(plan_session, 214)
    assert partner.merged_into_sud_id == lead.id
    targets = {
        o.tank_id: float(o.volume_hl)
        for o in lead.occupancies
        if o.volume_hl is not None
    }
    # 213 → Bergtank (100 hl), 214 → Kitzmann groß; jede Seite mit ihrer Menge.
    assert targets == {
        _tank(plan_session, "Bergtank 100 hl").id: pytest.approx(16.2),
        _tank(plan_session, "Kitzmann hinten").id: pytest.approx(16.2),
    }


def test_plankonflikte_werden_vermerkt_statt_verschluckt(plan_session) -> None:
    assert plan_session.stats["verworfen"] == 3
    for number in (251, 285, 297):
        assert "kollidiert" in (_sud(plan_session, number).notes or "")
    # Nicht nachgepflegte Zeilen tragen den Hinweis am Sud.
    assert "Kette gekappt" in (_sud(plan_session, 277).notes or "")


def test_ausschank_stationen_haben_plan_enden(plan_session) -> None:
    """„Bis leer" ist keine Planungsgröße — offene Fenster würden jede
    spätere anderssortige Belegung blockieren (Stefan, 2026-08-06:
    „kann wenig bewegen … Sorten werden nicht gemischt")."""
    offene = (
        plan_session.query(TankOccupancy)
        .filter(TankOccupancy.end_at.is_(None))
        .count()
    )
    assert offene == 0
    # Kitzmann vorne läuft seriell: Kellerbier endet exakt am Start des
    # Spezialsuds (19.08.), der wiederum am Weizen-Start (02.09.).
    kellerbier = _sud(plan_session, 288)
    spezialsud = _sud(plan_session, 292)
    vorne = _tank(plan_session, "Kitzmann vorne").id
    kb_occ = next(o for o in kellerbier.occupancies if o.tank_id == vorne)
    sp_occ = next(o for o in spezialsud.occupancies if o.tank_id == vorne)
    assert kb_occ.end_at == sp_occ.start_at
    assert sp_occ.end_at.date() == date(2026, 9, 2)


def test_zeitplan_ist_entsperrt_spezialsud_laesst_sich_verschieben(
    plan_session, plan_client
) -> None:
    """Vor den Plan-Enden schlug genau das mit 409 „Sorten werden nicht
    gemischt" fehl: das Spezialsud-Fenster überlappte die offenen
    Kellerbier-Belegungen in Kitzmann vorne."""
    sud = _sud(plan_session, 292)
    # Der Gärtank-Block wandert einen Tag; die (unveränderte!) Ausschank-
    # Station läuft im Payload mit — vorher reichte das für die Sperre.
    payload = []
    for o in sorted(sud.occupancies, key=lambda o: o.start_at):
        delta = timedelta(days=1) if o.stage.value == "fermentation_closed" else timedelta()
        payload.append(
            {
                "tank_id": str(o.tank_id),
                "stage": o.stage.value,
                "start_at": (o.start_at + delta).isoformat(),
                "end_at": (o.end_at + delta).isoformat() if o.end_at else None,
                "volume_hl": float(o.volume_hl) if o.volume_hl is not None else None,
            }
        )
    r = plan_client.put(f"/api/sude/{sud.id}/schedule", json={"occupancies": payload})
    assert r.status_code == 200, r.text

    # Echte Sortenkonflikte bleiben hart: das Spezialsud-Fenster in den
    # Weizen (ab 02.09.) hineinzuziehen ist weiterhin ein 409.
    hinein = [
        {**occ, "end_at": "2026-09-03T12:00:00+00:00"}
        if occ["stage"] == "ausschank"
        else occ
        for occ in payload
    ]
    r = plan_client.put(f"/api/sude/{sud.id}/schedule", json={"occupancies": hinein})
    assert r.status_code == 409
    assert "Sorten werden nicht gemischt" in r.json()["detail"]
