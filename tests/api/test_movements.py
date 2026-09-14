"""Manual movements: insufficient stock, market destination, inactive locations.

`docs/acceptance.md`, "Ledger, stock, and FIFO", "Locations", and
"Corrections".
"""

from typing import Any

from fastapi.testclient import TestClient

from tests.api.ledger_helpers import (
    bake,
    builtin_location_id,
    create_location,
    create_recipe,
    kitchen_id,
    move,
)
from tests.api.probes import login


def _recipe_and_size(client: TestClient) -> tuple[dict[str, Any], int]:
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    return recipe, recipe["sizes"][0]["id"]


def test_move_exceeding_on_hand_returns_422_with_fields_and_writes_nothing(
    client: TestClient,
) -> None:
    login(client)
    recipe, size_id = _recipe_and_size(client)
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 2}],
    )
    stand = create_location(client, "stand", "Stand")
    kitchen = kitchen_id(client)

    entries_before = client.get("/api/v1/entries").json()

    response = move(
        client, from_location_id=kitchen, to_location_id=stand["id"], size_id=size_id, quantity=5
    )

    assert response.status_code == 422
    body = response.json()
    assert body["location_id"] == kitchen
    assert body["size_id"] == size_id
    assert body["on_hand"] == 2
    assert body["requested"] == 5
    assert body["recipe_id"] == recipe["id"]
    assert body["recipe_name"] == recipe["name"]
    assert body["size_name"] == "Only"
    assert body["location_name"] == "Kitchen"

    entries_after = client.get("/api/v1/entries").json()
    assert entries_after == entries_before


def test_move_to_a_market_destination_is_rejected(client: TestClient) -> None:
    login(client)
    recipe, size_id = _recipe_and_size(client)
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 2}],
    )
    market = create_location(client, "market", "Market")
    kitchen = kitchen_id(client)

    response = move(
        client, from_location_id=kitchen, to_location_id=market["id"], size_id=size_id, quantity=1
    )

    assert response.status_code == 422


def test_move_into_an_inactive_stand_is_rejected(client: TestClient) -> None:
    login(client)
    recipe, size_id = _recipe_and_size(client)
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 2}],
    )
    stand = create_location(client, "stand", "Stand")
    kitchen = kitchen_id(client)

    deactivate = client.patch(f"/api/v1/locations/{stand['id']}", json={"active": False})
    assert deactivate.status_code == 200

    response = move(
        client, from_location_id=kitchen, to_location_id=stand["id"], size_id=size_id, quantity=1
    )

    assert response.status_code == 422


def test_move_out_of_an_inactive_stand_succeeds(client: TestClient) -> None:
    """Stock lands at an inactive stand only via undo; a move out of it still works."""
    login(client)
    recipe, size_id = _recipe_and_size(client)
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 3}],
    )
    stand = create_location(client, "stand", "Stand")
    kitchen = kitchen_id(client)

    to_stand = move(
        client, from_location_id=kitchen, to_location_id=stand["id"], size_id=size_id, quantity=3
    )
    assert to_stand.status_code == 201
    drain = move(
        client, from_location_id=stand["id"], to_location_id=kitchen, size_id=size_id, quantity=3
    )
    assert drain.status_code == 201

    deactivate = client.patch(f"/api/v1/locations/{stand['id']}", json={"active": False})
    assert deactivate.status_code == 200

    undo_drain = client.post("/api/v1/reversals", json={"entry_id": drain.json()["entry_id"]})
    assert undo_drain.status_code == 201

    response = move(
        client, from_location_id=stand["id"], to_location_id=kitchen, size_id=size_id, quantity=1
    )

    assert response.status_code == 201


def test_negative_quantity_is_rejected(client: TestClient) -> None:
    login(client)
    _recipe, size_id = _recipe_and_size(client)
    stand = create_location(client, "stand", "Stand")

    response = move(
        client, from_location_id=1, to_location_id=stand["id"], size_id=size_id, quantity=-1
    )

    assert response.status_code == 422


def test_strict_int_rejects_string_and_float_quantity(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    as_string = client.post(
        "/api/v1/movements",
        json={"from_location_id": 1, "to_location_id": stand["id"], "size_id": 1, "quantity": "1"},
    )
    as_float = client.post(
        "/api/v1/movements",
        json={"from_location_id": 1, "to_location_id": stand["id"], "size_id": 1, "quantity": 1.5},
    )

    assert as_string.status_code == 422
    assert as_float.status_code == 422


def test_zero_quantity_is_rejected_by_the_schema(client: TestClient) -> None:
    login(client)
    _recipe, size_id = _recipe_and_size(client)
    kitchen = kitchen_id(client)
    waste = builtin_location_id(client, "waste")

    response = client.post(
        "/api/v1/movements",
        json={
            "from_location_id": kitchen,
            "to_location_id": waste,
            "size_id": size_id,
            "quantity": 0,
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"]
