"""`POST` route for the reversals resource: undo, as its own endpoint.

`docs/build-brief.md`: undo is `POST /api/v1/reversals` naming the
entry it reverses -- not an entry update, so this resource has no
`GET`, `PUT`, `PATCH`, or `DELETE`. The route sits behind
`require_session`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends

from inventory.api.auth import require_session
from inventory.api.deps import WriteSession, now
from inventory.api.schemas.ledger import ReversalCreate, ReversalRead
from inventory.api.stock_context import with_catalog_names
from inventory.db.writes import undo
from inventory.domain import DomainError

router = APIRouter(prefix="/reversals", tags=["reversals"], dependencies=[Depends(require_session)])


@router.post("", status_code=201)
def create_reversal(
    payload: ReversalCreate,
    session: WriteSession,
    moment: datetime = Depends(now),
) -> ReversalRead:
    try:
        reversal_entry_id = undo(session, entry_id=payload.entry_id, now=moment)
    except DomainError as exc:
        raise with_catalog_names(session, exc) from None
    return ReversalRead(entry_id=reversal_entry_id, reverses_entry_id=payload.entry_id)
