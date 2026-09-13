from fastapi.testclient import TestClient

from inventory.app import create_app


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_disabled() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 404
