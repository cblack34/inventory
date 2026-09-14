"""Serves the built frontend and gates the SPA shell behind the session cookie.

The login page and the built asset bundle stay public; every other
non-API path serves the SPA shell when the session is authenticated and
redirects to `/login` otherwise. `/docs`, `/redoc`, and `/openapi.json`
are FastAPI's disabled documentation routes and must stay 404, not fall
through to the SPA catch-all below.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

_DIST_DIR = Path(__file__).parents[2] / "web" / "dist"
_DISABLED_DOC_ROUTES = frozenset({"docs", "redoc", "openapi.json"})


def mount_static(app: FastAPI) -> None:
    """Mount `/assets` and add the login page and SPA catch-all, if the build exists.

    The frontend build may not exist yet (tests, or a checkout before
    `make check` has run); skip mounting with a warning rather than
    fail app construction.
    """
    dist_dir = _DIST_DIR
    if not dist_dir.is_dir():
        sys.stderr.write(f"warning: {dist_dir} does not exist; frontend will not be served\n")
        return

    index_path = dist_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/login")
    def login_page() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{path:path}")
    def spa(path: str, request: Request) -> Response:
        if path.startswith("api/") or path in _DISABLED_DOC_ROUTES:
            raise HTTPException(status_code=404)
        if request.session.get("authenticated"):
            return FileResponse(index_path)
        return RedirectResponse("/login", status_code=303)
