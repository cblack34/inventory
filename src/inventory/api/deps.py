"""Request-scoped dependencies: sessions and the business clock.

Split out of `inventory.app` (rather than left as top-level functions
there) so a route module can depend on `read_session` / `write_session`
without importing `inventory.app` itself: every catalog and ledger route
module needs these, and `inventory.app.create_app` needs those route
modules' routers, so having the routers import straight from `app.py`
would be a circular import. `inventory.app` still re-exports all five
names (`from inventory.api.deps import ... as ...`) so existing call
sites that read them off `inventory.app` keep working unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.orm import Session

from inventory.db.transaction import write_transaction


def read_session(request: Request) -> Iterator[Session]:
    """Yield a plain session bound to the app's engine; opens no explicit transaction."""
    with Session(request.app.state.engine) as session:
        yield session


def write_session(request: Request) -> Iterator[Session]:
    """Open one serialized write transaction (`BEGIN IMMEDIATE`) and yield its session.

    FastAPI runs a generator dependency's teardown after the route
    handler returns or raises, so an exception the handler raises --
    including a `DomainError` -- propagates through this `with` block
    first: `write_transaction` rolls back before the exception reaches
    the Problem Details handler that renders the response.
    """
    with write_transaction(request.app.state.write_session_factory) as session:
        yield session


def business_today(instant: datetime, timezone: ZoneInfo) -> date:
    """The calendar date of an aware `instant` in the business's timezone.

    `docs/data-model.md` ("Expiration"): the owners enter visits in the
    evening, when a UTC container date would already be tomorrow.
    """
    return instant.astimezone(timezone).date()


def today(request: Request) -> date:
    """Today's calendar date in the business's configured timezone."""
    return business_today(datetime.now(UTC), request.app.state.timezone)


def now() -> datetime:
    """The current instant, always UTC."""
    return datetime.now(UTC)
