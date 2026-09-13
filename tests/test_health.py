import pytest
from fastapi.testclient import TestClient

from inventory.app import create_app


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
def test_documentation_routes_disabled(path: str) -> None:
    client = TestClient(create_app())

    response = client.get(path)

    assert response.status_code == 404
