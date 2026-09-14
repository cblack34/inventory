"""Bake: expiration ordering, zero counts, the cost split fixture, frozen cost.

`docs/acceptance.md`, "Bake"; `docs/data-model.md`, "Recipe cost estimate
and batch cost split".
"""

from typing import Any

from fastapi.testclient import TestClient

from tests.api.ledger_helpers import bake, create_recipe
from tests.api.probes import login


def _three_size_recipe(client: TestClient) -> dict[str, Any]:
    """A 1000-cent recipe with sizes of portion weight 200/100/50.

    `docs/acceptance.md`'s pinned fixture: counts 2/4/2 must yield
    per-size unit costs 222/111/56 cents.
    """
    return create_recipe(
        client,
        ingredient_price_cents=1000,
        sizes=[
            {
                "name": "Large",
                "portion_weight_g": 200,
                "price_cents": 300,
                "typical_yield_count": 2,
            },
            {
                "name": "Medium",
                "portion_weight_g": 100,
                "price_cents": 200,
                "typical_yield_count": 4,
            },
            {"name": "Small", "portion_weight_g": 50, "price_cents": 100, "typical_yield_count": 2},
        ],
    )


def test_expires_before_baked_is_rejected(client: TestClient) -> None:
    login(client)
    recipe = _three_size_recipe(client)
    size_id = recipe["sizes"][0]["id"]

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe["id"],
            "baked": "2026-01-10",
            "expires": "2026-01-01",
            "counts": [{"size_id": size_id, "count": 1}],
        },
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:inventory:problem:expires-before-baked"


def test_all_zero_counts_is_rejected(client: TestClient) -> None:
    login(client)
    recipe = _three_size_recipe(client)
    size_id = recipe["sizes"][0]["id"]

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe["id"],
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [{"size_id": size_id, "count": 0}],
        },
    )

    assert response.status_code == 422


def test_empty_counts_is_rejected(client: TestClient) -> None:
    login(client)
    recipe = _three_size_recipe(client)

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe["id"],
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [],
        },
    )

    assert response.status_code == 422


def test_bake_cost_split_pins_the_1000_cent_three_size_fixture(client: TestClient) -> None:
    login(client)
    recipe = _three_size_recipe(client)
    sizes = {size["name"]: size["id"] for size in recipe["sizes"]}

    response = bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[
            {"size_id": sizes["Large"], "count": 2},
            {"size_id": sizes["Medium"], "count": 4},
            {"size_id": sizes["Small"], "count": 2},
        ],
    )

    assert response["total_cost_cents"] == 1000
    unit_costs = {size["size_id"]: size["unit_cost_cents"] for size in response["sizes"]}
    assert unit_costs[sizes["Large"]] == 222
    assert unit_costs[sizes["Medium"]] == 111
    assert unit_costs[sizes["Small"]] == 56


def test_ingredient_price_change_after_bake_leaves_batch_unchanged(client: TestClient) -> None:
    """Non-negotiable 2: changing an ingredient price never changes an existing batch's cost."""
    login(client)
    recipe = create_recipe(
        client,
        ingredient_price_cents=1010,
        sizes=[
            {
                "name": "Regular",
                "portion_weight_g": 10,
                "price_cents": 100,
                "typical_yield_count": 1,
            }
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    ingredient_id = recipe["lines"][0]["ingredient_id"]

    batch = bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 20}],
    )
    assert batch["sizes"][0]["unit_cost_cents"] == 51

    price_change = client.patch(
        f"/api/v1/ingredients/{ingredient_id}", json={"current_price_cents": 999999}
    )
    assert price_change.status_code == 200

    reread = client.get(f"/api/v1/batches/{batch['id']}")
    assert reread.status_code == 200
    assert reread.json() == batch


def test_bake_with_a_foreign_size_reports_recipe_and_size_names(client: TestClient) -> None:
    """A count naming another recipe's size is an `UnknownSizeError` for this recipe.

    The Problem body must name the recipe actually being baked and the
    foreign size, not just their bare ids -- `docs/acceptance.md`'s
    ledger/stock bullet.
    """
    login(client)
    recipe = _three_size_recipe(client)
    other_recipe = create_recipe(
        client,
        sizes=[
            {"name": "Other", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    foreign_size_id = other_recipe["sizes"][0]["id"]

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe["id"],
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [{"size_id": foreign_size_id, "count": 1}],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:inventory:problem:unknown-size"
    assert body["recipe_id"] == recipe["id"]
    assert body["recipe_name"] == recipe["name"]
    assert body["size_names"] == {str(foreign_size_id): "Other"}


def test_duplicate_size_in_counts_is_rejected(client: TestClient) -> None:
    login(client)
    recipe = _three_size_recipe(client)
    size_id = recipe["sizes"][0]["id"]

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe["id"],
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [{"size_id": size_id, "count": 5}, {"size_id": size_id, "count": 0}],
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"]
