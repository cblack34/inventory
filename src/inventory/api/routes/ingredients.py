"""`GET`, `POST`, and `PATCH` routes for the ingredients resource.

No `PUT`, no `DELETE`: an ingredient is deactivate-only (`active=False`
via `PATCH`), never removed. Every route sits behind `require_session`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import read_session, write_session
from inventory.api.schemas.catalog import IngredientCreate, IngredientRead, IngredientUpdate
from inventory.api.schemas.ids import IdPath
from inventory.api.stock_context import catalog_errors
from inventory.db.catalog import IngredientPatch, create_ingredient, update_ingredient
from inventory.db.models import Ingredient

router = APIRouter(
    prefix="/ingredients", tags=["ingredients"], dependencies=[Depends(require_session)]
)


@router.get("")
def list_ingredients(session: Session = Depends(read_session)) -> list[IngredientRead]:
    rows = session.execute(select(Ingredient).order_by(Ingredient.id)).scalars().all()
    return [IngredientRead.model_validate(row) for row in rows]


@router.get("/{ingredient_id}")
def get_ingredient(
    ingredient_id: IdPath, session: Session = Depends(read_session)
) -> IngredientRead:
    row = session.get_one(Ingredient, ingredient_id)
    return IngredientRead.model_validate(row)


@router.post("", status_code=201)
def create_ingredient_route(
    payload: IngredientCreate, session: Session = Depends(write_session)
) -> IngredientRead:
    with catalog_errors(session):
        row = create_ingredient(
            session,
            name=payload.name,
            unit_label=payload.unit_label,
            current_price_cents=payload.current_price_cents,
        )
    return IngredientRead.model_validate(row)


@router.patch("/{ingredient_id}")
def update_ingredient_route(
    ingredient_id: IdPath, payload: IngredientUpdate, session: Session = Depends(write_session)
) -> IngredientRead:
    patch = IngredientPatch(**payload.model_dump(exclude_unset=True))
    with catalog_errors(session):
        row = update_ingredient(session, ingredient_id, patch)
    return IngredientRead.model_validate(row)
