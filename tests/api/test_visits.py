"""Stand and market visit settlement, and profit.

`docs/acceptance.md`, "Stand visit", "Market visit", "Profit", and
"Money".
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.ledger_helpers import (
    bake,
    builtin_location_id,
    create_location,
    create_recipe,
    kitchen_id,
    market_row,
    move,
    stand_row,
)
from tests.api.probes import login


def _priced_and_sample_recipe(client: TestClient) -> dict[str, Any]:
    return create_recipe(
        client,
        ingredient_price_cents=100,
        sizes=[
            {
                "name": "Priced",
                "portion_weight_g": 10,
                "price_cents": 300,
                "typical_yield_count": 2,
            },
            {"name": "Sample", "portion_weight_g": 10, "price_cents": 0, "typical_yield_count": 2},
        ],
    )


def _size_ids(recipe: dict[str, Any]) -> dict[str, int]:
    return {size["name"]: size["id"] for size in recipe["sizes"]}


def test_stand_visit_missing_priced_size_is_sold_and_zero_price_size_is_sampled(
    client: TestClient,
) -> None:
    login(client)
    recipe = _priced_and_sample_recipe(client)
    sizes = _size_ids(recipe)
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": sizes["Priced"], "count": 2}, {"size_id": sizes["Sample"], "count": 2}],
    )
    stand = create_location(client, "stand", "Stand")
    kitchen = kitchen_id(client)
    move(
        client,
        from_location_id=kitchen,
        to_location_id=stand["id"],
        size_id=sizes["Priced"],
        quantity=2,
    )
    move(
        client,
        from_location_id=kitchen,
        to_location_id=stand["id"],
        size_id=sizes["Sample"],
        quantity=2,
    )

    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [stand_row(sizes["Priced"], counted=1), stand_row(sizes["Sample"], counted=1)],
            "revenue_cents": 300,
        },
    )

    assert visit.status_code == 201
    profit = visit.json()["profit"]
    # Recipe cost 100 split evenly by weight over two units of each size (25
    # cents each); one missing priced unit routes to Sold, one missing
    # sample unit routes to Sampled, never the other way around.
    assert profit["sold_cost_cents"] == 25
    assert profit["sampled_cost_cents"] == 25
    assert profit["waste_cost_cents"] == 0


def test_counted_exceeding_on_hand_is_rejected_naming_size_on_hand_and_counted(
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
        counts=[{"size_id": size_id, "count": 2}],
    )
    stand = create_location(client, "stand", "Stand")
    move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=2,
    )

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [stand_row(size_id, counted=5)],
            "revenue_cents": 0,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["size_id"] == size_id
    assert body["on_hand"] == 2
    assert body["counted"] == 5
    assert body["recipe_id"] == recipe["id"]
    assert body["recipe_name"] == recipe["name"]
    assert body["size_name"] == "Only"


def test_added_exceeding_kitchen_stock_is_rejected_naming_recipe_size_and_location(
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
        counts=[{"size_id": size_id, "count": 2}],
    )
    stand = create_location(client, "stand", "Stand")
    kitchen = kitchen_id(client)

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [stand_row(size_id, added=5)],
            "revenue_cents": 0,
        },
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


def test_tossed_plus_pulled_exceeding_counted_is_rejected_naming_the_size(
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
        counts=[{"size_id": size_id, "count": 5}],
    )
    stand = create_location(client, "stand", "Stand")
    move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=5,
    )

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [stand_row(size_id, counted=3, tossed=2, pulled=2)],
            "revenue_cents": 0,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["size_id"] == size_id
    assert body["recipe_id"] == recipe["id"]
    assert body["recipe_name"] == recipe["name"]
    assert body["size_name"] == "Only"


def test_stand_payload_with_fee_cents_is_rejected(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [],
            "revenue_cents": 0,
            "fee_cents": 100,
        },
    )

    assert response.status_code == 422


def test_visit_payload_with_unknown_key_is_rejected(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [],
            "revenue_cents": 0,
            "surprise": True,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["kitchen", "production", "sold", "waste", "sampled"])
def test_stand_visit_at_a_non_stand_location_is_rejected(client: TestClient, kind: str) -> None:
    login(client)
    location_id = builtin_location_id(client, kind)

    response = client.post(
        "/api/v1/visits",
        json={"kind": "stand", "location_id": location_id, "rows": [], "revenue_cents": 0},
    )

    assert response.status_code == 422


def test_stand_visit_at_an_inactive_stand_is_rejected(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")
    client.patch(f"/api/v1/locations/{stand['id']}", json={"active": False})

    response = client.post(
        "/api/v1/visits",
        json={"kind": "stand", "location_id": stand["id"], "rows": [], "revenue_cents": 0},
    )

    assert response.status_code == 422


def test_stand_payload_against_a_market_is_rejected(client: TestClient) -> None:
    login(client)
    market = create_location(client, "market", "Market")

    response = client.post(
        "/api/v1/visits",
        json={"kind": "stand", "location_id": market["id"], "rows": [], "revenue_cents": 0},
    )

    assert response.status_code == 422


def test_market_payload_against_a_stand_is_rejected(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": stand["id"],
            "rows": [],
            "revenue_cents": 0,
            "fee_cents": 0,
        },
    )

    assert response.status_code == 422


def test_market_returned_plus_tossed_exceeding_taken_is_rejected_and_writes_zero_new_rows(
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
        counts=[{"size_id": size_id, "count": 5}],
    )
    market = create_location(client, "market", "Market")

    entries_before = client.get("/api/v1/entries").json()

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": market["id"],
            "rows": [market_row(size_id, taken=3, returned=2, tossed=2)],
            "revenue_cents": 0,
            "fee_cents": 0,
        },
    )

    assert response.status_code == 422
    entries_after = client.get("/api/v1/entries").json()
    assert entries_after == entries_before


def test_saved_visit_expected_revenue_unchanged_after_price_change_and_positive_difference(
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
        counts=[{"size_id": size_id, "count": 1}],
    )
    stand = create_location(client, "stand", "Stand")
    move(
        client,
        from_location_id=kitchen_id(client),
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=1,
    )

    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [stand_row(size_id, counted=0)],
            "revenue_cents": 200,
        },
    )
    assert visit.status_code == 201
    entry_id = visit.json()["entry_id"]
    assert visit.json()["expected_revenue_cents"] == 300
    assert visit.json()["difference_cents"] == 100

    price_change = client.patch(
        f"/api/v1/recipes/{recipe['id']}", json={"sizes": [{"id": size_id, "price_cents": 999}]}
    )
    assert price_change.status_code == 200

    reread = client.get(f"/api/v1/visits/{entry_id}")
    assert reread.status_code == 200
    assert reread.json()["expected_revenue_cents"] == 300
    assert reread.json()["difference_cents"] == 100


def test_visit_profit_equals_revenue_minus_fee_minus_costs_with_all_three_lines_present(
    client: TestClient,
) -> None:
    login(client)
    recipe = create_recipe(
        client,
        ingredient_price_cents=100,
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
        counts=[{"size_id": size_id, "count": 5}],
    )
    market = create_location(client, "market", "Market")

    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": market["id"],
            "rows": [market_row(size_id, taken=5, returned=1, tossed=1)],
            "revenue_cents": 900,
            "fee_cents": 50,
        },
    )

    assert visit.status_code == 201
    profit = visit.json()["profit"]
    # batch cost 100 (ingredient price 100 x quantity 1) split evenly over
    # 5 units of the one size is 20 cents each; taken 5, tossed 1,
    # returned 1 -> missing (sold) 3, waste 1, sampled 0.
    assert profit["sold_cost_cents"] == 60
    assert profit["waste_cost_cents"] == 20
    assert profit["sampled_cost_cents"] == 0
    assert profit["profit_cents"] == 900 - 50 - 60 - 20 - 0

    entry_id = visit.json()["entry_id"]
    reread = client.get(f"/api/v1/visits/{entry_id}")
    assert reread.json()["profit"] == profit


def test_fee_exceeding_revenue_gives_a_negative_profit_and_a_200(client: TestClient) -> None:
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
        counts=[{"size_id": size_id, "count": 1}],
    )
    market = create_location(client, "market", "Market")

    visit = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": market["id"],
            "rows": [market_row(size_id, taken=1, returned=0, tossed=0)],
            "revenue_cents": 10,
            "fee_cents": 500,
        },
    )

    assert visit.status_code == 201
    assert visit.json()["profit"]["profit_cents"] < 0
