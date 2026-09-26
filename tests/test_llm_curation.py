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
    WeekendCuration,
)
from event_radar.services.llm_curation import (
    CurationError,
    CurationReferenceError,
    OpenAICurationService,
    curate_with_fallback,
    validate_curation_references,
)
from tests.curation_helpers import recommendation_context


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
    return WeekendCuration(
        weekend_read=["Mixed event and outdoor options."],
        options=[
            option(event_id or context.event_cards[0].candidate_id, CandidateType.EVENT),
            option(context.hike_candidates[0].candidate_id, CandidateType.HIKE),
        ],
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
    assert outcome.diagnostics.total_tokens == 150


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
    duplicate = curation().model_copy(
        update={
            "options": [
                option(context.event_cards[0].candidate_id, CandidateType.EVENT),
                option(context.event_cards[0].candidate_id, CandidateType.EVENT),
            ]
        }
    )

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
