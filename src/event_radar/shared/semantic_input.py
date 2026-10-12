"""Local validation of all semantic inputs before any provider invocation."""

import re

from pydantic import ValidationError

from event_radar.models.regional import (
    RegionalAnalysisRequest,
    RegionalOpportunity,
    ResearchScope,
    SemanticInputFailure,
    SemanticInputReason,
    SourceEvidence,
)

_RULES: dict[str, SemanticInputReason] = {
    "regional_" + reason: reason
    for reason in (
        "duplicate_opportunity_identity",
        "duplicate_occurrence_identity",
        "outside_region",
        "outside_window",
        "after_as_of",
    )
}
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,119}\Z", re.ASCII)


class SemanticInputPreflightError(ValueError):
    def __init__(self, detail: SemanticInputFailure) -> None:
        super().__init__("Semantic input preflight failed.")
        self.detail = detail


def preflight_semantic_inputs(
    scope: ResearchScope,
    opportunities: tuple[RegionalOpportunity, ...],
    *,
    batch_size: int,
) -> tuple[RegionalAnalysisRequest, ...]:
    """Revalidate factual contracts, whole-inventory invariants, then all batches.

    model_dump prevents Pydantic's trusted instance/copy bypass from hiding a
    malformed nested candidate. Full-inventory checks catch duplicates spanning
    batches. Prepared immutable requests are reused by the provider loop.
    """
    if batch_size < 1:
        raise ValueError("Semantic analysis batch size must be positive.")
    validated: list[RegionalOpportunity] = []
    for index, item in enumerate(opportunities):
        try:
            validated.append(
                RegionalOpportunity.model_validate(item.model_dump(mode="python", warnings=False))
            )
        except ValidationError as error:
            raise _failure(error, opportunities, batch_size, "opportunity", index) from None
    try:
        RegionalAnalysisRequest(scope=scope, opportunities=tuple(validated))
    except ValidationError as error:
        raise _failure(error, opportunities, batch_size, "inventory") from None

    requests: list[RegionalAnalysisRequest] = []
    for offset in range(0, len(validated), batch_size):
        prepared: list[RegionalOpportunity] = []
        for index in range(offset, min(offset + batch_size, len(validated))):
            try:
                prepared.append(_analysis_input(validated[index]))
            except ValidationError as error:
                raise _failure(error, opportunities, batch_size, "batch", index) from None
        try:
            requests.append(RegionalAnalysisRequest(scope=scope, opportunities=tuple(prepared)))
        except ValidationError as error:
            raise _failure(error, opportunities, batch_size, "batch", offset) from None
    return tuple(requests)


def _analysis_input(opportunity: RegionalOpportunity) -> RegionalOpportunity:
    """Strip previous semantics only after validating the original candidate."""
    payload = opportunity.model_dump(mode="python")
    payload["semantics"] = None
    return RegionalOpportunity.model_validate(payload)


def _failure(
    error: ValidationError,
    opportunities: tuple[RegionalOpportunity, ...],
    batch_size: int,
    phase: str,
    index: int | None = None,
) -> SemanticInputPreflightError:
    # Never copy msg/input/url/ctx wholesale. Only known inventory error codes
    # may supply IDs, and all emitted strings must pass the Identifier grammar.
    first = error.errors(include_input=False, include_url=False)[0]
    reason = _RULES.get(first["type"], "other_contract_violation")
    ids: tuple[str, ...] = ()
    if first["type"] in _RULES:
        candidates = first.get("ctx", {}).get("opportunity_ids", ())
        if isinstance(candidates, tuple):
            ids = tuple(value for value in candidates if _safe_identifier(value))[:2]
    if not ids and index is not None:
        value = opportunities[index].opportunity_id
        ids = (value,) if _safe_identifier(value) else ()
    if index is None and ids:
        index = next(
            (i for i, item in enumerate(opportunities) if item.opportunity_id == ids[0]), None
        )
    sources = sorted(
        {
            evidence.source_id
            for item in opportunities
            if item.opportunity_id in ids
            for evidence in (item.evidence if isinstance(item.evidence, tuple) else ())
            if isinstance(evidence, SourceEvidence) and _safe_identifier(evidence.source_id)
        }
    )[:8]
    return SemanticInputPreflightError(
        SemanticInputFailure.model_validate(
            {
                "phase": phase,
                "reason": reason,
                "batch_number": index // batch_size + 1 if index is not None else None,
                "opportunity_ids": ids,
                "source_ids": tuple(sources),
            }
        )
    )


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None
