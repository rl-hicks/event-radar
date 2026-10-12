"""Authenticated self-service context, with no caller-selected account route."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from event_radar.api.dependencies import get_session
from event_radar.auth.identity import AuthenticatedUser, get_current_user
from event_radar.db.contexts import read_context, write_context
from event_radar.models.product_context import ContextRevision, ContextUpdate, ProductUserContext

router = APIRouter(prefix="/api/me/context")
Identity = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_session, scope="function")]


@router.get("", response_model=ContextRevision)
def get_context(identity: Identity, session: Database, response: Response) -> ContextRevision:
    response.headers["Cache-Control"] = "no-store"
    result = read_context(session, identity.id)
    if result is None:
        raise HTTPException(status_code=404)
    return result


@router.post("", response_model=ContextRevision, status_code=201)
def create_context(
    context: ProductUserContext, identity: Identity, session: Database, response: Response
) -> ContextRevision:
    response.headers["Cache-Control"] = "no-store"
    return write_context(session, identity.id, context, expected_revision_id=None)


@router.put("", response_model=ContextRevision)
def update_context(
    update: ContextUpdate, identity: Identity, session: Database, response: Response
) -> ContextRevision:
    response.headers["Cache-Control"] = "no-store"
    return write_context(
        session, identity.id, update.context, expected_revision_id=update.expected_revision_id
    )
