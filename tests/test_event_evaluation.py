from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from event_radar.models.event import Event
from event_radar.recommendation_config import DEFAULT_RECOMMENDATION_CONFIG
from event_radar.services.event_evaluation import evaluate_event, select_event_candidates

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
WINDOW_START = datetime(2026, 8, 7, tzinfo=PACIFIC_TIME)
WINDOW_END = datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)
MIDDAY = datetime(2026, 8, 8, 12, tzinfo=PACIFIC_TIME)


def _event(
    title: str,
    *,
    description: str | None = None,
    categories: set[str] | None = None,
    city: str = "Santa Rosa",
    venue: str | None = None,
    start_time: datetime | None = None,
    duration_hours: int | None = 2,
    price: Decimal | None = None,
) -> Event:
    event_start = start_time or datetime(2026, 8, 8, 18, tzinfo=PACIFIC_TIME)
    return Event(
        source_name="Test Source",
        source_id=title,
        source_url=HttpUrl("https://example.com/event"),
        title=title,
        description=description,
        start_time=event_start,
        end_time=(
            event_start + timedelta(hours=duration_hours) if duration_hours is not None else None
        ),
        venue=venue,
        city=city,
        categories=categories or set(),
        price_min=price,
    )


def test_social_event_receives_positive_signals_and_reasons() -> None:
    event = _event(
        "Downtown Summer Festival",
        description="A community gathering with live music, dancing, and local food.",
        categories={"festival", "live-music"},
        price=Decimal("0"),
    )

    evaluation = evaluate_event(event, WINDOW_START, WINDOW_END)

    assert evaluation.eligible is True
    assert evaluation.score > 20
    assert "festival or public celebration [category]" in evaluation.reasons
    assert "live music [category]" in evaluation.reasons
    assert "free admission" in evaluation.reasons


def test_structured_category_match_gets_category_weight() -> None:
    evaluation = evaluate_event(
        _event("Afternoon Gathering", categories={"music"}, start_time=MIDDAY, duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 10
    assert evaluation.reasons == ["live music [category]"]


def test_title_match_gets_title_weight_without_category_match() -> None:
    evaluation = evaluate_event(
        _event("Friday Night Concert", start_time=MIDDAY, duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 10
    assert evaluation.reasons == ["live music [title]"]


def test_description_only_match_gets_weaker_description_weight() -> None:
    evaluation = evaluate_event(
        _event(
            "Friday Gathering",
            description="Enjoy live music from a local trio.",
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 3
    assert evaluation.reasons == ["live music [description]"]


def test_community_festival_description_gets_weaker_community_weight() -> None:
    evaluation = evaluate_event(
        _event(
            "Friday Gathering",
            description="A community festival for the whole neighborhood.",
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 7
    assert evaluation.reasons == [
        "festival or public celebration [description]",
        "community gathering [description]",
    ]


def test_signal_uses_only_strongest_matching_evidence_field() -> None:
    evaluation = evaluate_event(
        _event(
            "Live Music Concert",
            description="Enjoy live music throughout the afternoon.",
            categories={"music"},
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 10
    assert evaluation.reasons.count("live music [category]") == 1
    assert all(reason != "live music [title]" for reason in evaluation.reasons)
    assert all(reason != "live music [description]" for reason in evaluation.reasons)


def test_description_only_semantic_signals_are_capped_in_aggregate() -> None:
    config = replace(
        DEFAULT_RECOMMENDATION_CONFIG,
        description_substance_minimum_characters=10_000,
    )
    evaluation = evaluate_event(
        _event(
            "Saturday Gathering",
            description=(
                "Live music accompanies a community gathering, comedy show, "
                "guided hike, and food festival."
            ),
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
        config,
    )

    assert evaluation.score == 8
    assert "description-only semantic score capped at 8" in evaluation.reasons


def test_category_and_title_scores_are_not_affected_by_description_cap() -> None:
    config = replace(
        DEFAULT_RECOMMENDATION_CONFIG,
        description_substance_minimum_characters=10_000,
    )
    evaluation = evaluate_event(
        _event(
            "Evening Concert",
            description="A community gathering with a comedy show and guided hike.",
            categories={"festival"},
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
        config,
    )

    assert evaluation.score == 30
    assert "festival or public celebration [category]" in evaluation.reasons
    assert "live music [title]" in evaluation.reasons
    assert "description-only semantic score capped at 8" in evaluation.reasons


def test_thematic_dance_word_does_not_imply_participatory_dance() -> None:
    evaluation = evaluate_event(
        _event(
            "Who Will Dance with Pancho Villa?",
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 0
    assert evaluation.activity_type == "other"
    assert all("participatory dance" not in reason for reason in evaluation.reasons)


def test_strong_dance_party_title_gets_participatory_dance_signal() -> None:
    evaluation = evaluate_event(
        _event("Salsa Dance Party", start_time=MIDDAY, duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 17
    assert "participatory dance or movement event [title]" in evaluation.reasons


def test_incidental_dancers_in_description_do_not_imply_participatory_dance() -> None:
    evaluation = evaluate_event(
        _event(
            "A Theatrical Production",
            description="Performers and dancers appear during the theatrical production.",
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert all("participatory dance" not in reason for reason in evaluation.reasons)


def test_structured_dance_category_gets_strong_dance_signal() -> None:
    evaluation = evaluate_event(
        _event("Evening Program", categories={"Dance"}, start_time=MIDDAY, duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 8
    assert "participatory dance or movement event [category]" in evaluation.reasons


def test_incidental_generic_music_in_description_is_not_live_music_evidence() -> None:
    evaluation = evaluate_event(
        _event(
            "Community Lecture",
            description="Background music may play while guests arrive.",
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert all("live music" not in reason for reason in evaluation.reasons)


def test_explicit_live_music_description_gets_weaker_live_music_signal() -> None:
    evaluation = evaluate_event(
        _event(
            "Friday Program",
            description="The afternoon includes live music from a local band.",
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 3
    assert evaluation.reasons == ["live music [description]"]


def test_adult_oriented_signal_remains_modest() -> None:
    evaluation = evaluate_event(
        _event("Tasting Program", categories={"wine"}, start_time=MIDDAY, duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 4
    assert evaluation.reasons == ["adult-oriented setting [category]"]


def test_description_substance_is_only_a_one_point_boost() -> None:
    evaluation = evaluate_event(
        _event(
            "Detailed Lecture",
            description="Informational details. " * 10,
            start_time=MIDDAY,
            duration_hours=None,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.score == 1
    assert evaluation.reasons == ["substantive event description"]


def test_explicitly_child_only_event_is_excluded() -> None:
    evaluation = evaluate_event(
        _event("Preschool Storytime"),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.eligible is False
    assert evaluation.exclusion_reasons == ["explicitly child-only event"]


def test_professional_only_event_is_excluded() -> None:
    evaluation = evaluate_event(
        _event("Business Networking Breakfast"),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.eligible is False
    assert evaluation.exclusion_reasons == ["explicitly professional or business-only event"]


def test_ordinary_event_remains_eligible_without_assumed_signals() -> None:
    evaluation = evaluate_event(
        _event("Local Book Discussion", duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.eligible is True
    assert evaluation.score == 2
    assert evaluation.reasons == ["evening timing"]


def test_venue_name_does_not_invent_an_event_type() -> None:
    evaluation = evaluate_event(
        _event("Quiet Reading", venue="Downtown Music Center", duration_hours=None),
        WINDOW_START,
        WINDOW_END,
    )

    assert "live music" not in evaluation.reasons


def test_structured_recreation_category_is_strong_sports_evidence() -> None:
    evaluation = evaluate_event(
        _event("Astronomy Talk", categories={"recreation"}),
        WINDOW_START,
        WINDOW_END,
    )

    assert "sports, fitness, or recreation [category]" in evaluation.reasons


def test_candidate_ordering_is_deterministic_for_equal_scores() -> None:
    later_title = _event("Beta Concert")
    earlier_title = _event("Alpha Concert")

    first = select_event_candidates([later_title, earlier_title], WINDOW_START, WINDOW_END)
    second = select_event_candidates([earlier_title, later_title], WINDOW_START, WINDOW_END)

    assert [candidate.event.title for candidate in first.candidates] == [
        "Alpha Concert",
        "Beta Concert",
    ]
    assert [candidate.event.title for candidate in second.candidates] == [
        "Alpha Concert",
        "Beta Concert",
    ]


def test_candidate_cap_and_minimum_score_are_applied() -> None:
    config = replace(
        DEFAULT_RECOMMENDATION_CONFIG,
        maximum_candidates=2,
        minimum_score=5,
    )
    events = [
        _event("First Concert"),
        _event("Second Concert"),
        _event("Third Concert"),
        _event("Ordinary Lecture", duration_hours=None),
    ]

    selection = select_event_candidates(events, WINDOW_START, WINDOW_END, config)

    assert len(selection.candidates) == 2
    assert all(candidate.score >= 5 for candidate in selection.candidates)
    assert "Ordinary Lecture" not in {candidate.event.title for candidate in selection.candidates}


def test_sparse_inventory_is_not_padded() -> None:
    selection = select_event_candidates(
        [_event("Neighborhood Art Walk")],
        WINDOW_START,
        WINDOW_END,
    )

    assert len(selection.candidates) == 1


def test_light_diversity_promotes_another_activity_type() -> None:
    config = replace(
        DEFAULT_RECOMMENDATION_CONFIG,
        maximum_candidates=4,
        diversity_soft_cap_per_type=2,
    )
    concerts = [_event(f"Concert {index}") for index in range(5)]
    art_walk = _event("Downtown Art Walk", start_time=datetime(2026, 8, 9, 12, tzinfo=PACIFIC_TIME))

    selection = select_event_candidates(
        [*concerts, art_walk],
        WINDOW_START,
        WINDOW_END,
        config,
    )

    selected_titles = [candidate.event.title for candidate in selection.candidates]
    assert "Downtown Art Walk" in selected_titles
    assert sum(title.startswith("Concert") for title in selected_titles) == 3


def test_light_diversity_avoids_repeated_title_when_other_options_exist() -> None:
    repeated_saturday = _event("County Fair")
    repeated_sunday = _event(
        "County Fair",
        start_time=datetime(2026, 8, 9, 12, tzinfo=PACIFIC_TIME),
    )
    art_walk = _event(
        "Downtown Art Walk",
        start_time=datetime(2026, 8, 9, 13, tzinfo=PACIFIC_TIME),
    )
    config = replace(DEFAULT_RECOMMENDATION_CONFIG, maximum_candidates=2)

    selection = select_event_candidates(
        [repeated_saturday, repeated_sunday, art_walk],
        WINDOW_START,
        WINDOW_END,
        config,
    )

    assert [candidate.event.title for candidate in selection.candidates] == [
        "County Fair",
        "Downtown Art Walk",
    ]


def test_out_of_window_event_is_hard_excluded() -> None:
    event = _event(
        "Sunday Concert",
        start_time=datetime(2026, 8, 10, tzinfo=PACIFIC_TIME),
    )

    evaluation = evaluate_event(event, WINDOW_START, WINDOW_END)

    assert evaluation.eligible is False
    assert "outside requested date window" in evaluation.exclusion_reasons
