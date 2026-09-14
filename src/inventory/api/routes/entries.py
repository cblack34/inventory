"""`GET` routes for the entries resource: the home screen's history list.

No `POST`, `PUT`, `PATCH`, or `DELETE`: an entry is created only as a
side effect of recording a batch, a visit, or a manual move, or of
undo (`POST /api/v1/reversals`); this resource is read-only. Both
routes sit behind `require_session`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import read_session
from inventory.api.schemas.ledger import EntryRead
from inventory.db.queries import history

router = APIRouter(prefix="/entries", tags=["entries"], dependencies=[Depends(require_session)])


@router.get("")
def list_entries(session: Session = Depends(read_session)) -> list[EntryRead]:
    return [EntryRead.model_validate(entry) for entry in history(session)]


@router.get("/{entry_id}")
def get_entry(entry_id: int, session: Session = Depends(read_session)) -> EntryRead:
    """Reuses `history`'s bounded-query read rather than a second query shape.

    `history` already runs a fixed number of statements regardless of
    how many entries exist; filtering the result in Python for one id
    keeps that guarantee instead of adding a second, entry-shaped read
    path next to it.
    """
    for entry in history(session):
        if entry.entry_id == entry_id:
            return EntryRead.model_validate(entry)
    raise NoResultFound(f"entry {entry_id} does not exist")
