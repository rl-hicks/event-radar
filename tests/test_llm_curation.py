from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from event_radar.models.curation import (
    CandidateType,
    CuratedOption,
    CurationConfidence,
    CurationRole,
    EventCuratedOption,
    HikeCuratedOption,
    WeekendCuration,
)
from event_radar.services.llm_curation import (
    CurationError,
    CurationReferenceError,
    OpenAICurationService,
    curate_with_fallback,
    validate_curation_references,
)
from tests.curation_helpers import event, event_card, recommendation_context


class FakeResponses:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


class FakeClient:
    def __init__(self, outputs: list[object]) -> None:
        self.responses = FakeResponses(outputs)


def option(candidate_id: str, kind: CandidateType) -> CuratedOption:
    return CuratedOption(
        candidate_type=kind,
        candidate_id=candidate_id,
        role=CurationRole.STRONG,
        why_it_survived="Worth preserving.",
        tradeoffs=["Travel time is unknown."],
        social_observation="Interaction is plausible but not guaranteed.",
        solo_observation="The experience has standalone value.",
        friction_observation="Known friction is proportional.",
        schedule_observation="No known conflict.",
        confidence=CurationConfidence.MODERATE,
    )


def curation(*, event_id: str | None = None) -> WeekendCuration:
    context = recommendation_context()
    event_value = option(
        event_id or context.event_cards[0].candidate_id,
        CandidateType.EVENT,
    )
    hike_value = option(context.hike_candidates[0].candidate_id, CandidateType.HIKE)
    return WeekendCuration(
        weekend_read=["Mixed event and outdoor options."],
        event_options=[EventCuratedOption.model_validate(event_value.model_dump())],
        hike_options=[HikeCuratedOption.model_validate(hike_value.model_dump())],
        notable_near_misses=[],
        important_unknowns=[],
    )


def response(value: WeekendCuration | None, *, status: str = "completed") -> SimpleNamespace:
    return SimpleNamespace(
        output_parsed=value,
        status=status,
        error=None,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150),
    )


def service(fake: FakeClient) -> OpenAICurationService:
    return OpenAICurationService(
        api_key="test",
        client=cast(AsyncOpenAI, fake),
        prompt_path=Path("prompts/weekend_curation.md"),
    )


@pytest.mark.asyncio
async def test_final_curation_receives_unscored_combined_event_cards() -> None:
    fake = FakeClient([response(curation())])
    outcome = await service(fake).curate(recommendation_context())

    assert outcome.curation is not None
    call = fake.responses.calls[0]
    payload = cast(str, call["input"])
    assert '"event_cards"' in payload
    assert '"deterministic_score"' in payload  # hike suitability remains deterministic
    event_fragment = payload.split('"event_cards":', 1)[1].split('"hike_candidates":', 1)[0]
    assert "deterministic_score" not in event_fragment
    assert "tools" not in call
    assert '"personal_experience_context"' in payload
    assert "category_priors" not in payload
    assert outcome.diagnostics.total_tokens == 150
    assert outcome.diagnostics.retained_event_count == 1
    assert outcome.diagnostics.retained_hike_count == 1
    assert outcome.diagnostics.retained_total_count == 2


@pytest.mark.asyncio
async def test_provider_failure_falls_back_without_fabricating_curation() -> None:
    outcome = await curate_with_fallback(
        service(FakeClient([RuntimeError("network")])),
        recommendation_context(),
    )

    assert outcome.curation is None
    assert outcome.diagnostics.success is False


def test_invalid_final_references_and_duplicate_ids_are_rejected() -> None:
    context = recommendation_context()
    unknown = curation(event_id="invented")
    repeated = EventCuratedOption.model_validate(
        option(context.event_cards[0].candidate_id, CandidateType.EVENT).model_dump()
    )
    duplicate = curation().model_copy(update={"event_options": [repeated, repeated]})

    with pytest.raises(CurationReferenceError, match="unknown"):
        validate_curation_references(context, unknown)
    with pytest.raises(CurationReferenceError, match="more than once"):
        validate_curation_references(context, duplicate)


@pytest.mark.asyncio
async def test_invalid_reference_gets_one_bounded_corrective_retry() -> None:
    fake = FakeClient([response(curation(event_id="invented")), response(curation())])

    outcome = await service(fake).curate(recommendation_context())

    assert outcome.curation is not None
    assert outcome.diagnostics.attempts == 2
    assert len(fake.responses.calls) == 2
    assert "CORRECTION REQUIRED" in cast(str, fake.responses.calls[1]["input"])


@pytest.mark.asyncio
async def test_second_invalid_result_uses_fallback() -> None:
    fake = FakeClient(
        [response(curation(event_id="invented")), response(curation(event_id="invented"))]
    )

    outcome = await curate_with_fallback(service(fake), recommendation_context())

    assert outcome.curation is None
    assert len(fake.responses.calls) == 2


@pytest.mark.asyncio
async def test_missing_key_falls_back_cleanly() -> None:
    outcome = await curate_with_fallback(
        OpenAICurationService(api_key=None),
        recommendation_context(),
    )

    assert outcome.curation is None
    assert outcome.diagnostics.fallback_reason == "OpenAI API key is not configured."


@pytest.mark.asyncio
async def test_direct_missing_key_raises_controlled_error() -> None:
    with pytest.raises(CurationError, match="API key"):
        await OpenAICurationService(api_key=None).curate(recommendation_context())


def _expanded_context(event_count: int, hike_count: int):
    context = recommendation_context()
    cards = []
    for index in range(event_count):
        source = event(title=f"Event {index}", source_id=f"event-{index}")
        cards.append(event_card(source))
    hikes = [
        context.hike_candidates[0].model_copy(
            update={"candidate_id": f"hike_{index}", "name": f"Hike {index}"}
        )
        for index in range(hike_count)
    ]
    return context.model_copy(update={"event_cards": cards, "hike_candidates": hikes})


def _event_option(candidate_id: str) -> EventCuratedOption:
    return EventCuratedOption.model_validate(option(candidate_id, CandidateType.EVENT).model_dump())


def _hike_option(candidate_id: str) -> HikeCuratedOption:
    return HikeCuratedOption.model_validate(option(candidate_id, CandidateType.HIKE).model_dump())


def test_event_and_hike_collections_have_independent_flexible_limits() -> None:
    context = _expanded_context(event_count=19, hike_count=6)
    value = WeekendCuration(
        weekend_read=["Unusually rich weekend."],
        event_options=[_event_option(candidate.candidate_id) for candidate in context.event_cards],
        hike_options=[
            _hike_option(candidate.candidate_id) for candidate in context.hike_candidates
        ],
        notable_near_misses=[],
        important_unknowns=[],
    )

    validate_curation_references(context, value)

    assert len(value.event_options) == 19
    assert len(value.hike_options) == 6


def test_final_curator_allows_fewer_than_twelve_events_without_padding() -> None:
    context = _expanded_context(event_count=3, hike_count=1)
    value = WeekendCuration(
        weekend_read=["Weak event weekend."],
        event_options=[_event_option(context.event_cards[0].candidate_id)],
        hike_options=[],
        notable_near_misses=[],
        important_unknowns=[],
    )

    validate_curation_references(context, value)

    assert len(value.event_options) == 1
    assert value.hike_options == []


def test_guided_hike_from_event_pipeline_remains_an_event() -> None:
    guided = event(title="Full Moon Guided Hike", source_id="guided-hike")
    context = recommendation_context(events=[guided])
    value = WeekendCuration(
        weekend_read=["Guided hike is a scheduled event."],
        event_options=[_event_option(context.event_cards[0].candidate_id)],
        hike_options=[],
        notable_near_misses=[],
        important_unknowns=[],
    )

    validate_curation_references(context, value)

    assert value.event_options[0].candidate_type is CandidateType.EVENT
