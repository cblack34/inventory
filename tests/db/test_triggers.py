"""Pins non-negotiable 2: batch cost is frozen at the database.

A raw `UPDATE` -- not the ORM -- is what proves the trigger, not a
validator, is what blocks the write; see `docs/acceptance.md`, "Bake".
"""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

# Plain ISO strings, not `date`/`datetime` objects: this is a raw-SQL test
# helper poking at the tables directly (the point is to prove the trigger
# fires outside the ORM), and Python 3.12 deprecated `sqlite3`'s default
# date/datetime adapters that binding real `date`/`datetime` objects here
# would otherwise exercise.
_CREATED_AT = "2026-01-01 12:00:00"
_BAKED = "2026-01-01"
_EXPIRES = "2026-01-06"


def _seed_one_batch_with_one_size(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entry (id, kind, created_at, voided) "
                "VALUES (1, 'bake', :created_at, 0)"
            ),
            {"created_at": _CREATED_AT},
        )
        conn.execute(text("INSERT INTO recipe (id, name, shelf_life_days) VALUES (1, 'r', 5)"))
        conn.execute(
            text(
                "INSERT INTO batch (id, recipe_id, entry_id, baked, expires, total_cost_cents) "
                "VALUES (1, 1, 1, :baked, :expires, 1000)"
            ),
            {"baked": _BAKED, "expires": _EXPIRES},
        )
        conn.execute(
            text(
                "INSERT INTO size (id, recipe_id, name, portion_weight_g, price_cents, "
                "typical_yield_count) VALUES (1, 1, 's', 50, 100, 2)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO batch_size (batch_id, size_id, count_made, unit_cost_cents) "
                "VALUES (1, 1, 4, 250)"
            )
        )


def test_raw_update_of_batch_total_cost_is_rejected(engine: Engine) -> None:
    _seed_one_batch_with_one_size(engine)

    with pytest.raises(IntegrityError, match="batch cost is frozen"), engine.begin() as conn:
        conn.execute(text("UPDATE batch SET total_cost_cents = 1 WHERE id = 1"))


def test_raw_update_of_batch_size_unit_cost_is_rejected(engine: Engine) -> None:
    _seed_one_batch_with_one_size(engine)

    with pytest.raises(IntegrityError, match="batch cost is frozen"), engine.begin() as conn:
        conn.execute(
            text("UPDATE batch_size SET unit_cost_cents = 1 WHERE batch_id = 1 AND size_id = 1")
        )


def test_raw_update_of_a_non_cost_batch_column_succeeds(engine: Engine) -> None:
    _seed_one_batch_with_one_size(engine)

    with engine.begin() as conn:
        conn.execute(text("UPDATE batch SET expires = '2026-01-07' WHERE id = 1"))
        (new_expires,) = conn.execute(text("SELECT expires FROM batch WHERE id = 1")).one()

    assert new_expires == "2026-01-07"
