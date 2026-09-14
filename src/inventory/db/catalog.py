"""The catalog write path: ingredients, recipes with lines and sizes, locations.

Every function here takes an open `Session` and writes rows; none of
them commits -- `inventory.db.transaction.write_transaction` owns the
transaction boundary (mirrors `inventory.db.writes`). See
`docs/data-model.md`, "Concepts": ingredients are deactivate-only, which
here means there is no delete, not that reactivation is unsupported --
`update_ingredient` lets `active` move either way, so a deactivated
ingredient can come back; recipes and sizes are permanent -- fields
update and sizes may be added, but no route or function here ever
removes one; a recipe or size update that
would leave the typical total weight (sum of portion_weight_g x
typical_yield_count over every size) at zero is rejected before
anything is written, the same rule
`inventory.domain.costing.split_unit_costs` enforces for the live cost
estimate.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from inventory.db.models import Ingredient, Location, Recipe, Size
from inventory.db.models import RecipeLine as RecipeLineRow
from inventory.db.stock import load_stock
from inventory.domain import DomainError
from inventory.domain.costing import SizeYield, split_unit_costs

_BUILTIN_LOCATION_KINDS = frozenset({"kitchen", "production", "sold", "waste", "sampled"})
_CREATABLE_LOCATION_KINDS = frozenset({"stand", "market"})


class UnknownIngredientError(DomainError):
    """A recipe line named an ingredient id that does not exist."""

    def __init__(self, *, ingredient_ids: frozenset[int]) -> None:
        self.ingredient_ids = ingredient_ids
        super().__init__(f"ingredients {sorted(ingredient_ids)} do not exist")


class SizeNotInRecipeError(DomainError):
    """A patch item's `id` names a size that belongs to a different recipe."""

    def __init__(self, *, size_id: int, recipe_id: int) -> None:
        self.size_id = size_id
        self.recipe_id = recipe_id
        super().__init__(f"size {size_id} does not belong to recipe {recipe_id}")


class IncompleteSizeError(DomainError):
    """A new-size patch item (no `id`) is missing a required field."""

    def __init__(self, *, missing_fields: tuple[str, ...]) -> None:
        self.missing_fields = missing_fields
        super().__init__(f"a new size is missing required fields: {', '.join(missing_fields)}")


class BuiltinLocationError(DomainError):
    """A rename or (de)activation was attempted on a built-in location."""

    def __init__(self, *, location_id: int, kind: str) -> None:
        self.location_id = location_id
        self.kind = kind
        super().__init__(f"location {location_id} ({kind}) is a built-in and cannot be changed")


class LocationHasStockError(DomainError):
    """Deactivating a location with units on hand was rejected."""

    def __init__(self, *, location_id: int, on_hand: int) -> None:
        self.location_id = location_id
        self.on_hand = on_hand
        super().__init__(
            f"location {location_id} holds {on_hand} units on hand and cannot be deactivated"
        )


class InvalidLocationKindError(DomainError):
    """A location create named a `kind` other than `stand` or `market`.

    Enforced here independent of the Pydantic `Literal["stand",
    "market"]` on `LocationCreate` -- this function is the write path's
    own guard, not a mirror of the API schema's validation.
    """

    def __init__(self, *, kind: str) -> None:
        self.kind = kind
        allowed = sorted(_CREATABLE_LOCATION_KINDS)
        super().__init__(f"location kind {kind!r} must be one of {allowed}")


class NameConflictError(DomainError):
    """A create or rename collided with an existing case-insensitive name."""

    def __init__(self, *, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field} {value!r} is already in use")


def _flush_catching_name_conflict(session: Session, *, field: str, value: str) -> None:
    """Translate a UNIQUE-constraint flush failure to `NameConflictError`, and only that failure.

    Any other `IntegrityError` (e.g. a CHECK constraint on a column
    Pydantic did not validate, reached by a caller that bypasses the
    API schema) is a different problem than a name collision and must
    not be misreported as one -- it re-raises unchanged.
    """
    try:
        session.flush()
    except IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc.orig):
            raise NameConflictError(field=field, value=value) from exc
        raise


# --- Ingredients -----------------------------------------------------------


def create_ingredient(
    session: Session, *, name: str, unit_label: str, current_price_cents: int
) -> Ingredient:
    ingredient = Ingredient(
        name=name, unit_label=unit_label, current_price_cents=current_price_cents, active=True
    )
    session.add(ingredient)
    session.flush()
    return ingredient


@dataclass(frozen=True)
class IngredientPatch:
    """Fields a `PATCH /ingredients/{id}` may change; `None` leaves a field alone."""

    name: str | None = None
    unit_label: str | None = None
    current_price_cents: int | None = None
    active: bool | None = None


def update_ingredient(session: Session, ingredient_id: int, patch: IngredientPatch) -> Ingredient:
    """Apply `patch` to an ingredient.

    `active` may move either way: deactivating hides the ingredient from
    the picker for new recipe lines, and reactivating brings it back.
    Deactivate-only in the data model means there is no delete.
    """
    ingredient = session.get_one(Ingredient, ingredient_id)
    if patch.name is not None:
        ingredient.name = patch.name
    if patch.unit_label is not None:
        ingredient.unit_label = patch.unit_label
    if patch.current_price_cents is not None:
        ingredient.current_price_cents = patch.current_price_cents
    if patch.active is not None:
        ingredient.active = patch.active
    session.flush()
    return ingredient


# --- Recipes -----------------------------------------------------------------


@dataclass(frozen=True)
class RecipeLineInput:
    """One ingredient line for `create_recipe` or a `lines` replacement."""

    ingredient_id: int
    quantity: int


@dataclass(frozen=True)
class SizeCreateInput:
    """A brand-new size, either on `create_recipe` or a sizes-patch item without an `id`."""

    name: str
    portion_weight_g: int
    price_cents: int
    typical_yield_count: int


@dataclass(frozen=True)
class SizePatchInput:
    """One item of a `sizes` patch list: `id` set updates, `id` absent creates."""

    id: int | None = None
    name: str | None = None
    portion_weight_g: int | None = None
    price_cents: int | None = None
    typical_yield_count: int | None = None


@dataclass(frozen=True)
class RecipeCreateRequest:
    """Inputs to `create_recipe`, grouped to stay under the arg-count lint."""

    name: str
    shelf_life_days: int
    lines: Sequence[RecipeLineInput]
    sizes: Sequence[SizeCreateInput]


@dataclass(frozen=True)
class RecipePatchRequest:
    """Inputs to `update_recipe`; a `None` field is left alone."""

    name: str | None = None
    shelf_life_days: int | None = None
    lines: Sequence[RecipeLineInput] | None = None
    sizes: Sequence[SizePatchInput] | None = None


def _reject_unknown_ingredients(session: Session, lines: Sequence[RecipeLineInput]) -> None:
    ingredient_ids = {line.ingredient_id for line in lines}
    if not ingredient_ids:
        return
    existing = (
        session.execute(select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids)))
        .scalars()
        .all()
    )
    unknown = ingredient_ids - set(existing)
    if unknown:
        raise UnknownIngredientError(ingredient_ids=frozenset(unknown))


def _reject_zero_typical_weight(yields: Sequence[SizeYield]) -> None:
    """Raise `inventory.domain.costing.ZeroWeightError` if `yields` sum to zero weight.

    Reuses `split_unit_costs`'s own zero-weight guard (batch cost `0` is
    thrown away) rather than re-implementing the same total-weight rule
    here.
    """
    split_unit_costs(0, yields)


def _replace_lines(session: Session, recipe_id: int, lines: Sequence[RecipeLineInput]) -> None:
    _reject_unknown_ingredients(session, lines)
    session.execute(delete(RecipeLineRow).where(RecipeLineRow.recipe_id == recipe_id))
    for line in lines:
        session.add(
            RecipeLineRow(
                recipe_id=recipe_id, ingredient_id=line.ingredient_id, quantity=line.quantity
            )
        )
    session.flush()


def _size_yields(sizes: Sequence[SizeCreateInput]) -> list[SizeYield]:
    return [
        SizeYield(size_id=0, portion_weight_g=size.portion_weight_g, count=size.typical_yield_count)
        for size in sizes
    ]


def create_recipe(session: Session, request: RecipeCreateRequest) -> Recipe:
    """Create a recipe with its lines and sizes; rejects zero typical total weight."""
    _reject_unknown_ingredients(session, request.lines)
    _reject_zero_typical_weight(_size_yields(request.sizes))

    recipe = Recipe(name=request.name, shelf_life_days=request.shelf_life_days)
    session.add(recipe)
    session.flush()

    for line in request.lines:
        session.add(
            RecipeLineRow(
                recipe_id=recipe.id, ingredient_id=line.ingredient_id, quantity=line.quantity
            )
        )
    session.flush()

    for size in request.sizes:
        session.add(
            Size(
                recipe_id=recipe.id,
                name=size.name,
                portion_weight_g=size.portion_weight_g,
                price_cents=size.price_cents,
                typical_yield_count=size.typical_yield_count,
            )
        )
        _flush_catching_name_conflict(session, field="name", value=size.name)

    return recipe


def _create_size(session: Session, recipe_id: int, item: SizePatchInput) -> None:
    name, portion_weight_g = item.name, item.portion_weight_g
    price_cents, typical_yield_count = item.price_cents, item.typical_yield_count
    if (
        name is None
        or portion_weight_g is None
        or price_cents is None
        or typical_yield_count is None
    ):
        missing = tuple(
            field
            for field, value in (
                ("name", name),
                ("portion_weight_g", portion_weight_g),
                ("price_cents", price_cents),
                ("typical_yield_count", typical_yield_count),
            )
            if value is None
        )
        raise IncompleteSizeError(missing_fields=missing)
    session.add(
        Size(
            recipe_id=recipe_id,
            name=name,
            portion_weight_g=portion_weight_g,
            price_cents=price_cents,
            typical_yield_count=typical_yield_count,
        )
    )
    _flush_catching_name_conflict(session, field="name", value=name)


def _update_size(session: Session, recipe_id: int, size_id: int, item: SizePatchInput) -> None:
    size = session.get_one(Size, size_id)
    if size.recipe_id != recipe_id:
        raise SizeNotInRecipeError(size_id=size_id, recipe_id=recipe_id)
    if item.name is not None:
        size.name = item.name
    if item.portion_weight_g is not None:
        size.portion_weight_g = item.portion_weight_g
    if item.price_cents is not None:
        size.price_cents = item.price_cents
    if item.typical_yield_count is not None:
        size.typical_yield_count = item.typical_yield_count
    _flush_catching_name_conflict(session, field="name", value=size.name)


def _apply_size_patches(session: Session, recipe_id: int, items: Sequence[SizePatchInput]) -> None:
    for item in items:
        if item.id is None:
            _create_size(session, recipe_id, item)
        else:
            _update_size(session, recipe_id, item.id, item)


def _prospective_size_yields(
    session: Session, recipe_id: int, items: Sequence[SizePatchInput]
) -> list[SizeYield]:
    """The recipe's size weights as they would be *after* `items` applied, computed with no write.

    Merges each existing size's stored weight/yield with any patch item
    naming its `id` (an unset field on the patch leaves the stored value
    alone), then appends one entry per new-size item (`id` absent),
    using `0` for a field the item leaves unset -- an incomplete new
    size fails its own `IncompleteSizeError` check later, in
    `_create_size`, before anything is written for it either way.
    """
    patches_by_id = {item.id: item for item in items if item.id is not None}
    rows = session.execute(
        select(Size.id, Size.portion_weight_g, Size.typical_yield_count).where(
            Size.recipe_id == recipe_id
        )
    ).all()
    yields: list[SizeYield] = []
    for row in rows:
        patch = patches_by_id.get(row.id)
        portion_weight_g = row.portion_weight_g
        typical_yield_count = row.typical_yield_count
        if patch is not None:
            if patch.portion_weight_g is not None:
                portion_weight_g = patch.portion_weight_g
            if patch.typical_yield_count is not None:
                typical_yield_count = patch.typical_yield_count
        yields.append(
            SizeYield(size_id=row.id, portion_weight_g=portion_weight_g, count=typical_yield_count)
        )
    yields.extend(
        SizeYield(
            size_id=0,
            portion_weight_g=item.portion_weight_g or 0,
            count=item.typical_yield_count or 0,
        )
        for item in items
        if item.id is None
    )
    return yields


def update_recipe(session: Session, recipe_id: int, request: RecipePatchRequest) -> Recipe:
    """Apply `request` to a recipe: patch fields, replace lines, add/patch sizes -- never remove."""
    recipe = session.get_one(Recipe, recipe_id)
    if request.name is not None:
        recipe.name = request.name
    if request.shelf_life_days is not None:
        recipe.shelf_life_days = request.shelf_life_days
    if request.lines is not None:
        _replace_lines(session, recipe_id, request.lines)
    if request.sizes is not None:
        _reject_zero_typical_weight(_prospective_size_yields(session, recipe_id, request.sizes))
        _apply_size_patches(session, recipe_id, request.sizes)
    session.flush()
    return recipe


# --- Locations ---------------------------------------------------------------


def create_location(session: Session, *, name: str, kind: str) -> Location:
    """Create an active stand or market; rejects any other `kind` regardless of the caller."""
    if kind not in _CREATABLE_LOCATION_KINDS:
        raise InvalidLocationKindError(kind=kind)
    location = Location(name=name, kind=kind, active=True)
    session.add(location)
    _flush_catching_name_conflict(session, field="name", value=name)
    return location


def _reject_builtin_change(location: Location) -> None:
    if location.kind in _BUILTIN_LOCATION_KINDS:
        raise BuiltinLocationError(location_id=location.id, kind=location.kind)


def _location_on_hand(session: Session, location_id: int) -> int:
    stock, _batches = load_stock(session)
    return sum(
        quantity
        for (candidate_location_id, _size_id, _batch_id), quantity in stock.items()
        if candidate_location_id == location_id
    )


def _reject_deactivate_with_stock(session: Session, location: Location) -> None:
    on_hand = _location_on_hand(session, location.id)
    if on_hand > 0:
        raise LocationHasStockError(location_id=location.id, on_hand=on_hand)


def update_location(
    session: Session, location_id: int, *, name: str | None = None, active: bool | None = None
) -> Location:
    """Rename or (de)activate a stand or market; rejects any change to a built-in.

    `kind` has no patch field at all (the Pydantic schema simply does not
    declare it, and `extra='forbid'` rejects a payload that tries), so
    there is nothing here to reject a kind change against -- the schema
    makes that state unrepresentable.
    """
    location = session.get_one(Location, location_id)
    if name is not None or active is not None:
        _reject_builtin_change(location)
    if active is False and location.active:
        _reject_deactivate_with_stock(session, location)
    if name is not None:
        location.name = name
    if active is not None:
        location.active = active
    conflict_value = name if name is not None else location.name
    _flush_catching_name_conflict(session, field="name", value=conflict_value)
    return location
