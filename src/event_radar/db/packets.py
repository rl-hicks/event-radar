"""Private packet readback and integrity. Explicit packet ID never implies currentness."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.models import CurationJob, UserContextRevision, WeekendPacketRecord
from event_radar.db.regional import read_regional_snapshot
from event_radar.models.packet_validation import PROMPT, validate_result
from event_radar.models.product_context import ContextRevision, ProductUserContext
from event_radar.models.weekend_packet import (
    CurationResult,
    PersonalizedRequest,
    WeekendPacket,
    digest,
)


class PacketCorrupt(Exception):
    pass


def read_packet(session: Session, authenticated_id: UUID, packet_id: UUID) -> WeekendPacket | None:
    row = session.scalar(
        select(WeekendPacketRecord).where(
            WeekendPacketRecord.id == packet_id, WeekendPacketRecord.user_id == authenticated_id
        )
    )
    if row is None:
        return None
    try:
        packet = WeekendPacket.model_validate(row.packet_payload)
        if digest(packet.model_dump(mode="json")) != row.content_hash:
            raise ValueError
        job = session.get(CurationJob, row.execution_id)
        context = session.scalar(
            select(UserContextRevision).where(
                UserContextRevision.id == row.context_revision_id,
                UserContextRevision.user_id == authenticated_id,
            )
        )
        snapshot = read_regional_snapshot(session, row.snapshot_id)
        if context is None or snapshot is None or job is None:
            raise ValueError
        revision = ContextRevision(
            revision_id=context.id,
            revision=context.revision,
            created_at=context.created_at,
            content_hash=context.content_hash,
            context=ProductUserContext.model_validate(context.context_payload),
        )
        request = PersonalizedRequest(
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.content_hash,
            research_quality=snapshot.quality_status,
            universe=snapshot.universe,
            context=revision,
            policy=packet.policy,
        )
        expected_identity = digest(
            {
                "account": str(authenticated_id),
                "request": request.model_dump(mode="json"),
                "prompt_hash": digest(PROMPT),
            }
        )
        if (
            context.schema_version != revision.context.schema_version
            or packet.packet_id != row.id
            or packet.user_id != row.user_id
            or packet.execution_id != row.execution_id
            or packet.curation_identity != job.identity
            or packet.curation_identity != expected_identity
            or packet.snapshot_id != row.snapshot_id
            or packet.snapshot_hash != snapshot.content_hash
            or packet.context_revision_id != context.id
            or packet.context_hash != context.content_hash
            or packet.region_id != snapshot.universe.scope.region.region_id
            or packet.weekend_friday != snapshot.universe.scope.window.friday
            or packet.research_as_of != snapshot.universe.scope.as_of
            or packet.research_quality != snapshot.quality_status
            or packet.prompt_hash != digest(PROMPT)
            or packet.created_at != row.created_at
            or packet.status != job.status
            or job.user_id != authenticated_id
            or job.snapshot_id != row.snapshot_id
            or job.context_revision_id != context.id
            or job.snapshot_hash != snapshot.content_hash
            or job.context_hash != context.content_hash
            or job.policy_payload != packet.policy.model_dump(mode="json")
            or job.finished_at != packet.created_at
            or job.usage_payload != packet.usage.model_dump(mode="json")
            or packet.status
            != (
                "partial"
                if "partial" in (snapshot.quality_status, packet.curation_status)
                else "success"
            )
        ):
            raise ValueError
        rebuilt = validate_result(
            request,
            CurationResult(
                status=packet.curation_status,
                recommendations=tuple(r.judgment for r in packet.recommendations),
            ),
        )
        if rebuilt != packet.recommendations:
            raise ValueError
        return packet
    except Exception:
        raise PacketCorrupt from None
