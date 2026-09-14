"""Lookup of the built-in locations, by kind, never by hard-coded id.

The initial migration seeds Kitchen, Production, Sold, Waste, and Sampled
(see `docs/data-model.md`, "Location"). Callers that need their ids --
the writes and visits leaves -- look them up here by `kind` so a future
migration could in principle renumber them without breaking anything.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventory.db.models import Location
from inventory.domain.visits import Locations

_KITCHEN = "kitchen"
_PRODUCTION = "production"
_SOLD = "sold"
_WASTE = "waste"
_SAMPLED = "sampled"
_INVENTORY_KINDS = (_KITCHEN, "stand", "market")


class MissingBuiltinLocationError(LookupError):
    """A required built-in location row is missing from the database."""

    def __init__(self, *, missing_kinds: frozenset[str]) -> None:
        self.missing_kinds = missing_kinds
        super().__init__(f"missing built-in locations for kinds: {sorted(missing_kinds)}")


@dataclass(frozen=True)
class BuiltinLocations:
    """The built-in singleton location ids, plus the `Locations` a visit needs.

    `Locations` (from `inventory.domain.visits`) has no field for
    Production, since Production never appears in a visit's inventory
    set -- it is the source of bakes only. `production_id` is carried
    alongside it here for the writes leaf's bake recording.
    """

    production_id: int
    locations: Locations


def load_builtin_locations(session: Session) -> BuiltinLocations:
    """Look up the built-in locations and every inventory location's id.

    `locations.inventory_location_ids` is Kitchen plus every stand and
    market row that exists (active or not -- an inactive location can
    still hold on-hand and appear in a fold; see `docs/data-model.md`,
    "Location"). Raises `MissingBuiltinLocationError` if any of the five
    singleton kinds has no row, which should only happen against a
    database that was never migrated.
    """
    rows = session.execute(
        select(Location.id, Location.kind).where(Location.kind.in_(_INVENTORY_KINDS))
    ).all()
    inventory_location_ids = frozenset(row.id for row in rows)
    singleton_ids_by_kind = {row.kind: row.id for row in rows if row.kind == _KITCHEN}

    remaining_kinds = (_PRODUCTION, _SOLD, _WASTE, _SAMPLED)
    remaining_rows = session.execute(
        select(Location.id, Location.kind).where(Location.kind.in_(remaining_kinds))
    ).all()
    singleton_ids_by_kind.update({row.kind: row.id for row in remaining_rows})

    missing_kinds = frozenset((_KITCHEN, *remaining_kinds)) - singleton_ids_by_kind.keys()
    if missing_kinds:
        raise MissingBuiltinLocationError(missing_kinds=missing_kinds)

    locations = Locations(
        kitchen_id=singleton_ids_by_kind[_KITCHEN],
        sold_id=singleton_ids_by_kind[_SOLD],
        waste_id=singleton_ids_by_kind[_WASTE],
        sampled_id=singleton_ids_by_kind[_SAMPLED],
        inventory_location_ids=inventory_location_ids,
    )
    return BuiltinLocations(production_id=singleton_ids_by_kind[_PRODUCTION], locations=locations)
