"""`GET`, `POST`, and `PATCH` routes for the recipes resource.

No `PUT`, no `DELETE`: a recipe and its sizes are permanent once created
(`docs/data-model.md`, "Concepts"). `PATCH` may update fields, replace
`lines` wholesale, and add or edit sizes, but never removes one. Every
route sits behind `require_session`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from inventory.api.auth import require_session
from inventory.api.deps import read_session, write_session
from inventory.api.schemas.catalog import (
    RecipeCreate,
    RecipeLineInput,
    RecipePatch,
    RecipeRead,
    SizeCreate,
    SizePatchItem,
)
from inventory.db.catalog import (
    RecipeCreateRequest,
    RecipePatchRequest,
    create_recipe,
    update_recipe,
)
from inventory.db.catalog import RecipeLineInput as DbLineInput
from inventory.db.catalog import SizeCreateInput as DbSizeCreate
from inventory.db.catalog import SizePatchInput as DbSizePatch
from inventory.db.models import Recipe
from inventory.db.models import RecipeLine as RecipeLineRow

router = APIRouter(prefix="/recipes", tags=["recipes"], dependencies=[Depends(require_session)])

# Loads every recipe's lines (and each line's ingredient, for the live
# cost estimate) and sizes in a bounded number of statements regardless
# of how many recipes come back -- `selectinload` issues one extra
# `SELECT ... WHERE recipe_id IN (...)` per relationship rather than one
# per row, avoiding the N+1 that a lazy `Recipe.lines` / `Recipe.sizes`
# access would otherwise trigger for every list or detail read.
_RECIPE_LOAD_OPTIONS = (
    selectinload(Recipe.lines).selectinload(RecipeLineRow.ingredient),
    selectinload(Recipe.sizes),
)


def _to_db_lines(lines: list[RecipeLineInput]) -> list[DbLineInput]:
    return [DbLineInput(ingredient_id=line.ingredient_id, quantity=line.quantity) for line in lines]


def _to_db_sizes(sizes: list[SizeCreate]) -> list[DbSizeCreate]:
    return [
        DbSizeCreate(
            name=size.name,
            portion_weight_g=size.portion_weight_g,
            price_cents=size.price_cents,
            typical_yield_count=size.typical_yield_count,
        )
        for size in sizes
    ]


def _to_db_size_patches(items: list[SizePatchItem]) -> list[DbSizePatch]:
    return [
        DbSizePatch(
            id=item.id,
            name=item.name,
            portion_weight_g=item.portion_weight_g,
            price_cents=item.price_cents,
            typical_yield_count=item.typical_yield_count,
        )
        for item in items
    ]


@router.get("")
def list_recipes(session: Session = Depends(read_session)) -> list[RecipeRead]:
    stmt = select(Recipe).order_by(Recipe.id).options(*_RECIPE_LOAD_OPTIONS)
    rows = session.execute(stmt).scalars().all()
    return [RecipeRead.from_model(row) for row in rows]


@router.get("/{recipe_id}")
def get_recipe(recipe_id: int, session: Session = Depends(read_session)) -> RecipeRead:
    stmt = select(Recipe).where(Recipe.id == recipe_id).options(*_RECIPE_LOAD_OPTIONS)
    row = session.execute(stmt).scalars().one()
    return RecipeRead.from_model(row)


@router.post("", status_code=201)
def create_recipe_route(
    payload: RecipeCreate, session: Session = Depends(write_session)
) -> RecipeRead:
    request = RecipeCreateRequest(
        name=payload.name,
        shelf_life_days=payload.shelf_life_days,
        lines=_to_db_lines(payload.lines),
        sizes=_to_db_sizes(payload.sizes),
    )
    row = create_recipe(session, request)
    return RecipeRead.from_model(row)


@router.patch("/{recipe_id}")
def update_recipe_route(
    recipe_id: int, payload: RecipePatch, session: Session = Depends(write_session)
) -> RecipeRead:
    request = RecipePatchRequest(
        name=payload.name,
        shelf_life_days=payload.shelf_life_days,
        lines=_to_db_lines(payload.lines) if payload.lines is not None else None,
        sizes=_to_db_size_patches(payload.sizes) if payload.sizes is not None else None,
    )
    row = update_recipe(session, recipe_id, request)
    return RecipeRead.from_model(row)
