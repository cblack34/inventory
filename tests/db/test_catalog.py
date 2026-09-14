"""Pins `create_location`'s own `kind` guard, independent of the API schema.

`LocationCreate.kind` is a Pydantic `Literal["stand", "market"]`, but
`inventory.db.catalog.create_location` enforces the same rule itself so
any other caller -- a future script, a different route -- cannot create
a `production`, `kitchen`, `sold`, `waste`, or `sampled` location by
going around the schema.
"""

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.catalog import InvalidLocationKindError, create_location


def test_create_location_rejects_a_kind_the_schema_would_never_allow_through(
    engine: Engine,
) -> None:
    with Session(engine) as session, pytest.raises(InvalidLocationKindError) as exc_info:
        create_location(session, name="Sneaky", kind="production")

    assert exc_info.value.kind == "production"


@pytest.mark.parametrize("kind", ["kitchen", "sold", "waste", "sampled", "bogus", ""])
def test_create_location_rejects_every_non_stand_non_market_kind(engine: Engine, kind: str) -> None:
    with Session(engine) as session, pytest.raises(InvalidLocationKindError):
        create_location(session, name="Sneaky", kind=kind)


def test_create_location_accepts_stand_and_market(engine: Engine) -> None:
    with Session(engine) as session:
        stand = create_location(session, name="Roadside", kind="stand")
        market = create_location(session, name="Farmers Market", kind="market")

    assert stand.kind == "stand"
    assert market.kind == "market"
