"""Enrich `InsufficientStock` with the names the Problem body must carry.

`docs/acceptance.md`'s ledger/stock bullet requires an insufficient-stock
rejection to name the recipe, size, and location, not just their bare
ids -- but `domain.ledger.InsufficientStock` only carries `location_id`
and `size_id`, since the domain package has no database access to look
those up. This module is the one place that does that lookup, on the
way out of a persistence call and before the exception reaches
`problems.py`'s Problem Details handler, which copies every public
`vars(exc)` member into the response body.
"""

from typing import Protocol, cast

from sqlalchemy.orm import Session

from inventory.db.models import Location, Size
from inventory.domain.ledger import InsufficientStock


class _StockContext(Protocol):
    """The four extension members this module adds to an `InsufficientStock`.

    `InsufficientStock` itself (in `inventory.domain.ledger`, off limits
    to this slice) declares none of these; a `Protocol` gives pyright a
    typed, mutable view of the same instance to assign through, instead
    of an untyped `setattr`.
    """

    recipe_id: int
    recipe_name: str
    size_name: str
    location_name: str


def with_stock_context(session: Session, exc: InsufficientStock) -> InsufficientStock:
    """Set `recipe_id`, `recipe_name`, `size_name`, and `location_name` on `exc`.

    Looked up from `exc.size_id` (and its recipe) and `exc.location_id`.
    Mutates `exc` in place and returns it so a call site can write
    `raise with_stock_context(session, exc) from None`.
    """
    size = session.get_one(Size, exc.size_id)
    location = session.get_one(Location, exc.location_id)
    context = cast(_StockContext, exc)
    context.recipe_id = size.recipe_id
    context.recipe_name = size.recipe.name
    context.size_name = size.name
    context.location_name = location.name
    return exc
