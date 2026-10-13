"""Import an already-exported public snapshot without research or identity rewriting."""

from typing import Literal
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.evidence import integrity_envelope
from event_radar.db.models import RegionalUniverse, RegionalUniverseSnapshot
from event_radar.db.regional import read_regional_snapshot
from event_radar.models.regional import RegionalWeekendUniverse
from event_radar.models.regional_discovery import AdaptiveDiscoverySummary
from event_radar.models.weekend_packet import digest


def import_public_snapshot(session: Session, envelope: dict[str, object]) -> UUID:
    """Caller explicitly selects a local application database and trusted export path.

    Envelope integrity detects corruption, not authenticity; provenance must be reviewed.
    No runs are invented. Snapshot insertion time is local; research as-of stays original.
    """
    if set(envelope) != {"format", "sha256", "payload"}:
        raise ValueError("Invalid public export.")
    payload = envelope["payload"]
    if not isinstance(payload, dict) or integrity_envelope(payload) != envelope:
        raise ValueError("Public export integrity failed.")
    if payload.get("availability") != "exported":
        raise ValueError("Snapshot unavailable.")
    universe = RegionalWeekendUniverse.model_validate(payload["universe"])
    sid, uid = UUID(payload["snapshot_id"]), UUID(payload["universe_id"])
    hashed = digest(universe.model_dump(mode="json"))
    if hashed != payload["snapshot_content_hash"]:
        raise ValueError("Snapshot integrity failed.")
    quality: Literal["success", "partial"] = TypeAdapter(
        Literal["success", "partial"]
    ).validate_python(payload["quality_status"])
    summary = payload.get("discovery_summary")
    summary = (
        AdaptiveDiscoverySummary.model_validate(summary).model_dump(mode="json")
        if summary
        else None
    )
    existing = read_regional_snapshot(session, sid)
    if existing:
        if (
            existing.universe_id != uid
            or existing.content_hash != hashed
            or existing.quality_status != quality
            or existing.discovery_summary != summary
        ):
            raise ValueError("Existing snapshot differs.")
        return sid
    scope = universe.scope
    logical = session.scalar(
        select(RegionalUniverse).where(
            RegionalUniverse.region_id == scope.region.region_id,
            RegionalUniverse.weekend_friday == scope.window.friday,
            RegionalUniverse.research_policy_version == scope.research_policy_version,
        )
    )
    if logical is not None or session.get(RegionalUniverse, uid) is not None:
        raise ValueError("Existing research identity requires explicit reconciliation.")
    logical = RegionalUniverse(
        id=uid,
        region_id=scope.region.region_id,
        weekend_friday=scope.window.friday,
        research_policy_version=scope.research_policy_version,
    )
    session.add(logical)
    session.flush()
    session.add(
        RegionalUniverseSnapshot(
            id=sid,
            universe_id=uid,
            schema_version=universe.schema_version,
            as_of=scope.as_of,
            quality_status=quality,
            content_hash=hashed,
            universe_payload=universe.model_dump(mode="json"),
            discovery_summary=summary,
        )
    )
    session.flush()
    logical.current_snapshot_id = sid
    session.flush()
    if read_regional_snapshot(session, sid) is None:
        raise ValueError("Imported snapshot unavailable.")
    return sid
