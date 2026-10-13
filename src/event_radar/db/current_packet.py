"""Read-only current-week applicability for the explicitly supported research region."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.contexts import read_context
from event_radar.db.models import (
    CurationJob,
    RegionalUniverse,
    RegionalUniverseSnapshot,
    UserContextRevision,
    WeekendPacketRecord,
)
from event_radar.db.packets import PacketCorrupt, read_packet
from event_radar.models.product_context import ContextModel
from event_radar.models.weekend_packet import WeekendPacket

REGION = "sonoma-county-ca"
RESEARCH_POLICY = "e1-weekly-sonoma-v1"


class CurrentPacket(ContextModel):
    state: Literal["current", "older_context", "not_generated", "unavailable"]
    weekend_friday: date
    region_id: str = REGION
    context_revision_id: UUID | None = None
    degraded: bool = False
    research_stale: bool = False
    snapshot_superseded: bool = False
    packet: WeekendPacket | None = None


def current_friday(now: datetime) -> date:
    if now.utcoffset() is None:
        raise ValueError("Aware time required.")
    day = now.astimezone(ZoneInfo("America/Los_Angeles")).date()
    return day + timedelta(days=4 - day.weekday())


def read_current_packet(
    session: Session,
    authenticated_id: UUID,
    *,
    now: datetime | None = None,
    research_policy: str = RESEARCH_POLICY,
) -> CurrentPacket:
    observed = now or datetime.now(UTC)
    friday = current_friday(observed)
    context = read_context(session, authenticated_id)
    revision_id = context.revision_id if context else None
    regional = session.scalar(
        select(RegionalUniverse).where(
            RegionalUniverse.region_id == REGION,
            RegionalUniverse.weekend_friday == friday,
            RegionalUniverse.research_policy_version == research_policy,
        )
    )
    if regional is None:
        return CurrentPacket(
            state="not_generated", weekend_friday=friday, context_revision_id=revision_id
        )
    # Join on relational provenance, not untrusted JSON claims or insertion order.
    rows = session.execute(
        select(WeekendPacketRecord.id, UserContextRevision.revision)
        .join(
            RegionalUniverseSnapshot, WeekendPacketRecord.snapshot_id == RegionalUniverseSnapshot.id
        )
        .join(
            UserContextRevision, WeekendPacketRecord.context_revision_id == UserContextRevision.id
        )
        .where(
            WeekendPacketRecord.user_id == authenticated_id,
            RegionalUniverseSnapshot.universe_id == regional.id,
        )
    ).all()
    candidates = []
    for packet_id, revision in rows:
        try:
            packet = read_packet(session, authenticated_id, packet_id)
        except PacketCorrupt:
            # A corrupt candidate must not silently turn into a misleading older fallback.
            return CurrentPacket(
                state="unavailable", weekend_friday=friday, context_revision_id=revision_id
            )
        if packet is None or packet.research_as_of > observed:
            return CurrentPacket(
                state="unavailable", weekend_friday=friday, context_revision_id=revision_id
            )
        if packet.region_id != REGION or packet.weekend_friday != friday:
            return CurrentPacket(
                state="unavailable", weekend_friday=friday, context_revision_id=revision_id
            )
        candidates.append((revision, packet))
    if not candidates:
        job = session.scalar(
            select(CurationJob.id)
            .join(RegionalUniverseSnapshot, CurationJob.snapshot_id == RegionalUniverseSnapshot.id)
            .where(
                CurationJob.user_id == authenticated_id,
                RegionalUniverseSnapshot.universe_id == regional.id,
                CurationJob.status == "failed",
            )
            .limit(1)
        )
        return CurrentPacket(
            state="unavailable" if job else "not_generated",
            weekend_friday=friday,
            context_revision_id=revision_id,
        )
    # Newest context first, then full quality, research freshness, generation, UUID tie-break.
    _, packet = max(
        candidates,
        key=lambda pair: (
            pair[0],
            pair[1].status == "success",
            pair[1].research_as_of,
            pair[1].created_at,
            str(pair[1].packet_id),
        ),
    )
    stale = observed - packet.research_as_of > timedelta(hours=packet.policy.max_research_age_hours)
    superseded = packet.snapshot_id != regional.current_snapshot_id
    return CurrentPacket(
        state="current"
        if context and packet.context_revision_id == context.revision_id
        else "older_context",
        degraded=packet.status == "partial" or stale or superseded,
        research_stale=stale,
        snapshot_superseded=superseded,
        packet=packet,
        weekend_friday=friday,
        context_revision_id=revision_id,
    )
