"""Direct Pydantic `model_fields` enumeration for docs/acceptance.md's Money bullet.

`tests/api/test_catalog_openapi.py` and `tests/api/test_ledger_openapi.py`
assert the generated OpenAPI JSON Schema `type` for an explicit field
list -- one layer removed from the Pydantic model itself: a field could
carry the right JSON Schema `type` by accident of how a particular
`Annotated[...]` alias happens to serialize while the underlying Python
annotation drifted (or vice versa). This module walks every `BaseModel`
subclass defined in `inventory.api.schemas.catalog`,
`inventory.api.schemas.ledger`, `inventory.api.auth`, and `inventory.app`
directly via `model_fields[name].annotation` (mirroring
`tests.domain.test_no_floats`'s dataclass walk), so a regression is
caught even if it never reaches the OpenAPI layer at all.
"""

import inspect
import typing
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from inventory import app as app_module
from inventory.api import auth as auth_module
from inventory.api.schemas import catalog, ledger

_MODULES = (catalog, ledger, auth_module, app_module)

_FORBIDDEN_TYPES = {float, Decimal}

_EXPECTED_INT_FIELDS: dict[type[BaseModel], tuple[str, ...]] = {
    # --- inventory.api.schemas.catalog ---
    catalog.IngredientCreate: ("current_price_cents",),
    catalog.IngredientUpdate: ("current_price_cents",),
    catalog.IngredientRead: ("current_price_cents",),
    catalog.RecipeLineInput: ("quantity",),
    catalog.RecipeLineRead: ("quantity",),
    catalog.SizeCreate: ("portion_weight_g", "price_cents", "typical_yield_count"),
    catalog.SizePatchItem: ("portion_weight_g", "price_cents", "typical_yield_count"),
    catalog.SizeRead: (
        "portion_weight_g",
        "price_cents",
        "typical_yield_count",
        "estimated_unit_cost_cents",
    ),
    catalog.RecipeCreate: ("shelf_life_days",),
    catalog.RecipePatch: ("shelf_life_days",),
    catalog.RecipeRead: ("shelf_life_days",),
    # --- inventory.api.schemas.ledger ---
    ledger.BakeCountItem: ("count",),
    ledger.BatchSizeRead: ("count_made", "unit_cost_cents"),
    ledger.BatchRead: ("total_cost_cents",),
    ledger.MovementCreate: ("quantity",),
    ledger.StandRowIn: ("counted", "tossed", "pulled", "added"),
    ledger.MarketRowIn: ("taken", "returned", "tossed"),
    ledger.StandVisitCreate: ("revenue_cents",),
    ledger.MarketVisitCreate: ("revenue_cents", "fee_cents"),
    ledger.ProfitRead: (
        "sold_cost_cents",
        "waste_cost_cents",
        "sampled_cost_cents",
        "profit_cents",
    ),
    ledger.VisitRead: (
        "revenue_cents",
        "fee_cents",
        "expected_revenue_cents",
        "difference_cents",
    ),
    ledger.EntryRead: ("revenue_cents", "profit_cents"),
    ledger.BatchStockRead: ("quantity",),
    ledger.SizeStockRead: ("quantity",),
}
"""Every money (`*_cents`), weight (`portion_weight_g`), or quantity/count
field (`quantity`, `shelf_life_days`, and the count fields
`docs/acceptance.md`'s Money bullet enumerates) on a `BaseModel` defined in
one of `_MODULES`. `inventory.api.auth.LoginRequest` and `inventory.app
.HealthResponse` carry no such field, so neither appears here; they are
still walked by the negative check below. Update this alongside the
SQLAlchemy (`tests/db/test_columns.py`), OpenAPI
(`tests/api/test_catalog_openapi.py`, `tests/api/test_ledger_openapi.py`),
and domain-dataclass (`tests/domain/test_no_floats.py`) enumerations
whenever a money, weight, or quantity field is added."""


def _mentions_forbidden_type(annotation: Any) -> bool:
    """True if `annotation` is, or nests anywhere, a forbidden type."""
    if annotation in _FORBIDDEN_TYPES:
        return True
    return any(_mentions_forbidden_type(arg) for arg in typing.get_args(annotation))


def _model_classes() -> list[type[BaseModel]]:
    """Every `BaseModel` subclass defined directly in one of `_MODULES`.

    `obj.__module__ == module.__name__` excludes a class merely imported
    into the module's namespace (for example `catalog.py` imports
    `RecipeLine`/`SizeYield` dataclasses, and every schema module
    re-exports `BaseModel` itself), so only that module's own models
    are collected.
    """
    found: list[type[BaseModel]] = []
    for module in _MODULES:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
    return found


def test_walk_reaches_every_model_with_an_enumerated_money_field() -> None:
    """Sanity check: the walk must actually reach every class enumerated below.

    Without this, a typo in `_MODULES` or the `__module__` filter would
    make `test_enumerated_pydantic_money_weight_and_quantity_fields_are_exactly_int`
    below vacuously correct instead of actually exercising the model.
    """
    found = {cls.__qualname__ for cls in _model_classes()}
    expected = {cls.__qualname__ for cls in _EXPECTED_INT_FIELDS}
    assert expected <= found


def test_enumerated_pydantic_money_weight_and_quantity_fields_are_exactly_int() -> None:
    """Positive check: each enumerated field resolves to exactly `int` (or `int | None`).

    `typing.get_type_hints` (rather than `model_fields[name].annotation`)
    strips the `Annotated[int, Field(...)]` wrapper the `Cents`/`Count`/
    `PositiveCount` aliases in `inventory.api.schemas.numbers` add, so an
    optional money field compares equal to plain `int | None` instead of
    `Annotated[int, FieldInfo(...)] | None`.
    """
    for model_cls, fields in _EXPECTED_INT_FIELDS.items():
        hints = typing.get_type_hints(model_cls)
        for field in fields:
            annotation = hints[field]
            assert annotation is int or annotation == (int | None), (
                f"{model_cls.__qualname__}.{field} is {annotation!r}, not int or int | None"
            )


def test_no_pydantic_model_field_is_float_or_decimal() -> None:
    """Negative check across every model in `_MODULES`, not just the enumerated list.

    Catches a money/weight/quantity field this module's enumeration
    hasn't been updated for yet, the same way
    `test_no_domain_dataclass_field_is_float_or_decimal` backstops
    `tests.domain.test_no_floats`'s own enumerated list.
    """
    offenders: list[str] = []
    for model_cls in _model_classes():
        hints = typing.get_type_hints(model_cls)
        for field_name in model_cls.model_fields:
            annotation = hints.get(field_name)
            if _mentions_forbidden_type(annotation):
                offenders.append(f"{model_cls.__qualname__}.{field_name}")

    assert offenders == []
