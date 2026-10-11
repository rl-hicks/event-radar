"""Real SDK parsing through deterministic HTTP, with external sockets forbidden."""

import asyncio
import json
import socket
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
from openai import APIResponseValidationError, AsyncOpenAI
from pydantic import PydanticInvalidForJsonSchema

from event_radar.models.regional_discovery import DiscoveryPlan
from event_radar.models.token_usage import TokenUsage
from event_radar.shared.discovery import DiscoveryProviderFailure, run_adaptive_discovery
from tests.test_adaptive_regional_discovery import (
    PACIFIC,
    Planner,
    Researcher,
    Verifier,
    budget,
    collection,
    novel_candidate,
    universe,
)
from tests.test_adaptive_regional_discovery_provider import (
    candidate,
    context,
    plan,
    provider,
    research_result,
    verification_result,
)

SENTINEL = "DO_NOT_PERSIST_RAW_CONTENT"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)


def envelope(value, *, web=True):
    return {
        "id": "resp_offline",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "offline",
        "error": None,
        "output": (
            [
                {
                    "type": "web_search_call",
                    "id": "ws_offline",
                    "status": "completed",
                    "action": {"type": "search", "query": "synthetic public event"},
                }
            ]
            if web
            else []
        )
        + [
            {
                "type": "message",
                "id": "msg_offline",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "annotations": [], "text": value.model_dump_json()}
                ],
            },
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 25,
            "total_tokens": 125,
            "input_tokens_details": {"cached_tokens": 20},
        },
    }


async def invoke(service, stage):
    if stage == "planning":
        return await service.plan(context())
    if stage == "research":
        return await service.research(context(), plan().tasks[0], max_web_search_calls=2)
    return await service.verify(context(), (candidate(),), max_web_search_calls=2)


@pytest.mark.parametrize(
    "stage,value",
    [
        ("planning", plan()),
        ("research", research_result()),
        ("verification", verification_result()),
    ],
)
async def test_real_sdk_valid_stages_and_request_bounds(stage, value):
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert body["store"] is False
        if stage != "planning":
            assert body["tool_choice"] == "required"
            assert body["max_tool_calls"] == 2
            assert body["tools"][0]["type"] == "web_search"
        else:
            assert "tools" not in body
        return httpx.Response(200, json=envelope(value, web=stage != "planning"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            result = await invoke(provider(client), stage)
    assert len(calls) == 1
    assert result.value == value
    assert result.tool_calls == int(stage != "planning")
    assert result.usage.total_tokens == 125
    assert result.latency_seconds >= 0


@pytest.mark.parametrize(
    "case,category,reason,structured,search",
    [
        ("missing", "response_behavior", "missing_structured_output", "missing", "observed"),
        ("incomplete", "response_behavior", "response_incomplete", "unknown", "observed"),
        ("error", "response_behavior", "response_error", "unknown", "observed"),
        ("absent_tool", "tool_behavior", "missing_required_web_search", "accepted", "absent"),
        ("malformed", "sdk_parse", "sdk_parse", "invalid", "observed"),
        ("invalid_schema", "sdk_parse", "sdk_parse", "invalid", "observed"),
        ("queued", "response_behavior", "response_not_completed", "unknown", "observed"),
        ("malformed_absent_tool", "sdk_parse", "sdk_parse", "invalid", "absent"),
    ],
)
async def test_sdk_failure_boundaries_preserve_received_usage(
    case, category, reason, structured, search
):
    body = envelope(research_result())
    if case == "missing":
        body["output"] = body["output"][:1]
    elif case == "incomplete":
        body["status"] = "incomplete"
        body["incomplete_details"] = {"reason": "max_output_tokens"}
        body["output"][-1]["content"][0]["text"] = SENTINEL
    elif case == "error":
        body["status"] = "failed"
        body["error"] = {"code": "server_error", "message": SENTINEL}
    elif case == "queued":
        body["status"] = "queued"
    elif case == "absent_tool":
        body["output"] = body["output"][1:]
    else:
        body["output"][-1]["content"][0]["text"] = (
            json.dumps({"private": SENTINEL}) if case == "invalid_schema" else SENTINEL
        )
        if case == "malformed_absent_tool":
            body["output"] = body["output"][1:]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            with pytest.raises(DiscoveryProviderFailure) as caught:
                await invoke(provider(client), "research")
    failure = caught.value
    assert failure.failure_category == category
    assert failure.reason == reason
    assert failure.response_received is True
    assert failure.structured_output == structured
    assert failure.required_web_search == search
    assert failure.usage.total_tokens == 125
    assert failure.usage.estimated_model_cost_usd is not None
    assert SENTINEL not in str(failure)


@pytest.mark.parametrize(
    "mode,category,received",
    [
        ("transport", "provider_transport", False),
        ("timeout", "timeout", False),
        (429, "provider_status", True),
        (503, "provider_status", True),
        (400, "provider_status", True),
    ],
)
async def test_no_hidden_retries_or_invented_billing(mode, category, received):
    calls = []

    def respond(request):
        calls.append(request)
        if mode == "transport":
            raise httpx.ConnectError(SENTINEL, request=request)
        if mode == "timeout":
            raise httpx.ReadTimeout(SENTINEL, request=request)
        return httpx.Response(mode, json={"error": {"message": SENTINEL}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport, max_retries=4) as client:
            with pytest.raises(DiscoveryProviderFailure) as caught:
                await invoke(provider(client), "research")
    failure = caught.value
    assert len(calls) == 1
    assert failure.failure_category == category
    assert failure.response_received is received
    assert failure.usage.total_tokens is None
    assert failure.usage.estimated_model_cost_usd is None
    assert failure.tool_calls is None
    assert failure.tool_calls_complete is False


async def test_schema_failure_is_zero_requests(monkeypatch):
    def invalid(*args, **kwargs):
        raise PydanticInvalidForJsonSchema(SENTINEL)

    def never(request):
        raise AssertionError("Schema error must precede HTTP")

    monkeypatch.setattr(DiscoveryPlan, "model_json_schema", invalid)
    async with httpx.AsyncClient(transport=httpx.MockTransport(never)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            with pytest.raises(DiscoveryProviderFailure) as caught:
                await invoke(provider(client), "planning")
    assert caught.value.reason == "schema_construction"
    assert caught.value.attempts == 0


async def test_public_response_validation_exception_retains_safe_evidence(monkeypatch):
    # Inject via public SDK method; do not depend on private SDK parser internals.
    from openai.resources.responses import AsyncResponses

    body = envelope(research_result())

    class Raw:
        http_response = httpx.Response(
            200, json=body, request=httpx.Request("POST", "https://example.org")
        )

        def parse(self):
            raise APIResponseValidationError(
                response=self.http_response, body=body, message=SENTINEL
            )

    async def fake_parse(*args, **kwargs):
        return Raw()

    monkeypatch.setattr(AsyncResponses, "parse", fake_parse)
    async with AsyncOpenAI(api_key="offline") as client:
        with pytest.raises(DiscoveryProviderFailure) as caught:
            await invoke(provider(client), "research")
    assert caught.value.failure_category == "response_schema"
    assert caught.value.usage.total_tokens == 125
    assert caught.value.tool_calls == 1


@pytest.mark.parametrize(
    "usage",
    [None, {"input_tokens": 100}, {"input_tokens": 100, "output_tokens": 25, "total_tokens": 125}],
)
async def test_partial_usage_never_becomes_complete_cost_accounting(usage):
    body = envelope(research_result())
    body["usage"] = usage
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            result = await invoke(provider(client), "research")
    assert result.usage.cached_input_tokens is None
    assert result.usage.input_tokens == (100 if usage else None)


async def run(researcher=None, verifier=None, planner=None, **kwargs):
    return await run_adaptive_discovery(
        universe().scope,
        collection(),
        planner or Planner(),
        researcher or Researcher(),
        verifier or Verifier(),
        budget=kwargs.pop("budget", budget()),
        observed_at=datetime(2026, 10, 2, 12, 45, tzinfo=PACIFIC),
        **kwargs,
    )


class FailedResearch(Researcher):
    async def research(self, *args, **kwargs):
        self.calls.append(1)
        raise DiscoveryProviderFailure(
            "invalid_response",
            category="sdk_parse",
            reason="sdk_parse",
            response_received=True,
            response_state="completed",
            structured_output="invalid",
            required_web_search="observed",
            tool_calls=1,
            tool_calls_complete=True,
            usage=TokenUsage(input_tokens=100),
            latency_seconds=0.01,
        )


async def test_failure_precedes_no_incremental_and_budget_stops_with_known_subtotals():
    researcher, verifier = FailedResearch(), Verifier()
    outcome = await run(researcher, verifier)
    assert outcome.summary.stop_reason == "provider_failure"
    assert outcome.diagnostics.status == "fallback"
    assert outcome.opportunities == collection().opportunities
    assert outcome.summary.usage.model_calls == 2
    assert outcome.summary.usage.completed_model_calls == 2
    assert outcome.summary.usage.model_cost_complete is False
    assert outcome.summary.usage.estimated_model_cost_usd == Decimal("0.001")
    assert outcome.diagnostics.input_tokens == 110
    assert outcome.diagnostics.usage_complete is False
    assert outcome.summary.operations[-1].stage == "research"
    assert outcome.summary.operations[-1].task_number == 1
    assert len(researcher.calls) == 1 and verifier.calls == []


@pytest.mark.parametrize("stage", ["planning", "research", "verification"])
async def test_transport_failure_stage_and_unknown_tool_usage(stage):
    class Fail:
        model_id = "offline"

        async def fail(self, *args, **kwargs):
            raise DiscoveryProviderFailure("timeout", category="timeout", reason="request_failed")

        plan = research = verify = fail

    outcome = await run(
        planner=Fail() if stage == "planning" else None,
        researcher=Fail() if stage == "research" else None,
        verifier=Fail() if stage == "verification" else None,
    )
    op = outcome.summary.operations[-1]
    assert op.stage == stage and op.completed_attempts == 0
    assert op.tool_calls is None and not op.tool_calls_complete
    assert op.input_tokens is None and op.estimated_model_cost_usd is None
    assert not outcome.summary.usage.web_search_calls_complete
    assert not outcome.summary.usage.model_cost_complete
    assert outcome.summary.stop_reason == "provider_failure"


async def test_local_result_validation_is_separate_and_retains_successful_call_usage():
    class WrongTask(Researcher):
        async def research(self, *args, **kwargs):
            result = await super().research(*args, **kwargs)
            return replace(result, value=result.value.model_copy(update={"task_id": "wrong"}))

    outcome = await run(researcher=WrongTask())
    assert outcome.summary.stop_reason == "provider_failure"
    op = outcome.summary.operations[-1]
    assert op.stage == "local_validation" and op.failure_category == "local_validation"
    assert op.attempts == 0
    assert outcome.summary.usage.model_calls == 2
    assert outcome.summary.usage.model_cost_complete is True


async def test_materialization_failure_is_separate():
    value = novel_candidate().model_copy(update={"county": "Marin County"})
    outcome = await run(researcher=Researcher(candidates=(value,)))
    assert outcome.summary.operations[-1].stage == "materialization"
    assert outcome.summary.operations[-1].reason == "materialization_invalid"
    assert outcome.summary.stop_reason == "provider_failure"
    assert outcome.new_opportunities == ()


async def test_unexpected_local_error_preserves_prior_operations_and_propagates():
    class Broken(Researcher):
        async def research(self, *args, **kwargs):
            raise RuntimeError(SENTINEL)

    captured = []
    with pytest.raises(RuntimeError):
        await run(researcher=Broken(), on_failure=lambda *args: captured.append(args))
    diagnostics, summary = captured[0]
    assert diagnostics.status == "failed"
    assert summary.operations[-1].stage == "research"
    assert summary.operations[-1].failure_category == "local_invariant"
    assert summary.operations[0].input_tokens == 10
    assert not summary.usage.attempts_complete
    assert SENTINEL not in summary.model_dump_json()


async def test_missing_successful_usage_stops_before_unbounded_research():
    class UnknownUsage(Planner):
        async def plan(self, context):
            return replace(await super().plan(context), usage=TokenUsage(input_tokens=10))

    researcher = Researcher()
    outcome = await run(planner=UnknownUsage(), researcher=researcher)
    assert outcome.summary.stop_reason == "budget_exhausted"
    assert not outcome.summary.usage.model_cost_complete
    assert not researcher.calls


@pytest.mark.parametrize(
    "status,expected",
    [
        ("failed", "web_search_failed"),
        ("searching", "web_search_unobservable"),
        (None, "web_search_unobservable"),
    ],
)
async def test_tool_failure_or_unknown_completion_is_not_verified_success(status, expected):
    body = envelope(research_result())
    body["output"][0]["status"] = status
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            with pytest.raises(DiscoveryProviderFailure) as caught:
                await invoke(provider(client), "research")
    assert caught.value.failure_category == "tool_behavior"
    assert caught.value.reason == expected
    assert caught.value.tool_calls == 1


async def test_cancellation_retains_prior_call_and_unknown_inflight_usage():
    class Cancelled(Researcher):
        async def research(self, *args, **kwargs):
            raise asyncio.CancelledError(SENTINEL)

    captured = []
    with pytest.raises(asyncio.CancelledError):
        await run(researcher=Cancelled(), on_failure=lambda *args: captured.append(args))
    diagnostics, summary = captured[0]
    assert diagnostics.attempts == 2
    assert diagnostics.input_tokens == 10
    assert summary.operations[-1].failure_category == "cancelled"
    assert summary.operations[-1].stage == "research"
    assert summary.operations[-1].input_tokens is None
    assert summary.operations[-1].completed_attempts == 0
    assert not summary.usage.model_cost_complete
    assert SENTINEL not in summary.model_dump_json()


async def test_no_sibling_task_or_verification_after_unknown_provider_failure():
    class MultipleTasks(Planner):
        async def plan(self, context):
            result = await super().plan(context)
            extra = result.value.tasks[0].model_copy(update={"task_id": "second-task"})
            return replace(
                result,
                value=result.value.model_copy(update={"tasks": (*result.value.tasks, extra)}),
            )

    researcher, verifier = FailedResearch(), Verifier()
    outcome = await run(planner=MultipleTasks(), researcher=researcher, verifier=verifier)
    assert outcome.summary.stop_reason == "provider_failure"
    assert len(researcher.calls) == 1
    assert not verifier.calls


async def test_verification_local_validation_failure_retains_usage():
    class InvalidVerifier(Verifier):
        async def verify(self, *args, **kwargs):
            result = await super().verify(*args, **kwargs)
            return replace(result, value=result.value.model_copy(update={"decisions": ()}))

    outcome = await run(verifier=InvalidVerifier())
    assert outcome.summary.operations[-2].stage == "verification"
    assert outcome.summary.operations[-1].stage == "local_validation"
    assert outcome.summary.usage.completed_model_calls == 3
    assert outcome.new_opportunities == ()


async def test_tool_budget_overrun_keeps_known_usage_and_reports_local_failure():
    class Overrun(Researcher):
        async def research(self, *args, **kwargs):
            return replace(await super().research(*args, **kwargs), tool_calls=100)

    captured = []
    with pytest.raises(ValueError):
        await run(researcher=Overrun(), on_failure=lambda *args: captured.append(args))
    _, summary = captured[0]
    assert summary.usage.web_search_calls == 100
    assert summary.operations[-2].input_tokens == 20
    assert summary.operations[-1].failure_category == "local_invariant"


@pytest.mark.parametrize("limit", ["max_model_calls", "max_web_search_calls", "max_model_cost_usd"])
async def test_existing_budget_limits_remain_enforced(limit):
    limits = {
        "max_model_calls": 1,
        "max_web_search_calls": 0,
        "max_model_cost_usd": Decimal("0.001"),
    }
    researcher = Researcher()
    outcome = await run(researcher=researcher, budget=budget(**{limit: limits[limit]}))
    assert outcome.summary.stop_reason == "budget_exhausted"
    assert not researcher.calls


@pytest.mark.parametrize("output", [None, "invalid"])
async def test_malformed_response_envelope_preserves_unknown_tool_accounting(output):
    body = envelope(research_result())
    body["output"] = output
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport) as client:
            with pytest.raises(DiscoveryProviderFailure) as caught:
                await invoke(provider(client), "research")
    assert caught.value.failure_category == "response_schema"
    assert caught.value.required_web_search == "unknown"
    assert caught.value.tool_calls is None
    assert caught.value.usage.total_tokens == 125


async def test_legacy_summary_json_remains_readable_without_new_evidence():
    from event_radar.models.regional_discovery import AdaptiveDiscoverySummary

    payload = (await run()).summary.model_dump(mode="json")
    payload.pop("operations")
    for key in ("completed_model_calls", "attempts_complete", "web_search_calls_complete"):
        payload["usage"].pop(key)
    restored = AdaptiveDiscoverySummary.model_validate(payload)
    assert restored.operations == ()
    assert restored.usage.completed_model_calls is None
    assert restored.usage.web_search_calls_complete is False
