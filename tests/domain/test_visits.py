"""Pins docs/data-model.md's "Visit settlement" and "Profit" sections, and
the matching rows in docs/acceptance.md's "Stand visit", "Market visit",
and "Profit" sections.
"""

from datetime import date

import pytest

from inventory.domain.ledger import BatchOrder, OnHand, PlannedMovement, allocate_fifo
from inventory.domain.visits import (
    Context,
    CountedExceedsOnHandError,
    Locations,
    MarketOverTakenError,
    MarketRow,
    OverCountedError,
    Profit,
    StandRow,
    plan_market_visit,
    plan_stand_visit,
    visit_profit,
)

KITCHEN = 1
STAND = 10
MARKET = 20
SOLD = 100
WASTE = 101
SAMPLED = 102

INVENTORY_LOCATIONS = frozenset({KITCHEN, STAND, MARKET})
LOCATIONS = Locations(
    kitchen_id=KITCHEN,
    sold_id=SOLD,
    waste_id=WASTE,
    sampled_id=SAMPLED,
    inventory_location_ids=INVENTORY_LOCATIONS,
)

PRICED_SIZE = 1
SAMPLE_SIZE = 2

EARLY = BatchOrder(batch_id=1, expires=date(2026, 9, 15), baked=date(2026, 9, 1))
LATE = BatchOrder(batch_id=2, expires=date(2026, 9, 25), baked=date(2026, 9, 10))


def _context(
    stock: OnHand, batches: dict[int, BatchOrder], prices_cents: dict[int, int]
) -> Context:
    return Context(stock=stock, batches=batches, locations=LOCATIONS, prices_cents=prices_cents)


class TestStandVisit:
    def test_missing_priced_size_sells_and_missing_zero_price_size_samples(self) -> None:
        stock: OnHand = {
            (STAND, PRICED_SIZE, EARLY.batch_id): 5,
            (STAND, SAMPLE_SIZE, LATE.batch_id): 5,
        }
        batches = {EARLY.batch_id: EARLY, LATE.batch_id: LATE}
        prices = {PRICED_SIZE: 200, SAMPLE_SIZE: 0}
        rows = [
            StandRow(size_id=PRICED_SIZE, counted=4, tossed=0, pulled=0, added=0),
            StandRow(size_id=SAMPLE_SIZE, counted=4, tossed=0, pulled=0, added=0),
        ]

        plan = plan_stand_visit(STAND, rows, _context(stock, batches, prices))

        assert (
            PlannedMovement(
                batch_id=EARLY.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=STAND,
                to_location_id=SOLD,
                quantity=1,
            )
            in plan.movements
        )
        assert (
            PlannedMovement(
                batch_id=LATE.batch_id,
                size_id=SAMPLE_SIZE,
                from_location_id=STAND,
                to_location_id=SAMPLED,
                quantity=1,
            )
            in plan.movements
        )
        # The zero-price size's missing unit never touches Sold.
        assert not any(
            movement.size_id == SAMPLE_SIZE and movement.to_location_id == SOLD
            for movement in plan.movements
        )
        assert plan.expected_revenue_cents == 200  # only the priced size's missing unit counts

    def test_a_size_absent_from_rows_settles_as_counted_equals_on_hand(self) -> None:
        stock: OnHand = {(STAND, PRICED_SIZE, EARLY.batch_id): 3}
        batches = {EARLY.batch_id: EARLY}
        context = _context(stock, batches, {PRICED_SIZE: 200})

        plan = plan_stand_visit(STAND, [], context)

        assert plan.movements == []
        assert plan.expected_revenue_cents == 0

    def test_counted_exceeding_on_hand_is_rejected_naming_size_on_hand_and_counted(self) -> None:
        stock: OnHand = {(STAND, PRICED_SIZE, EARLY.batch_id): 3}
        batches = {EARLY.batch_id: EARLY}
        context = _context(stock, batches, {PRICED_SIZE: 200})
        rows = [StandRow(size_id=PRICED_SIZE, counted=5, tossed=0, pulled=0, added=0)]

        with pytest.raises(CountedExceedsOnHandError) as excinfo:
            plan_stand_visit(STAND, rows, context)

        assert excinfo.value.size_id == PRICED_SIZE
        assert excinfo.value.on_hand == 3
        assert excinfo.value.counted == 5

    def test_tossed_plus_pulled_exceeding_counted_is_rejected_naming_the_size(self) -> None:
        stock: OnHand = {(STAND, PRICED_SIZE, EARLY.batch_id): 5}
        batches = {EARLY.batch_id: EARLY}
        context = _context(stock, batches, {PRICED_SIZE: 200})
        rows = [StandRow(size_id=PRICED_SIZE, counted=5, tossed=3, pulled=3, added=0)]

        with pytest.raises(OverCountedError) as excinfo:
            plan_stand_visit(STAND, rows, context)

        assert excinfo.value.size_id == PRICED_SIZE

    def test_added_allocates_from_kitchens_pre_visit_stock_never_units_just_pulled_back(
        self,
    ) -> None:
        # Batch EARLY (the earlier-expiring batch) starts at the stand and is
        # entirely pulled back to Kitchen by this same visit. Batch LATE
        # starts at Kitchen. If `added` used Kitchen's stock *after* the pull
        # was applied, FIFO would prefer the newly arrived, earlier-expiring
        # EARLY batch over LATE. It must not: `added` has to come from LATE.
        stock: OnHand = {
            (STAND, PRICED_SIZE, EARLY.batch_id): 3,
            (KITCHEN, PRICED_SIZE, LATE.batch_id): 2,
        }
        batches = {EARLY.batch_id: EARLY, LATE.batch_id: LATE}
        context = _context(stock, batches, {PRICED_SIZE: 200})
        rows = [StandRow(size_id=PRICED_SIZE, counted=3, tossed=0, pulled=3, added=2)]

        plan = plan_stand_visit(STAND, rows, context)

        pulled = [
            m for m in plan.movements if m.to_location_id == KITCHEN and m.from_location_id == STAND
        ]
        added = [
            m for m in plan.movements if m.to_location_id == STAND and m.from_location_id == KITCHEN
        ]
        assert pulled == [
            PlannedMovement(
                batch_id=EARLY.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=STAND,
                to_location_id=KITCHEN,
                quantity=3,
            )
        ]
        assert added == [
            PlannedMovement(
                batch_id=LATE.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=KITCHEN,
                to_location_id=STAND,
                quantity=2,
            )
        ]


class TestMarketVisit:
    def test_returned_plus_tossed_exceeding_taken_is_rejected(self) -> None:
        stock: OnHand = {(KITCHEN, PRICED_SIZE, EARLY.batch_id): 10}
        batches = {EARLY.batch_id: EARLY}
        context = _context(stock, batches, {PRICED_SIZE: 200})
        rows = [MarketRow(size_id=PRICED_SIZE, taken=5, returned=3, tossed=3)]

        with pytest.raises(MarketOverTakenError) as excinfo:
            plan_market_visit(MARKET, rows, context)

        assert excinfo.value.size_id == PRICED_SIZE
        assert excinfo.value.taken == 5
        assert excinfo.value.returned == 3
        assert excinfo.value.tossed == 3

    def test_steps_allocate_in_normative_order_reordering_would_assign_different_batches(
        self,
    ) -> None:
        # Two batches at Kitchen: EARLY (2 units) expires first, LATE (4
        # units) second. `taken` drains both fully into the market.
        stock: OnHand = {
            (KITCHEN, PRICED_SIZE, EARLY.batch_id): 2,
            (KITCHEN, PRICED_SIZE, LATE.batch_id): 4,
        }
        batches = {EARLY.batch_id: EARLY, LATE.batch_id: LATE}
        context = _context(stock, batches, {PRICED_SIZE: 200})
        rows = [MarketRow(size_id=PRICED_SIZE, taken=6, returned=2, tossed=1)]
        # missing = taken - returned - tossed = 3

        plan = plan_market_visit(MARKET, rows, context)

        sold = sorted(
            ((m.batch_id, m.quantity) for m in plan.movements if m.to_location_id == SOLD),
        )
        tossed = sorted(
            ((m.batch_id, m.quantity) for m in plan.movements if m.to_location_id == WASTE),
        )
        returned = sorted(
            (
                (m.batch_id, m.quantity)
                for m in plan.movements
                if m.to_location_id == KITCHEN and m.from_location_id == MARKET
            ),
        )
        # Normative order (missing before tossed): missing takes EARLY's 2
        # then 1 of LATE; tossed then takes 1 more of LATE; 2 of LATE remain
        # to return.
        assert sold == [(EARLY.batch_id, 2), (LATE.batch_id, 1)]
        assert tossed == [(LATE.batch_id, 1)]
        assert returned == [(LATE.batch_id, 2)]

        # Prove order matters: tossing before missing over the same
        # post-`taken` market stock assigns EARLY's units to Waste instead
        # of Sold, a different result than the normative order produced.
        post_taken_stock: OnHand = {
            (MARKET, PRICED_SIZE, EARLY.batch_id): 2,
            (MARKET, PRICED_SIZE, LATE.batch_id): 4,
        }
        reordered_tossed = allocate_fifo(post_taken_stock, MARKET, PRICED_SIZE, 1, batches)
        assert reordered_tossed == [(EARLY.batch_id, 1)]
        assert reordered_tossed != tossed

    def test_expected_revenue_is_sum_of_missing_times_price(self) -> None:
        stock: OnHand = {(KITCHEN, PRICED_SIZE, EARLY.batch_id): 10}
        batches = {EARLY.batch_id: EARLY}
        context = _context(stock, batches, {PRICED_SIZE: 150})
        rows = [MarketRow(size_id=PRICED_SIZE, taken=6, returned=2, tossed=1)]
        # missing = 6 - 2 - 1 = 3

        plan = plan_market_visit(MARKET, rows, context)

        assert plan.expected_revenue_cents == 3 * 150


class TestVisitProfit:
    def test_profit_equals_revenue_minus_fee_minus_costs_of_sold_waste_sampled(self) -> None:
        unit_costs_cents = {(EARLY.batch_id, PRICED_SIZE): 40, (LATE.batch_id, SAMPLE_SIZE): 10}
        movements = [
            PlannedMovement(
                batch_id=EARLY.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=MARKET,
                to_location_id=SOLD,
                quantity=3,
            ),
            PlannedMovement(
                batch_id=EARLY.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=MARKET,
                to_location_id=WASTE,
                quantity=1,
            ),
            PlannedMovement(
                batch_id=LATE.batch_id,
                size_id=SAMPLE_SIZE,
                from_location_id=MARKET,
                to_location_id=SAMPLED,
                quantity=2,
            ),
            PlannedMovement(
                batch_id=EARLY.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=MARKET,
                to_location_id=KITCHEN,
                quantity=2,
            ),
        ]

        profit = visit_profit(
            revenue_cents=1000,
            fee_cents=200,
            movements=movements,
            unit_costs_cents=unit_costs_cents,
            locations=LOCATIONS,
        )

        assert profit == Profit(
            sold_cost_cents=3 * 40,
            waste_cost_cents=1 * 40,
            sampled_cost_cents=2 * 10,
            profit_cents=1000 - 200 - (3 * 40) - (1 * 40) - (2 * 10),
        )

    def test_fee_exceeding_revenue_gives_negative_profit_not_an_error(self) -> None:
        unit_costs_cents = {(EARLY.batch_id, PRICED_SIZE): 5}
        movements = [
            PlannedMovement(
                batch_id=EARLY.batch_id,
                size_id=PRICED_SIZE,
                from_location_id=MARKET,
                to_location_id=SOLD,
                quantity=1,
            )
        ]

        profit = visit_profit(
            revenue_cents=10,
            fee_cents=100,
            movements=movements,
            unit_costs_cents=unit_costs_cents,
            locations=LOCATIONS,
        )

        assert profit.profit_cents == 10 - 100 - 5
        assert profit.profit_cents < 0
