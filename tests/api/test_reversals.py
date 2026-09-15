"""Undo, as its own endpoint: full restoration, double-undo, and the blocked case.

`docs/acceptance.md`, "Corrections".
"""

from fastapi.testclient import TestClient

from tests.api.ledger_helpers import (
    bake,
    create_location,
    create_recipe,
    kitchen_id,
    market_row,
    move,
)
from tests.api.probes import login


def test_undo_of_a_full_market_visit_restores_stock_and_voids_with_null_profit_in_history(
    client: TestClient,
) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 300, "typical_yield_count": 1}
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 10}],
    )
    market = create_location(client, "market", "Market")

    stock_before = client.get("/api/v1/stock").json()

    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": market["id"],
            "rows": [market_row(size_id, taken=10, returned=3, tossed=1)],
            "revenue_cents": 900,
            "fee_cents": 0,
        },
    )
    assert visit.status_code == 201
    entry_id = visit.json()["entry_id"]

    reversal = client.post("/api/v1/reversals", json={"entry_id": entry_id})
    assert reversal.status_code == 201
    assert reversal.json()["reverses_entry_id"] == entry_id

    stock_after = client.get("/api/v1/stock").json()
    assert stock_after == stock_before

    entries = client.get("/api/v1/entries").json()
    voided_entry = next(entry for entry in entries if entry["entry_id"] == entry_id)
    assert voided_entry["voided"] is True
    assert voided_entry["profit_cents"] is None
    assert voided_entry["revenue_cents"] is None


def test_undo_of_an_already_voided_entry_is_rejected(client: TestClient) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    stand = create_location(client, "stand", "Stand")
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 3}],
    )
    moved = move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=3,
    )
    entry_id = moved.json()["entry_id"]

    first_undo = client.post("/api/v1/reversals", json={"entry_id": entry_id})
    assert first_undo.status_code == 201

    second_undo = client.post("/api/v1/reversals", json={"entry_id": entry_id})
    assert second_undo.status_code == 422


def test_undo_of_a_reversal_is_rejected(client: TestClient) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    stand = create_location(client, "stand", "Stand")
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 3}],
    )
    moved = move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=3,
    )

    reversal = client.post("/api/v1/reversals", json={"entry_id": moved.json()["entry_id"]})
    assert reversal.status_code == 201

    undo_the_reversal = client.post(
        "/api/v1/reversals", json={"entry_id": reversal.json()["entry_id"]}
    )
    assert undo_the_reversal.status_code == 422


def test_manual_drain_after_a_visit_blocks_undo_of_that_visit_with_nothing_changed(
    client: TestClient,
) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 3}],
    )
    market = create_location(client, "market", "Market")

    # An echo visit: everything taken to the market comes straight back,
    # leaving Kitchen's on-hand for this batch exactly as it was before.
    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": market["id"],
            "rows": [market_row(size_id, taken=3, returned=3, tossed=0)],
            "revenue_cents": 0,
            "fee_cents": 0,
        },
    )
    assert visit.status_code == 201
    entry_id = visit.json()["entry_id"]

    waste_id = next(
        location["id"]
        for location in client.get("/api/v1/locations").json()
        if location["kind"] == "waste"
    )
    kitchen = kitchen_id(client)
    drain = move(
        client,
        from_location_id=kitchen,
        to_location_id=waste_id,
        size_id=size_id,
        quantity=3,
    )
    assert drain.status_code == 201

    entries_before = client.get("/api/v1/entries").json()

    undo_response = client.post("/api/v1/reversals", json={"entry_id": entry_id})

    assert undo_response.status_code == 422
    body = undo_response.json()
    assert body["location_id"] == kitchen
    assert body["size_id"] == size_id
    assert body["recipe_id"] == recipe["id"]
    assert body["recipe_name"] == recipe["name"]
    assert body["size_name"] == "Only"
    assert body["location_name"] == "Kitchen"
    entries_after = client.get("/api/v1/entries").json()
    assert entries_after == entries_before
    visit_entry = next(entry for entry in entries_after if entry["entry_id"] == entry_id)
    assert visit_entry["voided"] is False


def test_non_positive_entry_id_is_a_validation_error_not_a_404(client: TestClient) -> None:
    login(client)

    response = client.post("/api/v1/reversals", json={"entry_id": -1})

    assert response.status_code == 422
    assert response.json()["errors"]
