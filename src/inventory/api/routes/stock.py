"""`GET` route for the stock resource: derived on-hand, grouped and by batch.

No `POST`, `PUT`, `PATCH`, or `DELETE`: stock is never stored, only
derived from the movement ledger (non-negotiable 1), so there is
nothing to write here. The route sits behind `require_session`.
"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import read_session, today
from inventory.api.schemas.ledger import StockRead
from inventory.db.queries import stock_by_location

router = APIRouter(prefix="/stock", tags=["stock"], dependencies=[Depends(require_session)])


@router.get("")
def get_stock(
    session: Session = Depends(read_session), on_date: date = Depends(today)
) -> list[StockRead]:
    return [StockRead.model_validate(location) for location in stock_by_location(session, on_date)]
