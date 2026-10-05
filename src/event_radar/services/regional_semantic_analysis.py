"""OpenAI provider adapter for user-neutral regional semantic analysis."""

from __future__ import annotations

from pathlib import Path
from time import monotonic

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from event_radar.models.regional import RegionalAnalysisRequest
from event_radar.models.regional_semantics import RegionalSemanticAnalysis
from event_radar.models.token_usage import ModelTokenPricing, parse_token_usage
from event_radar.shared.semantic_analysis import (
    SemanticProviderFailure,
    SemanticProviderResponse,
)


class OpenAIRegionalSemanticProvider:
    """Explicitly configured provider; importing/constructing does not read legacy Settings."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model_id: str,
        prompt_path: Path,
        timeout_seconds: float,
        client: AsyncOpenAI | None = None,
        pricing: ModelTokenPricing | None = None,
    ) -> None:
        self._api_key = api_key
        self.model_id = model_id
        self._prompt_path = prompt_path
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._pricing = pricing

    async def analyze(
        self,
        request: RegionalAnalysisRequest,
        *,
        correction: str | None = None,
    ) -> SemanticProviderResponse:
        client = self._client
        if client is None:
            if not self._api_key:
                raise SemanticProviderFailure("not_configured", attempts=0)
            client = AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )

        try:
            instructions = self._prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SemanticProviderFailure("not_configured", attempts=0) from exc

        if correction:
            instructions += f"\n\nCORRECTION REQUIRED:\n{correction}"

        started = monotonic()
        try:
            response = await client.responses.parse(
                model=self.model_id,
                instructions=instructions,
                input=request.model_dump_json(exclude_none=False),
                text_format=RegionalSemanticAnalysis,
                reasoning={"effort": "low"},
                store=False,
            )
        except APITimeoutError as exc:
            raise SemanticProviderFailure(
                "timeout",
                latency_seconds=monotonic() - started,
            ) from exc
        except APIConnectionError as exc:
            raise SemanticProviderFailure(
                "unavailable",
                latency_seconds=monotonic() - started,
            ) from exc
        except APIStatusError as exc:
            code = (
                "rate_limited"
                if exc.status_code == 429
                else "unavailable"
                if exc.status_code >= 500
                else "invalid_response"
            )
            raise SemanticProviderFailure(
                code,
                latency_seconds=monotonic() - started,
            ) from exc
        except ValidationError as exc:
            raise SemanticProviderFailure(
                "invalid_response",
                latency_seconds=monotonic() - started,
            ) from exc

        usage = parse_token_usage(getattr(response, "usage", None), self._pricing)
        if response.status == "incomplete" or response.error is not None:
            raise SemanticProviderFailure(
                "invalid_response",
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        analysis = response.output_parsed
        if analysis is None:
            raise SemanticProviderFailure(
                "invalid_response",
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        return SemanticProviderResponse(
            analysis=analysis,
            usage=usage,
            attempts=1,
            latency_seconds=monotonic() - started,
        )
