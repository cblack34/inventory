"""Read models for the home screen: stock by location, and history.

Neither function writes anything. `stock_by_location` folds `load_stock`
(see `inventory.db.stock`) into the grouping the home screen needs --
inventory location, then size, then batch, each batch carrying its
`inventory.domain.expiration.expiry_state`. `history` reads every entry
newest first, with a non-voided visit's profit computed through
`inventory.db.visits.visit_profit`. See `docs/data-model.md`, "Profit"
and "Expiration", and `docs/acceptance.md`, "Home screen and expiration".
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Entry, Location, Recipe, Size
from inventory.db.stock import load_stock
from inventory.db.visits import visit_profit
from inventory.domain.expiration import ExpiryState, expiry_state
from inventory.domain.ledger import BatchOrder, OnHand


@dataclass(frozen=True)
class BatchStock:
    """One batch's contribution to a size's on-hand at a location."""

    batch_id: int
    expires: date
    quantity: int
    state: ExpiryState


@dataclass(frozen=True)
class SizeStock:
    """One (recipe, size)'s on-hand at a location, broken out by batch."""

    size_id: int
    size_name: str
    recipe_id: int
    recipe_name: str
    quantity: int
    batches: list[BatchStock]


@dataclass(frozen=True)
class LocationStock:
    """One inventory location's stock, grouped by size."""

    location_id: int
    name: str
    kind: str
    sizes: list[SizeStock]


@dataclass(frozen=True)
class HistoryEntry:
    """One past entry, as the home screen's history list shows it."""

    entry_id: int
    kind: str
    created_at: datetime
    voided: bool
    location_id: int | None
    revenue_cents: int | None
    profit_cents: int | None


@dataclass(frozen=True)
class _SizeInfo:
    """Size and recipe names, looked up once per `stock_by_location` call."""

    name: str
    recipe_id: int
    recipe_name: str


def _size_info(session: Session) -> dict[int, _SizeInfo]:
    rows = session.execute(
        select(Size.id, Size.name, Size.recipe_id, Recipe.name.label("recipe_name")).join(
            Recipe, Size.recipe_id == Recipe.id
        )
    ).all()
    return {
        row.id: _SizeInfo(name=row.name, recipe_id=row.recipe_id, recipe_name=row.recipe_name)
        for row in rows
    }


def _group_stock(stock: OnHand) -> dict[int, dict[int, dict[int, int]]]:
    """`stock` keyed by location, then size, then batch."""
    grouped: dict[int, dict[int, dict[int, int]]] = {}
    for (location_id, size_id, batch_id), quantity in stock.items():
        grouped.setdefault(location_id, {}).setdefault(size_id, {})[batch_id] = quantity
    return grouped


def _batch_stocks(
    batch_quantities: Mapping[int, int], batch_orders: Mapping[int, BatchOrder], today: date
) -> list[BatchStock]:
    return [
        BatchStock(
            batch_id=batch_id,
            expires=batch_orders[batch_id].expires,
            quantity=quantity,
            state=expiry_state(batch_orders[batch_id].expires, today),
        )
        for batch_id, quantity in sorted(batch_quantities.items())
    ]


def _size_stocks(
    sizes_for_location: Mapping[int, Mapping[int, int]],
    size_info: Mapping[int, _SizeInfo],
    batch_orders: Mapping[int, BatchOrder],
    today: date,
) -> list[SizeStock]:
    stocks: list[SizeStock] = []
    for size_id in sorted(sizes_for_location):
        batch_quantities = sizes_for_location[size_id]
        info = size_info[size_id]
        stocks.append(
            SizeStock(
                size_id=size_id,
                size_name=info.name,
                recipe_id=info.recipe_id,
                recipe_name=info.recipe_name,
                quantity=sum(batch_quantities.values()),
                batches=_batch_stocks(batch_quantities, batch_orders, today),
            )
        )
    return stocks


def stock_by_location(session: Session, today: date) -> list[LocationStock]:
    """Stock grouped by every inventory location, then size, then batch.

    Every Kitchen, stand, and market row appears, even with an empty
    `sizes` list; Production, Sold, Waste, and Sampled never do, since
    `load_stock` only folds movements into inventory locations. Each
    size's `quantity` is the sum of its batches, and each batch carries
    its own `expiry_state`, so a size holding one expired and one
    expiring-soon batch reports both states rather than merging them.
    """
    stock, batch_orders = load_stock(session)
    inventory_location_ids = load_builtin_locations(session).locations.inventory_location_ids

    locations = (
        session.execute(
            select(Location).where(Location.id.in_(inventory_location_ids)).order_by(Location.id)
        )
        .scalars()
        .all()
    )
    size_info = _size_info(session)
    grouped = _group_stock(stock)

    return [
        LocationStock(
            location_id=location.id,
            name=location.name,
            kind=location.kind,
            sizes=_size_stocks(grouped.get(location.id, {}), size_info, batch_orders, today),
        )
        for location in locations
    ]


def _history_entry(session: Session, entry: Entry) -> HistoryEntry:
    visit_row = entry.visit
    profit_cents = None
    if visit_row is not None and not entry.voided:
        profit_cents = visit_profit(session, entry.id).profit_cents
    return HistoryEntry(
        entry_id=entry.id,
        kind=entry.kind,
        created_at=entry.created_at,
        voided=entry.voided,
        location_id=visit_row.location_id if visit_row is not None else None,
        revenue_cents=visit_row.revenue_cents if visit_row is not None else None,
        profit_cents=profit_cents,
    )


def history(session: Session) -> list[HistoryEntry]:
    """Every entry, newest first, with revenue and profit for non-voided visits.

    `revenue_cents` reflects a voided visit's stored figure -- undo does
    not erase the cash that was actually collected -- but `profit_cents`
    is `None` for a voided visit: `docs/data-model.md`, "Profit" says a
    voided visit "shows no profit figure in history ... and is excluded
    from any profit or revenue totals."
    """
    entries = (
        session.execute(select(Entry).order_by(Entry.created_at.desc(), Entry.id.desc()))
        .scalars()
        .all()
    )
    return [_history_entry(session, entry) for entry in entries]
