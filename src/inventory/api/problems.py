"""RFC 9457 Problem Details: one error envelope for every rejection.

`docs/build-brief.md`'s `/api/v1` architecture bullet: every error
response is `application/problem+json` with `type`, `title`, `status`,
`detail`, and `instance`; a domain rejection carries the exception's own
fields as extension members, and a validation rejection carries an
`errors` list.
"""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import NoResultFound

from inventory.domain import DomainError

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_PROBLEM_URN_PREFIX = "urn:inventory:problem:"
_SCALAR_EXTENSION_TYPES = (int, str, bool, type(None))
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


def _is_int_collection(value: object) -> bool:
    if not isinstance(value, (list, set, frozenset)):
        return False
    items = cast("list[object] | set[object] | frozenset[object]", value)
    return all(isinstance(item, int) for item in items)


def _extension_members(exc: BaseException) -> dict[str, object]:
    """Every public attribute of `exc` that is a plain scalar or a collection of ints.

    Sets become sorted lists so the JSON body is deterministic.
    """
    members: dict[str, object] = {}
    for key, value in vars(exc).items():
        if isinstance(value, _SCALAR_EXTENSION_TYPES):
            members[key] = value
        elif _is_int_collection(value):
            if isinstance(value, (set, frozenset)):
                members[key] = sorted(cast("set[int] | frozenset[int]", value))
            else:
                members[key] = value
    return members


def _response(
    problem: Problem, *, request: Request, extra: dict[str, object] | None = None
) -> JSONResponse:
    body: dict[str, object] = problem.model_copy(update={"instance": request.url.path}).model_dump()
    if extra:
        body.update(jsonable_encoder(extra))
    return JSONResponse(status_code=problem.status, content=body, media_type=_PROBLEM_MEDIA_TYPE)


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
            detail="request body failed validation",
        )
        return _response(problem, request=request, extra={"errors": exc.errors()})

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc, ProblemHTTPException):
            problem = Problem(
                type=exc.type,
                title=exc.title,
                status=exc.status_code,
                detail=str(exc.detail),
            )
            return _response(problem, request=request, extra=exc.extra)
        problem = Problem(
            type=_PROBLEM_URN_PREFIX + f"http-{exc.status_code}",
            title=HTTPStatus(exc.status_code).phrase,
            status=exc.status_code,
            detail=str(exc.detail),
        )
        return _response(problem, request=request)
