"""Pins `record_bake`: frozen cost, per-size split, and Production->Kitchen movements.

See `docs/acceptance.md`, "Bake", and `docs/data-model.md`, "Recipe cost
estimate and batch cost split".
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Batch, BatchSize, Entry, Ingredient
from inventory.db.models import Movement as MovementRow
from inventory.db.writes import (
    BakeRequest,
    ExpiresBeforeBakedError,
    InvalidQuantityError,
    UnknownSizeError,
    record_bake,
)
from inventory.domain.costing import ZeroWeightError
from tests.db.seed import BakeFixture, SingleSizeRecipe

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
_BAKED = _NOW.date()
_EXPIRES = _BAKED + timedelta(days=5)


def _row_counts(session: Session) -> tuple[int, int, int]:
    entry_count = session.execute(select(func.count()).select_from(Entry)).scalar_one()
    batch_count = session.execute(select(func.count()).select_from(Batch)).scalar_one()
    movement_count = session.execute(select(func.count()).select_from(MovementRow)).scalar_one()
    return entry_count, batch_count, movement_count


def test_record_bake_writes_entry_batch_and_movements_with_pinned_unit_costs(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    with Session(engine) as session:
        batch_id = record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_BAKED,
                expires=_EXPIRES,
                counts={
                    bake_fixture.large_id: 2,
                    bake_fixture.medium_id: 4,
                    bake_fixture.small_id: 2,
                },
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        batch = session.get_one(Batch, batch_id)
        assert batch.entry.kind == "bake"
        assert batch.total_cost_cents == 1000

        batch_sizes = {
            row.size_id: row
            for row in session.execute(
                select(BatchSize).where(BatchSize.batch_id == batch_id)
            ).scalars()
        }
        assert batch_sizes[bake_fixture.large_id].count_made == 2
        assert batch_sizes[bake_fixture.large_id].unit_cost_cents == 222
        assert batch_sizes[bake_fixture.medium_id].count_made == 4
        assert batch_sizes[bake_fixture.medium_id].unit_cost_cents == 111
        assert batch_sizes[bake_fixture.small_id].count_made == 2
        assert batch_sizes[bake_fixture.small_id].unit_cost_cents == 56

        builtins = load_builtin_locations(session)
        movements = (
            session.execute(select(MovementRow).where(MovementRow.batch_id == batch_id))
            .scalars()
            .all()
        )
        assert len(movements) == 3
        quantities_by_size = {movement.size_id: movement.quantity for movement in movements}
        assert quantities_by_size == {
            bake_fixture.large_id: 2,
            bake_fixture.medium_id: 4,
            bake_fixture.small_id: 2,
        }
        for movement in movements:
            assert movement.from_location_id == builtins.production_id
            assert movement.to_location_id == builtins.locations.kitchen_id
            assert movement.entry_id == batch.entry_id


def test_record_bake_skips_zero_count_sizes(engine: Engine, bake_fixture: BakeFixture) -> None:
    with Session(engine) as session:
        batch_id = record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_BAKED,
                expires=_EXPIRES,
                counts={bake_fixture.large_id: 2, bake_fixture.medium_id: 4},
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        batch_size_rows = (
            session.execute(select(BatchSize).where(BatchSize.batch_id == batch_id)).scalars().all()
        )
        assert {row.size_id for row in batch_size_rows} == {
            bake_fixture.large_id,
            bake_fixture.medium_id,
        }

        movements = (
            session.execute(select(MovementRow).where(MovementRow.batch_id == batch_id))
            .scalars()
            .all()
        )
        assert {movement.size_id for movement in movements} == {
            bake_fixture.large_id,
            bake_fixture.medium_id,
        }


def test_record_bake_batch_cost_is_frozen_against_a_later_price_change(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    with Session(engine) as session:
        batch_id = record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_BAKED,
                expires=_EXPIRES,
                counts={
                    bake_fixture.large_id: 2,
                    bake_fixture.medium_id: 4,
                    bake_fixture.small_id: 2,
                },
            ),
            now=_NOW,
        )
        session.commit()

    with Session(engine) as session:
        ingredient = session.get_one(Ingredient, bake_fixture.ingredient_id)
        ingredient.current_price_cents = 999_999
        session.commit()

    with Session(engine) as session:
        batch = session.get_one(Batch, batch_id)
        assert batch.total_cost_cents == 1000
        unit_costs_by_size = {
            row.size_id: row.unit_cost_cents
            for row in session.execute(
                select(BatchSize).where(BatchSize.batch_id == batch_id)
            ).scalars()
        }
        assert unit_costs_by_size[bake_fixture.large_id] == 222
        assert unit_costs_by_size[bake_fixture.medium_id] == 111
        assert unit_costs_by_size[bake_fixture.small_id] == 56


def test_record_bake_rejects_all_zero_counts_and_writes_nothing(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    with Session(engine) as session:
        before = _row_counts(session)

        with pytest.raises(ZeroWeightError):
            record_bake(
                session,
                BakeRequest(
                    recipe_id=bake_fixture.recipe_id,
                    baked=_BAKED,
                    expires=_EXPIRES,
                    counts={bake_fixture.large_id: 0, bake_fixture.medium_id: 0},
                ),
                now=_NOW,
            )
        session.rollback()

    with Session(engine) as session:
        assert _row_counts(session) == before


def test_record_bake_rejects_expires_before_baked_and_writes_nothing(
    engine: Engine, bake_fixture: BakeFixture
) -> None:
    with Session(engine) as session:
        before = _row_counts(session)

        with pytest.raises(ExpiresBeforeBakedError):
            record_bake(
                session,
                BakeRequest(
                    recipe_id=bake_fixture.recipe_id,
                    baked=_BAKED,
                    expires=_BAKED - timedelta(days=1),
                    counts={bake_fixture.large_id: 2},
                ),
                now=_NOW,
            )
        session.rollback()

    with Session(engine) as session:
        assert _row_counts(session) == before


def test_bake_with_a_negative_count_is_rejected(engine: Engine, bake_fixture: BakeFixture) -> None:
    with Session(engine) as session, pytest.raises(InvalidQuantityError):
        record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date(),
                counts={bake_fixture.large_id: 1, bake_fixture.small_id: -1},
            ),
            now=_NOW,
        )


def test_bake_naming_a_size_from_another_recipe_is_rejected(
    engine: Engine, bake_fixture: BakeFixture, single_size_recipe: SingleSizeRecipe
) -> None:
    with Session(engine) as session, pytest.raises(UnknownSizeError) as excinfo:
        record_bake(
            session,
            BakeRequest(
                recipe_id=bake_fixture.recipe_id,
                baked=_NOW.date(),
                expires=_NOW.date(),
                counts={bake_fixture.large_id: 1, single_size_recipe.size_id: 5},
            ),
            now=_NOW,
        )
    assert excinfo.value.size_ids == {single_size_recipe.size_id}
