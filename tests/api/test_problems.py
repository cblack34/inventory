"""RFC 9457 Problem Details: content type, schema validity, extension members."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inventory.api.problems import Problem
from tests.api.probes import (
    add_domain_error_probe,
    add_empty_detail_probe,
    add_extension_types_probe,
    add_nonstandard_status_probe,
    add_not_found_probe,
    login,
)


def test_domain_error_becomes_422_with_extension_members(app: FastAPI) -> None:
    add_domain_error_probe(app)

    with TestClient(app) as client:
        login(client)
        response = client.get("/api/v1/_test/insufficient-stock")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"

    body = response.json()
    Problem.model_validate(body)
    assert body["type"] == "urn:inventory:problem:insufficient-stock"
    assert body["location_id"] == 1
    assert body["size_id"] == 2
    assert body["on_hand"] == 4
    assert body["requested"] == 6


def test_domain_error_extension_members_cover_any_json_encodable_attribute(
    app: FastAPI,
) -> None:
    add_extension_types_probe(app)

    with TestClient(app) as client:
        login(client)
        response = client.get("/api/v1/_test/extension-types")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"

    body = response.json()
    Problem.model_validate(body)
    assert body["observed_on"] == "2024-01-01"
    assert sorted(body["tags"]) == ["a", "b"]


def test_nonstandard_status_code_gets_a_fallback_title(app: FastAPI) -> None:
    add_nonstandard_status_probe(app)

    with TestClient(app) as client:
        login(client)
        response = client.get("/api/v1/_test/nonstandard-status")

    assert response.status_code == 599
    assert response.headers["content-type"] == "application/problem+json"

    body = response.json()
    Problem.model_validate(body)
    assert body["status"] == 599
    assert body["title"] == "HTTP 599"


def test_method_not_allowed_becomes_a_problem(client: TestClient) -> None:
    """`PUT /api/v1/session` is a matched path with the wrong method (405).

    Starlette raises its own base `HTTPException` for this case, not
    FastAPI's subclass -- pins that the handler registered on the base
    class actually catches it.
    """
    response = client.put("/api/v1/session")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    Problem.model_validate(response.json())


def test_method_not_allowed_preserves_the_allow_header(client: TestClient) -> None:
    """Starlette attaches `Allow` to its own 405 `HTTPException`; it must survive translation."""
    response = client.put("/api/v1/session")

    assert response.status_code == 405
    assert "post" in response.headers["allow"].lower()


def test_disabled_docs_404_never_shows_the_literal_string_none_as_detail(
    client: TestClient,
) -> None:
    response = client.get("/docs")

    assert response.status_code == 404
    body = response.json()
    Problem.model_validate(body)
    assert body["detail"] != "None"
    assert body["detail"] == "Not Found"


def test_no_result_found_becomes_404_problem(app: FastAPI) -> None:
    add_not_found_probe(app)

    with TestClient(app) as client:
        login(client)
        response = client.get("/api/v1/_test/not-found")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    Problem.model_validate(response.json())


def test_unknown_body_key_returns_422_with_errors_list(client: TestClient) -> None:
    response = client.post("/api/v1/session", json={"password": "whatever", "extra": "not allowed"})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"

    body = response.json()
    Problem.model_validate(body)
    assert body["type"] == "urn:inventory:problem:validation"
    assert isinstance(body["errors"], list)
    assert body["errors"]


def test_empty_string_detail_is_preserved(app: FastAPI) -> None:
    add_empty_detail_probe(app)

    with TestClient(app) as client:
        login(client)
        response = client.get("/api/v1/_test/empty-detail")

    assert response.status_code == 400
    assert response.json()["detail"] == ""
