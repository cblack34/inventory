"""RFC 9457 Problem Details: content type, schema validity, extension members."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inventory.api.problems import Problem
from tests.api.probes import add_domain_error_probe, add_not_found_probe, login


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
