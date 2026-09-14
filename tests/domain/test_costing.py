"""Pin the money-math acceptance numbers from docs/data-model.md and
docs/acceptance.md.
"""

import pytest

from inventory.domain.costing import (
    RecipeLine,
    SizeYield,
    ZeroWeightError,
    recipe_cost_cents,
    split_unit_costs,
    unit_cost_drift_bound,
)
from inventory.domain.money import round_half_up


class TestRoundHalfUp:
    def test_rounds_half_up_not_to_even(self) -> None:
        # 125 / 2 == 62.5 -> round_half_up gives 63; Python's round() gives
        # 62 (round-half-to-even), so the two must differ here.
        assert round_half_up(125, 2) == 63
        assert round(62.5) == 62

        # 25 / 2 == 12.5 -> round_half_up gives 13; round() gives 12.
        assert round_half_up(25, 2) == 13
        assert round(12.5) == 12

        # 25 / 1 == 25.0, an exact case with no rounding ambiguity.
        assert round_half_up(25, 1) == 25
        assert round(25.0) == 25

    def test_rejects_non_positive_denominator(self) -> None:
        with pytest.raises(ValueError, match="denominator"):
            round_half_up(10, 0)
        with pytest.raises(ValueError, match="denominator"):
            round_half_up(10, -1)


class TestRecipeCostCents:
    def test_sums_quantity_times_unit_price_exactly(self) -> None:
        lines = [
            RecipeLine(quantity=2, unit_price_cents=50),
            RecipeLine(quantity=3, unit_price_cents=0),
            RecipeLine(quantity=1, unit_price_cents=100),
        ]

        assert recipe_cost_cents(lines) == 200

    def test_empty_lines_cost_nothing(self) -> None:
        assert recipe_cost_cents([]) == 0


class TestSplitUnitCosts:
    def test_recipe_estimate_matches_pinned_acceptance_numbers(self) -> None:
        # 200-cent recipe, sizes of portion weight 50/20/10, typical yield
        # 2 each (typical total weight 160) -> per-size costs 63/25/13.
        yields = [
            SizeYield(size_id=1, portion_weight_g=50, count=2),
            SizeYield(size_id=2, portion_weight_g=20, count=2),
            SizeYield(size_id=3, portion_weight_g=10, count=2),
        ]

        assert split_unit_costs(200, yields) == {1: 63, 2: 25, 3: 13}

    def test_bake_single_size_matches_pinned_acceptance_number(self) -> None:
        # 1010-cent batch, one size, 20 units -> unit cost 51.
        yields = [SizeYield(size_id=1, portion_weight_g=100, count=20)]

        assert split_unit_costs(1010, yields) == {1: 51}

    def test_bake_three_sizes_matches_pinned_acceptance_numbers(self) -> None:
        # 1000-cent batch, portion weights 200/100/50, counts 2/4/2 ->
        # per-size unit costs 222/111/56; an equal split by count (125
        # each) is a different, wrong answer.
        yields = [
            SizeYield(size_id=1, portion_weight_g=200, count=2),
            SizeYield(size_id=2, portion_weight_g=100, count=4),
            SizeYield(size_id=3, portion_weight_g=50, count=2),
        ]

        result = split_unit_costs(1000, yields)

        assert result == {1: 222, 2: 111, 3: 56}
        assert result != {1: 125, 2: 125, 3: 125}

    def test_zero_total_weight_raises(self) -> None:
        yields = [SizeYield(size_id=1, portion_weight_g=0, count=0)]

        with pytest.raises(ZeroWeightError):
            split_unit_costs(100, yields)


class TestUnitCostDriftBound:
    def test_matches_ceiling_of_half_total_units(self) -> None:
        assert unit_cost_drift_bound(0) == 0
        assert unit_cost_drift_bound(1) == 1
        assert unit_cost_drift_bound(4) == 2
        assert unit_cost_drift_bound(5) == 3

    @pytest.mark.parametrize(
        ("batch_cost_cents", "yields"),
        [
            # data-model.md's example: exact equality is impossible here.
            (
                101,
                [
                    SizeYield(size_id=1, portion_weight_g=1, count=2),
                    SizeYield(size_id=2, portion_weight_g=1, count=2),
                ],
            ),
            (200, [SizeYield(size_id=1, portion_weight_g=50, count=2)]),
            (
                1000,
                [
                    SizeYield(size_id=1, portion_weight_g=200, count=2),
                    SizeYield(size_id=2, portion_weight_g=100, count=4),
                    SizeYield(size_id=3, portion_weight_g=50, count=2),
                ],
            ),
            (
                333,
                [
                    SizeYield(size_id=1, portion_weight_g=7, count=3),
                    SizeYield(size_id=2, portion_weight_g=13, count=5),
                    SizeYield(size_id=3, portion_weight_g=1, count=1),
                ],
            ),
            (1, [SizeYield(size_id=1, portion_weight_g=1, count=10)]),
        ],
    )
    def test_drift_never_exceeds_bound(
        self, batch_cost_cents: int, yields: list[SizeYield]
    ) -> None:
        unit_costs = split_unit_costs(batch_cost_cents, yields)
        total_units = sum(size_yield.count for size_yield in yields)
        total_allocated_cents = sum(
            unit_costs[size_yield.size_id] * size_yield.count for size_yield in yields
        )

        drift = abs(total_allocated_cents - batch_cost_cents)

        assert drift <= unit_cost_drift_bound(total_units)
