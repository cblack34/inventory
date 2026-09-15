"""Pins the business-timezone clock (docs/data-model.md, "Expiration")."""

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from pydantic import SecretStr

from inventory.app import business_today, create_app, now
from inventory.settings import Settings
from tests.api.conftest import TEST_SECRET
from tests.api.probes import TEST_PASSWORD, add_today_probe, login


def test_business_today_uses_the_configured_zone_not_utc() -> None:
    # 02:00 UTC on the 14th is still the evening of the 13th in Chicago.
    instant = datetime(2026, 9, 14, 2, 0, tzinfo=UTC)

    assert business_today(instant, ZoneInfo("America/Chicago")) == date(2026, 9, 13)
    assert business_today(instant, ZoneInfo("UTC")) == date(2026, 9, 14)


def test_now_is_aware_utc() -> None:
    instant = now()

    offset = instant.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_today_follows_the_injected_now_instant_not_the_wall_clock(db_path: Path) -> None:
    """`today` must derive from the `now` dependency it depends on, not `datetime.now(UTC)`.

    04:30 UTC is still 23:30 the previous day in America/Chicago, so a
    business configured for that timezone must see yesterday's date.
    Overriding `now`, rather than `today` itself, proves the wiring: if
    `today` ever went back to calling `datetime.now(UTC)` directly, this
    override would have no effect and the probe would report the real
    wall-clock date instead.
    """
    settings = Settings(
        DB=str(db_path),
        SHARED_PASSWORD=SecretStr(TEST_PASSWORD),
        SESSION_SECRET=SecretStr(TEST_SECRET),
        TIMEZONE="America/Chicago",
        INSECURE_COOKIES=True,
    )
    app = create_app(settings)
    injected_instant = datetime(2026, 3, 15, 4, 30, tzinfo=UTC)
    add_today_probe(app)
    app.dependency_overrides[now] = lambda: injected_instant
    try:
        with TestClient(app) as client:
            login(client)
            response = client.get("/api/v1/_test/today")
    finally:
        app.dependency_overrides.pop(now, None)

    assert response.json() == {"today": "2026-03-14"}
