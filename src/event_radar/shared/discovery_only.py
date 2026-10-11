"""Read-only WP5 diagnostics over WP6 evidence; no collection or semantic stage."""

from dataclasses import dataclass, field
from typing import get_args
from uuid import UUID

from sqlalchemy.orm import Session

from event_radar.db.regional import read_regional_snapshot
from event_radar.models.regional import OperationalDiagnostics
from event_radar.models.regional_discovery import (
    AdaptiveDiscoverySummary,
    DiscoveredEventCandidate,
    DiscoveryBudget,
    DiscoveryContext,
    DiscoveryPlan,
    DiscoveryResearchResult,
    DiscoveryTask,
    DiscoveryVerificationResult,
    SourceClassName,
)
from event_radar.shared.collection import RegionalCollectionBatch, SourceCoverageAssessment
from event_radar.shared.discovery import (
    DiscoveryPlanner,
    DiscoveryProviderResponse,
    DiscoveryResearcher,
    DiscoveryVerifier,
    build_coverage_snapshot,
    run_adaptive_discovery,
)


@dataclass
class _Recorder:
    planner: DiscoveryPlanner
    researcher: DiscoveryResearcher
    verifier: DiscoveryVerifier
    plans: list[dict[str, object]] = field(default_factory=list)
    research: list[dict[str, object]] = field(default_factory=list)
    verification: list[dict[str, object]] = field(default_factory=list)

    model_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.model_id = self.planner.model_id

    async def plan(self, context: DiscoveryContext) -> DiscoveryProviderResponse[DiscoveryPlan]:
        result = await self.planner.plan(context)
        self.plans.append(result.value.model_dump(mode="json"))
        return result

    async def research_call(
        self, context: DiscoveryContext, task: DiscoveryTask, *, max_web_search_calls: int
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]:
        result = await self.researcher.research(
            context, task, max_web_search_calls=max_web_search_calls
        )
        self.research.append(result.value.model_dump(mode="json"))
        return result

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]:
        result = await self.verifier.verify(
            context, candidates, max_web_search_calls=max_web_search_calls
        )
        self.verification.append(result.value.model_dump(mode="json"))
        return result


@dataclass
class _ResearchRecorder:
    recorder: _Recorder

    model_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.model_id = self.recorder.researcher.model_id

    async def research(
        self, context: DiscoveryContext, task: DiscoveryTask, *, max_web_search_calls: int
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]:
        return await self.recorder.research_call(
            context, task, max_web_search_calls=max_web_search_calls
        )


@dataclass
class _VerificationRecorder:
    recorder: _Recorder
    model_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.model_id = self.recorder.verifier.model_id

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]:
        return await self.recorder.verify(
            context, candidates, max_web_search_calls=max_web_search_calls
        )


async def diagnose_snapshot(
    session: Session,
    snapshot_id: UUID,
    planner: DiscoveryPlanner,
    researcher: DiscoveryResearcher,
    verifier: DiscoveryVerifier,
    *,
    budget: DiscoveryBudget,
) -> dict[str, object]:
    """Dependency-injected diagnostic only; never create a run or mutate a snapshot."""
    stored = read_regional_snapshot(session, snapshot_id)
    if stored is None:
        raise LookupError("Snapshot unavailable; historical evidence has not been reconstructed.")
    base = stored.universe
    # WP6 stores coverage statuses, but not the WP3 registry's source-class assessment.
    # Do not infer historical source classes from today's registry or channel names.
    assessment = SourceCoverageAssessment(
        enabled_source_ids=tuple(s.source_id for s in base.sources if s.status != "not_attempted"),
        disabled_source_ids=(),
        attempted_source_ids=tuple(
            s.source_id for s in base.sources if s.status != "not_attempted"
        ),
        successful_source_ids=tuple(s.source_id for s in base.sources if s.status == "success"),
        failed_source_ids=tuple(
            s.source_id for s in base.sources if s.status in ("failed", "partial")
        ),
        known_empty_source_ids=tuple(
            s.source_id for s in base.sources if s.status == "success" and s.result_count == 0
        ),
        searched_source_classes=(),
        unsearched_source_classes=get_args(SourceClassName),
    )
    collection = RegionalCollectionBatch(
        opportunities=base.opportunities,
        exclusions=base.exclusions,
        sources=base.sources,
        coverage=assessment,
        duplicates_removed=0,
    )
    recorder = _Recorder(planner, researcher, verifier)
    report: dict[str, object] = {
        "kind": "discovery-only-diagnostic",
        "schema_version": "1",
        "weekly_worker_completed": False,
        "base_snapshot_id": str(stored.snapshot_id),
        "base_universe_id": str(stored.universe_id),
        "base_content_hash": stored.content_hash,
        "scope": base.scope.model_dump(mode="json"),
        "base_quality_status": stored.quality_status,
        "source_class_accounting": "unavailable; all classes conservatively unsearched",
        "initial_coverage": build_coverage_snapshot(
            base.scope, assessment, base.opportunities
        ).model_dump(mode="json"),
        "plans": recorder.plans,
        "research_results": recorder.research,
        "verification_results": recorder.verification,
        "new_opportunities": [],
        "new_opportunities_complete": False,
        "remaining_gaps": None,
        "remaining_gaps_complete": False,
    }

    def failed(diagnostic: OperationalDiagnostics, summary: AdaptiveDiscoverySummary) -> None:
        report.update(
            diagnostics=diagnostic.model_dump(mode="json"),
            discovery_summary=summary.model_dump(mode="json"),
            status="failed",
            incremental_opportunity_count=sum(
                wave.incremental_opportunity_count for wave in summary.waves
            ),
            remaining_gaps=recorder.plans[-1]["gaps"] if recorder.plans else None,
        )

    try:
        result = await run_adaptive_discovery(
            base.scope,
            collection,
            recorder,
            _ResearchRecorder(recorder),
            _VerificationRecorder(recorder),
            budget=budget,
            observed_at=base.scope.as_of,
            on_failure=failed,
        )
    except Exception:
        if "diagnostics" not in report:
            raise
        return report
    report.update(
        status=result.diagnostics.status,
        new_opportunities_complete=True,
        incremental_opportunity_count=len(result.new_opportunities),
        diagnostics=result.diagnostics.model_dump(mode="json"),
        discovery_summary=result.summary.model_dump(mode="json"),
        new_opportunities=[o.model_dump(mode="json") for o in result.new_opportunities],
        exclusions=[e.model_dump(mode="json") for e in result.exclusions],
        final_coverage=build_coverage_snapshot(
            base.scope, assessment, result.opportunities
        ).model_dump(mode="json"),
    )
    if recorder.plans:
        report["remaining_gaps"] = recorder.plans[-1]["gaps"]
        # Only a terminal planner assessment observes the final inventory.
        report["remaining_gaps_complete"] = result.summary.stop_reason == "planner_stopped"
    return report
