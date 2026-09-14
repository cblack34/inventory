"""Expiration flags for a batch, relative to an injected `today`.

See ``docs/data-model.md``, "Expiration". `today` is the caller's
responsibility to obtain from the injected clock in the business's
configured timezone; this module takes it as a plain argument so it stays
pure and deterministic, testable without touching the wall clock.
"""

from datetime import date
from typing import Literal

ExpiryState = Literal["expired", "expiring_soon", "ok"]


def expiry_state(expires: date, today: date, horizon_days: int = 7) -> ExpiryState:
    """Classify `expires` relative to `today`.

    `expired` when `expires < today`; `expiring_soon` when
    `0 <= (expires - today).days <= horizon_days`; otherwise `ok`. The two
    non-"ok" states are mutually exclusive: an already-expired batch is
    never also flagged as expiring soon.
    """
    days_until_expiry = (expires - today).days
    if days_until_expiry < 0:
        return "expired"
    if days_until_expiry <= horizon_days:
        return "expiring_soon"
    return "ok"
