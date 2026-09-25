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


def option(
    candidate_id: str,
    candidate_type: CandidateType,
    *,
    role: CurationRole = CurationRole.STRONG,
) -> CuratedOption:
    return CuratedOption(
        candidate_type=candidate_type,
        candidate_id=candidate_id,
        role=role,
        why_it_survived="Distinctive enough to preserve for the final decision.",
        tradeoffs=["Actual travel time is unknown."],
        social_observation="Circulation offers plausible conversation hooks.",
        solo_observation="There is some solo friction but the activity has substance.",
        friction_observation="Known friction appears proportional to payoff.",
        schedule_observation="No known conflict.",
        confidence=CurationConfidence.MODERATE,
    )


def valid_curation(count: int = 2) -> WeekendCuration:
    context = recommendation_context()
    values = [
        option(context.event_candidates[0].candidate_id, CandidateType.EVENT),
        option(context.hike_candidates[0].candidate_id, CandidateType.HIKE),
    ][:count]
    return WeekendCuration(
        weekend_read=["The inventory mixes a social evening option and an outdoor option."],
        options=values,
        notable_near_misses=[],
        important_unknowns=["Actual travel time is unknown."],
    )


def response(
    curation: WeekendCuration | None,
    *,
    status: str = "completed",
    error: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        output_parsed=curation,
        status=status,
        error=error,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=300, total_tokens=1300),
    )


def service(fake: FakeClient) -> OpenAICurationService:
    return OpenAICurationService(
        api_key="test-key",
        client=cast(AsyncOpenAI, fake),
        prompt_path=Path("prompts/weekend_curation.md"),
    )


@pytest.mark.asyncio
async def test_valid_structured_result_uses_responses_api_without_tools() -> None:
    fake = FakeClient([response(valid_curation())])
    context = recommendation_context()

    outcome = await service(fake).curate(context)

    assert outcome.curation is not None
    assert len(outcome.curation.options) == 2
    assert outcome.diagnostics.total_tokens == 1300
    call = fake.responses.calls[0]
    assert call["model"] == "gpt-5.6"
    assert call["text_format"] is WeekendCuration
    assert call["store"] is False
    assert call["reasoning"] == {"effort": "medium"}
    assert "tools" not in call
    assert '"deterministic_score"' in cast(str, call["input"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_response",
    [
        response(None),
        response(None, status="incomplete"),
        response(None, error={"message": "provider error"}),
        ValueError("schema parse failed"),
        RuntimeError("network failed"),
    ],
)
async def test_provider_refusal_incomplete_schema_and_api_failures_fall_back(
    provider_response: object,
) -> None:
    outcome = await curate_with_fallback(
        service(FakeClient([provider_response])), recommendation_context()
    )

    assert outcome.curation is None
    assert outcome.diagnostics.success is False
    assert outcome.diagnostics.fallback_reason


@pytest.mark.asyncio
async def test_missing_key_falls_back_without_constructing_live_client() -> None:
    service_without_key = OpenAICurationService(api_key=None)

    outcome = await curate_with_fallback(service_without_key, recommendation_context())

    assert outcome.curation is None
    assert outcome.diagnostics.fallback_reason == "OpenAI API key is not configured."


def test_unknown_duplicate_wrong_type_and_too_many_options_are_rejected() -> None:
    context = recommendation_context()
    event_id = context.event_candidates[0].candidate_id

    unknown = valid_curation(0).model_copy(
        update={"options": [option("unknown", CandidateType.EVENT)]}
    )
    duplicate = valid_curation(0).model_copy(
        update={
            "options": [
                option(event_id, CandidateType.EVENT),
                option(event_id, CandidateType.EVENT),
            ]
        }
    )
    wrong_type = valid_curation(0).model_copy(
        update={"options": [option(event_id, CandidateType.HIKE)]}
    )
    too_many = WeekendCuration.model_construct(
        weekend_read=[],
        options=[option(event_id, CandidateType.EVENT)] * 19,
        notable_near_misses=[],
        important_unknowns=[],
    )

    with pytest.raises(CurationReferenceError, match="unknown"):
        validate_curation_references(context, unknown)
    with pytest.raises(CurationReferenceError, match="more than once"):
        validate_curation_references(context, duplicate)
    with pytest.raises(CurationReferenceError, match="wrong candidate type"):
        validate_curation_references(context, wrong_type)
    with pytest.raises(CurationReferenceError, match="maximum"):
        validate_curation_references(context, too_many)


@pytest.mark.asyncio
async def test_unknown_id_gets_one_corrective_retry_then_valid_result() -> None:
    invalid = valid_curation(0).model_copy(
        update={"options": [option("invented", CandidateType.EVENT)]}
    )
    fake = FakeClient([response(invalid), response(valid_curation(1))])

    outcome = await service(fake).curate(recommendation_context())

    assert outcome.curation is not None
    assert len(outcome.curation.options) == 1
    assert outcome.diagnostics.attempts == 2
    assert len(fake.responses.calls) == 2
    assert "CORRECTION REQUIRED" in cast(str, fake.responses.calls[1]["input"])


@pytest.mark.asyncio
async def test_second_semantically_invalid_result_falls_back_without_unbounded_retry() -> None:
    invalid = valid_curation(0).model_copy(
        update={"options": [option("invented", CandidateType.EVENT)]}
    )
    fake = FakeClient([response(invalid), response(invalid)])

    outcome = await curate_with_fallback(service(fake), recommendation_context())

    assert outcome.curation is None
    assert len(fake.responses.calls) == 2


@pytest.mark.asyncio
async def test_valid_result_with_fewer_than_twelve_is_accepted_and_order_is_preserved() -> None:
    context = recommendation_context()
    curation = WeekendCuration(
        weekend_read=[],
        options=[
            option(context.hike_candidates[0].candidate_id, CandidateType.HIKE),
            option(context.event_candidates[0].candidate_id, CandidateType.EVENT),
        ],
        notable_near_misses=[],
        important_unknowns=[],
    )

    outcome = await service(FakeClient([response(curation)])).curate(context)

    assert outcome.curation is not None
    assert [item.candidate_type for item in outcome.curation.options] == [
        CandidateType.HIKE,
        CandidateType.EVENT,
    ]


@pytest.mark.asyncio
async def test_curate_raises_controlled_error_without_fallback_wrapper() -> None:
    with pytest.raises(CurationError, match="API key"):
        await OpenAICurationService(api_key=None).curate(recommendation_context())
