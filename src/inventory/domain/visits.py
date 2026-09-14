"""Stand and market visit settlement, and visit profit.

Pure functions over plain data; see ``docs/data-model.md``, "Visit
settlement" and "Profit". Both visit types plan a list of
:class:`~inventory.domain.ledger.PlannedMovement` rows and an expected
revenue figure, computed all at once and returned only on success — a
rejected visit raises before returning anything, so a caller that writes
the plan's movements never sees a partial plan.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from inventory.domain import DomainError
from inventory.domain.ledger import BatchOrder, OnHand, PlannedMovement, allocate_fifo, apply


@dataclass(frozen=True)
class Locations:
    """The fixed location ids and the inventory-location set a visit needs."""

    kitchen_id: int
    sold_id: int
    waste_id: int
    sampled_id: int
    inventory_location_ids: frozenset[int]


@dataclass(frozen=True)
class Context:
    """Inputs shared by both settlement planners, grouped to keep arg counts low."""

    stock: OnHand
    batches: Mapping[int, BatchOrder]
    locations: Locations
    prices_cents: Mapping[int, int]


@dataclass(frozen=True)
class StandRow:
    """One size's counts on a stand-visit payload."""

    size_id: int
    counted: int
    tossed: int
    pulled: int
    added: int


@dataclass(frozen=True)
class MarketRow:
    """One size's counts on a market-visit payload."""

    size_id: int
    taken: int
    returned: int
    tossed: int


@dataclass(frozen=True)
class VisitPlan:
    """The movements a settlement would write, plus its expected revenue."""

    movements: list[PlannedMovement]
    expected_revenue_cents: int


class CountedExceedsOnHandError(DomainError):
    """Stand visit: `counted` for a size exceeds on-hand there.

    `missing = on_hand - counted` would be negative, which the data model
    forbids.
    """

    def __init__(self, *, size_id: int, on_hand: int, counted: int) -> None:
        self.size_id = size_id
        self.on_hand = on_hand
        self.counted = counted
        super().__init__(
            f"size {size_id}: counted {counted} exceeds on-hand {on_hand}",
        )


class OverCountedError(DomainError):
    """Stand visit: `tossed + pulled` exceeds `counted` for a size."""

    def __init__(self, *, size_id: int, counted: int, tossed: int, pulled: int) -> None:
        self.size_id = size_id
        self.counted = counted
        self.tossed = tossed
        self.pulled = pulled
        super().__init__(
            f"size {size_id}: tossed {tossed} + pulled {pulled} exceeds counted {counted}",
        )


class MarketOverTakenError(DomainError):
    """Market visit: `returned + tossed` exceeds `taken` for a size."""

    def __init__(self, *, size_id: int, taken: int, returned: int, tossed: int) -> None:
        self.size_id = size_id
        self.taken = taken
        self.returned = returned
        self.tossed = tossed
        super().__init__(
            f"size {size_id}: returned {returned} + tossed {tossed} exceeds taken {taken}",
        )


@dataclass(frozen=True)
class _Leg:
    """One planned removal or transfer: a size, a quantity, and its two ends."""

    from_location_id: int
    to_location_id: int
    size_id: int
    quantity: int


def _allocate_and_apply(
    stock: OnHand,
    leg: _Leg,
    context: Context,
) -> tuple[list[PlannedMovement], OnHand]:
    """FIFO-allocate `leg.quantity` and fold the resulting movements into `stock`.

    Returns the movements (one per batch the allocation spans) and the
    `stock` that results from applying all of them. A zero-quantity leg
    allocates nothing and returns `stock` unchanged.
    """
    movements: list[PlannedMovement] = []
    allocation = allocate_fifo(
        stock, leg.from_location_id, leg.size_id, leg.quantity, context.batches
    )
    for batch_id, quantity in allocation:
        planned = PlannedMovement(
            batch_id=batch_id,
            size_id=leg.size_id,
            from_location_id=leg.from_location_id,
            to_location_id=leg.to_location_id,
            quantity=quantity,
        )
        movements.append(planned)
        stock = apply(stock, planned, context.locations.inventory_location_ids)
    return movements, stock


def _sale_destination(size_id: int, context: Context) -> int:
    """Sold for a priced size, Sampled for a zero-price (or unpriced) size."""
    price = context.prices_cents.get(size_id, 0)
    return context.locations.sold_id if price > 0 else context.locations.sampled_id


def _stand_on_hand_by_size(stand_id: int, stock: OnHand) -> dict[int, int]:
    totals: dict[int, int] = {}
    for (location_id, size_id, _batch_id), quantity in stock.items():
        if location_id == stand_id:
            totals[size_id] = totals.get(size_id, 0) + quantity
    return totals


def _merge_stand_rows(
    rows: Sequence[StandRow], on_hand_by_size: Mapping[int, int]
) -> list[StandRow]:
    """Fill in a default row for every on-hand size the payload omitted.

    A size the payload doesn't mention settles as `counted = on_hand`
    (no sale, nothing tossed, pulled, or added).
    """
    by_size = {row.size_id: row for row in rows}
    for size_id, on_hand_quantity in on_hand_by_size.items():
        if size_id not in by_size:
            by_size[size_id] = StandRow(
                size_id=size_id, counted=on_hand_quantity, tossed=0, pulled=0, added=0
            )
    return [by_size[size_id] for size_id in sorted(by_size)]


def _stand_missing(row: StandRow, on_hand_quantity: int) -> int:
    missing = on_hand_quantity - row.counted
    if missing < 0:
        raise CountedExceedsOnHandError(
            size_id=row.size_id, on_hand=on_hand_quantity, counted=row.counted
        )
    if row.tossed + row.pulled > row.counted:
        raise OverCountedError(
            size_id=row.size_id, counted=row.counted, tossed=row.tossed, pulled=row.pulled
        )
    return missing


def _allocate_stand_row(
    row: StandRow,
    missing: int,
    stand_id: int,
    stock: OnHand,
    context: Context,
) -> tuple[list[PlannedMovement], OnHand]:
    """Allocate missing, tossed, and pulled in sequence from the stand's pre-visit stock.

    Each step allocates from what the previous one left, per the
    "Stand visit" allocation-order rule.
    """
    movements: list[PlannedMovement] = []
    legs = (
        _Leg(stand_id, _sale_destination(row.size_id, context), row.size_id, missing),
        _Leg(stand_id, context.locations.waste_id, row.size_id, row.tossed),
        _Leg(stand_id, context.locations.kitchen_id, row.size_id, row.pulled),
    )
    for leg in legs:
        step_movements, stock = _allocate_and_apply(stock, leg, context)
        movements.extend(step_movements)
    return movements, stock


def plan_stand_visit(
    stand_id: int,
    rows: Sequence[StandRow],
    context: Context,
) -> VisitPlan:
    """Plan a stand visit's movements and expected revenue.

    See ``docs/data-model.md``, "Visit settlement" > "Stand visit", for the
    full rule set this pins.
    """
    on_hand_by_size = _stand_on_hand_by_size(stand_id, context.stock)
    merged_rows = _merge_stand_rows(rows, on_hand_by_size)

    movements: list[PlannedMovement] = []
    expected_revenue_cents = 0
    stand_stock = context.stock
    for row in merged_rows:
        missing = _stand_missing(row, on_hand_by_size.get(row.size_id, 0))
        expected_revenue_cents += missing * context.prices_cents.get(row.size_id, 0)

        row_movements, stand_stock = _allocate_stand_row(
            row, missing, stand_id, stand_stock, context
        )
        movements.extend(row_movements)

        # `added` allocates FIFO over Kitchen's pre-visit stock (`context.stock`,
        # untouched by this visit's own `pulled` step) so it can never select
        # units this same visit pulls back.
        added_leg = _Leg(context.locations.kitchen_id, stand_id, row.size_id, row.added)
        added_movements, _ = _allocate_and_apply(context.stock, added_leg, context)
        movements.extend(added_movements)

    return VisitPlan(movements=movements, expected_revenue_cents=expected_revenue_cents)


def _market_missing(row: MarketRow) -> int:
    missing = row.taken - row.returned - row.tossed
    if missing < 0:
        raise MarketOverTakenError(
            size_id=row.size_id, taken=row.taken, returned=row.returned, tossed=row.tossed
        )
    return missing


def _allocate_market_row(
    row: MarketRow,
    missing: int,
    market_id: int,
    stock: OnHand,
    context: Context,
) -> tuple[list[PlannedMovement], OnHand]:
    """Run the four market-visit steps in their normative order.

    Taken (Kitchen -> market), then missing, then tossed, then returned,
    each FIFO over what the previous step left at the market. Reordering
    these would assign different batches, and therefore different frozen
    unit costs, to Sold, Waste, and Kitchen.
    """
    movements: list[PlannedMovement] = []
    legs = (
        _Leg(context.locations.kitchen_id, market_id, row.size_id, row.taken),
        _Leg(market_id, _sale_destination(row.size_id, context), row.size_id, missing),
        _Leg(market_id, context.locations.waste_id, row.size_id, row.tossed),
        _Leg(market_id, context.locations.kitchen_id, row.size_id, row.returned),
    )
    for leg in legs:
        step_movements, stock = _allocate_and_apply(stock, leg, context)
        movements.extend(step_movements)
    return movements, stock


def plan_market_visit(
    market_id: int,
    rows: Sequence[MarketRow],
    context: Context,
) -> VisitPlan:
    """Plan a market visit's movements and expected revenue.

    See ``docs/data-model.md``, "Visit settlement" > "Market visit", for
    the full rule set this pins.
    """
    movements: list[PlannedMovement] = []
    expected_revenue_cents = 0
    stock = context.stock
    for row in rows:
        missing = _market_missing(row)
        expected_revenue_cents += missing * context.prices_cents.get(row.size_id, 0)

        row_movements, stock = _allocate_market_row(row, missing, market_id, stock, context)
        movements.extend(row_movements)

    return VisitPlan(movements=movements, expected_revenue_cents=expected_revenue_cents)


@dataclass(frozen=True)
class Profit:
    """A visit's profit, with the three cost lines that make it up visible."""

    sold_cost_cents: int
    waste_cost_cents: int
    sampled_cost_cents: int
    profit_cents: int


def _cost_to(
    movements: Sequence[PlannedMovement],
    destination_id: int,
    unit_costs_cents: Mapping[tuple[int, int], int],
) -> int:
    return sum(
        unit_costs_cents[(movement.batch_id, movement.size_id)] * movement.quantity
        for movement in movements
        if movement.to_location_id == destination_id
    )


def visit_profit(
    revenue_cents: int,
    fee_cents: int,
    movements: Sequence[PlannedMovement],
    unit_costs_cents: Mapping[tuple[int, int], int],
    locations: Locations,
) -> Profit:
    """`profit = revenue - fee - cost_of(Sold) - cost_of(Waste) - cost_of(Sampled)`.

    Each cost is `sum(unit_cost * quantity)` over this visit's movements
    into that destination. `unit_costs_cents` is keyed by
    `(batch_id, size_id)`; this function does not compute the split, only
    sums it. Profit may be negative (for example when `fee_cents` exceeds
    `revenue_cents`).
    """
    sold_cost_cents = _cost_to(movements, locations.sold_id, unit_costs_cents)
    waste_cost_cents = _cost_to(movements, locations.waste_id, unit_costs_cents)
    sampled_cost_cents = _cost_to(movements, locations.sampled_id, unit_costs_cents)
    profit_cents = (
        revenue_cents - fee_cents - sold_cost_cents - waste_cost_cents - sampled_cost_cents
    )
    return Profit(
        sold_cost_cents=sold_cost_cents,
        waste_cost_cents=waste_cost_cents,
        sampled_cost_cents=sampled_cost_cents,
        profit_cents=profit_cents,
    )
