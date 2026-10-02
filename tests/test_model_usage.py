from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from openai import AsyncOpenAI

from event_radar.config import DEFAULT_OPENAI_MODEL, Settings
from event_radar.curation_config import DEFAULT_CURATION_CONFIG
from event_radar.models.token_usage import (
    ModelTokenPricing,
    TokenUsage,
    aggregate_token_usage,
    format_token_usage,
    parse_token_usage,
)
from event_radar.models.web_discovery import WebDiscoveryResult
from event_radar.services.event_analysis import analyze_scraped_events_with_fallback
from event_radar.services.llm_curation import OpenAICurationService, curate_with_fallback
from event_radar.services.web_event_discovery import (
    OpenAIWebDiscoveryService,
    discover_events_with_fallback,
)
from tests.test_event_analysis import request as analysis_request
from tests.test_event_analysis_batching import BatchResponses
from tests.test_event_analysis_batching import service as analysis_service
from tests.test_llm_curation import FakeClient, curation, recommendation_context, response, service
from tests.test_web_event_discovery import request as web_request

PRICING = ModelTokenPricing(2.0, 0.1, 10.0)


def usage(cached=40):
    value = SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120)
    if cached is not None:
        value.input_tokens_details = SimpleNamespace(cached_tokens=cached)
    return value


def test_central_model_and_configuration(monkeypatch):
    for key in [
        "OPENAI_MODEL",
        "OPENAI_EVENT_ANALYSIS_MODEL",
        "OPENAI_WEB_DISCOVERY_MODEL",
        "OPENAI_CURATION_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    config = Settings(_env_file=None)
    assert DEFAULT_OPENAI_MODEL == "gpt-6.1-sol"
    assert config.resolved_event_analysis_model == DEFAULT_OPENAI_MODEL
    assert config.resolved_web_discovery_model == DEFAULT_OPENAI_MODEL
    assert config.resolved_curation_model == DEFAULT_OPENAI_MODEL
    assert OpenAICurationService(api_key=None).model == DEFAULT_OPENAI_MODEL
    assert config.openai_timeout_seconds == 120
    assert DEFAULT_CURATION_CONFIG.reasoning_effort == "medium"
    for field, rate in [
        ("openai_input_usd_per_million", 2),
        ("openai_cached_input_usd_per_million", 0.1),
        ("openai_output_usd_per_million", 10),
    ]:
        assert Settings.model_fields[field].default == rate
    overridden = Settings(_env_file=None, openai_input_usd_per_million=3)
    assert ModelTokenPricing.from_settings(overridden).input_usd_per_million == 3


@pytest.mark.parametrize(
    "cached,cost", [(40, 0.000324), (None, 0.0004), (0, 0.0004), (100, 0.00021), (150, 0.000215)]
)
def test_usage_and_cost_without_cache_double_counting(cached, cost):
    parsed = parse_token_usage(usage(cached), PRICING)
    assert parsed.input_tokens == 100
    assert parsed.cached_input_tokens == cached
    assert parsed.output_tokens == 20
    assert parsed.total_tokens == 120
    assert parsed.estimated_model_cost_usd == pytest.approx(cost)
    assert "estimated_model_cost_usd=" in format_token_usage(parsed)


@pytest.mark.parametrize(
    "value",
    [None, SimpleNamespace(), SimpleNamespace(total_tokens=120), SimpleNamespace(input_tokens=100)],
)
def test_optional_usage_fields(value):
    parsed = parse_token_usage(value, PRICING)
    assert parsed.estimated_model_cost_usd is None
    assert parsed.total_tokens == getattr(value, "total_tokens", None)
    assert "estimated_model_cost_usd=n/a" in format_token_usage(parsed)


def test_aggregation_preserves_known_subtotals_and_unknowns():
    assert aggregate_token_usage([]) == TokenUsage()
    assert aggregate_token_usage([TokenUsage(), TokenUsage()]) == TokenUsage()
    parsed = parse_token_usage(usage(), PRICING)
    assert aggregate_token_usage([TokenUsage(), parsed]) == parsed
    assert parse_token_usage(
        usage(40), ModelTokenPricing(4, 0.2, 20)
    ).estimated_model_cost_usd == pytest.approx(0.000648)


class UsageBatchResponses(BatchResponses):
    async def parse(self, **kwargs):
        result = await super().parse(**kwargs)
        result.usage = usage()
        return result


@pytest.mark.asyncio
async def test_batches_and_all_stages_aggregate_with_valid_reasoning(capsys):
    request = analysis_request(count=71)
    batches = UsageBatchResponses(request)
    analysis = await analyze_scraped_events_with_fallback(analysis_service(batches), request)
    assert analysis.diagnostics.batch_count == 3
    assert analysis.diagnostics.input_tokens == 300
    assert analysis.diagnostics.cached_input_tokens == 120
    assert analysis.diagnostics.output_tokens == 60
    assert analysis.diagnostics.total_tokens == 360
    assert analysis.diagnostics.estimated_model_cost_usd == pytest.approx(3 * 0.000324)
    for batch in analysis.diagnostics.batches:
        assert batch.estimated_model_cost_usd == pytest.approx(0.000324)
    _, request2 = web_request()
    web_response = SimpleNamespace(
        status="completed",
        error=None,
        output_parsed=WebDiscoveryResult(discoveries=[]),
        output=[SimpleNamespace(type="web_search_call")],
        usage=usage(),
    )
    fake_web = FakeClient([web_response])
    web_service = OpenAIWebDiscoveryService(
        api_key="test",
        model=DEFAULT_OPENAI_MODEL,
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, fake_web),
        pricing=PRICING,
    )
    web = await web_service.discover(request2)
    final_response = response(curation())
    final_response.usage = usage()
    fake_final = FakeClient([final_response])
    final = await service(fake_final).curate(recommendation_context())
    aggregate = aggregate_token_usage([analysis.diagnostics, web.diagnostics, final.diagnostics])
    assert aggregate.input_tokens == 500
    assert aggregate.cached_input_tokens == 200
    assert aggregate.output_tokens == 100
    assert aggregate.total_tokens == 600
    assert aggregate.estimated_model_cost_usd == pytest.approx(5 * 0.000324)
    for calls, effort in [
        (batches.calls, "low"),
        (fake_web.responses.calls, "low"),
        (fake_final.responses.calls, "medium"),
    ]:
        for call in calls:
            assert call["reasoning"] == {"effort": effort}
            assert effort in {"low", "medium", "high", "xhigh", "max"}
            assert effort not in {"none", "minimal"}
            assert "temperature" not in call and "top_p" not in call
    assert fake_web.responses.calls[0]["max_tool_calls"] == 6
    logs = capsys.readouterr().out
    assert "batch=1/3" in logs and "batch=3/3" in logs
    for field in [
        "input_tokens=100",
        "cached_input_tokens=40",
        "output_tokens=20",
        "total_tokens=120",
        "estimated_model_cost_usd=0.0003",
    ]:
        assert field in logs


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [None, SimpleNamespace()])
async def test_absent_telemetry_does_not_fail_any_stage(missing):
    request = analysis_request(count=1)

    class MissingUsageResponses(BatchResponses):
        async def parse(self, **kwargs):
            result = await super().parse(**kwargs)
            result.usage = missing
            return result

    analysis = await analyze_scraped_events_with_fallback(
        analysis_service(MissingUsageResponses(request)), request
    )
    assert analysis.diagnostics.success
    assert analysis.diagnostics.estimated_model_cost_usd is None
    _, request2 = web_request()
    result = SimpleNamespace(
        status="completed",
        error=None,
        output_parsed=WebDiscoveryResult(discoveries=[]),
        output=[SimpleNamespace(type="web_search_call")],
        usage=missing,
    )
    web_service = OpenAIWebDiscoveryService(
        api_key="test",
        model=DEFAULT_OPENAI_MODEL,
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, FakeClient([result])),
    )
    web = await discover_events_with_fallback(web_service, request2)
    assert web.diagnostics.success
    assert web.diagnostics.estimated_model_cost_usd is None
    result = response(curation())
    result.usage = missing
    final = await service(FakeClient([result])).curate(recommendation_context())
    assert final.diagnostics.success
    assert final.diagnostics.estimated_model_cost_usd is None


@pytest.mark.asyncio
async def test_retries_and_failure_keep_available_billed_usage():
    fake = FakeClient([response(curation(event_id="invented")), response(curation())])
    final = await service(fake).curate(recommendation_context())
    assert final.diagnostics.total_tokens == 300
    assert final.diagnostics.estimated_model_cost_usd == pytest.approx(0.0014)
    fake = FakeClient([response(curation(event_id="invented")), RuntimeError("offline")])
    final = await curate_with_fallback(service(fake), recommendation_context())
    assert not final.diagnostics.success
    assert final.diagnostics.total_tokens == 150
    assert final.diagnostics.estimated_model_cost_usd == pytest.approx(0.0007)
    request = analysis_request(count=36)
    batches = UsageBatchResponses(request, malformed="missing")
    analysis = await analyze_scraped_events_with_fallback(analysis_service(batches), request)
    assert not analysis.diagnostics.success
    assert analysis.diagnostics.estimated_model_cost_usd == pytest.approx(3 * 0.000324)
    assert analysis.diagnostics.batches[1].estimated_model_cost_usd == pytest.approx(2 * 0.000324)
    _, request2 = web_request()
    result = SimpleNamespace(status="incomplete", error=None, usage=usage())
    web_service = OpenAIWebDiscoveryService(
        api_key="test",
        model=DEFAULT_OPENAI_MODEL,
        prompt_path=Path("prompts/web_event_discovery.md"),
        timeout_seconds=120,
        client=cast(AsyncOpenAI, FakeClient([result])),
    )
    web = await discover_events_with_fallback(web_service, request2)
    assert not web.diagnostics.success
    assert web.diagnostics.estimated_model_cost_usd == pytest.approx(0.000324)


def test_pipeline_log_and_audit_aggregate(tmp_path, capsys):
    import json

    from event_radar.main import _print_pipeline_diagnostics
    from event_radar.services.audit import write_audit_artifacts
    from event_radar.services.pipeline import build_event_intelligence_without_ai
    from tests.test_audit import fixture_pipeline, outcome

    pipeline = fixture_pipeline()
    intelligence = build_event_intelligence_without_ai(
        pipeline, model=DEFAULT_OPENAI_MODEL, reason="Synthetic"
    )
    final = outcome(3, 1)
    for diagnostic in [
        intelligence.analysis_outcome.diagnostics,
        intelligence.web_outcome.diagnostics,
        final.diagnostics,
    ]:
        diagnostic.input_tokens = 100
        diagnostic.cached_input_tokens = 40
        diagnostic.output_tokens = 20
        diagnostic.total_tokens = 120
        diagnostic.estimated_model_cost_usd = 0.000324
    _print_pipeline_diagnostics(pipeline, intelligence, final)
    logs = capsys.readouterr().out
    assert (
        "aggregate model usage (available telemetry): input_tokens=300 "
        "cached_input_tokens=120 output_tokens=60 total_tokens=360 "
        "estimated_model_cost_usd=0.0010"
    ) in logs
    audit = write_audit_artifacts(
        pipeline, intelligence, final, output_root=tmp_path, llm_requested=False
    )
    manifest = json.loads((audit.output_directory / "00-manifest.json").read_text())
    assert manifest["aggregate_ai_tokens"] == 360
    assert manifest["aggregate_ai_usage"] == {
        "input_tokens": 300,
        "cached_input_tokens": 120,
        "output_tokens": 60,
        "total_tokens": 360,
        "estimated_model_cost_usd": 0.000972,
    }
