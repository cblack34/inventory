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

_FORBIDDEN_TYPES = {float, Decimal}


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
            if field_type in _FORBIDDEN_TYPES:
                offenders.append(
                    f"{dataclass_type.__module__}.{dataclass_type.__qualname__}.{field.name}"
                )

    assert offenders == []
