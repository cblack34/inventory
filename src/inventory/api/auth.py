"""Session cookie auth: constant-time password check, per-IP throttle, session gate.

`docs/build-brief.md`: "Auth is a single shared password compared
server-side with a constant-time check, session held in a signed
cookie." Starlette's `SessionMiddleware` (`itsdangerous`) supplies the
signed cookie and its expiry claim (the timestamp signer rejects a
cookie once `max_age` has passed on every request); nothing here
hand-rolls signing.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette.middleware.sessions import SessionMiddleware

from inventory.api.problems import ProblemHTTPException
from inventory.settings import Settings

_SESSION_COOKIE = "session"
_MAX_AGE_SECONDS = 30 * 24 * 3600
_MAX_FAILURES = 5
_THROTTLE_WINDOW_SECONDS = 15 * 60


class LoginThrottle:
    """Per-IP failed-login counter with a rolling 15-minute window.

    A plain dict is fine for two users on one process; `create_app`
    builds one instance per app (stored on `app.state.login_throttle`)
    so tests get a fresh counter instead of sharing state across runs.
    """

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = defaultdict(list)

    def _recent_failures(self, ip: str, *, now: float) -> list[float]:
        recent = [ts for ts in self._failures[ip] if now - ts < _THROTTLE_WINDOW_SECONDS]
        self._failures[ip] = recent
        return recent

    def retry_after_seconds(self, ip: str) -> int | None:
        """Seconds until `ip`'s window clears, or `None` if it is not currently throttled."""
        now = time.monotonic()
        recent = self._recent_failures(ip, now=now)
        if len(recent) < _MAX_FAILURES:
            return None
        return max(1, round(_THROTTLE_WINDOW_SECONDS - (now - min(recent))))

    def record_failure(self, ip: str) -> None:
        now = time.monotonic()
        recent = self._recent_failures(ip, now=now)
        recent.append(now)

    def clear(self, ip: str) -> None:
        self._failures.pop(ip, None)


class LoginRequest(BaseModel):
    """`POST /api/v1/session` body: the shared password, nothing else."""

    model_config = ConfigDict(extra="forbid")

    password: str


def require_session(request: Request) -> None:
    """Raise a 401 Problem unless the session carries the authenticated flag.

    Applied to every `/api/v1/*` route except `POST /api/v1/session`
    and `GET /api/v1/health`.
    """
    if not request.session.get("authenticated"):
        raise ProblemHTTPException(
            401,
            type_="urn:inventory:problem:unauthorized",
            title="Unauthorized",
            detail="a valid session is required",
        )


def _client_ip(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


def _build_session_router(settings: Settings, throttle: LoginThrottle) -> APIRouter:
    router = APIRouter()

    @router.post("/session", status_code=204)
    def login(payload: LoginRequest, request: Request) -> Response:
        ip = _client_ip(request)
        retry_after = throttle.retry_after_seconds(ip)
        if retry_after is not None:
            raise ProblemHTTPException(
                429,
                type_="urn:inventory:problem:too-many-requests",
                title="Too Many Requests",
                detail="too many failed login attempts",
                retry_after_seconds=retry_after,
            )

        correct = secrets.compare_digest(
            payload.password.encode("utf-8"),
            settings.shared_password.get_secret_value().encode("utf-8"),
        )
        if not correct:
            throttle.record_failure(ip)
            raise ProblemHTTPException(
                401,
                type_="urn:inventory:problem:invalid-credentials",
                title="Invalid Credentials",
                detail="incorrect password",
            )

        throttle.clear(ip)
        request.session["authenticated"] = True
        return Response(status_code=204)

    return router


def install_auth(app: FastAPI, settings: Settings, throttle: LoginThrottle) -> None:
    """Add the session middleware and mount `POST /api/v1/session`."""
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie=_SESSION_COOKIE,
        max_age=_MAX_AGE_SECONDS,
        same_site="strict",
        https_only=not settings.insecure_cookies,
    )
    app.include_router(_build_session_router(settings, throttle), prefix="/api/v1")
