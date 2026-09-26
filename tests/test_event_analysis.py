from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from event_radar.models.event_analysis import (
    EventDisposition,
    ExperienceGroupProposal,
    ScrapedEventAnalysis,
    ScrapedEventJudgment,
    SemanticConfidence,
)
from event_radar.services.event_analysis import (
    OpenAIEventAnalysisService,
    analyze_scraped_events_with_fallback,
)
from event_radar.services.event_cards import (
    EventAnalysisReferenceError,
    build_scraped_analysis_request,
    build_scraped_event_cards,
    validate_scraped_analysis,
)
from tests.curation_helpers import END, START, event, example_user_context


def judgment(event_id: str, disposition: EventDisposition) -> ScrapedEventJudgment:
    return ScrapedEventJudgment(
        event_id=event_id,
        disposition=disposition,
        experience_summary="A real sourced experience.",
        experience_modes=["participatory"],
        interaction_architecture="Shared activity creates interaction hooks.",
        solo_viability="Reasonable solo.",
        active_value="Moderate.",
        distinctiveness="Potentially distinctive.",
        social_opportunity="Plausible, not guaranteed.",
        friction_summary="Travel time unknown.",
        schedule_observation="No known conflict.",
        uncertainties=[],
        reason_for_disposition="Evidence supports this routing choice.",
        confidence=SemanticConfidence.MODERATE,
    )


def request(count: int = 3):
    events = [
        event(
            title=f"Experience {index}",
            source_id=f"id-{index}",
            start_time=START + timedelta(hours=index + 1),
        )
        for index in range(count)
    ]
    return build_scraped_analysis_request(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        events=events,
    )


def test_every_valid_scraped_event_reaches_ai_one_without_legacy_anchors() -> None:
    value = request(35)
    payload = value.model_dump_json()

    assert len(value.events) == 35
    assert "deterministic_score" not in payload
    assert "deterministic_reasons" not in payload
    assert "activity_type" not in payload
    assert "rank" not in payload


def test_analysis_prompt_is_recall_oriented_and_biases_uncertainty_to_borderline() -> None:
    prompt = Path("prompts/event_analysis.md").read_text()

    assert "Analyze every supplied event_id exactly once" in prompt
    assert "Bias toward borderline rather than reject when uncertain" in prompt


def test_retain_and_borderline_feed_downstream_while_reject_stays_out() -> None:
    value = request()
    analysis = ScrapedEventAnalysis(
        events=[
            judgment(value.events[0].event_id, EventDisposition.RETAIN),
            judgment(value.events[1].event_id, EventDisposition.BORDERLINE),
            judgment(value.events[2].event_id, EventDisposition.REJECT),
        ],
        experience_groups=[],
    )

    cards = build_scraped_event_cards(value, analysis)

    assert {card.candidate_id for card in cards} == {
        value.events[0].event_id,
        value.events[1].event_id,
    }
    assert analysis.events[2].disposition is EventDisposition.REJECT


def test_experience_group_preserves_all_occurrence_ids_and_schedule_choices() -> None:
    value = request(2)
    judgments = [
        judgment(item.event_id, EventDisposition.RETAIN).model_copy(
            update={"experience_group_id": "same-show"}
        )
        for item in value.events
    ]
    analysis = ScrapedEventAnalysis(
        events=judgments,
        experience_groups=[
            ExperienceGroupProposal(
                group_id="same-show",
                occurrence_ids=[item.event_id for item in value.events],
                experience_summary="Two occurrences of one experience.",
            )
        ],
    )

    cards = build_scraped_event_cards(value, analysis)

    assert len(cards) == 1
    assert [item.event_id for item in cards[0].occurrences] == [
        item.event_id for item in value.events
    ]


def test_fabricated_or_missing_ids_are_rejected() -> None:
    value = request(2)
    analysis = ScrapedEventAnalysis(
        events=[
            judgment(value.events[0].event_id, EventDisposition.RETAIN),
            judgment("fabricated", EventDisposition.BORDERLINE),
        ],
        experience_groups=[],
    )

    with pytest.raises(EventAnalysisReferenceError, match="every supplied"):
        validate_scraped_analysis(value, analysis)


def test_analysis_failure_preserves_every_factual_event_as_broad_card() -> None:
    value = request(5)

    cards = build_scraped_event_cards(value, None)

    assert len(cards) == 5
    assert all(not card.semantic_analysis_available for card in cards)


class FakeResponses:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.output


class FakeClient:
    def __init__(self, output: object) -> None:
        self.responses = FakeResponses(output)


@pytest.mark.asyncio
async def test_analysis_service_validates_structured_output_and_logs_usage() -> None:
    value = request(1)
    analysis = ScrapedEventAnalysis(
        events=[judgment(value.events[0].event_id, EventDisposition.BORDERLINE)],
        experience_groups=[],
    )
    response = SimpleNamespace(
        output_parsed=analysis,
        status="completed",
        error=None,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
    )
    fake = FakeClient(response)
    service = OpenAIEventAnalysisService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/event_analysis.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, fake),
    )

    outcome = await service.analyze(value)

    assert outcome.analysis == analysis
    assert outcome.diagnostics.total_tokens == 120
    sent = cast(str, fake.responses.calls[0]["input"])
    assert "deterministic_score" not in sent


@pytest.mark.asyncio
async def test_analysis_provider_failure_degrades_without_legacy_ranking() -> None:
    class FailingResponses:
        async def parse(self, **kwargs: object) -> object:
            raise RuntimeError("network")

    service = OpenAIEventAnalysisService(
        api_key="test",
        model="gpt-5.6",
        prompt_path=Path("prompts/event_analysis.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=FailingResponses())),
    )

    outcome = await analyze_scraped_events_with_fallback(service, request(2))

    assert outcome.analysis is None
    assert outcome.diagnostics.success is False
