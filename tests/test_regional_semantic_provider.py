from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from event_radar.models.regional import RegionalAnalysisRequest, RegionalWeekendUniverse
from event_radar.models.regional_semantics import (
    OpportunitySemanticAnalysis,
    RegionalSemanticAnalysis,
)
from event_radar.models.token_usage import ModelTokenPricing
from event_radar.services.regional_semantic_analysis import OpenAIRegionalSemanticProvider
from event_radar.shared.semantic_analysis import SemanticProviderFailure

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PROMPT = Path("prompts/regional_semantic_analysis.md")


def request() -> RegionalAnalysisRequest:
    universe = RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text())
    opportunities = []
    for opportunity in universe.opportunities:
        payload = opportunity.model_dump(mode="python")
        payload["semantics"] = None
        opportunities.append(opportunity.__class__.model_validate(payload))
    return RegionalAnalysisRequest(
        scope=universe.scope,
        opportunities=tuple(opportunities),
    )


def analysis(value: RegionalAnalysisRequest) -> RegionalSemanticAnalysis:
    return RegionalSemanticAnalysis(
        opportunities=tuple(
            OpportunitySemanticAnalysis(
                opportunity_id=opportunity.opportunity_id,
                descriptors=(),
            )
            for opportunity in value.opportunities
        )
    )


class FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response: object) -> None:
        self.responses = FakeResponses(response)


@pytest.mark.asyncio
async def test_provider_sends_only_neutral_regional_request_and_structured_schema() -> None:
    value = request()
    response = SimpleNamespace(
        status="completed",
        error=None,
        output_parsed=analysis(value),
        usage=SimpleNamespace(
            input_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=25),
            output_tokens=20,
            total_tokens=120,
        ),
    )
    fake = FakeClient(response)
    provider = OpenAIRegionalSemanticProvider(
        api_key="synthetic-key",
        model_id="gpt-5.6",
        prompt_path=PROMPT,
        timeout_seconds=120,
        client=cast(AsyncOpenAI, fake),
        pricing=ModelTokenPricing(4.0, 0.4, 20.0),
    )

    result = await provider.analyze(value)

    assert result.analysis == analysis(value)
    assert result.usage.total_tokens == 120
    assert result.usage.cached_input_tokens == 25
    call = fake.responses.calls[0]
    assert call["model"] == "gpt-5.6"
    assert call["text_format"] is RegionalSemanticAnalysis
    assert call["reasoning"] == {"effort": "low"}
    assert call["store"] is False
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
    assert "descriptive, not recommendatory" in instructions
    assert "decide whether any person should attend" in instructions


@pytest.mark.asyncio
async def test_provider_appends_only_bounded_correction_instruction() -> None:
    value = request()
    response = SimpleNamespace(
        status="completed",
        error=None,
        output_parsed=analysis(value),
        usage=None,
    )
    fake = FakeClient(response)
    provider = OpenAIRegionalSemanticProvider(
        api_key="synthetic-key",
        model_id="gpt-5.6",
        prompt_path=PROMPT,
        timeout_seconds=120,
        client=cast(AsyncOpenAI, fake),
    )

    await provider.analyze(
        value,
        correction="Return supplied IDs exactly once.",
    )

    instructions = cast(str, fake.responses.calls[0]["instructions"])
    assert "CORRECTION REQUIRED" in instructions
    assert "Return supplied IDs exactly once." in instructions


@pytest.mark.asyncio
async def test_provider_requires_explicit_configuration_without_client() -> None:
    provider = OpenAIRegionalSemanticProvider(
        api_key=None,
        model_id="gpt-5.6",
        prompt_path=PROMPT,
        timeout_seconds=120,
    )

    with pytest.raises(SemanticProviderFailure) as caught:
        await provider.analyze(request())

    assert caught.value.failure_code == "not_configured"
    assert caught.value.attempts == 0


@pytest.mark.asyncio
async def test_incomplete_provider_response_degrades_without_raw_message() -> None:
    value = request()
    response = SimpleNamespace(
        status="incomplete",
        error=SimpleNamespace(code="synthetic-provider-detail"),
        output_parsed=None,
        usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
    )
    fake = FakeClient(response)
    provider = OpenAIRegionalSemanticProvider(
        api_key="synthetic-key",
        model_id="gpt-5.6",
        prompt_path=PROMPT,
        timeout_seconds=120,
        client=cast(AsyncOpenAI, fake),
    )

    with pytest.raises(SemanticProviderFailure) as caught:
        await provider.analyze(value)

    assert caught.value.failure_code == "invalid_response"
    assert "synthetic-provider-detail" not in str(caught.value)
    assert caught.value.usage.total_tokens == 12
