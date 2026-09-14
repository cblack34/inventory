"""FastAPI application factory."""

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


def create_app() -> FastAPI:
    app = FastAPI(
        title="inventory",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/api/v1/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app
