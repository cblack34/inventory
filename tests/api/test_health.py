"""`GET /api/v1/health`: public, and FastAPI's disabled docs routes stay 404."""

from fastapi.testclient import TestClient


def test_health_is_public_and_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_docs_and_redoc_stay_404(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
