"""Shared builders for ledger tests: catalog fixtures and a bake helper.

Mirrors `tests.api.probes`: plain functions the ledger `tests/api/test_*.py`
modules import directly, building the catalog objects (ingredients,
recipes, sizes, locations) a ledger test needs through the catalog API
itself, per `docs/implementation/slices/api.md`'s dependency on
api/catalog.
"""

from typing import Any

from fastapi.testclient import TestClient


def create_ingredient(client: TestClient, price_cents: int = 100, name: str = "Flour") -> int:
    response = client.post(
        "/api/v1/ingredients",
        json={"name": name, "unit_label": "g", "current_price_cents": price_cents},
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def create_recipe(
    client: TestClient,
    *,
    sizes: list[dict[str, Any]],
    ingredient_price_cents: int = 100,
    name: str = "Cookie",
) -> dict[str, Any]:
    ingredient_id = create_ingredient(client, ingredient_price_cents)
    response = client.post(
        "/api/v1/recipes",
        json={
            "name": name,
            "shelf_life_days": 5,
            "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            "sizes": sizes,
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_location(client: TestClient, kind: str, name: str) -> dict[str, Any]:
    response = client.post("/api/v1/locations", json={"name": name, "kind": kind})
    assert response.status_code == 201, response.json()
    return response.json()


def bake(
    client: TestClient,
    *,
    recipe_id: int,
    baked: str,
    expires: str,
    counts: list[dict[str, int]],
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/batches",
        json={"recipe_id": recipe_id, "baked": baked, "expires": expires, "counts": counts},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def move(
    client: TestClient, *, from_location_id: int, to_location_id: int, size_id: int, quantity: int
) -> Any:
    return client.post(
        "/api/v1/movements",
        json={
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "size_id": size_id,
            "quantity": quantity,
        },
    )


def builtin_location_id(client: TestClient, kind: str) -> int:
    locations = client.get("/api/v1/locations").json()
    return next(location["id"] for location in locations if location["kind"] == kind)


def kitchen_id(client: TestClient) -> int:
    return builtin_location_id(client, "kitchen")


def stand_row(
    size_id: int, counted: int = 0, tossed: int = 0, pulled: int = 0, added: int = 0
) -> dict[str, int]:
    return {
        "size_id": size_id,
        "counted": counted,
        "tossed": tossed,
        "pulled": pulled,
        "added": added,
    }


def market_row(size_id: int, taken: int = 0, returned: int = 0, tossed: int = 0) -> dict[str, int]:
    return {"size_id": size_id, "taken": taken, "returned": returned, "tossed": tossed}
