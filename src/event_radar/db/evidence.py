"""Public regional evidence export using WP6 validated wire contracts."""

import hashlib
import json
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.models import RegionalResearchRun
from event_radar.db.regional import read_regional_snapshot
from event_radar.models.regional import FailureCode, OperationalDiagnostics
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
        if run.status not in ("running", "success", "partial", "failed"):
            raise ValueError("Invalid stored run status.")
        # Select public columns explicitly; validate JSON instead of exporting arbitrary DB blobs.
        stages = (run.diagnostics_payload or {}).get("stages", [])
        diagnostics = TypeAdapter(tuple[OperationalDiagnostics, ...]).validate_python(stages)
        summary = (
            AdaptiveDiscoverySummary.model_validate(run.discovery_summary)
            if run.discovery_summary is not None
            else None
        )
        runs.append(
            {
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
        )
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
