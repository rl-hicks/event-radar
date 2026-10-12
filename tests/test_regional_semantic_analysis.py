import json
from decimal import Decimal
from pathlib import Path

import pytest

from event_radar.models.regional import (
    ImportantUnknown,
    RegionalAnalysisRequest,
    RegionalOpportunity,
    RegionalWeekendUniverse,
    ResearchScope,
)
from event_radar.models.regional_semantics import (
    OpportunitySemanticAnalysis,
    RegionalSemanticAnalysis,
)
from event_radar.models.token_usage import TokenUsage
from event_radar.shared.semantic_analysis import (
    SemanticProviderFailure,
    SemanticProviderResponse,
    SemanticReferenceError,
    enrich_regional_semantics,
    validate_semantic_analysis,
)

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PROFILES = Path(__file__).parent / "fixtures/regional/synthetic_profiles.json"


def fixture_universe() -> RegionalWeekendUniverse:
    return RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text())


def with_semantic_unknowns() -> tuple[ResearchScope, tuple[RegionalOpportunity, ...]]:
    universe = fixture_universe()
    enriched = []
    for opportunity in universe.opportunities:
        payload = opportunity.model_dump(mode="python")
        payload["unknowns"] = (
            *opportunity.unknowns,
            ImportantUnknown(
                kind="semantic_analysis",
                detail="Shared semantic analysis has not run yet.",
            ),
        )
        enriched.append(opportunity.__class__.model_validate(payload))
    return universe.scope, tuple(enriched)


class FakeSemanticProvider:
    model_id = "semantic-test"

    def __init__(self, *, fail_call: int | None = None) -> None:
        self.fail_call = fail_call
        self.requests: list[RegionalAnalysisRequest] = []

    async def analyze(
        self,
        request: RegionalAnalysisRequest,
        *,
        correction: str | None = None,
    ) -> SemanticProviderResponse:
        self.requests.append(request)
        call = len(self.requests)
        if self.fail_call == call:
            raise SemanticProviderFailure(
                "timeout",
                attempts=2,
                latency_seconds=0.5,
                usage=TokenUsage(
                    input_tokens=10,
                    cached_input_tokens=0,
                    output_tokens=0,
                    total_tokens=10,
                    estimated_model_cost_usd=0.001,
                ),
            )
        results: list[OpportunitySemanticAnalysis] = []
        for opportunity in request.opportunities:
            evidence = next(item for item in opportunity.evidence if "description" in item.claims)
            results.append(
                OpportunitySemanticAnalysis(
                    opportunity_id=opportunity.opportunity_id,
                    descriptors=(
                        {
                            "kind": "experience",
                            "description": f"Evidence-grounded description of {opportunity.title}.",
                            "evidence_ids": (evidence.evidence_id,),
                            "confidence": "moderate",
                        },
                    ),
                )
            )
        return SemanticProviderResponse(
            analysis=RegionalSemanticAnalysis(opportunities=tuple(results)),
            usage=TokenUsage(
                input_tokens=10,
                cached_input_tokens=2,
                output_tokens=5,
                total_tokens=15,
                estimated_model_cost_usd=0.002,
            ),
            attempts=1,
            latency_seconds=0.25,
        )


@pytest.mark.asyncio
async def test_semantic_enrichment_changes_only_semantics_and_semantic_unknown() -> None:
    scope, opportunities = with_semantic_unknowns()
    provider = FakeSemanticProvider()

    outcome = await enrich_regional_semantics(scope, opportunities, provider)

    assert outcome.diagnostics.status == "success"
    assert outcome.fallback_opportunity_ids == ()
    assert len(provider.requests) == 1
    for before, after in zip(opportunities, outcome.opportunities, strict=True):
        assert after.title == before.title
        assert after.location == before.location
        assert after.evidence == before.evidence
        assert after.occurrences == before.occurrences
        assert after.route == before.route
        assert after.access_open == before.access_open
        assert after.categories == before.categories
        assert after.semantics is not None
        assert len(after.semantics) == 1
        assert all(item.kind != "semantic_analysis" for item in after.unknowns)
        assert {(item.kind, item.detail) for item in after.unknowns} == {
            (item.kind, item.detail) for item in before.unknowns if item.kind != "semantic_analysis"
        }


@pytest.mark.asyncio
async def test_prior_semantics_are_not_sent_back_to_provider() -> None:
    universe = fixture_universe()
    provider = FakeSemanticProvider()

    await enrich_regional_semantics(universe.scope, universe.opportunities, provider)

    request = provider.requests[0]
    assert all(item.semantics is None for item in request.opportunities)


@pytest.mark.asyncio
async def test_semantic_batches_aggregate_usage_and_attempts() -> None:
    scope, opportunities = with_semantic_unknowns()
    provider = FakeSemanticProvider()

    outcome = await enrich_regional_semantics(
        scope,
        opportunities,
        provider,
        batch_size=1,
    )

    assert len(provider.requests) == 2
    assert outcome.diagnostics.input_count == 2
    assert outcome.diagnostics.result_count == 2
    assert outcome.diagnostics.attempts == 2
    assert outcome.diagnostics.input_tokens == 20
    assert outcome.diagnostics.cached_input_tokens == 4
    assert outcome.diagnostics.output_tokens == 10
    assert outcome.diagnostics.total_tokens == 30
    assert outcome.diagnostics.estimated_model_cost_usd == Decimal("0.004")
    assert outcome.diagnostics.usage_complete is True


@pytest.mark.asyncio
async def test_expected_provider_failure_preserves_failed_batch() -> None:
    scope, opportunities = with_semantic_unknowns()
    provider = FakeSemanticProvider(fail_call=2)

    outcome = await enrich_regional_semantics(
        scope,
        opportunities,
        provider,
        batch_size=1,
    )

    assert outcome.diagnostics.status == "partial"
    assert outcome.diagnostics.failure_code == "timeout"
    assert outcome.diagnostics.result_count == 1
    assert outcome.fallback_opportunity_ids == (opportunities[1].opportunity_id,)
    assert outcome.opportunities[0].semantics is not None
    assert outcome.opportunities[1] == opportunities[1]
    assert outcome.diagnostics.usage_complete is True


@pytest.mark.asyncio
async def test_missing_or_invented_opportunity_ids_retry_then_fall_back() -> None:
    universe = fixture_universe()

    class BadProvider(FakeSemanticProvider):
        async def analyze(
            self,
            request: RegionalAnalysisRequest,
            *,
            correction: str | None = None,
        ) -> SemanticProviderResponse:
            self.requests.append(request)
            return SemanticProviderResponse(
                analysis=RegionalSemanticAnalysis(
                    opportunities=(
                        OpportunitySemanticAnalysis(
                            opportunity_id="invented-opportunity",
                            descriptors=(),
                        ),
                    )
                )
            )

    provider = BadProvider()
    outcome = await enrich_regional_semantics(
        universe.scope,
        universe.opportunities,
        provider,
    )

    assert len(provider.requests) == 2
    assert outcome.diagnostics.status == "fallback"
    assert outcome.diagnostics.failure_code == "invalid_response"
    assert outcome.fallback_opportunity_ids == tuple(
        item.opportunity_id for item in universe.opportunities
    )
    assert outcome.opportunities == universe.opportunities


def test_reference_validator_rejects_invented_opportunity_id() -> None:
    universe = fixture_universe()
    provider_request = RegionalAnalysisRequest(
        scope=universe.scope,
        opportunities=universe.opportunities,
    )
    analysis = RegionalSemanticAnalysis(
        opportunities=(
            OpportunitySemanticAnalysis(
                opportunity_id="invented-opportunity",
                descriptors=(),
            ),
        )
    )
    with pytest.raises(SemanticReferenceError, match="every supplied"):
        validate_semantic_analysis(provider_request, analysis)


@pytest.mark.asyncio
async def test_descriptor_requires_description_evidence_from_same_opportunity() -> None:
    universe = fixture_universe()

    class BadEvidenceProvider(FakeSemanticProvider):
        async def analyze(
            self,
            request: RegionalAnalysisRequest,
            *,
            correction: str | None = None,
        ) -> SemanticProviderResponse:
            self.requests.append(request)
            return SemanticProviderResponse(
                analysis=RegionalSemanticAnalysis(
                    opportunities=tuple(
                        OpportunitySemanticAnalysis(
                            opportunity_id=opportunity.opportunity_id,
                            descriptors=(
                                {
                                    "kind": "experience",
                                    "description": "Unsupported semantic claim.",
                                    "evidence_ids": (
                                        "calendar"
                                        if opportunity.opportunity_id == "community-workshop"
                                        else "park",
                                    ),
                                    "confidence": "moderate",
                                },
                            ),
                        )
                        for opportunity in request.opportunities
                    )
                )
            )

    provider = BadEvidenceProvider()
    outcome = await enrich_regional_semantics(
        universe.scope,
        universe.opportunities,
        provider,
    )

    assert len(provider.requests) == 2
    assert outcome.diagnostics.status == "fallback"
    assert outcome.diagnostics.failure_code == "invalid_response"
    assert outcome.opportunities == universe.opportunities


@pytest.mark.asyncio
async def test_semantic_input_is_identical_for_divergent_consumers() -> None:
    universe = fixture_universe()
    profiles = json.loads(PROFILES.read_text())
    assert profiles[0] != profiles[1]

    wires = []
    for _profile in profiles:
        provider = FakeSemanticProvider()
        await enrich_regional_semantics(
            universe.scope,
            universe.opportunities,
            provider,
        )
        wires.append(provider.requests[0].model_dump_json())

    assert wires[0] == wires[1]
    for profile in profiles:
        assert profile["label"] not in wires[0]
    for prohibited in (
        "user_context",
        "permanent_directions",
        "temporary_directions",
        "drive_friction_from_santa_rosa",
        "why_it_may_fit",
        "disposition",
    ):
        assert prohibited not in wires[0]


@pytest.mark.asyncio
async def test_empty_semantic_work_is_a_real_skip_without_provider_call() -> None:
    universe = fixture_universe()
    provider = FakeSemanticProvider()

    outcome = await enrich_regional_semantics(
        universe.scope,
        (),
        provider,
    )

    assert provider.requests == []
    assert outcome.opportunities == ()
    assert outcome.diagnostics.status == "skipped"
    assert outcome.diagnostics.input_count == 0
    assert outcome.diagnostics.result_count == 0
    assert outcome.diagnostics.usage_complete is False
