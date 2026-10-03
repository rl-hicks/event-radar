"""WP3 process/database health and authenticated identity foundation."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from event_radar.api.dependencies import database_healthy, get_session
from event_radar.auth.identity import AuthenticatedUser, get_current_user
from event_radar.db.users import get_or_create_user

router = APIRouter()


class MeResponse(BaseModel):
    id: UUID
    email: str | None
    created_at: datetime
    database_roundtrip: bool


@router.get("/health")
def health(request: Request, healthy: Annotated[bool, Depends(database_healthy)]) -> JSONResponse:
    if healthy:
        return JSONResponse({"status": "ok", "database": "ok"})
    request.state.error_code = "database_unavailable"
    return JSONResponse(
        status_code=503,
        content={
            "status": "unavailable",
            "database": "unavailable",
            "error": {"code": "database_unavailable", "message": "Database unavailable."},
        },
    )


@router.get("/api/me", response_model=MeResponse)
def me(
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session, scope="function")],
) -> MeResponse:
    user = get_or_create_user(session, identity.id)
    return MeResponse(
        id=user.id,
        email=identity.email,
        created_at=user.created_at,
        database_roundtrip=True,
    )
