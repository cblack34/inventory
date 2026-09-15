"""The write-session dependency rolls back before the Problem handler renders.

FastAPI runs a generator dependency's teardown after the route body
raises, so `write_transaction`'s `with` block sees the exception and
rolls back before the response is built. Pin it: a row added then a
`DomainError` raised must leave the table exactly as it was.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.db.engine import make_engine
from inventory.db.models import Location
from tests.api.probes import add_rollback_probe, login


def test_domain_error_after_a_write_leaves_the_table_unchanged(app: FastAPI, db_path: Path) -> None:
    add_rollback_probe(app)

    with TestClient(app) as client:
        login(client)
        response = client.post("/api/v1/_test/rollback-probe")

    assert response.status_code == 422

    engine = make_engine(str(db_path))
    with Session(engine) as session:
        rows = session.execute(select(Location).where(Location.name == "Probe")).scalars().all()
    engine.dispose()

    assert rows == []
