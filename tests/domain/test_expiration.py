"""Pins the expiration rule in docs/data-model.md: `expired` when
`expires < today`; `expiring_soon` when `0 <= expires - today <= 7 days`;
otherwise `ok`. The two non-"ok" states are mutually exclusive.
"""

from datetime import date, timedelta

from inventory.domain.expiration import expiry_state

TODAY = date(2026, 9, 13)


def test_expires_today_is_soon() -> None:
    assert expiry_state(TODAY, TODAY) == "expiring_soon"


def test_expires_in_seven_days_is_soon() -> None:
    assert expiry_state(TODAY + timedelta(days=7), TODAY) == "expiring_soon"


def test_expires_in_eight_days_is_ok() -> None:
    assert expiry_state(TODAY + timedelta(days=8), TODAY) == "ok"


def test_expired_yesterday_is_expired_and_not_soon() -> None:
    result = expiry_state(TODAY - timedelta(days=1), TODAY)

    assert result == "expired"
    assert result != "expiring_soon"


def test_custom_horizon_is_respected() -> None:
    assert expiry_state(TODAY + timedelta(days=3), TODAY, horizon_days=3) == "expiring_soon"
    assert expiry_state(TODAY + timedelta(days=4), TODAY, horizon_days=3) == "ok"
