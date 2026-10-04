"""Public/synthetic contract tests; no legacy research execution."""

import copy
import json
from datetime import UTC, date
from pathlib import Path

import pytest
from pydantic import ValidationError

from event_radar.models.regional import (
    Observation,
    RegionalAnalysisRequest,
    RegionalDiscoveryRequest,
    RegionalWeekendUniverse,
    ResearchScope,
    WeekendWindow,
)

FIXTURES = Path(__file__).parent / "fixtures" / "regional"


def payload():
    return json.loads((FIXTURES / "universe.json").read_text())


def validate(value):
    # Test the actual JSON boundary, not Pydantic's trusted construction bypasses.
    return RegionalWeekendUniverse.model_validate_json(json.dumps(value))


def test_roundtrip_preserves_alternative_provenance_conflicts_and_unknowns():
    universe = validate(payload())
    restored = RegionalWeekendUniverse.model_validate_json(universe.model_dump_json())
    assert restored == universe
    event, hike = restored.opportunities
    assert {e.source_id for e in event.evidence} == {"public-feed", "public-calendar"}
    assert event.occurrences[0].price.state == "conflicting"
    assert [q.minimum for q in event.occurrences[0].price.quotes] == [0, 20]
    assert event.categories.value == ()
    assert hike.categories.value is None
    assert hike.access_open.value is None
    assert hike.route.distance_miles == 12
    assert hike.occurrences == ()
    assert restored.diagnostics[0].input_tokens is None
    assert restored.diagnostics[0].tool_calls == 0
    assert restored.sources[3].result_count == 0
    assert restored.sources[4].result_count is None


def test_known_false_and_unknown_price_are_not_missing_or_free():
    value = payload()
    event = value["opportunities"][0]
    event["access_open"] = {"state": "known", "value": False, "evidence_ids": ["organizer"]}
    event["occurrences"][0]["price"] = {"state": "unknown", "quotes": []}
    parsed = validate(value)
    assert parsed.opportunities[0].access_open.value is False
    assert parsed.opportunities[0].occurrences[0].price.quotes == ()


@pytest.mark.parametrize(
    "value",
    [
        {"state": "unknown", "value": False, "evidence_ids": []},
        {"state": "known", "value": None, "evidence_ids": ["source"]},
        {"state": "known", "value": False, "evidence_ids": []},
    ],
)
def test_invalid_observation_states_rejected(value):
    with pytest.raises(ValidationError):
        Observation[bool].model_validate_json(json.dumps(value))


def test_empty_search_partial_failure_and_empty_universe_are_independent():
    value = payload()
    value["opportunities"] = []
    value["exclusions"] = []
    for source in value["sources"]:
        if source["status"] in ("success", "partial"):
            source["result_count"] = 0
    value["diagnostics"][0]["result_count"] = 0
    parsed = validate(value)
    assert parsed.opportunities == ()
    assert parsed.sources[1].status == "partial"
    assert parsed.sources[3].status == "success"
    assert parsed.sources[3].result_count == 0
    assert parsed.sources[4].status == "failed"
    # Absence of configured sources also remains explicit, not a success claim.
    value["sources"] = []
    assert validate(value).sources == ()


def test_no_personal_count_caps():
    value = payload()
    event = value["opportunities"][0]
    value["opportunities"] = []
    value["exclusions"] = []
    for index in range(40):
        entry = copy.deepcopy(event)
        entry["opportunity_id"] = f"event-{index}"
        entry["occurrences"][0]["occurrence_id"] = f"occurrence-{index}"
        # Different locations avoid asserting that identical events are distinct.
        entry["location"]["venue"] = f"Synthetic Hall {index}"
        entry["occurrences"][0]["location"]["venue"] = f"Synthetic Hall {index}"
        value["opportunities"].append(entry)
    assert len(validate(value).opportunities) == 40


def test_two_different_consumers_reuse_identical_profile_free_wire_contract():
    profiles = json.loads((FIXTURES / "synthetic_profiles.json").read_text())
    assert profiles[0]["hiking"] != profiles[1]["hiking"]
    assert profiles[0]["available"] != profiles[1]["available"]
    assert profiles[0]["maximum_cost_usd"] != profiles[1]["maximum_cost_usd"]
    shared = validate(payload())
    wire = shared.model_dump_json()
    # This is consumer reuse evidence, not an E2 curation implementation.
    consumers = {p["label"]: RegionalWeekendUniverse.model_validate_json(wire) for p in profiles}
    assert all(result == shared for result in consumers.values())
    assert all(p["label"] not in wire for p in profiles)
    assert len(shared.opportunities) == 2  # The hard hike survives both consumers.
    # There is no profile argument/default/empty policy shim in either request.
    analysis = RegionalAnalysisRequest(scope=shared.scope, opportunities=shared.opportunities)
    discovery = RegionalDiscoveryRequest(scope=shared.scope, existing_opportunities=())
    assert analysis.scope.identity == discovery.scope.identity
    assert discovery.existing_opportunities == ()


@pytest.mark.parametrize(
    ("friday", "hours"),
    [
        ("2026-03-06", 71),
        ("2026-10-30", 73),
        ("2026-10-02", 72),
    ],
)
def test_calendar_weekend_dst_and_exclusive_end(friday, hours):
    window = WeekendWindow(friday=date.fromisoformat(friday), timezone="America/Los_Angeles")
    assert window.start.weekday() == 4 and window.start.hour == 0
    assert window.end.weekday() == 0 and window.end.hour == 0
    assert (
        window.end.astimezone(UTC) - window.start.astimezone(UTC)
    ).total_seconds() == hours * 3600
    assert window.overlaps(window.start, None)
    assert not window.overlaps(window.end, None)
    assert not window.overlaps(window.start.replace(day=window.start.day - 1), window.start)


def test_same_logical_identity_across_retry_time_and_policy_version_separation():
    value = payload()["scope"]
    first = ResearchScope.model_validate(value)
    value["as_of"] = "2026-10-04T22:00:00Z"
    second = ResearchScope.model_validate(value)
    assert first.identity.key == second.identity.key == "sonoma-county-ca/2026-10-02/regional-v1"
    assert first.window.start == second.window.start
    assert first.as_of != second.as_of
    value["research_policy_version"] = "regional-v2"
    assert ResearchScope.model_validate(value).identity != first.identity


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("as_of", "2026-10-02T12:00:00"),
        ("window", {"friday": "2026-10-03", "timezone": "America/Los_Angeles"}),
        ("window", {"friday": "2026-10-02", "timezone": "UTC"}),
        ("window", {"friday": "2026-10-02", "timezone": "Invalid/Zone"}),
    ],
)
def test_invalid_scope_rejected(field, value):
    data = payload()
    data["scope"][field] = value
    with pytest.raises(ValidationError):
        validate(data)


def test_distinct_occurrence_alternatives_preserved_but_exact_duplicate_rejected():
    value = payload()
    event = value["opportunities"][0]
    duplicate = copy.deepcopy(event["occurrences"][0])
    duplicate["occurrence_id"] = "alternative"
    event["occurrences"].append(duplicate)
    with pytest.raises(ValidationError, match="duplicate occurrences"):
        validate(value)
    sunday = copy.deepcopy(event["evidence"][1])
    sunday["evidence_id"] = "sunday-calendar"
    sunday["occurrence_start"] = "2026-10-04T14:00:00-07:00"
    sunday["occurrence_end"] = "2026-10-04T16:00:00-07:00"
    event["evidence"].append(sunday)
    duplicate["start"], duplicate["end"] = sunday["occurrence_start"], sunday["occurrence_end"]
    duplicate["evidence_ids"] = ["sunday-calendar"]
    assert len(validate(value).opportunities[0].occurrences) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_id",
        "missing_evidence",
        "mismatched_time",
        "wrong_claim",
        "outside_county",
        "outside_window",
        "future_evidence",
        "failed_source_evidence",
        "false_empty_failure",
        "invalid_price",
        "fake_conflict",
        "dangling_duplicate",
        "unknown_access_as_true",
        "credential_url",
    ],
)
def test_invalid_factual_contracts_fail_closed(mutation):
    value = payload()
    event = value["opportunities"][0]
    occurrence = event["occurrences"][0]
    if mutation == "duplicate_id":
        value["opportunities"].append(copy.deepcopy(event))
    elif mutation == "missing_evidence":
        event["evidence"] = []
    elif mutation == "mismatched_time":
        occurrence["start"] = "2026-10-03T15:00:00-07:00"
    elif mutation == "wrong_claim":
        occurrence["price"]["quotes"][0]["evidence_ids"] = ["missing"]
    elif mutation == "outside_county":
        event["location"]["county"] = "Marin County"
    elif mutation == "outside_window":
        occurrence["start"] = event["evidence"][1]["occurrence_start"] = "2026-10-05T00:00:00-07:00"
        occurrence["end"] = event["evidence"][1]["occurrence_end"] = None
    elif mutation == "future_evidence":
        event["evidence"][0]["observed_at"] = "2026-10-03T12:00:00-07:00"
    elif mutation == "failed_source_evidence":
        value["sources"][0].update(status="failed", result_count=None, failure_code="timeout")
    elif mutation == "false_empty_failure":
        value["sources"][-1]["result_count"] = 0
    elif mutation == "invalid_price":
        occurrence["price"]["quotes"][0]["minimum"] = "-1"
    elif mutation == "fake_conflict":
        occurrence["price"]["quotes"] = [occurrence["price"]["quotes"][0]] * 2
    elif mutation == "dangling_duplicate":
        value["exclusions"][0]["duplicate_of"] = "missing"
    elif mutation == "unknown_access_as_true":
        event["access_open"]["value"] = True
    elif mutation == "credential_url":
        event["evidence"][0]["url"] = "https://user:synthetic-password@example.org/event"
    with pytest.raises(ValidationError):
        validate(value)


PROHIBITED = [
    "user_context",
    "profile_id",
    "personal_experience_context",
    "permanent_directions",
    "temporary_directions",
    "telegram_chat_id",
    "recurring_availability",
    "drive_friction_from_santa_rosa",
    "score",
    "disposition",
    "why_it_may_fit",
    "schedule_observation",
    "provider_error_message",
]


@pytest.mark.parametrize("field", PROHIBITED)
def test_personal_fields_rejected_at_every_nested_json_object(field):
    value = payload()

    def paths(node, path=()):
        if isinstance(node, dict):
            yield path
            for key, child in node.items():
                yield from paths(child, (*path, key))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                yield from paths(child, (*path, index))

    for path in paths(value):
        changed = copy.deepcopy(value)
        target = changed
        for key in path:
            target = target[key]
        target[field] = "synthetic-private-marker"
        with pytest.raises(ValidationError) as error:
            validate(changed)
        assert any(e["type"] == "extra_forbidden" for e in error.value.errors())
        assert "synthetic-private-marker" not in str(error.value)


@pytest.mark.parametrize("request_type", [RegionalAnalysisRequest, RegionalDiscoveryRequest])
def test_personal_request_inputs_are_rejected(request_type):
    data = {"scope": payload()["scope"]}
    field = "opportunities" if request_type is RegionalAnalysisRequest else "existing_opportunities"
    data[field] = []
    for key in PROHIBITED:
        with pytest.raises(ValidationError):
            request_type.model_validate_json(json.dumps({**data, key: []}))


def test_json_schema_closes_all_nested_objects():
    schema = RegionalWeekendUniverse.model_json_schema()
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
    assert "user_context" not in json.dumps(schema)


@pytest.mark.parametrize("request_type", [RegionalAnalysisRequest, RegionalDiscoveryRequest])
def test_requests_enforce_same_region_time_and_duplicate_rules(request_type):
    value = payload()
    field = "opportunities" if request_type is RegionalAnalysisRequest else "existing_opportunities"
    request = {"scope": value["scope"], field: value["opportunities"]}
    request[field][0]["location"]["county"] = "Marin County"
    with pytest.raises(ValidationError, match="boundary"):
        request_type.model_validate_json(json.dumps(request))


def test_duplicate_occurrence_across_opportunity_ids_is_not_new_inventory():
    value = payload()
    duplicate = copy.deepcopy(value["opportunities"][0])
    duplicate["opportunity_id"] = "different-id"
    duplicate["occurrences"][0]["occurrence_id"] = "different-occurrence-id"
    value["opportunities"].append(duplicate)
    with pytest.raises(ValidationError, match="duplicate occurrences"):
        validate(value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("usage_complete", True),
        ("provider_error_message", "synthetic secret"),
        ("latency_seconds", -1),
        ("input_tokens", -1),
    ],
)
def test_diagnostics_do_not_claim_missing_usage_or_accept_raw_errors(field, replacement):
    value = payload()
    value["diagnostics"][0][field] = replacement
    with pytest.raises(ValidationError):
        validate(value)


def test_complete_zero_usage_and_partial_known_subtotals_are_distinct():
    value = payload()
    d = value["diagnostics"][0]
    d.update(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        estimated_model_cost_usd="0",
        usage_complete=True,
    )
    assert validate(value).diagnostics[0].estimated_model_cost_usd == 0
    d.update(
        input_tokens=10,
        cached_input_tokens=2,
        output_tokens=4,
        total_tokens=14,
        estimated_model_cost_usd=None,
        usage_complete=False,
    )
    assert validate(value).diagnostics[0].total_tokens == 14
    d["total_tokens"] = 15
    with pytest.raises(ValidationError, match="totals"):
        validate(value)


def test_known_empty_source_cannot_supply_an_opportunity():
    value = payload()
    value["sources"][0]["result_count"] = 0
    with pytest.raises(ValidationError, match="Known-empty"):
        validate(value)


def test_event_spanning_friday_is_included_without_current_time_truncation():
    value = payload()
    event = value["opportunities"][0]
    occurrence = event["occurrences"][0]
    occurrence["start"] = event["evidence"][1]["occurrence_start"] = "2026-10-01T23:00:00-07:00"
    occurrence["end"] = event["evidence"][1]["occurrence_end"] = "2026-10-02T01:00:00-07:00"
    assert len(validate(value).opportunities[0].occurrences) == 1


def test_unattempted_source_is_not_a_successful_empty_search():
    value = payload()
    value["sources"][3].update(
        status="not_attempted", observed_at=None, result_count=None, failure_code="not_configured"
    )
    assert validate(value).sources[3].result_count is None
    value["sources"][3]["result_count"] = 0
    with pytest.raises(ValidationError):
        validate(value)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.sonomacounty.com/events/synthetic-event",
        "https://happeningsonomacounty.com/event/synthetic-event/",
        "https://example.org/events?event_id=abc-123",
        "https://example.org/events?eid=102&occurrence_id=2026-10-03",
        "https://example.org/?p=724",
    ],
)
def test_public_evidence_urls_preserve_valid_event_identifiers(url):
    value = payload()
    value["opportunities"][0]["evidence"][0]["url"] = url
    assert str(validate(value).opportunities[0].evidence[0].url).startswith("https://")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/events/synthetic",
        "https://localhost/events",
        "https://sub.localhost/events",
        "https://127.0.0.1/events",
        "https://10.0.0.2/events",
        "https://[::1]/events",
        "https://metadata.google.internal/events",
        "https://example.local/events",
        "https://example.org:8443/events",
        "https://reader:password@example.org/events",
        "https://example.org/events#fragment",
        "https://example.org/events?utm_source=example",
        "https://example.org/events?token=synthetic",
        "https://example.org/events?api_key=synthetic",
        "https://example.org/events?event_id=",
        "https://example.org/events?id=123&id=456",
        "https://example.org/events?event_id=123%2F456",
        "https://example.org/events?event_id=123&tracking=synthetic",
        "https://example.org/events?unknown_field=123",
    ],
)
def test_unsafe_or_noncanonical_evidence_urls_are_rejected(url):
    value = payload()
    value["opportunities"][0]["evidence"][0]["url"] = url
    with pytest.raises(ValidationError):
        validate(value)


def test_known_end_cannot_be_discarded_or_contradicted():
    value = payload()
    event = value["opportunities"][0]
    occurrence = event["occurrences"][0]
    occurrence["end"] = None
    with pytest.raises(ValidationError, match="source-extracted"):
        validate(value)
    occurrence["end"] = "2026-10-03T17:00:00-07:00"
    with pytest.raises(ValidationError, match="source-extracted"):
        validate(value)
    # If no source supports an end, unknown is explicitly permitted.
    event["evidence"][1]["occurrence_end"] = None
    occurrence["end"] = None
    assert validate(value).opportunities[0].occurrences[0].end is None
    occurrence["end"] = "2026-10-03T16:00:00-07:00"
    with pytest.raises(ValidationError, match="end-time evidence"):
        validate(value)


def test_start_only_time_evidence_can_supplement_a_known_end():
    value = payload()
    event = value["opportunities"][0]
    start_only = copy.deepcopy(event["evidence"][1])
    start_only["evidence_id"] = "calendar-start-only"
    start_only["occurrence_end"] = None
    event["evidence"].append(start_only)
    event["occurrences"][0]["evidence_ids"].append("calendar-start-only")
    assert len(validate(value).opportunities[0].occurrences[0].evidence_ids) == 2
    # A second authoritative, incompatible end is not silently merged.
    start_only["occurrence_end"] = "2026-10-03T17:00:00-07:00"
    with pytest.raises(ValidationError, match="source-extracted"):
        validate(value)


def test_ticket_availability_cannot_be_inferred_from_physical_access():
    value = payload()
    event = value["opportunities"][0]
    availability = event["occurrences"][0]["available"]
    availability.update(state="known", value=False, evidence_ids=["organizer"])
    with pytest.raises(ValidationError, match="claim evidence"):
        validate(value)
    event["evidence"][0]["claims"].append("availability")
    assert validate(value).opportunities[0].occurrences[0].available.value is False
    event["access_open"] = {"state": "known", "value": True, "evidence_ids": ["organizer"]}
    assert validate(value).opportunities[0].access_open.value is True
    event["evidence"][0]["claims"].remove("access")
    with pytest.raises(ValidationError, match="claim evidence"):
        validate(value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("region_id", "marin-county-ca"),
        ("country_code", "CA"),
        ("subdivision_code", "NY"),
        ("county", "Marin County"),
        ("timezone", "America/New_York"),
    ],
)
def test_sonoma_research_identity_cannot_alias_a_different_region(field, replacement):
    value = payload()
    value["scope"]["region"][field] = replacement
    if field == "timezone":
        value["scope"]["window"]["timezone"] = replacement
    with pytest.raises(ValidationError):
        validate(value)


def test_autumn_repeated_hour_uses_actual_instants_for_occurrence_and_evidence():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from event_radar.models.regional import Occurrence, SourceEvidence

    la = ZoneInfo("America/Los_Angeles")
    # 01:45 daylight (08:45 UTC) precedes 01:15 standard (09:15 UTC).
    earlier = datetime(2026, 11, 1, 1, 45, tzinfo=la, fold=0)
    later = datetime(2026, 11, 1, 1, 15, tzinfo=la, fold=1)
    source = copy.deepcopy(payload()["opportunities"][0]["evidence"][1])
    source.update(occurrence_start=earlier, occurrence_end=later)
    assert SourceEvidence.model_validate(source).occurrence_end == later
    occurrence = copy.deepcopy(payload()["opportunities"][0]["occurrences"][0])
    occurrence.update(start=earlier, end=later)
    assert Occurrence.model_validate(occurrence).end == later
    source.update(occurrence_start=later, occurrence_end=earlier)
    with pytest.raises(ValidationError):
        SourceEvidence.model_validate(source)
    occurrence.update(start=later, end=earlier)
    with pytest.raises(ValidationError):
        Occurrence.model_validate(occurrence)


def test_autumn_repeated_hour_uses_actual_instants_for_publication_and_as_of():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from event_radar.models.regional import SourceEvidence

    la = ZoneInfo("America/Los_Angeles")
    earlier = datetime(2026, 11, 1, 1, 45, tzinfo=la, fold=0)
    later = datetime(2026, 11, 1, 1, 15, tzinfo=la, fold=1)
    source = copy.deepcopy(payload()["opportunities"][0]["evidence"][0])
    source.update(published_at=earlier, observed_at=later)
    assert SourceEvidence.model_validate(source).published_at == earlier
    source.update(published_at=later, observed_at=earlier)
    with pytest.raises(ValidationError, match="Publication"):
        SourceEvidence.model_validate(source)
    value = payload()
    value["scope"]["as_of"] = earlier
    value["sources"][0]["observed_at"] = later
    value["opportunities"][0]["evidence"][0]["observed_at"] = later
    with pytest.raises(ValidationError, match="as_of"):
        RegionalWeekendUniverse.model_validate(value)
    value["scope"]["as_of"] = later
    value["sources"][0]["observed_at"] = earlier
    value["opportunities"][0]["evidence"][0]["observed_at"] = earlier
    assert RegionalWeekendUniverse.model_validate(value).scope.as_of == later


def test_repeated_hour_distinct_instants_are_not_collapsed_as_duplicate_occurrences():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    la = ZoneInfo("America/Los_Angeles")
    value = payload()
    value["scope"]["window"]["friday"] = "2026-10-30"
    value["scope"]["as_of"] = "2026-10-31T22:00:00-07:00"
    event = value["opportunities"][0]
    first = event["occurrences"][0]
    evidence = event["evidence"][1]
    first["start"] = evidence["occurrence_start"] = datetime(2026, 11, 1, 1, 30, tzinfo=la, fold=0)
    first["end"] = evidence["occurrence_end"] = datetime(2026, 11, 1, 1, 40, tzinfo=la, fold=0)
    second = copy.deepcopy(first)
    second["occurrence_id"] = "workshop-standard-hour"
    evidence2 = copy.deepcopy(evidence)
    evidence2["evidence_id"] = "calendar-standard-hour"
    second["start"] = evidence2["occurrence_start"] = datetime(2026, 11, 1, 1, 30, tzinfo=la, fold=1)
    second["end"] = evidence2["occurrence_end"] = datetime(2026, 11, 1, 1, 40, tzinfo=la, fold=1)
    second["evidence_ids"] = [evidence2["evidence_id"]]
    event["evidence"].append(evidence2)
    event["occurrences"].append(second)
    assert len(RegionalWeekendUniverse.model_validate(value).opportunities[0].occurrences) == 2
