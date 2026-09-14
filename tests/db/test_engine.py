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

from inventory.db.engine import write_engine


def test_foreign_keys_are_enforced(engine: Engine) -> None:
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO recipe_line (recipe_id, ingredient_id, quantity) VALUES (999, 999, 1)"
            )
        )


def test_busy_timeout_is_set(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000


def test_write_engine_takes_the_write_lock_before_any_write(engine: Engine, db_path: Path) -> None:
    # A write transaction that has only begun, with no write statement yet,
    # must already hold the reserved lock so a second writer cannot begin.
    with write_engine(engine).begin():
        other = sqlite3.connect(str(db_path), timeout=0.1)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
        finally:
            other.close()


def test_read_transactions_do_not_take_the_write_lock(engine: Engine, db_path: Path) -> None:
    # A plain transaction reading the database must leave the reserved lock
    # free, so a writer can begin while a reader is open.
    with engine.begin() as conn:
        conn.execute(text("SELECT count(*) FROM location")).scalar_one()
        other = sqlite3.connect(str(db_path), timeout=0.1)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
        finally:
            other.close()
