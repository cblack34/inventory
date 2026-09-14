"""Shared fixtures for `tests/db`: a freshly migrated temp SQLite file.

Each fixture runs `alembic upgrade head` programmatically against a
`tmp_path` file rather than `Base.metadata.create_all`, per
`docs/engineering/code-quality.md` ("Every schema change ships an
Alembic migration ... No `create_all` outside tests") -- and this
package prefers the migration even in tests, so the migration itself is
what every test exercises.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.engine import make_engine
from inventory.db.models import Ingredient, Recipe, RecipeLine, Size

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def alembic_config(db_path: Path) -> Config:
    """An Alembic `Config` pointed at `db_path`, the way the app's tests do.

    Mirrors how `alembic/env.py` builds the URL from the `DB` environment
    variable, but sets it directly on the `Config` instead, which is the
    approach the issue's tests are pinned to.
    """
    config = Config(str(_ALEMBIC_INI))
    url = URL.create("sqlite+pysqlite", database=str(db_path))
    config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    return config


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "inventory.db"


@pytest.fixture
def migrated_config(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """An Alembic `Config` for a temp file, migrated to `head`.

    `alembic/env.py` lets a `DB` environment variable override the URL, so
    it is cleared here; otherwise a developer's or CI's real database
    could be migrated instead of the temp file.
    """
    monkeypatch.delenv("DB", raising=False)
    config = alembic_config(db_path)
    command.upgrade(config, "head")
    return config


@pytest.fixture
def engine(db_path: Path, migrated_config: Config) -> Iterator[Engine]:
    """A `make_engine` engine over a temp file already migrated to `head`."""
    del migrated_config  # ensures migration ran first; the engine just opens the file
    built_engine = make_engine(str(db_path))
    yield built_engine
    built_engine.dispose()


@dataclass(frozen=True)
class BakeFixture:
    """One ingredient, one recipe, three sizes priced for the pinned bake check.

    A 1-unit recipe line against a 1000-cent ingredient makes `batch_cost`
    1000 cents; portion weights 200/100/50 g are the fixture
    `docs/acceptance.md` ("Bake") pins for a 2/4/2-count bake, which must
    split to unit costs 222/111/56 cents. `sizes[2]` (`small_id`) is
    priced at zero, for the Sold-vs-Sampled resolution tests.
    """

    recipe_id: int
    ingredient_id: int
    large_id: int
    medium_id: int
    small_id: int


@pytest.fixture
def bake_fixture(engine: Engine) -> BakeFixture:
    with Session(engine) as session:
        ingredient = Ingredient(name="Flour", unit_label="g", current_price_cents=1000, active=True)
        session.add(ingredient)
        session.flush()

        recipe = Recipe(name="Cookie", shelf_life_days=5)
        session.add(recipe)
        session.flush()

        session.add(RecipeLine(recipe_id=recipe.id, ingredient_id=ingredient.id, quantity=1))

        large = Size(
            recipe_id=recipe.id,
            name="Large",
            portion_weight_g=200,
            price_cents=300,
            typical_yield_count=2,
        )
        medium = Size(
            recipe_id=recipe.id,
            name="Medium",
            portion_weight_g=100,
            price_cents=150,
            typical_yield_count=4,
        )
        small = Size(
            recipe_id=recipe.id,
            name="Small",
            portion_weight_g=50,
            price_cents=0,
            typical_yield_count=2,
        )
        session.add_all([large, medium, small])
        session.flush()
        session.commit()

        return BakeFixture(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            large_id=large.id,
            medium_id=medium.id,
            small_id=small.id,
        )


@dataclass(frozen=True)
class SingleSizeRecipe:
    """One ingredient, one recipe, one size -- for tests that only need FIFO plumbing."""

    recipe_id: int
    size_id: int


@pytest.fixture
def single_size_recipe(engine: Engine) -> SingleSizeRecipe:
    with Session(engine) as session:
        ingredient = Ingredient(name="Sugar", unit_label="g", current_price_cents=10, active=True)
        session.add(ingredient)
        session.flush()

        recipe = Recipe(name="Simple", shelf_life_days=5)
        session.add(recipe)
        session.flush()

        session.add(RecipeLine(recipe_id=recipe.id, ingredient_id=ingredient.id, quantity=10))
        size = Size(
            recipe_id=recipe.id,
            name="Only",
            portion_weight_g=50,
            price_cents=100,
            typical_yield_count=10,
        )
        session.add(size)
        session.flush()
        session.commit()

        return SingleSizeRecipe(recipe_id=recipe.id, size_id=size.id)
