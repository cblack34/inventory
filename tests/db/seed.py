"""Pure seed-data builders for `tests/db` fixtures.

No pytest dependency here, so `tests/db/test_*.py` modules import these
directly (`from tests.db.seed import ...`) instead of reaching into
`conftest.py`, which is reserved for the pytest fixtures themselves.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from inventory.db.models import Ingredient, Recipe, RecipeLine, Size


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


def seed_bake_fixture(session: Session) -> BakeFixture:
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


def seed_single_size_recipe(session: Session) -> SingleSizeRecipe:
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
