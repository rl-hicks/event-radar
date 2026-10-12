"""Offline adversarial semantic boundaries; no external HTTP is permitted."""

import asyncio
import json
import socket
from decimal import Decimal

import httpx
import pytest
from openai import (
    APIResponseValidationError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from openai.types.chat import ChatCompletion
from pydantic import PydanticInvalidForJsonSchema

from event_radar.models.regional_semantics import RegionalSemanticAnalysis
from event_radar.models.token_usage import ModelTokenPricing, TokenUsage
from event_radar.services.regional_semantic_analysis import OpenAIRegionalSemanticProvider
from event_radar.shared.failures import safe_usage
from event_radar.shared.semantic_analysis import (
    SemanticProviderFailure,
    enrich_regional_semantics,
)
from tests.test_regional_semantic_analysis import FakeSemanticProvider, fixture_universe
from tests.test_regional_semantic_provider import PROMPT, request

SENTINEL = "DO_NOT_PERSIST_RAW_CONTENT"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External network forbidden")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.mark.parametrize(
    "error,category,expected_cost",
    [
        (ContentFilterFinishReasonError(), "sdk_finish_reason", None),
        (
            LengthFinishReasonError(
                completion=ChatCompletion(
                    id="offline",
                    created=0,
                    object="chat.completion",
                    model="offline",
                    choices=[],
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )
            ),
            "sdk_finish_reason",
            0.00002,
        ),
        (
            APIResponseValidationError(
                response=httpx.Response(200, request=httpx.Request("POST", "https://example.org")),
                body={
                    "unsafe": SENTINEL,
                    "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                },
                message=SENTINEL,
            ),
            "response_schema",
            0.00002,
        ),
        (json.JSONDecodeError(SENTINEL, SENTINEL, 0), "sdk_parse", None),
    ],
)
async def test_additional_sdk_exceptions_are_bounded(error, category, expected_cost):
    class FakeClient:
        @property
        def responses(self):
            return self

        async def parse(self, **kwargs):
            raise error

    provider = OpenAIRegionalSemanticProvider(
        api_key=None,
        model_id="offline",
        prompt_path=PROMPT,
        timeout_seconds=1,
        client=FakeClient(),
        pricing=ModelTokenPricing(1, 0.1, 2),
    )
    with pytest.raises(SemanticProviderFailure) as caught:
        await provider.analyze(request())
    failure = caught.value
    assert failure.failure_code == "invalid_response"
    assert failure.failure_category == category
    assert failure.attempts == 1
    assert failure.latency_seconds >= 0
    assert failure.usage.estimated_model_cost_usd == expected_cost
    assert SENTINEL not in str(failure)


@pytest.mark.parametrize("malformed", [False, True])
async def test_public_sdk_parse_schema_and_response_contract_offline(malformed):
    """Exercise the supported responses.parse API via httpx.MockTransport."""
    value = request()
    calls = []

    def respond(http_request):
        body = json.loads(http_request.content)
        calls.append(body)
        schema = body["text"]["format"]["schema"]
        assert body["text"]["format"]["strict"] is True
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["opportunities"]
        assert "OpportunitySemanticAnalysis" in schema["$defs"]
        analysis = {
            "opportunities": [
                {"opportunity_id": item.opportunity_id, "descriptors": []}
                for item in value.opportunities
            ]
        }
        return httpx.Response(
            200,
            json={
                "id": "resp_offline",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "offline",
                "error": None,
                "output": [
                    {
                        "type": "message",
                        "id": "msg_offline",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": SENTINEL if malformed else json.dumps(analysis),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "input_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport, max_retries=0) as client:
            provider = OpenAIRegionalSemanticProvider(
                api_key=None,
                model_id="offline",
                prompt_path=PROMPT,
                timeout_seconds=1,
                client=client,
            )
            if malformed:
                with pytest.raises(SemanticProviderFailure) as caught:
                    await provider.analyze(value)
                assert caught.value.failure_category == "sdk_parse"
                # SDK parse does not expose the raw response on Pydantic errors.
                assert caught.value.usage.total_tokens is None
            else:
                result = await provider.analyze(value)
                assert result.usage.total_tokens == 15
                assert len(result.analysis.opportunities) == len(value.opportunities)
    assert len(calls) == 1


async def test_schema_construction_failure_occurs_before_mock_transport(monkeypatch):
    calls = []

    def invalid_schema(*args, **kwargs):
        raise PydanticInvalidForJsonSchema(SENTINEL)

    def unexpected_transport(request):
        calls.append(request)
        raise AssertionError("Schema construction should fail before transport")

    monkeypatch.setattr(RegionalSemanticAnalysis, "model_json_schema", invalid_schema)
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_transport)) as transport:
        async with AsyncOpenAI(api_key="offline", http_client=transport, max_retries=0) as client:
            provider = OpenAIRegionalSemanticProvider(
                api_key=None,
                model_id="offline",
                prompt_path=PROMPT,
                timeout_seconds=1,
                client=client,
            )
            with pytest.raises(SemanticProviderFailure) as caught:
                await provider.analyze(request())
    assert not calls
    assert caught.value.attempts == 0
    assert caught.value.failure_category == "configuration"


async def test_unexpected_local_error_retains_prior_batch_telemetry():
    class LocalError(FakeSemanticProvider):
        async def analyze(self, request, *, correction=None):
            if self.requests:
                raise RuntimeError(SENTINEL)
            return await super().analyze(request, correction=correction)

    universe = fixture_universe()
    diagnostics = []
    with pytest.raises(RuntimeError):
        await enrich_regional_semantics(
            universe.scope,
            universe.opportunities,
            LocalError(),
            batch_size=1,
            on_failure=diagnostics.append,
        )
    failure = diagnostics[0]
    assert failure.stage == "semantic_analysis" and failure.status == "failed"
    assert failure.failure_code == "invalid_response"
    assert failure.failure_category == "local_invariant"
    assert failure.provider_calls == 2
    assert failure.attempts == 1 and failure.attempts_complete is False
    assert failure.result_count == 1
    assert failure.total_tokens == 15 and failure.estimated_model_cost_usd == Decimal("0.002")
    assert failure.usage_complete is False
    assert SENTINEL not in failure.model_dump_json()


async def test_local_application_failure_retains_current_response_usage(monkeypatch):
    import event_radar.shared.semantic_analysis as module

    def fail(*args, **kwargs):
        raise ValueError(SENTINEL)

    monkeypatch.setattr(module, "_apply_analysis", fail)
    universe = fixture_universe()
    diagnostics = []
    with pytest.raises(ValueError):
        await enrich_regional_semantics(
            universe.scope,
            universe.opportunities,
            FakeSemanticProvider(),
            on_failure=diagnostics.append,
        )
    failure = diagnostics[0]
    assert failure.provider_calls == 1 and failure.attempts == 1
    assert failure.attempts_complete is True
    assert failure.total_tokens == 15
    assert failure.failure_category == "local_invariant"
    assert SENTINEL not in failure.model_dump_json()


async def test_cancellation_reports_inflight_unknowns_and_prior_usage():
    class Slow(FakeSemanticProvider):
        async def analyze(self, request, *, correction=None):
            if self.requests:
                raise asyncio.CancelledError(SENTINEL)
            return await super().analyze(request, correction=correction)

    universe = fixture_universe()
    diagnostics = []
    with pytest.raises(asyncio.CancelledError):
        await enrich_regional_semantics(
            universe.scope,
            universe.opportunities,
            Slow(),
            batch_size=1,
            on_failure=diagnostics.append,
        )
    assert diagnostics[0].failure_category == "cancelled"
    assert diagnostics[0].total_tokens == 15
    assert diagnostics[0].provider_calls == 2
    assert diagnostics[0].attempts_complete is False


def test_invalid_telemetry_cannot_break_failure_reporting():
    value = safe_usage(
        TokenUsage(
            input_tokens=10,
            cached_input_tokens=20,
            output_tokens=5,
            total_tokens=99,
            estimated_model_cost_usd=float("nan"),
        )
    )
    assert value.input_tokens == 10 and value.output_tokens == 5
    assert value.cached_input_tokens is value.total_tokens is value.estimated_model_cost_usd is None
