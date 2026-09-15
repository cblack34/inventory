"""Shared fixtures for `tests/api`: a migrated temp database and a test app.

Reuses `tests.db.conftest.alembic_config` -- the same "migrate a temp
SQLite file with Alembic, never `create_all`" approach `tests/db` uses
(see `docs/engineering/code-quality.md`) -- rather than restructuring
that module. Test-only probe routes and the `login` helper live in
`tests/api/probes.py`, mirroring `tests/db/seed.py`.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from inventory.app import create_app
from inventory.settings import Settings
from tests.api.probes import TEST_PASSWORD
from tests.db.conftest import alembic_config

TEST_SECRET = "0123456789abcdef0123456789abcdef"  # 32 bytes, test fixture only


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temp SQLite file migrated to `head`.

    `alembic/env.py` lets a `DB` environment variable override the URL,
    so it is cleared first; otherwise a developer's or CI's real
    database could be migrated instead of the temp file.
    """
    monkeypatch.delenv("DB", raising=False)
    path = tmp_path / "inventory.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(
        DB=str(db_path),
        SHARED_PASSWORD=SecretStr(TEST_PASSWORD),
        SESSION_SECRET=SecretStr(TEST_SECRET),
        TIMEZONE="UTC",
        INSECURE_COOKIES=True,
    )


@pytest.fixture
def dist_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A dummy Vite build so `mount_static` mounts `/assets` and serves `/login`."""
    dist = tmp_path / "web-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>inventory</body></html>")
    (assets / "x.js").write_text("export {};")
    (dist / "favicon.svg").write_text("<svg></svg>")
    monkeypatch.setattr("inventory.api.static._DIST_DIR", dist)
    return dist


@pytest.fixture
def app(settings: Settings, dist_dir: Path) -> FastAPI:
    del dist_dir  # depended on only so the monkeypatch runs before create_app mounts static
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
