"""Derived stock: independent fold, terminal-location exclusion, per-batch expiry.

`docs/acceptance.md`, "Ledger, stock, and FIFO" and "Home screen and
expiration".
"""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.api.deps import today
from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Movement as MovementRow
from tests.api.ledger_helpers import (
    bake,
    builtin_location_id,
    create_location,
    create_recipe,
    kitchen_id,
    move,
)
from tests.api.probes import login


def _independent_fold_by_location_and_size(app: FastAPI) -> dict[tuple[int, int], int]:
    """On-hand per (location, size), accumulated straight from the `movement` table.

    Opens its own `Session` on the app's engine and sums raw rows by hand:
    plus at the destination, minus at the source, inventory locations
    only. It deliberately does not call the ledger's `on_hand`, which is
    the fold `GET /api/v1/stock` itself uses, so a bug in that fold cannot
    cancel out against the expected value.
    """
    with Session(app.state.engine) as session:
        inventory_location_ids = load_builtin_locations(session).locations.inventory_location_ids
        rows = session.execute(select(MovementRow)).scalars().all()
        totals: dict[tuple[int, int], int] = {}
        for row in rows:
            if row.to_location_id in inventory_location_ids:
                key = (row.to_location_id, row.size_id)
                totals[key] = totals.get(key, 0) + row.quantity
            if row.from_location_id in inventory_location_ids:
                key = (row.from_location_id, row.size_id)
                totals[key] = totals.get(key, 0) - row.quantity
    return {key: quantity for key, quantity in totals.items() if quantity != 0}


def test_stock_matches_an_independent_fold_over_the_movements_made(
    app: FastAPI, client: TestClient
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
        counts=[{"size_id": size_id, "count": 5}],
    )

    stand = create_location(client, "stand", "Stand")
    move_response = move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=2,
    )
    assert move_response.status_code == 201

    stock = client.get("/api/v1/stock").json()
    expected = _independent_fold_by_location_and_size(app)

    seen_keys: set[tuple[int, int]] = set()
    for location in stock:
        for size in location["sizes"]:
            key = (location["location_id"], size["size_id"])
            seen_keys.add(key)
            assert size["quantity"] == expected.get(key, 0)

    # Every nonzero fold entry showed up somewhere in the endpoint's
    # response -- not just every entry the endpoint reported matching the
    # fold, which alone would pass even if the endpoint silently dropped a
    # location or size.
    assert seen_keys == {key for key, quantity in expected.items() if quantity != 0}


def test_terminal_locations_never_appear_in_stock(client: TestClient) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[
            {
                "name": "Priced",
                "portion_weight_g": 10,
                "price_cents": 100,
                "typical_yield_count": 1,
            },
            {"name": "Sample", "portion_weight_g": 10, "price_cents": 0, "typical_yield_count": 1},
        ],
    )
    priced_id = next(s["id"] for s in recipe["sizes"] if s["name"] == "Priced")
    sample_id = next(s["id"] for s in recipe["sizes"] if s["name"] == "Sample")
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": priced_id, "count": 3}, {"size_id": sample_id, "count": 3}],
    )

    stand = create_location(client, "stand", "Stand")
    kitchen = kitchen_id(client)
    move(
        client, from_location_id=kitchen, to_location_id=stand["id"], size_id=priced_id, quantity=1
    )
    move(
        client, from_location_id=kitchen, to_location_id=stand["id"], size_id=sample_id, quantity=1
    )

    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [
                {"size_id": priced_id, "counted": 0, "tossed": 0, "pulled": 0, "added": 0},
                {"size_id": sample_id, "counted": 0, "tossed": 0, "pulled": 0, "added": 0},
            ],
            "revenue_cents": 100,
        },
    )
    assert visit.status_code == 201

    waste_id = builtin_location_id(client, "waste")
    toss = move(
        client, from_location_id=kitchen, to_location_id=waste_id, size_id=priced_id, quantity=1
    )
    assert toss.status_code == 201

    stock = client.get("/api/v1/stock").json()
    kinds = {location["kind"] for location in stock}
    assert kinds.isdisjoint({"production", "sold", "waste", "sampled"})


def test_size_row_with_one_expired_and_one_expiring_soon_batch_reports_both_states(
    app: FastAPI, client: TestClient
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
        baked="2025-12-01",
        expires="2026-01-01",
        counts=[{"size_id": size_id, "count": 3}],
    )
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2025-12-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 4}],
    )

    app.dependency_overrides[today] = lambda: date(2026, 1, 5)
    try:
        stock = client.get("/api/v1/stock").json()
    finally:
        app.dependency_overrides.pop(today, None)

    kitchen = next(location for location in stock if location["kind"] == "kitchen")
    size_stock = next(size for size in kitchen["sizes"] if size["size_id"] == size_id)
    states_by_quantity = {batch["quantity"]: batch["state"] for batch in size_stock["batches"]}

    assert states_by_quantity[3] == "expired"
    assert states_by_quantity[4] == "expiring_soon"
