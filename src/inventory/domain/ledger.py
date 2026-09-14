"""Movement ledger: derived on-hand, FIFO allocation, and undo planning.

Stock is never stored; every stock figure here is folded from a list of
:class:`Movement` rows. Weights and prices live outside this module — a
movement carries only integer quantities. See ``docs/data-model.md``
("FIFO allocation" and "Corrections") for the rules this module pins.
"""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from inventory.domain import DomainError


@dataclass(frozen=True)
class Movement:
    """One append-only ledger row.

    `quantity` units of one batch and size moved from one location to
    another.
    """

    id: int
    batch_id: int
    size_id: int
    from_location_id: int
    to_location_id: int
    quantity: int


@dataclass(frozen=True)
class PlannedMovement:
    """A movement not yet written.

    The output of allocation or reversal planning, before it becomes a
    persisted :class:`Movement`.
    """

    batch_id: int
    size_id: int
    from_location_id: int
    to_location_id: int
    quantity: int
    reverses_movement_id: int | None = None


@dataclass(frozen=True)
class BatchOrder:
    """The FIFO ordering key for one batch.

    Earliest `expires` first, then earliest `baked`, then lowest
    `batch_id`.
    """

    batch_id: int
    expires: date
    baked: date


StockKey = tuple[int, int, int]
"""``(location_id, size_id, batch_id)``."""

OnHand = dict[StockKey, int]
"""Derived stock: quantity on hand per (location, size, batch)."""


class InsufficientStock(DomainError):  # noqa: N818 -- name is pinned by issue #10.
    """A removal or reversal would drive on-hand negative at a location."""

    def __init__(self, *, location_id: int, size_id: int, on_hand: int, requested: int) -> None:
        self.location_id = location_id
        self.size_id = size_id
        self.on_hand = on_hand
        self.requested = requested
        super().__init__(
            f"insufficient stock at location {location_id} for size {size_id}: "
            f"on hand {on_hand}, requested {requested}"
        )


def on_hand(movements: Iterable[Movement], inventory_location_ids: Collection[int]) -> OnHand:
    """Fold a movement list into on-hand per (location, size, batch).

    Only inventory locations (never terminal ones) appear in the result,
    and a (location, size, batch) that nets to zero is dropped rather than
    kept as an explicit zero.
    """
    totals: OnHand = {}
    for movement in movements:
        if movement.to_location_id in inventory_location_ids:
            key = (movement.to_location_id, movement.size_id, movement.batch_id)
            totals[key] = totals.get(key, 0) + movement.quantity
        if movement.from_location_id in inventory_location_ids:
            key = (movement.from_location_id, movement.size_id, movement.batch_id)
            totals[key] = totals.get(key, 0) - movement.quantity
    return {key: quantity for key, quantity in totals.items() if quantity != 0}


def _fifo_sort_key(order: BatchOrder) -> tuple[date, date, int]:
    return (order.expires, order.baked, order.batch_id)


def allocate_fifo(
    stock: OnHand,
    location_id: int,
    size_id: int,
    quantity: int,
    batches: Mapping[int, BatchOrder],
) -> list[tuple[int, int]]:
    """Choose which batches supply `quantity` units at (location, size).

    Earliest `expires` first, then earliest `baked`, then lowest
    `batch_id`; a single request may span several batches. Raises
    :class:`InsufficientStock` naming `location_id`, `size_id`, the total
    on hand, and `quantity` if there is not enough. Never mutates `stock`.
    """
    if quantity == 0:
        return []

    candidates = [
        (batch_id, available)
        for (candidate_location, candidate_size, batch_id), available in stock.items()
        if candidate_location == location_id and candidate_size == size_id and available > 0
    ]
    candidates.sort(key=lambda candidate: _fifo_sort_key(batches[candidate[0]]))

    available_total = sum(available for _, available in candidates)
    if available_total < quantity:
        raise InsufficientStock(
            location_id=location_id,
            size_id=size_id,
            on_hand=available_total,
            requested=quantity,
        )

    allocation: list[tuple[int, int]] = []
    remaining = quantity
    for batch_id, available in candidates:
        if remaining <= 0:
            break
        take = min(available, remaining)
        allocation.append((batch_id, take))
        remaining -= take
    return allocation


def apply(
    stock: OnHand,
    planned: PlannedMovement,
    inventory_location_ids: Collection[int],
) -> OnHand:
    """Return a new `OnHand` reflecting `planned` applied on top of `stock`.

    A helper for threading stock through a sequence of planned movements
    (used by both undo planning here and by the visits leaf). Never
    mutates `stock`.
    """
    updated = dict(stock)
    if planned.from_location_id in inventory_location_ids:
        key = (planned.from_location_id, planned.size_id, planned.batch_id)
        remaining = updated.get(key, 0) - planned.quantity
        if remaining == 0:
            updated.pop(key, None)
        else:
            updated[key] = remaining
    if planned.to_location_id in inventory_location_ids:
        key = (planned.to_location_id, planned.size_id, planned.batch_id)
        updated[key] = updated.get(key, 0) + planned.quantity
    return updated


def _check_reversal_source(
    reversal: PlannedMovement,
    stock: OnHand,
    inventory_location_ids: Collection[int],
) -> None:
    """Raise `InsufficientStock` if `reversal` would drive its source negative.

    A terminal source (Sold, Waste, Sampled) needs no check: the original
    movement's own row is what put the units there.
    """
    if reversal.from_location_id not in inventory_location_ids:
        return
    key = (reversal.from_location_id, reversal.size_id, reversal.batch_id)
    available = stock.get(key, 0)
    if available < reversal.quantity:
        raise InsufficientStock(
            location_id=reversal.from_location_id,
            size_id=reversal.size_id,
            on_hand=available,
            requested=reversal.quantity,
        )


def plan_reversal(
    original: Sequence[Movement],
    stock: OnHand,
    inventory_location_ids: Collection[int],
) -> list[PlannedMovement]:
    """Plan one reversal per movement in `original`, in descending id order.

    Each reversal targets the same batch and size as the movement it
    undoes and runs from that movement's destination back to its origin.
    The balance check is sequential: each reversal is checked against
    `stock` only after every earlier reversal in this walk has already
    been applied to a working copy — never against a single snapshot
    taken before undo began. All or nothing: raises before returning
    anything if any reversal would drive an inventory-location source
    negative.
    """
    working = dict(stock)
    reversals: list[PlannedMovement] = []
    for movement in sorted(original, key=lambda candidate: candidate.id, reverse=True):
        reversal = PlannedMovement(
            batch_id=movement.batch_id,
            size_id=movement.size_id,
            from_location_id=movement.to_location_id,
            to_location_id=movement.from_location_id,
            quantity=movement.quantity,
            reverses_movement_id=movement.id,
        )
        _check_reversal_source(reversal, working, inventory_location_ids)
        working = apply(working, reversal, inventory_location_ids)
        reversals.append(reversal)
    return reversals
