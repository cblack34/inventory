"""Persisted money totals and `shelf_life_days` are bounded (issue #37).

`inventory.api.schemas.numbers` caps every *individual* money, weight,
or quantity field at `10**9`, but a request whose individual fields are
all legal can still sum, at the persistence boundary, to a total past
SQLite's signed 64-bit `INTEGER` range: ten recipe lines each at the
per-field maximum give a recipe (and so a batch's) cost of `10**19`.
`inventory.domain.money.require_bounded_total` rejects that with a 422
naming the field before anything is written -- see
`inventory.db.writes.record_bake` and `inventory.db.visits`.
`shelf_life_days` used a bare `int = Field(ge=0)` rather than the shared
bounded `Count` type and could overflow the same way; it now shares that
type like every other integer field.
"""

from typing import Any

from fastapi.testclient import TestClient

from tests.api.ledger_helpers import bake, create_ingredient, create_location, create_recipe, move
from tests.api.probes import login

_MAX_FIELD_AMOUNT = 10**9


def _maximal_cost_recipe(client: TestClient) -> dict[str, Any]:
    """A recipe with ten lines, each individually legal, whose cost overflows the bound.

    Each line is `quantity = 10**9` against an ingredient priced
    `10**9` cents -- both within `Cents`/`Count`'s own per-field
    maximum -- so ten lines sum to a recipe cost of `10**19`, far past
    `domain.money.MAX_TOTAL_CENTS` (`10**12`).
    """
    lines = [
        {
            "ingredient_id": create_ingredient(client, _MAX_FIELD_AMOUNT, name=f"Ingredient {i}"),
            "quantity": _MAX_FIELD_AMOUNT,
        }
        for i in range(10)
    ]
    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Maximal Cost Recipe",
            "shelf_life_days": 1,
            "lines": lines,
            "sizes": [
                {"name": "Only", "portion_weight_g": 1, "price_cents": 1, "typical_yield_count": 1}
            ],
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_recipe_with_maximal_per_field_lines_is_accepted(client: TestClient) -> None:
    """Creating the recipe itself is legal: no field, and no persisted total, is involved yet."""
    login(client)

    recipe = _maximal_cost_recipe(client)

    assert recipe["name"] == "Maximal Cost Recipe"


def test_bake_whose_cost_would_overflow_returns_422_naming_total_cost_cents(
    client: TestClient,
) -> None:
    login(client)
    recipe = _maximal_cost_recipe(client)
    size_id = recipe["sizes"][0]["id"]
    entries_before = client.get("/api/v1/entries").json()

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe["id"],
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [{"size_id": size_id, "count": 1}],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["field"] == "total_cost_cents"

    entries_after = client.get("/api/v1/entries").json()
    assert entries_after == entries_before
    batches_after = client.get(f"/api/v1/batches/{1}")
    assert batches_after.status_code == 404


def test_shelf_life_days_over_max_is_rejected_on_create(client: TestClient) -> None:
    login(client)
    ingredient_id = create_ingredient(client)

    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Too Long",
            "shelf_life_days": 2**63,
            "lines": [{"ingredient_id": ingredient_id, "quantity": 1}],
            "sizes": [
                {"name": "Only", "portion_weight_g": 1, "price_cents": 1, "typical_yield_count": 1}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"]


def test_shelf_life_days_over_max_is_rejected_on_patch(client: TestClient) -> None:
    login(client)
    recipe = create_recipe(
        client,
        sizes=[{"name": "Only", "portion_weight_g": 1, "price_cents": 1, "typical_yield_count": 1}],
    )

    response = client.patch(f"/api/v1/recipes/{recipe['id']}", json={"shelf_life_days": 2**63})

    assert response.status_code == 422
    assert response.json()["errors"]


def test_stand_visit_expected_revenue_overflow_is_rejected_and_writes_nothing(
    client: TestClient,
) -> None:
    """A high-priced size with a large missing count overflows expected revenue, not cost.

    The recipe's ingredient is priced at 1 cent so the batch cost stays
    tiny; the size price (`10**9`, the per-field maximum) times 2000
    missing units (`2 * 10**12`) is what crosses
    `domain.money.MAX_TOTAL_CENTS`.
    """
    login(client)
    recipe = create_recipe(
        client,
        ingredient_price_cents=1,
        sizes=[
            {
                "name": "Pricey",
                "portion_weight_g": 1,
                "price_cents": _MAX_FIELD_AMOUNT,
                "typical_yield_count": 1,
            }
        ],
    )
    size_id = recipe["sizes"][0]["id"]
    bake(
        client,
        recipe_id=recipe["id"],
        baked="2026-01-01",
        expires="2026-01-10",
        counts=[{"size_id": size_id, "count": 2000}],
    )
    stand = create_location(client, "stand", "Stand")
    kitchen_response = client.get("/api/v1/locations").json()
    kitchen_id = next(loc["id"] for loc in kitchen_response if loc["kind"] == "kitchen")
    move(
        client,
        from_location_id=kitchen_id,
        to_location_id=stand["id"],
        size_id=size_id,
        quantity=2000,
    )
    entries_before = client.get("/api/v1/entries").json()

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [{"size_id": size_id, "counted": 0, "tossed": 0, "pulled": 0, "added": 0}],
            "revenue_cents": 0,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["field"] == "expected_revenue_cents"

    entries_after = client.get("/api/v1/entries").json()
    assert entries_after == entries_before
