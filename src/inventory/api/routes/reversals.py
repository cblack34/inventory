"""`POST` route for the reversals resource: undo, as its own endpoint.

`docs/build-brief.md`: undo is `POST /api/v1/reversals` naming the
entry it reverses -- not an entry update, so this resource has no
`GET`, `PUT`, `PATCH`, or `DELETE`. The route sits behind
`require_session`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import now, write_session
from inventory.api.schemas.ledger import ReversalCreate, ReversalRead
from inventory.db.writes import undo

router = APIRouter(prefix="/reversals", tags=["reversals"], dependencies=[Depends(require_session)])


@router.post("", status_code=201)
def create_reversal(
    payload: ReversalCreate,
    session: Session = Depends(write_session),
    moment: datetime = Depends(now),
) -> ReversalRead:
    reversal_entry_id = undo(session, entry_id=payload.entry_id, now=moment)
    return ReversalRead(entry_id=reversal_entry_id, reverses_entry_id=payload.entry_id)
