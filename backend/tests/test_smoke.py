"""Phase 1 smoke tests.

Validates only the round trip the brewmaster will actually exercise:
- the seed populates the expected number of tanks/recipes/sude
- listing endpoints return them
- PUT /api/sude/{id}/schedule persists occupancies
- the database refuses overlapping occupancies on the same tank

Phase 2 will add validation-rule coverage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from brewery_scheduler.models import Recipe, Sud, Tank


def test_seed_creates_full_inventory(session) -> None:
    assert session.query(Tank).count() == 21
    assert session.query(Recipe).count() == 4
    assert session.query(Sud).count() == 3


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


def test_db_rejects_overlapping_occupancies_on_same_tank(client, session) -> None:
    sude = session.query(Sud).limit(2).all()
    tank_id = str(session.query(Tank).first().id)
    start = datetime.now(timezone.utc).replace(microsecond=0)
    window = {
        "tank_id": tank_id,
        "stage": "fermentation_closed",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(days=7)).isoformat(),
    }

    r1 = client.put(f"/api/sude/{sude[0].id}/schedule", json={"occupancies": [window]})
    assert r1.status_code == 200

    overlap = dict(window, start_at=(start + timedelta(days=3)).isoformat())
    with pytest.raises(IntegrityError):
        client.put(f"/api/sude/{sude[1].id}/schedule", json={"occupancies": [overlap]})
