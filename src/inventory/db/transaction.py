"""One serialized write transaction: begin, yield a session, commit or roll back.

See `docs/data-model.md`, "Visit settlement": every entry that moves
stock runs in a serialized write transaction (`BEGIN IMMEDIATE` on
SQLite, with a busy timeout) so the availability read and the append
happen under one write lock.
"""

from contextlib import AbstractContextManager

from sqlalchemy.orm import Session, sessionmaker


def write_transaction(session_factory: sessionmaker[Session]) -> AbstractContextManager[Session]:
    """Open one write transaction and yield its session.

    `session_factory` must be built from `inventory.db.engine.write_engine`
    (reads use the plain engine instead) so the underlying engine's
    `begin` event issues `BEGIN IMMEDIATE` rather than a plain `BEGIN`.
    `sessionmaker.begin()` is the SQLAlchemy 2.0 idiom this wraps: it
    commits the session on a clean exit, and rolls back and re-raises on
    any exception -- `DomainError` and `IntegrityError` alike.
    """
    return session_factory.begin()
