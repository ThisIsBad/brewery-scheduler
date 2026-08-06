"""Import der Sudplanung 2026 (Sude 210-300).

Die Import-Tests pinnen `today` auf den Übernahme-Stichtag 2026-08-05 —
Status-Ableitungen (served/planned/fermenting) hängen am Kalender und
sollen nicht mit der realen CI-Uhr driften. Die übrige Suite läuft auf
der kleinen Demo-Welt (conftest); nur hier wird der echte Plan geladen.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

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
