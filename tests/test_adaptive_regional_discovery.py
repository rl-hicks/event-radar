import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from event_radar.models.regional import (
    Price,
    RegionalWeekendUniverse,
)
from event_radar.models.regional_discovery import (
    CandidateVerification,
    CoverageGap,
    DiscoveredEventCandidate,
    DiscoveryBudget,
    DiscoveryContext,
    DiscoveryEvidenceDraft,
    DiscoveryPlan,
    DiscoveryResearchResult,
    DiscoveryTask,
    DiscoveryVerificationResult,
    SourceLead,
)
from event_radar.models.regional_semantics import (
    OpportunitySemanticAnalysis,
    RegionalSemanticAnalysis,
)
from event_radar.models.token_usage import TokenUsage
from event_radar.shared.collection import (
    RegionalCollectionBatch,
    SourceCoverageAssessment,
)
from event_radar.shared.discovery import (
    DiscoveryProviderFailure,
    DiscoveryProviderResponse,
    build_coverage_snapshot,
    materialize_discovered_event,
    run_adaptive_discovery,
)
from event_radar.shared.semantic_analysis import (
    SemanticProviderResponse,
    enrich_regional_semantics,
)

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PACIFIC = ZoneInfo("America/Los_Angeles")


def universe() -> RegionalWeekendUniverse:
    return RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text())


def collection() -> RegionalCollectionBatch:
    value = universe()
    return RegionalCollectionBatch(
        opportunities=value.opportunities,
        exclusions=value.exclusions,
        sources=value.sources,
        coverage=SourceCoverageAssessment(
            enabled_source_ids=("sonoma-county-tourism", "happening-sonoma-county"),
            disabled_source_ids=(),
            attempted_source_ids=("sonoma-county-tourism", "happening-sonoma-county"),
            successful_source_ids=("sonoma-county-tourism", "happening-sonoma-county"),
            failed_source_ids=(),
            known_empty_source_ids=(),
            searched_source_classes=("regional_calendar",),
            unsearched_source_classes=("community_calendar", "direct_organizer"),
        ),
        duplicates_removed=0,
    )


def evidence(
    evidence_id: str,
    *,
    start: str,
    end: str,
    url: str,
) -> DiscoveryEvidenceDraft:
    return DiscoveryEvidenceDraft(
        evidence_id=evidence_id,
        url=url,
        source_name="Synthetic direct event page",
        claims=("existence", "location", "time", "description"),
        summary="Synthetic event page directly supports the event details.",
        confidence="high",
        occurrence_start=start,
        occurrence_end=end,
    )


def novel_candidate() -> DiscoveredEventCandidate:
    return DiscoveredEventCandidate(
        candidate_id="new-sunday-event",
        title="Synthetic Sunday Gathering",
        start="2026-10-04T15:00:00-07:00",
        end="2026-10-04T17:00:00-07:00",
        city="Sebastopol",
        venue="Synthetic Plaza",
        county="Sonoma County",
        evidence=(
            evidence(
                "new-page",
                start="2026-10-04T15:00:00-07:00",
                end="2026-10-04T17:00:00-07:00",
                url="https://example.org/sunday-gathering",
            ),
        ),
        price=Price(state="unknown", quotes=()),
        categories=("community",),
        unknowns=(),
    )


def duplicate_candidate() -> DiscoveredEventCandidate:
    return DiscoveredEventCandidate(
        candidate_id="duplicate-workshop",
        title="Synthetic Community Workshop",
        start="2026-10-03T14:00:00-07:00",
        end="2026-10-03T16:00:00-07:00",
        city="Petaluma",
        venue="Synthetic Community Hall",
        county="Sonoma County",
        evidence=(
            evidence(
                "duplicate-page",
                start="2026-10-03T14:00:00-07:00",
                end="2026-10-03T16:00:00-07:00",
                url="https://example.org/community-workshop",
            ),
        ),
        price=Price(state="unknown", quotes=()),
        categories=("workshop",),
        unknowns=(),
    )


def plan(*, should_continue: bool = True) -> DiscoveryPlan:
    if not should_continue:
        return DiscoveryPlan(
            gaps=(),
            tasks=(),
            should_continue=False,
            rationale="Current incremental research is sufficient for this bounded run.",
        )
    return DiscoveryPlan(
        gaps=(
            CoverageGap(
                gap_id="sunday-community-gap",
                dimension="time",
                description="Sunday regional event coverage is thin.",
                rationale="Current source inventory has limited Sunday programming.",
                priority="moderate",
            ),
        ),
        tasks=(
            DiscoveryTask(
                task_id="research-sunday-community",
                gap_ids=("sunday-community-gap",),
                search_goal="Find directly evidenced Sunday community events in Sonoma County.",
                target_area="Sonoma County",
                target_date=datetime(2026, 10, 4).date(),
                opportunity_type="scheduled public event",
            ),
        ),
        should_continue=True,
        rationale="One targeted search can test a meaningful observed coverage gap.",
    )


class Planner:
    model_id = "discovery-test"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[DiscoveryContext] = []
        self.fail = fail

    async def plan(self, context: DiscoveryContext):
        self.calls.append(context)
        if self.fail:
            raise DiscoveryProviderFailure(
                "unavailable",
                attempts=1,
                usage=TokenUsage(
                    input_tokens=10,
                    cached_input_tokens=0,
                    output_tokens=0,
                    total_tokens=10,
                    estimated_model_cost_usd=0.001,
                ),
            )
        return DiscoveryProviderResponse(
            value=plan(should_continue=len(self.calls) == 1),
            usage=TokenUsage(
                input_tokens=10,
                cached_input_tokens=2,
                output_tokens=5,
                total_tokens=15,
                estimated_model_cost_usd=0.001,
            ),
        )


class Researcher:
    model_id = "discovery-test"

    def __init__(self, candidates=None) -> None:
        self.candidates = tuple(candidates or (novel_candidate(), duplicate_candidate()))
        self.calls = []

    async def research(self, context, task, *, max_web_search_calls):
        self.calls.append((context, task, max_web_search_calls))
        return DiscoveryProviderResponse(
            value=DiscoveryResearchResult(
                task_id=task.task_id,
                candidates=self.candidates,
                source_leads=(
                    SourceLead(
                        lead_id="synthetic-calendar-lead",
                        name="Synthetic Community Calendar",
                        url="https://example.org/calendar",
                        source_class="community_calendar",
                        coverage_description="Recurring synthetic community programming.",
                        evidence_summary="The discovered event came from this recurring calendar.",
                    ),
                ),
            ),
            usage=TokenUsage(
                input_tokens=20,
                cached_input_tokens=4,
                output_tokens=8,
                total_tokens=28,
                estimated_model_cost_usd=0.002,
            ),
            tool_calls=min(2, max_web_search_calls),
        )


class Verifier:
    model_id = "discovery-test"

    def __init__(self, *, reject_all: bool = False) -> None:
        self.reject_all = reject_all
        self.calls = []

    async def verify(self, context, candidates, *, max_web_search_calls):
        self.calls.append((context, candidates, max_web_search_calls))
        decisions = tuple(
            CandidateVerification(
                candidate_id=candidate.candidate_id,
                verified=not self.reject_all,
                candidate=None if self.reject_all else candidate,
                rejection_code="unverifiable" if self.reject_all else None,
                rationale=(
                    "Synthetic verification rejected the candidate."
                    if self.reject_all
                    else "Synthetic verification confirmed the supplied evidence."
                ),
            )
            for candidate in candidates
        )
        return DiscoveryProviderResponse(
            value=DiscoveryVerificationResult(decisions=decisions),
            usage=TokenUsage(
                input_tokens=15,
                cached_input_tokens=3,
                output_tokens=6,
                total_tokens=21,
                estimated_model_cost_usd=0.002,
            ),
            tool_calls=min(1, max_web_search_calls),
        )


def budget(**overrides) -> DiscoveryBudget:
    values = {
        "max_waves": 3,
        "max_model_calls": 10,
        "max_web_search_calls": 10,
        "max_model_cost_usd": Decimal("5"),
    }
    values.update(overrides)
    return DiscoveryBudget(**values)


@pytest.mark.asyncio
async def test_adaptive_discovery_adds_new_event_merges_duplicate_and_stops_on_replan() -> None:
    value = universe()
    planner = Planner()
    researcher = Researcher()
    verifier = Verifier()

    outcome = await run_adaptive_discovery(
        value.scope,
        collection(),
        planner,
        researcher,
        verifier,
        budget=budget(),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
    )

    assert outcome.summary.stop_reason == "planner_stopped"
    assert len(outcome.opportunities) == 3
    assert len(outcome.new_opportunities) == 1
    assert outcome.new_opportunities[0].title == "Synthetic Sunday Gathering"
    assert outcome.new_opportunities[0].semantics is None
    assert any(item.kind == "semantic_analysis" for item in outcome.new_opportunities[0].unknowns)

    original = next(
        item for item in outcome.opportunities if item.opportunity_id == "community-workshop"
    )
    assert {item.source_id for item in original.evidence} >= {
        "public-feed",
        "public-calendar",
        "adaptive-discovery",
    }
    assert all(item.opportunity_id != "duplicate-workshop" for item in outcome.opportunities)

    assert outcome.summary.waves[0].incremental_opportunity_count == 1
    assert outcome.summary.waves[0].duplicate_count == 1
    assert outcome.summary.waves[0].source_lead_count == 1
    assert len(outcome.summary.source_leads) == 1
    assert outcome.summary.usage.waves == 1
    assert outcome.summary.usage.model_calls == 4
    assert outcome.summary.usage.web_search_calls == 3
    assert outcome.summary.usage.estimated_model_cost_usd == Decimal("0.006")
    assert outcome.summary.usage.model_cost_complete is True
    assert outcome.source_coverage.status == "success"
    assert outcome.source_coverage.result_count == 2
    assert outcome.diagnostics.status == "success"
    assert outcome.diagnostics.result_count == 1
    assert len(planner.calls) == 2
    assert len(researcher.calls) == 1
    assert len(verifier.calls) == 1


@pytest.mark.asyncio
async def test_duplicate_only_wave_preserves_existing_identity_and_stops() -> None:
    value = universe()
    outcome = await run_adaptive_discovery(
        value.scope,
        collection(),
        Planner(),
        Researcher(candidates=(duplicate_candidate(),)),
        Verifier(),
        budget=budget(),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
    )

    assert outcome.summary.stop_reason == "no_incremental_candidates"
    assert outcome.new_opportunities == ()
    assert {item.opportunity_id for item in outcome.opportunities} == {
        item.opportunity_id for item in value.opportunities
    }
    workshop = next(
        item for item in outcome.opportunities if item.opportunity_id == "community-workshop"
    )
    assert any(item.source_id == "adaptive-discovery" for item in workshop.evidence)


@pytest.mark.asyncio
async def test_model_call_budget_can_stop_before_any_web_research() -> None:
    value = universe()
    planner = Planner()
    researcher = Researcher()
    verifier = Verifier()

    outcome = await run_adaptive_discovery(
        value.scope,
        collection(),
        planner,
        researcher,
        verifier,
        budget=budget(max_model_calls=1),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
    )

    assert outcome.summary.stop_reason == "budget_exhausted"
    assert outcome.summary.usage.model_calls == 1
    assert outcome.summary.usage.web_search_calls == 0
    assert researcher.calls == []
    assert verifier.calls == []
    assert outcome.new_opportunities == ()


@pytest.mark.asyncio
async def test_planner_failure_is_truthful_failed_discovery_not_empty_success() -> None:
    value = universe()

    outcome = await run_adaptive_discovery(
        value.scope,
        collection(),
        Planner(fail=True),
        Researcher(),
        Verifier(),
        budget=budget(),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
    )

    assert outcome.summary.stop_reason == "provider_failure"
    assert outcome.source_coverage.status == "failed"
    assert outcome.source_coverage.result_count is None
    assert outcome.source_coverage.failure_code == "unavailable"
    assert outcome.diagnostics.status == "fallback"
    assert outcome.diagnostics.failure_code == "unavailable"
    assert outcome.new_opportunities == ()


@pytest.mark.asyncio
async def test_rejected_verification_does_not_enter_regional_inventory() -> None:
    value = universe()

    outcome = await run_adaptive_discovery(
        value.scope,
        collection(),
        Planner(),
        Researcher(candidates=(novel_candidate(),)),
        Verifier(reject_all=True),
        budget=budget(),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
    )

    assert outcome.summary.stop_reason == "no_incremental_candidates"
    assert outcome.new_opportunities == ()
    assert outcome.source_coverage.result_count == 0


def test_coverage_snapshot_reports_observed_counts_without_completeness_claim() -> None:
    value = universe()
    snapshot = build_coverage_snapshot(
        value.scope,
        collection().coverage,
        value.opportunities,
    )

    assert snapshot.event_count == 1
    assert snapshot.hike_count == 1
    assert snapshot.searched_source_classes == ("regional_calendar",)
    assert set(snapshot.unsearched_source_classes) == {
        "community_calendar",
        "direct_organizer",
    }
    assert snapshot.event_counts_by_city[0].key == "Petaluma"
    assert snapshot.event_counts_by_city[0].count == 1
    assert snapshot.event_counts_by_local_day[0].key == "2026-10-03"


def test_materializer_rejects_out_of_region_or_unsupported_time() -> None:
    value = universe()
    candidate = novel_candidate()
    outside = candidate.model_copy(update={"county": "Marin County"})
    with pytest.raises(ValueError, match="outside"):
        materialize_discovered_event(
            value.scope,
            outside,
            observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
            source_id="adaptive-discovery",
        )

    bad_evidence = candidate.evidence[0].model_copy(
        update={"occurrence_start": datetime(2026, 10, 4, 16, 0, tzinfo=PACIFIC)}
    )
    unsupported = candidate.model_copy(update={"evidence": (bad_evidence,)})
    with pytest.raises(ValueError, match="time"):
        materialize_discovered_event(
            value.scope,
            unsupported,
            observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
            source_id="adaptive-discovery",
        )


@pytest.mark.asyncio
async def test_verified_discovery_can_flow_directly_into_wp4_semantics() -> None:
    value = universe()
    discovery = await run_adaptive_discovery(
        value.scope,
        collection(),
        Planner(),
        Researcher(candidates=(novel_candidate(),)),
        Verifier(),
        budget=budget(),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
    )

    class SemanticProvider:
        model_id = "semantic-test"

        async def analyze(self, request, *, correction=None):
            opportunity = request.opportunities[0]
            evidence_id = next(
                item.evidence_id for item in opportunity.evidence if "description" in item.claims
            )
            return SemanticProviderResponse(
                analysis=RegionalSemanticAnalysis(
                    opportunities=(
                        OpportunitySemanticAnalysis(
                            opportunity_id=opportunity.opportunity_id,
                            descriptors=(
                                {
                                    "kind": "experience",
                                    "description": "A sourced shared regional experience.",
                                    "evidence_ids": (evidence_id,),
                                    "confidence": "moderate",
                                },
                            ),
                        ),
                    )
                )
            )

    semantic = await enrich_regional_semantics(
        value.scope,
        discovery.new_opportunities,
        SemanticProvider(),
    )

    assert semantic.opportunities[0].semantics is not None
    assert semantic.opportunities[0].semantics[0].kind == "experience"
