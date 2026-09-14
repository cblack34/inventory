"""Pins the migration's built-in seed data, idempotence, and drift-free state.

See `docs/acceptance.md`, "Locations" and "Login and deployment".
"""

from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command
from inventory.db.models import Location


def _location_rows(engine: Engine) -> dict[str, tuple[str, bool]]:
    with Session(engine) as session:
        rows = session.execute(select(Location.name, Location.kind, Location.active)).all()
    return {row.name: (row.kind, row.active) for row in rows}


def test_migration_seeds_exactly_the_five_builtin_locations(engine: Engine) -> None:
    assert _location_rows(engine) == {
        "Kitchen": ("kitchen", True),
        "Production": ("production", True),
        "Sold": ("sold", True),
        "Waste": ("waste", True),
        "Sampled": ("sampled", True),
    }


def test_upgrade_head_twice_is_a_no_op(migrated_config: Config, engine: Engine) -> None:
    """The `migrated_config`/`engine` fixtures already ran `upgrade head` once."""
    before = _location_rows(engine)

    command.upgrade(migrated_config, "head")

    assert _location_rows(engine) == before


def test_alembic_check_reports_no_drift(migrated_config: Config) -> None:
    """`alembic check` raises if the models and the migrated schema disagree."""
    command.check(migrated_config)
