"""`spa()`'s `/api` branch: 405 with `Allow` for a matched path, wrong method.

`spa()` is FastAPI's `GET /{path:path}` catch-all, registered last -- it
would otherwise "win" the routing match for any `GET` on a real,
POST-only `/api/v1` resource before that resource's own route ever gets
a chance to answer 405 itself, masking the mismatch as a 404. An unknown
API path, and FastAPI's disabled documentation routes, must still 404.
No login is needed for any of these: `spa()` raises before ever
checking the session cookie.
"""

from fastapi.testclient import TestClient


def test_get_on_a_post_only_path_returns_405_with_allow(client: TestClient) -> None:
    response = client.get("/api/v1/movements")

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_get_on_another_post_only_path_returns_405_with_allow(client: TestClient) -> None:
    response = client.get("/api/v1/visits")

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"


def test_unknown_api_path_still_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/nonexistent")

    assert response.status_code == 404
    assert "allow" not in response.headers


def test_disabled_doc_routes_still_return_404_not_405(client: TestClient) -> None:
    for path in ("/openapi.json", "/docs", "/redoc"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "allow" not in response.headers
