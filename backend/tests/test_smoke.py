"""Phase 1 smoke tests.

Validates only the round trip the brewmaster will actually exercise:
- the seed populates the expected number of tanks/recipes/sude
- listing endpoints return them
- PUT /api/sude/{id}/schedule persists occupancies
- POST /api/sude creates a Sud with auto-assigned style_year_number
- constraint violations surface as structured 409/422 responses

Phase 2 will add validation-rule coverage.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from brewery_scheduler.models import (
    Location,
    Recipe,
    Sud,
    Tank,
    TankOccupancy,
    TankStage,
)

# The seeded style names (Bierrezepte.xlsx) — beer_style is a free string
# since migration 0013.
KELLERBIER = "Keller Hell"
WEIZEN = "Weizen"
FESTBIER = "Festbier"
SPEZIALSUD = "Spezialsud"


def test_db_rejects_duplicate_style_year_number(session) -> None:
    # The constraint from migration 0005 turns a concurrent-create race into
    # a rejected insert instead of a silently duplicated Sud-Nr.
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    existing = (
        session.query(Sud).filter(Sud.beer_style == KELLERBIER).one()
    )
    dupe = Sud(
        recipe_id=kellerbier.id,
        beer_style=KELLERBIER,
        brew_at=existing.brew_at,
        brew_date=existing.brew_date,
        style_year_number=existing.style_year_number,
    )
    session.add(dupe)
    with pytest.raises(IntegrityError) as excinfo:
        session.commit()
    session.rollback()
    assert "uq_sude_style_year_number" in str(excinfo.value)


def test_orm_returns_enum_members(session) -> None:
    tank = session.query(Tank).filter(Tank.name == "Offener Gärbottich").one()
    assert isinstance(tank.stage, TankStage)
    occ = session.query(TankOccupancy).first()
    assert isinstance(occ.stage, TankStage)
    sud = session.query(Sud).first()
    assert isinstance(sud.beer_style, str)


def test_seed_creates_full_inventory(session) -> None:
    assert session.query(Tank).count() == 22
    assert session.query(Recipe).count() == 10
    assert session.query(Sud).count() == 4
    assert session.query(TankOccupancy).count() == 6
    # The Excel's „frühere Biere" are seeded archived.
    inactive = {
        r.beer_style for r in session.query(Recipe).filter(Recipe.active.is_(False))
    }
    assert inactive == {"Wit", "Leichtbier"}


def test_seed_assigns_sud_numbers(session) -> None:
    leads = session.query(Sud).filter(Sud.merged_into_sud_id.is_(None)).all()
    partners = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).all()

    # Each lead is the first of its style/year; the merged Festbier partner
    # is a brew in its own right and gets the next number.
    assert all(s.style_year_number == 1 for s in leads)
    assert [p.style_year_number for p in partners] == [2]

    # global_number is sequential and unique starting from 1.
    globals_ = sorted(s.global_number for s in session.query(Sud).all())
    assert globals_ == [1, 2, 3, 4]


def test_seed_partner_has_no_occupancies(session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    assert partner.occupancies == []


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
    assert len(body) == 22
    capacities = sorted(t["capacity_hl"] for t in body)
    # Sanity: tanks measured in hectoliters (smallest = 10, largest = 120).
    assert capacities[0] == 10
    assert capacities[-1] == 120


def test_list_sude_returns_seeded_batches(client) -> None:
    r = client.get("/api/sude")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 4
    assert all("recipe" in s for s in body)
    assert all("volume_hl" in s and "merged_into_sud_id" in s for s in body)


def test_update_schedule_replaces_occupancies(client, session) -> None:
    # Kellerbier explicitly: a wheat Sud would trip the open-fermentation rule
    # on this bare closed-fermentation payload.
    sud_id = str(_seeded_lead(session, KELLERBIER).id)
    tank_id = str(session.query(Tank).filter(Tank.name == "Lisa").one().id)
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
    assert len(body) == 10
    assert {x["beer_style"] for x in body} == {
        "Keller Hell",
        "Weizen",
        "Festbier",
        "Spezialsud",
        "bay. Dunkel",
        "Rauchbier",
        "Weizenbock",
        "Collab Widder",
        "Wit",
        "Leichtbier",
    }


def test_create_sud_assigns_next_style_year_number(client, session) -> None:
    kellerbier_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    # Seed has one Kellerbier with style_year_number=1 in the current year, so
    # the next one in the same year should get 2; a different year should get 1.
    # A fixed month/day avoids today.replace(year=+1), which raises on Feb 29.
    today = date.today()
    next_year = date(today.year + 1, 6, 15)

    r1 = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier_recipe.id),
            "brew_at": _brew_at(today),
            "brewmaster": "test",
        },
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["style_year_number"] == 2

    r2 = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier_recipe.id),
            "brew_at": _brew_at(next_year),
            "brewmaster": "test",
        },
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["style_year_number"] == 1


def test_create_sud_with_initial_occupancy_uses_recipe_default_duration(
    client, session
) -> None:
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    ferm_tank = (
        session.query(Tank).filter(Tank.name == "Lovis").one()
    )  # not used by seed, so free for fermentation_closed
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier.id),
            "brew_at": _brew_at(date.today()),
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


def test_create_sud_422_on_overlong_brewmaster(client, session) -> None:
    recipe_id = str(session.query(Recipe).first().id)
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": recipe_id,
            "brew_at": _brew_at(date.today()),
            "brewmaster": "x" * 200,
        },
    )
    # Without the schema bound this would hit the String(128) column and 500.
    assert r.status_code == 422


def test_create_sud_404_on_unknown_recipe(client) -> None:
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": "00000000-0000-0000-0000-000000000000",
            "brew_at": _brew_at(date.today()),
        },
    )
    assert r.status_code == 404


def _brew_at(d: date) -> str:
    return datetime.combine(d, time(9), tzinfo=timezone.utc).isoformat()


def _seeded_lead(session, style: str) -> Sud:
    return (
        session.query(Sud)
        .join(Recipe, Recipe.id == Sud.recipe_id)
        .filter(Recipe.beer_style == style, Sud.merged_into_sud_id.is_(None))
        .one()
    )


def test_merge_partner_happy_path(client, session) -> None:
    # The Kellerbier lead sits in 30-hl tanks with 15 hl — room for one partner.
    lead = _seeded_lead(session, KELLERBIER)
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(lead.recipe_id),
            "brew_at": _brew_at((lead.brew_date + timedelta(days=1))),
            "merge_into_sud_id": str(lead.id),
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["merged_into_sud_id"] == str(lead.id)
    assert body["occupancies"] == []
    assert body["volume_hl"] == 15
    # Its own brew number: seed Kellerbier is Nr. 1, so the partner is Nr. 2.
    assert body["style_year_number"] == 2


def test_merge_rejects_when_combined_volume_exceeds_tank(client, session) -> None:
    # The seeded Festbier lead already has one partner: 30 hl in a 30-hl tank.
    lead = _seeded_lead(session, FESTBIER)
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(lead.recipe_id),
            "brew_at": _brew_at((lead.brew_date + timedelta(days=1))),
            "merge_into_sud_id": str(lead.id),
        },
    )
    assert r.status_code == 409, r.text
    assert "exceeds" in r.json()["detail"]


def test_merge_rejects_different_recipe(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    wheat_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == WEIZEN).one()
    )
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(wheat_recipe.id),
            "brew_at": _brew_at((lead.brew_date + timedelta(days=1))),
            "merge_into_sud_id": str(lead.id),
        },
    )
    assert r.status_code == 422, r.text
    assert "same recipe" in r.json()["detail"]


def test_merge_brew_gap_boundary(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)

    # Exactly 2 calendar days: accepted.
    r_ok = client.post(
        "/api/sude",
        json={
            "recipe_id": str(lead.recipe_id),
            "brew_at": _brew_at((lead.brew_date + timedelta(days=2))),
            "merge_into_sud_id": str(lead.id),
        },
    )
    assert r_ok.status_code == 201, r_ok.text

    # 3 days: rejected. (Weizen lead is untouched, so use it for the reject
    # case to keep the Kellerbier tank's volume budget out of the picture.)
    weizen_lead = _seeded_lead(session, WEIZEN)
    r_reject = client.post(
        "/api/sude",
        json={
            "recipe_id": str(weizen_lead.recipe_id),
            "brew_at": _brew_at((weizen_lead.brew_date + timedelta(days=3))),
            "merge_into_sud_id": str(weizen_lead.id),
        },
    )
    assert r_reject.status_code == 422, r_reject.text
    assert "48" in r_reject.json()["detail"]


def test_merge_rejects_chaining_onto_a_partner(client, session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(partner.recipe_id),
            "brew_at": _brew_at(partner.brew_date),
            "merge_into_sud_id": str(partner.id),
        },
    )
    assert r.status_code == 422, r.text
    assert "itself a partner" in r.json()["detail"]


def test_merge_capped_for_unscheduled_lead(client, session) -> None:
    # An unscheduled lead has no occupancies to validate against — the cap
    # against the largest fermentation tank (30 hl) must still fire.
    recipe_id = str(
        session.query(Recipe).filter(Recipe.beer_style == SPEZIALSUD).one().id
    )
    lead = client.post(
        "/api/sude",
        json={"recipe_id": recipe_id, "brew_at": _brew_at(date.today())},
    ).json()

    first = client.post(
        "/api/sude",
        json={
            "recipe_id": recipe_id,
            "brew_at": _brew_at(date.today()),
            "merge_into_sud_id": lead["id"],
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/sude",
        json={
            "recipe_id": recipe_id,
            "brew_at": _brew_at(date.today()),
            "merge_into_sud_id": lead["id"],
        },
    )
    assert second.status_code == 409, second.text
    assert "largest fermentation tank" in second.json()["detail"]


def test_schedule_rechecks_combined_volume_for_lead(client, session) -> None:
    # The POST-time check must not be bypassable by rescheduling the lead
    # into a smaller tank afterwards.
    lead = _seeded_lead(session, FESTBIER)  # 15 + 15 hl partner
    small_tank = session.query(Tank).filter(Tank.name == "Lovis").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=150)

    r = client.put(
        f"/api/sude/{lead.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(small_tank.id),
                    "stage": "fermentation_closed",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=7)).isoformat(),
                }
            ]
        },
    )
    assert r.status_code == 409, r.text
    assert "merged batch" in r.json()["detail"]


def test_merge_rejects_initial_occupancy_combination(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    tank_id = str(session.query(Tank).filter(Tank.name == "Lovis").one().id)
    start = datetime.now(timezone.utc).replace(microsecond=0)
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(lead.recipe_id),
            "brew_at": _brew_at((lead.brew_date + timedelta(days=1))),
            "merge_into_sud_id": str(lead.id),
            "initial_occupancy": {
                "tank_id": tank_id,
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
            },
        },
    )
    assert r.status_code == 422, r.text
    assert "mutually exclusive" in r.json()["detail"]


def test_merge_404_on_unknown_lead(client, session) -> None:
    recipe_id = str(session.query(Recipe).first().id)
    r = client.post(
        "/api/sude",
        json={
            "recipe_id": recipe_id,
            "brew_at": _brew_at(date.today()),
            "merge_into_sud_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert r.status_code == 404


def _transfer(client, sud_id, allocations, start, end=None, from_tank=None):
    return client.post(
        f"/api/sude/{sud_id}/transfer",
        json={
            "start_at": start.isoformat(),
            "end_at": end.isoformat() if end else None,
            "allocations": allocations,
            **({"from_tank_id": str(from_tank)} if from_tank else {}),
        },
    )


def test_transfer_to_storage_happy_path(client, session) -> None:
    # Weizen sits in closed fermentation (Alva, ends +4d); move it on.
    lead = _seeded_lead(session, WEIZEN)
    target = session.query(Tank).filter(Tank.name == "Benjamin").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)

    r = _transfer(client, lead.id, [{"tank_id": str(target.id)}], start)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "storing"
    storage_occs = [o for o in body["occupancies"] if o["stage"] == "storage"]
    assert len(storage_occs) == 1
    assert storage_occs[0]["tank_id"] == str(target.id)
    # end_at derived from the recipe's storage duration (14 days for Weizen).
    expected_end = start + timedelta(days=14)
    actual_end = datetime.fromisoformat(
        storage_occs[0]["end_at"].replace("Z", "+00:00")
    )
    assert actual_end == expected_end


def test_transfer_backward_move_allowed(client, session) -> None:
    # Kellerbier's latest occupancy is storage; moving back into a
    # fermentation tank is unusual but allowed (decided 2026-08-03: the
    # usual order is convention, not a constraint).
    lead = _seeded_lead(session, KELLERBIER)
    ferm_tank = session.query(Tank).filter(Tank.name == "Greta").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)

    r = _transfer(client, lead.id, [{"tank_id": str(ferm_tank.id)}], start)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "fermenting"
    assert any(
        o["tank_id"] == str(ferm_tank.id) and o["stage"] == "fermentation_closed"
        for o in body["occupancies"]
    )
    assert body["warnings"] == []


def test_transfer_same_stage_move_allowed(client, session) -> None:
    # Re-tanking within the same stage (Lagertank → anderer Lagertank).
    lead = _seeded_lead(session, KELLERBIER)
    other_storage = session.query(Tank).filter(Tank.name == "Evelyn").one()
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = _transfer(client, lead.id, [{"tank_id": str(other_storage.id)}], start)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "storing"
    assert any(
        o["tank_id"] == str(other_storage.id) and o["stage"] == "storage"
        for o in body["occupancies"]
    )
    assert body["warnings"] == []


def test_transfer_to_ausschank_with_active_yeast_warns(client, session) -> None:
    # Bergkirchweih case: straight from the fermenter to an Ausschank tank.
    # Goes through, but flags the potentially active yeast.
    lead = _seeded_lead(session, WEIZEN)
    a_tank = session.query(Tank).filter(Tank.name == "Striezi Keller 1").one()
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = _transfer(
        client, lead.id, [{"tank_id": str(a_tank.id), "volume_hl": 15.0}], start
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_ausschank"
    assert any("Gärzeit" in w for w in body["warnings"]), body["warnings"]


def test_transfer_rejects_partner(client, session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    target = session.query(Tank).filter(Tank.name == "Evelyn").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)

    r = _transfer(client, partner.id, [{"tank_id": str(target.id)}], start)
    assert r.status_code == 422, r.text
    assert "transfer the lead" in r.json()["detail"]


def test_transfer_split_across_storage_tanks(client, session) -> None:
    # Splitting is allowed at every stage (Stefan, 2026-08-04): the 15-hl
    # Weizen goes 8/7 across two free Schänke-4 storage tanks.
    lead = _seeded_lead(session, WEIZEN)
    t1 = session.query(Tank).filter(Tank.name == "Benjamin").one()
    t2 = session.query(Tank).filter(Tank.name == "Evelyn").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)

    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(t1.id), "volume_hl": 8},
            {"tank_id": str(t2.id), "volume_hl": 7},
        ],
        start,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "storing"
    storage_occs = [o for o in body["occupancies"] if o["stage"] == "storage"]
    assert sorted(o["volume_hl"] for o in storage_occs) == [7, 8]
    # Both shares inherit the recipe-derived storage end (14 days for Weizen).
    expected_end = start + timedelta(days=14)
    for occ in storage_occs:
        actual = datetime.fromisoformat(occ["end_at"].replace("Z", "+00:00"))
        assert actual == expected_end


def test_transfer_split_share_must_fit_tank(client, session) -> None:
    # Shares sum correctly, but 16 hl cannot enter a 15-hl fermenter.
    # Outside the Ausschank stage capacity is per-tank, not blended
    # headroom.
    lead = _seeded_lead(session, FESTBIER)  # merged batch, 30 hl
    t1 = session.query(Tank).filter(Tank.name == "Alva").one()
    t2 = session.query(Tank).filter(Tank.name == "Lovis").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)

    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(t1.id), "volume_hl": 16},
            {"tank_id": str(t2.id), "volume_hl": 14},
        ],
        start,
    )
    assert r.status_code == 409, r.text
    assert "exceeds" in r.json()["detail"]


def test_withdraw_respects_split_storage_share(client, session) -> None:
    # After an 8/7 storage split, each tank only gives up its own share.
    lead = _seeded_lead(session, WEIZEN)
    t1 = session.query(Tank).filter(Tank.name == "Benjamin").one()
    t2 = session.query(Tank).filter(Tank.name == "Evelyn").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(t1.id), "volume_hl": 8},
            {"tank_id": str(t2.id), "volume_hl": 7},
        ],
        start,
    )
    assert r.status_code == 200, r.text

    at = (start + timedelta(days=1)).isoformat()
    over = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={"tank_id": str(t2.id), "volume_hl": 7.5, "at": at},
    )
    assert over.status_code == 409, over.text
    assert "7 hl" in over.json()["detail"]

    ok = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={"tank_id": str(t2.id), "volume_hl": 5, "at": at},
    )
    assert ok.status_code == 200, ok.text


def test_transfer_moves_only_the_source_share(client, session) -> None:
    # After an 8/7 storage split, pushing Benjamin onward moves its 8 hl;
    # the 7-hl sibling share stays where it is.
    lead = _seeded_lead(session, WEIZEN)
    t1 = session.query(Tank).filter(Tank.name == "Benjamin").one()
    t2 = session.query(Tank).filter(Tank.name == "Evelyn").one()
    a35 = session.query(Tank).filter(Tank.name == "Striezi Keller 2").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(t1.id), "volume_hl": 8},
            {"tank_id": str(t2.id), "volume_hl": 7},
        ],
        start,
    )
    assert r.status_code == 200, r.text

    onward = start + timedelta(days=3)
    r = _transfer(
        client,
        lead.id,
        [{"tank_id": str(a35.id), "volume_hl": 8}],
        onward,
        from_tank=t1.id,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    occs = {(o["tank_id"], o["stage"]): o for o in body["occupancies"]}

    sibling = occs[(str(t2.id), "storage")]
    assert sibling["volume_hl"] == 7
    sibling_end = datetime.fromisoformat(sibling["end_at"].replace("Z", "+00:00"))
    assert sibling_end == start + timedelta(days=14)

    source = occs[(str(t1.id), "storage")]
    source_end = datetime.fromisoformat(source["end_at"].replace("Z", "+00:00"))
    assert source_end == onward

    moved = occs[(str(a35.id), "ausschank")]
    assert moved["volume_hl"] == 8
    assert body["status"] == "in_ausschank"


def test_transfer_scoped_sum_checks_against_share(client, session) -> None:
    # Allocations of a scoped move must match the tank's share (8 hl), not
    # the batch total (15 hl).
    lead = _seeded_lead(session, WEIZEN)
    t1 = session.query(Tank).filter(Tank.name == "Benjamin").one()
    t2 = session.query(Tank).filter(Tank.name == "Evelyn").one()
    a35 = session.query(Tank).filter(Tank.name == "Striezi Keller 2").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(t1.id), "volume_hl": 8},
            {"tank_id": str(t2.id), "volume_hl": 7},
        ],
        start,
    )
    assert r.status_code == 200, r.text

    r = _transfer(
        client,
        lead.id,
        [{"tank_id": str(a35.id), "volume_hl": 15}],
        start + timedelta(days=3),
        from_tank=t1.id,
    )
    assert r.status_code == 422, r.text
    assert "8 hl are being moved" in r.json()["detail"]


def test_scoped_moves_blend_shares_into_ausschank_headroom(client, session) -> None:
    # Sequential consolidation: both split shares end up in the 35-hl
    # Ausschank tank (8 + 7). A same-style batch bringing 25 hl on top
    # would overflow it — the sibling share must keep counting toward
    # headroom even while its batch is mid-move.
    lead = _seeded_lead(session, WEIZEN)
    t1 = session.query(Tank).filter(Tank.name == "Benjamin").one()
    t2 = session.query(Tank).filter(Tank.name == "Evelyn").one()
    a35 = session.query(Tank).filter(Tank.name == "Striezi Keller 2").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)
    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(t1.id), "volume_hl": 8},
            {"tank_id": str(t2.id), "volume_hl": 7},
        ],
        start,
    )
    assert r.status_code == 200, r.text
    r = _transfer(
        client,
        lead.id,
        [{"tank_id": str(a35.id), "volume_hl": 8}],
        start + timedelta(days=1),
        from_tank=t1.id,
    )
    assert r.status_code == 200, r.text
    r = _transfer(
        client,
        lead.id,
        [{"tank_id": str(a35.id), "volume_hl": 7}],
        start + timedelta(days=2),
        from_tank=t2.id,
    )
    assert r.status_code == 200, r.text

    zweiter = _api_sud(client, session, WEIZEN, "Greta", start - timedelta(days=20))
    r = client.put(
        f"/api/sude/{zweiter['id']}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(a35.id),
                    "stage": "ausschank",
                    "start_at": (start + timedelta(days=3)).isoformat(),
                    "end_at": None,
                    "volume_hl": 25,
                }
            ]
        },
    )
    assert r.status_code == 409, r.text
    assert "exceeds" in r.json()["detail"]


def test_transfer_split_to_two_ausschank_tanks(client, session) -> None:
    # The merged Festbier batch (30 hl) splits 20/10 across two Ausschank tanks.
    lead = _seeded_lead(session, FESTBIER)
    a100 = session.query(Tank).filter(Tank.name == "Bergtank 100 hl").one()
    a80 = session.query(Tank).filter(Tank.name == "Kitzmann hinten").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)

    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(a100.id), "volume_hl": 20},
            {"tank_id": str(a80.id), "volume_hl": 10},
        ],
        start,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_ausschank"
    ausschank_occs = [o for o in body["occupancies"] if o["stage"] == "ausschank"]
    assert sorted(o["volume_hl"] for o in ausschank_occs) == [10, 20]
    # Ausschank has no recipe-derived duration: stays open until poured.
    assert all(o["end_at"] is None for o in ausschank_occs)


def test_transfer_split_volumes_must_sum_to_batch(client, session) -> None:
    lead = _seeded_lead(session, FESTBIER)
    a100 = session.query(Tank).filter(Tank.name == "Bergtank 100 hl").one()
    a80 = session.query(Tank).filter(Tank.name == "Kitzmann hinten").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)

    r = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(a100.id), "volume_hl": 20},
            {"tank_id": str(a80.id), "volume_hl": 5},
        ],
        start,
    )
    assert r.status_code == 422, r.text
    assert "sum" in r.json()["detail"]


def test_ausschank_consolidates_batches_until_capacity(client, session) -> None:
    # Two batches may share an Ausschank tank; a third that would overflow
    # the 35-hl tank is rejected. Builds its own Sude via the API.
    recipe_id = str(
        session.query(Recipe).filter(Recipe.beer_style == SPEZIALSUD).one().id
    )
    a35 = session.query(Tank).filter(Tank.name == "Striezi Keller 1").one()
    ferm_tanks = ["Greta", "Anouk", "Yuri"]
    base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=200)

    statuses = []
    for i, tank_name in enumerate(ferm_tanks):
        ferm_tank = session.query(Tank).filter(Tank.name == tank_name).one()
        created = client.post(
            "/api/sude",
            json={
                "recipe_id": recipe_id,
                "brew_at": _brew_at(date.today()),
                "initial_occupancy": {
                    "tank_id": str(ferm_tank.id),
                    "stage": "fermentation_closed",
                    "start_at": (base + timedelta(days=i)).isoformat(),
                    "end_at": (base + timedelta(days=7 + i)).isoformat(),
                },
            },
        ).json()
        r = _transfer(
            client,
            created["id"],
            [{"tank_id": str(a35.id)}],
            base + timedelta(days=10),
        )
        statuses.append(r.status_code)

    # 15 + 15 = 30 hl fit into 35 hl; the third 15 hl would make 45.
    assert statuses == [200, 200, 409]


def _api_sud(client, session, style, ferm_tank_name, start, days=7) -> dict:
    """Create an extra Sud of `style` via the API with a finished
    fermentation window — the seeds carry only one lead per style, and
    same-style scenarios (sortenreines Blending) need a second."""
    recipe = (
        session.query(Recipe)
        .filter(Recipe.beer_style == style)
        .order_by(Recipe.version.desc())
        .first()
    )
    ferm_tank = session.query(Tank).filter(Tank.name == ferm_tank_name).one()
    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(recipe.id),
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(ferm_tank.id),
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(days=days)).isoformat(),
            },
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _existing_occupancies_payload(sud) -> list[dict]:
    return [
        {
            "tank_id": str(o.tank_id),
            "stage": o.stage if isinstance(o.stage, str) else o.stage.value,
            "start_at": o.start_at.isoformat(),
            "end_at": o.end_at.isoformat() if o.end_at else None,
            "volume_hl": float(o.volume_hl) if o.volume_hl is not None else None,
        }
        for o in sud.occupancies
    ]


def test_schedule_enforces_ausschank_headroom(client, session) -> None:
    # The generic schedule endpoint must apply the same headroom rule —
    # with same-style batches, so headroom (not the style rule) decides.
    lead = _seeded_lead(session, KELLERBIER)
    a35 = session.query(Tank).filter(Tank.name == "Striezi Keller 2").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=300)

    r1 = client.put(
        f"/api/sude/{lead.id}/schedule",
        json={
            "occupancies": _existing_occupancies_payload(lead)
            + [
                {
                    "tank_id": str(a35.id),
                    "stage": "ausschank",
                    "start_at": start.isoformat(),
                    "end_at": None,
                    "volume_hl": 30,
                }
            ]
        },
    )
    assert r1.status_code == 200, r1.text

    zweiter = _api_sud(client, session, KELLERBIER, "Greta", start - timedelta(days=20))
    r2 = client.put(
        f"/api/sude/{zweiter['id']}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(a35.id),
                    "stage": "ausschank",
                    "start_at": start.isoformat(),
                    "end_at": None,
                    "volume_hl": 15,
                }
            ]
        },
    )
    assert r2.status_code == 409, r2.text
    assert "capacity" in r2.json()["detail"]


def test_occupancy_stage_must_match_tank_stage(client, session) -> None:
    # A stage label contradicting the tank would dodge every stage-scoped
    # rule (EXCLUDE, sortenrein, headroom) — both occupancy-creating
    # endpoints reject it.
    keller = _seeded_lead(session, KELLERBIER)
    a120 = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=300)

    spoofed = client.put(
        f"/api/sude/{keller.id}/schedule",
        json={
            "occupancies": _existing_occupancies_payload(keller)
            + [
                {
                    "tank_id": str(a120.id),
                    "stage": "storage",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=7)).isoformat(),
                }
            ]
        },
    )
    assert spoofed.status_code == 422, spoofed.text
    assert "passt nicht" in spoofed.json()["detail"]

    recipe = session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(recipe.id),
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(a120.id),
                "stage": "storage",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(days=7)).isoformat(),
            },
        },
    )
    assert created.status_code == 422, created.text
    assert "passt nicht" in created.json()["detail"]


def test_create_sud_ausschank_occupancy_respects_sortenrein(client, session) -> None:
    # POST /api/sude is the third occupancy-creating endpoint — the
    # sortenrein rule must hold there too.
    weizen = _seeded_lead(session, WEIZEN)
    a120 = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    r = _transfer(
        client, weizen.id, [{"tank_id": str(a120.id), "volume_hl": 15}], start
    )
    assert r.status_code == 200, r.text

    keller_recipe = session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    blocked = client.post(
        "/api/sude",
        json={
            "recipe_id": str(keller_recipe.id),
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(a120.id),
                "stage": "ausschank",
                "start_at": (start + timedelta(days=1)).isoformat(),
                "end_at": (start + timedelta(days=30)).isoformat(),
            },
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert "nicht gemischt" in blocked.json()["detail"]


def test_emptied_share_frees_tank_for_other_styles(client, session) -> None:
    # Eine leergezapfte Teilmenge gibt IHREN Tank sofort frei — sonst
    # blockiert eine offene Null-Belegung den Tank für andere Sorten,
    # obwohl er physisch leer ist.
    weizen = _seeded_lead(session, WEIZEN)
    keller = _seeded_lead(session, KELLERBIER)
    a1 = session.query(Tank).filter(Tank.name == "Striezi Keller 1").one()
    a2 = session.query(Tank).filter(Tank.name == "Striezi Keller 2").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    r = _transfer(
        client,
        weizen.id,
        [
            {"tank_id": str(a1.id), "volume_hl": 10},
            {"tank_id": str(a2.id), "volume_hl": 5},
        ],
        start,
    )
    assert r.status_code == 200, r.text

    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    r = client.post(
        f"/api/tanks/{a2.id}/withdraw",
        json={"volume_hl": 5, "at": at, "kind": "ausschank"},
    )
    assert r.status_code == 200, r.text
    body = r.json()[0]
    a2_occ = next(o for o in body["occupancies"] if o["tank_id"] == str(a2.id))
    assert a2_occ["end_at"] is not None
    # Der Sud lebt weiter (10 hl in Striezi Keller 1) …
    assert body["status"] == "in_ausschank"

    # … aber der geleerte Tank nimmt jetzt eine andere Sorte an.
    r = _transfer(
        client,
        keller.id,
        [{"tank_id": str(a2.id), "volume_hl": 15}],
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1),
    )
    assert r.status_code == 200, r.text


def test_sud_withdraw_empties_share_and_completes_batch(client, session) -> None:
    # Auch die Sud-Ebene beendet leergezapfte Belegungen und schließt den
    # Sud ab, wenn nichts mehr übrig ist (Parität zum Tank-Endpoint).
    weizen = _seeded_lead(session, WEIZEN)
    a1 = session.query(Tank).filter(Tank.name == "Striezi Keller 1").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    r = _transfer(
        client, weizen.id, [{"tank_id": str(a1.id), "volume_hl": 15}], start
    )
    assert r.status_code == 200, r.text

    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    r = client.post(
        f"/api/sude/{weizen.id}/withdraw",
        json={"tank_id": str(a1.id), "volume_hl": 15, "at": at, "kind": "ausschank"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "served"
    a1_occ = next(o for o in body["occupancies"] if o["tank_id"] == str(a1.id))
    assert a1_occ["end_at"] is not None


def test_ausschank_rejects_style_mix(client, session) -> None:
    # Sorten werden nie gemischt (Stefan, 2026-08-05): sobald ein
    # Ausschanktank eine Sorte enthält, blockt jede andere — beim
    # Umdrücken UND beim Planen.
    weizen = _seeded_lead(session, WEIZEN)
    keller = _seeded_lead(session, KELLERBIER)
    a120 = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    r = _transfer(
        client, weizen.id, [{"tank_id": str(a120.id), "volume_hl": 15}], start
    )
    assert r.status_code == 200, r.text

    blocked = _transfer(
        client,
        keller.id,
        [{"tank_id": str(a120.id), "volume_hl": 15}],
        start + timedelta(days=1),
    )
    assert blocked.status_code == 409, blocked.text
    assert "nicht gemischt" in blocked.json()["detail"]

    planned = client.put(
        f"/api/sude/{keller.id}/schedule",
        json={
            "occupancies": _existing_occupancies_payload(keller)
            + [
                {
                    "tank_id": str(a120.id),
                    "stage": "ausschank",
                    "start_at": (start + timedelta(days=1)).isoformat(),
                    "end_at": None,
                    "volume_hl": 15,
                }
            ]
        },
    )
    assert planned.status_code == 409, planned.text
    assert "nicht gemischt" in planned.json()["detail"]


def test_schedule_allows_stage_regression(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    ferm = session.query(Tank).filter(Tank.name == "Lisa").one()
    storage = session.query(Tank).filter(Tank.name == "Vincenz").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.put(
        f"/api/sude/{lead.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(storage.id),
                    "stage": "storage",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=7)).isoformat(),
                },
                {
                    "tank_id": str(ferm.id),
                    "stage": "fermentation_closed",
                    "start_at": (start + timedelta(days=7)).isoformat(),
                    "end_at": (start + timedelta(days=14)).isoformat(),
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["occupancies"]) == 2


def test_schedule_warns_wheat_without_open_fermentation(client, session) -> None:
    weizen = _seeded_lead(session, WEIZEN)
    ferm = session.query(Tank).filter(Tank.name == "Lovis").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.put(
        f"/api/sude/{weizen.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(ferm.id),
                    "stage": "fermentation_closed",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=7)).isoformat(),
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert any("offene Gärung" in w for w in r.json()["warnings"])


def test_schedule_warns_ausschank_with_active_yeast(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    a50 = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.put(
        f"/api/sude/{lead.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(a50.id),
                    "stage": "ausschank",
                    "start_at": start.isoformat(),
                    "end_at": None,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert any("Gärzeit" in w for w in r.json()["warnings"])


def test_create_warns_wheat_starting_in_closed_fermenter(client, session) -> None:
    wheat_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == WEIZEN).one()
    )
    ferm = session.query(Tank).filter(Tank.name == "Lovis").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.post(
        "/api/sude",
        json={
            "recipe_id": str(wheat_recipe.id),
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(ferm.id),
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
            },
        },
    )
    assert r.status_code == 201, r.text
    assert any("offene Gärung" in w for w in r.json()["warnings"])


def test_create_rejects_initial_occupancy_over_capacity(client, session) -> None:
    # Seit der Vincenz-Tankwelt gibt es keinen Nicht-Ausschank-Tank unter
    # 15 hl mehr — der Test legt sich seinen Zwickeltank selbst an.
    recipe_id = str(
        session.query(Recipe).filter(Recipe.beer_style == SPEZIALSUD).one().id
    )
    location_id = str(
        session.query(Location).filter(Location.name == "Schänke 4").one().id
    )
    created_tank = client.post(
        "/api/tanks",
        json={
            "name": "Zwickel 5",
            "location_id": location_id,
            "stage": "storage",
            "capacity_hl": 5,
        },
    )
    assert created_tank.status_code == 201, created_tank.text
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.post(
        "/api/sude",
        json={
            "recipe_id": recipe_id,
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": created_tank.json()["id"],
                "stage": "storage",
                "start_at": start.isoformat(),
            },
        },
    )
    assert r.status_code == 409, r.text
    assert "capacity" in r.json()["detail"]


def test_transfer_truncates_running_occupancy(client, session) -> None:
    # Kellerbier's storage occupancy has a planned end 14 days out; an early
    # transfer must truncate it at the transfer start — the beer physically
    # left, the tank is free again, and no overlapping two-tank state exists.
    lead = _seeded_lead(session, KELLERBIER)
    a50 = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = _transfer(client, lead.id, [{"tank_id": str(a50.id)}], start)
    assert r.status_code == 200, r.text
    body = r.json()
    storage = [o for o in body["occupancies"] if o["stage"] == "storage"]
    assert len(storage) == 1
    truncated_end = datetime.fromisoformat(storage[0]["end_at"].replace("Z", "+00:00"))
    assert truncated_end == start


def test_transfer_out_of_open_fermentation_warns_below_minimum_days(
    client, session
) -> None:
    wheat_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == WEIZEN).one()
    )
    open_tank = session.query(Tank).filter(Tank.name == "Offener Gärbottich").one()
    closed_tank = session.query(Tank).filter(Tank.name == "Lovis").one()
    base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)

    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(wheat_recipe.id),
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(open_tank.id),
                "stage": "fermentation_open",
                "start_at": base.isoformat(),
                "end_at": (base + timedelta(days=4)).isoformat(),
            },
        },
    ).json()

    # Day 2: truncating at the transfer start leaves only 2 open days — the
    # move goes through but carries the wheat warning.
    early = _transfer(
        client,
        created["id"],
        [{"tank_id": str(closed_tank.id)}],
        base + timedelta(days=2),
    )
    assert early.status_code == 200, early.text
    body = early.json()
    assert any("offene Gärung" in w for w in body["warnings"]), body["warnings"]
    open_occs = [o for o in body["occupancies"] if o["stage"] == "fermentation_open"]
    truncated_end = datetime.fromisoformat(
        open_occs[0]["end_at"].replace("Z", "+00:00")
    )
    assert truncated_end == base + timedelta(days=2)

    # A second wheat Sud that sits out its full 4 open days moves warning-free.
    base2 = base + timedelta(days=20)
    full_term = client.post(
        "/api/sude",
        json={
            "recipe_id": str(wheat_recipe.id),
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(open_tank.id),
                "stage": "fermentation_open",
                "start_at": base2.isoformat(),
                "end_at": (base2 + timedelta(days=4)).isoformat(),
            },
        },
    ).json()
    on_time = _transfer(
        client,
        full_term["id"],
        [{"tank_id": str(closed_tank.id)}],
        base2 + timedelta(days=4),
    )
    assert on_time.status_code == 200, on_time.text
    assert on_time.json()["warnings"] == []


def test_transfer_rejects_unscheduled_sud(client, session) -> None:
    recipe_id = str(session.query(Recipe).first().id)
    created = client.post(
        "/api/sude",
        json={"recipe_id": recipe_id, "brew_at": _brew_at(date.today())},
    ).json()
    target = session.query(Tank).filter(Tank.name == "Fritz").one()
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = _transfer(client, created["id"], [{"tank_id": str(target.id)}], start)
    assert r.status_code == 422, r.text
    assert "schedule it before" in r.json()["detail"]


def test_withdraw_happy_path_and_remaining_volume(client, session) -> None:
    # Kellerbier (15 hl) sits in storage tank Vincenz right now.
    lead = _seeded_lead(session, KELLERBIER)
    tank = session.query(Tank).filter(Tank.name == "Vincenz").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r1 = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "volume_hl": 5,
            "at": now.isoformat(),
            "notes": "2 Fässer fürs Festzelt",
        },
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert len(body["withdrawals"]) == 1
    assert body["withdrawals"][0]["volume_hl"] == 5
    assert body["withdrawals"][0]["kind"] == "keg_fill"

    # 5 of 15 hl are gone — withdrawing 12 more must fail with the remainder.
    r2 = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "volume_hl": 12,
            "at": now.isoformat(),
        },
    )
    assert r2.status_code == 409, r2.text
    assert "10 hl" in r2.json()["detail"]


def test_transfer_distributes_remaining_volume_after_withdrawals(
    client, session
) -> None:
    # 2 hl went into kegs — the Ausschank split must distribute 13 hl, not
    # the brewed 15 (Stefan's field-test finding).
    lead = _seeded_lead(session, KELLERBIER)
    storage_tank = session.query(Tank).filter(Tank.name == "Vincenz").one()
    a100 = session.query(Tank).filter(Tank.name == "Bergtank 100 hl").one()
    a80 = session.query(Tank).filter(Tank.name == "Kitzmann hinten").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    keg = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(storage_tank.id),
            "volume_hl": 2,
            "at": now.isoformat(),
        },
    )
    assert keg.status_code == 200, keg.text

    wrong = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(a100.id), "volume_hl": 8},
            {"tank_id": str(a80.id), "volume_hl": 7},
        ],
        now + timedelta(minutes=5),
    )
    assert wrong.status_code == 422, wrong.text
    assert "13 hl" in wrong.json()["detail"]

    right = _transfer(
        client,
        lead.id,
        [
            {"tank_id": str(a100.id), "volume_hl": 8},
            {"tank_id": str(a80.id), "volume_hl": 5},
        ],
        now + timedelta(minutes=5),
    )
    assert right.status_code == 200, right.text


def test_withdraw_ausschank_kind_round_trips(client, session) -> None:
    # Pours are tracked separately from keg fills (beer tax) — including
    # pours straight from a fermentation tank (Bergkirchweih).
    weizen = _seeded_lead(session, WEIZEN)
    ferm_tank = session.query(Tank).filter(Tank.name == "Alva").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{weizen.id}/withdraw",
        json={
            "tank_id": str(ferm_tank.id),
            "volume_hl": 3,
            "at": now.isoformat(),
            "kind": "ausschank",
            "notes": "Bergkirchweih",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["withdrawals"][0]["kind"] == "ausschank"


def test_withdraw_rejects_tank_not_occupied_at_time(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    wrong_tank = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(wrong_tank.id),
            "volume_hl": 1,
            "at": now.isoformat(),
        },
    )
    assert r.status_code == 422, r.text
    assert "does not occupy" in r.json()["detail"]


def test_withdraw_rejects_partner(client, session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    tank = session.query(Tank).filter(Tank.name == "Wanda").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{partner.id}/withdraw",
        json={"tank_id": str(tank.id), "volume_hl": 1, "at": now.isoformat()},
    )
    assert r.status_code == 422, r.text
    assert "withdraw from the lead" in r.json()["detail"]


def test_withdraw_rejects_non_positive_volume(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    tank = session.query(Tank).filter(Tank.name == "Vincenz").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={"tank_id": str(tank.id), "volume_hl": 0, "at": now.isoformat()},
    )
    assert r.status_code == 422


def test_schedule_rejected_for_merge_partner(client, session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    tank_id = str(session.query(Tank).filter(Tank.name == "Lovis").one().id)
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=120)
    r = client.put(
        f"/api/sude/{partner.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": tank_id,
                    "stage": "fermentation_closed",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=7)).isoformat(),
                }
            ]
        },
    )
    assert r.status_code == 422, r.text
    assert "shares its lead" in r.json()["detail"]


def test_overlapping_occupancy_returns_structured_409(client, session) -> None:
    # Non-wheat leads only: a bare closed-fermentation payload would trip the
    # wheat open-fermentation rule before ever reaching the DB constraint.
    sude = [
        _seeded_lead(session, KELLERBIER),
        _seeded_lead(session, FESTBIER),
    ]
    tank_id = str(session.query(Tank).filter(Tank.name == "Lisa").one().id)
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
    sud_id = str(_seeded_lead(session, KELLERBIER).id)
    tank_id = str(session.query(Tank).filter(Tank.name == "Lisa").one().id)
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


# ---------------------------------------------------------------------------
# Tank administration (Tankverwaltung)


def _location_id(client, name: str) -> str:
    return next(x["id"] for x in client.get("/api/locations").json() if x["name"] == name)


def test_tank_create_and_duplicate_name(client, session) -> None:
    haupt = _location_id(client, "Schänke 4")
    r = client.post(
        "/api/tanks",
        json={"name": "F-NEU-20", "location_id": haupt, "stage": "fermentation_closed", "capacity_hl": 20},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "F-NEU-20"
    assert body["location_id"] == haupt
    assert body["active"] is True

    dup = client.post(
        "/api/tanks",
        json={"name": "F-NEU-20", "location_id": haupt, "stage": "storage", "capacity_hl": 10},
    )
    assert dup.status_code == 409, dup.text
    assert "vergeben" in dup.json()["detail"]


def test_tank_rename_and_capacity_change_when_idle(client, session) -> None:
    idle = session.query(Tank).filter(Tank.name == "Striezi Keller 4").one()  # never seeded busy
    r = client.patch(
        f"/api/tanks/{idle.id}", json={"name": "Striezi 4b", "capacity_hl": 12}
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Striezi 4b"
    assert r.json()["capacity_hl"] == 12


def test_tank_stage_change_blocked_while_occupied(client, session) -> None:
    busy = session.query(Tank).filter(Tank.name == "Vincenz").one()  # running storage occ
    r = client.patch(f"/api/tanks/{busy.id}", json={"stage": "ausschank"})
    assert r.status_code == 409, r.text
    assert "nicht geändert" in r.json()["detail"]

    rename_only = client.patch(f"/api/tanks/{busy.id}", json={"name": "Vincenzb"})
    assert rename_only.status_code == 200, rename_only.text


def test_tank_capacity_cannot_drop_below_load(client, session) -> None:
    busy = session.query(Tank).filter(Tank.name == "Vincenz").one()  # holds 15 hl Kellerbier
    r = client.patch(f"/api/tanks/{busy.id}", json={"capacity_hl": 10})
    assert r.status_code == 409, r.text
    assert "Kapazität" in r.json()["detail"]

    ok = client.patch(f"/api/tanks/{busy.id}", json={"capacity_hl": 20})
    assert ok.status_code == 200, ok.text


def test_tank_delete_refused_while_occupied(client, session) -> None:
    busy = session.query(Tank).filter(Tank.name == "Vincenz").one()
    r = client.delete(f"/api/tanks/{busy.id}")
    assert r.status_code == 409, r.text
    assert "Belegungen" in r.json()["detail"]


def test_tank_delete_with_history_deactivates(client, session) -> None:
    # Lisa carries only the Kellerbier's PAST fermentation occupancy.
    tank = session.query(Tank).filter(Tank.name == "Lisa").one()
    r = client.delete(f"/api/tanks/{tank.id}")
    assert r.status_code == 204, r.text

    listed = {t["name"]: t for t in client.get("/api/tanks").json()}
    assert listed["Lisa"]["active"] is False

    # Reactivating brings it back for pickers.
    back = client.patch(f"/api/tanks/{tank.id}", json={"active": True})
    assert back.status_code == 200
    assert back.json()["active"] is True


def test_tank_delete_without_history_removes(client, session) -> None:
    created = client.post(
        "/api/tanks",
        json={
            "name": "TEMP-1",
            "location_id": _location_id(client, "Striezi Keller"),
            "stage": "storage",
            "capacity_hl": 5,
        },
    ).json()
    r = client.delete(f"/api/tanks/{created['id']}")
    assert r.status_code == 204, r.text
    names = [t["name"] for t in client.get("/api/tanks").json()]
    assert "TEMP-1" not in names


def test_list_sude_exposes_persistent_process_warnings(client, session) -> None:
    # Park the Kellerbier in an Ausschank tank without any completed
    # fermentation — the yeast warning must survive into plain reads so the
    # Kellerblick can mark the Sud.
    lead = _seeded_lead(session, KELLERBIER)
    a50 = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.put(
        f"/api/sude/{lead.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(a50.id),
                    "stage": "ausschank",
                    "start_at": start.isoformat(),
                    "end_at": None,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text

    listed = client.get("/api/sude").json()
    flagged = next(s for s in listed if s["id"] == str(lead.id))
    assert any("Gärzeit" in w for w in flagged["warnings"]), flagged["warnings"]

    # The seeded Weizen ran its open fermentation correctly — no flag.
    weizen = next(
        s
        for s in listed
        if s["recipe"]["beer_style"] == "Weizen" and s["merged_into_sud_id"] is None
    )
    assert weizen["warnings"] == []


# ---------------------------------------------------------------------------
# Standorte (locations)


def test_locations_seeded_in_order(client) -> None:
    body = client.get("/api/locations").json()
    assert [x["name"] for x in body] == [
        "Schänke 4",
        "Kitzmann Keller",
        "Resenscheck Keller",
        "Striezi Keller",
    ]


def test_location_create_rename_and_duplicate(client) -> None:
    r = client.post("/api/locations", json={"name": "Festzelt"})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["position"] == 5

    dup = client.post("/api/locations", json={"name": "Festzelt"})
    assert dup.status_code == 409
    assert "vergeben" in dup.json()["detail"]

    renamed = client.patch(
        f"/api/locations/{created['id']}", json={"name": "Bergkirchweih"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Bergkirchweih"

    # New tanks can live at the new location right away.
    tank = client.post(
        "/api/tanks",
        json={
            "name": "FEST-10",
            "location_id": created["id"],
            "stage": "ausschank",
            "capacity_hl": 10,
        },
    )
    assert tank.status_code == 201, tank.text
    assert tank.json()["location_id"] == created["id"]


def test_location_delete_only_when_empty(client) -> None:
    haupt = _location_id(client, "Schänke 4")
    blocked = client.delete(f"/api/locations/{haupt}")
    assert blocked.status_code == 409, blocked.text
    assert "Tanks" in blocked.json()["detail"]

    fresh = client.post("/api/locations", json={"name": "Leerstand"}).json()
    gone = client.delete(f"/api/locations/{fresh['id']}")
    assert gone.status_code == 204
    names = [x["name"] for x in client.get("/api/locations").json()]
    assert "Leerstand" not in names


# ---------------------------------------------------------------------------
# Tank lock (Schloss, 2026-08-03: protects master data, not occupancies)


def test_locked_tank_rejects_edits_and_removal_but_not_beer(client, session) -> None:
    tank = session.query(Tank).filter(Tank.name == "Benjamin").one()

    locked = client.patch(f"/api/tanks/{tank.id}", json={"locked": True})
    assert locked.status_code == 200, locked.text
    assert locked.json()["locked"] is True

    renamed = client.patch(f"/api/tanks/{tank.id}", json={"name": "Benjaminb"})
    assert renamed.status_code == 409, renamed.text
    assert "gesperrt" in renamed.json()["detail"]

    removed = client.delete(f"/api/tanks/{tank.id}")
    assert removed.status_code == 409, removed.text
    assert "gesperrt" in removed.json()["detail"]

    # Beer keeps flowing: scheduling into a locked tank stays allowed.
    lead = _seeded_lead(session, KELLERBIER)
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=500)
    scheduled = client.put(
        f"/api/sude/{lead.id}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(tank.id),
                    "stage": "storage",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=7)).isoformat(),
                }
            ]
        },
    )
    assert scheduled.status_code == 200, scheduled.text

    # Unlocking is always possible; edits work again afterwards.
    unlocked = client.patch(f"/api/tanks/{tank.id}", json={"locked": False})
    assert unlocked.status_code == 200
    renamed_ok = client.patch(f"/api/tanks/{tank.id}", json={"name": "Benjaminb"})
    assert renamed_ok.status_code == 200, renamed_ok.text


# ---------------------------------------------------------------------------
# Phase 3: recipe versioning + per-Sud overrides


def test_recipe_new_version_increments_and_keeps_old_suds(client, session) -> None:
    old_kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    existing_sud = _seeded_lead(session, KELLERBIER)

    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Keller Hell",
            "name": "Kellerbier (v2, längere Lagerung)",
            "fermentation_duration_days": 7,
            "open_fermentation_required": False,
            "storage_duration_days": 28,
            "max_storage_duration_days": 70,
            "created_by": "test",
            "notes": "Lagerdauer nach Brauereimeister-Session angepasst.",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 2
    assert body["created_by"] == "test"

    # The old version stays listed (history), the existing Sud keeps its link.
    listed = client.get("/api/recipes").json()
    kellerbier_versions = [
        x["version"] for x in listed if x["beer_style"] == "Keller Hell"
    ]
    assert sorted(kellerbier_versions) == [1, 2]
    session.refresh(existing_sud)
    assert existing_sud.recipe_id == old_kellerbier.id


def test_recipe_open_fermentation_requires_duration(client) -> None:
    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Weizen",
            "name": "Weizen kaputt",
            "fermentation_duration_days": 7,
            "open_fermentation_required": True,
            "storage_duration_days": 14,
            "max_storage_duration_days": 45,
        },
    )
    assert r.status_code == 422, r.text
    assert "offenen Gärung" in r.json()["detail"]


def test_recipe_max_storage_must_cover_storage(client) -> None:
    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Spezialsud",
            "name": "Special kaputt",
            "fermentation_duration_days": 7,
            "storage_duration_days": 30,
            "max_storage_duration_days": 20,
        },
    )
    assert r.status_code == 422, r.text
    assert "Lagerdauer" in r.json()["detail"]


def test_sud_overrides_drive_derived_dates_and_warnings(client, session) -> None:
    # A Sud with shortened closed fermentation: the derived end date and the
    # yeast warning must both follow the override, not the recipe.
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    ferm_tank = session.query(Tank).filter(Tank.name == "Lovis").one()
    a50 = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)

    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier.id),
            "brew_at": _brew_at(date.today()),
            "recipe_overrides": {"fermentation_duration_days": 3},
            "initial_occupancy": {
                "tank_id": str(ferm_tank.id),
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
                # end_at omitted: must derive from the OVERRIDE (3 days).
            },
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["recipe_overrides"] == {"fermentation_duration_days": 3}
    occ_end = datetime.fromisoformat(
        body["occupancies"][0]["end_at"].replace("Z", "+00:00")
    )
    assert occ_end == start + timedelta(days=3)

    # After the (shortened) fermentation completed, Ausschank raises no
    # yeast warning — the override says 3 days are enough for this batch.
    r = client.post(
        f"/api/sude/{body['id']}/transfer",
        json={
            "start_at": (start + timedelta(days=3)).isoformat(),
            "end_at": None,
            "allocations": [{"tank_id": str(a50.id), "volume_hl": 15.0}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []


def test_storage_override_drives_transfer_end_date(client, session) -> None:
    # Transfer to storage with end_at omitted must derive from the Sud's
    # storage override, not the recipe (review finding, night 2).
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    ferm_tank = session.query(Tank).filter(Tank.name == "Lovis").one()
    storage_tank = session.query(Tank).filter(Tank.name == "Benjamin").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=90)

    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier.id),
            "brew_at": _brew_at(date.today()),
            "recipe_overrides": {"storage_duration_days": 10},
            "initial_occupancy": {
                "tank_id": str(ferm_tank.id),
                "stage": "fermentation_closed",
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(days=7)).isoformat(),
            },
        },
    ).json()

    r = client.post(
        f"/api/sude/{created['id']}/transfer",
        json={
            "start_at": (start + timedelta(days=7)).isoformat(),
            "end_at": None,
            "allocations": [{"tank_id": str(storage_tank.id)}],
        },
    )
    assert r.status_code == 200, r.text
    storage_occ = next(
        o for o in r.json()["occupancies"] if o["stage"] == "storage"
    )
    end = datetime.fromisoformat(storage_occ["end_at"].replace("Z", "+00:00"))
    assert end == start + timedelta(days=7) + timedelta(days=10)  # override, not 21


def test_schedule_respects_overrides_and_keeps_them(client, session) -> None:
    # PUT /schedule on an overridden Sud: warnings judge against the
    # override, and the overrides survive the wholesale replacement.
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    ferm_tank = session.query(Tank).filter(Tank.name == "Lovis").one()
    a50 = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=120)

    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(kellerbier.id),
            "brew_at": _brew_at(date.today()),
            "recipe_overrides": {"fermentation_duration_days": 3},
        },
    ).json()

    # 3 days closed fermentation (matches the override, NOT the 7-day
    # recipe) followed by Ausschank: no yeast warning may fire.
    r = client.put(
        f"/api/sude/{created['id']}/schedule",
        json={
            "occupancies": [
                {
                    "tank_id": str(ferm_tank.id),
                    "stage": "fermentation_closed",
                    "start_at": start.isoformat(),
                    "end_at": (start + timedelta(days=3)).isoformat(),
                },
                {
                    "tank_id": str(a50.id),
                    "stage": "ausschank",
                    "start_at": (start + timedelta(days=3)).isoformat(),
                    "end_at": None,
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    assert r.json()["recipe_overrides"] == {"fermentation_duration_days": 3}

    listed = client.get("/api/sude").json()
    entry = next(s for s in listed if s["id"] == created["id"])
    assert entry["recipe_overrides"] == {"fermentation_duration_days": 3}
    assert entry["warnings"] == []


def test_open_fermentation_override_drives_end_and_warning(client, session) -> None:
    wheat = session.query(Recipe).filter(Recipe.beer_style == WEIZEN).one()
    open_tank = session.query(Tank).filter(Tank.name == "Offener Gärbottich").one()
    closed_tank = session.query(Tank).filter(Tank.name == "Lovis").one()
    base = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=150)

    created = client.post(
        "/api/sude",
        json={
            "recipe_id": str(wheat.id),
            "brew_at": _brew_at(date.today()),
            "recipe_overrides": {"open_fermentation_duration_days": 2},
            "initial_occupancy": {
                "tank_id": str(open_tank.id),
                "stage": "fermentation_open",
                "start_at": base.isoformat(),
                # end_at omitted: must derive 2 days from the override.
            },
        },
    ).json()
    occ_end = datetime.fromisoformat(
        created["occupancies"][0]["end_at"].replace("Z", "+00:00")
    )
    assert occ_end == base + timedelta(days=2)

    # After the (shortened) open fermentation the move into the closed
    # fermenter is warning-free — 2 days satisfy this Sud's own rule.
    r = client.post(
        f"/api/sude/{created['id']}/transfer",
        json={
            "start_at": (base + timedelta(days=2)).isoformat(),
            "end_at": None,
            "allocations": [{"tank_id": str(closed_tank.id)}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []


def test_recipe_version_collision_hits_db_constraint(client, session) -> None:
    # The read-then-insert race resolves at uq_recipes_style_version: the
    # loser gets the structured 409, never a silent duplicate version.
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == KELLERBIER).one()
    )
    session.add(
        Recipe(
            beer_style=KELLERBIER,
            version=2,
            name="Racing v2",
            fermentation_duration_days=7,
            open_fermentation_required=False,
            storage_duration_days=21,
            max_storage_duration_days=60,
        )
    )
    session.commit()

    dupe = Recipe(
        beer_style=KELLERBIER,
        version=2,
        name="Racing v2 (loser)",
        fermentation_duration_days=7,
        open_fermentation_required=False,
        storage_duration_days=21,
        max_storage_duration_days=60,
    )
    session.add(dupe)
    with pytest.raises(IntegrityError) as excinfo:
        session.commit()
    session.rollback()
    assert "uq_recipes_style_version" in str(excinfo.value)
    assert kellerbier.version == 1


def test_recipe_ingredients_roundtrip(client) -> None:
    # Brew sheet aligned with Bierrezepte.xlsx (2026-08-04): malts with
    # maltster, hop additions with free-text timing and alpha acid, mash
    # steps, brewing water, boil time, carbonation and pitching notes all
    # persist through create and list.
    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Keller Hell",
            "name": "Kellerbier (mit Schüttung)",
            "fermentation_duration_days": 7,
            "storage_duration_days": 21,
            "max_storage_duration_days": 60,
            "malts": [
                {"name": "Pilsner Malz", "kg": 250, "maelzerei": "BM"},
                {"name": "Münchner Malz", "kg": 60},
            ],
            "hop_gaben": [
                {
                    "name": "Perle",
                    "gramm": 1800,
                    "zeitpunkt": "Kochbeginn",
                    "alpha_prozent": 6.5,
                },
                {"name": "Tettnanger", "gramm": 600, "zeitpunkt": "nach 50 min"},
            ],
            "maischplan": [
                {"schritt": "Einmaischen", "temp_c": 61.5, "dauer_min": 10},
                {"schritt": "Rast", "temp_c": 62.5, "dauer_min": 45},
                {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
                {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
            ],
            "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
            "yeast": "3470 Wagner",
            "original_gravity_plato": 12.5,
            "ibu": 24,
            "color_ebc": 11,
            "kochzeit_min": 70,
            "karbonisierung_g_l": 4.5,
            "anstellhinweis": "bei 9,5 Grad anstellen",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["malts"][0] == {
        "name": "Pilsner Malz",
        "kg": 250,
        "maelzerei": "BM",
    }
    assert body["hop_gaben"][0]["alpha_prozent"] == 6.5
    assert body["hop_gaben"][1]["zeitpunkt"] == "nach 50 min"
    assert body["yeast"] == "3470 Wagner"
    assert body["original_gravity_plato"] == 12.5

    listed = client.get("/api/recipes").json()
    fresh = next(x for x in listed if x["id"] == body["id"])
    assert len(fresh["malts"]) == 2
    assert len(fresh["hop_gaben"]) == 2
    assert [r["schritt"] for r in fresh["maischplan"]] == [
        "Einmaischen",
        "Rast",
        "Rast",
        "Abmaischen",
    ]
    assert fresh["maischplan"][1]["temp_c"] == 62.5
    assert fresh["wasser"] == {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]}
    assert fresh["kochzeit_min"] == 70
    assert fresh["karbonisierung_g_l"] == 4.5
    assert fresh["anstellhinweis"] == "bei 9,5 Grad anstellen"
    assert fresh["ibu"] == 24


def test_tank_withdraw_distributes_proportionally(client, session) -> None:
    # Blending (2026-08-04, sortenrein seit 2026-08-05): zwei Weizen-Sude
    # (15 + 10 hl nach einer Fassabfüllung) teilen sich Bergtank 120 hl; eine
    # Tankbuchung über 10 hl verteilt sich im Verhältnis 3:2.
    weizen = _seeded_lead(session, WEIZEN)
    a120 = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    zweiter = _api_sud(client, session, WEIZEN, "Greta", start - timedelta(days=20))
    ferm_tank = session.query(Tank).filter(Tank.name == "Greta").one()
    r = client.post(
        f"/api/sude/{zweiter['id']}/withdraw",
        json={
            "tank_id": str(ferm_tank.id),
            "volume_hl": 5,
            "at": (start - timedelta(days=15)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text

    r = _transfer(client, weizen.id, [{"tank_id": str(a120.id), "volume_hl": 15}], start)
    assert r.status_code == 200, r.text
    r = _transfer(
        client, zweiter["id"], [{"tank_id": str(a120.id), "volume_hl": 10}], start
    )
    assert r.status_code == 200, r.text

    at = (start + timedelta(days=1)).isoformat()
    r = client.post(
        f"/api/tanks/{a120.id}/withdraw",
        json={"volume_hl": 10, "at": at, "kind": "ausschank"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    per_sud = {s["id"]: s["withdrawals"][-1]["volume_hl"] for s in body}
    assert per_sud[str(weizen.id)] == 6
    assert per_sud[zweiter["id"]] == 4
    assert all(s["withdrawals"][-1]["kind"] == "ausschank" for s in body)


def test_tank_withdraw_finishes_emptied_sude(client, session) -> None:
    # Auto-Abschluss: Ausschank 25 hl + Schwund 5 hl leeren den
    # Festbier-Doppelsud — Lead UND Partner stehen auf `served`, die
    # Belegung endet.
    festbier = _seeded_lead(session, FESTBIER)
    a100 = session.query(Tank).filter(Tank.name == "Bergtank 100 hl").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    r = _transfer(
        client, festbier.id, [{"tank_id": str(a100.id), "volume_hl": 30}], start
    )
    assert r.status_code == 200, r.text

    at = (start + timedelta(days=1)).isoformat()
    r = client.post(
        f"/api/tanks/{a100.id}/withdraw",
        json={"volume_hl": 25, "at": at, "kind": "ausschank"},
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "in_ausschank"

    r = client.post(
        f"/api/tanks/{a100.id}/withdraw",
        json={"volume_hl": 5, "at": at, "kind": "schwund"},
    )
    assert r.status_code == 200, r.text
    body = r.json()[0]
    assert body["status"] == "served"
    ausschank_occ = next(o for o in body["occupancies"] if o["stage"] == "ausschank")
    assert ausschank_occ["end_at"] is not None

    partner = session.query(Sud).filter(Sud.merged_into_sud_id == festbier.id).one()
    session.refresh(partner)
    assert partner.status.value == "served"


def test_tank_withdraw_validation(client, session) -> None:
    weizen = _seeded_lead(session, WEIZEN)
    a120 = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    a50 = session.query(Tank).filter(Tank.name == "Kitzmann vorne").one()
    storage = session.query(Tank).filter(Tank.name == "Benjamin").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    r = _transfer(client, weizen.id, [{"tank_id": str(a120.id), "volume_hl": 15}], start)
    assert r.status_code == 200, r.text
    at = (start + timedelta(days=1)).isoformat()

    over = client.post(
        f"/api/tanks/{a120.id}/withdraw",
        json={"volume_hl": 16, "at": at, "kind": "ausschank"},
    )
    assert over.status_code == 409, over.text
    assert "nur 15 hl" in over.json()["detail"]

    empty = client.post(
        f"/api/tanks/{a50.id}/withdraw",
        json={"volume_hl": 1, "at": at, "kind": "ausschank"},
    )
    assert empty.status_code == 422, empty.text

    wrong_stage = client.post(
        f"/api/tanks/{storage.id}/withdraw",
        json={"volume_hl": 1, "at": at, "kind": "ausschank"},
    )
    assert wrong_stage.status_code == 422, wrong_stage.text
    assert "Ausschanktank" in wrong_stage.json()["detail"]


def test_tank_withdraw_kegs_stay_summable(client, session) -> None:
    # Fassabfüllung am Tank: hl aus Stückzahlen, die Stückzahlen hängen an
    # genau EINER Teilbuchung, damit Summen über alle Buchungen stimmen.
    weizen = _seeded_lead(session, WEIZEN)
    a120 = session.query(Tank).filter(Tank.name == "Bergtank 120 hl").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=60)
    zweiter = _api_sud(client, session, WEIZEN, "Anouk", start - timedelta(days=20))
    _transfer(client, weizen.id, [{"tank_id": str(a120.id), "volume_hl": 15}], start)
    _transfer(client, zweiter["id"], [{"tank_id": str(a120.id), "volume_hl": 15}], start)

    at = (start + timedelta(days=1)).isoformat()
    r = client.post(
        f"/api/tanks/{a120.id}/withdraw",
        json={"at": at, "kind": "keg_fill", "kegs": [{"size_l": 50, "count": 6}]},
    )
    assert r.status_code == 200, r.text
    rows = [s["withdrawals"][-1] for s in r.json()]
    assert sum(w["volume_hl"] for w in rows) == 3.0
    keg_rows = [w for w in rows if w["keg_counts"]]
    assert len(keg_rows) == 1
    assert keg_rows[0]["keg_counts"] == [{"size_l": 50, "count": 6}]


def test_new_beer_style_starts_at_version_one(client) -> None:
    # Free styles (2026-08-04): a brand-new beer name simply starts its
    # own version history — that is how Collab beers get added.
    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Collab Zebra",
            "name": "Collab Zebra",
            "fermentation_duration_days": 7,
            "storage_duration_days": 14,
            "max_storage_duration_days": 45,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["active"] is True


def test_style_active_archives_all_versions(client) -> None:
    r = client.post(
        "/api/recipes/style-active",
        json={"beer_style": "Keller Hell", "active": False},
    )
    assert r.status_code == 200, r.text
    assert all(x["active"] is False for x in r.json())

    listed = client.get("/api/recipes").json()
    kh = [x for x in listed if x["beer_style"] == "Keller Hell"]
    assert kh and all(x["active"] is False for x in kh)

    # A new version of an archived beer stays archived …
    r2 = client.post(
        "/api/recipes",
        json={
            "beer_style": "Keller Hell",
            "name": "Keller Hell (Test)",
            "fermentation_duration_days": 7,
            "storage_duration_days": 21,
            "max_storage_duration_days": 60,
        },
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["active"] is False

    # … and reactivating brings the whole style back.
    r3 = client.post(
        "/api/recipes/style-active",
        json={"beer_style": "Keller Hell", "active": True},
    )
    assert r3.status_code == 200
    assert all(x["active"] is True for x in r3.json())

    r4 = client.post(
        "/api/recipes/style-active",
        json={"beer_style": "Gibtsnicht", "active": False},
    )
    assert r4.status_code == 404


def test_style_farbe_paints_all_versions_and_inherits(client) -> None:
    # Bierfarbe (2026-08-06): stilweit wie das Archiv-Flag; neue Versionen
    # erben sie, kaputte Hex-Werte sind ein 422.
    r = client.post(
        "/api/recipes/style-farbe",
        json={"beer_style": "Keller Hell", "farbe": "#123abc"},
    )
    assert r.status_code == 200, r.text
    assert all(x["farbe"] == "#123abc" for x in r.json())

    neu = client.post(
        "/api/recipes",
        json={
            "beer_style": "Keller Hell",
            "name": "Keller Hell (Farbtest)",
            "fermentation_duration_days": 7,
            "storage_duration_days": 21,
            "max_storage_duration_days": 60,
        },
    )
    assert neu.status_code == 201, neu.text
    assert neu.json()["farbe"] == "#123abc"

    kaputt = client.post(
        "/api/recipes/style-farbe",
        json={"beer_style": "Keller Hell", "farbe": "gold"},
    )
    assert kaputt.status_code == 422

    fehlt = client.post(
        "/api/recipes/style-farbe",
        json={"beer_style": "Gibtsnicht", "farbe": "#123abc"},
    )
    assert fehlt.status_code == 404

    # Die Farbe hängt auch am Sud (über dessen Rezept) — der Zeitplan
    # liest sie dort.
    sude = client.get("/api/sude").json()
    keller_sud = next(s for s in sude if s["recipe"]["beer_style"] == "Keller Hell")
    assert keller_sud["recipe"]["farbe"] == "#123abc"


def test_recipe_hop_timing_requires_text(client) -> None:
    # The timing is free text as on the paper sheet — an empty one is a
    # data-entry slip, not a valid Gabe.
    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Spezialsud",
            "name": "Gabe ohne Zeitpunkt",
            "fermentation_duration_days": 7,
            "storage_duration_days": 21,
            "max_storage_duration_days": 60,
            "hop_gaben": [{"name": "Perle", "gramm": 500, "zeitpunkt": ""}],
        },
    )
    assert r.status_code == 422


def test_recipe_ingredients_validation(client) -> None:
    r = client.post(
        "/api/recipes",
        json={
            "beer_style": "Spezialsud",
            "name": "Kaputte Schüttung",
            "fermentation_duration_days": 7,
            "storage_duration_days": 21,
            "max_storage_duration_days": 60,
            "malts": [{"name": "Pilsner", "kg": 0}],
        },
    )
    assert r.status_code == 422


def test_keg_counts_compute_volume_and_persist(client, session) -> None:
    # 2026-08-04: keg fills entered as counts per size; hl computed.
    lead = _seeded_lead(session, KELLERBIER)  # 15 hl in Vincenz
    tank = session.query(Tank).filter(Tank.name == "Vincenz").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "at": now.isoformat(),
            "kind": "keg_fill",
            "kegs": [
                {"size_l": 50, "count": 4},
                {"size_l": 30, "count": 2},
            ],
        },
    )
    assert r.status_code == 200, r.text
    w = r.json()["withdrawals"][-1]
    assert w["volume_hl"] == 2.6  # (4*50 + 2*30) / 100
    assert w["keg_counts"] == [
        {"size_l": 50, "count": 4},
        {"size_l": 30, "count": 2},
    ]


def test_keg_counts_validation(client, session) -> None:
    lead = _seeded_lead(session, KELLERBIER)
    tank = session.query(Tank).filter(Tank.name == "Vincenz").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    # Kegs on a pour are rejected …
    r1 = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "at": now.isoformat(),
            "kind": "ausschank",
            "kegs": [{"size_l": 50, "count": 1}],
        },
    )
    assert r1.status_code == 422, r1.text
    assert "Fassabfüllungen" in r1.json()["detail"]

    # … as is giving both a volume and counts …
    r2 = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "at": now.isoformat(),
            "kind": "keg_fill",
            "volume_hl": 2,
            "kegs": [{"size_l": 50, "count": 1}],
        },
    )
    assert r2.status_code == 422, r2.text
    assert "nicht beides" in r2.json()["detail"]

    # … and neither.
    r3 = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "at": now.isoformat(),
            "kind": "keg_fill",
        },
    )
    assert r3.status_code == 422, r3.text

    # Overdraw via kegs hits the remaining-volume rule (15 hl remain).
    r4 = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={
            "tank_id": str(tank.id),
            "at": now.isoformat(),
            "kind": "keg_fill",
            "kegs": [{"size_l": 50, "count": 40}],
        },
    )
    assert r4.status_code == 409, r4.text
