"""Strict ints and non-negative constraints across the ledger's money/quantity fields.

`docs/acceptance.md`, "Money": every money, weight, and quantity field is
strictly validated as a non-negative `int`; posting `"1"`, `1.5`, or a
negative value for one field from each family returns 422.
`tests/api/test_movements.py` already pins this for a movement's
`quantity`; this module covers the bake-count, visit-revenue, and
visit-fee families the other ledger tests don't otherwise exercise.
"""

from fastapi.testclient import TestClient

from tests.api.ledger_helpers import create_location, create_recipe
from tests.api.probes import login


def _size_id(client: TestClient) -> tuple[int, int]:
    recipe = create_recipe(
        client,
        sizes=[
            {"name": "Only", "portion_weight_g": 10, "price_cents": 100, "typical_yield_count": 1}
        ],
    )
    return recipe["sizes"][0]["id"], recipe["id"]


def test_strict_int_rejects_string_and_float_for_a_bake_count(client: TestClient) -> None:
    login(client)
    size_id, recipe_id = _size_id(client)

    def payload(count: object) -> dict[str, object]:
        return {
            "recipe_id": recipe_id,
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [{"size_id": size_id, "count": count}],
        }

    assert client.post("/api/v1/batches", json=payload("1")).status_code == 422
    assert client.post("/api/v1/batches", json=payload(1.5)).status_code == 422


def test_negative_bake_count_is_rejected(client: TestClient) -> None:
    login(client)
    size_id, recipe_id = _size_id(client)

    response = client.post(
        "/api/v1/batches",
        json={
            "recipe_id": recipe_id,
            "baked": "2026-01-01",
            "expires": "2026-01-10",
            "counts": [{"size_id": size_id, "count": -1}],
        },
    )

    assert response.status_code == 422


def test_negative_stand_visit_revenue_is_rejected(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    response = client.post(
        "/api/v1/visits",
        json={"kind": "stand", "location_id": stand["id"], "rows": [], "revenue_cents": -1},
    )

    assert response.status_code == 422


def test_strict_int_rejects_string_and_float_for_visit_revenue(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    as_string = client.post(
        "/api/v1/visits",
        json={"kind": "stand", "location_id": stand["id"], "rows": [], "revenue_cents": "1"},
    )
    as_float = client.post(
        "/api/v1/visits",
        json={"kind": "stand", "location_id": stand["id"], "rows": [], "revenue_cents": 1.5},
    )

    assert as_string.status_code == 422
    assert as_float.status_code == 422


def test_negative_market_fee_is_rejected(client: TestClient) -> None:
    login(client)
    market = create_location(client, "market", "Market")

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "market",
            "location_id": market["id"],
            "rows": [],
            "revenue_cents": 0,
            "fee_cents": -1,
        },
    )

    assert response.status_code == 422


def test_negative_stand_row_counted_is_rejected(client: TestClient) -> None:
    login(client)
    stand = create_location(client, "stand", "Stand")

    response = client.post(
        "/api/v1/visits",
        json={
            "kind": "stand",
            "location_id": stand["id"],
            "rows": [{"size_id": 1, "counted": -1, "tossed": 0, "pulled": 0, "added": 0}],
            "revenue_cents": 0,
        },
    )

    assert response.status_code == 422


def test_reversal_entry_id_strict_int_rejects_string(client: TestClient) -> None:
    login(client)

    response = client.post("/api/v1/reversals", json={"entry_id": "1"})

    assert response.status_code == 422
