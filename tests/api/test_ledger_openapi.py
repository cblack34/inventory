"""OpenAPI-shape checks for the ledger resources (`docs/acceptance.md`).

No `PUT`, `PATCH`, or `DELETE` on batches, movements, entries, visits, or
reversals; undo is its own `POST /api/v1/reversals` endpoint rather than
an entry update; and no route anywhere declares a state-changing `GET`
(a `GET` operation with a request body).
"""

from typing import Any

from fastapi import FastAPI

_LEDGER_PATH_PREFIXES = (
    "/api/v1/batches",
    "/api/v1/movements",
    "/api/v1/reversals",
    "/api/v1/visits",
    "/api/v1/entries",
)


def test_no_put_patch_or_delete_on_any_ledger_resource(app: FastAPI) -> None:
    schema = app.openapi()

    for path, methods in schema["paths"].items():
        if path.startswith(_LEDGER_PATH_PREFIXES):
            assert "put" not in methods, path
            assert "patch" not in methods, path
            assert "delete" not in methods, path


def test_undo_is_its_own_post_endpoint_not_an_entry_update(app: FastAPI) -> None:
    schema = app.openapi()

    assert "post" in schema["paths"]["/api/v1/reversals"]
    entry_detail = schema["paths"].get("/api/v1/entries/{entry_id}", {})
    assert "patch" not in entry_detail
    assert "put" not in entry_detail
    assert "post" not in entry_detail


def test_no_state_changing_get_anywhere_in_the_document(app: FastAPI) -> None:
    schema = app.openapi()

    for path, methods in schema["paths"].items():
        get_operation = methods.get("get")
        if get_operation is not None:
            assert "requestBody" not in get_operation, path


def test_movements_resource_has_no_list_or_detail_get(app: FastAPI) -> None:
    """The movement ledger is append-only and read only through stock/entries."""
    schema = app.openapi()

    assert "get" not in schema["paths"]["/api/v1/movements"]


def _declared_type(property_schema: dict[str, Any]) -> str | None:
    """The JSON Schema `type` of `property_schema`, unwrapping an optional field's `anyOf`.

    Mirrors `tests.api.test_catalog_openapi._declared_type`; duplicated
    here (rather than imported) so each OpenAPI-shape module stays a
    self-contained pin -- see that module's docstring for why a nullable
    field renders as `anyOf` rather than a top-level `type`.
    """
    if "type" in property_schema:
        return property_schema["type"]
    for branch in property_schema.get("anyOf", ()):
        if branch.get("type") not in (None, "null"):
            return branch["type"]
    return None


def test_every_ledger_money_weight_and_quantity_field_is_integer(app: FastAPI) -> None:
    """The ledger-side counterpart of the catalog OpenAPI-integer check.

    Explicit per-schema field list (mirroring
    `docs/acceptance.md`'s Money enumeration) rather than a name-suffix
    heuristic, so a schema that drops `type: integer` -- or a renamed
    field this list is not updated for -- fails loudly rather than being
    silently skipped.
    """
    schemas = app.openapi()["components"]["schemas"]
    expected_integer_fields = {
        "BakeCountItem": ("count",),
        "BatchRead": ("total_cost_cents",),
        "BatchSizeRead": ("count_made", "unit_cost_cents"),
        "MovementCreate": ("quantity",),
        "StandRowIn": ("counted", "tossed", "pulled", "added"),
        "MarketRowIn": ("taken", "returned", "tossed"),
        "StandVisitCreate": ("revenue_cents",),
        "MarketVisitCreate": ("revenue_cents", "fee_cents"),
        "VisitRead": (
            "revenue_cents",
            "fee_cents",
            "expected_revenue_cents",
            "difference_cents",
        ),
        "ProfitRead": (
            "sold_cost_cents",
            "waste_cost_cents",
            "sampled_cost_cents",
            "profit_cents",
        ),
        "BatchStockRead": ("quantity",),
        "SizeStockRead": ("quantity",),
        # `EntryRead.revenue_cents`/`profit_cents` are `int | None` (a
        # non-visit entry has neither); the OpenAPI shape is
        # `anyOf: [{type: integer}, {type: null}]`, which
        # `_declared_type` already unwraps to the non-null branch.
        "EntryRead": ("revenue_cents", "profit_cents"),
    }

    for schema_name, fields in expected_integer_fields.items():
        properties = schemas[schema_name]["properties"]
        for field in fields:
            declared_type = _declared_type(properties[field])
            assert declared_type == "integer", f"{schema_name}.{field} is {declared_type!r}"
