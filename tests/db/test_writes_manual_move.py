"""Pins `record_manual_move`: FIFO removal/transfer and destination rules.

See `docs/data-model.md`, "Corrections", and `docs/acceptance.md`,
"Ledger, stock, and FIFO" / "Corrections".
"""

from datetime import UTC, datetime

import pytest
from conftest import BakeFixture, SingleSizeRecipe
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.engine import make_session_factory, write_engine
from inventory.db.models import Entry, Location
from inventory.db.models import Movement as MovementRow
from inventory.db.transaction import write_transaction
from inventory.db.writes import (
    InvalidDestinationLocationError,
    record_bake,
    record_manual_move,
)
from inventory.domain.ledger import InsufficientStock

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _row_counts(session: Session) -> tuple[int, int]:
    entry_count = session.execute(select(func.count()).select_from(Entry)).scalar_one()
    movement_count = session.execute(select(func.count()).select_from(MovementRow)).scalar_one()
    return entry_count, movement_count


def _make_stand(session: Session, *, name: str, active: bool = True) -> int:
    stand = Location(name=name, kind="stand", active=active)
    session.add(stand)
    session.flush()
    return stand.id


def _bake_ten_units(engine: Engine, single_size_recipe: SingleSizeRecipe) -> None:
    session_factory = make_session_factory(write_engine(engine))
    with write_transaction(session_factory) as session:
        record_bake(
            session,
            recipe_id=single_size_recipe.recipe_id,
            baked=_NOW.date(),
            expires=_NOW.date(),
            counts={single_size_recipe.size_id: 10},
            now=_NOW,
        )


def test_manual_removal_exceeding_on_hand_raises_and_writes_nothing(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    _bake_ten_units(engine, single_size_recipe)

    with Session(engine) as session:
        before = _row_counts(session)
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id

        with pytest.raises(InsufficientStock):
            record_manual_move(
                session,
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=single_size_recipe.size_id,
                quantity=11,
                now=_NOW,
            )
        session.rollback()

    with Session(engine) as session:
        assert _row_counts(session) == before


def test_manual_move_to_a_market_destination_is_rejected(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    _bake_ten_units(engine, single_size_recipe)

    with Session(engine) as session:
        market = Location(name="Farmers Market", kind="market", active=True)
        session.add(market)
        session.flush()
        session.commit()
        market_id = market.id

    with Session(engine) as session:
        before = _row_counts(session)
        kitchen_id = load_builtin_locations(session).locations.kitchen_id

        with pytest.raises(InvalidDestinationLocationError):
            record_manual_move(
                session,
                from_location_id=kitchen_id,
                to_location_id=market_id,
                size_id=single_size_recipe.size_id,
                quantity=1,
                now=_NOW,
            )
        session.rollback()

    with Session(engine) as session:
        assert _row_counts(session) == before


def test_manual_move_into_an_inactive_stand_is_rejected(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    _bake_ten_units(engine, single_size_recipe)

    with Session(engine) as session:
        stand_id = _make_stand(session, name="Old Stand", active=False)
        session.commit()

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id

        with pytest.raises(InvalidDestinationLocationError):
            record_manual_move(
                session,
                from_location_id=kitchen_id,
                to_location_id=stand_id,
                size_id=single_size_recipe.size_id,
                quantity=1,
                now=_NOW,
            )


def test_manual_move_out_of_an_inactive_stand_succeeds(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    _bake_ten_units(engine, single_size_recipe)

    with Session(engine) as session:
        stand_id = _make_stand(session, name="Roadside Stand", active=True)
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        record_manual_move(
            session,
            from_location_id=kitchen_id,
            to_location_id=stand_id,
            size_id=single_size_recipe.size_id,
            quantity=5,
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        stand = session.get_one(Location, stand_id)
        stand.active = False
        session.commit()

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        entry_id = record_manual_move(
            session,
            from_location_id=stand_id,
            to_location_id=kitchen_id,
            size_id=single_size_recipe.size_id,
            quantity=5,
            now=_NOW,
        )
        session.commit()

    assert entry_id is not None


def test_manual_move_naming_sold_for_a_zero_price_size_lands_in_sampled(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    session_factory = make_session_factory(write_engine(engine))
    with write_transaction(session_factory) as session:
        record_bake(
            session,
            recipe_id=bake_fixture.recipe_id,
            baked=_NOW.date(),
            expires=_NOW.date(),
            counts={bake_fixture.small_id: 3},  # small is priced at zero
            now=_NOW,
        )

    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        kitchen_id = locations.kitchen_id
        sold_id = locations.sold_id
        sampled_id = locations.sampled_id

        entry_id = record_manual_move(
            session,
            from_location_id=kitchen_id,
            to_location_id=sold_id,  # caller names Sold ...
            size_id=bake_fixture.small_id,
            quantity=1,
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        movement = session.execute(
            select(MovementRow).where(MovementRow.entry_id == entry_id)
        ).scalar_one()
        # ... but it resolves to Sampled because the size is priced at zero.
        assert movement.to_location_id == sampled_id
        assert movement.to_location_id != sold_id
