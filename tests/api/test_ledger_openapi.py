"""OpenAPI-shape checks for the ledger resources (`docs/acceptance.md`).

No `PUT`, `PATCH`, or `DELETE` on batches, movements, entries, visits, or
reversals; undo is its own `POST /api/v1/reversals` endpoint rather than
an entry update; and no route anywhere declares a state-changing `GET`
(a `GET` operation with a request body).
"""

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
