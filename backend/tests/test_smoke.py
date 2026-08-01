"""Phase 1 smoke tests.

Validates only the round trip the brewmaster will actually exercise:
- the seed populates the expected number of tanks/recipes/sude
- listing endpoints return them
- PUT /api/sude/{id}/schedule persists occupancies
- constraint violations surface as structured 409/422 responses

Phase 2 will add validation-rule coverage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brewery_scheduler.models import Recipe, Sud, Tank, TankOccupancy


def test_seed_creates_full_inventory(session) -> None:
    assert session.query(Tank).count() == 21
    assert session.query(Recipe).count() == 4
    assert session.query(Sud).count() == 3
    assert session.query(TankOccupancy).count() == 6


def test_seed_assigns_sud_numbers(session) -> None:
    sude = session.query(Sud).all()

    # Each seeded Sud is the first of its style/year, so style_year_number == 1.
    assert all(s.style_year_number == 1 for s in sude)

    # global_number is sequential and unique starting from 1.
    globals_ = sorted(s.global_number for s in sude)
    assert globals_ == [1, 2, 3]


def test_list_sude_exposes_style_year_number(client) -> None:
    body = client.get("/api/sude").json()
    assert all("style_year_number" in s for s in body)
    assert all("global_number" not in s for s in body), (
        "global_number is internal-only; do not leak it to the frontend"
    )


def test_health_endpoint(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_tanks_returns_full_inventory(client) -> None:
    r = client.get("/api/tanks")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 21
    capacities = sorted(t["capacity_hl"] for t in body)
    # Sanity: tanks measured in hectoliters (smallest = 10, largest = 120).
    assert capacities[0] == 10
    assert capacities[-1] == 120


def test_list_sude_returns_seeded_batches(client) -> None:
    r = client.get("/api/sude")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert all("recipe" in s for s in body)


def test_update_schedule_replaces_occupancies(client, session) -> None:
    sud_id = str(session.query(Sud).first().id)
    tank_id = str(session.query(Tank).first().id)
    start = datetime.now(timezone.utc).replace(microsecond=0)

    payload = {
        "occupancies": [
            {
                "tank_id": tank_id,
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(days=7)).isoformat(),
            }
        ]
    }
    r = client.put(f"/api/sude/{sud_id}/schedule", json=payload)
    assert r.status_code == 200, r.text
    assert len(r.json()["occupancies"]) == 1

    # Replacing again should not accumulate.
    r2 = client.put(f"/api/sude/{sud_id}/schedule", json={"occupancies": []})
    assert r2.status_code == 200
    assert r2.json()["occupancies"] == []


def test_overlapping_occupancy_returns_structured_409(client, session) -> None:
    sude = session.query(Sud).order_by(Sud.brew_date).limit(2).all()
    tank_id = str(session.query(Tank).filter(Tank.name == "F-30-1").one().id)
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    window = {
        "tank_id": tank_id,
        "stage": "fermentation_closed",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(days=7)).isoformat(),
    }

    r1 = client.put(f"/api/sude/{sude[0].id}/schedule", json={"occupancies": [window]})
    assert r1.status_code == 200

    overlap = dict(window, start_at=(start + timedelta(days=3)).isoformat())
    r2 = client.put(f"/api/sude/{sude[1].id}/schedule", json={"occupancies": [overlap]})
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["constraint"] == "ex_tank_occupancy_no_overlap"
    assert "occupied" in body["detail"]


def test_inverted_time_window_returns_structured_422(client, session) -> None:
    sud_id = str(session.query(Sud).first().id)
    tank_id = str(session.query(Tank).filter(Tank.name == "F-30-1").one().id)
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=90)

    r = client.put(
        f"/api/sude/{sud_id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": tank_id,
                    "stage": "fermentation_closed",
                    "start_at": start.isoformat(),
                    "end_at": (start - timedelta(days=1)).isoformat(),
                }
            ]
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["constraint"] == "ck_tank_occupancy_time_order"
