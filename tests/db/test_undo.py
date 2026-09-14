"""Pins `undo`: reversal rows, voiding, sequential balance check, and uniqueness.

See `docs/data-model.md`, "Corrections", and `docs/acceptance.md`,
"Bake" and "Corrections".
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Entry, Location
from inventory.db.models import Movement as MovementRow
from inventory.db.stock import load_stock
from inventory.db.writes import (
    AlreadyVoidedEntryError,
    BakeRequest,
    CannotUndoReversalError,
    ManualMove,
    record_bake,
    record_manual_move,
    undo,
)
from inventory.domain.ledger import InsufficientStock
from tests.db.seed import SingleSizeRecipe

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _bake_ten_units(session: Session, single_size_recipe: SingleSizeRecipe) -> int:
    return record_bake(
        session,
        BakeRequest(
            recipe_id=single_size_recipe.recipe_id,
            baked=_NOW.date(),
            expires=_NOW.date(),
            counts={single_size_recipe.size_id: 10},
        ),
        now=_NOW,
    )


def test_undo_of_a_manual_toss_restores_stock_and_voids_with_reverses_movement_id(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session:
        _bake_ten_units(session, single_size_recipe)
        session.commit()

    with Session(engine) as session:
        stock_before, _batches = load_stock(session)
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id

        toss_entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=single_size_recipe.size_id,
                quantity=3,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        toss_movement_id = session.execute(
            select(MovementRow.id).where(MovementRow.entry_id == toss_entry_id)
        ).scalar_one()

        reversal_entry_id = undo(session, entry_id=toss_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        original_entry = session.get_one(Entry, toss_entry_id)
        assert original_entry.voided is True

        reversal_movement = session.execute(
            select(MovementRow).where(MovementRow.entry_id == reversal_entry_id)
        ).scalar_one()
        assert reversal_movement.reverses_movement_id == toss_movement_id

        stock_after, _batches = load_stock(session)

    assert stock_after == stock_before


def test_undo_of_an_already_voided_entry_is_rejected(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session:
        _bake_ten_units(session, single_size_recipe)
        session.commit()

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id
        toss_entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=single_size_recipe.size_id,
                quantity=3,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        undo(session, entry_id=toss_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session, pytest.raises(AlreadyVoidedEntryError):
        undo(session, entry_id=toss_entry_id, now=_NOW)


def test_undo_of_a_reversal_entry_is_rejected(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session:
        _bake_ten_units(session, single_size_recipe)
        session.commit()

    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        toss_entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=locations.kitchen_id,
                to_location_id=locations.waste_id,
                size_id=single_size_recipe.size_id,
                quantity=3,
            ),
            now=_NOW,
        )
        reversal_entry_id = undo(session, entry_id=toss_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session, pytest.raises(CannotUndoReversalError):
        undo(session, entry_id=reversal_entry_id, now=_NOW)


def test_two_identical_removals_produce_distinct_rows_and_undo_of_one_leaves_the_other(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session:
        _bake_ten_units(session, single_size_recipe)
        session.commit()

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        waste_id = load_builtin_locations(session).locations.waste_id

        first_entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=single_size_recipe.size_id,
                quantity=2,
            ),
            now=_NOW,
        )
        second_entry_id = record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=waste_id,
                size_id=single_size_recipe.size_id,
                quantity=2,
            ),
            now=_NOW,
        )
        session.commit()

    assert first_entry_id != second_entry_id

    with Session(engine) as session:
        first_movement_id = session.execute(
            select(MovementRow.id).where(MovementRow.entry_id == first_entry_id)
        ).scalar_one()
        second_movement_id = session.execute(
            select(MovementRow.id).where(MovementRow.entry_id == second_entry_id)
        ).scalar_one()
        assert first_movement_id != second_movement_id

        undo(session, entry_id=first_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        assert session.get_one(Entry, first_entry_id).voided is True
        assert session.get_one(Entry, second_entry_id).voided is False

        second_movement = session.get_one(MovementRow, second_movement_id)
        assert second_movement.reverses_movement_id is None

    # A raw attempt to insert a second reversal for the already-reversed
    # row must fail on the `reverses_movement_id` unique constraint.
    with Session(engine) as session:
        locations = load_builtin_locations(session).locations
        batch_id = session.get_one(MovementRow, first_movement_id).batch_id

        reversal_entry = Entry(kind="reversal", created_at=_NOW, voided=False)
        session.add(reversal_entry)
        session.flush()

        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                insert(MovementRow).values(
                    entry_id=reversal_entry.id,
                    batch_id=batch_id,
                    size_id=single_size_recipe.size_id,
                    from_location_id=locations.waste_id,
                    to_location_id=locations.kitchen_id,
                    quantity=1,
                    reverses_movement_id=first_movement_id,
                )
            )


def test_undo_of_a_bake_checks_kitchen_balance_sequentially(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session:
        stock_before_bake, _batches = load_stock(session)

    with Session(engine) as session:
        batch_id = _bake_ten_units(session, single_size_recipe)
        session.commit()

    with Session(engine) as session:
        bake_entry_id = session.execute(
            select(MovementRow.entry_id).where(MovementRow.batch_id == batch_id)
        ).scalar_one()

    with Session(engine) as session:
        stand = Location(name="Only Stand", kind="stand", active=True)
        session.add(stand)
        session.flush()
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=stand.id,
                size_id=single_size_recipe.size_id,
                quantity=10,
            ),
            now=_NOW,
        )
        session.commit()
        stand_id = stand.id

    with Session(engine) as session, pytest.raises(InsufficientStock):
        undo(session, entry_id=bake_entry_id, now=_NOW)

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        record_manual_move(
            session,
            ManualMove(
                from_location_id=stand_id,
                to_location_id=kitchen_id,
                size_id=single_size_recipe.size_id,
                quantity=10,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        undo(session, entry_id=bake_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        stock_after, _batches = load_stock(session)

    assert stock_after == stock_before_bake
