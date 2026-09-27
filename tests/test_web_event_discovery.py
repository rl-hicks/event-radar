import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from openai import AsyncOpenAI, BadRequestError
from pydantic import ValidationError

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.event_analysis import EventEvidenceClaim, SemanticConfidence
from event_radar.models.web_discovery import (
    DiscoveredEvent,
    WebDiscoveryOutcome,
    WebDiscoveryResult,
    WebEvidenceSource,
)
from event_radar.services.event_cards import (
    build_scraped_analysis_request,
    build_web_discovery_request,
    build_web_event_cards,
    event_occurrence_fact,
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
        personal_experience_context="Recall-oriented test projection.",
        permanent_directions=[],
        temporary_directions=[],
        events=[event()],
    )
    return analysis_request, build_web_discovery_request(
        analysis_request,
        personal_experience_context="Discovery-oriented test projection.",
    )


def evidence_source(
    *,
    url: str = "https://organizer.example/workshop",
    name: str = "Official event page",
    claims: list[EventEvidenceClaim] | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> WebEvidenceSource:
    claims = claims or [
        EventEvidenceClaim.EVENT_EXISTENCE,
        EventEvidenceClaim.DATE_TIME,
        EventEvidenceClaim.LOCATION,
        EventEvidenceClaim.EXPERIENCE_DESCRIPTION,
    ]
    supports_time = EventEvidenceClaim.DATE_TIME in claims
    start_time = start_time or START.replace(hour=15)
    end_time = end_time or START.replace(hour=17)
    return WebEvidenceSource(
        source_url=url,
        source_name=name,
        supported_claims=claims,
        source_confidence=SemanticConfidence.HIGH,
        evidence_summary="Official source supports its listed claims.",
        occurrence_start_time=start_time if supports_time else None,
        occurrence_end_time=end_time if supports_time else None,
    )


def discovery(
    *,
    identifier: str = "web-1",
    title: str = "Guided Art Workshop",
    evidence_sources: list[WebEvidenceSource] | None = None,
) -> DiscoveredEvent:
    return DiscoveredEvent(
        discovery_id=identifier,
        title=title,
        evidence_sources=evidence_sources or [evidence_source()],
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
    payload = discovery().model_dump()
    payload["evidence_sources"][0]["source_url"] = "not a URL"
    with pytest.raises(ValidationError):
        DiscoveredEvent.model_validate(payload)


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


def test_one_official_event_page_can_support_all_required_claims() -> None:
    _, value = request()
    found = discovery()

    _validate_discoveries(value, [found])

    assert len(found.evidence_sources) == 1


def test_calendar_time_and_operator_details_form_valid_evidence_chain() -> None:
    _, value = request()
    calendar = evidence_source(
        url="https://calendar.example/weekend-event",
        name="Regional event calendar",
        claims=[
            EventEvidenceClaim.EVENT_EXISTENCE,
            EventEvidenceClaim.DATE_TIME,
            EventEvidenceClaim.LOCATION,
        ],
    )
    operator = evidence_source(
        url="https://operator.example/activity",
        name="Official operator",
        claims=[EventEvidenceClaim.EXPERIENCE_DESCRIPTION],
    )
    found = discovery(evidence_sources=[calendar, operator])

    _validate_discoveries(value, [found])

    assert [source.source_name for source in found.evidence_sources] == [
        "Regional event calendar",
        "Official operator",
    ]


def test_generic_operator_page_without_occurrence_time_is_invalid() -> None:
    _, value = request()
    generic = evidence_source(
        claims=[
            EventEvidenceClaim.EVENT_EXISTENCE,
            EventEvidenceClaim.LOCATION,
            EventEvidenceClaim.EXPERIENCE_DESCRIPTION,
        ]
    )

    with pytest.raises(ValueError, match="date_time"):
        _validate_discoveries(value, [discovery(evidence_sources=[generic])])


def test_claimed_occurrence_must_match_source_extracted_time() -> None:
    _, value = request()
    wrong_time = evidence_source(start_time=START.replace(hour=14))

    with pytest.raises(ValueError, match="start time is not directly supported"):
        _validate_discoveries(value, [discovery(evidence_sources=[wrong_time])])


def test_multiple_evidence_sources_survive_into_web_event_card() -> None:
    calendar = evidence_source(
        url="https://calendar.example/weekend-event",
        name="Regional event calendar",
        claims=[
            EventEvidenceClaim.EVENT_EXISTENCE,
            EventEvidenceClaim.DATE_TIME,
            EventEvidenceClaim.LOCATION,
        ],
    )
    operator = evidence_source(
        url="https://operator.example/activity",
        name="Official operator",
        claims=[EventEvidenceClaim.EXPERIENCE_DESCRIPTION],
    )

    card = build_web_event_cards([discovery(evidence_sources=[calendar, operator])])[0]
    sources = card.occurrences[0].sources

    assert [source.source_name for source in sources] == [
        "Regional event calendar",
        "Official operator",
    ]
    assert sources[0].supported_claims == calendar.supported_claims
    assert sources[1].supported_claims == operator.supported_claims


def test_scraped_event_source_provenance_is_unchanged() -> None:
    source_event = event()
    occurrence = event_occurrence_fact(source_event)

    assert len(occurrence.sources) == 1
    assert occurrence.sources[0].source_name == source_event.source_name
    assert occurrence.sources[0].source_url == source_event.source_url
    assert occurrence.sources[0].supported_claims == []
    assert occurrence.sources[0].source_confidence is None


def test_serialized_web_discovery_audit_payload_preserves_evidence_chain() -> None:
    calendar = evidence_source(
        url="https://calendar.example/weekend-event",
        name="Regional event calendar",
        claims=[
            EventEvidenceClaim.EVENT_EXISTENCE,
            EventEvidenceClaim.DATE_TIME,
            EventEvidenceClaim.LOCATION,
        ],
    )
    operator = evidence_source(
        url="https://operator.example/activity",
        name="Official operator",
        claims=[EventEvidenceClaim.EXPERIENCE_DESCRIPTION],
    )
    found = discovery(evidence_sources=[calendar, operator])
    outcome = WebDiscoveryOutcome(
        result=WebDiscoveryResult(discoveries=[found]),
        valid_discoveries=[found],
        duplicates_removed=0,
        diagnostics=AIStageDiagnostics(
            stage="web_event_discovery",
            model="test",
            success=True,
            input_count=0,
            result_count=1,
            attempts=1,
            tool_calls=1,
        ),
    )

    payload = json.loads(outcome.model_dump_json())
    sources = payload["result"]["discoveries"][0]["evidence_sources"]

    assert len(sources) == 2
    assert sources[0]["supported_claims"] == [
        "event_existence",
        "date_time",
        "location",
    ]
    assert sources[0]["occurrence_start_time"] == found.start_time.isoformat()
    assert sources[1]["supported_claims"] == ["experience_description"]


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
    assert "Discovery-oriented test projection." in cast(str, fake.responses.calls[0]["input"])
    assert "category_priors" not in cast(str, fake.responses.calls[0]["input"])
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
    responses = FakeResponses(response)
    service = OpenAIWebDiscoveryService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=responses)),
    )

    outcome = await service.discover(value)

    assert (
        outcome.valid_discoveries[0].evidence_sources[0].source_url
        == "https://organizer.example/workshop"
    )
    assert outcome.diagnostics.tool_calls == 1
    assert len(responses.calls) == 1


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
