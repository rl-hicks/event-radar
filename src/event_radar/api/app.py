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
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from event_radar.api.config import web_origins
from event_radar.api.dependencies import DatabaseResources
from event_radar.api.errors import DatabaseUnavailable, error_response
from event_radar.api.routes import router

logger = logging.getLogger("event_radar.api")


def create_app() -> FastAPI:
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

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        return error_response(request, 422, "validation_error", "Request validation failed.")

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
    # Outer CORS middleware also applies to sanitized error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_origins(),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )
    return app
