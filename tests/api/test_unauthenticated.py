"""Unauthenticated matrix (`docs/acceptance.md`, "Login and deployment").

Unauthenticated GETs: an app route redirects to `/login`; an API route
returns 401; `/login` and a built asset stay public (200); FastAPI's
disabled `/openapi.json` stays 404.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.probes import add_protected_probe


def test_unauthenticated_app_route_redirects_to_login(app: FastAPI) -> None:
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/recipes")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_unauthenticated_api_route_returns_401_problem(app: FastAPI) -> None:
    add_protected_probe(app)

    with TestClient(app) as client:
        response = client.get("/api/v1/_test/probe")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


def test_login_page_is_public(client: TestClient) -> None:
    response = client.get("/login")

    assert response.status_code == 200


def test_built_asset_is_public(client: TestClient) -> None:
    response = client.get("/assets/x.js")

    assert response.status_code == 200


def test_openapi_json_stays_404(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 404


def test_docs_and_redoc_stay_404(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
