"""OpenAI provider adapter for user-neutral regional semantic analysis."""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

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

from event_radar.models.regional import FailureCode, RegionalAnalysisRequest
from event_radar.models.regional_semantics import RegionalSemanticAnalysis
from event_radar.models.token_usage import ModelTokenPricing, TokenUsage, parse_token_usage
from event_radar.shared.failures import safe_usage
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
            code: FailureCode = (
                "rate_limited"
                if exc.status_code == 429
                else "unavailable"
                if exc.status_code >= 500
                else "invalid_response"
            )
            raise SemanticProviderFailure(
                code,
                category="provider_status",
                latency_seconds=monotonic() - started,
            ) from exc
        except (PydanticInvalidForJsonSchema, PydanticSchemaGenerationError) as exc:
            raise SemanticProviderFailure(
                "not_configured",
                attempts=0,
                category="configuration",
                latency_seconds=monotonic() - started,
            ) from exc
        except APIResponseValidationError as exc:
            usage = _response_error_usage(exc, self._pricing)
            raise SemanticProviderFailure(
                "invalid_response",
                category="response_schema",
                usage=usage,
                latency_seconds=monotonic() - started,
            ) from exc
        except (LengthFinishReasonError, ContentFilterFinishReasonError) as exc:
            raise SemanticProviderFailure(
                "invalid_response",
                category="sdk_finish_reason",
                usage=_response_error_usage(exc, self._pricing),
                latency_seconds=monotonic() - started,
            ) from exc
        except (ValidationError, JSONDecodeError) as exc:
            raise SemanticProviderFailure(
                "invalid_response",
                category="sdk_parse",
                latency_seconds=monotonic() - started,
            ) from exc

        usage = safe_usage(parse_token_usage(getattr(response, "usage", None), self._pricing))
        if (
            getattr(response, "status", None) != "completed"
            or getattr(response, "error", None) is not None
        ):
            raise SemanticProviderFailure(
                "invalid_response",
                category="response_behavior",
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        analysis = getattr(response, "output_parsed", None)
        if not isinstance(analysis, RegionalSemanticAnalysis):
            raise SemanticProviderFailure(
                "invalid_response",
                category="response_behavior",
                latency_seconds=monotonic() - started,
                usage=usage,
            )
        return SemanticProviderResponse(
            analysis=analysis,
            usage=usage,
            attempts=1,
            latency_seconds=monotonic() - started,
        )


def _response_error_usage(
    error: APIResponseValidationError | LengthFinishReasonError | ContentFilterFinishReasonError,
    pricing: ModelTokenPricing | None,
) -> TokenUsage:
    """Extract only known numeric usage, never persist the response/error body."""
    if isinstance(error, APIResponseValidationError):
        body = error.body
        usage = body.get("usage") if isinstance(body, dict) else None
        if isinstance(usage, dict):
            details = usage.get("input_tokens_details")
            return safe_usage(
                parse_token_usage(
                    SimpleNamespace(
                        input_tokens=usage.get("input_tokens"),
                        output_tokens=usage.get("output_tokens"),
                        total_tokens=usage.get("total_tokens"),
                        input_tokens_details=SimpleNamespace(
                            cached_tokens=details.get("cached_tokens")
                            if isinstance(details, dict)
                            else None,
                        ),
                    ),
                    pricing,
                )
            )
    if isinstance(error, LengthFinishReasonError):
        usage_object = error.completion.usage
        if usage_object is not None:
            return safe_usage(
                parse_token_usage(
                    SimpleNamespace(
                        input_tokens=usage_object.prompt_tokens,
                        output_tokens=usage_object.completion_tokens,
                        total_tokens=usage_object.total_tokens,
                        input_tokens_details=SimpleNamespace(
                            cached_tokens=getattr(
                                usage_object.prompt_tokens_details, "cached_tokens", None
                            ),
                        ),
                    ),
                    pricing,
                )
            )
    return TokenUsage()
