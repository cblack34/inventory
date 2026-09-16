"""Pydantic v2 schemas for ingredients, recipes (with sizes), and locations.

Every input model forbids unknown keys and validates strictly (no `"1"`
for an `int` field, no `1.5` either) so a malformed payload becomes a 422
Problem rather than a silently coerced value; see `docs/acceptance.md`,
"Money". Response models are plain `BaseModel`s built either from an ORM
row (`from_attributes=True`) or, for a recipe, via `RecipeRead.from_model`
so the per-size cost estimate can be computed alongside the plain fields.
Money fields end in `_cents`, weight fields in `_g`, matching
`inventory.db.models`.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from inventory.api.schemas.ids import Id
from inventory.api.schemas.numbers import Cents, Count, PositiveCount
from inventory.db.models import Recipe
from inventory.domain.costing import RecipeLine as CostLine
from inventory.domain.costing import SizeYield, recipe_cost_cents, split_unit_costs

# --- Ingredients -------------------------------------------------------------


class IngredientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    unit_label: str = Field(min_length=1)
    current_price_cents: Cents


class IngredientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(default=None, min_length=1)
    unit_label: str | None = Field(default=None, min_length=1)
    current_price_cents: Cents | None = None
    active: bool | None = None


class IngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    unit_label: str
    current_price_cents: int
    active: bool


# --- Recipes and sizes --------------------------------------------------------


class RecipeLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ingredient_id: Id
    quantity: Count


class RecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    quantity: int


class SizeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    portion_weight_g: PositiveCount
    price_cents: Cents
    typical_yield_count: Count


class SizePatchItem(BaseModel):
    """One `sizes` patch item: `id` present updates that size, absent creates one.

    `id` is typed `int | SkipJsonSchema[None]` rather than plain
    `int | None`: Pydantic renders a bare `int | None` as `anyOf:
    [{type: integer}, {type: null}]`, which tells an OpenAPI client
    that an explicit `null` is a valid value. It is not -- the
    `_reject_explicit_null_id` validator below rejects `{"id": null}`
    at the wire -- so the generated schema should read as a plain
    optional integer (present or absent, never `null`).
    `SkipJsonSchema[None]` drops the `null` branch from the *schema*
    only; Python still sees `None` when the key is omitted, and the
    validator below still runs on every payload, `null` included.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    id: Id | SkipJsonSchema[None] = None
    name: str | None = Field(default=None, min_length=1)
    portion_weight_g: PositiveCount | None = None
    price_cents: Cents | None = None
    typical_yield_count: Count | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null_id(cls, data: Any) -> Any:
        """Reject `{"id": null, ...}`: only an absent `id` key means create.

        Raising here (rather than loosening the field type) keeps the
        rejection inside `RequestValidationError`, so it surfaces as a
        422 with an `errors` list like any other shape violation.
        """
        if isinstance(data, dict) and cast(dict[str, Any], data).get("id", "present") is None:
            raise ValueError("id must not be null; omit the key entirely to create a new size")
        return cast(Any, data)


def _check_unique_ingredient_ids(lines: list[RecipeLineInput]) -> list[RecipeLineInput]:
    """Raise if `lines` names the same `ingredient_id` twice.

    `recipe_line` carries no `(recipe_id, ingredient_id)` uniqueness, and
    `recipe_cost_cents` sums every line, so an accepted duplicate silently
    doubles that ingredient's contribution to the recipe's (and, once
    baked, the batch's frozen) cost.
    """
    seen: set[int] = set()
    for line in lines:
        if line.ingredient_id in seen:
            raise ValueError(f"ingredient_id {line.ingredient_id} appears more than once in lines")
        seen.add(line.ingredient_id)
    return lines


class SizeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    portion_weight_g: int
    price_cents: int
    typical_yield_count: int
    estimated_unit_cost_cents: int


class RecipeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    shelf_life_days: Count
    lines: list[RecipeLineInput] = Field(default_factory=list[RecipeLineInput])
    sizes: list[SizeCreate] = Field(min_length=1)

    @field_validator("lines")
    @classmethod
    def _reject_duplicate_ingredient_ids(
        cls, lines: list[RecipeLineInput]
    ) -> list[RecipeLineInput]:
        return _check_unique_ingredient_ids(lines)


class RecipePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(default=None, min_length=1)
    shelf_life_days: Count | None = None
    lines: list[RecipeLineInput] | None = None
    sizes: list[SizePatchItem] | None = None

    @field_validator("lines")
    @classmethod
    def _reject_duplicate_ingredient_ids(
        cls, lines: list[RecipeLineInput] | None
    ) -> list[RecipeLineInput] | None:
        return lines if lines is None else _check_unique_ingredient_ids(lines)


def _estimated_unit_costs(recipe: Recipe) -> dict[int, int]:
    cost_lines = [
        CostLine(quantity=line.quantity, unit_price_cents=line.ingredient.current_price_cents)
        for line in recipe.lines
    ]
    yields = [
        SizeYield(
            size_id=size.id, portion_weight_g=size.portion_weight_g, count=size.typical_yield_count
        )
        for size in recipe.sizes
    ]
    return split_unit_costs(recipe_cost_cents(cost_lines), yields)


class RecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    shelf_life_days: int
    lines: list[RecipeLineRead]
    sizes: list[SizeRead]

    @classmethod
    def from_model(cls, recipe: Recipe) -> RecipeRead:
        """Build the read model, including each size's live cost estimate.

        `estimated_unit_cost_cents` is computed on read from the
        recipe's current ingredient prices and each size's typical
        yield, never stored -- `docs/data-model.md`, "Recipe cost
        estimate and batch cost split". A persisted recipe's total
        typical weight is never zero (rejected at write time), so
        `split_unit_costs` never raises here.
        """
        unit_costs = _estimated_unit_costs(recipe)
        return cls(
            id=recipe.id,
            name=recipe.name,
            shelf_life_days=recipe.shelf_life_days,
            lines=[RecipeLineRead.model_validate(line) for line in recipe.lines],
            sizes=[
                SizeRead(
                    id=size.id,
                    name=size.name,
                    portion_weight_g=size.portion_weight_g,
                    price_cents=size.price_cents,
                    typical_yield_count=size.typical_yield_count,
                    estimated_unit_cost_cents=unit_costs[size.id],
                )
                for size in recipe.sizes
            ],
        )


# --- Locations -----------------------------------------------------------------


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    kind: Literal["stand", "market"]


class LocationPatch(BaseModel):
    """No `kind` field: kind is immutable, so a payload naming it is an unknown key (422)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(default=None, min_length=1)
    active: bool | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    active: bool
