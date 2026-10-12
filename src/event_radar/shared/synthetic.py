"""Explicit synthetic-only composition for worker smoke runs; no network I/O."""

from datetime import datetime, timedelta

from pydantic import HttpUrl

from event_radar.models.regional import (
    Price,
    RegionalAnalysisRequest,
    ResearchScope,
    SemanticDescriptor,
)
from event_radar.models.regional_discovery import (
    CandidateVerification,
    CoverageGap,
    DiscoveredEventCandidate,
    DiscoveryContext,
    DiscoveryEvidenceDraft,
    DiscoveryPlan,
    DiscoveryResearchResult,
    DiscoveryTask,
    DiscoveryVerificationResult,
)
from event_radar.models.regional_semantics import (
    OpportunitySemanticAnalysis,
    RegionalSemanticAnalysis,
)
from event_radar.models.token_usage import TokenUsage
from event_radar.shared.collection import RegionalSourceDescriptor, RegionalSourceResult
from event_radar.shared.discovery import DiscoveryProviderResponse, materialize_discovered_event
from event_radar.shared.semantic_analysis import SemanticProviderResponse


def synthetic_usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        estimated_model_cost_usd=0,
    )


def synthetic_candidate(scope: ResearchScope, *, discovered: bool) -> DiscoveredEventCandidate:
    name = "discovered" if discovered else "collected"
    start = scope.window.start + timedelta(days=2 if discovered else 1, hours=14)
    end = start + timedelta(hours=2)
    return DiscoveredEventCandidate(
        candidate_id=f"synthetic-{name}",
        title=f"Synthetic {name} workshop",
        start=start,
        end=end,
        city="Petaluma",
        venue=f"Synthetic {name} hall",
        county="Sonoma County",
        price=Price(state="unknown", quotes=()),
        categories=("workshop",),
        unknowns=(),
        evidence=(
            DiscoveryEvidenceDraft(
                evidence_id=f"synthetic-{name}-page",
                url=HttpUrl(f"https://example.org/{name}"),
                source_name="Synthetic fixture",
                claims=("existence", "location", "time", "description"),
                summary="Synthetic workshop with guided hands-on practice.",
                confidence="high",
                occurrence_start=start,
                occurrence_end=end,
            ),
        ),
    )


class SyntheticSource:
    descriptor = RegionalSourceDescriptor(
        source_id="synthetic-source",
        source_class="community_calendar",
        mechanism="catalog",
        coverage_description="Synthetic fixtures only.",
        opportunity_kinds=("event",),
    )

    async def collect(self, scope: ResearchScope, *, observed_at: datetime) -> RegionalSourceResult:
        return RegionalSourceResult(
            opportunities=(
                materialize_discovered_event(
                    scope,
                    synthetic_candidate(scope, discovered=False),
                    observed_at=observed_at,
                    source_id=self.descriptor.source_id,
                ),
            )
        )


class SyntheticSemantics:
    model_id = "synthetic-semantics"

    async def analyze(
        self,
        request: RegionalAnalysisRequest,
        *,
        correction: str | None = None,
    ) -> SemanticProviderResponse:
        return SemanticProviderResponse(
            analysis=RegionalSemanticAnalysis(
                opportunities=tuple(
                    OpportunitySemanticAnalysis(
                        opportunity_id=item.opportunity_id,
                        descriptors=(
                            SemanticDescriptor(
                                kind="participation",
                                description="Guided hands-on practice.",
                                evidence_ids=(item.evidence[0].evidence_id,),
                                confidence="high",
                            ),
                        ),
                    )
                    for item in request.opportunities
                )
            ),
            usage=synthetic_usage(),
            latency_seconds=0,
        )


class SyntheticDiscovery:
    model_id = "synthetic-discovery"

    async def plan(self, context: DiscoveryContext) -> DiscoveryProviderResponse[DiscoveryPlan]:
        keep_going = len(context.existing_opportunities) < 2
        return DiscoveryProviderResponse(
            value=DiscoveryPlan(
                gaps=(
                    CoverageGap(
                        gap_id="synthetic-gap",
                        dimension="time",
                        description="Synthetic Sunday gap.",
                        rationale="Exercise bounded discovery.",
                        priority="moderate",
                    ),
                )
                if keep_going
                else (),
                tasks=(
                    DiscoveryTask(
                        task_id="synthetic-task",
                        gap_ids=("synthetic-gap",),
                        search_goal="Exercise synthetic discovery.",
                    ),
                )
                if keep_going
                else (),
                should_continue=keep_going,
                rationale="Synthetic smoke run only.",
            ),
            usage=synthetic_usage(),
            latency_seconds=0,
        )

    async def research(
        self,
        context: DiscoveryContext,
        task: DiscoveryTask,
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]:
        return DiscoveryProviderResponse(
            value=DiscoveryResearchResult(
                task_id=task.task_id,
                candidates=(synthetic_candidate(context.scope, discovered=True),),
                source_leads=(),
            ),
            usage=synthetic_usage(),
            tool_calls=0,
            latency_seconds=0,
        )

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]:
        # Independent fixture oracle; never admits arbitrary external leads.
        expected = synthetic_candidate(context.scope, discovered=True)
        return DiscoveryProviderResponse(
            value=DiscoveryVerificationResult(
                decisions=tuple(
                    CandidateVerification(
                        candidate_id=item.candidate_id,
                        verified=item == expected,
                        candidate=expected if item == expected else None,
                        rejection_code=None if item == expected else "unverifiable",
                        rationale="Compared against the independent synthetic fixture oracle.",
                    )
                    for item in candidates
                )
            ),
            usage=synthetic_usage(),
            tool_calls=0,
            latency_seconds=0,
        )
