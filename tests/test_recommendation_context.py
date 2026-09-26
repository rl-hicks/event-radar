from datetime import datetime, timedelta
from decimal import Decimal

from event_radar.models.event_analysis import EventOrigin
from event_radar.services.event_cards import event_occurrence_fact
from event_radar.services.recommendation_context import (
    event_candidate_id,
    recommendation_context_size,
)
from tests.curation_helpers import PACIFIC_TIME, event, event_card, recommendation_context


def test_context_contains_unscored_event_cards_weather_directions_and_hikes() -> None:
    context = recommendation_context()

    assert context.permanent_directions == ["Prefer participatory activities."]
    assert context.temporary_directions == ["A friend may join Sunday."]
    assert context.baseline_weather is not None
    assert len(context.event_cards) == 1
    assert len(context.hike_candidates) == 1
    serialized = context.model_dump_json()
    assert "deterministic_score" not in context.event_cards[0].model_dump_json()
    assert '"origin":"scraped"' in serialized


def test_event_card_preserves_authoritative_facts_and_unknown_price() -> None:
    source = event(description="x" * 1400)
    context = recommendation_context(events=[source])
    occurrence = context.event_cards[0].occurrences[0]

    assert occurrence.event_id == event_candidate_id(source)
    assert occurrence.title == source.title
    assert occurrence.price_min is None
    assert occurrence.price_max is None
    assert len(occurrence.description or "") <= 1200
    assert occurrence.sources[0].source_name == source.source_name


def test_event_card_preserves_structured_price_and_conflict() -> None:
    source = event(
        price=Decimal("25"),
        price_details="$25 admission",
    ).model_copy(update={"price_conflict": True})
    occurrence = event_occurrence_fact(source)

    assert occurrence.price_min == Decimal("25")
    assert occurrence.price_details == "$25 admission"
    assert occurrence.price_conflict is True


def test_event_candidate_id_distinguishes_recurring_occurrences() -> None:
    first = event()
    second = first.model_copy(update={"start_time": first.start_time + timedelta(days=1)})

    assert event_candidate_id(first) != event_candidate_id(second)


def test_context_does_not_cap_valid_event_cards_at_legacy_limit() -> None:
    events = [
        event(
            title=f"Experience {index}",
            source_id=f"event-{index}",
            start_time=datetime(2026, 8, 8, 13, tzinfo=PACIFIC_TIME) + timedelta(minutes=index),
        )
        for index in range(35)
    ]
    context = recommendation_context(events=events)

    assert len(context.event_cards) == 35


def test_context_size_diagnostic_is_nonzero() -> None:
    characters, approximate_tokens = recommendation_context_size(recommendation_context())

    assert characters > 0
    assert approximate_tokens == (characters + 3) // 4


def test_hike_context_preserves_deterministic_suitability_and_unchecked_access() -> None:
    hike = recommendation_context().hike_candidates[0]

    assert hike.deterministic_score == 36
    assert hike.access_status == "unchecked"
    assert "not verified" in hike.access_warning.lower()


def test_context_unknowns_have_unique_semantic_kinds() -> None:
    context = recommendation_context()

    kinds = [unknown.kind for unknown in context.known_unknowns]
    assert len(kinds) == len(set(kinds))


def test_web_card_origin_is_supported() -> None:
    card = event_card().model_copy(update={"origin": EventOrigin.WEB_DISCOVERED})
    context = recommendation_context().model_copy(update={"event_cards": [card]})

    assert context.event_cards[0].origin is EventOrigin.WEB_DISCOVERED
