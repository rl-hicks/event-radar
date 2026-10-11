"""WP5 diagnostics round-trip through a separate disposable PostgreSQL fixture."""

import asyncio
from dataclasses import replace

import httpx
import pytest
from openai import AsyncOpenAI

from event_radar.db.models import RegionalResearchRun, RegionalUniverseSnapshot
from event_radar.db.session import build_session_factory
from event_radar.models.regional import RegionalWeekendUniverse
from event_radar.models.regional_discovery import AdaptiveDiscoverySummary
from event_radar.shared.worker import run_regional_worker
from tests.test_adaptive_regional_discovery_provider import plan, provider, research_result
from tests.test_discovery_failure_evidence import SENTINEL, envelope
from tests.test_shared_worker_integration import budget, read, scope
from tests.test_shared_worker_integration import worker as worker


@pytest.mark.parametrize("stage", ["planning", "research", "verification"])
@pytest.mark.parametrize("prior_good", [False, True])
async def test_sdk_failure_persists_safe_stage_evidence_and_preserves_universe(
    worker, stage, prior_good
):
    deps, _, _, _ = worker
    good = await run_regional_worker(scope(), deps, budget=budget()) if prior_good else None
    original = read(deps) if prior_good else None
    failure_index = {"planning": 0, "research": 1, "verification": 2}[stage]
    calls = []

    def respond(request):
        index = len(calls)
        calls.append(index)
        body = envelope(plan() if index == 0 else research_result(), web=index != 0)
        if index == failure_index:
            body["output"][-1]["content"][0]["text"] = SENTINEL
            body["usage"] = {"input_tokens": 100}  # partial, never fabricated zero
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            adapter = provider(client)
            result = await run_regional_worker(
                scope(),
                replace(deps, planner=adapter, researcher=adapter, verifier=adapter),
                budget=budget(),
                refresh=prior_good,
            )
    assert len(calls) == failure_index + 1
    assert result.status == "partial" and result.failure_code == "invalid_response"
    if prior_good:
        assert read(deps) == original
        assert read(deps).snapshot_id == good.snapshot_id
    else:
        assert read(deps).snapshot_id == result.snapshot_id
        assert read(deps).quality_status == "partial"
    with build_session_factory(deps.engine)() as session:
        run = session.get(RegionalResearchRun, result.run_id)
        snapshot = session.get(RegionalUniverseSnapshot, result.snapshot_id)
        assert run.status == snapshot.quality_status == "partial"
        assert run.discovery_summary == snapshot.discovery_summary
        detail = AdaptiveDiscoverySummary.model_validate(run.discovery_summary)
        assert detail.stop_reason == "provider_failure"
        assert detail.operations[-1].stage == stage
        assert detail.operations[-1].failure_category == "sdk_parse"
        assert detail.operations[-1].structured_output == "invalid"
        assert detail.operations[-1].response_received is True
        assert detail.operations[-1].output_tokens is None
        assert detail.operations[-1].estimated_model_cost_usd is None
        assert detail.usage.model_cost_complete is False
        restored = RegionalWeekendUniverse.model_validate(snapshot.universe_payload)
        assert len(restored.opportunities) == 1  # valid collected opportunity is retained
        assert restored.opportunities[0].semantics
        diagnostic = next(
            item for item in restored.diagnostics if item.stage == "complementary_discovery"
        )
        assert diagnostic.status == "fallback" and diagnostic.usage_complete is False
        serialized = str(
            (run.diagnostics_payload, run.discovery_summary, snapshot.universe_payload)
        )
        assert SENTINEL not in serialized
        for prohibited in (
            "api_key",
            "user_context",
            "permanent_directions",
            "temporary_directions",
            "telegram",
        ):
            assert prohibited not in serialized.lower()


async def test_transport_unknowns_roundtrip_without_false_zero(worker):
    deps, _, _, _ = worker

    def respond(request):
        raise httpx.ReadTimeout(SENTINEL, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            result = await run_regional_worker(
                scope(), replace(deps, planner=provider(client)), budget=budget()
            )
    assert result.status == "partial"
    persisted = read(deps)
    detail = AdaptiveDiscoverySummary.model_validate(persisted.discovery_summary)
    assert detail.operations[0].tool_calls is None
    assert detail.operations[0].total_tokens is None
    assert detail.operations[0].estimated_model_cost_usd is None
    assert detail.usage.web_search_calls == 0  # known subtotal, explicitly incomplete
    assert not detail.usage.web_search_calls_complete
    assert not detail.usage.model_cost_complete
    assert detail.usage.completed_model_calls == 0
    assert SENTINEL not in str(persisted)


@pytest.mark.parametrize("mode", ["local_error", "timeout"])
async def test_fatal_discovery_evidence_and_last_good_survive(worker, mode):
    deps, _, _, _ = worker
    good = await run_regional_worker(scope(), deps, budget=budget())

    class Broken:
        model_id = "offline"

        async def research(self, *args, **kwargs):
            if mode == "timeout":
                await asyncio.Event().wait()
            raise RuntimeError(SENTINEL)

    result = await run_regional_worker(
        scope(),
        replace(deps, researcher=Broken()),
        budget=replace(budget(), timeout_seconds=0.15),
        refresh=True,
    )
    assert result.status == "failed" and result.snapshot_id is None
    assert read(deps).snapshot_id == good.snapshot_id
    with build_session_factory(deps.engine)() as session:
        run = session.get(RegionalResearchRun, result.run_id)
        summary = AdaptiveDiscoverySummary.model_validate(run.discovery_summary)
        assert summary.operations[0].stage == "planning"
        assert summary.operations[0].total_tokens is not None
        assert summary.operations[-1].stage == "research"
        assert summary.operations[-1].total_tokens is None
        assert not summary.usage.model_cost_complete
        assert not summary.usage.attempts_complete
        diagnostic = run.diagnostics_payload["stages"][-1]
        assert diagnostic["failure_category"] == (
            "timeout" if mode == "timeout" else "local_invariant"
        )
        assert SENTINEL not in str((run.discovery_summary, run.diagnostics_payload))
