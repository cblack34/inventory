"""FastAPI application factory.

`create_app` takes `Settings` explicitly (see `inventory.settings`) so
`inventory.openapi` can build the OpenAPI document with dummy values and
never touch the real environment, and so `inventory.__main__` can fail
fast on bad configuration before ever constructing the app.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from inventory.api.auth import LoginThrottle, install_auth
from inventory.api.problems import install_problem_handlers, problem_response
from inventory.api.static import mount_static
from inventory.db.engine import make_engine, make_session_factory, write_engine
from inventory.db.transaction import write_transaction
from inventory.settings import Settings


class HealthResponse(BaseModel):
    status: str


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


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI app for `settings`: engine, auth, error envelope, static mount."""
    app = FastAPI(
        title="inventory",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        responses={
            401: problem_response(),
            404: problem_response(),
            422: problem_response(),
        },
    )

    engine = make_engine(settings.db)
    app.state.settings = settings
    app.state.engine = engine
    app.state.write_session_factory = make_session_factory(write_engine(engine))
    app.state.timezone = ZoneInfo(settings.timezone)

    install_problem_handlers(app)

    throttle = LoginThrottle()
    app.state.login_throttle = throttle
    install_auth(app, settings, throttle)

    @app.get("/api/v1/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    mount_static(app)

    return app
