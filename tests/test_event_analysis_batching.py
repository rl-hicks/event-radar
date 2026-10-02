import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from openai import APITimeoutError, AsyncOpenAI, RateLimitError

import event_radar.services.event_analysis as analysis_module
import event_radar.services.pipeline as pipeline_module
from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.event_analysis import (
    EventDisposition,
    ExperienceGroupProposal,
    ScrapedAnalysisDiagnostics,
    ScrapedEventAnalysis,
    ScrapedEventAnalysisOutcome,
)
from event_radar.models.web_discovery import WebDiscoveryOutcome, WebDiscoveryResult
from event_radar.services.audit import write_audit_artifacts
from event_radar.services.event_analysis import (
    SCRAPED_EVENT_ANALYSIS_BATCH_SIZE,
    OpenAIEventAnalysisService,
    analyze_scraped_events_with_fallback,
)
from event_radar.services.event_cards import (
    EventAnalysisReferenceError,
    build_scraped_event_cards,
    build_web_event_cards,
)
from event_radar.services.pipeline import build_event_intelligence
from tests.curation_helpers import event
from tests.test_audit import fixture_pipeline
from tests.test_audit import outcome as curation_outcome
from tests.test_event_analysis import judgment, request
from tests.test_pipeline_degradation import _discovered_event


class BatchResponses:
    """Synthetic provider: derives IDs only from the current batch payload."""

    def __init__(self, value, *, failures=None, malformed=None, grouped=False, repair=False):
        self.value = value
        self.failures = failures or set()
        self.malformed = malformed
        self.grouped = grouped
        self.repair = repair
        self.calls = []
        self.payloads = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        payload, _ = json.JSONDecoder().raw_decode(kwargs["input"])
        self.payloads.append(payload)
        ids = [item["event_id"] for item in payload["events"]]
        index = (
            next(index for index, item in enumerate(self.value.events) if item.event_id == ids[0])
            // SCRAPED_EVENT_ANALYSIS_BATCH_SIZE
            + 1
        )
        if index in self.failures:
            raise APITimeoutError(request=httpx.Request("POST", "https://example.test"))
        events = [judgment(item, EventDisposition.RETAIN) for item in reversed(ids)]
        groups = []
        if (
            self.malformed
            and index == 2
            and (not self.repair or "CORRECTION REQUIRED" not in kwargs["input"])
        ):
            if self.malformed == "missing":
                events.pop()
            elif self.malformed == "duplicate":
                events[-1] = events[0]
            elif self.malformed == "foreign":
                events[-1] = judgment(self.value.events[0].event_id, EventDisposition.RETAIN)
            elif self.malformed == "invented":
                events[-1] = judgment("invented", EventDisposition.RETAIN)
            elif self.malformed == "none":
                events = None
        if self.grouped:
            for item in events:
                item.experience_group_id = "same-group"
            groups = [
                ExperienceGroupProposal(
                    group_id="same-group",
                    occurrence_ids=list(reversed(ids)),
                    experience_summary="Grouped within one batch.",
                )
            ]
        return SimpleNamespace(
            output_parsed=(
                ScrapedEventAnalysis(events=events, experience_groups=groups)
                if events is not None
                else None
            ),
            status="completed",
            error=None,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
        )


def service(responses):
    return OpenAIEventAnalysisService(
        api_key="synthetic-key",
        model="test",
        prompt_path=Path("prompts/event_analysis.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, SimpleNamespace(responses=responses)),
    )


@pytest.mark.parametrize(
    "count,sizes",
    [
        (0, []),
        (1, [1]),
        (12, [12]),
        (35, [35]),
        (36, [35, 1]),
        (70, [35, 35]),
        (93, [35, 35, 23]),
    ],
)
async def test_boundaries_deterministic_order_context_and_no_lost_or_duplicate_ids(count, sizes):
    value = request(count)
    fake = BatchResponses(value)
    result = await analyze_scraped_events_with_fallback(service(fake), value)
    diagnostic = result.diagnostics
    assert isinstance(diagnostic, ScrapedAnalysisDiagnostics)
    assert [len(payload["events"]) for payload in fake.payloads] == sizes
    assert [item["event_id"] for payload in fake.payloads for item in payload["events"]] == [
        item.event_id for item in value.events
    ]
    assert (
        [item.event_id for item in result.analysis.events]
        == [item.event_id for item in value.events]
        if count
        else result.analysis is None
    )
    assert diagnostic.status == ("success" if count else "skipped")
    assert diagnostic.batch_count == len(sizes)
    assert diagnostic.batch_size == 35
    assert diagnostic.result_count == count
    assert diagnostic.attempts == len(sizes)
    expected_context = value.model_dump(mode="json", exclude={"events"})
    for payload, call in zip(fake.payloads, fake.calls, strict=True):
        assert {key: val for key, val in payload.items() if key != "events"} == expected_context
        assert call["instructions"] == Path("prompts/event_analysis.md").read_text()
        assert call["reasoning"] == {"effort": "low"}
        assert call["store"] is False


@pytest.mark.parametrize("failures", [set(), {1}, {2}, {3}, {1, 2, 3}])
async def test_batch_failures_preserve_partition_cards_and_aggregate_metrics(
    failures,
    monkeypatch,
    capsys,
):
    value = request(93)
    fake = BatchResponses(value, failures=failures)
    clock = iter([0.0, 2.0, 10.0, 13.0, 20.0, 25.0])
    monkeypatch.setattr(analysis_module, "monotonic", lambda: next(clock))
    result = await analyze_scraped_events_with_fallback(service(fake), value)
    diagnostic = result.diagnostics
    fallback_count = sum([35, 35, 23][index - 1] for index in failures)
    assert diagnostic.status == (
        "success" if not failures else "fallback" if len(failures) == 3 else "partial"
    )
    assert diagnostic.success == (not failures)
    assert diagnostic.successful_batch_count == 3 - len(failures)
    assert diagnostic.failed_batch_count == len(failures)
    assert diagnostic.fallback_event_count == fallback_count
    assert diagnostic.result_count == 93 - fallback_count
    assert diagnostic.input_count == 93
    assert diagnostic.attempts == 3  # Timeouts never retry.
    assert diagnostic.latency_seconds == 10
    for field, per_call in [("input_tokens", 100), ("output_tokens", 20), ("total_tokens", 120)]:
        assert getattr(diagnostic, field) == (
            per_call * (3 - len(failures)) if len(failures) < 3 else None
        )
    assert [batch.batch_index for batch in diagnostic.batches] == [1, 2, 3]
    assert [batch.latency_seconds for batch in diagnostic.batches] == [2, 3, 5]
    semantic_ids = [item.event_id for item in result.analysis.events] if result.analysis else []
    combined = semantic_ids + result.fallback_event_ids
    assert len(combined) == len(set(combined)) == 93
    assert set(combined) == {item.event_id for item in value.events}
    cards = build_scraped_event_cards(
        value,
        result.analysis,
        fallback_event_ids=result.fallback_event_ids,
    )
    assert [card.candidate_id for card in cards] == [item.event_id for item in value.events]
    assert sum(not card.semantic_analysis_available for card in cards) == fallback_count
    assert sum(card.semantic_analysis_available for card in cards) == 93 - fallback_count
    for card in cards:
        assert card.occurrences == [
            next(item for item in value.events if item.event_id == card.candidate_id)
        ]
    output = capsys.readouterr().out
    assert f"status={diagnostic.status}" in output
    for index in failures:
        assert f"batch={index}/3 status=fallback" in output
        assert "fallback_reason=APITimeoutError" in output
        assert "error_type=APITimeoutError" in output
    assert value.personal_experience_context not in output
    assert "synthetic-key" not in output


@pytest.mark.parametrize("kind", ["missing", "duplicate", "foreign", "invented", "none"])
async def test_invalid_batch_output_cannot_corrupt_adjacent_batches(kind):
    value = request(93)
    fake = BatchResponses(value, malformed=kind)
    result = await analyze_scraped_events_with_fallback(service(fake), value)
    assert result.diagnostics.status == "partial"
    assert result.diagnostics.result_count == 58
    assert result.fallback_event_ids == [item.event_id for item in value.events[35:70]]
    attempts = 3 if kind == "none" else 4
    assert result.diagnostics.attempts == attempts
    assert result.diagnostics.total_tokens == attempts * 120
    assert result.diagnostics.batches[1].provider_error_type == "MalformedOutput"
    cards = build_scraped_event_cards(
        value,
        result.analysis,
        fallback_event_ids=result.fallback_event_ids,
    )
    assert len(cards) == 93


async def test_corrective_retry_counts_both_responses_and_preserves_other_batches():
    value = request(93)
    result = await analyze_scraped_events_with_fallback(
        service(BatchResponses(value, malformed="missing", repair=True)),
        value,
    )
    assert result.diagnostics.status == "success"
    assert result.diagnostics.attempts == 4
    assert result.diagnostics.input_tokens == 400
    assert result.diagnostics.output_tokens == 80
    assert result.diagnostics.total_tokens == 480


async def test_groups_are_local_namespaced_and_deterministically_ordered():
    value = request(93)
    result = await analyze_scraped_events_with_fallback(
        service(BatchResponses(value, grouped=True)),
        value,
    )
    assert [group.group_id for group in result.analysis.experience_groups] == [
        "batch-1:same-group",
        "batch-2:same-group",
        "batch-3:same-group",
    ]
    cards = build_scraped_event_cards(value, result.analysis)
    assert len(cards) == 3
    assert [len(card.occurrences) for card in cards] == [35, 35, 23]
    assert [item.event_id for card in cards for item in card.occurrences] == [
        item.event_id for item in value.events
    ]
    assert len({card.candidate_id for card in cards}) == 3


async def test_quota_diagnostics_are_safe_and_distinct_from_timeout(capsys):
    class QuotaResponses:
        async def parse(self, **kwargs):
            raise RateLimitError(
                "secret raw context synthetic-key",
                response=httpx.Response(429, request=httpx.Request("POST", "https://example.test")),
                body={
                    "code": "insufficient_quota",
                    "type": "insufficient_quota",
                    "message": "secret raw context synthetic-key",
                },
            )

    result = await analyze_scraped_events_with_fallback(service(QuotaResponses()), request(1))
    batch = result.diagnostics.batches[0]
    assert batch.provider_error_code == "insufficient_quota"
    assert batch.provider_status_code == 429
    assert batch.provider_error_type == "RateLimitError"
    assert batch.attempts == 1
    serialized = result.model_dump_json() + capsys.readouterr().out
    assert "insufficient_quota" in serialized
    assert "secret raw context" not in serialized
    assert "synthetic-key" not in serialized


async def test_invalid_input_and_batch_size_fail_before_provider_calls():
    value = request(1)
    fake = BatchResponses(value)
    with pytest.raises(ValueError, match="positive"):
        await analyze_scraped_events_with_fallback(service(fake), value, batch_size=0)
    duplicate = value.model_copy(update={"events": value.events * 2})
    with pytest.raises(EventAnalysisReferenceError, match="unique"):
        await analyze_scraped_events_with_fallback(service(fake), duplicate)
    assert not fake.calls


async def test_partial_pipeline_keeps_full_ai3_universe_web_cards_and_audit(
    monkeypatch,
    tmp_path,
):
    pipeline = fixture_pipeline()
    events = [event(title=f"Event {index}", source_id=str(index)) for index in range(93)]
    pipeline = replace(pipeline, valid_events=events)
    value = pipeline_module._analysis_request(pipeline)
    fake = BatchResponses(value, failures={2})
    discovery = _discovered_event()
    web_calls = []

    async def discover(service, request):
        web_calls.append(request)
        return WebDiscoveryOutcome(
            result=WebDiscoveryResult(discoveries=[discovery]),
            valid_discoveries=[discovery],
            duplicates_removed=0,
            diagnostics=AIStageDiagnostics(
                stage="web_event_discovery",
                model="test",
                success=True,
                input_count=93,
                result_count=1,
                attempts=1,
            ),
        )

    monkeypatch.setattr(pipeline_module, "discover_events_with_fallback", discover)
    intelligence = await build_event_intelligence(
        pipeline,
        analysis_service=service(fake),
        web_service=SimpleNamespace(),
    )
    assert len(web_calls) == 1
    assert len(web_calls[0].existing_events) == 93
    assert intelligence.web_event_cards == build_web_event_cards([discovery])
    assert len(intelligence.context.event_cards) == 94
    assert intelligence.context.event_cards == intelligence.combined_event_cards
    assert len(intelligence.context.hike_candidates) == 1

    from event_radar.models.curation import WeekendCuration
    from tests.test_llm_curation import FakeClient, response
    from tests.test_llm_curation import service as final_service

    final_client = FakeClient(
        [
            response(
                WeekendCuration(
                    weekend_read=["Synthetic review."],
                    event_options=[],
                    hike_options=[],
                    notable_near_misses=[],
                    important_unknowns=[],
                )
            )
        ]
    )
    final_result = await final_service(final_client).curate(intelligence.context)
    assert final_result.diagnostics.success
    sent = json.loads(final_client.responses.calls[0]["input"])
    assert sent["event_cards"] == [
        card.model_dump(mode="json") for card in intelligence.combined_event_cards
    ]
    assert len(sent["event_cards"]) == 94
    assert (
        final_client.responses.calls[0]["instructions"]
        == Path("prompts/weekend_curation.md").read_text()
    )
    assert any("partially degraded" in note for note in intelligence.context.event_pipeline_notes)
    assert sum(card.semantic_analysis_available for card in intelligence.scraped_event_cards) == 58

    artifact = write_audit_artifacts(
        pipeline,
        intelligence,
        curation_outcome(94, 1),
        output_root=tmp_path,
        llm_requested=True,
    )
    manifest = json.loads((artifact.output_directory / "00-manifest.json").read_text())
    scraped = manifest["scraped_analysis"]
    assert scraped["semantic_card_count"] == 58
    assert scraped["fallback_factual_card_count"] == 35
    assert scraped["diagnostics"]["status"] == "partial"
    assert scraped["diagnostics"]["batch_count"] == 3
    assert [batch["success"] for batch in scraped["diagnostics"]["batches"]] == [True, False, True]
    saved = ScrapedEventAnalysisOutcome.model_validate_json(
        (artifact.output_directory / "06-scraped-event-analysis.json").read_text()
    )
    assert saved == intelligence.analysis_outcome


@pytest.mark.parametrize(
    "status,code",
    [
        ("incomplete", "max_output_tokens"),
        ("failed", "server_error"),
    ],
)
async def test_response_level_failures_keep_safe_reason_and_usage(status, code, capsys):
    class Responses:
        async def parse(self, **kwargs):
            return SimpleNamespace(
                status=status,
                error=(
                    SimpleNamespace(code=code, message="PRIVATE RESPONSE MESSAGE")
                    if status == "failed"
                    else None
                ),
                incomplete_details=SimpleNamespace(reason=code),
                output_parsed=None,
                usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
            )

    result = await analyze_scraped_events_with_fallback(service(Responses()), request(1))
    assert result.diagnostics.batches[0].provider_error_code == code
    assert result.diagnostics.total_tokens == 120
    assert result.diagnostics.attempts == 1
    assert code in capsys.readouterr().out
    assert "PRIVATE RESPONSE MESSAGE" not in result.model_dump_json()


async def test_provider_timeout_configuration_and_sdk_retries_unchanged(monkeypatch):
    value = request(36)
    fake = BatchResponses(value)
    clients = []

    def client(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(responses=fake)

    monkeypatch.setattr(analysis_module, "AsyncOpenAI", client)
    configured = OpenAIEventAnalysisService(
        api_key="synthetic-key",
        model="test",
        prompt_path=Path("prompts/event_analysis.md"),
        timeout_seconds=120,
    )
    await analyze_scraped_events_with_fallback(configured, value)
    assert clients == [
        {"api_key": "synthetic-key", "timeout": 120, "max_retries": 0},
        {"api_key": "synthetic-key", "timeout": 120, "max_retries": 0},
    ]


async def test_mixed_cards_keep_existing_reject_semantics():
    value = request(36)
    fake = BatchResponses(value, failures={2})
    original = fake.parse

    async def parse(**kwargs):
        response = await original(**kwargs)
        response.output_parsed.events[0].disposition = EventDisposition.REJECT
        return response

    fake.parse = parse
    result = await analyze_scraped_events_with_fallback(service(fake), value)
    assert len(result.analysis.events) == 35
    assert len(result.fallback_event_ids) == 1
    cards = build_scraped_event_cards(
        value,
        result.analysis,
        fallback_event_ids=result.fallback_event_ids,
    )
    assert len(cards) == 35  # One explicit semantic reject; no lost input judgments.
    assert sum(not card.semantic_analysis_available for card in cards) == 1


@pytest.mark.parametrize(
    "count,failures,status,semantic_count,factual_count",
    [
        (36, set(), "success", 36, 0),
        (36, {2}, "partial", 35, 1),
        (36, {1, 2}, "fallback", 0, 36),
        (0, set(), "skipped", 0, 0),
    ],
)
@pytest.mark.parametrize("final_success", [True, False])
async def test_ai1_status_reaches_console_telegram_packet_and_audit(
    count,
    failures,
    status,
    semantic_count,
    factual_count,
    final_success,
    monkeypatch,
    tmp_path,
    capsys,
):
    from event_radar.main import _print_pipeline_diagnostics
    from event_radar.models.curation import WeekendCuration
    from event_radar.services.curation_rendering import (
        render_chatgpt_packet,
        render_telegram_curation_summary,
    )
    from tests.test_llm_curation import FakeClient, response
    from tests.test_llm_curation import service as final_service

    pipeline = replace(
        fixture_pipeline(),
        valid_events=[
            event(title=f"Event {index}", source_id=str(index)) for index in range(count)
        ],
    )
    value = pipeline_module._analysis_request(pipeline)
    fake = BatchResponses(value, failures=failures)

    async def discover(service, request):
        return WebDiscoveryOutcome(
            result=WebDiscoveryResult(discoveries=[]),
            valid_discoveries=[],
            duplicates_removed=0,
            diagnostics=AIStageDiagnostics(
                stage="web_event_discovery",
                model="test",
                success=True,
                input_count=count,
                result_count=0,
                attempts=1,
            ),
        )

    monkeypatch.setattr(pipeline_module, "discover_events_with_fallback", discover)
    intelligence = await build_event_intelligence(
        pipeline,
        analysis_service=service(fake),
        web_service=SimpleNamespace(),
    )
    assert intelligence.analysis_outcome.diagnostics.status == status
    assert intelligence.analysis_outcome.diagnostics.success == (status == "success")
    assert sum(card.semantic_analysis_available for card in intelligence.scraped_event_cards) == (
        semantic_count
    )
    assert sum(
        not card.semantic_analysis_available for card in intelligence.scraped_event_cards
    ) == (factual_count)
    assert intelligence.context.event_cards == intelligence.combined_event_cards
    assert len(intelligence.context.event_cards) == count
    final_result = curation_outcome(count, 1)
    if final_success:
        final_client = FakeClient(
            [
                response(
                    WeekendCuration(
                        weekend_read=["Synthetic review."],
                        event_options=[],
                        hike_options=[],
                        notable_near_misses=[],
                        important_unknowns=[],
                    )
                )
            ]
        )
        final_result = await final_service(final_client).curate(intelligence.context)
        payload = json.loads(final_client.responses.calls[0]["input"])
        assert len(payload["event_cards"]) == count
        assert payload["event_pipeline_notes"] == intelligence.context.event_pipeline_notes
    capsys.readouterr()
    _print_pipeline_diagnostics(pipeline, intelligence, final_result)
    summary = capsys.readouterr().out
    assert f"- scraped_event_analysis: {status}," in summary
    assert "- web_event_discovery: success," in summary

    packet = render_chatgpt_packet(intelligence.context, final_result)
    telegram = render_telegram_curation_summary(intelligence.context, final_result)
    expected = {
        "partial": (
            "Scraped-event semantic analysis partially degraded; successful batches were preserved "
            "and some scraped events use broad factual fallback cards."
        ),
        "fallback": (
            "Scraped-event semantic analysis was unavailable; broad factual scraped cards "
            "were preserved without pretending analysis succeeded."
        ),
        "skipped": (
            "AI #1 scraped-event analysis was skipped because no fixed-feed events were available."
        ),
    }
    for rendered in (packet, telegram):
        if status == "success":
            assert "partially degraded" not in rendered
            assert "Scraped-event semantic analysis was unavailable" not in rendered
            assert "Event research status" not in rendered
        else:
            assert "Event research status" in rendered
            assert expected[status] in rendered
        if status in {"partial", "skipped"}:
            assert "Scraped-event semantic analysis was unavailable" not in rendered

    artifact = write_audit_artifacts(
        pipeline,
        intelligence,
        final_result,
        output_root=tmp_path,
        llm_requested=True,
    )
    manifest = json.loads((artifact.output_directory / "00-manifest.json").read_text())
    scraped = manifest["scraped_analysis"]
    assert scraped["status"] == status
    assert scraped["success"] == (status == "success")
    assert scraped["ran"] == (count > 0)
    assert scraped["semantic_card_count"] == semantic_count
    assert scraped["fallback_factual_card_count"] == factual_count
    assert scraped["diagnostics"]["status"] == status
    saved = json.loads((artifact.output_directory / "06-scraped-event-analysis.json").read_text())
    assert saved["diagnostics"]["status"] == status
    assert (artifact.output_directory / "13-final-packet.md").read_text() == packet
    if status == "skipped":
        assert fake.calls == []
