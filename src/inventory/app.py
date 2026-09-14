"""FastAPI application factory.

`create_app` takes `Settings` explicitly (see `inventory.settings`) so
`inventory.openapi` can build the OpenAPI document with dummy values and
never touch the real environment, and so `inventory.__main__` can fail
fast on bad configuration before ever constructing the app.
"""

from zoneinfo import ZoneInfo

from fastapi import FastAPI
from pydantic import BaseModel

from inventory.api.auth import LoginThrottle, install_auth
from inventory.api.deps import business_today, now, read_session, today, write_session
from inventory.api.problems import install_problem_handlers, problem_response
from inventory.api.routes.batches import router as batches_router
from inventory.api.routes.entries import router as entries_router
from inventory.api.routes.ingredients import router as ingredients_router
from inventory.api.routes.locations import router as locations_router
from inventory.api.routes.movements import router as movements_router
from inventory.api.routes.recipes import router as recipes_router
from inventory.api.routes.reversals import router as reversals_router
from inventory.api.routes.stock import router as stock_router
from inventory.api.routes.visits import router as visits_router
from inventory.api.static import mount_static
from inventory.db.engine import make_engine, make_session_factory, write_engine
from inventory.settings import Settings

# `business_today`, `now`, `read_session`, `today`, and `write_session` live
# in `inventory.api.deps` (see that module's docstring for why); re-exported
# here so existing call sites that read them off `inventory.app` -- tests
# and, soon, ledger routes -- keep working unchanged.
__all__ = [
    "HealthResponse",
    "business_today",
    "create_app",
    "now",
    "read_session",
    "today",
    "write_session",
]


class HealthResponse(BaseModel):
    status: str


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

    app.include_router(ingredients_router, prefix="/api/v1")
    app.include_router(recipes_router, prefix="/api/v1")
    app.include_router(locations_router, prefix="/api/v1")
    app.include_router(batches_router, prefix="/api/v1")
    app.include_router(movements_router, prefix="/api/v1")
    app.include_router(reversals_router, prefix="/api/v1")
    app.include_router(visits_router, prefix="/api/v1")
    app.include_router(entries_router, prefix="/api/v1")
    app.include_router(stock_router, prefix="/api/v1")

    mount_static(app)

    return app
