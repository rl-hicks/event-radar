"""AI #3 judgment and validation. Never imports or invokes regional research."""

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol, get_args

from event_radar.models.packet_validation import PROMPT as PROMPT
from event_radar.models.packet_validation import validate_result as validate_result
from event_radar.models.weekend_packet import (
    ContextField,
    ContextReference,
    CurationResult,
    CurationUsage,
    PersonalizedRequest,
    RecommendationJudgment,
)


class ProviderFailure(Exception):
    def __init__(self, code: str, usage: CurationUsage | None = None) -> None:
        super().__init__("Curation provider unavailable.")
        self.code = (
            code
            if code
            in {"timeout", "unavailable", "invalid_response", "rate_limited", "not_configured"}
            else "unavailable"
        )
        self.usage = usage or CurationUsage()


@dataclass(frozen=True)
class ProviderResponse:
    result: CurationResult
    usage: CurationUsage


class CurationProvider(Protocol):
    async def curate(self, request: PersonalizedRequest) -> ProviderResponse: ...


class DeterministicCurationProvider:
    """Offline contract fake: token overlap, not production-quality personal judgment."""

    async def curate(self, request: PersonalizedRequest) -> ProviderResponse:
        context = request.context.context
        items = []
        for opportunity in request.universe.opportunities:
            corpus = " ".join(
                [opportunity.title, *(s.description for s in opportunity.semantics or ())]
            ).lower()
            refs = []
            for field in get_args(ContextField):
                for index, value in enumerate(getattr(context, field) or ()):
                    tokens = set(re.findall(r"[a-z]{4,}", value.lower()))
                    if tokens.intersection(re.findall(r"[a-z]{4,}", corpus)):
                        refs.append(ContextReference(field=field, index=index))
            if not refs or any(value.lower() in corpus for value in context.exclusions or ()):
                continue
            semantics = opportunity.semantics or ()
            items.append(
                RecommendationJudgment(
                    opportunity_id=opportunity.opportunity_id,
                    evidence_ids=tuple(e.evidence_id for e in opportunity.evidence)[:32],
                    context_refs=tuple(refs[:5]),
                    semantic_indices=tuple(range(min(len(semantics), 8))),
                    expected_value="outdoor_exploration"
                    if opportunity.kind == "hike"
                    else "participation",
                    strength="consider",
                    friction="needs_assessment",
                    tradeoffs=("travel", "commitment", "availability"),
                )
            )
        maximum = request.policy.max_recommendations
        if context.output and context.output.maximum_recommendations:
            maximum = min(maximum, context.output.maximum_recommendations)
        return ProviderResponse(
            CurationResult(status="success", recommendations=tuple(items[:maximum])),
            CurationUsage(
                provider_calls=0,
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_model_cost_usd=0,
                usage_complete=True,
            ),
        )


async def invoke(provider: CurationProvider, request: PersonalizedRequest) -> ProviderResponse:
    # One call, no correction or retry. Provider receives a separate validated object.
    private_copy = PersonalizedRequest.model_validate_json(request.model_dump_json())
    async with asyncio.timeout(request.policy.timeout_seconds):
        return await provider.curate(private_copy)
