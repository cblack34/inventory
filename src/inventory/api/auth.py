"""Session cookie auth: constant-time password check, per-IP throttle, session gate.

`docs/build-brief.md`: "Auth is a single shared password compared
server-side with a constant-time check, session held in a signed
cookie." Starlette's `SessionMiddleware` (`itsdangerous`) supplies the
signed cookie and its expiry claim (the timestamp signer rejects a
cookie once `max_age` has passed on every request); nothing here
hand-rolls signing.
"""

import math
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette.middleware.sessions import SessionMiddleware

from inventory.api.problems import ProblemHTTPException, problem_response
from inventory.settings import Settings

_SESSION_COOKIE = "session"
_MAX_AGE_SECONDS = 30 * 24 * 3600
_MAX_FAILURES = 5
_THROTTLE_WINDOW_SECONDS = 15 * 60
# ponytail: two users behind one shared password will never attract hundreds
# of distinct attacking IPs; if this ceiling ever fires for real, replace the
# plain dict with a bounded TTL cache (e.g. `cachetools.TTLCache`) instead of
# raising the number.
_SWEEP_CEILING = 256


class LoginThrottle:
    """Per-IP failed-login counter with a rolling 15-minute window.

    A plain dict guarded by a lock is fine for two users on one process;
    `create_app` builds one instance per app (stored on
    `app.state.login_throttle`) so tests get a fresh counter instead of
    sharing state across runs. `clock` is a `time.monotonic`-shaped
    callable so tests can advance time without sleeping.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._failures: OrderedDict[str, list[float]] = OrderedDict()
        self._clock = clock
        self._lock = threading.Lock()

    def _recent_failures_locked(self, ip: str, *, now: float) -> list[float]:
        """`ip`'s failures still inside the window; also evicts `ip` if none are left."""
        recent = [ts for ts in self._failures.get(ip, ()) if now - ts < _THROTTLE_WINDOW_SECONDS]
        if recent:
            self._failures[ip] = recent
        else:
            self._failures.pop(ip, None)
        return recent

    def _sweep_locked(self, now: float) -> None:
        """Evict every IP whose failures have all aged out, bounding total memory."""
        for ip in list(self._failures):
            self._recent_failures_locked(ip, now=now)

    def _evict_oldest_locked(self) -> None:
        """Drop the least-recently-touched IPs until the dict is back at the ceiling.

        The sweep above only removes IPs whose failures have aged out; an
        attacker flooding distinct IPs faster than the window elapses
        never ages out, so this is the actual memory bound. Dropping the
        oldest-touched IP just gives that IP a fresh window early -- the
        right failure mode under attack (see the ponytail note on
        `_SWEEP_CEILING` above for the upgrade path).
        """
        while len(self._failures) > _SWEEP_CEILING:
            self._failures.popitem(last=False)

    def retry_after_seconds(self, ip: str) -> int | None:
        """Seconds until `ip`'s window clears, or `None` if it is not currently throttled."""
        now = self._clock()
        with self._lock:
            recent = self._recent_failures_locked(ip, now=now)
        if len(recent) < _MAX_FAILURES:
            return None
        return max(1, math.ceil(_THROTTLE_WINDOW_SECONDS - (now - min(recent))))

    def record_failure(self, ip: str) -> None:
        now = self._clock()
        with self._lock:
            recent = self._recent_failures_locked(ip, now=now)
            recent.append(now)
            self._failures[ip] = recent
            self._failures.move_to_end(ip)
            if len(self._failures) > _SWEEP_CEILING:
                self._sweep_locked(now)
            if len(self._failures) > _SWEEP_CEILING:
                self._evict_oldest_locked()

    def clear(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)

    @property
    def tracked_ip_count(self) -> int:
        """How many IPs currently have at least one still-in-window failure.

        A test seam for the memory-bound sweep, not used by routing.
        """
        with self._lock:
            return len(self._failures)


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

    @router.post("/session", status_code=204, responses={429: problem_response()})
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
