"""Record stand and market visits atomically, and read a visit's profit.

Each `record_*_visit` function validates the target location, loads
on-hand and current size prices, builds a `domain.visits.Context`, and
calls the matching planner (`plan_stand_visit` or `plan_market_visit`)
before writing anything. Both planners raise a `DomainError` subclass
before returning if the payload is invalid, so a rejected visit never
touches `entry`, `visit`, or `movement` -- see `docs/data-model.md`,
"Visit settlement". `visit_profit` reads a saved visit's profit the same
way `docs/data-model.md`, "Profit" defines it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Entry, Location, Size
from inventory.db.models import Movement as MovementRow
from inventory.db.models import Visit as VisitRow
from inventory.db.stock import load_stock, unit_costs
from inventory.db.writes import InvalidQuantityError
from inventory.domain import DomainError
from inventory.domain.ledger import PlannedMovement
from inventory.domain.visits import (
    Context,
    MarketRow,
    Profit,
    StandRow,
    plan_market_visit,
    plan_stand_visit,
)
from inventory.domain.visits import visit_profit as _domain_visit_profit


class DuplicateSizeError(DomainError):
    """A visit payload names the same size in more than one row."""

    def __init__(self, *, size_id: int) -> None:
        self.size_id = size_id
        super().__init__(f"size {size_id} appears more than once in the visit rows")


class InvalidVisitLocationError(DomainError):
    """A visit named a location that is missing, the wrong kind, or inactive.

    Covers a location id that does not exist, one whose `kind` is not the
    expected `stand` or `market` (including every terminal kind and the
    stand/market-vs-market/stand mismatch), and an inactive stand or
    market.
    """

    def __init__(self, *, location_id: int, expected_kind: str) -> None:
        self.location_id = location_id
        self.expected_kind = expected_kind
        super().__init__(f"location {location_id} is not an active {expected_kind}")


class EntryIsNotAVisitError(DomainError):
    """`visit_profit` was asked about an entry with no `visit` row."""

    def __init__(self, *, entry_id: int) -> None:
        self.entry_id = entry_id
        super().__init__(f"entry {entry_id} is not a visit")


@dataclass(frozen=True)
class StandVisit:
    """Inputs to `record_stand_visit`, grouped to stay under the arg-count lint."""

    stand_id: int
    rows: Sequence[StandRow]
    revenue_cents: int


@dataclass(frozen=True)
class MarketVisit:
    """Inputs to `record_market_visit`, grouped to stay under the arg-count lint."""

    market_id: int
    rows: Sequence[MarketRow]
    revenue_cents: int
    fee_cents: int


@dataclass(frozen=True)
class _VisitWrite:
    """Grouped inputs to `_write_visit`, private to this module."""

    location_id: int
    revenue_cents: int
    fee_cents: int
    movements: Sequence[PlannedMovement]
    expected_revenue_cents: int


def _require_visit_location(session: Session, *, location_id: int, expected_kind: str) -> None:
    location = session.get(Location, location_id)
    if location is None or location.kind != expected_kind or not location.active:
        raise InvalidVisitLocationError(location_id=location_id, expected_kind=expected_kind)


def _require_valid_rows(
    rows: Sequence[StandRow] | Sequence[MarketRow], fields: tuple[str, ...]
) -> None:
    """Reject duplicate size ids and negative fields before any DB read.

    A duplicate would be silently merged or dropped by the planner, so it
    is rejected rather than interpreted. Runs first so a rejected visit
    never touches `entry`, `visit`, or `movement`.
    """
    seen: set[int] = set()
    for row in rows:
        if row.size_id in seen:
            raise DuplicateSizeError(size_id=row.size_id)
        seen.add(row.size_id)
    for row in rows:
        for name in fields:
            value: int = getattr(row, name)
            if value < 0:
                raise InvalidQuantityError(
                    field=f"rows[{row.size_id}].{name}", value=value, minimum=0
                )


def _size_prices_cents(session: Session) -> dict[int, int]:
    rows = session.execute(select(Size.id, Size.price_cents)).all()
    return {row.id: row.price_cents for row in rows}


def _build_context(session: Session) -> Context:
    stock, batches = load_stock(session)
    locations = load_builtin_locations(session).locations
    return Context(
        stock=stock,
        batches=batches,
        locations=locations,
        prices_cents=_size_prices_cents(session),
    )


def _write_visit(session: Session, write: _VisitWrite, *, now: datetime) -> int:
    entry = Entry(kind="visit", created_at=now, voided=False)
    session.add(entry)
    session.flush()

    session.add(
        VisitRow(
            entry_id=entry.id,
            location_id=write.location_id,
            revenue_cents=write.revenue_cents,
            fee_cents=write.fee_cents,
            expected_revenue_cents=write.expected_revenue_cents,
        )
    )
    for planned in write.movements:
        session.add(
            MovementRow(
                entry_id=entry.id,
                batch_id=planned.batch_id,
                size_id=planned.size_id,
                from_location_id=planned.from_location_id,
                to_location_id=planned.to_location_id,
                quantity=planned.quantity,
            )
        )
    session.flush()
    return entry.id


def record_stand_visit(session: Session, visit: StandVisit, *, now: datetime) -> int:
    """Record a stand visit: FIFO sale/waste/pull/add movements, `fee_cents = 0`.

    Rejects a negative `revenue_cents`, a negative `counted`, `tossed`,
    `pulled`, or `added` on any row, and a `stand_id` that is missing,
    not a `stand`, or inactive -- all before loading stock.
    `plan_stand_visit` raises before returning if any size's counted,
    tossed+pulled, or added is invalid, so nothing is written on
    rejection.
    """
    if visit.revenue_cents < 0:
        raise InvalidQuantityError(field="revenue_cents", value=visit.revenue_cents, minimum=0)
    _require_valid_rows(visit.rows, ("counted", "tossed", "pulled", "added"))
    _require_visit_location(session, location_id=visit.stand_id, expected_kind="stand")

    context = _build_context(session)
    plan = plan_stand_visit(visit.stand_id, visit.rows, context)

    return _write_visit(
        session,
        _VisitWrite(
            location_id=visit.stand_id,
            revenue_cents=visit.revenue_cents,
            fee_cents=0,
            movements=plan.movements,
            expected_revenue_cents=plan.expected_revenue_cents,
        ),
        now=now,
    )


def record_market_visit(session: Session, visit: MarketVisit, *, now: datetime) -> int:
    """Record a market visit: FIFO take/sale/waste/return movements.

    Rejects a negative `revenue_cents` or `fee_cents`, a negative
    `taken`, `returned`, or `tossed` on any row, and a `market_id` that
    is missing, not a `market`, or inactive -- all before loading
    stock. `plan_market_visit` raises before returning if any size's
    returned+tossed exceeds taken, so nothing is written on rejection.
    """
    if visit.revenue_cents < 0:
        raise InvalidQuantityError(field="revenue_cents", value=visit.revenue_cents, minimum=0)
    if visit.fee_cents < 0:
        raise InvalidQuantityError(field="fee_cents", value=visit.fee_cents, minimum=0)
    _require_valid_rows(visit.rows, ("taken", "returned", "tossed"))
    _require_visit_location(session, location_id=visit.market_id, expected_kind="market")

    context = _build_context(session)
    plan = plan_market_visit(visit.market_id, visit.rows, context)

    return _write_visit(
        session,
        _VisitWrite(
            location_id=visit.market_id,
            revenue_cents=visit.revenue_cents,
            fee_cents=visit.fee_cents,
            movements=plan.movements,
            expected_revenue_cents=plan.expected_revenue_cents,
        ),
        now=now,
    )


def visit_profit(session: Session, entry_id: int) -> Profit:
    """A visit's profit: revenue minus fee minus the frozen cost of Sold, Waste, Sampled.

    Raises `EntryIsNotAVisitError` if `entry_id` names an entry with no
    `visit` row.
    """
    visit_row = session.get(VisitRow, entry_id)
    if visit_row is None:
        raise EntryIsNotAVisitError(entry_id=entry_id)

    movement_rows = (
        session.execute(select(MovementRow).where(MovementRow.entry_id == entry_id)).scalars().all()
    )
    costs = unit_costs(session, {row.batch_id for row in movement_rows})
    movements = [
        PlannedMovement(
            batch_id=row.batch_id,
            size_id=row.size_id,
            from_location_id=row.from_location_id,
            to_location_id=row.to_location_id,
            quantity=row.quantity,
        )
        for row in movement_rows
    ]
    locations = load_builtin_locations(session).locations
    return _domain_visit_profit(
        revenue_cents=visit_row.revenue_cents,
        fee_cents=visit_row.fee_cents,
        movements=movements,
        unit_costs_cents=costs,
        locations=locations,
    )
