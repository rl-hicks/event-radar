"""Explicit, user-neutral OpenAI discovery with bounded response evidence.

The public raw-response wrapper defers structured parsing until safe numeric
telemetry is captured. Raw bodies and exception text never leave this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import Literal, cast

from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from pydantic import PydanticInvalidForJsonSchema, PydanticSchemaGenerationError, ValidationError

from event_radar.models.regional import FailureCategory, FailureCode
from event_radar.models.regional_discovery import (
    DiscoveredEventCandidate,
    DiscoveryContext,
    DiscoveryFailureReason,
    DiscoveryPlan,
    DiscoveryResearchRequest,
    DiscoveryResearchResult,
    DiscoveryTask,
    DiscoveryVerificationRequest,
    DiscoveryVerificationResult,
    ResponseState,
    StructuredOutputState,
    WebSearchState,
)
from event_radar.models.token_usage import ModelTokenPricing, TokenUsage, parse_token_usage
from event_radar.shared.discovery import DiscoveryProviderFailure, DiscoveryProviderResponse
from event_radar.shared.failures import safe_usage


@dataclass
class _Evidence:
    usage: TokenUsage = field(default_factory=TokenUsage)
    received: bool = False
    state: ResponseState = "unknown"
    structured: StructuredOutputState = "unknown"
    search: WebSearchState = "unknown"
    tool_calls: int | None = None
    tools_complete: bool = False

    def read(self, body: object, pricing: ModelTokenPricing | None, *, web: bool) -> None:
        self.received = True
        self.search = "unknown" if web else "not_required"
        if not isinstance(body, dict):
            return
        status = body.get("status")
        if status in ("completed", "incomplete", "failed", "cancelled", "queued", "in_progress"):
            self.state = cast(ResponseState, status)
        usage = body.get("usage")
        if isinstance(usage, dict):
            details = usage.get("input_tokens_details")
            self.usage = safe_usage(
                parse_token_usage(
                    SimpleNamespace(
                        input_tokens=usage.get("input_tokens"),
                        output_tokens=usage.get("output_tokens"),
                        total_tokens=usage.get("total_tokens"),
                        input_tokens_details=SimpleNamespace(
                            cached_tokens=(
                                details.get("cached_tokens") if isinstance(details, dict) else None
                            )
                        ),
                    ),
                    pricing,
                )
            )
        output = body.get("output")
        if isinstance(output, list):
            self.tool_calls = sum(
                isinstance(item, dict) and item.get("type") == "web_search_call" for item in output
            )
            recognizable = all(
                isinstance(item, dict) and isinstance(item.get("type"), str) for item in output
            )
            self.tools_complete = recognizable and self.state == "completed"
            if web:
                searches = [
                    item
                    for item in output
                    if isinstance(item, dict) and item.get("type") == "web_search_call"
                ]
                self.search = (
                    "failed"
                    if any(item.get("status") == "failed" for item in searches)
                    else "unknown"
                    if any(item.get("status") != "completed" for item in searches)
                    else "observed"
                    if self.tool_calls
                    else "absent"
                    if self.tools_complete
                    else "unknown"
                )

    def failure(
        self,
        code: FailureCode,
        category: FailureCategory,
        reason: DiscoveryFailureReason,
        started: float,
        *,
        attempts: int = 1,
    ) -> DiscoveryProviderFailure:
        return DiscoveryProviderFailure(
            code,
            category=category,
            reason=reason,
            attempts=attempts,
            usage=self.usage if attempts else None,
            tool_calls=self.tool_calls,
            latency_seconds=monotonic() - started,
            response_received=self.received,
            response_state=self.state,
            structured_output=self.structured,
            required_web_search=self.search,
            tool_calls_complete=self.tools_complete,
        )


class OpenAIAdaptiveDiscoveryProvider:
    """Three-stage planner/research/verifier using explicit configuration."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model_id: str,
        planning_prompt_path: Path,
        research_prompt_path: Path,
        verification_prompt_path: Path,
        timeout_seconds: float,
        max_web_search_calls_per_request: int,
        search_context_size: Literal["low", "medium", "high"] = "medium",
        client: AsyncOpenAI | None = None,
        pricing: ModelTokenPricing | None = None,
    ) -> None:
        if max_web_search_calls_per_request < 1:
            raise ValueError("Discovery per-request web-search cap must be positive.")
        self._api_key, self.model_id = api_key, model_id
        self._planning_prompt_path = planning_prompt_path
        self._research_prompt_path = research_prompt_path
        self._verification_prompt_path = verification_prompt_path
        self._timeout_seconds = timeout_seconds
        self._max_web_search_calls_per_request = max_web_search_calls_per_request
        self._search_context_size = search_context_size
        self._client, self._pricing = client, pricing

    async def plan(self, context: DiscoveryContext) -> DiscoveryProviderResponse[DiscoveryPlan]:
        return await self._parse(
            prompt_path=self._planning_prompt_path,
            request_json=context.model_dump_json(exclude_none=False),
            text_format=DiscoveryPlan,
            max_web_search_calls=0,
        )

    async def research(
        self, context: DiscoveryContext, task: DiscoveryTask, *, max_web_search_calls: int
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]:
        request = DiscoveryResearchRequest(context=context, task=task)
        return await self._parse(
            prompt_path=self._research_prompt_path,
            request_json=request.model_dump_json(exclude_none=False),
            text_format=DiscoveryResearchResult,
            max_web_search_calls=self._bounded_search_calls(max_web_search_calls),
        )

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]:
        request = DiscoveryVerificationRequest(context=context, candidates=candidates)
        return await self._parse(
            prompt_path=self._verification_prompt_path,
            request_json=request.model_dump_json(exclude_none=False),
            text_format=DiscoveryVerificationResult,
            max_web_search_calls=self._bounded_search_calls(max_web_search_calls),
        )

    async def _parse[T](
        self,
        *,
        prompt_path: Path,
        request_json: str,
        text_format: type[T],
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[T]:
        client = self._client_or_failure()
        instructions = self._read_prompt(prompt_path)
        started = monotonic()
        evidence = _Evidence(search="unknown" if max_web_search_calls else "not_required")
        try:
            # Public SDK interface. .parse() is deferred by with_raw_response,
            # retaining telemetry even when structured output cannot be parsed.
            if max_web_search_calls:
                raw = await client.responses.with_raw_response.parse(
                    model=self.model_id,
                    instructions=instructions,
                    input=request_json,
                    text_format=text_format,
                    reasoning={"effort": "medium"},
                    store=False,
                    tools=[
                        {"type": "web_search", "search_context_size": self._search_context_size}
                    ],
                    tool_choice="required",
                    max_tool_calls=max_web_search_calls,
                )
            else:
                raw = await client.responses.with_raw_response.parse(
                    model=self.model_id,
                    instructions=instructions,
                    input=request_json,
                    text_format=text_format,
                    reasoning={"effort": "medium"},
                    store=False,
                )
            evidence.received = True
            body = raw.http_response.json()
            evidence.read(body, self._pricing, web=bool(max_web_search_calls))
            if isinstance(body, dict) and body.get("error") is not None:
                raise evidence.failure(
                    "invalid_response", "response_behavior", "response_error", started
                )
            if evidence.state != "completed":
                raise evidence.failure(
                    "invalid_response",
                    "response_behavior",
                    "response_incomplete"
                    if evidence.state == "incomplete"
                    else "response_not_completed",
                    started,
                )
            if not isinstance(body, dict) or not isinstance(body.get("output"), list):
                evidence.structured = "invalid"
                raise evidence.failure(
                    "invalid_response", "response_schema", "response_schema", started
                )
            response = raw.parse()
        except APITimeoutError as exc:
            raise evidence.failure("timeout", "timeout", "request_failed", started) from exc
        except APIConnectionError as exc:
            raise evidence.failure(
                "unavailable", "provider_transport", "request_failed", started
            ) from exc
        except APIStatusError as exc:
            # HTTP error bodies are not model response envelopes. Billing remains unknown.
            evidence.received = True
            code: FailureCode = (
                "rate_limited"
                if exc.status_code == 429
                else "unavailable"
                if exc.status_code >= 500
                else "invalid_response"
            )
            raise evidence.failure(code, "provider_status", "request_failed", started) from exc
        except (PydanticInvalidForJsonSchema, PydanticSchemaGenerationError) as exc:
            raise evidence.failure(
                "not_configured", "configuration", "schema_construction", started, attempts=0
            ) from exc
        except APIResponseValidationError as exc:
            if not evidence.received:
                evidence.read(exc.body, self._pricing, web=bool(max_web_search_calls))
            evidence.structured = "invalid"
            raise evidence.failure(
                "invalid_response", "response_schema", "response_schema", started
            ) from exc
        except (LengthFinishReasonError, ContentFilterFinishReasonError) as exc:
            raise evidence.failure(
                "invalid_response", "sdk_finish_reason", "sdk_finish_reason", started
            ) from exc
        except (ValidationError, JSONDecodeError) as exc:
            evidence.structured = "invalid"
            raise evidence.failure("invalid_response", "sdk_parse", "sdk_parse", started) from exc

        result = response.output_parsed
        if not isinstance(result, text_format):
            evidence.structured = "missing" if result is None else "invalid"
            raise evidence.failure(
                "invalid_response", "response_behavior", "missing_structured_output", started
            )
        evidence.structured = "accepted"
        if max_web_search_calls and evidence.search != "observed":
            raise evidence.failure(
                "invalid_response",
                "tool_behavior",
                "missing_required_web_search"
                if evidence.search == "absent"
                else "web_search_failed"
                if evidence.search == "failed"
                else "web_search_unobservable",
                started,
            )
        if evidence.tool_calls is None or not evidence.tools_complete:
            raise evidence.failure(
                "invalid_response", "tool_behavior", "web_search_unobservable", started
            )
        return DiscoveryProviderResponse(
            value=result,
            usage=evidence.usage,
            tool_calls=evidence.tool_calls,
            attempts=1,
            latency_seconds=monotonic() - started,
        )

    def _client_or_failure(self) -> AsyncOpenAI:
        if self._client is not None:
            # Hidden SDK retries would bypass the run's model/search-call budget.
            return self._client.with_options(max_retries=0, timeout=self._timeout_seconds)
        if not self._api_key:
            raise DiscoveryProviderFailure("not_configured", attempts=0, reason="configuration")
        return AsyncOpenAI(api_key=self._api_key, timeout=self._timeout_seconds, max_retries=0)

    @staticmethod
    def _read_prompt(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DiscoveryProviderFailure(
                "not_configured", attempts=0, reason="configuration"
            ) from exc

    def _bounded_search_calls(self, remaining: int) -> int:
        if remaining < 1:
            raise DiscoveryProviderFailure("not_configured", attempts=0, reason="configuration")
        return min(remaining, self._max_web_search_calls_per_request)
