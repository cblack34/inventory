"""History: newest first, with kind, timestamp, voided, location, revenue, profit.

`docs/acceptance.md`, "Profit" (the home-screen history bullet).
"""

from fastapi.testclient import TestClient

from tests.api.ledger_helpers import (
    bake,
    create_location,
    create_recipe,
    kitchen_id,
    move,
    stand_row,
)
from tests.api.probes import login


def test_entries_list_newest_first_with_full_shape(client: TestClient) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 300, "typical_yield_count": 1}
        ],
    )
    size_id = recipe["sizes"][0]["id"]

    bake_response = bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 2}],
    )
    stand = create_location(client, "stand", "Stand")
    move_response = move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=1,
    )
    visit_response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [stand_row(size_id, counted=0)],
            "revenue_cents": 300,
        },
    )
    assert visit_response.status_code == 201

    entries = client.get("/api/v1/entries").json()

    ids_newest_first = [entry["entry_id"] for entry in entries]
    assert ids_newest_first == sorted(ids_newest_first, reverse=True)

    by_id = {entry["entry_id"]: entry for entry in entries}
    bake_entry = by_id[bake_response["entry_id"]]
    move_entry = by_id[move_response.json()["entry_id"]]
    visit_entry = by_id[visit_response.json()["entry_id"]]

    assert bake_entry["kind"] == "bake"
    assert bake_entry["voided"] is False
    assert bake_entry["location_id"] is None
    assert bake_entry["revenue_cents"] is None
    assert bake_entry["profit_cents"] is None

    assert move_entry["kind"] == "manual"
    assert move_entry["location_id"] is None

    assert visit_entry["kind"] == "visit"
    assert visit_entry["voided"] is False
    assert visit_entry["location_id"] == stand["id"]
    assert visit_entry["revenue_cents"] == 300
    # Recipe cost 100 (ingredient price 100 x quantity 1) split over two
    # baked units of the one size gives a 50-cent unit cost; one unit is
    # missing (on-hand 1, counted 0) and sells, so profit is 300 - 50.
    assert visit_entry["profit_cents"] == 250


def test_get_single_entry_matches_the_list_entry(client: TestClient) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    bake_response = bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 1}],
    )

    entry_id = bake_response["entry_id"]
    single = client.get(f"/api/v1/entries/{entry_id}")
    listed = client.get("/api/v1/entries").json()

    assert single.status_code == 200
    assert single.json() == next(entry for entry in listed if entry["entry_id"] == entry_id)


def test_get_missing_entry_returns_404(client: TestClient) -> None:
    login(client)

    response = client.get("/api/v1/entries/999999")

    assert response.status_code == 404
