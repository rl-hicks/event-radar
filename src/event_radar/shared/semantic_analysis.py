"""Provider-neutral semantic enrichment for Regional Weekend Universe opportunities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from time import monotonic
from typing import Literal, Protocol

from event_radar.models.regional import (
    FailureCategory,
    FailureCode,
    OperationalDiagnostics,
    RegionalAnalysisRequest,
    RegionalOpportunity,
    ResearchScope,
    SemanticInputFailure,
)
from event_radar.models.regional_semantics import RegionalSemanticAnalysis
from event_radar.models.token_usage import TokenUsage, aggregate_token_usage
from event_radar.shared.failures import classify_failure, safe_usage
from event_radar.shared.semantic_input import SemanticInputPreflightError, preflight_semantic_inputs


@dataclass(frozen=True, slots=True)
class SemanticProviderResponse:
    analysis: RegionalSemanticAnalysis
    usage: TokenUsage = field(default_factory=TokenUsage)
    attempts: int = 1
    latency_seconds: float | None = None


class RegionalSemanticProvider(Protocol):
    model_id: str

    async def analyze(
        self,
        request: RegionalAnalysisRequest,
        *,
        correction: str | None = None,
    ) -> SemanticProviderResponse: ...


class SemanticProviderFailure(RuntimeError):
    """Expected bounded provider failure that can degrade one semantic batch."""

    def __init__(
        self,
        failure_code: FailureCode,
        *,
        attempts: int = 1,
        latency_seconds: float | None = None,
        usage: TokenUsage | None = None,
        category: FailureCategory | None = None,
    ) -> None:
        if type(attempts) is not int or attempts < 0:
            raise ValueError("Invalid semantic provider attempt accounting.")
        super().__init__(failure_code)
        self.failure_code = failure_code
        self.attempts = attempts
        self.latency_seconds = latency_seconds
        self.usage = safe_usage(usage or TokenUsage())
        self.failure_category: FailureCategory = category or (
            "configuration"
            if failure_code == "not_configured"
            else "response_schema"
            if failure_code == "invalid_response"
            else "provider_status"
            if failure_code == "rate_limited"
            else "provider_transport"
        )


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
    on_failure: Callable[[OperationalDiagnostics], None] | None = None,
) -> SemanticEnrichmentOutcome:
    """Enrich every opportunity without allowing the provider to rewrite factual fields."""
    started = monotonic()
    attempts = 0
    provider_calls = 0
    attempts_complete = True
    result_count = 0
    usages: list[TokenUsage] = []
    try:
        requests = preflight_semantic_inputs(scope, opportunities, batch_size=batch_size)

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
                    usage_complete=False,
                ),
                fallback_opportunity_ids=(),
            )

        enriched: dict[str, RegionalOpportunity] = {
            item.opportunity_id: item for item in opportunities
        }
        fallback_ids: list[str] = []
        usages = []
        attempts = 0
        latency_seconds = 0.0
        failure_codes: list[FailureCode] = []
        failure_categories: list[FailureCategory] = []
        successful_batches = 0

        for batch_index, request in enumerate(requests):
            offset = batch_index * batch_size
            originals = opportunities[offset : offset + batch_size]
            response: SemanticProviderResponse | None = None
            reference_error = False
            for validation_attempt in range(2):
                correction = (
                    None
                    if validation_attempt == 0
                    else (
                        "Return every supplied opportunity_id exactly once. "
                        "Use only evidence_ids belonging to that opportunity, and only "
                        "description-supporting evidence for semantic descriptors."
                    )
                )
                try:
                    provider_calls += 1
                    attempts_complete = False
                    candidate = await provider.analyze(request, correction=correction)
                except SemanticProviderFailure as exc:
                    attempts_complete = True
                    attempts += exc.attempts
                    latency_seconds += exc.latency_seconds or 0.0
                    usages.append(exc.usage)
                    failure_codes.append(exc.failure_code)
                    failure_categories.append(exc.failure_category)
                    break

                if type(candidate.attempts) is not int or candidate.attempts < 1:
                    raise ValueError("Invalid semantic provider attempt accounting.")
                attempts_complete = True
                attempts += candidate.attempts
                latency_seconds += candidate.latency_seconds or 0.0
                usages.append(safe_usage(candidate.usage))
                try:
                    validate_semantic_analysis(request, candidate.analysis)
                except SemanticReferenceError:
                    reference_error = True
                    if validation_attempt == 0:
                        continue
                    failure_codes.append("invalid_response")
                    failure_categories.append("response_schema")
                    break
                response = candidate
                reference_error = False
                break

            if response is None:
                if reference_error and not failure_codes:
                    failure_codes.append("invalid_response")
                fallback_ids.extend(item.opportunity_id for item in originals)
                continue

            enriched.update(_apply_analysis(originals, response.analysis))
            successful_batches += 1
            result_count += len(originals)

        batch_count = (len(opportunities) + batch_size - 1) // batch_size
        failed_batches = batch_count - successful_batches
        status: Literal["success", "partial", "fallback"] = (
            "success"
            if failed_batches == 0
            else "partial"
            if successful_batches > 0
            else "fallback"
        )
        complete_usage = (
            all(_usage_complete(item) for item in usages) and len(usages) == batch_count
        )
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
                failure_category=failure_categories[0] if failure_categories else None,
                provider_calls=provider_calls,
                attempts_complete=attempts_complete,
            ),
            fallback_opportunity_ids=tuple(fallback_ids),
        )

    except BaseException as error:
        code, category = classify_failure(error)
        if isinstance(error, SemanticInputPreflightError) and provider_calls == 0:
            usages = [
                TokenUsage(
                    input_tokens=0,
                    cached_input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    estimated_model_cost_usd=0,
                )
            ]
        if on_failure is not None:
            on_failure(
                _diagnostics(
                    model_id=provider.model_id,
                    status="failed",
                    attempts=attempts,
                    input_count=len(opportunities),
                    result_count=result_count,
                    latency_seconds=monotonic() - started,
                    usages=tuple(usages),
                    failure_code=code,
                    usage_complete=provider_calls == 0,
                    input_failure=(
                        error.detail if isinstance(error, SemanticInputPreflightError) else None
                    ),
                    failure_category=category,
                    provider_calls=provider_calls,
                    attempts_complete=attempts_complete,
                )
            )
        raise


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
    failure_category: FailureCategory | None = None,
    provider_calls: int | None = None,
    attempts_complete: bool = True,
    input_failure: SemanticInputFailure | None = None,
) -> OperationalDiagnostics:
    usage = safe_usage(aggregate_token_usage(usages))
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
        usage_complete=usage_complete and _usage_complete(usage),
        failure_code=failure_code,
        failure_category=failure_category,
        provider_calls=provider_calls,
        attempts_complete=attempts_complete,
        input_failure=input_failure,
    )
