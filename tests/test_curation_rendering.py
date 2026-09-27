from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import HttpUrl

from event_radar.models.curation import (
    CandidateType,
    CurationConfidence,
    CurationDiagnostics,
    CurationOutcome,
    CurationRole,
    EventCuratedOption,
    HikeCuratedOption,
    ImportantUnknown,
    ImportantUnknownKind,
    WeekendCuration,
)
from event_radar.models.event_analysis import EventEvidenceClaim, EventSourceFact
from event_radar.services.curation_rendering import (
    format_event_time_range,
    render_chatgpt_packet,
    render_telegram_curation_summary,
    write_chatgpt_packet,
)
from tests.curation_helpers import event, recommendation_context


def curated_outcome() -> CurationOutcome:
    context = recommendation_context()
    option = EventCuratedOption(
        candidate_type=CandidateType.EVENT,
        candidate_id=context.event_cards[0].candidate_id,
        role=CurationRole.STANDOUT,
        why_it_survived="Distinctive public experience.",
        tradeoffs=["Attendance is unknown."],
        social_observation="Circulation creates hooks.",
        solo_observation="Normal solo attendance.",
        friction_observation="Low known friction.",
        schedule_observation="No known conflict.",
        confidence=CurationConfidence.HIGH,
    )
    return CurationOutcome(
        curation=WeekendCuration(
            weekend_read=["The weekend has a strong participatory option."],
            event_options=[option],
            hike_options=[],
            notable_near_misses=[],
            important_unknowns=[],
        ),
        diagnostics=CurationDiagnostics(
            model="test",
            success=True,
            input_event_cards=1,
            input_hike_candidates=1,
            retained_event_count=1,
            retained_hike_count=0,
            retained_total_count=1,
            attempts=1,
        ),
    )


def fallback_outcome() -> CurationOutcome:
    context = recommendation_context()
    return CurationOutcome(
        curation=None,
        diagnostics=CurationDiagnostics(
            model="test",
            success=False,
            fallback_reason="Unavailable",
            input_event_cards=len(context.event_cards),
            input_hike_candidates=len(context.hike_candidates),
            retained_event_count=0,
            retained_hike_count=0,
            retained_total_count=0,
            attempts=1,
        ),
    )


def test_packet_rehydrates_authoritative_occurrences_without_legacy_event_scores() -> None:
    context = recommendation_context()
    packet = render_chatgpt_packet(context, curated_outcome())
    card = context.event_cards[0]
    occurrence = card.occurrences[0]

    assert card.title in packet
    assert str(occurrence.sources[0].source_url) in packet
    assert "Experience summary" in packet
    assert "Deterministic score" not in packet
    assert "Saturday, August 8 at 6:00 PM PDT" in packet


def test_fallback_packet_is_explicit_and_preserves_broad_event_cards() -> None:
    context = recommendation_context()
    packet = render_chatgpt_packet(context, fallback_outcome())

    assert "Automated final LLM curation unavailable" in packet
    assert "Broad event-card inventory" in packet
    assert context.event_cards[0].title in packet


def test_telegram_summary_uses_final_curation_and_attachment_language() -> None:
    summary = render_telegram_curation_summary(recommendation_context(), curated_outcome())

    assert "Curated event pool: 1" in summary
    assert "Independent hikes retained separately: 0" in summary
    assert "Full ChatGPT decision packet attached" in summary


def test_packet_is_written_under_requested_output_directory(tmp_path: Path) -> None:
    context = recommendation_context()
    packet = render_chatgpt_packet(context, curated_outcome())

    path = write_chatgpt_packet(
        packet,
        output_directory=tmp_path,
        weekend_start=context.weekend_start,
    )

    assert path.read_text() == packet


def test_event_time_range_converts_utc_to_pdt_and_preserves_end_time() -> None:
    rendered = format_event_time_range(
        datetime(2026, 9, 26, 1, tzinfo=UTC),
        datetime(2026, 9, 26, 3, tzinfo=UTC),
        "America/Los_Angeles",
    )

    assert rendered == "Friday, September 25 at 6:00 PM PDT to 8:00 PM PDT"


def test_event_time_range_converts_winter_timestamp_to_pst() -> None:
    rendered = format_event_time_range(
        datetime(2026, 12, 5, 2, tzinfo=UTC),
        None,
        "America/Los_Angeles",
    )

    assert rendered == "Friday, December 4 at 6:00 PM PST"


def test_packet_renders_source_backed_price_conflict_not_free() -> None:
    source = event(
        price=Decimal("60"),
        price_details=("$60-$75 admission (conflicts with structured source metadata marked Free)"),
    ).model_copy(update={"price_max": Decimal("75"), "price_conflict": True})
    packet = render_chatgpt_packet(
        recommendation_context(events=[source]),
        fallback_outcome(),
    )

    assert "$60-$75 admission" in packet
    assert "Price: Free" not in packet


def test_important_unknowns_are_deduplicated_by_semantic_kind() -> None:
    context = recommendation_context()
    context = context.model_copy(
        update={
            "known_unknowns": [
                ImportantUnknown(
                    kind=ImportantUnknownKind.TRAVEL_TIME,
                    detail="Travel times are unknown.",
                )
            ]
        }
    )
    outcome = curated_outcome()
    assert outcome.curation is not None
    outcome = outcome.model_copy(
        update={
            "curation": outcome.curation.model_copy(
                update={
                    "important_unknowns": [
                        ImportantUnknown(
                            kind=ImportantUnknownKind.TRAVEL_TIME,
                            detail="Routing is unavailable.",
                        )
                    ]
                }
            )
        }
    )

    packet = render_chatgpt_packet(context, outcome)

    assert packet.count("Travel times are unknown.") == 1
    assert "Routing is unavailable." not in packet


def test_packet_renders_independent_hikes_outside_event_sections() -> None:
    context = recommendation_context()
    event_option = curated_outcome().curation
    assert event_option is not None
    hike_option = HikeCuratedOption(
        candidate_id=context.hike_candidates[0].candidate_id,
        role=CurationRole.STRONG,
        why_it_survived="A worthwhile independent outdoor option.",
        tradeoffs=["Access remains unchecked."],
        social_observation="No social claim.",
        solo_observation="Suitable for solo consideration.",
        friction_observation="Moderate drive friction.",
        schedule_observation="Sunday window.",
        confidence=CurationConfidence.MODERATE,
    )
    outcome = curated_outcome()
    assert outcome.curation is not None
    outcome = outcome.model_copy(
        update={"curation": outcome.curation.model_copy(update={"hike_options": [hike_option]})}
    )

    packet = render_chatgpt_packet(context, outcome)
    hike_heading = packet.index("## Potential independent hikes")
    hike_name = packet.index(context.hike_candidates[0].name)

    assert "independent hikes are additive and do not consume event slots" in packet
    assert hike_heading < hike_name
    assert packet.count(context.hike_candidates[0].name) == 1


def test_packet_renders_multiple_web_evidence_sources_with_supported_claims() -> None:
    context = recommendation_context()
    card = context.event_cards[0]
    occurrence = card.occurrences[0].model_copy(
        update={
            "sources": [
                EventSourceFact(
                    source_name="Regional calendar",
                    source_id=None,
                    source_url=HttpUrl("https://calendar.example/event"),
                    supported_claims=[
                        EventEvidenceClaim.EVENT_EXISTENCE,
                        EventEvidenceClaim.DATE_TIME,
                        EventEvidenceClaim.LOCATION,
                    ],
                    source_confidence="high",
                ),
                EventSourceFact(
                    source_name="Official operator",
                    source_id=None,
                    source_url=HttpUrl("https://operator.example/activity"),
                    supported_claims=[EventEvidenceClaim.EXPERIENCE_DESCRIPTION],
                    source_confidence="high",
                ),
            ]
        }
    )
    context = context.model_copy(
        update={"event_cards": [card.model_copy(update={"occurrences": [occurrence]})]}
    )

    packet = render_chatgpt_packet(context, fallback_outcome())

    assert "[Regional calendar](https://calendar.example/event)" in packet
    assert "event existence, date/time, location" in packet
    assert "[Official operator](https://operator.example/activity)" in packet
    assert "experience/details" in packet
