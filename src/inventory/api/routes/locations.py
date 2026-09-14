"""`GET`, `POST`, and `PATCH` routes for the locations resource.

No `PUT`, no `DELETE`: a stand or market is deactivate-only. Kind is
immutable and not even a field on the patch schema, so a payload naming
it is rejected as an unknown key. Every route sits behind
`require_session`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.api.auth import require_session
from inventory.api.deps import read_session, write_session
from inventory.api.schemas.catalog import LocationCreate, LocationPatch, LocationRead
from inventory.db.catalog import create_location, update_location
from inventory.db.models import Location

router = APIRouter(prefix="/locations", tags=["locations"], dependencies=[Depends(require_session)])


@router.get("")
def list_locations(session: Session = Depends(read_session)) -> list[LocationRead]:
    rows = session.execute(select(Location).order_by(Location.id)).scalars().all()
    return [LocationRead.model_validate(row) for row in rows]


@router.get("/{location_id}")
def get_location(location_id: int, session: Session = Depends(read_session)) -> LocationRead:
    row = session.get_one(Location, location_id)
    return LocationRead.model_validate(row)


@router.post("", status_code=201)
def create_location_route(
    payload: LocationCreate, session: Session = Depends(write_session)
) -> LocationRead:
    row = create_location(session, name=payload.name, kind=payload.kind)
    return LocationRead.model_validate(row)


@router.patch("/{location_id}")
def update_location_route(
    location_id: int, payload: LocationPatch, session: Session = Depends(write_session)
) -> LocationRead:
    row = update_location(session, location_id, name=payload.name, active=payload.active)
    return LocationRead.model_validate(row)
