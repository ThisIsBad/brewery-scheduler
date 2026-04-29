"""Phase 1 smoke tests.

Validates only the round trip the brewmaster will actually exercise:
- the seed populates the expected number of tanks/recipes/sude
- listing endpoints return them
- PUT /api/sude/{id}/schedule persists occupancies
- POST /api/sude creates a Sud with auto-assigned style_year_number
- the database refuses overlapping occupancies on the same tank

Phase 2 will add validation-rule coverage.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from brewery_scheduler.models import BeerStyle, Recipe, Sud, Tank, TankOccupancy


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


def test_list_recipes_returns_seeded_recipes(client) -> None:
    r = client.get("/api/recipes")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 4
    assert {x["beer_style"] for x in body} == {
        "kellerbier",
        "wheat",
        "festbier",
        "special",
    }


def test_create_sud_assigns_next_style_year_number(client, session) -> None:
    kellerbier_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.KELLERBIER).one()
    )
    # Seed has one Kellerbier with style_year_number=1 in the current year, so
    # the next one in the same year should get 2; a different year should get 1.
    today = date.today()
    next_year = today.replace(year=today.year + 1)

    r1 = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier_recipe.id),
            "brew_date": today.isoformat(),
            "brewmaster": "test",
        },
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["style_year_number"] == 2

    r2 = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier_recipe.id),
            "brew_date": next_year.isoformat(),
            "brewmaster": "test",
        },
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["style_year_number"] == 1


def test_create_sud_with_initial_occupancy_uses_recipe_default_duration(
    client, session
) -> None:
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.KELLERBIER).one()
    )
    ferm_tank = (
        session.query(Tank).filter(Tank.name == "F-15-2").one()
    )  # not used by seed, so free for fermentation_closed
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier.id),
            "brew_date": date.today().isoformat(),
            "initial_occupancy": {
                "tank_id": str(ferm_tank.id),
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
                # end_at omitted on purpose — server should fill from recipe.
            },
        },
    )
    assert r.status_code == 201, r.text
    occ = r.json()["occupancies"][0]
    expected_end = start + timedelta(days=float(kellerbier.fermentation_duration_days))
    # Compare parsed datetimes — Pydantic and datetime.isoformat disagree on
    # whether UTC is "Z" or "+00:00" depending on versions; both are valid ISO.
    actual_end = datetime.fromisoformat(occ["end_at"].replace("Z", "+00:00"))
    assert actual_end == expected_end


def test_create_sud_404_on_unknown_recipe(client) -> None:
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": "00000000-0000-0000-0000-000000000000",
            "brew_date": date.today().isoformat(),
        },
    )
    assert r.status_code == 404


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
