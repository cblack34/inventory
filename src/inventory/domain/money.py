"""Integer-only money rounding, and the bound on a persisted money total.

Round half up, never banker's rounding, so recipe estimates and bake costs
agree (see ``docs/data-model.md``, "Recipe cost estimate and batch cost
split"). No ``float``, ``Decimal``, or ``fractions`` involved: the fraction
``numerator / denominator`` is rounded using only integer arithmetic.

``inventory.api.schemas.numbers`` bounds every individual money, weight, or
quantity *input* at ``10**9``, but nothing bounds the aggregates computed
from them: ten recipe lines each at the per-field maximum give a recipe
cost of ``10**19``, above SQLite's signed 64-bit ``INTEGER`` range
(~9.22 * 10**18). ``MAX_TOTAL_CENTS`` and ``require_bounded_total`` below
are the one place a *persisted total* (a batch's frozen cost, a visit's
expected revenue, or a visit's Sold+Waste+Sampled movement cost) is
checked before it reaches the database -- the
persistence boundary calls this, never the pure cost-split functions
above, so a read-only estimate (never persisted, and a plain Python int)
is unaffected.
"""

from inventory.domain import DomainError


class AmountTooLargeError(DomainError):
    """A persisted money total exceeded ``MAX_TOTAL_CENTS``."""

    def __init__(self, *, field: str, value: int, limit: int) -> None:
        self.field = field
        self.value = value
        self.limit = limit
        super().__init__(f"{field} = {value} exceeds the maximum of {limit}")


MAX_TOTAL_CENTS = 10**12
"""Upper bound for a persisted money total.

Comfortably inside SQLite's signed 64-bit ``INTEGER`` range
(~9.22 * 10**18) even summed across many rows, and far above any real
total this two-person business will ever produce.
"""


def require_bounded_total(value: int, *, field: str) -> None:
    """Raise ``AmountTooLargeError`` if `value` exceeds ``MAX_TOTAL_CENTS``."""
    if value > MAX_TOTAL_CENTS:
        raise AmountTooLargeError(field=field, value=value, limit=MAX_TOTAL_CENTS)


def round_half_up(numerator: int, denominator: int) -> int:
    """Round ``numerator / denominator`` to the nearest integer, half up.

    Assumes a non-negative ``numerator``; callers in this domain only ever
    round non-negative cent amounts. Raises ``ValueError`` for a
    non-positive ``denominator``, which would make the fraction undefined
    or ill-signed.
    """
    if denominator <= 0:
        msg = f"denominator must be positive, got {denominator}"
        raise ValueError(msg)
    return (2 * numerator + denominator) // (2 * denominator)
