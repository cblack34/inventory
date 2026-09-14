"""The atomic write path: record a bake, a manual move, or an undo.

Every function here takes an open `Session` and writes rows; none of
them commits -- `inventory.db.transaction.write_transaction` owns the
transaction boundary. Each function calls straight into
`inventory.domain.costing` and `inventory.domain.ledger` for the rules
non-negotiables 2, 3, and 4 pin; nothing here re-derives a rule the
domain package already owns.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Batch, BatchSize, Entry, Ingredient, Location, RecipeLine, Size
from inventory.db.models import Movement as MovementRow
from inventory.db.stock import load_stock
from inventory.domain import DomainError
from inventory.domain.costing import RecipeLine as CostLine
from inventory.domain.costing import SizeYield, recipe_cost_cents, split_unit_costs
from inventory.domain.ledger import Movement as LedgerMovement
from inventory.domain.ledger import allocate_fifo, plan_reversal
from inventory.domain.visits import Locations

_TRANSFERABLE_KINDS = ("kitchen", "stand")


class InvalidQuantityError(DomainError):
    """A count or quantity below the minimum the write path accepts."""

    def __init__(self, *, field: str, value: int, minimum: int) -> None:
        self.field = field
        self.value = value
        self.minimum = minimum
        super().__init__(f"{field} must be at least {minimum}, got {value}")


class UnknownSizeError(DomainError):
    """A bake named a size that does not belong to its recipe."""

    def __init__(self, *, recipe_id: int, size_ids: frozenset[int]) -> None:
        self.recipe_id = recipe_id
        self.size_ids = size_ids
        super().__init__(f"sizes {sorted(size_ids)} do not belong to recipe {recipe_id}")


class ExpiresBeforeBakedError(DomainError):
    """A bake's expiration date is earlier than its baked date."""

    def __init__(self, *, baked: date, expires: date) -> None:
        self.baked = baked
        self.expires = expires
        super().__init__(f"expires {expires} is before baked {baked}")


class SameLocationError(DomainError):
    """A manual move named the same location as both source and destination."""

    def __init__(self, *, location_id: int) -> None:
        self.location_id = location_id
        super().__init__(f"source and destination are both location {location_id}")


class InvalidSourceLocationError(DomainError):
    """A manual move's source is not an inventory location."""

    def __init__(self, *, location_id: int) -> None:
        self.location_id = location_id
        super().__init__(f"location {location_id} is not an inventory location")


class InvalidDestinationLocationError(DomainError):
    """A manual move's destination is not an allowed destination.

    Allowed: an active inventory location that is not a market, or
    Waste, or Sold/Sampled -- resolved by the size's price regardless of
    which of the two the caller names.
    """

    def __init__(self, *, location_id: int) -> None:
        self.location_id = location_id
        super().__init__(f"location {location_id} is not a valid manual-move destination")


class AlreadyVoidedEntryError(DomainError):
    """Undo was requested for an entry that is already voided."""

    def __init__(self, *, entry_id: int) -> None:
        self.entry_id = entry_id
        super().__init__(f"entry {entry_id} is already voided")


class CannotUndoReversalError(DomainError):
    """Undo was requested for a reversal entry; only bake, visit, and manual entries undo."""

    def __init__(self, *, entry_id: int) -> None:
        self.entry_id = entry_id
        super().__init__(f"entry {entry_id} is a reversal and cannot itself be undone")


def _batch_cost_cents(session: Session, recipe_id: int) -> int:
    lines = session.execute(
        select(RecipeLine.quantity, Ingredient.current_price_cents)
        .join(Ingredient, RecipeLine.ingredient_id == Ingredient.id)
        .where(RecipeLine.recipe_id == recipe_id)
    ).all()
    return recipe_cost_cents(
        [
            CostLine(quantity=line.quantity, unit_price_cents=line.current_price_cents)
            for line in lines
        ]
    )


def _bake_yields(session: Session, recipe_id: int, counts: Mapping[int, int]) -> list[SizeYield]:
    for size_id, count in counts.items():
        if count < 0:
            raise InvalidQuantityError(field=f"counts[{size_id}]", value=count, minimum=0)
    sizes = session.execute(
        select(Size.id, Size.portion_weight_g).where(Size.recipe_id == recipe_id)
    ).all()
    unknown = frozenset(counts) - {size.id for size in sizes}
    if unknown:
        raise UnknownSizeError(recipe_id=recipe_id, size_ids=unknown)
    return [
        SizeYield(
            size_id=size.id, portion_weight_g=size.portion_weight_g, count=counts.get(size.id, 0)
        )
        for size in sizes
        if counts.get(size.id, 0) > 0
    ]


@dataclass(frozen=True)
class BakeRequest:
    """Inputs to `record_bake`, grouped to stay under the arg-count lint."""

    recipe_id: int
    baked: date
    expires: date
    counts: Mapping[int, int]


def record_bake(session: Session, request: BakeRequest, *, now: datetime) -> int:
    """Record a bake: frozen batch cost, per-size unit costs, and Production->Kitchen movements.

    Rejects `expires < baked` with `ExpiresBeforeBakedError` and rejects
    an all-zero (or empty) `counts` -- `domain.costing.ZeroWeightError`
    propagates from `split_unit_costs` -- both before writing anything. A
    size absent from `counts`, or present with a zero count, gets no
    `batch_size` row and no movement.
    """
    if request.expires < request.baked:
        raise ExpiresBeforeBakedError(baked=request.baked, expires=request.expires)

    batch_cost_cents = _batch_cost_cents(session, request.recipe_id)
    yields = _bake_yields(session, request.recipe_id, request.counts)
    unit_costs_by_size = split_unit_costs(batch_cost_cents, yields)

    builtins = load_builtin_locations(session)

    entry = Entry(kind="bake", created_at=now, voided=False)
    session.add(entry)
    session.flush()

    batch = Batch(
        recipe_id=request.recipe_id,
        entry_id=entry.id,
        baked=request.baked,
        expires=request.expires,
        total_cost_cents=batch_cost_cents,
    )
    session.add(batch)
    session.flush()

    for size_yield in yields:
        session.add(
            BatchSize(
                batch_id=batch.id,
                size_id=size_yield.size_id,
                count_made=size_yield.count,
                unit_cost_cents=unit_costs_by_size[size_yield.size_id],
            )
        )
        session.add(
            MovementRow(
                entry_id=entry.id,
                batch_id=batch.id,
                size_id=size_yield.size_id,
                from_location_id=builtins.production_id,
                to_location_id=builtins.locations.kitchen_id,
                quantity=size_yield.count,
            )
        )
    session.flush()
    return batch.id


def _sale_destination(session: Session, size_id: int, locations: Locations) -> int:
    """Sold for a priced size, Sampled for a zero-price size."""
    price_cents = session.execute(select(Size.price_cents).where(Size.id == size_id)).scalar_one()
    return locations.sold_id if price_cents > 0 else locations.sampled_id


def _resolve_manual_destination(
    session: Session, *, to_location_id: int, size_id: int, locations: Locations
) -> int:
    """Resolve the caller's requested destination to the one actually written.

    Naming Sold or Sampled resolves by the size's price regardless of
    which of the two the caller named. Waste is always valid. Any other
    destination must be an active Kitchen or stand row -- never a
    market, and never an inactive location.
    """
    if to_location_id in (locations.sold_id, locations.sampled_id):
        return _sale_destination(session, size_id, locations)
    if to_location_id == locations.waste_id:
        return to_location_id

    destination = session.get(Location, to_location_id)
    if destination is None or destination.kind not in _TRANSFERABLE_KINDS or not destination.active:
        raise InvalidDestinationLocationError(location_id=to_location_id)
    return to_location_id


@dataclass(frozen=True)
class ManualMove:
    """Inputs to `record_manual_move`, grouped to stay under the arg-count lint."""

    from_location_id: int
    to_location_id: int
    size_id: int
    quantity: int


def record_manual_move(session: Session, move: ManualMove, *, now: datetime) -> int:
    """Record a manual move or removal: FIFO from `from_location_id`.

    Source must differ from destination and be an inventory location.
    Destination must be an active, non-market inventory location, Waste,
    or Sold/Sampled -- naming either of the sale pair resolves by the
    size's price regardless of which one the caller names. Raises
    `domain.ledger.InsufficientStock` untouched when FIFO cannot cover
    `quantity`.
    """
    if move.quantity <= 0:
        raise InvalidQuantityError(field="quantity", value=move.quantity, minimum=1)
    if move.from_location_id == move.to_location_id:
        raise SameLocationError(location_id=move.from_location_id)

    builtins = load_builtin_locations(session)
    if move.from_location_id not in builtins.locations.inventory_location_ids:
        raise InvalidSourceLocationError(location_id=move.from_location_id)

    destination_id = _resolve_manual_destination(
        session,
        to_location_id=move.to_location_id,
        size_id=move.size_id,
        locations=builtins.locations,
    )

    stock, batches = load_stock(session)
    allocation = allocate_fifo(stock, move.from_location_id, move.size_id, move.quantity, batches)

    entry = Entry(kind="manual", created_at=now, voided=False)
    session.add(entry)
    session.flush()

    for batch_id, allocated_quantity in allocation:
        session.add(
            MovementRow(
                entry_id=entry.id,
                batch_id=batch_id,
                size_id=move.size_id,
                from_location_id=move.from_location_id,
                to_location_id=destination_id,
                quantity=allocated_quantity,
            )
        )
    session.flush()
    return entry.id


def _to_ledger_movement(row: MovementRow) -> LedgerMovement:
    return LedgerMovement(
        id=row.id,
        batch_id=row.batch_id,
        size_id=row.size_id,
        from_location_id=row.from_location_id,
        to_location_id=row.to_location_id,
        quantity=row.quantity,
    )


def undo(session: Session, *, entry_id: int, now: datetime) -> int:
    """Undo `entry_id`: append a reversal entry, or raise before writing anything.

    Rejects a reversal entry (`CannotUndoReversalError`) and an
    already-voided entry (`AlreadyVoidedEntryError`) before touching
    anything else. Otherwise plans one reversal per
    movement the original entry created (`domain.ledger.plan_reversal`,
    reverse creation order, sequential balance check) and raises
    `InsufficientStock` untouched if any reversal would drive an
    inventory-location source negative.
    """
    original_entry = session.get_one(Entry, entry_id)
    if original_entry.kind == "reversal":
        raise CannotUndoReversalError(entry_id=entry_id)
    if original_entry.voided:
        raise AlreadyVoidedEntryError(entry_id=entry_id)

    original_rows = (
        session.execute(select(MovementRow).where(MovementRow.entry_id == entry_id)).scalars().all()
    )
    original_movements = [_to_ledger_movement(row) for row in original_rows]

    builtins = load_builtin_locations(session)
    stock, _batches = load_stock(session)
    reversals = plan_reversal(original_movements, stock, builtins.locations.inventory_location_ids)

    reversal_entry = Entry(
        kind="reversal", created_at=now, reverses_entry_id=entry_id, voided=False
    )
    session.add(reversal_entry)
    session.flush()

    for planned in reversals:
        session.add(
            MovementRow(
                entry_id=reversal_entry.id,
                batch_id=planned.batch_id,
                size_id=planned.size_id,
                from_location_id=planned.from_location_id,
                to_location_id=planned.to_location_id,
                quantity=planned.quantity,
                reverses_movement_id=planned.reverses_movement_id,
            )
        )
    original_entry.voided = True
    session.flush()
    return reversal_entry.id
