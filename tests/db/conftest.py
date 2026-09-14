"""Shared fixtures for `tests/db`: a freshly migrated temp SQLite file.

Each fixture runs `alembic upgrade head` programmatically against a
`tmp_path` file rather than `Base.metadata.create_all`, per
`docs/engineering/code-quality.md` ("Every schema change ships an
Alembic migration ... No `create_all` outside tests") -- and this
package prefers the migration even in tests, so the migration itself is
what every test exercises.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import URL
from sqlalchemy.engine import Engine

from alembic import command
from inventory.db.engine import make_engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def alembic_config(db_path: Path) -> Config:
    """An Alembic `Config` pointed at `db_path`, the way the app's tests do.

    Mirrors how `alembic/env.py` builds the URL from the `DB` environment
    variable, but sets it directly on the `Config` instead, which is the
    approach the issue's tests are pinned to.
    """
    config = Config(str(_ALEMBIC_INI))
    url = URL.create("sqlite+pysqlite", database=str(db_path))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    return config


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "inventory.db"


@pytest.fixture
def migrated_config(db_path: Path) -> Config:
    """An Alembic `Config` for a temp file, migrated to `head`."""
    config = alembic_config(db_path)
    command.upgrade(config, "head")
    return config


@pytest.fixture
def engine(db_path: Path, migrated_config: Config) -> Iterator[Engine]:
    """A `make_engine` engine over a temp file already migrated to `head`."""
    del migrated_config  # ensures migration ran first; the engine just opens the file
    built_engine = make_engine(str(db_path))
    yield built_engine
    built_engine.dispose()
