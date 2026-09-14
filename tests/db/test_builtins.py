"""Pins `load_builtin_locations`: looked up by kind, never a hard-coded id."""

from sqlalchemy import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from inventory.db.builtins import load_builtin_locations
from inventory.db.models import Location


def test_load_builtin_locations_resolves_every_singleton_by_kind(engine: Engine) -> None:
    with Session(engine) as session:
        result = load_builtin_locations(session)

    ids_by_kind = {
        "kitchen": result.locations.kitchen_id,
        "production": result.production_id,
        "sold": result.locations.sold_id,
        "waste": result.locations.waste_id,
        "sampled": result.locations.sampled_id,
    }
    assert len(set(ids_by_kind.values())) == 5
    with Session(engine) as session:
        for kind, location_id in ids_by_kind.items():
            assert session.get(Location, location_id) is not None
            assert session.get_one(Location, location_id).kind == kind
    assert result.locations.inventory_location_ids == {result.locations.kitchen_id}


def test_load_builtin_locations_includes_stands_and_markets_in_inventory_set(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        session.execute(insert(Location).values(name="Farmers Market", kind="market", active=True))
        session.commit()

        result = load_builtin_locations(session)

    assert len(result.locations.inventory_location_ids) == 2
    assert result.locations.kitchen_id in result.locations.inventory_location_ids
