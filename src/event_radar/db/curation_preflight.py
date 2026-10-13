"""Read-only AI #3 pilot preflight; no credentials, provider construction or network."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from event_radar.auth.identity import AuthenticatedUser
from event_radar.db.contexts import read_context
from event_radar.db.models import CurationJob, WeekendPacketRecord
from event_radar.db.regional import read_regional_snapshot
from event_radar.models.packet_validation import PROMPT, historical_validator
from event_radar.models.product_context import ContextModel
from event_radar.models.weekend_packet import (
    CurationPolicy,
    CurationResult,
    PersonalizedRequest,
    digest,
)

Rate = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class PricingReview(ContextModel):
    model: str
    input_usd_per_million: Rate
    output_usd_per_million: Rate
    model_context_tokens: int = Field(strict=True, ge=1, le=10000000)
    structured_output_supported: Literal[True]
    reviewed_at: AwareDatetime
    reference: str = Field(min_length=1, max_length=400)
    exposure_envelope_usd: Annotated[float, Field(gt=0, le=10, allow_inf_nan=False)]


class CurationPreflight(ContextModel):
    ready: bool
    blockers: tuple[str, ...]
    snapshot_id: UUID
    context_revision_id: UUID | None = None
    snapshot_hash: str | None = None
    research_policy: str | None = None
    research_as_of: AwareDatetime | None = None
    fresh_until: AwareDatetime | None = None
    research_quality: str | None = None
    weekend_friday: str | None = None
    opportunities: int | None = None
    request_bytes: int | None = None
    estimated_input_tokens: int | None = None
    estimated_exposure_usd: float | None = None
    policy: CurationPolicy
    prompt_hash: str = digest(PROMPT)
    existing_packet_id: UUID | None = None
    identity: str | None = None


def curation_preflight(
    session: Session,
    user: AuthenticatedUser,
    snapshot_id: UUID,
    policy: CurationPolicy,
    *,
    pricing: PricingReview | None = None,
    credentials_ready: bool = False,
    now: datetime | None = None,
) -> CurationPreflight:
    policy = CurationPolicy.model_validate(policy.model_dump(mode="json", warnings=False))
    observed = now or datetime.now(UTC)
    context = read_context(session, user.id)
    snapshot = read_regional_snapshot(session, snapshot_id)
    if context is None or snapshot is None:
        return CurationPreflight(
            ready=False,
            blockers=("context_missing" if context is None else "snapshot_missing",),
            snapshot_id=snapshot_id,
            policy=policy,
        )
    scope = snapshot.universe.scope
    blockers = []
    if observed < scope.as_of:
        blockers.append("research_future")
    if observed > scope.as_of + timedelta(hours=policy.max_research_age_hours):
        blockers.append("research_stale")
    if observed >= scope.window.end:
        blockers.append("weekend_expired")
    if scope.research_policy_version != policy.research_policy_version:
        blockers.append("research_policy_mismatch")
    if len(snapshot.universe.opportunities) > policy.max_opportunities:
        blockers.append("opportunity_limit")
    payload = dict(
        schema_version="personalized-request-v1",
        snapshot_id=str(snapshot_id),
        snapshot_hash=snapshot.content_hash,
        research_quality=snapshot.quality_status,
        universe=snapshot.universe.model_dump(mode="json"),
        context=context.model_dump(mode="json"),
        policy=policy.model_dump(mode="json"),
    )
    size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    if size > policy.max_input_bytes:
        blockers.append("request_size_limit")
    historical_validator(policy.version, policy.prompt_version, digest(PROMPT))
    identity, existing_id = None, None
    if not any(
        b in blockers
        for b in ("research_policy_mismatch", "opportunity_limit", "request_size_limit")
    ):
        request = PersonalizedRequest.model_validate(payload)
        size = len(request.model_dump_json().encode())
        identity = digest(
            {
                "account": str(user.id),
                "request": request.model_dump(mode="json"),
                "prompt_hash": digest(PROMPT),
            }
        )
        job = session.scalar(select(CurationJob).where(CurationJob.identity == identity))
        if job:
            existing_id = session.scalar(
                select(WeekendPacketRecord.id).where(
                    WeekendPacketRecord.execution_id == job.id,
                    WeekendPacketRecord.user_id == user.id,
                )
            )
            if existing_id is None:
                blockers.append("prior_claim_requires_reconciliation")
    # Conservative one-byte/token planning heuristic, including prompt/schema and framing reserve.
    # It is neither a tokenizer result nor a hard billing/context-window bound.
    estimated_tokens = (
        size
        + len(PROMPT.encode())
        + len(json.dumps(CurationResult.model_json_schema()).encode())
        + 4096
    )
    exposure = 0.0 if policy.provider == "deterministic" else None
    if policy.provider == "openai":
        if not credentials_ready:
            blockers.append("credentials_not_supplied")
        if (
            pricing is None
            or pricing.model != policy.model
            or not timedelta(0) <= observed - pricing.reviewed_at <= timedelta(days=7)
        ):
            blockers.append("model_pricing_review_required")
        else:
            if estimated_tokens + policy.max_output_tokens > pricing.model_context_tokens:
                blockers.append("model_context_window_review_required")
            exposure = (
                estimated_tokens * pricing.input_usd_per_million
                + policy.max_output_tokens * pricing.output_usd_per_million
            ) / 1_000_000
            if exposure > pricing.exposure_envelope_usd:
                blockers.append("estimated_exposure_exceeds_review")
    return CurationPreflight(
        ready=not blockers,
        blockers=tuple(blockers),
        snapshot_id=snapshot_id,
        context_revision_id=context.revision_id,
        snapshot_hash=snapshot.content_hash,
        research_policy=scope.research_policy_version,
        research_as_of=scope.as_of,
        fresh_until=scope.as_of + timedelta(hours=policy.max_research_age_hours),
        research_quality=snapshot.quality_status,
        weekend_friday=str(scope.window.friday),
        opportunities=len(snapshot.universe.opportunities),
        request_bytes=size,
        estimated_input_tokens=estimated_tokens,
        estimated_exposure_usd=exposure,
        policy=policy,
        existing_packet_id=existing_id,
        identity=identity,
    )
