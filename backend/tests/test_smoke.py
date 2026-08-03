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
    BeerStyle,
    Recipe,
    Sud,
    Tank,
    TankOccupancy,
    TankStage,
)


def test_db_rejects_duplicate_style_year_number(session) -> None:
    # The constraint from migration 0005 turns a concurrent-create race into
    # a rejected insert instead of a silently duplicated Sud-Nr.
    kellerbier = (
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.KELLERBIER).one()
    )
    existing = (
        session.query(Sud).filter(Sud.beer_style == BeerStyle.KELLERBIER).one()
    )
    dupe = Sud(
        recipe_id=kellerbier.id,
        beer_style=BeerStyle.KELLERBIER,
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
    tank = session.query(Tank).filter(Tank.name == "F-OPEN-15").one()
    assert isinstance(tank.stage, TankStage)
    occ = session.query(TankOccupancy).first()
    assert isinstance(occ.stage, TankStage)
    sud = session.query(Sud).first()
    assert isinstance(sud.beer_style, BeerStyle)


def test_seed_creates_full_inventory(session) -> None:
    assert session.query(Tank).count() == 21
    assert session.query(Recipe).count() == 4
    assert session.query(Sud).count() == 4
    assert session.query(TankOccupancy).count() == 6


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
    assert len(body) == 21
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
    sud_id = str(_seeded_lead(session, BeerStyle.KELLERBIER).id)
    tank_id = str(session.query(Tank).filter(Tank.name == "F-30-1").one().id)
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


def _seeded_lead(session, style: BeerStyle) -> Sud:
    return (
        session.query(Sud)
        .join(Recipe, Recipe.id == Sud.recipe_id)
        .filter(Recipe.beer_style == style, Sud.merged_into_sud_id.is_(None))
        .one()
    )


def test_merge_partner_happy_path(client, session) -> None:
    # The Kellerbier lead sits in 30-hl tanks with 15 hl — room for one partner.
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
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
    lead = _seeded_lead(session, BeerStyle.FESTBIER)
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    wheat_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.WHEAT).one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)

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
    weizen_lead = _seeded_lead(session, BeerStyle.WHEAT)
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
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.SPECIAL).one().id
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
    lead = _seeded_lead(session, BeerStyle.FESTBIER)  # 15 + 15 hl partner
    small_tank = session.query(Tank).filter(Tank.name == "F-15-2").one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    tank_id = str(session.query(Tank).filter(Tank.name == "F-15-2").one().id)
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


def _transfer(client, sud_id, allocations, start, end=None):
    return client.post(
        f"/api/sude/{sud_id}/transfer",
        json={
            "start_at": start.isoformat(),
            "end_at": end.isoformat() if end else None,
            "allocations": allocations,
        },
    )


def test_transfer_to_storage_happy_path(client, session) -> None:
    # Weizen sits in closed fermentation (F-15-1, ends +4d); move it on.
    lead = _seeded_lead(session, BeerStyle.WHEAT)
    target = session.query(Tank).filter(Tank.name == "S-30-3").one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    ferm_tank = session.query(Tank).filter(Tank.name == "F-30-3").one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    other_storage = session.query(Tank).filter(Tank.name == "S-30-4").one()
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
    lead = _seeded_lead(session, BeerStyle.WHEAT)
    a_tank = session.query(Tank).filter(Tank.name == "A2-35-1").one()
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = _transfer(
        client, lead.id, [{"tank_id": str(a_tank.id), "volume_hl": 15.0}], start
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_ausschank"
    assert any("Hefe" in w for w in body["warnings"]), body["warnings"]


def test_transfer_rejects_partner(client, session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    target = session.query(Tank).filter(Tank.name == "S-30-4").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)

    r = _transfer(client, partner.id, [{"tank_id": str(target.id)}], start)
    assert r.status_code == 422, r.text
    assert "transfer the lead" in r.json()["detail"]


def test_transfer_rejects_multi_target_before_ausschank(client, session) -> None:
    lead = _seeded_lead(session, BeerStyle.WHEAT)
    t1 = session.query(Tank).filter(Tank.name == "S-30-4").one()
    t2 = session.query(Tank).filter(Tank.name == "S-30-5").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=5)

    r = _transfer(
        client,
        lead.id,
        [{"tank_id": str(t1.id)}, {"tank_id": str(t2.id)}],
        start,
    )
    assert r.status_code == 422, r.text
    assert "stay together" in r.json()["detail"]


def test_transfer_split_to_two_ausschank_tanks(client, session) -> None:
    # The merged Festbier batch (30 hl) splits 20/10 across two Ausschank tanks.
    lead = _seeded_lead(session, BeerStyle.FESTBIER)
    a100 = session.query(Tank).filter(Tank.name == "A-100").one()
    a80 = session.query(Tank).filter(Tank.name == "A-80").one()
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
    lead = _seeded_lead(session, BeerStyle.FESTBIER)
    a100 = session.query(Tank).filter(Tank.name == "A-100").one()
    a80 = session.query(Tank).filter(Tank.name == "A-80").one()
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
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.SPECIAL).one().id
    )
    a35 = session.query(Tank).filter(Tank.name == "A2-35-1").one()
    ferm_tanks = ["F-30-3", "F-30-4", "F-30-5"]
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
    # The generic schedule endpoint must apply the same headroom rule. The
    # payloads keep each Sud's completed fermentation history so the
    # yeast-free rule is satisfied and headroom is the deciding factor.
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    weizen = _seeded_lead(session, BeerStyle.WHEAT)
    a35 = session.query(Tank).filter(Tank.name == "A2-35-2").one()
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

    r2 = client.put(
        f"/api/sude/{weizen.id}/schedule",
        json={
            "occupancies": _existing_occupancies_payload(weizen)
            + [
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


def test_schedule_allows_stage_regression(client, session) -> None:
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    ferm = session.query(Tank).filter(Tank.name == "F-30-1").one()
    storage = session.query(Tank).filter(Tank.name == "S-30-1").one()
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
    weizen = _seeded_lead(session, BeerStyle.WHEAT)
    ferm = session.query(Tank).filter(Tank.name == "F-15-2").one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    a50 = session.query(Tank).filter(Tank.name == "A-50").one()
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
    assert any("Hefe" in w for w in r.json()["warnings"])


def test_create_warns_wheat_starting_in_closed_fermenter(client, session) -> None:
    wheat_recipe = (
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.WHEAT).one()
    )
    ferm = session.query(Tank).filter(Tank.name == "F-15-2").one()
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
    recipe_id = str(
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.SPECIAL).one().id
    )
    small_storage = session.query(Tank).filter(Tank.name == "S2-10-1").one()
    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=400)

    r = client.post(
        "/api/sude",
        json={
            "recipe_id": recipe_id,
            "brew_at": _brew_at(date.today()),
            "initial_occupancy": {
                "tank_id": str(small_storage.id),
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    a50 = session.query(Tank).filter(Tank.name == "A-50").one()
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
        session.query(Recipe).filter(Recipe.beer_style == BeerStyle.WHEAT).one()
    )
    open_tank = session.query(Tank).filter(Tank.name == "F-OPEN-15").one()
    closed_tank = session.query(Tank).filter(Tank.name == "F-15-2").one()
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
    target = session.query(Tank).filter(Tank.name == "S-30-5").one()
    start = datetime.now(timezone.utc).replace(microsecond=0)

    r = _transfer(client, created["id"], [{"tank_id": str(target.id)}], start)
    assert r.status_code == 422, r.text
    assert "schedule it before" in r.json()["detail"]


def test_withdraw_happy_path_and_remaining_volume(client, session) -> None:
    # Kellerbier (15 hl) sits in storage tank S-30-1 right now.
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    tank = session.query(Tank).filter(Tank.name == "S-30-1").one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    storage_tank = session.query(Tank).filter(Tank.name == "S-30-1").one()
    a100 = session.query(Tank).filter(Tank.name == "A-100").one()
    a80 = session.query(Tank).filter(Tank.name == "A-80").one()
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
    weizen = _seeded_lead(session, BeerStyle.WHEAT)
    ferm_tank = session.query(Tank).filter(Tank.name == "F-15-1").one()
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    wrong_tank = session.query(Tank).filter(Tank.name == "A-120").one()
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
    tank = session.query(Tank).filter(Tank.name == "F-30-2").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{partner.id}/withdraw",
        json={"tank_id": str(tank.id), "volume_hl": 1, "at": now.isoformat()},
    )
    assert r.status_code == 422, r.text
    assert "withdraw from the lead" in r.json()["detail"]


def test_withdraw_rejects_non_positive_volume(client, session) -> None:
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    tank = session.query(Tank).filter(Tank.name == "S-30-1").one()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    r = client.post(
        f"/api/sude/{lead.id}/withdraw",
        json={"tank_id": str(tank.id), "volume_hl": 0, "at": now.isoformat()},
    )
    assert r.status_code == 422


def test_schedule_rejected_for_merge_partner(client, session) -> None:
    partner = session.query(Sud).filter(Sud.merged_into_sud_id.is_not(None)).one()
    tank_id = str(session.query(Tank).filter(Tank.name == "F-15-2").one().id)
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
        _seeded_lead(session, BeerStyle.KELLERBIER),
        _seeded_lead(session, BeerStyle.FESTBIER),
    ]
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
    sud_id = str(_seeded_lead(session, BeerStyle.KELLERBIER).id)
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


# ---------------------------------------------------------------------------
# Tank administration (Tankverwaltung)


def _location_id(client, name: str) -> str:
    return next(x["id"] for x in client.get("/api/locations").json() if x["name"] == name)


def test_tank_create_and_duplicate_name(client, session) -> None:
    haupt = _location_id(client, "Hauptkeller")
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
    idle = session.query(Tank).filter(Tank.name == "S2-10-2").one()  # never seeded busy
    r = client.patch(
        f"/api/tanks/{idle.id}", json={"name": "S2-10-2b", "capacity_hl": 12}
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "S2-10-2b"
    assert r.json()["capacity_hl"] == 12


def test_tank_stage_change_blocked_while_occupied(client, session) -> None:
    busy = session.query(Tank).filter(Tank.name == "S-30-1").one()  # running storage occ
    r = client.patch(f"/api/tanks/{busy.id}", json={"stage": "ausschank"})
    assert r.status_code == 409, r.text
    assert "nicht geändert" in r.json()["detail"]

    rename_only = client.patch(f"/api/tanks/{busy.id}", json={"name": "S-30-1b"})
    assert rename_only.status_code == 200, rename_only.text


def test_tank_capacity_cannot_drop_below_load(client, session) -> None:
    busy = session.query(Tank).filter(Tank.name == "S-30-1").one()  # holds 15 hl Kellerbier
    r = client.patch(f"/api/tanks/{busy.id}", json={"capacity_hl": 10})
    assert r.status_code == 409, r.text
    assert "Kapazität" in r.json()["detail"]

    ok = client.patch(f"/api/tanks/{busy.id}", json={"capacity_hl": 20})
    assert ok.status_code == 200, ok.text


def test_tank_delete_refused_while_occupied(client, session) -> None:
    busy = session.query(Tank).filter(Tank.name == "S-30-1").one()
    r = client.delete(f"/api/tanks/{busy.id}")
    assert r.status_code == 409, r.text
    assert "Belegungen" in r.json()["detail"]


def test_tank_delete_with_history_deactivates(client, session) -> None:
    # F-30-1 carries only the Kellerbier's PAST fermentation occupancy.
    tank = session.query(Tank).filter(Tank.name == "F-30-1").one()
    r = client.delete(f"/api/tanks/{tank.id}")
    assert r.status_code == 204, r.text

    listed = {t["name"]: t for t in client.get("/api/tanks").json()}
    assert listed["F-30-1"]["active"] is False

    # Reactivating brings it back for pickers.
    back = client.patch(f"/api/tanks/{tank.id}", json={"active": True})
    assert back.status_code == 200
    assert back.json()["active"] is True


def test_tank_delete_without_history_removes(client, session) -> None:
    created = client.post(
        "/api/tanks",
        json={
            "name": "TEMP-1",
            "location_id": _location_id(client, "Nebenkeller"),
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
    lead = _seeded_lead(session, BeerStyle.KELLERBIER)
    a50 = session.query(Tank).filter(Tank.name == "A-50").one()
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
    assert any("Hefe" in w for w in flagged["warnings"]), flagged["warnings"]

    # The seeded Weizen ran its open fermentation correctly — no flag.
    weizen = next(
        s
        for s in listed
        if s["recipe"]["beer_style"] == "wheat" and s["merged_into_sud_id"] is None
    )
    assert weizen["warnings"] == []


# ---------------------------------------------------------------------------
# Standorte (locations)


def test_locations_seeded_in_order(client) -> None:
    body = client.get("/api/locations").json()
    assert [x["name"] for x in body] == ["Hauptkeller", "Nebenkeller"]


def test_location_create_rename_and_duplicate(client) -> None:
    r = client.post("/api/locations", json={"name": "Festzelt"})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["position"] == 3

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
    haupt = _location_id(client, "Hauptkeller")
    blocked = client.delete(f"/api/locations/{haupt}")
    assert blocked.status_code == 409, blocked.text
    assert "Tanks" in blocked.json()["detail"]

    fresh = client.post("/api/locations", json={"name": "Leerstand"}).json()
    gone = client.delete(f"/api/locations/{fresh['id']}")
    assert gone.status_code == 204
    names = [x["name"] for x in client.get("/api/locations").json()]
    assert "Leerstand" not in names
