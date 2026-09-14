"""Integer-only money rounding.

Round half up, never banker's rounding, so recipe estimates and bake costs
agree (see ``docs/data-model.md``, "Recipe cost estimate and batch cost
split"). No ``float``, ``Decimal``, or ``fractions`` involved: the fraction
``numerator / denominator`` is rounded using only integer arithmetic.
"""


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
