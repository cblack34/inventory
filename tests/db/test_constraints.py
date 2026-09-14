"""Pins the CHECK and UNIQUE constraints from the persistence issue's spec.

Movement quantity and case-insensitive location-name uniqueness are the
two constraints the issue names explicitly as tests to pin; the rest are
covered by `test_migration.py`'s `alembic check` drift comparison.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


def test_movement_with_zero_quantity_is_rejected(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entry (id, kind, created_at, voided) "
                "VALUES (1, 'manual', '2026-01-01 12:00:00', 0)"
            )
        )
        conn.execute(text("INSERT INTO recipe (id, name, shelf_life_days) VALUES (1, 'r', 5)"))
        conn.execute(
            text(
                "INSERT INTO batch (id, recipe_id, entry_id, baked, expires, total_cost_cents) "
                "VALUES (1, 1, 1, '2026-01-01', '2026-01-06', 1000)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO size (id, recipe_id, name, portion_weight_g, price_cents, "
                "typical_yield_count) VALUES (1, 1, 's', 50, 100, 2)"
            )
        )

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO movement "
                "(entry_id, batch_id, size_id, from_location_id, to_location_id, quantity) "
                "VALUES (1, 1, 1, 2, 1, 0)"
            )
        )


def test_location_name_differing_only_by_case_is_rejected(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text("INSERT INTO location (name, kind, active) VALUES ('kitchen', 'stand', 1)")
        )
