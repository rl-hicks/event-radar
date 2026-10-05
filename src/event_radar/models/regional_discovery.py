"""User-neutral contracts for adaptive regional discovery and verification."""

from datetime import UTC, date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    model_validator,
)

from event_radar.models.regional import (
    Claim,
    Confidence,
    Count,
    Identifier,
    ImportantUnknown,
    Price,
    RegionalOpportunity,
    ResearchScope,
    Text,
)

SourceClassName = Literal[
    "regional_calendar",
    "direct_organizer",
    "ticketing_platform",
    "community_calendar",
    "outdoor_catalog",
    "weather",
    "other",
]
GapDimension = Literal[
    "source_class",
    "geography",
    "time",
    "opportunity_type",
    "general",
]
GapPriority = Literal["high", "moderate", "low"]
DiscoveryStopReason = Literal[
    "planner_stopped",
    "no_tasks",
    "no_incremental_candidates",
    "budget_exhausted",
    "provider_failure",
    "max_waves",
]
VerificationRejection = Literal[
    "outside_region",
    "outside_window",
    "missing_evidence",
    "conflicting_time",
    "unverifiable",
    "invalid",
]


class DiscoveryContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class CoverageCount(DiscoveryContract):
    key: Text
    count: Count


class RegionalCoverageSnapshot(DiscoveryContract):
    searched_source_classes: tuple[SourceClassName, ...]
    unsearched_source_classes: tuple[SourceClassName, ...]
    successful_source_ids: tuple[Identifier, ...]
    failed_source_ids: tuple[Identifier, ...]
    known_empty_source_ids: tuple[Identifier, ...]
    event_count: Count
    hike_count: Count
    event_counts_by_city: tuple[CoverageCount, ...]
    event_counts_by_local_day: tuple[CoverageCount, ...]


class DiscoveryContext(DiscoveryContract):
    scope: ResearchScope
    coverage: RegionalCoverageSnapshot
    existing_opportunities: tuple[RegionalOpportunity, ...]


class CoverageGap(DiscoveryContract):
    gap_id: Identifier
    dimension: GapDimension
    description: Text
    rationale: Text
    priority: GapPriority


class DiscoveryTask(DiscoveryContract):
    task_id: Identifier
    gap_ids: tuple[Identifier, ...] = Field(min_length=1)
    search_goal: Text
    target_area: Text | None = None
    target_date: date | None = None
    opportunity_type: Text | None = None


class DiscoveryPlan(DiscoveryContract):
    gaps: tuple[CoverageGap, ...]
    tasks: tuple[DiscoveryTask, ...]
    should_continue: StrictBool
    rationale: Text

    @model_validator(mode="after")
    def validate_plan(self) -> "DiscoveryPlan":
        gap_ids = tuple(item.gap_id for item in self.gaps)
        task_ids = tuple(item.task_id for item in self.tasks)
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("Discovery gap IDs must be unique.")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Discovery task IDs must be unique.")
        known_gaps = set(gap_ids)
        if any(gap_id not in known_gaps for task in self.tasks for gap_id in task.gap_ids):
            raise ValueError("Discovery tasks may reference only supplied gap IDs.")
        if not self.should_continue and self.tasks:
            raise ValueError("A stopped discovery plan cannot contain research tasks.")
        return self


class DiscoveryEvidenceDraft(DiscoveryContract):
    evidence_id: Identifier
    url: HttpUrl
    source_name: Text
    claims: tuple[Claim, ...] = Field(min_length=1)
    summary: Text
    confidence: Confidence
    occurrence_start: AwareDatetime | None = None
    occurrence_end: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_time_claim(self) -> "DiscoveryEvidenceDraft":
        if len(self.claims) != len(set(self.claims)):
            raise ValueError("Discovery evidence claims must be unique.")
        has_time = "time" in self.claims
        if has_time != (self.occurrence_start is not None):
            raise ValueError("Time evidence requires an extracted occurrence start.")
        if self.occurrence_end is not None:
            if (
                self.occurrence_start is None
                or self.occurrence_end.astimezone(UTC)
                <= self.occurrence_start.astimezone(UTC)
            ):
                raise ValueError("Discovery evidence end must follow its start.")
        return self


class DiscoveredEventCandidate(DiscoveryContract):
    candidate_id: Identifier
    title: Text
    start: AwareDatetime
    end: AwareDatetime | None
    city: Text
    venue: Text | None
    county: Text
    evidence: tuple[DiscoveryEvidenceDraft, ...] = Field(min_length=1)
    price: Price
    categories: tuple[Text, ...]
    unknowns: tuple[ImportantUnknown, ...]

    @model_validator(mode="after")
    def validate_candidate(self) -> "DiscoveredEventCandidate":
        if self.end is not None and self.end.astimezone(UTC) <= self.start.astimezone(UTC):
            raise ValueError("Discovered event end must follow start.")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Discovery evidence IDs must be unique.")
        return self


class SourceLead(DiscoveryContract):
    lead_id: Identifier
    name: Text
    url: HttpUrl
    source_class: SourceClassName
    coverage_description: Text
    evidence_summary: Text


class DiscoveryResearchResult(DiscoveryContract):
    task_id: Identifier
    candidates: tuple[DiscoveredEventCandidate, ...]
    source_leads: tuple[SourceLead, ...]


class CandidateVerification(DiscoveryContract):
    candidate_id: Identifier
    verified: StrictBool
    candidate: DiscoveredEventCandidate | None
    rejection_code: VerificationRejection | None
    rationale: Text

    @model_validator(mode="after")
    def consistent_decision(self) -> "CandidateVerification":
        if self.verified:
            if self.candidate is None or self.rejection_code is not None:
                raise ValueError("Verified discovery requires a candidate and no rejection code.")
            if self.candidate.candidate_id != self.candidate_id:
                raise ValueError("Verified discovery candidate ID must match the decision.")
        elif self.candidate is not None or self.rejection_code is None:
            raise ValueError("Rejected discovery requires a rejection code and no candidate.")
        return self


class DiscoveryVerificationResult(DiscoveryContract):
    decisions: tuple[CandidateVerification, ...]

    @model_validator(mode="after")
    def unique_candidate_ids(self) -> "DiscoveryVerificationResult":
        ids = tuple(item.candidate_id for item in self.decisions)
        if len(ids) != len(set(ids)):
            raise ValueError("Verification candidate IDs must be unique.")
        return self


class DiscoveryBudget(DiscoveryContract):
    max_waves: Annotated[int, Field(ge=1, le=20, strict=True)]
    max_model_calls: Annotated[int, Field(ge=1, le=200, strict=True)]
    max_web_search_calls: Annotated[int, Field(ge=0, le=1000, strict=True)]
    max_model_cost_usd: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class DiscoveryBudgetUsage(DiscoveryContract):
    waves: Count
    model_calls: Count
    web_search_calls: Count
    estimated_model_cost_usd: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
    model_cost_complete: StrictBool


class DiscoveryWaveRecord(DiscoveryContract):
    wave: Annotated[int, Field(ge=1, strict=True)]
    planned_task_ids: tuple[Identifier, ...]
    verified_candidate_count: Count
    incremental_opportunity_count: Count
    duplicate_count: Count
    source_lead_count: Count


class AdaptiveDiscoverySummary(DiscoveryContract):
    stop_reason: DiscoveryStopReason
    budget: DiscoveryBudget
    usage: DiscoveryBudgetUsage
    waves: tuple[DiscoveryWaveRecord, ...]
    source_leads: tuple[SourceLead, ...]
