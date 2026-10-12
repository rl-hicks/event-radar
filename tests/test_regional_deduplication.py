import copy
import json
from pathlib import Path

from event_radar.models.regional import RegionalOpportunity
from event_radar.shared.deduplication import deduplicate_regional_opportunities

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"


def event_payload():
    return json.loads(FIXTURE.read_text())["opportunities"][0]


def test_cross_source_duplicate_preserves_evidence_and_price_conflict() -> None:
    first = event_payload()
    second = copy.deepcopy(first)
    second["opportunity_id"] = "same-event-source-two"
    second["evidence"][0]["evidence_id"] = "source-two"
    second["evidence"][0]["source_id"] = "source-two-feed"
    second["evidence"][0]["source_record_id"] = "record-two"
    second["evidence"][0]["claims"] = [
        "existence",
        "location",
        "time",
        "price",
        "description",
    ]
    second["evidence"][0]["occurrence_start"] = second["occurrences"][0]["start"]
    second["evidence"][0]["occurrence_end"] = second["occurrences"][0]["end"]
    second["location"]["evidence_ids"] = ["source-two"]
    second["occurrences"][0]["occurrence_id"] = "same-event-source-two-occurrence"
    second["occurrences"][0]["location"]["evidence_ids"] = ["source-two"]
    second["occurrences"][0]["evidence_ids"] = ["source-two"]
    second["occurrences"][0]["price"] = {
        "state": "known",
        "quotes": [
            {
                "minimum": "25",
                "maximum": "25",
                "currency": "USD",
                "details": "$25",
                "evidence_ids": ["source-two"],
            }
        ],
    }
    second["categories"]["evidence_ids"] = ["source-two"]
    second["semantics"] = None
    second["evidence"] = [second["evidence"][0]]

    result = deduplicate_regional_opportunities(
        (
            RegionalOpportunity.model_validate(second),
            RegionalOpportunity.model_validate(first),
        )
    )

    assert result.duplicates_removed == 1
    assert len(result.opportunities) == 1
    merged = result.opportunities[0]
    assert {e.source_id for e in merged.evidence} == {
        "public-feed",
        "public-calendar",
        "source-two-feed",
    }
    assert merged.occurrences[0].price.state == "conflicting"
    assert len(merged.occurrences[0].price.quotes) == 3
    assert len(result.exclusions) == 1
    assert result.exclusions[0].reason == "duplicate_occurrence"
    assert result.exclusions[0].duplicate_of == merged.occurrences[0].occurrence_id


def test_different_end_time_remains_distinct() -> None:
    first = RegionalOpportunity.model_validate(event_payload())
    payload = event_payload()
    payload["opportunity_id"] = "different-time"
    payload["occurrences"][0]["occurrence_id"] = "different-time-occ"
    payload["occurrences"][0]["end"] = "2026-10-03T17:00:00-07:00"
    payload["evidence"][1]["occurrence_end"] = "2026-10-03T17:00:00-07:00"
    second = RegionalOpportunity.model_validate(payload)

    result = deduplicate_regional_opportunities((first, second))

    assert result.duplicates_removed == 0
    assert len(result.opportunities) == 2
