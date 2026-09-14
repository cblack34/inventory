"""Pins the business-timezone clock (docs/data-model.md, "Expiration")."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from inventory.app import business_today, now


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
