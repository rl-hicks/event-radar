from pathlib import Path

from event_radar.models.curation import (
    CandidateType,
    CuratedOption,
    CurationConfidence,
    CurationDiagnostics,
    CurationOutcome,
    CurationRole,
    WeekendCuration,
)
from event_radar.services.curation_rendering import (
    render_chatgpt_packet,
    render_telegram_curation_summary,
    write_chatgpt_packet,
)
from tests.curation_helpers import START, recommendation_context


def outcome() -> CurationOutcome:
    context = recommendation_context()
    options = [
        CuratedOption(
            candidate_type=CandidateType.EVENT,
            candidate_id=context.event_candidates[0].candidate_id,
            role=CurationRole.STANDOUT,
            why_it_survived="A structured, circulating event with standalone value.",
            tradeoffs=["Solo attendance may reduce some of the value."],
            social_observation="Circulation creates plausible conversation hooks.",
            solo_observation="The market structure gives a solo attendee something to do.",
            friction_observation="Price and travel time remain unknown.",
            schedule_observation="No conflict with the climbing anchor.",
            confidence=CurationConfidence.HIGH,
        ),
        CuratedOption(
            candidate_type=CandidateType.HIKE,
            candidate_id=context.hike_candidates[0].candidate_id,
            role=CurationRole.STRONG,
            why_it_survived="A scenic outdoor option with favorable trailhead weather.",
            tradeoffs=["Access has not been checked."],
            social_observation="Social interaction is not required for the hike to be worthwhile.",
            solo_observation="Catalog solo fit is strong.",
            friction_observation="This is a destination outing.",
            schedule_observation="Sunday timing avoids Saturday climbing.",
            confidence=CurationConfidence.MODERATE,
        ),
    ]
    curation = WeekendCuration(
        weekend_read=["There is a useful mix of social and outdoor possibilities."],
        options=options,
        notable_near_misses=[],
        important_unknowns=["Actual travel time is unknown."],
    )
    return CurationOutcome(
        curation=curation,
        diagnostics=CurationDiagnostics(
            model="gpt-5.6",
            success=True,
            input_event_candidates=1,
            input_hike_candidates=1,
            retained_options=2,
            attempts=1,
        ),
    )


def fallback_outcome() -> CurationOutcome:
    return CurationOutcome(
        curation=None,
        diagnostics=CurationDiagnostics(
            model="gpt-5.6",
            success=False,
            fallback_reason="OpenAI API key is not configured.",
            input_event_candidates=1,
            input_hike_candidates=1,
            retained_options=0,
            attempts=0,
        ),
    )


def test_packet_rehydrates_authoritative_facts_and_contains_context() -> None:
    context = recommendation_context()
    packet = render_chatgpt_packet(context, outcome())
    event = context.event_candidates[0]
    hike = context.hike_candidates[0]

    assert event.title in packet
    assert str(event.source_url) in packet
    assert event.start_time.strftime("%A, %B %-d") in packet
    assert "Price: UNKNOWN" in packet
    assert context.user_context.core_objective in packet
    assert context.permanent_directions[0] in packet
    assert context.temporary_directions[0] in packet
    assert "Weather context" in packet
    assert hike.name in packet
    assert str(hike.official_source_url) in packet
    assert hike.access_warning in packet
    assert "ChatGPT handoff instructions" in packet
    assert "Never claim hike access is verified" in packet


def test_ai_output_schema_cannot_overwrite_factual_event_fields() -> None:
    fields = CuratedOption.model_fields

    assert "title" not in fields
    assert "start_time" not in fields
    assert "source_url" not in fields


def test_fallback_packet_is_labeled_and_keeps_all_deterministic_candidates() -> None:
    context = recommendation_context()
    packet = render_chatgpt_packet(context, fallback_outcome())

    assert "Automated LLM curation unavailable for this run." in packet
    assert context.event_candidates[0].title in packet
    assert context.hike_candidates[0].name in packet
    assert context.event_candidates[0].deterministic_reasons[0] in packet
    assert context.hike_candidates[0].deterministic_reasons[0] in packet


def test_compact_telegram_summary_mentions_attachment_and_split() -> None:
    context = recommendation_context()
    summary = render_telegram_curation_summary(context, outcome())

    assert "Curated decision set: 2" in summary
    assert "Events retained: 1" in summary
    assert "Hikes retained: 1" in summary
    assert "Full ChatGPT decision packet attached." in summary
    assert len(summary) < 4000


def test_fallback_telegram_summary_is_clear() -> None:
    summary = render_telegram_curation_summary(recommendation_context(), fallback_outcome())

    assert "Automated LLM curation was unavailable." in summary
    assert "Events included: 1" in summary
    assert "Hikes included: 1" in summary


def test_packet_is_written_to_gitignored_output_directory(tmp_path: Path) -> None:
    packet = "# Packet\n"

    path = write_chatgpt_packet(packet, output_directory=tmp_path, weekend_start=START)

    assert path.name == "event-radar-2026-08-08.md"
    assert path.read_text(encoding="utf-8") == packet
