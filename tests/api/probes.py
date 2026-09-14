"""Test-only routes and a login helper, kept out of `conftest.py`'s fixtures.

Mirrors `tests/db/seed.py`: plain builders `tests/api/test_*.py` modules
import directly, since none of this needs pytest. Several acceptance
checks need a protected route or a write-path route that does not exist
in the production app yet (catalog and ledger are later leaves), so
each test registers one of these on its own `app` fixture instance
before wrapping it in a `TestClient`.
"""

from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.app import write_session
from inventory.db.models import Location
from inventory.db.writes import InvalidQuantityError
from inventory.domain import DomainError
from inventory.domain.ledger import InsufficientStock

TEST_PASSWORD = "correct horse"


class _ExtensionTypesError(DomainError):
    """Test-only error carrying a `date` and a `frozenset[str]` extension member.

    Pins that `_extension_members` (in `inventory.api.problems`) encodes
    every non-private attribute generically via `jsonable_encoder`,
    rather than only the scalar-or-int-collection shapes it used to
    special-case.
    """

    def __init__(self) -> None:
        super().__init__("carries a date and a frozenset")
        self.observed_on = date(2024, 1, 1)
        self.tags = frozenset({"b", "a"})


def login(client: TestClient, password: str = TEST_PASSWORD) -> None:
    """Log `client` in with `password` and raise if the attempt fails."""
    response = client.post("/api/v1/session", json={"password": password})
    response.raise_for_status()


def _move_to_front(app: FastAPI) -> None:
    """Re-insert the just-added last route at the front of `app.router.routes`.

    These probes are added after `create_app` already ran `mount_static`,
    which registers the SPA catch-all `GET /{path:path}` last; being a
    greedy wildcard, it would otherwise shadow anything appended after
    it, since Starlette matches routes in registration order.
    """
    routes = app.router.routes
    routes.insert(0, routes.pop())


def add_protected_probe(app: FastAPI, path: str = "/api/v1/_test/probe") -> None:
    """A protected route that only echoes success; pins the 401-when-unauthenticated case."""

    @app.get(path, dependencies=[Depends(require_session)])
    def probe() -> dict[str, bool]:
        return {"ok": True}

    _move_to_front(app)


def add_domain_error_probe(app: FastAPI, path: str = "/api/v1/_test/insufficient-stock") -> None:
    """A protected route that raises the pinned `InsufficientStock` fixture error.

    `location_id=1, size_id=2, on_hand=4, requested=6` are the exact
    values the issue's Problem Details test pins.
    """

    @app.get(path, dependencies=[Depends(require_session)])
    def probe() -> None:
        raise InsufficientStock(location_id=1, size_id=2, on_hand=4, requested=6)

    _move_to_front(app)


def add_extension_types_probe(app: FastAPI, path: str = "/api/v1/_test/extension-types") -> None:
    """A protected route raising a domain error with non-scalar extension members."""

    @app.get(path, dependencies=[Depends(require_session)])
    def probe() -> None:
        raise _ExtensionTypesError()

    _move_to_front(app)


def add_nonstandard_status_probe(
    app: FastAPI, path: str = "/api/v1/_test/nonstandard-status"
) -> None:
    """A protected route raising an `HTTPException` with a code `HTTPStatus` doesn't know.

    `detail` must be given explicitly: Starlette's own `HTTPException.__init__`
    derives a default detail from `HTTPStatus(status_code).phrase` when
    none is given, which would raise `ValueError` for `599` before the
    exception even reaches the Problem handler this probe is pinning.
    """

    @app.get(path, dependencies=[Depends(require_session)])
    def probe() -> None:
        raise HTTPException(status_code=599, detail="made up for the test")

    _move_to_front(app)


def add_not_found_probe(app: FastAPI, path: str = "/api/v1/_test/not-found") -> None:
    """A protected route that raises `NoResultFound`, to pin the 404 Problem mapping."""

    @app.get(path, dependencies=[Depends(require_session)])
    def probe() -> None:
        raise NoResultFound("nothing here")

    _move_to_front(app)


def add_rollback_probe(app: FastAPI, path: str = "/api/v1/_test/rollback-probe") -> None:
    """A protected route that writes a row, then raises, to pin write-session rollback order."""

    @app.post(path, dependencies=[Depends(require_session)])
    def probe(session: Session = Depends(write_session)) -> None:
        session.add(Location(name="Probe", kind="stand", active=True))
        session.flush()
        raise InvalidQuantityError(field="probe", value=-1, minimum=0)

    _move_to_front(app)


def add_empty_detail_probe(app: FastAPI, path: str = "/api/v1/_test/empty-detail") -> None:
    """A protected route raising an `HTTPException` whose detail is the empty string.

    Starlette fills a default phrase only for `None`, so `""` reaches the
    Problem handler as-is and must be preserved, not treated as absent.
    """

    @app.get(path, dependencies=[Depends(require_session)])
    def probe() -> None:
        raise HTTPException(status_code=400, detail="")

    _move_to_front(app)
