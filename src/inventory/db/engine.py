"""SQLite engine factory implementing SQLAlchemy's pysqlite recipe.

Verified against SQLAlchemy 2.0's dialect documentation, "Transactions
with SQLite and the sqlite3 driver" and "Serializable isolation /
Savepoints / Transactional DDL"
(https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl):
the `connect` event disables `sqlite3`'s own legacy BEGIN emission
(`isolation_level = None`) so SQLAlchemy's `begin` event is free to issue
its own; the `begin` event issues `BEGIN IMMEDIATE` rather than plain
`BEGIN` so the write lock is acquired at transaction start instead of
being deferred to the first write statement -- that immediacy, combined
with `PRAGMA busy_timeout`, is what serializes two concurrent writers
instead of racing them (see `docs/data-model.md`, "Visit settlement":
"Every entry that moves stock ... runs in a serialized write transaction
(`BEGIN IMMEDIATE` on SQLite, with a busy timeout)").
"""

from typing import Any

from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(db_path: str) -> Engine:
    """Build a `sqlite+pysqlite` engine that runs every write under `BEGIN IMMEDIATE`.

    `db_path` is a filesystem path to the SQLite file (or `:memory:`).
    """
    url = URL.create("sqlite+pysqlite", database=db_path)
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        # Disable sqlite3's own BEGIN emission entirely so the `begin`
        # event below is the only thing that starts a transaction.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a `sessionmaker` bound to `engine`."""
    return sessionmaker(engine)
