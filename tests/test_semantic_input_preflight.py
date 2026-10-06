"""Semantic admission/preflight regressions; external sockets are forbidden."""

from copy import deepcopy
from datetime import timedelta

import pytest
from pydantic import ValidationError

from event_radar.collectors.happening_sonoma import parse_happening_sonoma_event
from event_radar.models.regional import RegionalAnalysisRequest, RegionalOpportunity
from event_radar.shared import semantic_input
from event_radar.shared.collection import RegionalSourceDescriptor
from event_radar.shared.event_sources import (
    EventCollectorRegionalAdapter,
    event_to_regional_opportunity,
)
from event_radar.shared.semantic_analysis import enrich_regional_semantics
from event_radar.shared.semantic_input import SemanticInputPreflightError, preflight_semantic_inputs
from tests.test_regional_event_adapter import FakeCollector
from tests.test_regional_semantic_analysis import FakeSemanticProvider, fixture_universe

SENTINEL = "PRIVATE_RAW_PAYLOAD_SENTINEL"


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External network forbidden")

    monkeypatch.setattr("socket.socket.connect", blocked)


def inventory(count=107):
    universe = fixture_universe()
    event = universe.opportunities[0]
    items = []
    for index in range(count):
        payload = event.model_dump(mode="python")
        payload["opportunity_id"] = f"event-{index:03}"
        payload["title"] = f"Public fixture {index}"
        for occurrence_index, occurrence in enumerate(payload["occurrences"]):
            occurrence["occurrence_id"] = f"occurrence-{index}-{occurrence_index}"
        items.append(RegionalOpportunity.model_validate(payload))
    return universe.scope, tuple(items)


def outside_region(item):
    payload = item.model_dump(mode="python")
    payload["location"]["subdivision_code"] = "SC"
    for occurrence in payload["occurrences"]:
        occurrence["location"]["subdivision_code"] = "SC"
    return RegionalOpportunity.model_validate(payload)


async def test_fifth_batch_conflict_is_detected_before_first_call():
    scope, items = inventory()
    items = (*items[:46], outside_region(items[46]), *items[47:])
    # Reproduce the old incremental behavior: batches 1-4 validate, batch 5 fails.
    for offset in range(0, 40, 10):
        RegionalAnalysisRequest(scope=scope, opportunities=items[offset : offset + 10])
    with pytest.raises(ValidationError) as caught:
        RegionalAnalysisRequest(scope=scope, opportunities=items[40:50])
    assert caught.value.errors()[0]["type"] == "regional_outside_region"

    provider = FakeSemanticProvider()
    diagnostics = []
    with pytest.raises(SemanticInputPreflightError):
        await enrich_regional_semantics(
            scope, items, provider, batch_size=10, on_failure=diagnostics.append
        )
    assert provider.requests == []
    failure = diagnostics[0]
    assert failure.failure_category == "local_validation"
    assert failure.failure_code == "invalid_response"
    assert failure.provider_calls == failure.attempts == failure.result_count == 0
    assert failure.attempts_complete and failure.usage_complete
    assert failure.total_tokens == failure.estimated_model_cost_usd == 0
    assert failure.input_failure.model_dump() == {
        "phase": "inventory",
        "reason": "outside_region",
        "batch_number": 5,
        "opportunity_ids": ("event-046",),
        "source_ids": ("public-calendar", "public-feed"),
    }


async def test_all_107_inputs_and_batches_prepared_before_first_call(monkeypatch):
    scope, items = inventory()
    prepared = []
    original = semantic_input._analysis_input

    def tracked(item):
        prepared.append(item.opportunity_id)
        return original(item)

    monkeypatch.setattr(semantic_input, "_analysis_input", tracked)

    class Provider(FakeSemanticProvider):
        async def analyze(self, request, *, correction=None):
            assert len(prepared) == 107
            assert all(item.semantics is None for item in request.opportunities)
            return await super().analyze(request, correction=correction)

    provider = Provider()
    outcome = await enrich_regional_semantics(scope, items, provider, batch_size=10)
    assert [len(request.opportunities) for request in provider.requests] == [10] * 10 + [7]
    assert len(outcome.opportunities) == outcome.diagnostics.result_count == 107
    assert outcome.diagnostics.status == "success"


async def test_late_batch_transformation_error_still_costs_zero(monkeypatch):
    scope, items = inventory()
    original = semantic_input._analysis_input

    def broken(item):
        if item.opportunity_id == "event-106":
            RegionalOpportunity.model_validate({"title": SENTINEL})
        return original(item)

    monkeypatch.setattr(semantic_input, "_analysis_input", broken)
    provider = FakeSemanticProvider()
    diagnostics = []
    with pytest.raises(SemanticInputPreflightError):
        await enrich_regional_semantics(
            scope, items, provider, batch_size=10, on_failure=diagnostics.append
        )
    assert not provider.requests
    assert diagnostics[0].input_failure.phase == "batch"
    assert diagnostics[0].input_failure.batch_number == 11
    assert SENTINEL not in diagnostics[0].model_dump_json()


@pytest.mark.parametrize("kind", ["opportunity_id", "occurrence_id", "exact_occurrence"])
async def test_inventory_duplicates_across_batches_cost_zero(kind):
    scope, items = inventory()
    payload = items[-1].model_dump(mode="python")
    if kind == "opportunity_id":
        payload["opportunity_id"] = items[0].opportunity_id
    elif kind == "occurrence_id":
        payload["occurrences"][0]["occurrence_id"] = items[0].occurrences[0].occurrence_id
    else:
        payload["title"] = items[0].title
    items = (*items[:-1], RegionalOpportunity.model_validate(payload))
    provider = FakeSemanticProvider()
    with pytest.raises(SemanticInputPreflightError) as caught:
        await enrich_regional_semantics(scope, items, provider, batch_size=10)
    assert not provider.requests
    assert caught.value.detail.reason == (
        "duplicate_opportunity_identity"
        if kind == "opportunity_id"
        else "duplicate_occurrence_identity"
    )


@pytest.mark.parametrize("field", ["categories", "evidence"])
async def test_trusted_nested_bypass_revalidated_without_raw_payload(field):
    scope, items = inventory()
    invalid = items[-1].model_copy(update={field: {"state": SENTINEL}})
    provider = FakeSemanticProvider()
    diagnostics = []
    with pytest.raises(SemanticInputPreflightError) as caught:
        await enrich_regional_semantics(
            scope,
            (*items[:-1], invalid),
            provider,
            batch_size=10,
            on_failure=diagnostics.append,
        )
    assert not provider.requests
    assert caught.value.detail.phase == "opportunity"
    assert caught.value.detail.reason == "other_contract_violation"
    assert SENTINEL not in str(caught.value)
    assert SENTINEL not in diagnostics[0].model_dump_json()


@pytest.mark.parametrize("state,expected", [("SC", 0), ("CA", 1), (" California ", 1)])
async def test_source_location_conflict_is_explicitly_excluded_not_rewritten(state, expected):
    scope, _ = inventory()
    record = {
        "id": 4001,
        "title": "Synthetic public listing",
        "url": "https://happeningsonomacounty.com/event/synthetic-public/",
        "all_day": False,
        "utc_start_date": "2026-10-03 21:00:00",
        "utc_end_date": "2026-10-03 23:00:00",
        "venue": {"city": "Cloverdale", "state": state, "venue": "Public fixture hall"},
    }
    event = parse_happening_sonoma_event(deepcopy(record))
    assert event is not None
    if state == "SC":
        original = event_to_regional_opportunity(
            event, source_id="happening-sonoma-county", scope=scope, observed_at=scope.as_of
        )
        with pytest.raises(ValidationError):
            RegionalAnalysisRequest(scope=scope, opportunities=(original,))
    adapter = EventCollectorRegionalAdapter(
        descriptor=RegionalSourceDescriptor(
            source_id="happening-sonoma-county",
            source_class="regional_calendar",
            mechanism="api",
            coverage_description="Public fixture",
            opportunity_kinds=("event",),
        ),
        collector=FakeCollector([event]),
    )
    result = await adapter.collect(scope, observed_at=scope.as_of)
    assert len(result.opportunities) == expected
    if expected:
        assert result.opportunities[0].location.subdivision_code == "CA"
        assert result.exclusions == ()
        assert len(preflight_semantic_inputs(scope, result.opportunities, batch_size=10)) == 1
    else:
        assert result.exclusions[0].reason == "outside_region"
        assert result.exclusions[0].source_record_id == "4001"
        assert result.exclusions[0].source_id == "happening-sonoma-county"
    assert event.state == state.strip()


def test_preflight_after_as_of_has_bounded_rule():
    scope, items = inventory(1)
    payload = items[0].model_dump(mode="python")
    payload["evidence"][0]["observed_at"] = scope.as_of + timedelta(days=1)
    item = RegionalOpportunity.model_validate(payload)
    with pytest.raises(SemanticInputPreflightError) as caught:
        preflight_semantic_inputs(scope, (item,), batch_size=10)
    assert caught.value.detail.reason == "after_as_of"


def test_preflight_outside_window_has_bounded_rule():
    scope, items = inventory(1)
    payload = items[0].model_dump(mode="python")
    for evidence in payload["evidence"]:
        for field in ("occurrence_start", "occurrence_end"):
            if evidence[field] is not None:
                evidence[field] += timedelta(days=7)
    for occurrence in payload["occurrences"]:
        occurrence["start"] += timedelta(days=7)
        if occurrence["end"] is not None:
            occurrence["end"] += timedelta(days=7)
    item = RegionalOpportunity.model_validate(payload)
    with pytest.raises(SemanticInputPreflightError) as caught:
        preflight_semantic_inputs(scope, (item,), batch_size=10)
    assert caught.value.detail.reason == "outside_window"
