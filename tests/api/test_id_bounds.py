"""Every id -- a body field or a path parameter -- shares one strict, bounded type.

`inventory.api.schemas.ids.Id` (body fields) and `IdPath` (path
parameters) both reject `0`, a negative id, and an id past SQLite's
signed 64-bit `INTEGER PRIMARY KEY` range with a 422 `errors` list,
never a 404 (which would suggest "no such row") or a 500 (an
out-of-range value the database driver cannot represent). One body id
and one path id per resource family is enough to pin that every route
actually wires the shared type in, not just some of them.
"""

import pytest
from fastapi.testclient import TestClient

from tests.api.probes import login

_BAD_IDS = [0, -1, 2**63]


@pytest.fixture(autouse=True)
def _logged_in(client: TestClient) -> None:
    login(client)


@pytest.mark.parametrize("bad_id", _BAD_IDS, ids=["zero", "negative", "over-max"])
class TestBodyIdIsBounded:
    """One `POST` per resource family whose body carries at least one id field."""

    def test_recipe_line_ingredient_id(self, client: TestClient, bad_id: int) -> None:
        response = client.post(
            "/api/v1/recipes",
            json={
                "name": "Test Recipe",
                "shelf_life_days": 1,
                "lines": [{"ingredient_id": bad_id, "quantity": 1}],
                "sizes": [
                    {
                        "name": "One",
                        "portion_weight_g": 1,
                        "price_cents": 1,
                        "typical_yield_count": 1,
                    }
                ],
            },
        )

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_batch_recipe_id(self, client: TestClient, bad_id: int) -> None:
        response = client.post(
            "/api/v1/batches",
            json={
                "recipe_id": bad_id,
                "baked": "2026-01-01",
                "expires": "2026-01-10",
                "counts": [{"size_id": 1, "count": 1}],
            },
        )

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_movement_from_location_id(self, client: TestClient, bad_id: int) -> None:
        response = client.post(
            "/api/v1/movements",
            json={"from_location_id": bad_id, "to_location_id": 1, "size_id": 1, "quantity": 1},
        )

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_reversal_entry_id(self, client: TestClient, bad_id: int) -> None:
        response = client.post("/api/v1/reversals", json={"entry_id": bad_id})

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_visit_location_id(self, client: TestClient, bad_id: int) -> None:
        response = client.post(
            "/api/v1/visits",
            json={"kind": "stand", "location_id": bad_id, "rows": [], "revenue_cents": 0},
        )

        assert response.status_code == 422
        assert response.json()["errors"]


@pytest.mark.parametrize("bad_id", _BAD_IDS, ids=["zero", "negative", "over-max"])
class TestPathIdIsBounded:
    """One `GET /{..._id}` per resource family that has a single-item route."""

    def test_ingredient_id(self, client: TestClient, bad_id: int) -> None:
        response = client.get(f"/api/v1/ingredients/{bad_id}")

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_recipe_id(self, client: TestClient, bad_id: int) -> None:
        response = client.get(f"/api/v1/recipes/{bad_id}")

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_location_id(self, client: TestClient, bad_id: int) -> None:
        response = client.get(f"/api/v1/locations/{bad_id}")

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_batch_id(self, client: TestClient, bad_id: int) -> None:
        response = client.get(f"/api/v1/batches/{bad_id}")

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_entry_id(self, client: TestClient, bad_id: int) -> None:
        response = client.get(f"/api/v1/entries/{bad_id}")

        assert response.status_code == 422
        assert response.json()["errors"]

    def test_visit_id(self, client: TestClient, bad_id: int) -> None:
        response = client.get(f"/api/v1/visits/{bad_id}")

        assert response.status_code == 422
        assert response.json()["errors"]
