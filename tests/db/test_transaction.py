"""Pins `write_transaction`: commit on success, roll back and re-raise on failure.

Also pins that it is built from `write_engine` -- its `BEGIN IMMEDIATE`
takes the write lock as soon as the transaction opens, before any write
statement -- by reusing the same probe `test_engine.py` uses for
`write_engine` itself.
"""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from inventory.db.engine import make_session_factory, write_engine
from inventory.db.models import Location
from inventory.db.transaction import write_transaction
from inventory.domain import DomainError


def test_write_transaction_commits_on_clean_exit(engine: Engine) -> None:
    session_factory = make_session_factory(write_engine(engine))

    with write_transaction(session_factory) as session:
        session.add(Location(name="Farmers Market", kind="market", active=True))

    with session_factory() as session:
        assert session.execute(select(Location).where(Location.name == "Farmers Market")).one()


def test_write_transaction_rolls_back_on_domain_error(engine: Engine) -> None:
    session_factory = make_session_factory(write_engine(engine))

    class _BoomError(DomainError):
        pass

    with pytest.raises(_BoomError), write_transaction(session_factory) as session:
        session.add(Location(name="Rolled Back Stand", kind="stand", active=True))
        raise _BoomError("nope")

    with session_factory() as session:
        assert (
            session.execute(select(Location).where(Location.name == "Rolled Back Stand")).first()
            is None
        )


def test_write_transaction_rolls_back_on_integrity_error(engine: Engine) -> None:
    session_factory = make_session_factory(write_engine(engine))

    with pytest.raises(IntegrityError), write_transaction(session_factory) as session:
        session.add(Location(name="kitchen", kind="stand", active=True))  # NOCASE collision


def test_write_transaction_takes_the_write_lock_before_any_write(
    engine: Engine, db_path: Path
) -> None:
    session_factory = make_session_factory(write_engine(engine))

    with write_transaction(session_factory) as session:
        session.execute(select(Location.id)).all()  # no write statement issued yet

        other = sqlite3.connect(str(db_path), timeout=0.1)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
        finally:
            other.close()
