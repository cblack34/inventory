"""Serves the built frontend and gates the SPA shell behind the session cookie.

The login page and the built asset bundle stay public; every other
non-API path serves the SPA shell when the session is authenticated and
redirects to `/login` otherwise. `/docs`, `/redoc`, and `/openapi.json`
are FastAPI's disabled documentation routes and must stay 404, not fall
through to the SPA catch-all below. A `GET` on a registered `/api` path
that only accepts a different method (e.g. `GET /api/v1/movements`,
which is `POST`-only) answers 405 with `Allow`, rather than the 404 an
unknown API path gets -- see `_allowed_api_methods`.
"""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.routing import iter_route_contexts
from fastapi.staticfiles import StaticFiles

_DIST_DIR = Path(__file__).parents[2] / "web" / "dist"
_DISABLED_DOC_ROUTES = frozenset({"docs", "redoc", "openapi.json"})


def _allowed_api_methods(app: FastAPI, request_path: str) -> frozenset[str]:
    """Every HTTP method a registered route matches `request_path`, or an empty set.

    `spa()`'s own catch-all (`GET /{path:path}`) is registered last and
    matches any path -- including an existing `/api` resource requested
    with the wrong method -- so it wins Starlette's routing loop before
    the real route ever gets a chance to answer 405 itself. Re-deriving
    the accepted methods here lets `spa()` answer 405 with `Allow`
    instead of masking the mismatch as a 404.

    Uses `iter_route_contexts` -- the same flattening FastAPI's own
    OpenAPI generator uses -- rather than walking `app.routes` by hand:
    `include_router` wraps each included router in a lazy
    `_IncludedRouter` that only resolves nested routes (and applies
    their path prefix) on demand, so there is no other way to get a
    flat list of every route's final path and methods. Only considers
    a route whose own path starts with `/api`: this excludes `spa()`'s
    own greedy `/{path:path}` catch-all (which would otherwise "match"
    every path, including this one, and wrongly add `GET` to the
    result), `/login`, and the `/assets` mount.
    """
    allowed: set[str] = set()
    for context in iter_route_contexts(app.routes):
        methods = context.methods
        path_regex = getattr(context, "path_regex", None)
        if not methods or path_regex is None or context.path is None:
            continue
        if context.path.startswith("/api") and path_regex.fullmatch(request_path):
            allowed.update(methods)
    return frozenset(allowed)


def _root_dist_file(dist_dir: Path, normalized_path: str) -> Path | None:
    """`normalized_path` as an existing regular file directly under `dist_dir`, or `None`.

    Resolves both sides and checks containment before ever touching the
    filesystem result: `normalized_path` comes straight from the URL, so
    something like `../pyproject.toml` must not resolve to a path
    outside `dist_dir` (`/assets` is unaffected -- it is a separate
    `StaticFiles` mount matched before this catch-all route ever runs).

    Compares the resolved candidate against `index.html` by inode
    (`samefile`), not by string, once both are known to exist: a
    same-directory prefix (`./index.html`), a traversal that folds back
    in (`foo/../index.html`), and a case variant on a case-insensitive
    filesystem (`INDEX.HTML`) all name the same file on disk even
    though `Path.resolve()` collapses the first two but never corrects
    letter case for the third -- so a string comparison of resolved
    paths alone would still miss that last alias. Every one of them
    falls through to the session-gated branch below, never served here.
    """
    if not normalized_path:
        # The shell itself is gated by the session check below, never public.
        return None
    resolved_dist = dist_dir.resolve()
    candidate = (dist_dir / normalized_path).resolve()
    if candidate.parent != resolved_dist:
        # Only files directly under dist are public; nested files fall
        # through to the session-gated shell (assets have their own mount).
        return None
    if not candidate.is_file():
        return None
    resolved_index = (dist_dir / "index.html").resolve()
    if candidate.samefile(resolved_index):
        return None
    return candidate


def mount_static(app: FastAPI) -> None:
    """Mount `/assets` and add the login page and SPA catch-all, if the build exists.

    The frontend build may not exist yet (tests, or a checkout before
    `make check` has run); skip mounting with a warning rather than
    fail app construction.
    """
    dist_dir = _DIST_DIR
    index_path = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"
    if not (index_path.is_file() and assets_dir.is_dir()):
        sys.stderr.write(
            f"warning: {dist_dir} lacks index.html or assets/; frontend will not be served\n"
        )
        return

    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request) -> Response:
        normalized = path.strip("/")
        if normalized in _DISABLED_DOC_ROUTES:
            raise HTTPException(status_code=404)
        if normalized.startswith("api/"):
            allowed = _allowed_api_methods(request.app, request.url.path)
            if allowed:
                raise HTTPException(status_code=405, headers={"Allow": ", ".join(sorted(allowed))})
            raise HTTPException(status_code=404)
        root_file = _root_dist_file(dist_dir, normalized)
        if root_file is not None:
            return FileResponse(root_file)
        if request.session.get("authenticated"):
            return FileResponse(index_path)
        return RedirectResponse("/login", status_code=303)
