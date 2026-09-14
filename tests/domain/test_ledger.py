"""Pins the ledger rules in docs/data-model.md: derived on-hand, FIFO

allocation by expiration, and sequential undo planning.
"""

from datetime import date

import pytest

from inventory.domain.ledger import (
    BatchOrder,
    InsufficientStock,
    Movement,
    OnHand,
    PlannedMovement,
    allocate_fifo,
    apply,
    on_hand,
    plan_reversal,
)

KITCHEN = 1
STAND = 2
MARKET = 3
PRODUCTION = 100
SOLD = 101
WASTE = 102

INVENTORY_LOCATIONS = {KITCHEN, STAND, MARKET}
SIZE = 1


def test_on_hand_matches_independent_fold_and_excludes_terminal_locations() -> None:
    movements = [
        Movement(
            id=1,
            batch_id=1,
            size_id=SIZE,
            from_location_id=PRODUCTION,
            to_location_id=KITCHEN,
            quantity=20,
        ),
        Movement(
            id=2,
            batch_id=1,
            size_id=SIZE,
            from_location_id=KITCHEN,
            to_location_id=STAND,
            quantity=8,
        ),
        Movement(
            id=3, batch_id=1, size_id=SIZE, from_location_id=STAND, to_location_id=SOLD, quantity=5
        ),
        Movement(
            id=4,
            batch_id=1,
            size_id=SIZE,
            from_location_id=STAND,
            to_location_id=WASTE,
            quantity=1,
        ),
    ]

    result = on_hand(movements, INVENTORY_LOCATIONS)

    independent_fold: dict[tuple[int, int, int], int] = {}
    for movement in movements:
        if movement.to_location_id in INVENTORY_LOCATIONS:
            key = (movement.to_location_id, movement.size_id, movement.batch_id)
            independent_fold[key] = independent_fold.get(key, 0) + movement.quantity
        if movement.from_location_id in INVENTORY_LOCATIONS:
            key = (movement.from_location_id, movement.size_id, movement.batch_id)
            independent_fold[key] = independent_fold.get(key, 0) - movement.quantity
    independent_fold = {
        key: quantity for key, quantity in independent_fold.items() if quantity != 0
    }

    assert result == independent_fold
    assert result == {(KITCHEN, SIZE, 1): 12, (STAND, SIZE, 1): 2}
    # Production, Sold, and Waste (terminal) never appear, even though
    # movements flowed to or from them.
    assert all(location in INVENTORY_LOCATIONS for location, _, _ in result)


def test_allocate_fifo_drains_the_earlier_expiring_batch_first_even_when_baked_later() -> None:
    batches = {
        1: BatchOrder(batch_id=1, expires=date(2026, 9, 20), baked=date(2026, 9, 10)),
        2: BatchOrder(batch_id=2, expires=date(2026, 9, 15), baked=date(2026, 9, 12)),
    }
    stock: OnHand = {(KITCHEN, SIZE, 1): 5, (KITCHEN, SIZE, 2): 4}

    allocation = allocate_fifo(stock, KITCHEN, SIZE, 6, batches)

    # Batch 2 was baked later than batch 1 but expires first, so it drains
    # fully before batch 1 supplies the remainder. Ordering by baked date
    # or by id would put batch 1 first and fail this assertion.
    assert allocation == [(2, 4), (1, 2)]
    # The input is untouched.
    assert stock == {(KITCHEN, SIZE, 1): 5, (KITCHEN, SIZE, 2): 4}


def test_allocate_fifo_breaks_ties_by_baked_date_then_batch_id() -> None:
    same_day = date(2026, 9, 20)
    batches = {
        3: BatchOrder(batch_id=3, expires=same_day, baked=date(2026, 9, 12)),
        1: BatchOrder(batch_id=1, expires=same_day, baked=date(2026, 9, 10)),
        2: BatchOrder(batch_id=2, expires=same_day, baked=date(2026, 9, 10)),
    }
    stock: OnHand = {(KITCHEN, SIZE, 3): 1, (KITCHEN, SIZE, 1): 1, (KITCHEN, SIZE, 2): 1}

    allocation = allocate_fifo(stock, KITCHEN, SIZE, 3, batches)

    # Equal expiration: earlier baked wins (1 and 2 before 3); equal baked
    # as well: lower batch id wins (1 before 2).
    assert allocation == [(1, 1), (2, 1), (3, 1)]


def test_allocate_fifo_raises_insufficient_stock_and_returns_nothing() -> None:
    batches = {1: BatchOrder(batch_id=1, expires=date(2026, 9, 20), baked=date(2026, 9, 10))}
    stock: OnHand = {(KITCHEN, SIZE, 1): 3}

    with pytest.raises(InsufficientStock) as excinfo:
        allocate_fifo(stock, KITCHEN, SIZE, 5, batches)

    error = excinfo.value
    assert error.location_id == KITCHEN
    assert error.size_id == SIZE
    assert error.on_hand == 3
    assert error.requested == 5


def test_allocate_fifo_zero_quantity_returns_empty_list_without_touching_batches() -> None:
    assert allocate_fifo({}, KITCHEN, SIZE, 0, {}) == []


def test_apply_returns_a_new_dict_and_never_mutates_the_input() -> None:
    stock: OnHand = {(KITCHEN, SIZE, 1): 10}
    planned = PlannedMovement(
        batch_id=1,
        size_id=SIZE,
        from_location_id=KITCHEN,
        to_location_id=STAND,
        quantity=4,
    )

    result = apply(stock, planned, INVENTORY_LOCATIONS)

    assert result == {(KITCHEN, SIZE, 1): 6, (STAND, SIZE, 1): 4}
    assert stock == {(KITCHEN, SIZE, 1): 10}


def test_sequential_undo_of_market_visit_succeeds_where_a_single_snapshot_would_reject_it() -> None:
    """Walk the acceptance example: 10 taken, 6 sold, 1 tossed, 3 returned.

    Reversing in descending id restores the market's on-hand before the
    `taken` reversal is checked, so the whole undo succeeds. Checking that
    same `taken` reversal against a single pre-undo snapshot instead — the
    market nets to zero after the visit, so it holds no on-hand for this
    batch at all — is shown to fail.
    """
    batch_id = 1
    bake = Movement(
        id=1,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=PRODUCTION,
        to_location_id=KITCHEN,
        quantity=20,
    )
    taken = Movement(
        id=2,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=KITCHEN,
        to_location_id=MARKET,
        quantity=10,
    )
    sold = Movement(
        id=3,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=MARKET,
        to_location_id=SOLD,
        quantity=6,
    )
    tossed = Movement(
        id=4,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=MARKET,
        to_location_id=WASTE,
        quantity=1,
    )
    returned = Movement(
        id=5,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=MARKET,
        to_location_id=KITCHEN,
        quantity=3,
    )
    visit_movements = [taken, sold, tossed, returned]

    pre_undo_stock = on_hand([bake, *visit_movements], INVENTORY_LOCATIONS)
    # The market nets to zero (10 - 6 - 1 - 3) and is dropped entirely.
    assert pre_undo_stock == {(KITCHEN, SIZE, batch_id): 13}

    reversals = plan_reversal(visit_movements, pre_undo_stock, INVENTORY_LOCATIONS)

    assert [reversal.reverses_movement_id for reversal in reversals] == [5, 4, 3, 2]
    stock_after_undo = pre_undo_stock
    for reversal in reversals:
        stock_after_undo = apply(stock_after_undo, reversal, INVENTORY_LOCATIONS)
    # Stock after undo equals stock before the visit ever happened.
    assert stock_after_undo == {(KITCHEN, SIZE, batch_id): 20}

    # A single pre-undo snapshot check would reject the `taken` reversal in
    # isolation: the snapshot shows 0 on hand at the market for this batch
    # (it isn't even a key), but reversing `taken` alone needs 10 there.
    with pytest.raises(InsufficientStock) as excinfo:
        plan_reversal([taken], pre_undo_stock, INVENTORY_LOCATIONS)
    assert excinfo.value.location_id == MARKET
    assert excinfo.value.on_hand == 0
    assert excinfo.value.requested == 10


def test_undo_rejected_when_a_later_movement_outside_the_undo_drained_the_source() -> None:
    batch_id = 1
    bake = Movement(
        id=1,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=PRODUCTION,
        to_location_id=KITCHEN,
        quantity=10,
    )
    added_to_stand = Movement(
        id=10,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=KITCHEN,
        to_location_id=STAND,
        quantity=5,
    )
    later_manual_removal = Movement(
        id=20,
        batch_id=batch_id,
        size_id=SIZE,
        from_location_id=STAND,
        to_location_id=WASTE,
        quantity=5,
    )
    stock_before_undo = on_hand([bake, added_to_stand, later_manual_removal], INVENTORY_LOCATIONS)
    assert stock_before_undo == {(KITCHEN, SIZE, batch_id): 5}

    with pytest.raises(InsufficientStock) as excinfo:
        plan_reversal([added_to_stand], stock_before_undo, INVENTORY_LOCATIONS)

    assert excinfo.value.location_id == STAND
    assert excinfo.value.on_hand == 0
    assert excinfo.value.requested == 5


def test_reversal_from_a_terminal_location_needs_no_balance_check() -> None:
    sold = Movement(
        id=3, batch_id=1, size_id=SIZE, from_location_id=MARKET, to_location_id=SOLD, quantity=100
    )

    # No stock data exists for Sold at all (it is terminal and excluded
    # from on-hand), yet reversing a movement out of it succeeds.
    reversals = plan_reversal([sold], {}, INVENTORY_LOCATIONS)

    assert reversals == [
        PlannedMovement(
            batch_id=1,
            size_id=SIZE,
            from_location_id=SOLD,
            to_location_id=MARKET,
            quantity=100,
            reverses_movement_id=3,
        )
    ]
