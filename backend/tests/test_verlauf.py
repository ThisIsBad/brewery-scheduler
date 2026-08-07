"""Änderungsprotokoll (Stefan, 2026-08-07).

Der Wert des Protokolls steht und fällt damit, dass niemand es umgehen
kann — deshalb prüfen die Tests nicht die Protokollfunktion selbst,
sondern gehen durch die echten Endpunkte.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brewery_scheduler.models import AuditLog, Sud, Tank

BENUTZER = {"X-Authenticated-User": "stefan"}


def _erster_sud(session) -> Sud:
    return (
        session.query(Sud)
        .filter(Sud.merged_into_sud_id.is_(None))
        .order_by(Sud.global_number)
        .first()
    )


def test_seed_erzeugt_keine_eintraege(session) -> None:
    """Der Import legt hunderte Sude an, die niemand „geändert" hat."""
    assert session.query(AuditLog).count() == 0


def test_tankaenderung_merkt_sich_benutzer_und_werte(client, session) -> None:
    tank = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    r = client.patch(
        f"/api/tanks/{tank.id}", json={"verbrauch_hl_pro_woche": 22}, headers=BENUTZER
    )
    assert r.status_code == 200

    eintrag = client.get("/api/verlauf", headers=BENUTZER).json()[0]
    assert eintrag["actor"] == "stefan"
    assert eintrag["action"] == "update"
    assert eintrag["entity"] == "tanks"
    assert eintrag["entity_id"] == str(tank.id)
    assert eintrag["changes"]["verbrauch_hl_pro_woche"] == {"alt": 15.0, "neu": 22.0}


def test_ohne_header_bleibt_der_benutzer_unbestimmt(client, session) -> None:
    """Ohne Caddy davor (Entwicklung) darf niemand fälschlich genannt
    werden — protokolliert wird trotzdem."""
    tank = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    client.patch(f"/api/tanks/{tank.id}", json={"verbrauch_hl_pro_woche": 9})

    eintrag = client.get("/api/verlauf").json()[0]
    assert eintrag["actor"] == "unbekannt"


def test_verlauf_eines_suds_umfasst_seine_belegungen(client, session) -> None:
    """Eine Umplanung ändert Belegungen, nicht den Sud selbst — im
    Verlauf des Suds muss sie trotzdem auftauchen."""
    sud = _erster_sud(session)
    belegungen = sorted(sud.occupancies, key=lambda o: o.start_at)
    payload = [
        {
            "tank_id": str(o.tank_id),
            "stage": o.stage.value,
            "start_at": (o.start_at + timedelta(hours=3)).isoformat(),
            "end_at": (o.end_at + timedelta(hours=3)).isoformat() if o.end_at else None,
            "volume_hl": float(o.volume_hl) if o.volume_hl is not None else None,
        }
        for o in belegungen
    ]
    r = client.put(
        f"/api/sude/{sud.id}/schedule", json={"occupancies": payload}, headers=BENUTZER
    )
    assert r.status_code == 200, r.text

    verlauf = client.get(f"/api/verlauf?sud_id={sud.id}", headers=BENUTZER).json()
    assert verlauf, "Die Umplanung fehlt im Verlauf des Suds"
    assert {e["entity"] for e in verlauf} <= {"sude", "tank_occupancy"}
    assert all(e["actor"] == "stefan" for e in verlauf)
    assert all(e["sud_id"] == str(sud.id) for e in verlauf)


def test_anlegen_und_loeschen_halten_den_zustand_fest(client, session) -> None:
    haupt = session.query(Tank).first().location_id
    neu = client.post(
        "/api/tanks",
        json={
            "name": "Protokolltank",
            "location_id": str(haupt),
            "stage": "storage",
            "capacity_hl": 12,
        },
        headers=BENUTZER,
    )
    assert neu.status_code == 201, neu.text
    tank_id = neu.json()["id"]

    angelegt = client.get("/api/verlauf", headers=BENUTZER).json()[0]
    assert angelegt["action"] == "create"
    assert angelegt["changes"]["name"] == "Protokolltank"
    assert angelegt["changes"]["capacity_hl"] == 12.0

    client.delete(f"/api/tanks/{tank_id}", headers=BENUTZER)
    zuletzt = client.get("/api/verlauf", headers=BENUTZER).json()[0]
    # Deaktivieren statt Löschen ist erlaubt — beides muss auffindbar sein.
    assert zuletzt["entity_id"] == tank_id
    assert zuletzt["action"] in {"update", "delete"}


def test_verlauf_ist_neueste_zuerst_und_begrenzbar(client, session) -> None:
    tank = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    for wert in (11, 12, 13):
        client.patch(
            f"/api/tanks/{tank.id}",
            json={"verbrauch_hl_pro_woche": wert},
            headers=BENUTZER,
        )

    alle = client.get("/api/verlauf", headers=BENUTZER).json()
    zeiten = [datetime.fromisoformat(e["at"]) for e in alle]
    assert zeiten == sorted(zeiten, reverse=True)
    assert alle[0]["changes"]["verbrauch_hl_pro_woche"]["neu"] == 13.0

    assert len(client.get("/api/verlauf?limit=2", headers=BENUTZER).json()) == 2


def test_lesende_zugriffe_erzeugen_nichts(client, session) -> None:
    client.get("/api/sude", headers=BENUTZER)
    client.get("/api/tanks", headers=BENUTZER)
    assert session.query(AuditLog).count() == 0


def test_gefaelschter_header_gilt_trotzdem_nur_lokal(client, session) -> None:
    """In Produktion überschreibt Caddy den Header. Der Test hält fest,
    dass das Backend selbst ihm vertraut — die Absicherung liegt bewusst
    im Proxy (deploy/Caddyfile), nicht hier."""
    tank = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    client.patch(
        f"/api/tanks/{tank.id}",
        json={"verbrauch_hl_pro_woche": 7},
        headers={"X-Authenticated-User": "wer-auch-immer"},
    )
    assert client.get("/api/verlauf").json()[0]["actor"] == "wer-auch-immer"


def test_zeitstempel_liegt_in_der_gegenwart(client, session) -> None:
    tank = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    client.patch(f"/api/tanks/{tank.id}", json={"capacity_hl": 55}, headers=BENUTZER)
    eintrag = client.get("/api/verlauf", headers=BENUTZER).json()[0]
    abstand = datetime.now(timezone.utc) - datetime.fromisoformat(eintrag["at"])
    assert abs(abstand) < timedelta(minutes=5)
