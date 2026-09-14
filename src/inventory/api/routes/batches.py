"""`POST` and `GET` routes for the batches resource.

No `PUT`, `PATCH`, or `DELETE`: a batch's cost fields are frozen at
bake time (non-negotiable 2) and enforced at the database by a
`BEFORE UPDATE` trigger, so no write path here even attempts to change
them once written. Every route sits behind `require_session`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from inventory.api.auth import require_session
from inventory.api.deps import now, read_session, write_session
from inventory.api.schemas.ledger import BatchCreate, BatchRead
from inventory.db.models import Batch
from inventory.db.writes import BakeRequest, record_bake

router = APIRouter(prefix="/batches", tags=["batches"], dependencies=[Depends(require_session)])

# One extra `SELECT ... WHERE batch_id IN (...)` for `batch_sizes`, bounded
# regardless of how many sizes the batch has, rather than a lazy per-size load.
_BATCH_LOAD_OPTIONS = (selectinload(Batch.batch_sizes),)


def _load_batch(session: Session, batch_id: int) -> Batch:
    stmt = select(Batch).where(Batch.id == batch_id).options(*_BATCH_LOAD_OPTIONS)
    return session.execute(stmt).scalars().one()


@router.post("", status_code=201)
def create_batch(
    payload: BatchCreate,
    session: Session = Depends(write_session),
    moment: datetime = Depends(now),
) -> BatchRead:
    request = BakeRequest(
        recipe_id=payload.recipe_id,
        baked=payload.baked,
        expires=payload.expires,
        counts=payload.counts_by_size(),
    )
    batch_id = record_bake(session, request, now=moment)
    return BatchRead.from_model(_load_batch(session, batch_id))


@router.get("/{batch_id}")
def get_batch(batch_id: int, session: Session = Depends(read_session)) -> BatchRead:
    return BatchRead.from_model(_load_batch(session, batch_id))
