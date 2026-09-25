from dataclasses import replace
from datetime import datetime, timedelta

from event_radar.curation_config import DEFAULT_CURATION_CONFIG
from event_radar.models.curation import ImportantUnknownKind
from event_radar.recommendation_config import DEFAULT_RECOMMENDATION_CONFIG
from event_radar.services.recommendation_context import (
    build_recommendation_context,
    event_candidate_id,
    recommendation_context_size,
)
from tests.curation_helpers import (
    END,
    START,
    baseline_weather,
    event,
    event_selection,
    example_user_context,
    hike_selection,
    recommendation_context,
)


def test_context_contains_window_directions_weather_and_candidates() -> None:
    context = recommendation_context()

    assert context.weekend_start == START
    assert context.weekend_end == END
    assert context.permanent_directions == ["Prefer participatory activities."]
    assert context.temporary_directions == ["A friend may join Sunday."]
    assert context.baseline_weather is not None
    assert context.baseline_weather.location_name == "Santa Rosa, CA"
    assert len(context.event_candidates) == 1
    assert len(context.hike_candidates) == 1


def test_event_description_is_bounded_and_unknown_price_stays_unknown() -> None:
    source_event = event(description="A very long semantic event description")
    context = build_recommendation_context(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        baseline_weather=baseline_weather(),
        event_selection=event_selection([source_event]),
        hike_selection=hike_selection(),
        config=replace(DEFAULT_CURATION_CONFIG, event_description_max_characters=12),
    )

    candidate = context.event_candidates[0]
    assert candidate.description is not None
    assert len(candidate.description) <= 12
    assert candidate.description.endswith("...")
    assert candidate.price_min is None
    assert candidate.price_max is None


def test_unknown_event_end_time_remains_unknown() -> None:
    source_event = event().model_copy(update={"end_time": None})

    context = build_recommendation_context(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        baseline_weather=baseline_weather(),
        event_selection=event_selection([source_event]),
        hike_selection=hike_selection(),
    )

    assert context.event_candidates[0].end_time is None


def test_hike_context_preserves_useful_facts_and_unchecked_access() -> None:
    hike = recommendation_context().hike_candidates[0]

    assert hike.candidate_id
    assert hike.distance_miles > 0
    assert hike.official_source_url is not None
    assert hike.deterministic_reasons
    assert hike.access_status == "unchecked"
    assert hike.access_warning == (
        "Access status not verified - check official source before leaving."
    )


def test_event_candidate_id_distinguishes_recurring_occurrences() -> None:
    first = event(start_time=datetime.fromisoformat("2026-08-08T18:00:00-07:00"))
    second = first.model_copy(update={"start_time": first.start_time + timedelta(days=1)})

    assert first.source_id == second.source_id
    assert event_candidate_id(first) != event_candidate_id(second)
    assert event_candidate_id(first) == event_candidate_id(first.model_copy())


def test_context_size_diagnostic_is_nonzero() -> None:
    characters, approximate_tokens = recommendation_context_size(recommendation_context())

    assert characters > 100
    assert approximate_tokens == (characters + 3) // 4


def test_event_recall_and_context_caps_are_twenty_eight() -> None:
    events = [event(title=f"Candidate {index}") for index in range(30)]

    context = build_recommendation_context(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        baseline_weather=baseline_weather(),
        event_selection=event_selection(events),
        hike_selection=hike_selection(),
    )

    assert DEFAULT_RECOMMENDATION_CONFIG.maximum_candidates == 28
    assert DEFAULT_CURATION_CONFIG.maximum_event_candidates == 28
    assert len(context.event_candidates) == 28


def test_context_preserves_structured_event_price_details() -> None:
    source_event = event(
        price=__import__("decimal").Decimal("25"),
        price_details="$25-$50",
    ).model_copy(update={"price_max": __import__("decimal").Decimal("50")})

    context = build_recommendation_context(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=[],
        temporary_directions=[],
        baseline_weather=baseline_weather(),
        event_selection=event_selection([source_event]),
        hike_selection=hike_selection(),
    )

    candidate = context.event_candidates[0]
    assert candidate.price_min == __import__("decimal").Decimal("25")
    assert candidate.price_max == __import__("decimal").Decimal("50")
    assert candidate.price_currency == "USD"
    assert candidate.price_details == "$25-$50"


def test_context_unknowns_have_unique_semantic_kinds() -> None:
    context = recommendation_context()
    kinds = [unknown.kind for unknown in context.known_unknowns]

    assert len(kinds) == len(set(kinds))
    assert ImportantUnknownKind.TRAVEL_TIME in kinds
    assert ImportantUnknownKind.EVENT_AVAILABILITY in kinds
    assert ImportantUnknownKind.HIKE_ACCESS in kinds
