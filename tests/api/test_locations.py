"""Location create/patch (`docs/acceptance.md`, "Locations")."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.engine import make_engine
from inventory.db.writes import BakeRequest, ManualMove, record_bake, record_manual_move
from tests.api.probes import login


def _seed_stock_at_location(
    db_path: Path, *, recipe_id: int, size_id: int, location_id: int, quantity: int
) -> None:
    """Bake into Kitchen, then move `quantity` units into `location_id`.

    Bypasses the (not-yet-built) ledger HTTP routes -- this leaf only
    owns catalog -- by calling the persistence write path directly
    against the same database file the test's `client` is using, the
    same way `tests/db` seeds fixtures.
    """
    engine = make_engine(str(db_path))
    try:
        with Session(engine) as session:
            builtins = load_builtin_locations(session)
            record_bake(
                session,
                BakeRequest(
                    recipe_id=recipe_id,
                    baked=date(2024, 1, 1),
                    expires=date(2024, 1, 10),
                    counts={size_id: quantity},
                ),
                now=datetime(2024, 1, 1, tzinfo=UTC),
            )
            record_manual_move(
                session,
                ManualMove(
                    from_location_id=builtins.locations.kitchen_id,
                    to_location_id=location_id,
                    size_id=size_id,
                    quantity=quantity,
                ),
                now=datetime(2024, 1, 1, tzinfo=UTC),
            )
            session.commit()
    finally:
        engine.dispose()


def _create_recipe(client: TestClient) -> dict[str, Any]:
    ingredient = client.post(
        "/api/v1/ingredients",
        json={"name": "Flour", "unit_label": "g", "current_price_cents": 100},
    ).json()
    return client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient["id"], "quantity": 1}],
            "sizes": [
                {
                    "name": "Regular",
                    "portion_weight_g": 10,
                    "price_cents": 100,
                    "typical_yield_count": 1,
                }
            ],
        },
    ).json()


def _builtin_location(client: TestClient, kind: str) -> dict[str, Any]:
    locations = client.get("/api/v1/locations").json()
    return next(location for location in locations if location["kind"] == kind)


def test_create_stand_and_market(client: TestClient) -> None:
    login(client)

    stand = client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"})
    market = client.post("/api/v1/locations", json={"name": "Farmers Market", "kind": "market"})

    assert stand.status_code == 201
    assert stand.json()["active"] is True
    assert market.status_code == 201


def test_create_with_a_builtin_kind_is_rejected(client: TestClient) -> None:
    login(client)

    for kind in ("production", "kitchen", "sold", "waste", "sampled"):
        response = client.post("/api/v1/locations", json={"name": f"Nope {kind}", "kind": kind})
        assert response.status_code == 422, kind


def test_patch_cannot_change_kind(client: TestClient) -> None:
    login(client)
    stand = client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"}).json()

    response = client.patch(f"/api/v1/locations/{stand['id']}", json={"kind": "market"})

    assert response.status_code == 422


def test_rename_or_deactivate_a_builtin_is_rejected(client: TestClient) -> None:
    login(client)
    kitchen = _builtin_location(client, "kitchen")

    renamed = client.patch(f"/api/v1/locations/{kitchen['id']}", json={"name": "New Kitchen"})
    deactivated = client.patch(f"/api/v1/locations/{kitchen['id']}", json={"active": False})

    assert renamed.status_code == 422
    assert renamed.json()["location_name"] == "Kitchen"
    assert deactivated.status_code == 422
    assert deactivated.json()["location_name"] == "Kitchen"


def test_deactivate_a_stand_with_stock_is_rejected_naming_on_hand(
    client: TestClient, db_path: Path
) -> None:
    login(client)
    recipe = _create_recipe(client)
    size_id = recipe["sizes"][0]["id"]
    stand = client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"}).json()

    _seed_stock_at_location(
        db_path, recipe_id=recipe["id"], size_id=size_id, location_id=stand["id"], quantity=3
    )

    response = client.patch(f"/api/v1/locations/{stand['id']}", json={"active": False})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:inventory:problem:location-has-stock"
    assert body["on_hand"] == 3
    assert body["location_name"] == stand["name"]


def test_deactivate_an_empty_stand_succeeds_and_can_be_reactivated(client: TestClient) -> None:
    login(client)
    stand = client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"}).json()

    deactivated = client.patch(f"/api/v1/locations/{stand['id']}", json={"active": False})
    reactivated = client.patch(f"/api/v1/locations/{stand['id']}", json={"active": True})

    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert reactivated.status_code == 200
    assert reactivated.json()["active"] is True


def test_location_name_collision_case_insensitive_is_rejected(client: TestClient) -> None:
    login(client)
    client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"})

    response = client.post("/api/v1/locations", json={"name": "ROADSIDE", "kind": "market"})

    assert response.status_code == 422
    assert response.json()["type"] == "urn:inventory:problem:name-conflict"


def test_patch_rename_collision_reports_the_supplied_colliding_value(client: TestClient) -> None:
    login(client)
    client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"})
    market = client.post(
        "/api/v1/locations", json={"name": "Farmers Market", "kind": "market"}
    ).json()

    response = client.patch(f"/api/v1/locations/{market['id']}", json={"name": "ROADSIDE"})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:inventory:problem:name-conflict"
    assert body["value"] == "ROADSIDE"


def test_patch_empty_name_is_rejected_with_errors_list(client: TestClient) -> None:
    login(client)
    stand = client.post("/api/v1/locations", json={"name": "Roadside", "kind": "stand"}).json()

    response = client.patch(f"/api/v1/locations/{stand['id']}", json={"name": ""})

    assert response.status_code == 422
    assert "errors" in response.json()
