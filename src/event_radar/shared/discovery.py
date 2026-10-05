"""Budgeted, provider-neutral adaptive discovery for shared regional research."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import StrictBool

from event_radar.models.regional import (
    FactualExclusion,
    FailureCode,
    ImportantUnknown,
    Location,
    Observation,
    Occurrence,
    OperationalDiagnostics,
    RegionalDiscoveryRequest,
    RegionalOpportunity,
    ResearchScope,
    SourceCoverage,
    SourceEvidence,
)
from event_radar.models.regional_discovery import (
    AdaptiveDiscoverySummary,
    CoverageCount,
    DiscoveredEventCandidate,
    DiscoveryBudget,
    DiscoveryBudgetUsage,
    DiscoveryContext,
    DiscoveryPlan,
    DiscoveryResearchResult,
    DiscoveryStopReason,
    DiscoveryTask,
    DiscoveryVerificationResult,
    DiscoveryWaveRecord,
    RegionalCoverageSnapshot,
    SourceLead,
)
from event_radar.models.token_usage import TokenUsage, aggregate_token_usage
from event_radar.shared.collection import RegionalCollectionBatch, SourceCoverageAssessment
from event_radar.shared.deduplication import deduplicate_regional_opportunities

@dataclass(frozen=True, slots=True)
class DiscoveryProviderResponse[T]:
    value: T
    usage: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: int = 0
    attempts: int = 1
    latency_seconds: float | None = None


class DiscoveryProviderFailure(RuntimeError):
    """Expected bounded model/tool failure; raw provider text is never required."""

    def __init__(
        self,
        failure_code: FailureCode,
        *,
        attempts: int = 1,
        tool_calls: int = 0,
        latency_seconds: float | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.attempts = attempts
        self.tool_calls = tool_calls
        self.latency_seconds = latency_seconds
        self.usage = usage or TokenUsage()


class DiscoveryPlanner(Protocol):
    model_id: str

    async def plan(
        self,
        context: DiscoveryContext,
    ) -> DiscoveryProviderResponse[DiscoveryPlan]: ...


class DiscoveryResearcher(Protocol):
    model_id: str

    async def research(
        self,
        context: DiscoveryContext,
        task: DiscoveryTask,
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]: ...


class DiscoveryVerifier(Protocol):
    model_id: str

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]: ...


@dataclass(frozen=True, slots=True)
class AdaptiveDiscoveryOutcome:
    opportunities: tuple[RegionalOpportunity, ...]
    new_opportunities: tuple[RegionalOpportunity, ...]
    exclusions: tuple[FactualExclusion, ...]
    source_coverage: SourceCoverage
    diagnostics: OperationalDiagnostics
    summary: AdaptiveDiscoverySummary


@dataclass(slots=True)
class _BudgetTracker:
    budget: DiscoveryBudget
    waves: int = 0
    model_calls: int = 0
    web_search_calls: int = 0
    estimated_model_cost_usd: Decimal = Decimal("0")
    usages: list[TokenUsage] = field(default_factory=list)
    latency_seconds: float = 0.0
    failure_codes: list[FailureCode] = field(default_factory=list)
    model_cost_complete: bool = True

    @property
    def remaining_web_search_calls(self) -> int:
        return max(self.budget.max_web_search_calls - self.web_search_calls, 0)

    def can_model_call(self) -> bool:
        return (
            self.model_calls < self.budget.max_model_calls
            and self.estimated_model_cost_usd < self.budget.max_model_cost_usd
        )

    def consume_response[T](self, response: DiscoveryProviderResponse[T]) -> None:
        if response.tool_calls < 0 or response.attempts < 1:
            raise ValueError("Provider response accounting must be non-negative.")
        if response.attempts > self.budget.max_model_calls - self.model_calls:
            raise ValueError("Provider exceeded the supplied model-call budget.")
        if response.tool_calls > self.remaining_web_search_calls:
            raise ValueError("Provider exceeded the supplied web-search budget.")
        self.model_calls += response.attempts
        self.web_search_calls += response.tool_calls
        self.latency_seconds += response.latency_seconds or 0.0
        self.usages.append(response.usage)
        if response.usage.estimated_model_cost_usd is not None:
            self.estimated_model_cost_usd += Decimal(str(response.usage.estimated_model_cost_usd))
        else:
            self.model_cost_complete = False

    def consume_failure(self, failure: DiscoveryProviderFailure) -> None:
        if failure.attempts > self.budget.max_model_calls - self.model_calls:
            raise ValueError("Provider failure exceeded the supplied model-call budget.")
        if failure.tool_calls > self.remaining_web_search_calls:
            raise ValueError("Provider failure exceeded the supplied web-search budget.")
        self.model_calls += failure.attempts
        self.web_search_calls += failure.tool_calls
        self.latency_seconds += failure.latency_seconds or 0.0
        self.usages.append(failure.usage)
        self.failure_codes.append(failure.failure_code)
        if failure.usage.estimated_model_cost_usd is not None:
            self.estimated_model_cost_usd += Decimal(str(failure.usage.estimated_model_cost_usd))
        else:
            self.model_cost_complete = False

    def usage(self) -> DiscoveryBudgetUsage:
        return DiscoveryBudgetUsage(
            waves=self.waves,
            model_calls=self.model_calls,
            web_search_calls=self.web_search_calls,
            estimated_model_cost_usd=self.estimated_model_cost_usd,
            model_cost_complete=self.model_cost_complete,
        )


async def run_adaptive_discovery(
    scope: ResearchScope,
    collection: RegionalCollectionBatch,
    planner: DiscoveryPlanner,
    researcher: DiscoveryResearcher,
    verifier: DiscoveryVerifier,
    *,
    budget: DiscoveryBudget,
    observed_at: datetime,
    discovery_source_id: str = "adaptive-discovery",
) -> AdaptiveDiscoveryOutcome:
    """Run bounded discovery waves until coverage, yield, or budget says to stop."""
    if observed_at.utcoffset() is None:
        raise ValueError("Discovery observation time must be timezone-aware.")
    if observed_at.astimezone(UTC) > scope.as_of.astimezone(UTC):
        raise ValueError("Discovery observation cannot follow the scope as_of cutoff.")

    current = collection.opportunities
    initial_ids = {item.opportunity_id for item in current}
    exclusions = list(collection.exclusions)
    source_leads: dict[str, SourceLead] = {}
    wave_records: list[DiscoveryWaveRecord] = []
    tracker = _BudgetTracker(budget)
    verified_total = 0
    provider_failure_seen = False
    stop_reason: DiscoveryStopReason = "max_waves"

    for wave in range(1, budget.max_waves + 1):
        if not tracker.can_model_call():
            stop_reason = "budget_exhausted"
            break

        context = DiscoveryContext(
            scope=scope,
            coverage=build_coverage_snapshot(scope, collection.coverage, current),
            existing_opportunities=current,
        )
        try:
            planned = await planner.plan(context)
        except DiscoveryProviderFailure as exc:
            tracker.consume_failure(exc)
            provider_failure_seen = True
            stop_reason = "provider_failure"
            break
        tracker.consume_response(planned)
        plan = planned.value

        if not plan.should_continue:
            stop_reason = "planner_stopped"
            break
        if not plan.tasks:
            stop_reason = "no_tasks"
            break

        tracker.waves = wave
        wave_candidates: list[DiscoveredEventCandidate] = []
        planned_task_ids: list[str] = []
        wave_provider_failure = False
        source_leads_before = len(source_leads)

        for task in plan.tasks:
            if not tracker.can_model_call() or tracker.remaining_web_search_calls <= 0:
                stop_reason = "budget_exhausted"
                break
            planned_task_ids.append(task.task_id)
            try:
                researched = await researcher.research(
                    context,
                    task,
                    max_web_search_calls=tracker.remaining_web_search_calls,
                )
            except DiscoveryProviderFailure as exc:
                tracker.consume_failure(exc)
                provider_failure_seen = wave_provider_failure = True
                continue
            tracker.consume_response(researched)
            _validate_research_result(task, researched.value)
            wave_candidates.extend(researched.value.candidates)
            for lead in researched.value.source_leads:
                source_leads.setdefault(str(lead.url), lead)

        if stop_reason == "budget_exhausted" and not wave_candidates:
            break

        verified_candidates: list[DiscoveredEventCandidate] = []
        if wave_candidates:
            if not tracker.can_model_call() or tracker.remaining_web_search_calls <= 0:
                stop_reason = "budget_exhausted"
                break
            unique_candidates = _unique_candidates(tuple(wave_candidates))
            try:
                verified = await verifier.verify(
                    context,
                    unique_candidates,
                    max_web_search_calls=tracker.remaining_web_search_calls,
                )
            except DiscoveryProviderFailure as exc:
                tracker.consume_failure(exc)
                provider_failure_seen = wave_provider_failure = True
                verified = None
            if verified is not None:
                tracker.consume_response(verified)
                _validate_verification(unique_candidates, verified.value)
                verified_candidates.extend(
                    decision.candidate
                    for decision in verified.value.decisions
                    if decision.verified and decision.candidate is not None
                )

        materialized: list[RegionalOpportunity] = []
        for candidate in verified_candidates:
            try:
                materialized.append(
                    materialize_discovered_event(
                        scope,
                        candidate,
                        observed_at=observed_at,
                        source_id=discovery_source_id,
                    )
                )
            except ValueError:
                provider_failure_seen = wave_provider_failure = True
                tracker.failure_codes.append("invalid_response")

        verified_total += len(materialized)
        before_ids = {item.opportunity_id for item in current}
        deduplicated = deduplicate_regional_opportunities(
            (*current, *materialized),
            preferred_opportunity_ids=frozenset(before_ids),
        )
        exclusions.extend(deduplicated.exclusions)
        current = deduplicated.opportunities
        incremental = sum(item.opportunity_id not in before_ids for item in current)
        wave_records.append(
            DiscoveryWaveRecord(
                wave=wave,
                planned_task_ids=tuple(planned_task_ids),
                verified_candidate_count=len(materialized),
                incremental_opportunity_count=incremental,
                duplicate_count=deduplicated.duplicates_removed,
                source_lead_count=len(source_leads) - source_leads_before,
            )
        )

        if incremental == 0:
            stop_reason = "no_incremental_candidates"
            break
        if wave_provider_failure:
            stop_reason = "provider_failure"
            break
        if not tracker.can_model_call():
            stop_reason = "budget_exhausted"
            break
    else:
        stop_reason = "max_waves"

    new_opportunities = tuple(item for item in current if item.opportunity_id not in initial_ids)
    usage = aggregate_token_usage(tracker.usages)
    status: Literal["success", "partial", "fallback"] = (
        "fallback"
        if provider_failure_seen and not new_opportunities
        else "partial"
        if provider_failure_seen
        else "success"
    )
    coverage_status: Literal["success", "partial", "failed"] = (
        "partial"
        if provider_failure_seen and verified_total > 0
        else "failed"
        if provider_failure_seen
        else "success"
    )
    failure_code = tracker.failure_codes[0] if tracker.failure_codes else None
    models = {planner.model_id, researcher.model_id, verifier.model_id}
    model_id = next(iter(models)) if len(models) == 1 else None
    usage_complete = bool(tracker.usages) and all(_usage_complete(item) for item in tracker.usages)

    return AdaptiveDiscoveryOutcome(
        opportunities=current,
        new_opportunities=new_opportunities,
        exclusions=tuple(exclusions),
        source_coverage=SourceCoverage(
            source_id=discovery_source_id,
            channel="complementary_discovery",
            scope="Adaptive public-web discovery for uncovered regional weekend opportunities.",
            status=coverage_status,
            observed_at=observed_at,
            result_count=verified_total if coverage_status != "failed" else None,
            failure_code=failure_code if coverage_status in ("partial", "failed") else None,
        ),
        diagnostics=OperationalDiagnostics(
            stage="complementary_discovery",
            model_id=model_id,
            status=status,
            attempts=tracker.model_calls,
            input_count=len(collection.opportunities),
            result_count=len(new_opportunities),
            latency_seconds=tracker.latency_seconds,
            tool_calls=tracker.web_search_calls,
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            estimated_model_cost_usd=(
                Decimal(str(usage.estimated_model_cost_usd))
                if usage.estimated_model_cost_usd is not None
                else None
            ),
            usage_complete=usage_complete,
            failure_code=failure_code,
        ),
        summary=AdaptiveDiscoverySummary(
            stop_reason=stop_reason,
            budget=budget,
            usage=tracker.usage(),
            waves=tuple(wave_records),
            source_leads=tuple(source_leads.values()),
        ),
    )


def build_coverage_snapshot(
    scope: ResearchScope,
    coverage: SourceCoverageAssessment,
    opportunities: tuple[RegionalOpportunity, ...],
) -> RegionalCoverageSnapshot:
    """Summarize observed coverage without claiming regional completeness."""
    event_count = sum(item.kind == "event" for item in opportunities)
    hike_count = sum(item.kind == "hike" for item in opportunities)
    city_counts: Counter[str] = Counter()
    day_counts: Counter[str] = Counter()
    timezone = ZoneInfo(scope.region.timezone)
    for opportunity in opportunities:
        if opportunity.kind != "event":
            continue
        if opportunity.location.city is not None:
            city_counts[opportunity.location.city] += 1
        for occurrence in opportunity.occurrences:
            day_counts[occurrence.start.astimezone(timezone).date().isoformat()] += 1
    return RegionalCoverageSnapshot(
        searched_source_classes=coverage.searched_source_classes,
        unsearched_source_classes=coverage.unsearched_source_classes,
        successful_source_ids=coverage.successful_source_ids,
        failed_source_ids=coverage.failed_source_ids,
        known_empty_source_ids=coverage.known_empty_source_ids,
        event_count=event_count,
        hike_count=hike_count,
        event_counts_by_city=tuple(
            CoverageCount(key=key, count=value) for key, value in sorted(city_counts.items())
        ),
        event_counts_by_local_day=tuple(
            CoverageCount(key=key, count=value) for key, value in sorted(day_counts.items())
        ),
    )


def materialize_discovered_event(
    scope: ResearchScope,
    candidate: DiscoveredEventCandidate,
    *,
    observed_at: datetime,
    source_id: str,
) -> RegionalOpportunity:
    """Convert a verified lead into the same factual contract used by WP3 sources."""
    if candidate.county != scope.region.county:
        raise ValueError("Verified discovery is outside the regional boundary.")
    if not scope.window.overlaps(candidate.start, candidate.end):
        raise ValueError("Verified discovery is outside the regional weekend.")

    evidence = tuple(
        SourceEvidence(
            evidence_id=item.evidence_id,
            source_id=source_id,
            url=item.url,
            source_record_id=candidate.candidate_id,
            observed_at=observed_at,
            published_at=None,
            claims=item.claims,
            summary=item.summary,
            confidence=item.confidence,
            occurrence_start=item.occurrence_start,
            occurrence_end=item.occurrence_end,
        )
        for item in candidate.evidence
    )
    registry = {item.evidence_id: item for item in evidence}
    required = {"existence", "location", "time", "description"}
    supported = {claim for item in evidence for claim in item.claims}
    if not required.issubset(supported):
        raise ValueError("Verified discovery is missing required evidence claims.")

    time_ids = tuple(
        item.evidence_id
        for item in evidence
        if "time" in item.claims
        and item.occurrence_start is not None
        and item.occurrence_start.astimezone(UTC) == candidate.start.astimezone(UTC)
        and (
            candidate.end is None
            or (
                item.occurrence_end is not None
                and item.occurrence_end.astimezone(UTC) == candidate.end.astimezone(UTC)
            )
        )
    )
    if not time_ids:
        raise ValueError("Verified discovery time is not directly supported by evidence.")

    location_ids = tuple(item.evidence_id for item in evidence if "location" in item.claims)
    description_ids = tuple(item.evidence_id for item in evidence if "description" in item.claims)
    for quote in candidate.price.quotes:
        if any(
            evidence_id not in registry or "price" not in registry[evidence_id].claims
            for evidence_id in quote.evidence_ids
        ):
            raise ValueError("Verified discovery price lacks price evidence.")

    opportunity_id = _stable_id(
        "discovered",
        candidate.title.casefold().strip(),
        candidate.start.astimezone(UTC).isoformat(),
        candidate.city.casefold().strip(),
        (candidate.venue or "").casefold().strip(),
    )
    occurrence_id = _stable_id("occurrence", opportunity_id)
    unknowns = tuple(candidate.unknowns)
    if not any(item.kind == "semantic_analysis" for item in unknowns):
        unknowns = (
            *unknowns,
            ImportantUnknown(
                kind="semantic_analysis",
                detail="Shared semantic enrichment has not run yet.",
            ),
        )
    location = Location(
        country_code="US",
        subdivision_code="CA",
        county=candidate.county,
        city=candidate.city,
        venue=candidate.venue,
        evidence_ids=location_ids,
    )
    opportunity = RegionalOpportunity(
        opportunity_id=opportunity_id,
        kind="event",
        title=candidate.title,
        location=location,
        evidence=evidence,
        semantics=None,
        categories=(
            Observation[tuple[str, ...]](
                state="known",
                value=tuple(sorted(set(candidate.categories))),
                evidence_ids=description_ids,
            )
            if candidate.categories
            else Observation[tuple[str, ...]](
                state="unknown",
                value=None,
                evidence_ids=(),
            )
        ),
        occurrences=(
            Occurrence(
                occurrence_id=occurrence_id,
                start=candidate.start,
                end=candidate.end,
                location=location,
                evidence_ids=time_ids,
                price=candidate.price,
                available=Observation[StrictBool](
                    state="unknown",
                    value=None,
                    evidence_ids=(),
                ),
            ),
        ),
        route=None,
        access_open=Observation[StrictBool](
            state="unknown",
            value=None,
            evidence_ids=(),
        ),
        unknowns=unknowns,
    )
    RegionalDiscoveryRequest(
        scope=scope,
        existing_opportunities=(opportunity,),
    )
    return opportunity


def _validate_research_result(
    task: DiscoveryTask,
    result: DiscoveryResearchResult,
) -> None:
    if result.task_id != task.task_id:
        raise ValueError("Discovery result task ID must match the requested task.")
    candidate_ids = tuple(item.candidate_id for item in result.candidates)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Discovery candidate IDs must be unique within a task result.")
    lead_ids = tuple(item.lead_id for item in result.source_leads)
    if len(lead_ids) != len(set(lead_ids)):
        raise ValueError("Discovery source lead IDs must be unique within a task result.")


def _validate_verification(
    candidates: tuple[DiscoveredEventCandidate, ...],
    result: DiscoveryVerificationResult,
) -> None:
    expected = {item.candidate_id for item in candidates}
    actual = {item.candidate_id for item in result.decisions}
    if expected != actual:
        raise ValueError("Verification must decide every supplied candidate exactly once.")


def _unique_candidates(
    candidates: tuple[DiscoveredEventCandidate, ...],
) -> tuple[DiscoveredEventCandidate, ...]:
    unique: dict[str, DiscoveredEventCandidate] = {}
    for candidate in candidates:
        unique.setdefault(candidate.candidate_id, candidate)
    return tuple(unique.values())


def _usage_complete(usage: TokenUsage) -> bool:
    return all(
        value is not None
        for value in (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}-{digest}"
