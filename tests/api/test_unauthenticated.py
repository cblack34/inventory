"""Unauthenticated matrix (`docs/acceptance.md`, "Login and deployment").

Unauthenticated GETs: an app route redirects to `/login`; an API route
returns 401; `/login` and a built asset stay public (200); FastAPI's
disabled `/openapi.json` stays 404.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.probes import add_protected_probe, login


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


def test_disabled_doc_routes_with_a_trailing_slash_stay_404_unauthenticated(
    client: TestClient,
) -> None:
    assert client.get("/docs/").status_code == 404
    assert client.get("/redoc/").status_code == 404
    assert client.get("/openapi.json/").status_code == 404


def test_disabled_doc_routes_with_a_trailing_slash_stay_404_authenticated(
    client: TestClient,
) -> None:
    login(client)

    assert client.get("/docs/").status_code == 404
    assert client.get("/redoc/").status_code == 404
    assert client.get("/openapi.json/").status_code == 404


def test_root_level_dist_file_is_public_unauthenticated(client: TestClient) -> None:
    response = client.get("/favicon.svg")

    assert response.status_code == 200
    assert response.text == "<svg></svg>"


def test_root_level_dist_file_is_public_authenticated(client: TestClient) -> None:
    login(client)

    response = client.get("/favicon.svg")

    assert response.status_code == 200
    assert response.text == "<svg></svg>"


def test_path_traversal_cannot_escape_the_dist_directory(client: TestClient) -> None:
    response = client.get("/../pyproject.toml", follow_redirects=False)

    assert response.status_code in (303, 404)
    assert "[project]" not in response.text


def test_authenticated_app_route_serves_the_spa_shell(client: TestClient) -> None:
    login(client)

    response = client.get("/recipes")

    assert response.status_code == 200
    assert "inventory" in response.text


def test_index_html_is_gated_like_any_shell_path(client: TestClient) -> None:
    unauthenticated = client.get("/index.html", follow_redirects=False)
    assert unauthenticated.status_code == 303

    login(client)
    authenticated = client.get("/index.html")
    assert authenticated.status_code == 200
    assert "inventory" in authenticated.text


@pytest.mark.parametrize(
    "alias",
    ["/foo/%2e%2e/index.html", "/%2e/index.html", "/INDEX.HTML"],
    ids=["dot-dot-traversal", "dot-prefix", "case-variant"],
)
def test_every_index_html_alias_is_gated(client: TestClient, alias: str) -> None:
    """A traversal, a `.` prefix, and a case variant all name `index.html` and must all be gated.

    `httpx` collapses a literal `..`/`.` segment before the request
    ever leaves the client, which would make a plain `/foo/../index.html`
    request exercise nothing new here; percent-encoding the dots
    (`%2e`) survives client-side normalization so the raw, undecoded
    alias actually reaches the app, matching what a real HTTP client
    or proxy that does not normalize dot-segments could send.
    """
    unauthenticated = client.get(alias, follow_redirects=False)
    assert unauthenticated.status_code == 303

    login(client)
    authenticated = client.get(alias)
    assert authenticated.status_code == 200
    assert "inventory" in authenticated.text
