"""`POST` route for the movements resource: a manual transfer or removal.

No `GET` list, `PUT`, `PATCH`, or `DELETE`: the movement ledger is
append-only (non-negotiable 1); reading it back happens through
`GET /api/v1/stock` (derived on-hand) and `GET /api/v1/entries`
(history), never a movements collection of its own. The route sits
behind `require_session`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import now, write_session
from inventory.api.schemas.ledger import EntryRead, MovementCreate
from inventory.api.stock_context import with_catalog_names
from inventory.db.models import Entry
from inventory.db.writes import ManualMove, record_manual_move
from inventory.domain import DomainError

router = APIRouter(prefix="/movements", tags=["movements"], dependencies=[Depends(require_session)])


@router.post("", status_code=201)
def create_movement(
    payload: MovementCreate,
    session: Session = Depends(write_session),
    moment: datetime = Depends(now),
) -> EntryRead:
    move = ManualMove(
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
        size_id=payload.size_id,
        quantity=payload.quantity,
    )
    try:
        entry_id = record_manual_move(session, move, now=moment)
    except DomainError as exc:
        raise with_catalog_names(session, exc) from None
    entry = session.get_one(Entry, entry_id)
    return EntryRead(
        entry_id=entry.id,
        kind=entry.kind,
        created_at=entry.created_at,
        voided=entry.voided,
        location_id=None,
        revenue_cents=None,
        profit_cents=None,
    )
