"""Every money, weight, and quantity input shares one bounded upper limit.

`inventory.api.schemas.numbers.Cents`/`Count`/`PositiveCount` cap every
money (`_cents`), weight (`_g`), and quantity input at `10**9` --
comfortably above any real value this business enters, and comfortably
below where the value would overflow SQLite's signed 64-bit `INTEGER`
binding and reach the client as an unhandled 500 instead of a 422
Problem. One field from each family is enough to pin that the bound is
actually wired in, not just declared; `just-over-max` catches a bound
that quietly moved, `past-int64` is the original overflow report.
"""

import pytest
from fastapi.testclient import TestClient

from tests.api.probes import login

_BAD_AMOUNTS = [10**9 + 1, 2**63]


@pytest.fixture(autouse=True)
def _logged_in(client: TestClient) -> None:
    login(client)


@pytest.mark.parametrize("bad_amount", _BAD_AMOUNTS, ids=["just-over-max", "past-int64"])
def test_money_field_is_bounded(client: TestClient, bad_amount: int) -> None:
    response = client.post(
        "/api/v1/ingredients",
        json={"name": "Test Ingredient", "unit_label": "g", "current_price_cents": bad_amount},
    )

    assert response.status_code == 422
    assert response.json()["errors"]


@pytest.mark.parametrize("bad_amount", _BAD_AMOUNTS, ids=["just-over-max", "past-int64"])
def test_weight_field_is_bounded(client: TestClient, bad_amount: int) -> None:
    response = client.post(
        "/api/v1/recipes",
        json={
            "name": "Test Recipe",
            "shelf_life_days": 1,
            "lines": [],
            "sizes": [
                {
                    "name": "One",
                    "portion_weight_g": bad_amount,
                    "price_cents": 1,
                    "typical_yield_count": 1,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"]


@pytest.mark.parametrize("bad_amount", _BAD_AMOUNTS, ids=["just-over-max", "past-int64"])
def test_quantity_field_is_bounded(client: TestClient, bad_amount: int) -> None:
    response = client.post(
        "/api/v1/movements",
        json={"from_location_id": 1, "to_location_id": 2, "size_id": 1, "quantity": bad_amount},
    )

    assert response.status_code == 422
    assert response.json()["errors"]
