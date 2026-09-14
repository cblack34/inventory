"""Ingredient create/patch (`docs/acceptance.md`, "Ingredients and recipes")."""

from fastapi.testclient import TestClient

from tests.api.probes import login


def _create_ingredient(client: TestClient, *, price_cents: int = 100) -> int:
    response = client.post(
        "/api/v1/ingredients",
        json={"name": "Flour", "unit_label": "g", "current_price_cents": price_cents},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_ingredient_returns_active_row(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/v1/ingredients",
        json={"name": "Sugar", "unit_label": "g", "current_price_cents": 5},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sugar"
    assert body["current_price_cents"] == 5
    assert body["active"] is True


def test_patch_ingredient_price_changes_every_recipe_using_it(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client, price_cents=200)
    recipe = client.post(
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
                }
            ],
        },
    ).json()
    assert recipe["sizes"][0]["estimated_unit_cost_cents"] == 200

    patched = client.patch(
        f"/api/v1/ingredients/{ingredient_id}", json={"current_price_cents": 400}
    )
    assert patched.status_code == 200

    reloaded = client.get(f"/api/v1/recipes/{recipe['id']}").json()
    assert reloaded["sizes"][0]["estimated_unit_cost_cents"] == 400


def test_ingredient_can_be_deactivated_and_reactivated(client: TestClient) -> None:
    login(client)
    ingredient_id = _create_ingredient(client)

    deactivated = client.patch(f"/api/v1/ingredients/{ingredient_id}", json={"active": False})
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    reactivated = client.patch(f"/api/v1/ingredients/{ingredient_id}", json={"active": True})
    assert reactivated.status_code == 200
    assert reactivated.json()["active"] is True


def test_negative_price_rejected(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/v1/ingredients",
        json={"name": "Salt", "unit_label": "g", "current_price_cents": -1},
    )

    assert response.status_code == 422


def test_strict_int_price_rejects_string_and_float(client: TestClient) -> None:
    login(client)

    as_string = client.post(
        "/api/v1/ingredients",
        json={"name": "Salt", "unit_label": "g", "current_price_cents": "1"},
    )
    as_float = client.post(
        "/api/v1/ingredients",
        json={"name": "Salt", "unit_label": "g", "current_price_cents": 1.5},
    )

    assert as_string.status_code == 422
    assert as_float.status_code == 422


def test_unknown_field_rejected_with_errors_list(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/api/v1/ingredients",
        json={
            "name": "Salt",
            "unit_label": "g",
            "current_price_cents": 1,
            "unexpected": "nope",
        },
    )

    assert response.status_code == 422
    assert "errors" in response.json()
