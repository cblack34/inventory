"""Recipe create/patch, sizes, and the live cost estimate.

`docs/acceptance.md`, "Ingredients and recipes": the 200-cent recipe
with sizes of portion weight 50/20/10 and a typical yield of 2 each
must return per-size estimates 63/25/13 -- the `round_half_up` boundary
`round()` would get wrong (62/25/12).
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from tests.api.probes import login


def _create_ingredient(client: TestClient, price_cents: int) -> int:
    response = client.post(
        "/api/v1/ingredients",
        json={"name": "Flour", "unit_label": "g", "current_price_cents": price_cents},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_cost_estimate_pins_round_half_up_boundary(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=200)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            "sizes": [
                {
                    "name": "Large",
                    "portion_weight_g": 50,
                    "price_cents": 300,
                    "typical_yield_count": 2,
                },
                {
                    "name": "Medium",
                    "portion_weight_g": 20,
                    "price_cents": 200,
                    "typical_yield_count": 2,
                },
                {
                    "name": "Small",
                    "portion_weight_g": 10,
                    "price_cents": 0,
                    "typical_yield_count": 2,
                },
            ],
        },
    )

    assert response.status_code == 201
    sizes = {size["name"]: size for size in response.json()["sizes"]}
    assert sizes["Large"]["estimated_unit_cost_cents"] == 63
    assert sizes["Medium"]["estimated_unit_cost_cents"] == 25
    assert sizes["Small"]["estimated_unit_cost_cents"] == 13
    assert sizes["Small"]["price_cents"] == 0


def test_zero_typical_total_weight_is_rejected(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=200)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            "sizes": [
                {
                    "name": "Large",
                    "portion_weight_g": 50,
                    "price_cents": 300,
                    "typical_yield_count": 0,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:inventory:problem:zero-weight"


def _create_recipe_with_two_sizes(client: TestClient) -> dict[str, Any]:
    ingredient_id = _create_ingredient(client, price_cents=100)
    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            "sizes": [
                {
                    "name": "Large",
                    "portion_weight_g": 50,
                    "price_cents": 300,
                    "typical_yield_count": 2,
                },
                {
                    "name": "Small",
                    "portion_weight_g": 10,
                    "price_cents": 100,
                    "typical_yield_count": 2,
                },
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_patch_can_add_and_edit_sizes_but_never_remove_one(client: TestClient) -> None:
    login(client)
    recipe = _create_recipe_with_two_sizes(client)
    large_id = next(size["id"] for size in recipe["sizes"] if size["name"] == "Large")

    patched = client.patch(
        f"/api/v1/recipes/{recipe['id']}",
        json={
            "sizes": [
                {"id": large_id, "price_cents": 999},
                {
                    "name": "Extra Large",
                    "portion_weight_g": 80,
                    "price_cents": 500,
                    "typical_yield_count": 1,
                },
            ]
        },
    )

    assert patched.status_code == 200
    sizes_by_name = {size["name"]: size for size in patched.json()["sizes"]}
    assert set(sizes_by_name) == {"Large", "Small", "Extra Large"}
    assert sizes_by_name["Large"]["price_cents"] == 999
    assert sizes_by_name["Small"]["price_cents"] == 100


def test_patch_size_with_explicit_null_id_is_rejected(client: TestClient) -> None:
    """Only an *absent* `id` key means create; `"id": null` is a validation error, not a create."""
    login(client)
    recipe = _create_recipe_with_two_sizes(client)

    response = client.patch(
        f"/api/v1/recipes/{recipe['id']}",
        json={
            "sizes": [
                {
                    "id": None,
                    "name": "Extra Large",
                    "portion_weight_g": 80,
                    "price_cents": 500,
                    "typical_yield_count": 1,
                }
            ]
        },
    )

    assert response.status_code == 422
    assert "errors" in response.json()


def test_patch_size_without_id_key_creates(client: TestClient) -> None:
    """The same payload minus the `id` key is a valid create, confirming the null case above."""
    login(client)
    recipe = _create_recipe_with_two_sizes(client)

    response = client.patch(
        f"/api/v1/recipes/{recipe['id']}",
        json={
            "sizes": [
                {
                    "name": "Extra Large",
                    "portion_weight_g": 80,
                    "price_cents": 500,
                    "typical_yield_count": 1,
                }
            ]
        },
    )

    assert response.status_code == 200
    names = {size["name"] for size in response.json()["sizes"]}
    assert "Extra Large" in names


def test_patch_size_id_belonging_to_another_recipe_is_rejected(client: TestClient) -> None:
    login(client)
    recipe_a = _create_recipe_with_two_sizes(client)
    recipe_b = _create_recipe_with_two_sizes(client)
    other_size_id = recipe_b["sizes"][0]["id"]

    response = client.patch(
        f"/api/v1/recipes/{recipe_a['id']}",
        json={"sizes": [{"id": other_size_id, "price_cents": 1}]},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:inventory:problem:size-not-in-recipe"
    # The target recipe being patched, not the foreign size's own recipe.
    assert body["recipe_id"] == recipe_a["id"]
    assert body["recipe_name"] == recipe_a["name"]
    assert body["size_id"] == other_size_id
    assert body["size_name"] == recipe_b["sizes"][0]["name"]
    assert body["size_recipe_id"] == recipe_b["id"]


def test_patch_lines_replaces_the_whole_list(client: TestClient) -> None:
    login(client)
    first_ingredient = _create_ingredient(client, price_cents=100)
    recipe = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": first_ingredient, "quantity": 2}],
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
    second_ingredient = _create_ingredient(client, price_cents=50)

    patched = client.patch(
        f"/api/v1/recipes/{recipe['id']}",
        json={"lines": [{"ingredient_id": second_ingredient, "quantity": 3}]},
    )

    assert patched.status_code == 200
    lines = patched.json()["lines"]
    assert lines == [{"ingredient_id": second_ingredient, "quantity": 3}]
    # 3 * 50 cents = 150 cents split over one size of weight 10 and yield 1.
    assert patched.json()["sizes"][0]["estimated_unit_cost_cents"] == 150


def test_unknown_ingredient_in_a_line_is_rejected(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": 999999, "quantity": 1}],
            "sizes": [
                {
                    "name": "Regular",
                    "portion_weight_g": 10,
                    "price_cents": 100,
                    "typical_yield_count": 1,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:inventory:problem:unknown-ingredient"


def test_size_names_are_unique_case_insensitively_within_a_recipe(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=100)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            "sizes": [
                {
                    "name": "Regular",
                    "portion_weight_g": 10,
                    "price_cents": 100,
                    "typical_yield_count": 1,
                },
                {
                    "name": "REGULAR",
                    "portion_weight_g": 10,
                    "price_cents": 100,
                    "typical_yield_count": 1,
                },
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["type"] == "urn:inventory:problem:name-conflict"


def test_strict_int_rejects_string_and_float_for_a_weight_field(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=100)
    base_payload = {
        "name": "Cookie",
        "shelf_life_days": 5,
        "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
    }

    string_size = {
        "name": "Regular",
        "portion_weight_g": "10",
        "price_cents": 1,
        "typical_yield_count": 1,
    }
    float_size = {**string_size, "portion_weight_g": 1.5}

    as_string = client.post("/api/v1/recipes", json={**base_payload, "sizes": [string_size]})
    as_float = client.post("/api/v1/recipes", json={**base_payload, "sizes": [float_size]})

    assert as_string.status_code == 422
    assert as_float.status_code == 422


def test_negative_quantity_is_rejected(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=100)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": -1}],
            "sizes": [
                {
                    "name": "Regular",
                    "portion_weight_g": 10,
                    "price_cents": 100,
                    "typical_yield_count": 1,
                }
            ],
        },
    )

    assert response.status_code == 422


def test_patch_empty_name_is_rejected_with_errors_list(client: TestClient) -> None:
    login(client)
    recipe = _create_recipe_with_two_sizes(client)

    response = client.patch(f"/api/v1/recipes/{recipe['id']}", json={"name": ""})

    assert response.status_code == 422
    assert "errors" in response.json()


def _count_statements(app: FastAPI, action: Callable[[], object]) -> int:
    """Run `action`, counting every statement `app.state.engine` executes for it.

    Mirrors `tests.db.test_queries._history_with_query_count`'s
    `before_cursor_execute` listener.
    """
    engine = app.state.engine
    count = 0

    def _count_statement(
        _conn: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _count_statement)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", _count_statement)
    return count


def test_list_recipes_runs_a_bounded_number_of_queries_regardless_of_recipe_count(
    client: TestClient, app: FastAPI
) -> None:
    """Pins the `selectinload` fix for the list endpoint's ingredient/lines/sizes N+1.

    Before eager loading, each extra recipe added one lazy `lines` query
    and one lazy `sizes` query (plus one more per line for its
    ingredient), so three recipes and six recipes would run a different
    number of statements. After `selectinload`, the statement count is
    bounded by the number of relationships, not the number of rows.
    """
    login(client)
    for _ in range(3):
        _create_recipe_with_two_sizes(client)
    three_recipes_count = _count_statements(app, lambda: client.get("/api/v1/recipes"))

    for _ in range(3):
        _create_recipe_with_two_sizes(client)
    six_recipes_count = _count_statements(app, lambda: client.get("/api/v1/recipes"))

    assert three_recipes_count == six_recipes_count


def test_get_recipe_runs_the_same_bounded_number_of_queries(
    client: TestClient, app: FastAPI
) -> None:
    login(client)
    recipe = _create_recipe_with_two_sizes(client)

    list_count = _count_statements(app, lambda: client.get("/api/v1/recipes"))
    get_count = _count_statements(app, lambda: client.get(f"/api/v1/recipes/{recipe['id']}"))

    assert get_count == list_count


def test_strict_int_rejects_string_and_float_for_a_quantity_field(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=100)
    size = {"name": "Regular", "portion_weight_g": 10, "price_cents": 1, "typical_yield_count": 1}

    def payload(quantity: object) -> dict[str, Any]:
        return {
            "name": "Cookie",
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": quantity}],
            "sizes": [size],
        }

    assert client.post("/api/v1/recipes", json=payload("1")).status_code == 422
    assert client.post("/api/v1/recipes", json=payload(1.5)).status_code == 422
