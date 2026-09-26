import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from openai import AsyncOpenAI, BadRequestError
from pydantic import ValidationError

from event_radar.models.event_analysis import SemanticConfidence
from event_radar.models.web_discovery import (
    DiscoveredEvent,
    WebDiscoveryResult,
)
from event_radar.services.event_cards import (
    build_scraped_analysis_request,
    build_web_discovery_request,
    remove_exact_web_duplicates,
)
from event_radar.services.web_event_discovery import (
    OpenAIWebDiscoveryService,
    WebDiscoveryError,
    _validate_discoveries,
    discover_events_with_fallback,
)
from tests.curation_helpers import END, START, event, example_user_context


def request():
    analysis_request = build_scraped_analysis_request(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        events=[event()],
    )
    return analysis_request, build_web_discovery_request(analysis_request)


def discovery(*, identifier: str = "web-1", title: str = "Guided Art Workshop") -> DiscoveredEvent:
    return DiscoveredEvent(
        discovery_id=identifier,
        title=title,
        source_url="https://organizer.example/workshop",
        source_name="Official organizer",
        start_time=START.replace(hour=15),
        end_time=START.replace(hour=17),
        venue="Studio",
        city="Santa Rosa",
        description_evidence="Official page lists a guided hands-on workshop.",
        why_it_may_fit="Structured participation.",
        experience_summary="A guided art workshop.",
        experience_modes=["workshop"],
        interaction_architecture="Shared instruction and tasks.",
        solo_viability="Normal solo.",
        active_value="Hands-on.",
        distinctiveness="Distinctive.",
        social_opportunity="Plausible through shared tasks.",
        friction_summary="Local.",
        schedule_observation="Open Saturday afternoon.",
        uncertainties=["Availability not verified."],
        verification_confidence=SemanticConfidence.HIGH,
        source_confidence=SemanticConfidence.HIGH,
    )


def test_structured_output_schema_avoids_unsupported_uri_format() -> None:
    schema = json.dumps(WebDiscoveryResult.model_json_schema())

    assert '"format": "uri"' not in schema
    assert '"pattern"' not in schema


def test_web_discovery_requires_evidence_and_timezone_aware_time() -> None:
    with pytest.raises(ValidationError):
        DiscoveredEvent.model_validate(
            {
                **discovery().model_dump(),
                "description_evidence": "",
            }
        )
    with pytest.raises(ValidationError):
        DiscoveredEvent.model_validate(
            {
                **discovery().model_dump(),
                "start_time": "2026-08-08T15:00:00",
            }
        )
    with pytest.raises(ValidationError):
        DiscoveredEvent.model_validate(
            {
                **discovery().model_dump(),
                "source_url": "not a URL",
            }
        )


def test_exact_scraped_duplicate_is_removed_conservatively() -> None:
    analysis_request, _ = request()
    duplicate = discovery(
        title=analysis_request.events[0].title,
    ).model_copy(
        update={
            "start_time": analysis_request.events[0].start_time,
            "end_time": analysis_request.events[0].end_time,
            "city": analysis_request.events[0].city,
            "venue": analysis_request.events[0].venue,
        }
    )

    retained, removed = remove_exact_web_duplicates(
        [duplicate],
        analysis_request.events,
        timezone="America/Los_Angeles",
    )

    assert retained == []
    assert removed == 1


def test_discovery_validation_rejects_duplicate_ids_and_out_of_window_events() -> None:
    _, value = request()
    duplicate = discovery()
    with pytest.raises(ValueError, match="unique"):
        _validate_discoveries(value, [duplicate, duplicate])

    outside = discovery().model_copy(update={"start_time": value.weekend_end})
    with pytest.raises(ValueError, match="outside"):
        _validate_discoveries(value, [outside])


class FakeResponses:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.output


@pytest.mark.asyncio
async def test_web_search_service_uses_official_tool_and_accepts_zero_results() -> None:
    _, value = request()
    response = SimpleNamespace(
        output_parsed=WebDiscoveryResult(discoveries=[]),
        status="completed",
        error=None,
        usage=SimpleNamespace(input_tokens=50, output_tokens=10, total_tokens=60),
        output=[
            SimpleNamespace(type="web_search_call"),
            SimpleNamespace(type="web_search_call"),
        ],
    )
    fake = SimpleNamespace(responses=FakeResponses(response))
    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, fake),
    )

    outcome = await service.discover(value)

    assert outcome.valid_discoveries == []
    assert outcome.diagnostics.tool_calls == 2
    tools = fake.responses.calls[0]["tools"]
    tool = cast(list[dict[str, object]], tools)[0]
    assert tool["type"] == "web_search"
    assert tool["user_location"] == {
        "type": "approximate",
        "city": value.user_context.base_location.name,
        "region": "California",
        "country": "US",
        "timezone": value.user_context.base_location.timezone,
    }
    assert fake.responses.calls[0]["tool_choice"] == "required"
    assert fake.responses.calls[0]["max_tool_calls"] == 6
    assert fake.responses.calls[0]["reasoning"] == {"effort": "low"}
    assert tool["search_context_size"] == "low"


@pytest.mark.asyncio
async def test_successful_search_preserves_source_evidence() -> None:
    _, value = request()
    found = discovery()
    response = SimpleNamespace(
        output_parsed=WebDiscoveryResult(discoveries=[found]),
        status="completed",
        error=None,
        usage=None,
        output=[SimpleNamespace(type="web_search_call")],
    )
    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=FakeResponses(response))),
    )

    outcome = await service.discover(value)

    assert outcome.valid_discoveries[0].source_url == "https://organizer.example/workshop"
    assert outcome.diagnostics.tool_calls == 1


@pytest.mark.asyncio
async def test_zero_web_search_calls_is_unsuccessful() -> None:
    _, value = request()
    response = SimpleNamespace(
        output_parsed=WebDiscoveryResult(discoveries=[]),
        status="completed",
        error=None,
        usage=None,
        output=[],
    )
    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=FakeResponses(response))),
    )

    with pytest.raises(WebDiscoveryError, match="without a web_search_call"):
        await service.discover(value)


@pytest.mark.asyncio
async def test_malformed_structured_result_fails_safely() -> None:
    _, value = request()
    response = SimpleNamespace(
        output_parsed={"discoveries": "malformed"},
        status="completed",
        error=None,
        usage=None,
        output=[SimpleNamespace(type="web_search_call")],
    )
    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=FakeResponses(response))),
    )

    outcome = await discover_events_with_fallback(service, value)

    assert outcome.diagnostics.success is False
    assert "no valid structured result" in (outcome.diagnostics.fallback_reason or "")


@pytest.mark.asyncio
async def test_bad_request_exposes_only_sanitized_provider_diagnostics() -> None:
    _, value = request()
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    error = BadRequestError(
        "SECRET API KEY AND COMPLETE PRIVATE PROMPT",
        response=response,
        body={
            "error": {
                "type": "invalid_request_error",
                "code": "invalid_json_schema",
                "param": "text.format.schema",
                "message": "Unsupported schema format.",
            }
        },
    )

    class Failing:
        async def parse(self, **kwargs: object) -> object:
            raise error

    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=Failing())),
    )

    outcome = await discover_events_with_fallback(service, value)

    diagnostics = outcome.diagnostics
    assert diagnostics.provider_status_code == 400
    assert diagnostics.provider_error_type == "invalid_request_error"
    assert diagnostics.provider_error_code == "invalid_json_schema"
    assert diagnostics.provider_error_param == "text.format.schema"
    assert diagnostics.provider_error_message == "Unsupported schema format."
    serialized = diagnostics.model_dump_json()
    assert "SECRET API KEY" not in serialized
    assert "COMPLETE PRIVATE PROMPT" not in serialized


@pytest.mark.asyncio
async def test_web_failure_degrades_gracefully_to_no_discoveries() -> None:
    _, value = request()

    class Failing:
        async def parse(self, **kwargs: object) -> object:
            raise RuntimeError("network")

    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=Failing())),
    )

    outcome = await discover_events_with_fallback(service, value)

    assert outcome.valid_discoveries == []
    assert outcome.diagnostics.success is False
