from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from event_radar.models.regional import Price, RegionalWeekendUniverse
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
    RegionalCoverageSnapshot,
)
from event_radar.models.token_usage import ModelTokenPricing
from event_radar.services.adaptive_regional_discovery import (
    OpenAIAdaptiveDiscoveryProvider,
)
from event_radar.shared.discovery import DiscoveryProviderFailure

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PLAN_PROMPT = Path("prompts/regional_discovery_plan.md")
RESEARCH_PROMPT = Path("prompts/regional_discovery_research.md")
VERIFY_PROMPT = Path("prompts/regional_discovery_verify.md")


def context() -> DiscoveryContext:
    universe = RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text())
    return DiscoveryContext(
        scope=universe.scope,
        coverage=RegionalCoverageSnapshot(
            searched_source_classes=("regional_calendar", "outdoor_catalog"),
            unsearched_source_classes=("community_calendar", "direct_organizer"),
            successful_source_ids=("sonoma-county-tourism", "happening-sonoma-county"),
            failed_source_ids=(),
            known_empty_source_ids=(),
            event_count=1,
            hike_count=1,
            event_counts_by_city=(),
            event_counts_by_local_day=(),
        ),
        existing_opportunities=universe.opportunities,
    )


def plan() -> DiscoveryPlan:
    return DiscoveryPlan(
        gaps=(
            CoverageGap(
                gap_id="community-gap",
                dimension="source_class",
                description="Community calendar coverage has not been searched.",
                rationale="The deterministic source set has no community-calendar adapter.",
                priority="moderate",
            ),
        ),
        tasks=(
            DiscoveryTask(
                task_id="search-community",
                gap_ids=("community-gap",),
                search_goal="Find directly evidenced public community events for the weekend.",
                target_area="Sonoma County",
            ),
        ),
        should_continue=True,
        rationale="One targeted research task can test the observed source-class gap.",
    )


def candidate() -> DiscoveredEventCandidate:
    return DiscoveredEventCandidate(
        candidate_id="candidate-one",
        title="Synthetic Sunday Event",
        start="2026-10-04T15:00:00-07:00",
        end="2026-10-04T17:00:00-07:00",
        city="Sebastopol",
        venue="Synthetic Plaza",
        county="Sonoma County",
        evidence=(
            DiscoveryEvidenceDraft(
                evidence_id="candidate-page",
                url="https://example.org/sunday-event",
                source_name="Synthetic Event Page",
                claims=("existence", "location", "time", "description"),
                summary="Synthetic direct evidence.",
                confidence="high",
                occurrence_start="2026-10-04T15:00:00-07:00",
                occurrence_end="2026-10-04T17:00:00-07:00",
            ),
        ),
        price=Price(state="unknown", quotes=()),
        categories=(),
        unknowns=(),
    )


def research_result() -> DiscoveryResearchResult:
    return DiscoveryResearchResult(
        task_id="search-community",
        candidates=(candidate(),),
        source_leads=(),
    )


def verification_result() -> DiscoveryVerificationResult:
    value = candidate()
    return DiscoveryVerificationResult(
        decisions=(
            CandidateVerification(
                candidate_id=value.candidate_id,
                verified=True,
                candidate=value,
                rejection_code=None,
                rationale="Synthetic public evidence verifies the candidate.",
            ),
        )
    )


class FakeResponses:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = FakeResponses(responses)


def response(parsed: object, *, with_search: bool) -> object:
    return SimpleNamespace(
        status="completed",
        error=None,
        output_parsed=parsed,
        output=[SimpleNamespace(type="web_search_call")] if with_search else [],
        usage=SimpleNamespace(
            input_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=20),
            output_tokens=25,
            total_tokens=125,
        ),
    )


def provider(fake: FakeClient) -> OpenAIAdaptiveDiscoveryProvider:
    return OpenAIAdaptiveDiscoveryProvider(
        api_key="synthetic-key",
        model_id="gpt-6.1-sol",
        planning_prompt_path=PLAN_PROMPT,
        research_prompt_path=RESEARCH_PROMPT,
        verification_prompt_path=VERIFY_PROMPT,
        timeout_seconds=120,
        max_web_search_calls_per_request=4,
        search_context_size="medium",
        client=cast(AsyncOpenAI, fake),
        pricing=ModelTokenPricing(2.0, 0.1, 10.0),
    )


@pytest.mark.asyncio
async def test_planner_is_neutral_structured_and_does_not_use_web_search() -> None:
    fake = FakeClient([response(plan(), with_search=False)])
    service = provider(fake)

    result = await service.plan(context())

    assert result.value == plan()
    assert result.tool_calls == 0
    call = fake.responses.calls[0]
    assert call["model"] == "gpt-6.1-sol"
    assert call["text_format"] is DiscoveryPlan
    assert call["reasoning"] == {"effort": "medium"}
    assert call["store"] is False
    assert "tools" not in call
    sent = cast(str, call["input"])
    for prohibited in (
        "user_context",
        "permanent_directions",
        "temporary_directions",
        "drive_friction_from_santa_rosa",
        "why_it_may_fit",
        "disposition",
    ):
        assert prohibited not in sent
    instructions = cast(str, call["instructions"])
    assert "coverage gap" in instructions
    assert "Do not use or infer user preferences" in instructions


@pytest.mark.asyncio
async def test_research_and_verification_use_separate_bounded_web_calls() -> None:
    fake = FakeClient(
        [
            response(research_result(), with_search=True),
            response(verification_result(), with_search=True),
        ]
    )
    service = provider(fake)
    ctx = context()
    task = plan().tasks[0]

    researched = await service.research(ctx, task, max_web_search_calls=9)
    verified = await service.verify(ctx, (candidate(),), max_web_search_calls=2)

    assert researched.value == research_result()
    assert verified.value == verification_result()
    research_call, verify_call = fake.responses.calls
    for call in (research_call, verify_call):
        assert call["tool_choice"] == "required"
        assert call["reasoning"] == {"effort": "medium"}
        assert call["store"] is False
        tools = cast(list[dict[str, object]], call["tools"])
        assert tools == [{"type": "web_search", "search_context_size": "medium"}]
    assert research_call["max_tool_calls"] == 4
    assert verify_call["max_tool_calls"] == 2
    assert research_call["text_format"] is DiscoveryResearchResult
    assert verify_call["text_format"] is DiscoveryVerificationResult
    assert "candidate-one" not in cast(str, research_call["input"])
    assert "candidate-one" in cast(str, verify_call["input"])


@pytest.mark.asyncio
async def test_provider_reports_usage_without_implicit_settings_lookup() -> None:
    fake = FakeClient([response(research_result(), with_search=True)])
    service = provider(fake)

    result = await service.research(
        context(),
        plan().tasks[0],
        max_web_search_calls=3,
    )

    assert result.usage.input_tokens == 100
    assert result.usage.cached_input_tokens == 20
    assert result.usage.output_tokens == 25
    assert result.usage.total_tokens == 125
    assert result.usage.estimated_model_cost_usd is not None


@pytest.mark.asyncio
async def test_provider_requires_explicit_configuration_without_client() -> None:
    service = OpenAIAdaptiveDiscoveryProvider(
        api_key=None,
        model_id="gpt-6.1-sol",
        planning_prompt_path=PLAN_PROMPT,
        research_prompt_path=RESEARCH_PROMPT,
        verification_prompt_path=VERIFY_PROMPT,
        timeout_seconds=120,
        max_web_search_calls_per_request=4,
    )

    with pytest.raises(DiscoveryProviderFailure) as caught:
        await service.plan(context())

    assert caught.value.failure_code == "not_configured"
    assert caught.value.attempts == 0


@pytest.mark.asyncio
async def test_web_stage_requires_an_actual_web_search_call() -> None:
    fake = FakeClient([response(research_result(), with_search=False)])
    service = provider(fake)

    with pytest.raises(DiscoveryProviderFailure) as caught:
        await service.research(
            context(),
            plan().tasks[0],
            max_web_search_calls=3,
        )

    assert caught.value.failure_code == "invalid_response"


def test_per_request_search_cap_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        OpenAIAdaptiveDiscoveryProvider(
            api_key=None,
            model_id="gpt-6.1-sol",
            planning_prompt_path=PLAN_PROMPT,
            research_prompt_path=RESEARCH_PROMPT,
            verification_prompt_path=VERIFY_PROMPT,
            timeout_seconds=120,
            max_web_search_calls_per_request=0,
        )
