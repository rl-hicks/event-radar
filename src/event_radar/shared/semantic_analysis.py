"""Provider-neutral semantic enrichment for Regional Weekend Universe opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol

from event_radar.models.regional import (
    FailureCode,
    OperationalDiagnostics,
    RegionalAnalysisRequest,
    RegionalOpportunity,
    ResearchScope,
)
from event_radar.models.regional_semantics import RegionalSemanticAnalysis
from event_radar.models.token_usage import TokenUsage, aggregate_token_usage


@dataclass(frozen=True, slots=True)
class SemanticProviderResponse:
    analysis: RegionalSemanticAnalysis
    usage: TokenUsage = field(default_factory=TokenUsage)
    attempts: int = 1
    latency_seconds: float | None = None


class RegionalSemanticProvider(Protocol):
    model_id: str

    async def analyze(self, request: RegionalAnalysisRequest) -> SemanticProviderResponse: ...


class SemanticProviderFailure(RuntimeError):
    """Expected bounded provider failure that can degrade one semantic batch."""

    def __init__(
        self,
        failure_code: FailureCode,
        *,
        attempts: int = 1,
        latency_seconds: float | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.attempts = attempts
        self.latency_seconds = latency_seconds
        self.usage = usage or TokenUsage()


class SemanticReferenceError(ValueError):
    """Structured output does not map exactly to supplied opportunities/evidence."""


@dataclass(frozen=True, slots=True)
class SemanticEnrichmentOutcome:
    opportunities: tuple[RegionalOpportunity, ...]
    diagnostics: OperationalDiagnostics
    fallback_opportunity_ids: tuple[str, ...]


async def enrich_regional_semantics(
    scope: ResearchScope,
    opportunities: tuple[RegionalOpportunity, ...],
    provider: RegionalSemanticProvider,
    *,
    batch_size: int = 25,
) -> SemanticEnrichmentOutcome:
    """Enrich every opportunity without allowing the provider to rewrite factual fields."""
    if batch_size < 1:
        raise ValueError("Semantic analysis batch size must be positive.")

    ids = tuple(item.opportunity_id for item in opportunities)
    if len(ids) != len(set(ids)):
        raise ValueError("Semantic analysis input opportunity IDs must be unique.")

    if not opportunities:
        return SemanticEnrichmentOutcome(
            opportunities=(),
            diagnostics=_diagnostics(
                model_id=provider.model_id,
                status="skipped",
                attempts=0,
                input_count=0,
                result_count=0,
                latency_seconds=0.0,
                usages=(),
                failure_code=None,
                usage_complete=True,
            ),
            fallback_opportunity_ids=(),
        )

    enriched: dict[str, RegionalOpportunity] = {
        item.opportunity_id: item for item in opportunities
    }
    fallback_ids: list[str] = []
    usages: list[TokenUsage] = []
    attempts = 0
    latency_seconds = 0.0
    failure_codes: list[FailureCode] = []
    successful_batches = 0

    for offset in range(0, len(opportunities), batch_size):
        originals = opportunities[offset : offset + batch_size]
        request = RegionalAnalysisRequest(
            scope=scope,
            opportunities=tuple(_analysis_input(item) for item in originals),
        )
        try:
            response = await provider.analyze(request)
        except SemanticProviderFailure as exc:
            attempts += exc.attempts
            latency_seconds += exc.latency_seconds or 0.0
            usages.append(exc.usage)
            failure_codes.append(exc.failure_code)
            fallback_ids.extend(item.opportunity_id for item in originals)
            continue

        attempts += response.attempts
        latency_seconds += response.latency_seconds or 0.0
        usages.append(response.usage)
        validate_semantic_analysis(request, response.analysis)
        enriched.update(_apply_analysis(originals, response.analysis))
        successful_batches += 1

    batch_count = (len(opportunities) + batch_size - 1) // batch_size
    failed_batches = batch_count - successful_batches
    status = (
        "success"
        if failed_batches == 0
        else "partial"
        if successful_batches > 0
        else "fallback"
    )
    complete_usage = all(_usage_complete(item) for item in usages) and len(usages) == batch_count
    return SemanticEnrichmentOutcome(
        opportunities=tuple(enriched[item.opportunity_id] for item in opportunities),
        diagnostics=_diagnostics(
            model_id=provider.model_id,
            status=status,
            attempts=attempts,
            input_count=len(opportunities),
            result_count=len(opportunities) - len(fallback_ids),
            latency_seconds=latency_seconds,
            usages=tuple(usages),
            failure_code=failure_codes[0] if failure_codes else None,
            usage_complete=complete_usage,
        ),
        fallback_opportunity_ids=tuple(fallback_ids),
    )


def validate_semantic_analysis(
    request: RegionalAnalysisRequest,
    analysis: RegionalSemanticAnalysis,
) -> None:
    expected = {item.opportunity_id: item for item in request.opportunities}
    actual = {item.opportunity_id: item for item in analysis.opportunities}
    if actual.keys() != expected.keys():
        raise SemanticReferenceError(
            "Semantic output must analyze every supplied opportunity exactly once."
        )

    for opportunity_id, result in actual.items():
        opportunity = expected[opportunity_id]
        evidence = {item.evidence_id: item for item in opportunity.evidence}
        descriptor_signatures: set[tuple[object, ...]] = set()
        for descriptor in result.descriptors:
            signature = (
                descriptor.kind,
                descriptor.description,
                descriptor.evidence_ids,
                descriptor.confidence,
            )
            if signature in descriptor_signatures:
                raise SemanticReferenceError("Duplicate semantic descriptors are not permitted.")
            descriptor_signatures.add(signature)
            for evidence_id in descriptor.evidence_ids:
                source = evidence.get(evidence_id)
                if source is None or "description" not in source.claims:
                    raise SemanticReferenceError(
                        "Semantic descriptors require description-supporting evidence."
                    )


def _analysis_input(opportunity: RegionalOpportunity) -> RegionalOpportunity:
    """Remove prior semantics so retries/reanalysis reason only from shared factual evidence."""
    payload = opportunity.model_dump(mode="python")
    payload["semantics"] = None
    return RegionalOpportunity.model_validate(payload)


def _apply_analysis(
    originals: tuple[RegionalOpportunity, ...],
    analysis: RegionalSemanticAnalysis,
) -> dict[str, RegionalOpportunity]:
    results = {item.opportunity_id: item for item in analysis.opportunities}
    enriched: dict[str, RegionalOpportunity] = {}
    for opportunity in originals:
        payload = opportunity.model_dump(mode="python")
        payload["semantics"] = results[opportunity.opportunity_id].descriptors
        payload["unknowns"] = tuple(
            item for item in opportunity.unknowns if item.kind != "semantic_analysis"
        )
        enriched[opportunity.opportunity_id] = RegionalOpportunity.model_validate(payload)
    return enriched


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


def _diagnostics(
    *,
    model_id: str,
    status: Literal["success", "partial", "fallback", "failed", "skipped"],
    attempts: int,
    input_count: int,
    result_count: int,
    latency_seconds: float | None,
    usages: tuple[TokenUsage, ...],
    failure_code: FailureCode | None,
    usage_complete: bool,
) -> OperationalDiagnostics:
    usage = aggregate_token_usage(usages)
    return OperationalDiagnostics(
        stage="semantic_analysis",
        model_id=model_id,
        status=status,
        attempts=attempts,
        input_count=input_count,
        result_count=result_count,
        latency_seconds=latency_seconds,
        tool_calls=0,
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
    )
