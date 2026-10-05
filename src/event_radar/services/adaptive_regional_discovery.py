"""OpenAI adapter for neutral adaptive regional discovery.

No legacy Settings object is imported. Construction is inert; live calls require an
explicit client or API key and are separately authorized by the execution layer.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Literal

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from event_radar.models.regional_discovery import (
    DiscoveredEventCandidate,
    DiscoveryContext,
    DiscoveryPlan,
    DiscoveryResearchRequest,
    DiscoveryResearchResult,
    DiscoveryTask,
    DiscoveryVerificationRequest,
    DiscoveryVerificationResult,
)
from event_radar.models.token_usage import ModelTokenPricing, parse_token_usage
from event_radar.shared.discovery import (
    DiscoveryProviderFailure,
    DiscoveryProviderResponse,
)


class OpenAIAdaptiveDiscoveryProvider:
    """Three-stage planner/research/verifier provider using explicit configuration."""

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
        self._api_key = api_key
        self.model_id = model_id
        self._planning_prompt_path = planning_prompt_path
        self._research_prompt_path = research_prompt_path
        self._verification_prompt_path = verification_prompt_path
        self._timeout_seconds = timeout_seconds
        self._max_web_search_calls_per_request = max_web_search_calls_per_request
        self._search_context_size = search_context_size
        self._client = client
        self._pricing = pricing

    async def plan(
        self,
        context: DiscoveryContext,
    ) -> DiscoveryProviderResponse[DiscoveryPlan]:
        client = self._client_or_failure()
        instructions = self._read_prompt(self._planning_prompt_path)
        started = monotonic()
        try:
            response = await client.responses.parse(
                model=self.model_id,
                instructions=instructions,
                input=context.model_dump_json(exclude_none=False),
                text_format=DiscoveryPlan,
                reasoning={"effort": "medium"},
                store=False,
            )
        except (APITimeoutError, APIConnectionError, APIStatusError, ValidationError) as exc:
            raise self._failure(exc, started=started) from exc

        usage = parse_token_usage(getattr(response, "usage", None), self._pricing)
        if response.status == "incomplete" or response.error is not None:
            raise DiscoveryProviderFailure(
                "invalid_response",
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        result = response.output_parsed
        if not isinstance(result, DiscoveryPlan):
            raise DiscoveryProviderFailure(
                "invalid_response",
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        return DiscoveryProviderResponse(
            value=result,
            usage=usage,
            tool_calls=0,
            attempts=1,
            latency_seconds=monotonic() - started,
        )

    async def research(
        self,
        context: DiscoveryContext,
        task: DiscoveryTask,
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]:
        allowed = self._bounded_search_calls(max_web_search_calls)
        request = DiscoveryResearchRequest(context=context, task=task)
        return await self._web_parse(
            prompt_path=self._research_prompt_path,
            request_json=request.model_dump_json(exclude_none=False),
            text_format=DiscoveryResearchResult,
            max_web_search_calls=allowed,
        )

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]:
        allowed = self._bounded_search_calls(max_web_search_calls)
        request = DiscoveryVerificationRequest(
            context=context,
            candidates=candidates,
        )
        return await self._web_parse(
            prompt_path=self._verification_prompt_path,
            request_json=request.model_dump_json(exclude_none=False),
            text_format=DiscoveryVerificationResult,
            max_web_search_calls=allowed,
        )

    async def _web_parse[T](
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
        try:
            response = await client.responses.parse(
                model=self.model_id,
                instructions=instructions,
                input=request_json,
                text_format=text_format,
                tools=[
                    {
                        "type": "web_search",
                        "search_context_size": self._search_context_size,
                    }
                ],
                tool_choice="required",
                max_tool_calls=max_web_search_calls,
                reasoning={"effort": "medium"},
                store=False,
            )
        except (APITimeoutError, APIConnectionError, APIStatusError, ValidationError) as exc:
            raise self._failure(exc, started=started) from exc

        usage = parse_token_usage(getattr(response, "usage", None), self._pricing)
        tool_calls = _web_search_call_count(response.output)
        if (
            response.status == "incomplete"
            or response.error is not None
            or response.output_parsed is None
            or tool_calls == 0
        ):
            raise DiscoveryProviderFailure(
                "invalid_response",
                tool_calls=tool_calls,
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        return DiscoveryProviderResponse(
            value=response.output_parsed,
            usage=usage,
            tool_calls=tool_calls,
            attempts=1,
            latency_seconds=monotonic() - started,
        )

    def _client_or_failure(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise DiscoveryProviderFailure("not_configured", attempts=0)
        return AsyncOpenAI(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=0,
        )

    @staticmethod
    def _read_prompt(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DiscoveryProviderFailure("not_configured", attempts=0) from exc

    def _bounded_search_calls(self, remaining: int) -> int:
        if remaining < 1:
            raise DiscoveryProviderFailure("not_configured", attempts=0)
        return min(remaining, self._max_web_search_calls_per_request)

    @staticmethod
    def _failure(
        exc: Exception,
        *,
        started: float,
    ) -> DiscoveryProviderFailure:
        if isinstance(exc, APITimeoutError):
            code = "timeout"
        elif isinstance(exc, APIConnectionError):
            code = "unavailable"
        elif isinstance(exc, APIStatusError):
            code = (
                "rate_limited"
                if exc.status_code == 429
                else "unavailable"
                if exc.status_code >= 500
                else "invalid_response"
            )
        else:
            code = "invalid_response"
        return DiscoveryProviderFailure(
            code,
            latency_seconds=monotonic() - started,
        )


def _web_search_call_count(output: object) -> int:
    if not isinstance(output, list):
        return 0
    return sum(getattr(item, "type", None) == "web_search_call" for item in output)
