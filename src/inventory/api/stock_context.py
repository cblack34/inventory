"""Enrich a domain rejection with the names the Problem body must carry.

`docs/acceptance.md`'s ledger/stock bullet requires a domain rejection to
name the recipe, size, and location, not just their bare ids -- but a
`DomainError` (in `inventory.domain.*`, off limits to this slice) only
ever carries a `size_id` and/or a `location_id`, since the domain
package has no database access to look those up. This module is the one
place that does that lookup, on the way out of a persistence call and
before the exception reaches `problems.py`'s Problem Details handler,
which copies every public `vars(exc)` member into the response body.
"""

from typing import Protocol, cast

from sqlalchemy.orm import Session

from inventory.db.models import Location, Size
from inventory.domain import DomainError


class _CatalogNames(Protocol):
    """The extension members this module may add to a `DomainError`.

    No `DomainError` subclass declares these; a `Protocol` gives pyright
    a typed, mutable view of the same instance to assign through,
    instead of an untyped `setattr`.
    """

    recipe_id: int
    recipe_name: str
    size_name: str
    location_name: str


def with_catalog_names(session: Session, exc: DomainError) -> DomainError:
    """Add `recipe_id`, `recipe_name`, `size_name`, `location_name` when known.

    Looked up from `exc.size_id` (and its recipe) when `exc` carries an
    `int` `size_id`, and from `exc.location_id` when it carries an `int`
    `location_id` -- most `DomainError` subclasses carry one or the
    other, a few carry both, and some (e.g. a bad `counts[<size>]`
    quantity) carry neither. A lookup that finds no row is skipped
    rather than raised: a stale or malformed id must not turn one
    rejection into a different, more confusing one. Mutates `exc` in
    place and returns it so a call site can write
    `raise with_catalog_names(session, exc) from None`.
    """
    context = cast(_CatalogNames, exc)
    size_id = getattr(exc, "size_id", None)
    if isinstance(size_id, int):
        size = session.get(Size, size_id)
        if size is not None:
            context.recipe_id = size.recipe_id
            context.recipe_name = size.recipe.name
            context.size_name = size.name
    location_id = getattr(exc, "location_id", None)
    if isinstance(location_id, int):
        location = session.get(Location, location_id)
        if location is not None:
            context.location_name = location.name
    return exc
