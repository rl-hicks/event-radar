"""Account-owned delivery status/revocation; initiation is operator-only."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from event_radar.api.contexts import Database, Identity
from event_radar.db.delivery import DeliveryDenied, revoke
from event_radar.db.models import DeliveryBinding

router = APIRouter(prefix="/api/me/delivery")


@router.get("/bindings")
def bindings(identity: Identity, session: Database, response: Response) -> list[dict[str, object]]:
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "id": str(row.id),
            "channel": row.channel,
            "revision": row.revision,
            "status": row.status,
            "consent": row.consent,
        }
        for row in session.scalars(
            select(DeliveryBinding)
            .where(DeliveryBinding.user_id == identity.id)
            .order_by(DeliveryBinding.revision)
        )
    ]


@router.post("/bindings/{binding_id}/revoke", status_code=204)
def revoke_binding(binding_id: UUID, identity: Identity, session: Database) -> None:
    try:
        revoke(session, identity.id, binding_id)
    except DeliveryDenied:
        raise HTTPException(status_code=404) from None
