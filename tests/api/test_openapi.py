"""`app.openapi()` declares `Problem` so generated frontend types include it."""

import json

from fastapi import FastAPI


def test_problem_schema_is_declared_and_used_on_session_422(app: FastAPI) -> None:
    schema = app.openapi()

    assert "Problem" in schema["components"]["schemas"]

    session_post = schema["paths"]["/api/v1/session"]["post"]
    assert "422" in session_post["responses"]
    assert "Problem" in json.dumps(session_post["responses"]["422"])


def test_session_declares_429_too_many_requests(app: FastAPI) -> None:
    schema = app.openapi()

    session_post = schema["paths"]["/api/v1/session"]["post"]
    assert "429" in session_post["responses"]


def test_session_422_is_problem_json_only_no_application_json(app: FastAPI) -> None:
    session_post = app.openapi()["paths"]["/api/v1/session"]["post"]

    content = session_post["responses"]["422"]["content"]
    assert "application/problem+json" in content
    assert "application/json" not in content


def test_ui_routes_are_excluded_from_the_schema(app: FastAPI) -> None:
    schema = app.openapi()

    assert "/login" not in schema["paths"]
    assert "/{path}" not in schema["paths"]
