"""Enrich a domain rejection with the names the Problem body must carry.

`docs/acceptance.md`'s ledger/stock bullet requires a domain rejection to
name the recipe, size, and location, not just their bare ids -- but a
`DomainError` (in `inventory.domain.*`, off limits to this slice) only
ever carries a `size_id`, a `size_ids` collection, a `recipe_id`, and/or
a `location_id`, since the domain package has no database access to
look those up. This module is the one place that does that lookup, on
the way out of a persistence call and before the exception reaches
`problems.py`'s Problem Details handler, which copies every public
`vars(exc)` member into the response body.
"""

from collections.abc import Collection, Generator
from contextlib import contextmanager
from typing import Protocol, cast

from sqlalchemy.orm import Session

from inventory.db.models import Location, Recipe, Size
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
    size_names: dict[int, str]
    size_recipe_id: int
    location_name: str


def _add_size_name(session: Session, context: _CatalogNames, exc: DomainError) -> None:
    """From a singular `size_id`: `size_name`, and the target `recipe_id` when unset.

    `SizeNotInRecipeError` already carries the *target* recipe's id
    (the recipe being patched); the size named belongs to a different,
    foreign recipe. Overwriting `recipe_id` with the foreign size's
    recipe would misreport which recipe the caller meant to patch, so an
    already-set `recipe_id` is left alone, and the foreign recipe goes
    into `size_recipe_id` instead, but only when it actually differs.
    """
    size_id = getattr(exc, "size_id", None)
    if not isinstance(size_id, int):
        return
    size = session.get(Size, size_id)
    if size is None:
        return
    context.size_name = size.name
    existing_recipe_id = getattr(exc, "recipe_id", None)
    if not isinstance(existing_recipe_id, int):
        context.recipe_id = size.recipe_id
    elif size.recipe_id != existing_recipe_id:
        context.size_recipe_id = size.recipe_id


def _add_recipe_name(session: Session, context: _CatalogNames, exc: DomainError) -> None:
    """From `exc.recipe_id` (its own, or the one `_add_size_name` just filled in)."""
    recipe_id = getattr(exc, "recipe_id", None)
    if not isinstance(recipe_id, int) or getattr(exc, "recipe_name", None) is not None:
        return
    recipe = session.get(Recipe, recipe_id)
    if recipe is not None:
        context.recipe_name = recipe.name


def _add_location_name(session: Session, context: _CatalogNames, exc: DomainError) -> None:
    location_id = getattr(exc, "location_id", None)
    if not isinstance(location_id, int):
        return
    location = session.get(Location, location_id)
    if location is not None:
        context.location_name = location.name


def _add_size_names(session: Session, context: _CatalogNames, exc: DomainError) -> None:
    """From a plural `size_ids` collection (e.g. `UnknownSizeError`)."""
    raw = getattr(exc, "size_ids", None)
    if not isinstance(raw, (frozenset, set, list)):
        return
    size_ids = cast(Collection[object], raw)
    names: dict[int, str] = {}
    for size_id in size_ids:
        if isinstance(size_id, int):
            size = session.get(Size, size_id)
            if size is not None:
                names[size_id] = size.name
    context.size_names = names


def with_catalog_names(session: Session, exc: DomainError) -> DomainError:
    """Add `recipe_id`, `recipe_name`, `size_name`/`size_names`, `location_name` when known.

    Looked up from `exc.size_id` (and its recipe), `exc.size_ids`,
    `exc.recipe_id`, and `exc.location_id` -- most `DomainError`
    subclasses carry one or two of these, a few carry more, and some
    (e.g. a bad `counts[<size>]` quantity) carry none. A lookup that
    finds no row is skipped rather than raised: a stale or malformed id
    must not turn one rejection into a different, more confusing one.
    Mutates `exc` in place and returns it so a call site can write
    `raise with_catalog_names(session, exc) from None`.
    """
    context = cast(_CatalogNames, exc)
    _add_size_name(session, context, exc)
    _add_recipe_name(session, context, exc)
    _add_location_name(session, context, exc)
    _add_size_names(session, context, exc)
    return exc


@contextmanager
def catalog_errors(session: Session) -> Generator[None]:
    """Wrap one persistence call: enrich any `DomainError` it raises before it propagates.

    `raise with_catalog_names(session, exc) from None` inline at every
    catalog and bake call site would repeat the same four lines in
    `routes/batches.py`, `routes/recipes.py`, `routes/locations.py`, and
    `routes/ingredients.py`; this is that block, usable as
    `with catalog_errors(session): row = create_recipe(session, request)`.
    """
    try:
        yield
    except DomainError as exc:
        raise with_catalog_names(session, exc) from None
