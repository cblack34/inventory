"""Shared upper bound for money, weight, and quantity inputs across the API.

Every bare `Field(ge=0)`/`Field(ge=1)` on a money (`_cents`), weight
(`_g`), or quantity field accepted an arbitrary-size Python `int`: a
request such as `current_price_cents = 2**63` passed that validation,
then overflowed at the database boundary -- SQLite's signed 64-bit
`INTEGER` cannot hold it, so `sqlite3` raised `OverflowError` binding
the value, which the app has no handler for, reaching the client as an
unhandled 500 instead of a 422 Problem. Their arithmetic (a recipe's
summed line cost, a batch's summed size cost) can also overflow even
when every individual input fits.

`10**9` (one billion, of cents or grams or units) is far above any
real value this two-person cottage business will ever enter, and far
below where summing a handful of such inputs could itself approach the
signed 64-bit boundary, so bounding each input there is a belt-and-
suspenders API-level check -- not a business rule, which belongs in
`docs/data-model.md` if one is ever needed.
"""

from typing import Annotated

from pydantic import Field

_MAX_AMOUNT = 10**9

Cents = Annotated[int, Field(strict=True, ge=0, le=_MAX_AMOUNT)]
"""A nonnegative money amount in integer cents (a price, a fee, revenue)."""

Count = Annotated[int, Field(strict=True, ge=0, le=_MAX_AMOUNT)]
"""A nonnegative quantity or weight (a count of units, a weight in grams)."""

PositiveCount = Annotated[int, Field(strict=True, ge=1, le=_MAX_AMOUNT)]
"""The `ge=1` variant of `Count`, for a quantity or weight that must be positive."""
