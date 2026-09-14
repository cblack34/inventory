"""Pin the connection hooks in `inventory.db.engine.make_engine`.

Each test would fail if its hook were removed: foreign keys enforced,
busy timeout set, and `BEGIN IMMEDIATE` taking the write lock at
transaction start rather than at the first write.
"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


def test_foreign_keys_are_enforced(engine: Engine) -> None:
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO recipe_line (recipe_id, ingredient_id, quantity) "
                "VALUES (999, 999, 1)"
            )
        )


def test_busy_timeout_is_set(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000


def test_begin_takes_the_write_lock_before_any_write(engine: Engine, db_path: Path) -> None:
    # A transaction that has only begun, with no write statement yet, must
    # already hold the reserved lock so a second writer cannot begin. A
    # plain `BEGIN` would defer the lock and let both proceed.
    with engine.begin():
        other = sqlite3.connect(str(db_path), timeout=0.1)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
        finally:
            other.close()
