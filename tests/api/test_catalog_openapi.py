"""OpenAPI-shape checks for the catalog resources (`docs/acceptance.md`).

No `DELETE` on ingredients, recipes, sizes (sizes have no path of their
own), or locations; no `PUT` anywhere; every catalog money, weight, or
quantity field is declared `integer`, on every create, read, and
patch/update schema that carries one -- derived once from
`app.openapi()["components"]["schemas"]` and hard-coded below so a
regression (a new numeric field, or a schema that loses `type:
integer`) is caught.
"""

from typing import Any

from fastapi import FastAPI

_CATALOG_PATH_PREFIXES = ("/api/v1/ingredients", "/api/v1/recipes", "/api/v1/locations")


def test_no_delete_on_any_catalog_resource(app: FastAPI) -> None:
    schema = app.openapi()

    for path, methods in schema["paths"].items():
        if path.startswith(_CATALOG_PATH_PREFIXES):
            assert "delete" not in methods, path


def test_no_put_anywhere_in_the_document(app: FastAPI) -> None:
    schema = app.openapi()

    for methods in schema["paths"].values():
        assert "put" not in methods


def _declared_type(property_schema: dict[str, Any]) -> str | None:
    """The JSON Schema `type` of `property_schema`, unwrapping an optional field's `anyOf`.

    Pydantic v2 renders `int | None` as `{"anyOf": [{"type": "integer",
    ...}, {"type": "null"}]}` rather than a top-level `type`, since a
    nullable field has no single JSON Schema type; every patch/update
    field checked here is exactly that shape, so the non-null branch's
    `type` is what matters. Returns a type only when every non-null
    `anyOf` branch agrees on it, so e.g. `anyOf: [{type: integer},
    {type: string}, {type: null}]` (a field that isn't cleanly one
    type) resolves to `None` rather than silently picking the first
    branch and passing an `== "integer"` check it shouldn't.
    """
    if "type" in property_schema:
        return property_schema["type"]
    non_null_types = {
        branch["type"]
        for branch in property_schema.get("anyOf", ())
        if branch.get("type") not in (None, "null")
    }
    if len(non_null_types) == 1:
        return next(iter(non_null_types))
    return None


def test_declared_type_requires_every_non_null_anyof_branch_to_agree() -> None:
    """Pins the tightened `_declared_type`: a mixed `anyOf` is not silently `integer`."""
    assert _declared_type({"type": "integer"}) == "integer"
    assert _declared_type({"anyOf": [{"type": "integer"}, {"type": "null"}]}) == "integer"
    assert (
        _declared_type({"anyOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}]})
        is None
    )
    assert _declared_type({"anyOf": [{"type": "null"}]}) is None


def test_every_catalog_money_weight_and_quantity_field_is_integer(app: FastAPI) -> None:
    schemas = app.openapi()["components"]["schemas"]
    expected_integer_fields = {
        "IngredientCreate": ("current_price_cents",),
        "IngredientRead": ("current_price_cents",),
        "IngredientUpdate": ("current_price_cents",),
        "RecipeCreate": ("shelf_life_days",),
        "RecipePatch": ("shelf_life_days",),
        "RecipeRead": ("shelf_life_days",),
        "RecipeLineInput": ("quantity",),
        "RecipeLineRead": ("quantity",),
        "SizeCreate": ("portion_weight_g", "price_cents", "typical_yield_count"),
        "SizePatchItem": ("portion_weight_g", "price_cents", "typical_yield_count"),
        "SizeRead": (
            "portion_weight_g",
            "price_cents",
            "typical_yield_count",
            "estimated_unit_cost_cents",
        ),
    }

    for schema_name, fields in expected_integer_fields.items():
        properties = schemas[schema_name]["properties"]
        for field in fields:
            declared_type = _declared_type(properties[field])
            assert declared_type == "integer", f"{schema_name}.{field} is {declared_type!r}"


def test_size_patch_item_id_is_a_plain_optional_integer_not_nullable(app: FastAPI) -> None:
    """`SizePatchItem.id` renders as `{"type": "integer"}`, never `anyOf`/`null`.

    An explicit `null` is rejected at the wire (`_reject_explicit_null_id`
    in `inventory.api.schemas.catalog`) -- only an absent key means
    "create a new size" -- so the generated schema, and the TypeScript
    it drives, must describe `id` as an optional plain integer rather
    than a nullable one.
    """
    id_schema = app.openapi()["components"]["schemas"]["SizePatchItem"]["properties"]["id"]

    assert id_schema.get("type") == "integer"
    assert "anyOf" not in id_schema
    assert "null" not in id_schema.values()
