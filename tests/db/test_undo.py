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
from inventory.db.catalog import update_location
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


def test_undo_of_a_manual_move_that_lands_in_a_now_inactive_stand_succeeds(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """A reversal may land in an inactive location if the balance check passes.

    Deactivation itself requires zero on-hand (`update_location`), so the
    only way to get an inactive destination for an *undo* is: move units
    into a stand, drain them back out so it can be deactivated, then undo
    the drain -- the reversal moves Kitchen -> stand again, into a stand
    that is now inactive. A brand-new move into an inactive stand is
    rejected (`test_manual_move_into_an_inactive_stand_is_rejected` in
    `tests/db/test_writes_manual_move.py`); undo is not a new move and
    must still succeed here.
    """
    with Session(engine) as session:
        _bake_ten_units(session, single_size_recipe)
        session.commit()

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        stand = Location(name="Only Stand", kind="stand", active=True)
        session.add(stand)
        session.flush()
        stand_id = stand.id

        record_manual_move(
            session,
            ManualMove(
                from_location_id=kitchen_id,
                to_location_id=stand_id,
                size_id=single_size_recipe.size_id,
                quantity=10,
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        kitchen_id = load_builtin_locations(session).locations.kitchen_id
        drain_entry_id = record_manual_move(
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
        update_location(session, stand_id, active=False)
        session.commit()

    with Session(engine) as session:
        reversal_entry_id = undo(session, entry_id=drain_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        drained_entry = session.get_one(Entry, drain_entry_id)
        assert drained_entry.voided is True

        stand = session.get_one(Location, stand_id)
        assert stand.active is False

        reversal_movement = session.execute(
            select(MovementRow).where(MovementRow.entry_id == reversal_entry_id)
        ).scalar_one()
        assert reversal_movement.from_location_id == kitchen_id
        assert reversal_movement.to_location_id == stand_id
        assert reversal_movement.quantity == 10

        stock_after, _batches = load_stock(session)

    stand_quantity_after = sum(
        quantity
        for (location_id, _size_id, _batch_id), quantity in stock_after.items()
        if location_id == stand_id
    )
    assert stand_quantity_after == 10


def _movement_snapshot(session: Session, entry_id: int) -> list[dict[str, int | None]]:
    """Every column of every movement row for `entry_id`, ordered and by value.

    A plain `dict` per row (not the ORM object itself) so the "before"
    values survive past their originating session and can be diffed
    against a fresh "after" read without triggering a re-fetch.
    """
    rows = (
        session.execute(
            select(MovementRow).where(MovementRow.entry_id == entry_id).order_by(MovementRow.id)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "entry_id": row.entry_id,
            "batch_id": row.batch_id,
            "size_id": row.size_id,
            "from_location_id": row.from_location_id,
            "to_location_id": row.to_location_id,
            "quantity": row.quantity,
            "reverses_movement_id": row.reverses_movement_id,
        }
        for row in rows
    ]


def test_undo_leaves_the_original_movement_rows_byte_for_byte_unchanged(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """Undo appends a reversal; it never rewrites the entry it reverses.

    Snapshots every column of the original toss's movement row (and its
    entry's `created_at`) before undo, then asserts every value is
    identical afterward -- not merely that stock round-trips -- and that
    the reversal's movement rows are new ids, not the same rows relabeled.
    """
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
        before = _movement_snapshot(session, toss_entry_id)
        original_created_at = session.get_one(Entry, toss_entry_id).created_at

    with Session(engine) as session:
        reversal_entry_id = undo(session, entry_id=toss_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        after = _movement_snapshot(session, toss_entry_id)
        assert after == before

        original_entry = session.get_one(Entry, toss_entry_id)
        assert original_entry.created_at == original_created_at
        assert original_entry.voided is True

        reversal_rows = _movement_snapshot(session, reversal_entry_id)
        assert reversal_rows != []
        original_ids = {row["id"] for row in before}
        reversal_ids = {row["id"] for row in reversal_rows}
        assert reversal_ids.isdisjoint(original_ids)
