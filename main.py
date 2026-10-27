"""FastAPI application factory."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.app import __version__
from backend.app.api.deps import build_container
from backend.app.api.routes import router
from backend.app.config import Settings, get_settings
from backend.app.logging_setup import configure_logging, request_id_var


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        app.state.container = build_container(settings)
        yield

    app = FastAPI(
        title="Root Canon AI",
        version=__version__,
        description="Evidence grounded clinical decision support for UK dental surgery.",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "X-API-Key"])

    @app.middleware("http")
    async def correlation(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(router)
    return app


app = create_app()
