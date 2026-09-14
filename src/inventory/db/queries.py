"""Read models for the home screen: stock by location, and history.

Neither function writes anything. `stock_by_location` folds `load_stock`
(see `inventory.db.stock`) into the grouping the home screen needs --
inventory location, then size, then batch, each batch carrying its
`inventory.domain.expiration.expiry_state`. `history` reads every entry
newest first; a non-voided visit's profit is computed with the same
`revenue - fee - cost_of(Sold) - cost_of(Waste) - cost_of(Sampled)` rule
as `inventory.db.visits.visit_profit`, but over a handful of queries
sized to the number of *kinds* of thing it reads, not the number of
visits, so `history` stays a bounded number of round trips regardless
of history length. See `docs/data-model.md`, "Profit" and "Expiration",
and `docs/acceptance.md`, "Home screen and expiration".
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import BatchSize, Entry, Location, Recipe, Size
from inventory.db.models import Movement as MovementRow
from inventory.db.models import Visit as VisitRow
from inventory.db.stock import load_stock
from inventory.domain.expiration import ExpiryState, expiry_state
from inventory.domain.ledger import BatchOrder, OnHand
from inventory.domain.visits import Locations, profit_from_costs


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


def _visit_rows_by_entry(session: Session) -> dict[int, VisitRow]:
    rows = session.execute(select(VisitRow)).scalars().all()
    return {row.entry_id: row for row in rows}


def _visit_costs_by_entry(session: Session) -> dict[int, dict[int, int]]:
    """`entry_id -> {to_location_id: total_cost_cents}` for every non-voided visit, in one query.

    Sums `unit_cost_cents * quantity` over each visit's movements, per
    destination location, the same figure `visit_profit`'s `_cost_to`
    computes one visit at a time. Only destinations a movement actually
    lands on appear; a visit with no waste, say, has no entry for
    Waste's location id.
    """
    non_voided_visit_ids = (
        select(Entry.id)
        .join(VisitRow, VisitRow.entry_id == Entry.id)
        .where(Entry.voided.is_(False))
    )
    rows = session.execute(
        select(
            MovementRow.entry_id,
            MovementRow.to_location_id,
            func.sum(BatchSize.unit_cost_cents * MovementRow.quantity),
        )
        .join(
            BatchSize,
            (BatchSize.batch_id == MovementRow.batch_id)
            & (BatchSize.size_id == MovementRow.size_id),
        )
        .where(MovementRow.entry_id.in_(non_voided_visit_ids))
        .group_by(MovementRow.entry_id, MovementRow.to_location_id)
    ).all()
    costs: dict[int, dict[int, int]] = {}
    for entry_id, to_location_id, cost_cents in rows:
        costs.setdefault(entry_id, {})[to_location_id] = cost_cents
    return costs


def _visit_profit_cents(
    visit_row: VisitRow, costs_by_location: Mapping[int, int], locations: Locations
) -> int:
    return profit_from_costs(
        revenue_cents=visit_row.revenue_cents,
        fee_cents=visit_row.fee_cents,
        sold_cost_cents=costs_by_location.get(locations.sold_id, 0),
        waste_cost_cents=costs_by_location.get(locations.waste_id, 0),
        sampled_cost_cents=costs_by_location.get(locations.sampled_id, 0),
    ).profit_cents


def _history_entry(
    entry: Entry,
    visit_row: VisitRow | None,
    costs_by_entry: Mapping[int, Mapping[int, int]],
    locations: Locations,
) -> HistoryEntry:
    profit_cents = None
    if visit_row is not None and not entry.voided:
        profit_cents = _visit_profit_cents(visit_row, costs_by_entry.get(entry.id, {}), locations)
    return HistoryEntry(
        entry_id=entry.id,
        kind=entry.kind,
        created_at=entry.created_at,
        voided=entry.voided,
        location_id=visit_row.location_id if visit_row is not None else None,
        revenue_cents=(
            visit_row.revenue_cents if visit_row is not None and not entry.voided else None
        ),
        profit_cents=profit_cents,
    )


def history(session: Session) -> list[HistoryEntry]:
    """Every entry, newest first; revenue and profit only for non-voided visits.

    A voided visit reports `None` for both `revenue_cents` and
    `profit_cents`: `docs/data-model.md`, "Profit" says a voided visit
    "shows no profit figure in history ... and is excluded from any
    profit or revenue totals", and withholding the figure is what keeps a
    consumer from summing it by accident. The stored `visit` row and the
    original movements remain in the database for audit.

    Runs a bounded number of queries regardless of how many entries or
    visits exist: one for every entry, one for every visit row, one
    aggregate for every non-voided visit's movement costs, and the two
    `load_builtin_locations` issues -- never one query per visit.
    """
    entries = (
        session.execute(select(Entry).order_by(Entry.created_at.desc(), Entry.id.desc()))
        .scalars()
        .all()
    )
    visits_by_entry = _visit_rows_by_entry(session)
    costs_by_entry = _visit_costs_by_entry(session)
    locations = load_builtin_locations(session).locations
    return [
        _history_entry(entry, visits_by_entry.get(entry.id), costs_by_entry, locations)
        for entry in entries
    ]
