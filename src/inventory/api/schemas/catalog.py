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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inventory.db.models import Recipe
from inventory.domain.costing import RecipeLine as CostLine
from inventory.domain.costing import SizeYield, recipe_cost_cents, split_unit_costs

# --- Ingredients -------------------------------------------------------------


class IngredientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    unit_label: str
    current_price_cents: int = Field(ge=0)


class IngredientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = None
    unit_label: str | None = None
    current_price_cents: int | None = Field(default=None, ge=0)
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

    ingredient_id: int
    quantity: int = Field(ge=0)


class RecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_id: int
    quantity: int


class SizeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    portion_weight_g: int = Field(ge=1)
    price_cents: int = Field(ge=0)
    typical_yield_count: int = Field(ge=0)


class SizePatchItem(BaseModel):
    """One `sizes` patch item: `id` present updates that size, absent creates one."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: int | None = None
    name: str | None = None
    portion_weight_g: int | None = Field(default=None, ge=1)
    price_cents: int | None = Field(default=None, ge=0)
    typical_yield_count: int | None = Field(default=None, ge=0)


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

    name: str
    shelf_life_days: int = Field(ge=0)
    lines: list[RecipeLineInput] = Field(default_factory=list[RecipeLineInput])
    sizes: list[SizeCreate] = Field(min_length=1)


class RecipePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = None
    shelf_life_days: int | None = Field(default=None, ge=0)
    lines: list[RecipeLineInput] | None = None
    sizes: list[SizePatchItem] | None = None


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

    name: str
    kind: Literal["stand", "market"]


class LocationPatch(BaseModel):
    """No `kind` field: kind is immutable, so a payload naming it is an unknown key (422)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = None
    active: bool | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    active: bool
