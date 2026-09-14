"""Pins `load_stock` against an independent fold, and `unit_costs`.

`load_stock` must equal `domain.ledger.on_hand` run directly over the raw
movement rows -- the acceptance check under "Ledger, stock, and FIFO" --
and must include every movement regardless of whether its entry is
voided, since a voided entry's own reversal rows already net it to zero.
"""

from datetime import UTC, datetime

from conftest import BakeFixture
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Movement as MovementRow
from inventory.db.stock import load_stock, unit_costs
from inventory.db.writes import record_bake, record_manual_move, undo
from inventory.domain.ledger import Movement as LedgerMovement
from inventory.domain.ledger import on_hand

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_load_stock_matches_an_independent_fold_over_raw_movements(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    with Session(engine) as session:
        record_bake(
            session,
            recipe_id=bake_fixture.recipe_id,
            baked=_NOW.date(),
            expires=_NOW.date(),
            counts={bake_fixture.large_id: 2, bake_fixture.medium_id: 4, bake_fixture.small_id: 2},
            now=_NOW,
        )
        session.commit()

        record_manual_move(
            session,
            from_location_id=load_builtin_locations(session).locations.kitchen_id,
            to_location_id=load_builtin_locations(session).locations.waste_id,
            size_id=bake_fixture.large_id,
            quantity=1,
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        stock, _batches = load_stock(session)

        inventory_location_ids = load_builtin_locations(session).locations.inventory_location_ids
        raw_rows = session.execute(select(MovementRow)).scalars().all()
        raw_movements = [
            LedgerMovement(
                id=row.id,
                batch_id=row.batch_id,
                size_id=row.size_id,
                from_location_id=row.from_location_id,
                to_location_id=row.to_location_id,
                quantity=row.quantity,
            )
            for row in raw_rows
        ]
        expected = on_hand(raw_movements, inventory_location_ids)

    assert stock == expected
    assert stock  # non-empty: the bake left units at Kitchen


def test_load_stock_includes_movements_from_a_voided_entry(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    with Session(engine) as session:
        bake_batch_id = record_bake(
            session,
            recipe_id=bake_fixture.recipe_id,
            baked=_NOW.date(),
            expires=_NOW.date(),
            counts={bake_fixture.large_id: 5},
            now=_NOW,
        )
        session.commit()
        bake_entry_id = session.execute(
            select(MovementRow.entry_id).where(MovementRow.batch_id == bake_batch_id)
        ).scalar_one()

        undo(session, entry_id=bake_entry_id, now=_NOW)
        session.commit()

    with Session(engine) as session:
        stock, _batches = load_stock(session)

    assert stock == {}


def test_unit_costs_reads_frozen_batch_size_rows(engine: Engine, bake_fixture: BakeFixture) -> None:
    with Session(engine) as session:
        batch_id = record_bake(
            session,
            recipe_id=bake_fixture.recipe_id,
            baked=_NOW.date(),
            expires=_NOW.date(),
            counts={bake_fixture.large_id: 2, bake_fixture.medium_id: 4, bake_fixture.small_id: 2},
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        costs = unit_costs(session, [batch_id])

    assert costs == {
        (batch_id, bake_fixture.large_id): 222,
        (batch_id, bake_fixture.medium_id): 111,
        (batch_id, bake_fixture.small_id): 56,
    }


def test_unit_costs_of_empty_batch_ids_is_empty(engine: Engine) -> None:
    with Session(engine) as session:
        assert unit_costs(session, []) == {}
