import json
import logging
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from event_radar.api.schemas import HealthResponse, MeResponse
from event_radar.auth.supabase import (
    AuthenticatedUser,
    SupabaseAuthConfigurationError,
    get_current_user,
)
from event_radar.config import settings
from event_radar.db.session import (
    ProductDatabaseConfigurationError,
    check_database,
    get_session,
)
from event_radar.db.users import get_or_create_app_user

logger = logging.getLogger("event_radar.api")

DatabaseSession = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def _error_payload(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def create_app() -> FastAPI:
    app = FastAPI(title="Event Radar API", version="0.1.0")

    if settings.web_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.web_origin_list,
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                json.dumps(
                    {
                        "event": "api_request_failed",
                        "method": request.method,
                        "path": request.url.path,
                    }
                )
            )
            raise
        logger.info(
            json.dumps(
                {
                    "event": "api_request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload("request_error", message),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload("validation_error", "Request validation failed."),
        )

    @app.exception_handler(ProductDatabaseConfigurationError)
    async def database_configuration_handler(
        _request: Request, _exc: ProductDatabaseConfigurationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error_payload("database_unavailable", "Database is not configured."),
        )

    @app.exception_handler(SupabaseAuthConfigurationError)
    async def auth_configuration_handler(
        _request: Request, _exc: SupabaseAuthConfigurationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_error_payload("auth_unavailable", "Authentication is not configured."),
        )

    @app.get("/health", response_model=HealthResponse)
    def health(session: DatabaseSession) -> HealthResponse:
        check_database(session)
        return HealthResponse(status="ok", database="ok")

    @app.get("/api/me", response_model=MeResponse)
    def me(user: CurrentUser, session: DatabaseSession) -> MeResponse:
        app_user = get_or_create_app_user(session, user.id)
        return MeResponse(
            id=app_user.id,
            email=user.email,
            created_at=app_user.created_at,
            database_roundtrip=True,
        )

    return app


app = create_app()
