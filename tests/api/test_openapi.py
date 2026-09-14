"""`app.openapi()` declares `Problem` so generated frontend types include it."""

import json

from fastapi import FastAPI


def test_problem_schema_is_declared_and_used_on_session_422(app: FastAPI) -> None:
    schema = app.openapi()

    assert "Problem" in schema["components"]["schemas"]

    session_post = schema["paths"]["/api/v1/session"]["post"]
    assert "422" in session_post["responses"]
    assert "Problem" in json.dumps(session_post["responses"]["422"])
