"""`POST /api/v1/session`: cookie attributes, wrong password, throttle, tampering."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from inventory.app import create_app
from inventory.settings import Settings
from tests.api.conftest import TEST_SECRET
from tests.api.probes import TEST_PASSWORD, add_protected_probe, login


def test_correct_password_sets_cookie_with_expected_attributes(client: TestClient) -> None:
    response = client.post("/api/v1/session", json={"password": TEST_PASSWORD})

    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "max-age=2592000" in cookie


def test_secure_flag_present_only_when_cookies_are_not_insecure(db_path: Path) -> None:
    secure_settings = Settings(
        DB=str(db_path),
        SHARED_PASSWORD=SecretStr(TEST_PASSWORD),
        SESSION_SECRET=SecretStr(TEST_SECRET),
        TIMEZONE="UTC",
        INSECURE_COOKIES=False,
    )
    with TestClient(create_app(secure_settings)) as secure_client:
        secure_cookie = secure_client.post(
            "/api/v1/session", json={"password": TEST_PASSWORD}
        ).headers["set-cookie"]
    assert "secure" in secure_cookie.lower()

    insecure_settings = Settings(
        DB=str(db_path),
        SHARED_PASSWORD=SecretStr(TEST_PASSWORD),
        SESSION_SECRET=SecretStr(TEST_SECRET),
        TIMEZONE="UTC",
        INSECURE_COOKIES=True,
    )
    with TestClient(create_app(insecure_settings)) as insecure_client:
        insecure_cookie = insecure_client.post(
            "/api/v1/session", json={"password": TEST_PASSWORD}
        ).headers["set-cookie"]
    assert "secure" not in insecure_cookie.lower()


def test_wrong_password_returns_401_and_sets_no_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/session", json={"password": "wrong"})

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert "set-cookie" not in response.headers


def test_sixth_consecutive_failure_is_throttled_with_retry_after(client: TestClient) -> None:
    for _ in range(5):
        failure = client.post("/api/v1/session", json={"password": "wrong"})
        assert failure.status_code == 401

    response = client.post("/api/v1/session", json={"password": "wrong"})

    assert response.status_code == 429
    body = response.json()
    assert isinstance(body["retry_after_seconds"], int)
    assert body["retry_after_seconds"] > 0


def test_throttle_rejects_even_the_correct_password(client: TestClient) -> None:
    for _ in range(5):
        client.post("/api/v1/session", json={"password": "wrong"})

    response = client.post("/api/v1/session", json={"password": TEST_PASSWORD})

    assert response.status_code == 429


def test_tampered_cookie_is_treated_as_unauthenticated(app: FastAPI) -> None:
    add_protected_probe(app)

    with TestClient(app) as client:
        login(client)
        cookie_value = client.cookies.get("session")
        assert cookie_value is not None
        # Alter the first payload character: its high bits always change the
        # decoded bytes, unlike the final signature character whose low bits
        # can be base64 padding and decode identically.
        first = "f" if cookie_value[0] != "f" else "g"
        tampered = first + cookie_value[1:]
        client.cookies.set("session", tampered)

        response = client.get("/api/v1/_test/probe")

    assert response.status_code == 401
