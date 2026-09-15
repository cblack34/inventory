"""RFC 9457 Problem Details: one error envelope for every rejection.

`docs/build-brief.md`'s `/api/v1` architecture bullet: every error
response is `application/problem+json` with `type`, `title`, `status`,
`detail`, and `instance`; a domain rejection carries the exception's own
fields as extension members, and a validation rejection carries an
`errors` list.
"""

import re
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import NoResultFound
from starlette.exceptions import HTTPException as StarletteHTTPException

from inventory.domain import DomainError

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_PROBLEM_URN_PREFIX = "urn:inventory:problem:"
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


class Problem(BaseModel):
    """An RFC 9457 Problem Details document; extra keys are extension members."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class ProblemHTTPException(HTTPException):
    """An `HTTPException` that names its own Problem `type`, `title`, and extensions.

    Raised directly by auth code (401 unauthorized, 429 throttled) where
    there is no domain exception to introspect.
    """

    def __init__(
        self, status_code: int, *, type_: str, title: str, detail: str, **extra: object
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.type = type_
        self.title = title
        self.extra = extra


def _slug(class_name: str) -> str:
    """`InsufficientStock` -> `insufficient-stock`; `InvalidQuantityError` -> `invalid-quantity`."""
    return _CAMEL_BOUNDARY.sub("-", class_name.removesuffix("Error")).lower()


def _humanize(class_name: str) -> str:
    """`InsufficientStock` -> `Insufficient Stock`."""
    return _CAMEL_BOUNDARY.sub(" ", class_name.removesuffix("Error"))


def _detail_or_none(detail: object) -> str | None:
    """`exc.detail` as a Problem `detail`, never the literal string `"None"`.

    `HTTPException.detail` is typed `Any` and defaults to `None` for a
    bare `HTTPException(status_code=...)` call; falling through to
    `str(None)` would render the four-character string `"None"` in the
    response body instead of leaving `detail` empty.
    """
    if detail is None:
        return None
    return str(detail)


_ECHOING_ERROR_KEYS = frozenset({"input", "ctx"})


def _sanitized_errors(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every `RequestValidationError.errors()` item, minus `input` and `ctx`.

    `input` is pydantic's copy of the offending value verbatim -- a
    rejected password, for instance -- and `ctx` can carry a value
    derived from it; `type`, `loc`, and `msg` never do. Dropping both
    keeps a 422 body from echoing what the caller submitted.
    """
    return [
        {key: value for key, value in error.items() if key not in _ECHOING_ERROR_KEYS}
        for error in errors
    ]


def _validation_location(exc: RequestValidationError) -> str:
    """The first error's request part (`body`, `query`, `path`, ...), or `body` as a fallback.

    `RequestValidationError` covers every part of the request FastAPI
    validates through a Pydantic model, not only the JSON body -- a
    path parameter like `IdPath` (`GET /ingredients/0`) or a query
    parameter fails through the same exception, with `errors()[0]["loc"]`
    naming the part first. A hard-coded "request body failed
    validation" read as wrong for those; deriving the word instead
    keeps the detail accurate for whichever part actually failed.
    """
    errors = exc.errors()
    if errors and errors[0]["loc"]:
        location = errors[0]["loc"][0]
        if isinstance(location, str):
            return location
    return "body"


def _http_status_title(status_code: int) -> str:
    """`HTTPStatus(status_code).phrase`, or `HTTP {status_code}` for a non-standard code.

    `HTTPStatus` raises `ValueError` for a code it does not know (e.g. a
    made-up `599`); a Problem still needs a `title` for those.
    """
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return f"HTTP {status_code}"


def _extension_members(exc: BaseException) -> dict[str, object]:
    """Every non-private attribute of `exc`, JSON-encoded for the Problem body.

    `vars(exc)` is whatever a `DomainError` subclass set on `self` in its
    own `__init__` (a plain `Exception`'s `args` lives outside `__dict__`
    and never appears here); `jsonable_encoder` handles anything
    `json.dumps` can't on its own, such as a `date` or a `frozenset`.
    """
    return {
        key: jsonable_encoder(value) for key, value in vars(exc).items() if not key.startswith("_")
    }


def problem_response() -> dict[str, Any]:
    """An OpenAPI `responses` entry describing an `application/problem+json` body.

    Not `{"model": Problem}`: FastAPI's `model=` shortcut always adds the
    schema under the route's default response media type
    (`application/json` here, since nothing overrides
    `default_response_class`), regardless of what `content` also says --
    so it cannot express "this response is `application/problem+json`
    and nothing else." A raw `content` dict with a `$ref` sidesteps that;
    `_register_problem_schema` below makes sure `Problem` actually lands
    in `components.schemas` for the `$ref` to resolve, since no route
    ever exercises the `model=` path that would otherwise put it there.
    """
    return {"content": {_PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}}}


def _register_problem_schema(app: FastAPI) -> None:
    """Add `Problem` to `components.schemas` once, on top of `app.openapi()`.

    FastAPI's own documented way to post-process a generated schema
    (https://fastapi.tiangolo.com/how-to/extending-openapi/): wrap the
    bound method so the first call still builds and caches the schema
    normally, then add the one schema `problem_response`'s `$ref` needs
    that nothing else registers.
    """
    original_openapi = app.openapi

    def _openapi_with_problem_schema() -> dict[str, Any]:
        schema = original_openapi()
        schema.setdefault("components", {}).setdefault("schemas", {})["Problem"] = (
            Problem.model_json_schema()
        )
        return schema

    app.openapi = _openapi_with_problem_schema


def _response(
    problem: Problem,
    *,
    request: Request,
    extra: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, object] = problem.model_copy(update={"instance": request.url.path}).model_dump()
    if extra:
        body.update(jsonable_encoder(extra))
    return JSONResponse(
        status_code=problem.status,
        content=body,
        media_type=_PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    """Register the exception handlers that turn every rejection into a `Problem`."""

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        class_name = type(exc).__name__
        problem = Problem(
            type=_PROBLEM_URN_PREFIX + _slug(class_name),
            title=_humanize(class_name),
            status=422,
            detail=str(exc),
        )
        return _response(problem, request=request, extra=_extension_members(exc))

    @app.exception_handler(NoResultFound)
    async def _no_result_found(request: Request, exc: NoResultFound) -> JSONResponse:
        problem = Problem(
            type=_PROBLEM_URN_PREFIX + "not-found",
            title="Not Found",
            status=404,
            detail=str(exc) or "the requested resource does not exist",
        )
        return _response(problem, request=request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        problem = Problem(
            type=_PROBLEM_URN_PREFIX + "validation",
            title="Validation Error",
            status=422,
            detail=f"request {_validation_location(exc)} failed validation",
        )
        errors = _sanitized_errors(exc.errors())
        return _response(problem, request=request, extra={"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handles every `HTTPException`, ours or Starlette's own.

        Registered for Starlette's base class, not FastAPI's subclass:
        Starlette raises its own base `HTTPException` directly for cases
        FastAPI never sees first, such as a matched path with the wrong
        method (405) -- an app-level handler keyed on the FastAPI
        subclass would miss those and fall back to Starlette's default
        plain-JSON error body.
        """
        if isinstance(exc, ProblemHTTPException):
            problem = Problem(
                type=exc.type,
                title=exc.title,
                status=exc.status_code,
                detail=_detail_or_none(exc.detail),
            )
            return _response(problem, request=request, extra=exc.extra, headers=exc.headers)
        problem = Problem(
            type=_PROBLEM_URN_PREFIX + f"http-{exc.status_code}",
            title=_http_status_title(exc.status_code),
            status=exc.status_code,
            detail=_detail_or_none(exc.detail),
        )
        return _response(problem, request=request, headers=exc.headers)

    _register_problem_schema(app)
