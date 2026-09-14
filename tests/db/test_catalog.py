"""Pins `create_location`'s own `kind` guard, independent of the API schema.

`LocationCreate.kind` is a Pydantic `Literal["stand", "market"]`, but
`inventory.db.catalog.create_location` enforces the same rule itself so
any other caller -- a future script, a different route -- cannot create
a `production`, `kitchen`, `sold`, `waste`, or `sampled` location by
going around the schema.
"""

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from inventory.db.catalog import (
    InvalidLocationKindError,
    RecipePatchRequest,
    SizePatchInput,
    create_location,
    update_recipe,
)
from inventory.db.models import Size
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
