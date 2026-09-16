"""`GET /api/v1/today`: the business date the bake form prefills from.

`docs/data-model.md`, "Expiration": the business date, not the browser's
clock, is authoritative. `today()` (`inventory.api.deps`) already derives
it from the injected `now` dependency and the configured timezone; this
route just exposes that as a resource -- see `tests/api/test_clock.py`
for the timezone/clock derivation itself.
"""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inventory.app import now
from tests.api.probes import login


def test_today_returns_the_injected_business_date(app: FastAPI) -> None:
    injected_instant = datetime(2026, 3, 15, 4, 30, tzinfo=UTC)
    app.dependency_overrides[now] = lambda: injected_instant
    try:
        with TestClient(app) as client:
            login(client)
            response = client.get("/api/v1/today")
    finally:
        app.dependency_overrides.pop(now, None)

    assert response.status_code == 200
    assert response.json() == {"today": "2026-03-15"}


def test_today_requires_a_session(client: TestClient) -> None:
    response = client.get("/api/v1/today")

    assert response.status_code == 401


def test_today_is_listed_in_the_openapi_paths(app: FastAPI) -> None:
    schema = app.openapi()

    assert "/api/v1/today" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/today"]
