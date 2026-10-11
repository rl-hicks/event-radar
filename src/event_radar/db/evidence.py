"""Public regional evidence export using WP6 validated wire contracts."""

import hashlib
import json
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.models import RegionalResearchRun, RegionalUniverse
from event_radar.db.regional import read_regional_snapshot
from event_radar.models.regional import FailureCode, OperationalDiagnostics, ResearchIdentity
from event_radar.models.regional_discovery import AdaptiveDiscoverySummary


def integrity_envelope(payload: dict[str, object]) -> dict[str, object]:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "format": "event-radar-public-evidence-v1",
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "payload": payload,
    }


def export_snapshot(session: Session, snapshot_id: UUID) -> dict[str, object]:
    stored = read_regional_snapshot(session, snapshot_id)
    if stored is None:
        return integrity_envelope(
            {
                "availability": "unavailable",
                "requested_snapshot_id": str(snapshot_id),
                "record": None,
            }
        )
    runs = []
    for run in session.scalars(
        select(RegionalResearchRun)
        .where(RegionalResearchRun.universe_id == stored.universe_id)
        .order_by(RegionalResearchRun.started_at, RegionalResearchRun.id)
    ):
        runs.append(_run_record(run))
    summary = (
        AdaptiveDiscoverySummary.model_validate(stored.discovery_summary)
        if stored.discovery_summary is not None
        else None
    )
    return integrity_envelope(
        {
            "availability": "exported",
            "snapshot_id": str(stored.snapshot_id),
            "universe_id": str(stored.universe_id),
            "snapshot_content_hash": stored.content_hash,
            "quality_status": stored.quality_status,
            "universe": stored.universe.model_dump(mode="json", exclude_none=False),
            "opportunity_counts": {
                "total": len(stored.universe.opportunities),
                "events": sum(o.kind == "event" for o in stored.universe.opportunities),
                "hikes": sum(o.kind == "hike" for o in stored.universe.opportunities),
            },
            "discovery_summary": summary.model_dump(mode="json") if summary else None,
            "related_identity_runs": runs,
            "accounting_note": "Nulls are unknown; known subtotals are not a complete bill. "
            "Model estimates exclude tool fees. Related runs may refer to other snapshots.",
        }
    )


def _run_record(run: RegionalResearchRun) -> dict[str, object]:
    if run.status not in ("running", "success", "partial", "failed"):
        raise ValueError("Invalid stored run status.")
    # Select public columns explicitly; validate JSON instead of exporting arbitrary DB blobs.
    payload = run.diagnostics_payload
    if payload is not None and (not isinstance(payload, dict) or set(payload) != {"stages"}):
        raise ValueError("Invalid stored run diagnostics envelope.")
    stages = payload["stages"] if payload is not None else []
    diagnostics = TypeAdapter(tuple[OperationalDiagnostics, ...]).validate_python(stages)
    summary = (
        AdaptiveDiscoverySummary.model_validate(run.discovery_summary)
        if run.discovery_summary is not None
        else None
    )
    return {
        "run_id": str(run.id),
        "status": run.status,
        "snapshot_id": str(run.snapshot_id) if run.snapshot_id else None,
        "requested_as_of": run.requested_as_of.isoformat(),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "failure_code": TypeAdapter(FailureCode | None).validate_python(run.failure_code),
        "diagnostics": [d.model_dump(mode="json") for d in diagnostics],
        "discovery_summary": summary.model_dump(mode="json") if summary else None,
    }


def export_run(session: Session, run_id: UUID) -> dict[str, object]:
    """Export one public research attempt, including a first failure without a snapshot."""
    run = session.get(RegionalResearchRun, run_id)
    if run is None:
        return integrity_envelope(
            {
                "availability": "unavailable",
                "requested_run_id": str(run_id),
                "record": None,
            }
        )
    logical = session.get(RegionalUniverse, run.universe_id)
    if logical is None:
        raise ValueError("Stored run references a missing regional identity.")
    identity = ResearchIdentity(
        region_id=logical.region_id,
        friday=logical.weekend_friday,
        research_policy_version=logical.research_policy_version,
    )
    record = _run_record(run)
    snapshot = None
    if run.snapshot_id is not None:
        stored = read_regional_snapshot(session, run.snapshot_id)
        if (
            stored is None
            or stored.universe_id != run.universe_id
            or stored.universe.scope.as_of != run.requested_as_of
        ):
            raise ValueError("Stored run references an inconsistent snapshot.")
        snapshot = {
            "snapshot_id": str(stored.snapshot_id),
            "quality_status": stored.quality_status,
            "content_hash": stored.content_hash,
            "schema_version": stored.universe.schema_version,
        }
    return integrity_envelope(
        {
            "availability": "exported",
            "universe_id": str(logical.id),
            "identity": identity.model_dump(mode="json"),
            "record": record,
            "snapshot": snapshot,
            "accounting_note": "Nulls are unknown; known subtotals are not a complete bill. "
            "Model estimates exclude tool fees.",
        }
    )
