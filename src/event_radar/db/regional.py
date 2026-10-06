"""Transactional persistence for the shared Regional Weekend Universe."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.db.models import (
    RegionalResearchRun,
    RegionalUniverse,
    RegionalUniverseSnapshot,
)
from event_radar.models.regional import (
    FailureCode,
    OperationalDiagnostics,
    RegionalWeekendUniverse,
    ResearchIdentity,
    ResearchScope,
)
from event_radar.models.regional_discovery import AdaptiveDiscoverySummary

SnapshotQuality = Literal["success", "partial"]


@dataclass(frozen=True, slots=True)
class PersistedUniverse:
    universe_id: UUID
    snapshot_id: UUID
    quality_status: SnapshotQuality
    content_hash: str
    universe: RegionalWeekendUniverse
    discovery_summary: dict[str, object] | None


def begin_regional_research_run(
    session: Session,
    scope: ResearchScope,
    *,
    run_id: UUID | None = None,
) -> RegionalResearchRun:
    """Create one running attempt against the stable logical universe key."""
    identity = _get_or_create_identity(session, scope)
    identifier = run_id or uuid4()
    existing = session.get(RegionalResearchRun, identifier)
    if existing is not None:
        if existing.universe_id != identity.id or existing.requested_as_of.astimezone(
            UTC
        ) != scope.as_of.astimezone(UTC):
            raise ValueError("Existing regional run ID belongs to different research inputs.")
        return existing

    run = RegionalResearchRun(
        id=identifier,
        universe_id=identity.id,
        status="running",
        requested_as_of=scope.as_of,
        finished_at=None,
        snapshot_id=None,
        failure_code=None,
        diagnostics_payload=None,
        discovery_summary=None,
    )
    session.add(run)
    session.flush()
    return run


def complete_regional_research_run(
    session: Session,
    run_id: UUID,
    universe: RegionalWeekendUniverse,
    *,
    quality_status: SnapshotQuality,
    failure_code: FailureCode | None = None,
    diagnostics: tuple[OperationalDiagnostics, ...] = (),
    discovery_summary: AdaptiveDiscoverySummary | None = None,
    finished_at: datetime | None = None,
) -> RegionalUniverseSnapshot:
    """Persist/reuse an immutable snapshot and complete a running attempt.

    Successful snapshots always advance the logical head. A partial snapshot advances
    the head only when no prior usable snapshot exists, preserving a previous success.
    """
    run = _running_run(session, run_id)
    identity = session.get(RegionalUniverse, run.universe_id)
    if identity is None:
        raise RuntimeError("Regional run references a missing logical universe.")

    expected = ResearchIdentity(
        region_id=identity.region_id,
        friday=identity.weekend_friday,
        research_policy_version=identity.research_policy_version,
    )
    if universe.scope.identity != expected:
        raise ValueError("Persisted universe identity does not match the research run.")
    if universe.scope.as_of.astimezone(UTC) != run.requested_as_of.astimezone(UTC):
        raise ValueError("Persisted universe as_of does not match the research run.")
    if quality_status == "success" and failure_code is not None:
        raise ValueError("Successful regional runs cannot carry a failure code.")
    if quality_status == "partial" and failure_code is None:
        raise ValueError("Partial regional runs require a bounded failure code.")

    payload = universe.model_dump(mode="json", exclude_none=False)
    content_hash = _content_hash(payload)
    snapshot = session.scalar(
        select(RegionalUniverseSnapshot).where(
            RegionalUniverseSnapshot.universe_id == identity.id,
            RegionalUniverseSnapshot.content_hash == content_hash,
        )
    )
    summary_payload = (
        discovery_summary.model_dump(mode="json", exclude_none=False)
        if discovery_summary is not None
        else None
    )
    if snapshot is None:
        snapshot = RegionalUniverseSnapshot(
            id=uuid4(),
            universe_id=identity.id,
            schema_version=universe.schema_version,
            as_of=universe.scope.as_of,
            quality_status=quality_status,
            content_hash=content_hash,
            universe_payload=payload,
            discovery_summary=summary_payload,
        )
        session.add(snapshot)
        session.flush()
    elif snapshot.quality_status != quality_status:
        raise ValueError("Identical snapshot content cannot change its quality classification.")

    completed_at = _aware_now(finished_at)
    run.status = quality_status
    run.finished_at = completed_at
    run.snapshot_id = snapshot.id
    run.failure_code = failure_code
    run.diagnostics_payload = _diagnostics_payload(diagnostics)
    run.discovery_summary = summary_payload

    if quality_status == "success" or identity.current_snapshot_id is None:
        identity.current_snapshot_id = snapshot.id
    identity.updated_at = completed_at
    session.flush()
    return snapshot


def fail_regional_research_run(
    session: Session,
    run_id: UUID,
    *,
    failure_code: FailureCode,
    diagnostics: tuple[OperationalDiagnostics, ...] = (),
    discovery_summary: AdaptiveDiscoverySummary | None = None,
    finished_at: datetime | None = None,
) -> RegionalResearchRun:
    """Record a failed attempt without altering the last-good snapshot pointer."""
    run = _running_run(session, run_id)
    identity = session.get(RegionalUniverse, run.universe_id)
    if identity is None:
        raise RuntimeError("Regional run references a missing logical universe.")

    completed_at = _aware_now(finished_at)
    run.status = "failed"
    run.finished_at = completed_at
    run.snapshot_id = None
    run.failure_code = failure_code
    run.diagnostics_payload = _diagnostics_payload(diagnostics)
    run.discovery_summary = (
        discovery_summary.model_dump(mode="json", exclude_none=False)
        if discovery_summary is not None
        else None
    )
    identity.updated_at = completed_at
    session.flush()
    return run


def read_current_regional_universe(
    session: Session,
    identity: ResearchIdentity,
) -> PersistedUniverse | None:
    """Read the current last-good universe through the validated wire contract."""
    record = session.scalar(
        select(RegionalUniverse).where(
            RegionalUniverse.region_id == identity.region_id,
            RegionalUniverse.weekend_friday == identity.friday,
            RegionalUniverse.research_policy_version == identity.research_policy_version,
        )
    )
    if record is None or record.current_snapshot_id is None:
        return None
    snapshot = session.get(RegionalUniverseSnapshot, record.current_snapshot_id)
    if snapshot is None or snapshot.universe_id != record.id:
        raise RuntimeError("Regional universe head references an invalid snapshot.")
    parsed = RegionalWeekendUniverse.model_validate(snapshot.universe_payload)
    quality = snapshot.quality_status
    if quality not in ("success", "partial"):
        raise RuntimeError("Stored regional snapshot has an invalid quality status.")
    typed_quality = cast(SnapshotQuality, quality)
    return PersistedUniverse(
        universe_id=record.id,
        snapshot_id=snapshot.id,
        quality_status=typed_quality,
        content_hash=snapshot.content_hash,
        universe=parsed,
        discovery_summary=snapshot.discovery_summary,
    )


def _get_or_create_identity(session: Session, scope: ResearchScope) -> RegionalUniverse:
    identity = scope.identity
    record = session.scalar(
        select(RegionalUniverse).where(
            RegionalUniverse.region_id == identity.region_id,
            RegionalUniverse.weekend_friday == identity.friday,
            RegionalUniverse.research_policy_version == identity.research_policy_version,
        )
    )
    if record is not None:
        return record
    record = RegionalUniverse(
        id=uuid4(),
        region_id=identity.region_id,
        weekend_friday=identity.friday,
        research_policy_version=identity.research_policy_version,
        current_snapshot_id=None,
    )
    session.add(record)
    session.flush()
    return record


def _running_run(session: Session, run_id: UUID) -> RegionalResearchRun:
    run = session.get(RegionalResearchRun, run_id)
    if run is None:
        raise ValueError("Regional research run does not exist.")
    if run.status != "running":
        raise ValueError("Regional research run is already finalized.")
    return run


def _content_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _diagnostics_payload(
    diagnostics: tuple[OperationalDiagnostics, ...],
) -> dict[str, object] | None:
    if not diagnostics:
        return None
    return {"stages": [item.model_dump(mode="json", exclude_none=False) for item in diagnostics]}


def _aware_now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.utcoffset() is None:
        raise ValueError("Regional persistence timestamps must be timezone-aware.")
    return result
