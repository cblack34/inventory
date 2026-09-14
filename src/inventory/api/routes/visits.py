"""`POST` and `GET` routes for the visits resource: stand and market settlement.

`docs/build-brief.md`: "a stand or market visit is `POST
/api/v1/visits` with the kind in the payload" -- one resource, a
discriminated union on `kind` rather than two separate routes. No
`PUT`, `PATCH`, or `DELETE`: a saved visit's revenue, fee, and expected
revenue are permanent; undo (`POST /api/v1/reversals`) is the only
correction path. Every route sits behind `require_session`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import now, read_session, write_session
from inventory.api.schemas.ledger import MarketVisitCreate, StandVisitCreate, VisitCreate, VisitRead
from inventory.db.models import Entry, Location
from inventory.db.models import Visit as VisitRow
from inventory.db.visits import (
    MarketVisit,
    StandVisit,
    record_market_visit,
    record_stand_visit,
    visit_profit,
)
from inventory.domain.visits import MarketRow, StandRow

router = APIRouter(prefix="/visits", tags=["visits"], dependencies=[Depends(require_session)])


def _record_stand(session: Session, payload: StandVisitCreate, moment: datetime) -> int:
    rows = [
        StandRow(
            size_id=row.size_id,
            counted=row.counted,
            tossed=row.tossed,
            pulled=row.pulled,
            added=row.added,
        )
        for row in payload.rows
    ]
    visit = StandVisit(stand_id=payload.location_id, rows=rows, revenue_cents=payload.revenue_cents)
    return record_stand_visit(session, visit, now=moment)


def _record_market(session: Session, payload: MarketVisitCreate, moment: datetime) -> int:
    rows = [
        MarketRow(size_id=row.size_id, taken=row.taken, returned=row.returned, tossed=row.tossed)
        for row in payload.rows
    ]
    visit = MarketVisit(
        market_id=payload.location_id,
        rows=rows,
        revenue_cents=payload.revenue_cents,
        fee_cents=payload.fee_cents,
    )
    return record_market_visit(session, visit, now=moment)


def _visit_read(session: Session, entry_id: int, *, voided: bool) -> VisitRead:
    visit_row = session.get(VisitRow, entry_id)
    if visit_row is None:
        raise NoResultFound(f"entry {entry_id} is not a visit")
    location = session.get_one(Location, visit_row.location_id)
    profit = None if voided else visit_profit(session, entry_id)
    return VisitRead.from_row(
        entry_id=entry_id, kind=location.kind, visit_row=visit_row, profit=profit
    )


@router.post("", status_code=201)
def create_visit(
    payload: VisitCreate,
    session: Session = Depends(write_session),
    moment: datetime = Depends(now),
) -> VisitRead:
    if payload.kind == "stand":
        entry_id = _record_stand(session, payload, moment)
    else:
        entry_id = _record_market(session, payload, moment)
    return _visit_read(session, entry_id, voided=False)


@router.get("/{entry_id}")
def get_visit(entry_id: int, session: Session = Depends(read_session)) -> VisitRead:
    entry = session.get_one(Entry, entry_id)
    return _visit_read(session, entry_id, voided=entry.voided)
