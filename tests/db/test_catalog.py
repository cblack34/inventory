"""Pins `create_location`'s own `kind` guard, independent of the API schema.

`LocationCreate.kind` is a Pydantic `Literal["stand", "market"]`, but
`inventory.db.catalog.create_location` enforces the same rule itself so
any other caller -- a future script, a different route -- cannot create
a `production`, `kitchen`, `sold`, `waste`, or `sampled` location by
going around the schema.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from inventory.db.catalog import (
    DuplicateSizePatchError,
    InvalidLocationKindError,
    NameConflictError,
    RecipeLineInput,
    RecipePatchRequest,
    SizePatchInput,
    create_location,
    update_recipe,
)
from inventory.db.models import RecipeLine, Size
from inventory.domain.costing import ZeroWeightError
from tests.db.seed import SingleSizeRecipe


def test_create_location_rejects_a_kind_the_schema_would_never_allow_through(
    engine: Engine,
) -> None:
    with Session(engine) as session, pytest.raises(InvalidLocationKindError) as exc_info:
        create_location(session, name="Sneaky", kind="production")

    assert exc_info.value.kind == "production"


@pytest.mark.parametrize("kind", ["kitchen", "sold", "waste", "sampled", "bogus", ""])
def test_create_location_rejects_every_non_stand_non_market_kind(engine: Engine, kind: str) -> None:
    with Session(engine) as session, pytest.raises(InvalidLocationKindError):
        create_location(session, name="Sneaky", kind=kind)


def test_create_location_accepts_stand_and_market(engine: Engine) -> None:
    with Session(engine) as session:
        stand = create_location(session, name="Roadside", kind="stand")
        market = create_location(session, name="Farmers Market", kind="market")

    assert stand.kind == "stand"
    assert market.kind == "market"


def test_patch_zero_weight_is_rejected_before_any_size_row_is_written(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """The prospective-weight check runs before any size row is created, mutated, or flushed.

    Setting the recipe's only size to a zero yield must raise
    `ZeroWeightError` without ever touching the `size` row -- caught
    directly here (rather than letting the caller's transaction roll
    back) and then queried in the same session, so a flush that
    happened before the raise would still show up.
    """
    with Session(engine) as session:
        request = RecipePatchRequest(
            sizes=[SizePatchInput(id=single_size_recipe.size_id, typical_yield_count=0)]
        )

        with pytest.raises(ZeroWeightError):
            update_recipe(session, single_size_recipe.recipe_id, request)

        size = session.get_one(Size, single_size_recipe.size_id)
        assert size.typical_yield_count == 10


def test_integrity_error_other_than_a_unique_conflict_is_not_translated(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """Only a UNIQUE-constraint flush failure becomes `NameConflictError`.

    Calling `update_recipe` directly with a new size (`id=None`) whose
    `portion_weight_g` is `0` bypasses the Pydantic schema's `ge=1`
    (`SizePatchInput` is a plain dataclass) and hits the
    `ck_size_portion_weight` CHECK constraint instead of the
    `uq_size_recipe_name` UNIQUE constraint -- that must surface as the
    underlying `IntegrityError`, not a misleading name conflict.
    """
    with Session(engine) as session:
        request = RecipePatchRequest(
            sizes=[
                SizePatchInput(
                    name="Zero Weight",
                    portion_weight_g=0,
                    price_cents=100,
                    typical_yield_count=1,
                )
            ]
        )

        with pytest.raises(IntegrityError):
            update_recipe(session, single_size_recipe.recipe_id, request)


def test_duplicate_size_id_in_a_sizes_patch_is_rejected_before_any_write(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """The same size `id` named twice in one patch is rejected before anything is touched.

    Left unchecked, `_prospective_size_yields` would merge duplicate
    patch items into a dict keyed by `id`, silently keeping only the
    last one -- so this raises `DuplicateSizePatchError` first, and the
    size row must come back completely unchanged.
    """
    with Session(engine) as session:
        request = RecipePatchRequest(
            sizes=[
                SizePatchInput(id=single_size_recipe.size_id, name="First"),
                SizePatchInput(id=single_size_recipe.size_id, name="Second"),
            ]
        )

        with pytest.raises(DuplicateSizePatchError) as exc_info:
            update_recipe(session, single_size_recipe.recipe_id, request)

        assert exc_info.value.size_id == single_size_recipe.size_id
        size = session.get_one(Size, single_size_recipe.size_id)
        assert size.name == "Only"


def test_duplicate_new_size_name_in_a_patch_is_rejected_case_insensitively_before_any_write(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """Two new sizes (no `id`) sharing a name, differing only in case, reject the whole patch.

    The `uq_size_recipe_name` UNIQUE constraint would eventually catch
    this too, but only after the first new size is already added to
    the session -- this must raise `NameConflictError` before either
    new `Size` row exists.
    """
    with Session(engine) as session:
        request = RecipePatchRequest(
            sizes=[
                SizePatchInput(
                    name="Jumbo", portion_weight_g=10, price_cents=100, typical_yield_count=1
                ),
                SizePatchInput(
                    name="JUMBO", portion_weight_g=20, price_cents=200, typical_yield_count=2
                ),
            ]
        )

        with pytest.raises(NameConflictError) as exc_info:
            update_recipe(session, single_size_recipe.recipe_id, request)

        assert exc_info.value.value == "JUMBO"
        sizes = (
            session.execute(select(Size).where(Size.recipe_id == single_size_recipe.recipe_id))
            .scalars()
            .all()
        )
        assert [size.name for size in sizes] == ["Only"]


def test_patch_validates_before_mutating_anything_including_a_valid_lines_replacement(
    engine: Engine, single_size_recipe: SingleSizeRecipe
) -> None:
    """A valid `lines` replacement paired with a zero-weight `sizes` update writes neither.

    `update_recipe` must run every pure validation -- including the
    prospective zero-weight check on `sizes` -- before it applies any
    field, replaces any line, or patches any size. Caught directly here
    (rather than letting the caller's transaction roll back) so the
    session's pending state after the raise proves the mutation phase
    never started: no new or dirty objects, and the line rows read back
    identical to the pre-call snapshot.
    """
    with Session(engine) as session:
        pre_lines = session.execute(
            select(RecipeLine.ingredient_id, RecipeLine.quantity).where(
                RecipeLine.recipe_id == single_size_recipe.recipe_id
            )
        ).all()
        ingredient_id = pre_lines[0].ingredient_id

        request = RecipePatchRequest(
            lines=[RecipeLineInput(ingredient_id=ingredient_id, quantity=999)],
            sizes=[SizePatchInput(id=single_size_recipe.size_id, typical_yield_count=0)],
        )

        with pytest.raises(ZeroWeightError):
            update_recipe(session, single_size_recipe.recipe_id, request)

        assert len(session.new) == 0
        assert len(session.dirty) == 0

        post_lines = session.execute(
            select(RecipeLine.ingredient_id, RecipeLine.quantity).where(
                RecipeLine.recipe_id == single_size_recipe.recipe_id
            )
        ).all()
        assert post_lines == pre_lines
