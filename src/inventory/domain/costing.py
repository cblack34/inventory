"""Recipe cost estimate and batch cost split by weight.

Pure functions over plain data; see ``docs/data-model.md``, "Recipe cost
estimate and batch cost split". The same split serves the recipe-screen
estimate (typical yield counts) and the bake (actual counts) — one
function, two callers.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from inventory.domain import DomainError
from inventory.domain.money import round_half_up


@dataclass(frozen=True)
class RecipeLine:
    """One ingredient line on a recipe, at a fixed price."""

    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class SizeYield:
    """One size's portion weight and unit count for a cost split."""

    size_id: int
    portion_weight_g: int
    count: int


class ZeroWeightError(DomainError):
    """Raised when the total weight across yields is zero.

    Cost cannot be split by weight without a positive denominator; the
    caller must reject a recipe or bake with zero total yield weight
    before reaching this function.
    """


def recipe_cost_cents(lines: Sequence[RecipeLine]) -> int:
    """Sum ``quantity * unit_price_cents`` over recipe lines.

    Both factors are integers, so the sum is already exact cents; no
    rounding step applies.
    """
    return sum(line.quantity * line.unit_price_cents for line in lines)


def split_unit_costs(batch_cost_cents: int, yields: Sequence[SizeYield]) -> dict[int, int]:
    """Split a cost across sizes proportional to each size's portion weight.

    ``unit_cost(size) = round_half_up(batch_cost * portion_weight, total_weight)``
    where ``total_weight = Σ (portion_weight * count)`` over all yields.
    Raises ``ZeroWeightError`` when total weight is zero.
    """
    total_weight_g = sum(size_yield.portion_weight_g * size_yield.count for size_yield in yields)
    if total_weight_g == 0:
        msg = "total weight across yields is zero; cannot split cost by weight"
        raise ZeroWeightError(msg)
    return {
        size_yield.size_id: round_half_up(
            batch_cost_cents * size_yield.portion_weight_g, total_weight_g
        )
        for size_yield in yields
    }


def unit_cost_drift_bound(total_units: int) -> int:
    """Bound on ``|Σ (unit_cost * count) - batch_cost|`` in cents.

    Each unit's rounding error is at most half a cent, so the bound is
    ``ceil(total_units / 2)``, computed with integer arithmetic.
    """
    return (total_units + 1) // 2
