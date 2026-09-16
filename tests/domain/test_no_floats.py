"""Pins the Money non-negotiable and docs/acceptance.md's Money bullet for
domain dataclasses: no field anywhere is `float` or `Decimal`.

Walks every submodule under `inventory.domain` (not just the package
`__init__`, which alone wouldn't see a submodule's own dataclasses),
collects every dataclass defined in one of those modules, and asserts
none of its fields resolve to `float` or `Decimal`.
"""

import dataclasses
import importlib
import pkgutil
import typing
from decimal import Decimal
from typing import Any

import inventory.domain as domain_pkg
from inventory.domain.costing import RecipeLine, SizeYield
from inventory.domain.ledger import Movement, PlannedMovement

# `_Leg` is a private module-level dataclass (no public re-export); imported
# directly, with an explicit pyright suppression, so its `quantity` field
# can be pinned alongside every other domain money/quantity field below.
from inventory.domain.visits import (
    MarketRow,
    Profit,
    StandRow,
    VisitPlan,
    _Leg,  # pyright: ignore[reportPrivateUsage]
)

_FORBIDDEN_TYPES = {float, Decimal}

_EXPECTED_INT_FIELDS: dict[type, tuple[str, ...]] = {
    RecipeLine: ("quantity", "unit_price_cents"),
    SizeYield: ("portion_weight_g", "count"),
    Movement: ("quantity",),
    PlannedMovement: ("quantity",),
    StandRow: ("counted", "tossed", "pulled", "added"),
    MarketRow: ("taken", "returned", "tossed"),
    Profit: ("sold_cost_cents", "waste_cost_cents", "sampled_cost_cents", "profit_cents"),
    VisitPlan: ("expected_revenue_cents",),
    _Leg: ("quantity",),
}
"""The money/weight/quantity fields `docs/acceptance.md`'s Money bullet
enumerates that live on a domain dataclass, mirroring the explicit lists
`test_pinned_money_weight_and_quantity_columns_are_integer` (SQLAlchemy)
and `test_every_catalog_money_weight_and_quantity_field_is_integer`
(OpenAPI) already keep for their own layer. Update this alongside those
two whenever a money, weight, or quantity field is added."""


def _mentions_forbidden_type(annotation: Any) -> bool:
    """True if `annotation` is, or nests anywhere, a forbidden type.

    Walks `typing.get_args` recursively so `float | None`, `list[float]`,
    and `dict[str, Decimal]` are caught, not only a bare `float`.
    """
    if annotation in _FORBIDDEN_TYPES:
        return True
    return any(_mentions_forbidden_type(arg) for arg in typing.get_args(annotation))


def _domain_dataclasses() -> list[type]:
    found: list[type] = []
    for module_info in pkgutil.walk_packages(domain_pkg.__path__, domain_pkg.__name__ + "."):
        module = importlib.import_module(module_info.name)
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and dataclasses.is_dataclass(obj)
                and obj.__module__.startswith(domain_pkg.__name__)
            ):
                found.append(obj)
    return found


def test_no_domain_dataclass_field_is_float_or_decimal() -> None:
    dataclass_types = _domain_dataclasses()
    # Sanity check: the walk must reach every domain module, including the
    # ones this leaf adds, or the assertion below passes vacuously.
    found_names = {dataclass_type.__qualname__ for dataclass_type in dataclass_types}
    assert {"SizeYield", "Movement", "StandRow", "MarketRow", "Profit"} <= found_names

    offenders: list[str] = []
    for dataclass_type in dataclass_types:
        hints: dict[str, Any] = typing.get_type_hints(dataclass_type)
        for field in dataclasses.fields(dataclass_type):
            field_type = hints.get(field.name, field.type)
            if _mentions_forbidden_type(field_type):
                offenders.append(
                    f"{dataclass_type.__module__}.{dataclass_type.__qualname__}.{field.name}"
                )

    assert offenders == []


def test_enumerated_domain_dataclass_money_and_quantity_fields_are_exactly_int() -> None:
    """Positive counterpart to `test_no_domain_dataclass_field_is_float_or_decimal`.

    That test only asserts a field is not `float`/`Decimal`; a field
    typed e.g. `str` for a quantity would pass it undetected, unlike the
    positive `isinstance(..., Integer)` / `declared_type == "integer"`
    checks the SQLAlchemy and catalog-OpenAPI sides use. This asserts
    the enumerated fields resolve to exactly `int`.
    """
    for dataclass_type, fields in _EXPECTED_INT_FIELDS.items():
        hints = typing.get_type_hints(dataclass_type)
        for field in fields:
            assert hints[field] is int, (
                f"{dataclass_type.__qualname__}.{field} is {hints[field]!r}, not int"
            )


def test_forbidden_type_detection_sees_nested_annotations() -> None:
    assert _mentions_forbidden_type(float)
    assert _mentions_forbidden_type(float | None)
    assert _mentions_forbidden_type(list[float])
    assert _mentions_forbidden_type(dict[str, Decimal])
    assert not _mentions_forbidden_type(int | None)
    assert not _mentions_forbidden_type(dict[str, int])
