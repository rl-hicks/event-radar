"""Ownership-protected historical packet read. Never initiates curation."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from event_radar.api.contexts import Database, Identity
from event_radar.db.current_packet import CurrentPacket, read_current_packet
from event_radar.db.packets import read_packet
from event_radar.models.weekend_packet import WeekendPacket

router = APIRouter(prefix="/api/me/packets")


@router.get("/current", response_model=CurrentPacket)
def get_current_packet(identity: Identity, session: Database, response: Response) -> CurrentPacket:
    response.headers["Cache-Control"] = "no-store"
    return read_current_packet(session, identity.id)


@router.get("/{packet_id}", response_model=WeekendPacket)
def get_packet(
    packet_id: UUID, identity: Identity, session: Database, response: Response
) -> WeekendPacket:
    response.headers["Cache-Control"] = "no-store"
    packet = read_packet(session, identity.id, packet_id)
    if packet is None:
        raise HTTPException(status_code=404)
    return packet
