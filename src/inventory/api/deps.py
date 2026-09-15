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

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
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

    Every write route depends on this through `WriteSession` below, not
    a bare `Depends(write_session)`: a generator dependency defaults to
    scope `"request"`, whose teardown FastAPI runs from the
    `AsyncExitStack` that closes *after* the response has already been
    sent (`fastapi.routing.request_response`), so a client could see a
    201 for a write this transaction had not yet committed. Scope
    `"function"` tears down from the stack that closes *before* the
    response is sent, so the commit is visible to any request the
    client makes after receiving the response -- the exception-path
    ordering above is unaffected either way, since both stacks unwind
    on a raised exception before `wrap_app_handling_exceptions` builds
    the error response.
    """
    with write_transaction(request.app.state.write_session_factory) as session:
        yield session


WriteSession = Annotated[Session, Depends(write_session, scope="function")]


def business_today(instant: datetime, timezone: ZoneInfo) -> date:
    """The calendar date of an aware `instant` in the business's timezone.

    `docs/data-model.md` ("Expiration"): the owners enter visits in the
    evening, when a UTC container date would already be tomorrow.
    """
    return instant.astimezone(timezone).date()


def now() -> datetime:
    """The current instant, always UTC."""
    return datetime.now(UTC)


def today(request: Request, instant: datetime = Depends(now)) -> date:
    """Today's calendar date in the business's configured timezone.

    Depends on `now` (rather than calling `datetime.now(UTC)` directly)
    so a test overriding `now` via `app.dependency_overrides` also drives
    `today`, and every route depending on either sees one consistent
    instant for the request.
    """
    return business_today(instant, request.app.state.timezone)
