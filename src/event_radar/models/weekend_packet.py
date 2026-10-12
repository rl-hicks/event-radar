"""Private AI #3 and delivery-neutral packet contracts; no runtime configuration."""

import hashlib
import json
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from event_radar.models.product_context import ContextModel, ContextRevision
from event_radar.models.regional import (
    Identifier,
    RegionalOpportunity,
    RegionalWeekendUniverse,
)

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Count = Annotated[int, Field(strict=True, ge=0, le=10000000)]
ContextField = Literal[
    "interests",
    "activity_preferences",
    "desired_experiences",
    "objectives",
    "social_preferences",
    "participation_preferences",
    "solo_considerations",
]
Value = Literal[
    "learning", "participation", "connection", "outdoor_exploration", "entertainment", "discovery"
]
Tradeoff = Literal[
    "cost",
    "travel",
    "schedule",
    "commitment",
    "solo_practicality",
    "access",
    "availability",
    "weather",
]
Text = Annotated[str, StringConstraints(min_length=1, max_length=2400)]


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class CurationPolicy(ContextModel):
    version: Literal["personal-curation-v1"] = "personal-curation-v1"
    prompt_version: Literal["personal-curation-prompt-v1"] = "personal-curation-prompt-v1"
    provider: Literal["deterministic", "openai"] = "deterministic"
    model: Identifier = "deterministic-v1"
    configuration_version: Identifier = "default-v1"
    research_policy_version: Identifier
    max_recommendations: Annotated[int, Field(strict=True, ge=1, le=18)] = 12
    max_input_bytes: Annotated[int, Field(strict=True, ge=1000, le=1000000)] = 500000
    max_opportunities: Annotated[int, Field(strict=True, ge=1, le=2000)] = 500
    max_output_tokens: Annotated[int, Field(strict=True, ge=1000, le=16000)] = 6000
    timeout_seconds: Annotated[float, Field(gt=0, le=120, allow_inf_nan=False)] = 30
    max_research_age_hours: Annotated[int, Field(strict=True, ge=1, le=168)] = 96


class PersonalizedRequest(ContextModel):
    schema_version: Literal["personalized-request-v1"] = "personalized-request-v1"
    snapshot_id: UUID
    snapshot_hash: Digest
    research_quality: Literal["success", "partial"]
    universe: RegionalWeekendUniverse
    context: ContextRevision
    policy: CurationPolicy

    @model_validator(mode="after")
    def pinned_inputs(self) -> "PersonalizedRequest":
        if digest(self.universe.model_dump(mode="json")) != self.snapshot_hash:
            raise ValueError("Snapshot integrity mismatch.")
        if digest(self.context.context.model_dump(mode="json")) != self.context.content_hash:
            raise ValueError("Context integrity mismatch.")
        if self.universe.scope.research_policy_version != self.policy.research_policy_version:
            raise ValueError("Incompatible research.")
        if len(self.universe.opportunities) > self.policy.max_opportunities:
            raise ValueError("Input exceeds full-universe limit.")
        if len(self.model_dump_json().encode()) > self.policy.max_input_bytes:
            raise ValueError("Input exceeds full-universe byte limit.")
        return self


class ContextReference(ContextModel):
    field: ContextField
    index: Annotated[int, Field(strict=True, ge=0, le=19)]


class RecommendationJudgment(ContextModel):
    """No arbitrary provider prose or provider-generated factual event fields."""

    opportunity_id: Identifier
    evidence_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=32)]
    context_refs: Annotated[tuple[ContextReference, ...], Field(max_length=5)]
    semantic_indices: Annotated[
        tuple[Annotated[int, Field(strict=True, ge=0, le=1000)], ...], Field(max_length=8)
    ]
    expected_value: Value
    strength: Literal["consider", "recommended", "exceptional"]
    friction: Literal["needs_assessment", "within_supplied_preferences", "exceptional_tradeoff"]
    tradeoffs: Annotated[tuple[Tradeoff, ...], Field(max_length=8)]


class CurationResult(ContextModel):
    schema_version: Literal["curation-result-v1"] = "curation-result-v1"
    status: Literal["success", "partial"]
    recommendations: Annotated[tuple[RecommendationJudgment, ...], Field(max_length=18)]


class CurationUsage(ContextModel):
    provider_calls: Annotated[int, Field(strict=True, ge=0, le=1)] | None = None
    latency_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    input_tokens: Count | None = None
    cached_input_tokens: Count | None = None
    output_tokens: Count | None = None
    total_tokens: Count | None = None
    estimated_model_cost_usd: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    cost_scope: Literal["model_tokens_only"] = "model_tokens_only"
    usage_complete: bool = False

    @model_validator(mode="after")
    def consistent(self) -> "CurationUsage":
        counts = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.total_tokens,
        )
        if self.usage_complete != all(v is not None for v in counts):
            raise ValueError("Usage completeness mismatch.")
        if self.cached_input_tokens is not None and self.input_tokens is not None:
            if self.cached_input_tokens > self.input_tokens:
                raise ValueError("Invalid cache count.")
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
        ):
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError("Invalid token total.")
        return self


class PacketRecommendation(ContextModel):
    judgment: RecommendationJudgment
    rationale: Text
    # Exclusively copied from pinned, validated research, never generated by AI #3.
    facts: RegionalOpportunity
    important_unknowns: Annotated[tuple[Text, ...], Field(max_length=64)]


class WeekendPacket(ContextModel):
    schema_version: Literal["weekend-packet-v1"] = "weekend-packet-v1"
    packet_id: UUID
    user_id: UUID
    execution_id: UUID
    curation_identity: Digest
    region_id: Identifier
    weekend_friday: date
    snapshot_id: UUID
    snapshot_hash: Digest
    research_as_of: AwareDatetime
    research_quality: Literal["success", "partial"]
    context_revision_id: UUID
    context_hash: Digest
    policy: CurationPolicy
    prompt_hash: Digest
    curation_status: Literal["success", "partial"]
    status: Literal["success", "partial"]
    created_at: AwareDatetime
    recommendations: Annotated[tuple[PacketRecommendation, ...], Field(max_length=18)]
    usage: CurationUsage
