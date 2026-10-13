"""API foundation isolated from the personal research runtime."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from event_radar.api.config import web_origins
from event_radar.api.contexts import router as context_router
from event_radar.api.cors import ProductCORSMiddleware
from event_radar.api.delivery import router as delivery_router
from event_radar.api.dependencies import DatabaseResources
from event_radar.api.errors import DatabaseUnavailable, error_response
from event_radar.api.packets import router as packet_router
from event_radar.api.routes import router
from event_radar.auth.config import AuthUnavailable
from event_radar.db.contexts import ContextConflict, ContextCorrupt
from event_radar.db.packets import PacketCorrupt

logger = logging.getLogger("event_radar.api")


def create_app(*, telegram_webhook_secret: str | None = None) -> FastAPI:
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)
    resources = DatabaseResources()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            resources.close()

    app = FastAPI(
        title="Event Radar",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.database = resources

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        errors = {
            401: ("authentication_required", "Authentication required."),
            403: ("forbidden", "Access denied."),
            404: ("not_found", "Resource not found."),
            405: ("method_not_allowed", "Method not allowed."),
        }
        code, message = errors.get(exc.status_code, ("request_error", "Request failed."))
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return error_response(request, exc.status_code, code, message, headers=headers)

    @app.exception_handler(ContextConflict)
    async def context_conflict(request: Request, exc: ContextConflict) -> Response:
        return error_response(
            request, 409, "context_conflict", "Context changed; read it again before saving."
        )

    @app.exception_handler(PacketCorrupt)
    async def packet_corrupt(request: Request, exc: PacketCorrupt) -> Response:
        return error_response(request, 503, "packet_unavailable", "Packet unavailable.")

    @app.exception_handler(ContextCorrupt)
    async def context_corrupt(request: Request, exc: ContextCorrupt) -> Response:
        return error_response(request, 503, "context_unavailable", "Context unavailable.")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        return error_response(request, 422, "validation_error", "Request validation failed.")

    @app.exception_handler(AuthUnavailable)
    async def auth_unavailable(request: Request, exc: AuthUnavailable) -> Response:
        return error_response(
            request, 503, "authentication_unavailable", "Authentication unavailable."
        )

    @app.exception_handler(DatabaseUnavailable)
    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: Exception) -> Response:
        return error_response(request, 503, "database_unavailable", "Database unavailable.")

    @app.middleware("http")
    async def request_log(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Do not log exception strings, traceback locals, bodies, or headers.
            response = error_response(request, 500, "internal_error", "Internal server error.")
        if request.url.path.startswith(("/api/me/packets", "/api/me/delivery")):
            response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        # Route templates avoid logging arbitrary secret-bearing paths or query strings.
        path = getattr(route, "path", "<unmatched>")
        logger.info(
            json.dumps(
                {
                    "event": "api_request",
                    "method": request.method[:16],
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "error_code": getattr(request.state, "error_code", None),
                }
            )
        )
        return response

    app.include_router(router)
    app.include_router(context_router)
    app.include_router(packet_router)
    app.include_router(delivery_router)
    if telegram_webhook_secret is not None:
        from event_radar.api.telegram_inbound import webhook_router

        app.include_router(webhook_router(telegram_webhook_secret))
    # Outer CORS middleware also applies to sanitized error responses.
    app.add_middleware(ProductCORSMiddleware, origins=web_origins())
    return app
