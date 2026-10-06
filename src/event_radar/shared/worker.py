"""Standalone user-neutral WP3 -> WP4 -> WP5 -> WP4 -> WP6 orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine

from event_radar.db.regional import (
    begin_regional_research_run,
    complete_regional_research_run,
    fail_regional_research_run,
    read_current_regional_universe,
)
from event_radar.db.regional_claim import claim_regional_research
from event_radar.models.regional import (
    FailureCode,
    ImportantUnknown,
    OperationalDiagnostics,
    RegionalWeekendUniverse,
    ResearchScope,
)
from event_radar.models.regional_discovery import AdaptiveDiscoverySummary, DiscoveryBudget
from event_radar.shared.collection import SourceRegistry, collect_registered_sources
from event_radar.shared.discovery import (
    DiscoveryPlanner,
    DiscoveryResearcher,
    DiscoveryVerifier,
    run_adaptive_discovery,
)
from event_radar.shared.semantic_analysis import (
    RegionalSemanticProvider,
    enrich_regional_semantics,
)


@dataclass(frozen=True)
class ResearchBudget:
    """Explicit discovery bounds plus a deadline for the entire research path.

    Values are configuration, not owner authorization for provider spend.
    Live runtime composition requires separately supplied explicit configuration
    and owner authorization; a runtime acknowledgement cannot grant it.
    """

    discovery: DiscoveryBudget
    timeout_seconds: float
    semantic_batch_size: int = 25

    def __post_init__(self) -> None:
        if not 0 < self.timeout_seconds <= 3600:
            raise ValueError("Research timeout must be between zero and 3600 seconds.")
        if self.semantic_batch_size < 1:
            raise ValueError("Semantic batch size must be positive.")


@dataclass(frozen=True)
class WorkerDependencies:
    engine: Engine
    registry: SourceRegistry
    semantic_provider: RegionalSemanticProvider
    planner: DiscoveryPlanner
    researcher: DiscoveryResearcher
    verifier: DiscoveryVerifier


@dataclass(frozen=True)
class WorkerResult:
    status: Literal["success", "partial", "failed", "replayed", "busy"]
    run_id: UUID | None = None
    snapshot_id: UUID | None = None
    failure_code: FailureCode | None = None


async def run_regional_worker(
    scope: ResearchScope,
    dependencies: WorkerDependencies,
    *,
    budget: ResearchBudget,
    refresh: bool = False,
) -> WorkerResult:
    """Run an explicit weekend; successful same-key retries do no research.

    Refresh is an explicit new attempt, never inferred from as_of/wall clock.
    Partial/failed attempts can be retried. The current successful snapshot
    remains available throughout research and survives failed/partial refreshes.
    """
    scope = ResearchScope.model_validate(scope.model_dump())
    diagnostics: list[OperationalDiagnostics] = []
    summary: AdaptiveDiscoverySummary | None = None
    with claim_regional_research(dependencies.engine, scope.identity) as claim:
        if claim is None:
            return WorkerResult("busy")
        session = claim.session
        with session.begin():
            claim.recover_abandoned(scope.identity)
            current = read_current_regional_universe(session, scope.identity)
            if current is not None and current.quality_status == "success" and not refresh:
                return WorkerResult("replayed", snapshot_id=current.snapshot_id)
            run = begin_regional_research_run(session, scope)
            run_id = run.id

        try:
            async with asyncio.timeout(budget.timeout_seconds):
                started = monotonic()
                collection = await collect_registered_sources(
                    scope, dependencies.registry, observed_at=scope.as_of
                )
                collection_failure: FailureCode | None = next(
                    (source.failure_code for source in collection.sources if source.failure_code),
                    None,
                )
                if not collection.coverage.attempted_source_ids:
                    collection_failure = "not_configured"
                diagnostics.append(
                    OperationalDiagnostics(
                        stage="collection",
                        model_id=None,
                        status="partial" if collection_failure else "success",
                        attempts=len(collection.coverage.attempted_source_ids),
                        input_count=sum(source.result_count or 0 for source in collection.sources),
                        result_count=len(collection.opportunities),
                        latency_seconds=monotonic() - started,
                        tool_calls=0,
                        input_tokens=0,
                        cached_input_tokens=0,
                        output_tokens=0,
                        total_tokens=0,
                        estimated_model_cost_usd=Decimal(0),
                        usage_complete=True,
                        failure_code=collection_failure,
                    )
                )
                initial = await enrich_regional_semantics(
                    scope,
                    collection.opportunities,
                    dependencies.semantic_provider,
                    batch_size=budget.semantic_batch_size,
                )
                diagnostics.append(initial.diagnostics)
                discovery = await run_adaptive_discovery(
                    scope,
                    replace(collection, opportunities=initial.opportunities),
                    dependencies.planner,
                    dependencies.researcher,
                    dependencies.verifier,
                    budget=budget.discovery,
                    observed_at=scope.as_of,
                )
                diagnostics.append(discovery.diagnostics)
                summary = discovery.summary
                initial_by_id = {item.opportunity_id: item for item in initial.opportunities}
                new_ids = {item.opportunity_id for item in discovery.new_opportunities}
                needs_enrichment = tuple(
                    item
                    for item in discovery.opportunities
                    if item.opportunity_id in new_ids
                    or (
                        item.semantics is None
                        and item.opportunity_id in initial_by_id
                        and initial_by_id[item.opportunity_id].semantics is not None
                    )
                )
                incremental = await enrich_regional_semantics(
                    scope,
                    needs_enrichment,
                    dependencies.semantic_provider,
                    batch_size=budget.semantic_batch_size,
                )
                diagnostics.append(incremental.diagnostics)
                enriched = {item.opportunity_id: item for item in incremental.opportunities}
                # WP5 already merges/deduplicates against the enriched inventory,
                # preserving its preferred IDs and alternate discovery provenance.
                # Re-enrich only new candidates or merges that invalidated semantics.
                opportunities = tuple(
                    enriched.get(item.opportunity_id, item) for item in discovery.opportunities
                )
                universe = RegionalWeekendUniverse(
                    scope=scope,
                    opportunities=opportunities,
                    sources=(*collection.sources, discovery.source_coverage),
                    exclusions=discovery.exclusions,
                    diagnostics=tuple(diagnostics),
                    unknowns=(
                        ImportantUnknown(
                            kind="source_coverage",
                            detail="Bounded enabled-source and adaptive research; completeness "
                            "is unknown. Disabled/unregistered sources were not searched.",
                        ),
                    ),
                )
                failure = next(
                    (item.failure_code for item in diagnostics if item.failure_code), None
                )
                quality: Literal["success", "partial"] = "partial" if failure else "success"
                claim.check_connection()
                with session.begin():
                    snapshot = complete_regional_research_run(
                        session,
                        run_id,
                        universe,
                        quality_status=quality,
                        failure_code=failure,
                        diagnostics=tuple(diagnostics),
                        discovery_summary=summary,
                        finished_at=datetime.now(UTC),
                    )
                    snapshot_id = snapshot.id
                return WorkerResult(quality, run_id, snapshot_id, failure)
        except BaseException as exc:
            # Roll back any failed completion before marking the attempt failed.
            # Raw source/provider/DB exception text is never stored or logged.
            session.rollback()
            claim.check_connection()
            failure = "timeout" if isinstance(exc, TimeoutError) else "unavailable"
            with session.begin():
                fail_regional_research_run(
                    session,
                    run_id,
                    failure_code=failure,
                    diagnostics=tuple(diagnostics),
                    discovery_summary=summary,
                )
            if not isinstance(exc, Exception):
                raise
            return WorkerResult("failed", run_id, failure_code=failure)
