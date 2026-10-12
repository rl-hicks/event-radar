"""Explicit internal packet operation. No HTTP trigger, delivery, research or retries."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from event_radar.db.contexts import ContextCorrupt, read_context
from event_radar.db.models import AppUser, CurationJob, WeekendPacketRecord
from event_radar.db.packets import read_packet
from event_radar.db.regional import read_regional_snapshot
from event_radar.models.weekend_packet import (
    CurationPolicy,
    CurationUsage,
    PersonalizedRequest,
    WeekendPacket,
    digest,
)
from event_radar.services.personalized_curation import (
    PROMPT,
    CurationProvider,
    ProviderFailure,
    invoke,
    validate_result,
)


@dataclass(frozen=True)
class GenerationOutcome:
    status: str
    packet_id: UUID | None = None
    failure_code: str | None = None


async def generate_packet(
    engine: Engine,
    authenticated_id: UUID,
    snapshot_id: UUID,
    policy: CurationPolicy,
    provider: CurationProvider,
    *,
    now: datetime | None = None,
) -> GenerationOutcome:
    """Account UUID is trusted internal authority, never an arbitrary public API selector.

    Durable unique insert claims the request before any provider call. Running/failed jobs
    are not retried implicitly (including process death); a future explicit recovery policy
    must reconcile uncertain spend. No database transaction is held across network work.
    """
    observed = now or datetime.now(UTC)
    if observed.utcoffset() is None:
        return GenerationOutcome("failed", failure_code="invalid_input")
    try:
        policy = CurationPolicy.model_validate(policy.model_dump(mode="json", warnings=False))
        with Session(engine) as session:
            snapshot = read_regional_snapshot(session, snapshot_id)
            context = read_context(session, authenticated_id)
        if snapshot is None:
            return GenerationOutcome("failed", failure_code="snapshot_missing")
        if context is None:
            return GenerationOutcome("failed", failure_code="context_missing")
        age = observed - snapshot.universe.scope.as_of
        if age < timedelta(0) or age > timedelta(hours=policy.max_research_age_hours):
            return GenerationOutcome("failed", failure_code="research_stale")
        if observed >= snapshot.universe.scope.window.end:
            return GenerationOutcome("failed", failure_code="weekend_expired")
        request = PersonalizedRequest(
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot.content_hash,
            research_quality=snapshot.quality_status,
            universe=snapshot.universe,
            context=context,
            policy=policy,
        )
    except ContextCorrupt:
        return GenerationOutcome("failed", failure_code="context_corrupt")
    except (ValueError, RuntimeError):
        return GenerationOutcome("failed", failure_code="invalid_input")
    identity = digest(
        {
            "account": str(authenticated_id),
            "request": request.model_dump(mode="json"),
            "prompt_hash": digest(PROMPT),
        }
    )
    execution_id = uuid4()
    with Session(engine) as session, session.begin():
        claimed = session.execute(
            insert(CurationJob)
            .values(
                id=execution_id,
                identity=identity,
                user_id=authenticated_id,
                snapshot_id=snapshot_id,
                snapshot_hash=snapshot.content_hash,
                context_revision_id=context.revision_id,
                context_hash=context.content_hash,
                policy_payload=policy.model_dump(mode="json"),
                status="running",
                started_at=datetime.now(UTC),
                finished_at=None,
                failure_code=None,
                usage_payload=None,
            )
            .on_conflict_do_nothing(index_elements=["identity"])
            .returning(CurationJob.id)
        ).scalar()
        if claimed is None:
            existing = session.scalar(select(CurationJob).where(CurationJob.identity == identity))
            assert existing is not None
            row = session.scalar(
                select(WeekendPacketRecord).where(
                    WeekendPacketRecord.execution_id == existing.id,
                    WeekendPacketRecord.user_id == authenticated_id,
                )
            )
            if row:
                packet = read_packet(session, authenticated_id, row.id)
                assert packet is not None
                return GenerationOutcome(packet.status, packet.packet_id)
            return GenerationOutcome(existing.status, failure_code=existing.failure_code)
    usage = CurationUsage()
    started = monotonic()
    failure = None
    cancelled = False
    try:
        response = await invoke(provider, request)
        usage = CurationUsage.model_validate(response.usage.model_dump(mode="json", warnings=False))
        recommendations = validate_result(request, response.result)
        status: Literal["success", "partial"] = (
            "partial"
            if "partial" in (request.research_quality, response.result.status)
            else "success"
        )
    except asyncio.CancelledError:
        failure, cancelled = "cancelled", True
    except (TimeoutError, ProviderFailure) as exc:
        failure = exc.code if isinstance(exc, ProviderFailure) else "timeout"
        if isinstance(exc, ProviderFailure):
            try:
                usage = CurationUsage.model_validate(
                    exc.usage.model_dump(mode="json", warnings=False)
                )
            except ValueError:
                usage = CurationUsage()
    except Exception:
        failure = "invalid_response"
    usage = usage.model_copy(update={"latency_seconds": monotonic() - started})
    completed = datetime.now(UTC)
    packet_id = uuid4()
    with Session(engine) as session, session.begin():
        # Same account lock as context writer closes the context-change publication race.
        session.execute(
            select(AppUser.id).where(AppUser.id == authenticated_id).with_for_update()
        ).one()
        job = session.get(CurationJob, execution_id)
        assert job is not None
        if failure is None:
            try:
                latest = read_context(session, authenticated_id)
                if latest is None or latest.revision_id != context.revision_id:
                    failure = "context_changed"
            except ContextCorrupt:
                failure = "context_corrupt"
        if failure is None:
            try:
                pinned = read_regional_snapshot(session, snapshot_id)
                if pinned is None or pinned.content_hash != request.snapshot_hash:
                    failure = "snapshot_changed"
            except (ValueError, RuntimeError):
                failure = "snapshot_corrupt"
        job.finished_at = completed
        job.usage_payload = usage.model_dump(mode="json")
        if failure:
            job.status = "failed"
            job.failure_code = failure
        else:
            packet = WeekendPacket(
                packet_id=packet_id,
                user_id=authenticated_id,
                execution_id=execution_id,
                curation_identity=identity,
                region_id=request.universe.scope.region.region_id,
                weekend_friday=request.universe.scope.window.friday,
                snapshot_id=snapshot_id,
                snapshot_hash=request.snapshot_hash,
                research_as_of=request.universe.scope.as_of,
                research_quality=request.research_quality,
                context_revision_id=context.revision_id,
                context_hash=context.content_hash,
                policy=policy,
                prompt_hash=digest(PROMPT),
                status=status,
                created_at=completed,
                recommendations=recommendations,
                usage=usage,
            )
            job.status = status
            session.add(
                WeekendPacketRecord(
                    id=packet_id,
                    user_id=authenticated_id,
                    execution_id=execution_id,
                    context_revision_id=context.revision_id,
                    snapshot_id=snapshot_id,
                    content_hash=digest(packet.model_dump(mode="json")),
                    packet_payload=packet.model_dump(mode="json"),
                    created_at=completed,
                )
            )
    if cancelled:
        raise asyncio.CancelledError
    if failure:
        return GenerationOutcome("failed", failure_code=failure)
    return GenerationOutcome(status, packet_id)
