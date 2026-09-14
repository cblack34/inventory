"""OpenAPI-shape checks for the catalog resources (`docs/acceptance.md`).

No `DELETE` on ingredients, recipes, sizes (sizes have no path of their
own), or locations; no `PUT` anywhere; every catalog money, weight, or
quantity field is declared `integer`.
"""

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


def test_every_catalog_money_weight_and_quantity_field_is_integer(app: FastAPI) -> None:
    schemas = app.openapi()["components"]["schemas"]
    expected_integer_fields = {
        "IngredientCreate": ("current_price_cents",),
        "IngredientRead": ("current_price_cents",),
        "RecipeCreate": ("shelf_life_days",),
        "RecipeRead": ("shelf_life_days",),
        "RecipeLineInput": ("quantity",),
        "SizeCreate": ("portion_weight_g", "price_cents", "typical_yield_count"),
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
            declared_type = properties[field].get("type")
            assert declared_type == "integer", f"{schema_name}.{field} is {declared_type!r}"
