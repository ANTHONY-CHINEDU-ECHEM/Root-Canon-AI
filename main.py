"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app import __version__
from backend.app.api.deps import build_container
from backend.app.api.routes import router
from backend.app.config import Settings, get_settings
from backend.app.logging_setup import configure_logging, get_logger, request_id_var
from backend.app.observability import metrics

log = get_logger("api")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def _route_label(request: Request) -> str:
    # Use the route template, never the raw path, so metric cardinality stays bounded.
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


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
                       allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
                       expose_headers=["X-Request-ID", "Retry-After"])

    @app.middleware("http")
    async def correlation(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", "")[:64] or str(uuid.uuid4())
        request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - defensive: never leak a stack trace to a client
            log.exception("unhandled_error", path=request.url.path)
            response = JSONResponse({"detail": "Internal error", "request_id": request_id}, status_code=500)
        route = _route_label(request)
        metrics.HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        metrics.HTTP_LATENCY.labels(route).observe(time.perf_counter() - started)
        response.headers["X-Request-ID"] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    app.include_router(router)
    return app


app = create_app()
