"""Pins `record_manual_move`: FIFO removal/transfer and destination rules.

See `docs/data-model.md`, "Corrections", and `docs/acceptance.md`,
"Ledger, stock, and FIFO" / "Corrections".
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.engine import make_session_factory, write_engine
from inventory.db.models import Entry, Location
from inventory.db.models import Movement as MovementRow
from inventory.db.transaction import write_transaction
from inventory.db.writes import (
    BakeRequest,
    InvalidDestinationLocationError,
    InvalidQuantityError,
    ManualMove,
    UnknownSizeError,
    record_bake,
    record_manual_move,
)
from inventory.domain.ledger import InsufficientStock
from tests.db.seed import BakeFixture, SingleSizeRecipe

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
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date(),
                counts={single_size_recipe.size_id: 10},
            ),
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
                ManualMove(
                    from_location_id=kitchen_id,
                    to_location_id=waste_id,
                    size_id=single_size_recipe.size_id,
                    quantity=11,
                ),
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
                ManualMove(
                    from_location_id=kitchen_id,
                    to_location_id=market_id,
                    size_id=single_size_recipe.size_id,
                    quantity=1,
                ),
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
                ManualMove(
                    from_location_id=kitchen_id,
                    to_location_id=stand_id,
                    size_id=single_size_recipe.size_id,
                    quantity=1,
                ),
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
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=stand_id,
                size_id=single_size_recipe.size_id,
                quantity=5,
            ),
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
            ManualMove(
                from_location_id=stand_id,
                to_location_id=kitchen_id,
                size_id=single_size_recipe.size_id,
                quantity=5,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        rows = session.execute(
            select(MovementRow).where(MovementRow.entry_id == entry_id)
        ).scalars()
        moved = [(row.from_location_id, row.to_location_id, row.quantity) for row in rows]
    assert moved == [(stand_id, kitchen_id, 5)]


@pytest.mark.parametrize("quantity", [0, -1])
def test_manual_move_with_non_positive_quantity_is_rejected_and_writes_nothing(
    engine: Engine, single_size_recipe: SingleSizeRecipe, quantity: int
) -> None:
    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        entries_before = session.execute(select(func.count()).select_from(Entry)).scalar_one()
        with pytest.raises(InvalidQuantityError):
            record_manual_move(
                session,
                ManualMove(
                    from_location_id=locations.kitchen_id,
                    to_location_id=locations.waste_id,
                    size_id=single_size_recipe.size_id,
                    quantity=quantity,
                ),
                now=_NOW,
            )
        session.rollback()
        assert (
            session.execute(select(func.count()).select_from(Entry)).scalar_one() == entries_before
        )


def test_manual_removal_drains_the_earlier_expiring_batch_first_across_two_bakes(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    baked_first = _NOW.date()
    with Session(engine) as session:
        # Baked first, expires later.
        later_batch_id = record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=baked_first,
                expires=baked_first.replace(day=20),
                counts={single_size_recipe.size_id: 5},
            ),
            now=_NOW,
        )
        # Baked second, expires sooner (a legal edited expiration).
        sooner_batch_id = record_bake(
            session,
            BakeRequest(
                recipe_id=single_size_recipe.recipe_id,
                baked=baked_first.replace(day=2),
                expires=baked_first.replace(day=10),
                counts={single_size_recipe.size_id: 4},
            ),
            now=_NOW,
        )
        locations = load_builtin_locations(session).locations
        entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=locations.kitchen_id,
                to_location_id=locations.waste_id,
                size_id=single_size_recipe.size_id,
                quantity=6,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        rows = (
            session.execute(
                select(MovementRow).where(MovementRow.entry_id == entry_id).order_by(MovementRow.id)
            )
            .scalars()
            .all()
        )
    assert [(row.batch_id, row.quantity) for row in rows] == [
        (sooner_batch_id, 4),
        (later_batch_id, 2),
    ]


def test_manual_move_naming_sold_for_a_zero_price_size_lands_in_sampled(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    session_factory = make_session_factory(write_engine(engine))
    with write_transaction(session_factory) as session:
        record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date(),
                counts={bake_fixture.small_id: 3},  # small is priced at zero
            ),
            now=_NOW,
        )

    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        kitchen_id = locations.kitchen_id
        sold_id = locations.sold_id
        sampled_id = locations.sampled_id

        entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=sold_id,  # caller names Sold ...
                size_id=bake_fixture.small_id,
                quantity=1,
            ),
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


def test_manual_move_naming_an_unknown_size_is_rejected_and_writes_nothing(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    _bake_ten_units(engine, single_size_recipe)
    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        before = _row_counts(session)
        with pytest.raises(UnknownSizeError) as excinfo:
            record_manual_move(
                session,
                ManualMove(
                    from_location_id=locations.kitchen_id,
                    to_location_id=locations.sold_id,
                    size_id=999_999,
                    quantity=1,
                ),
                now=_NOW,
            )
        session.rollback()
        assert excinfo.value.size_ids == {999_999}
        assert _row_counts(session) == before
