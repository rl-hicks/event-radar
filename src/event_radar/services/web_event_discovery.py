from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from openai import APIStatusError, AsyncOpenAI

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.web_discovery import (
    DiscoveredEvent,
    WebDiscoveryOutcome,
    WebDiscoveryRequest,
    WebDiscoveryResult,
)
from event_radar.services.event_cards import remove_exact_web_duplicates


@dataclass(frozen=True)
class ProviderErrorDiagnostics:
    status_code: int | None = None
    error_type: str | None = None
    error_code: str | None = None
    parameter: str | None = None
    message: str | None = None


class WebDiscoveryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        latency_seconds: float | None = None,
        provider: ProviderErrorDiagnostics | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.latency_seconds = latency_seconds
        self.provider = provider or ProviderErrorDiagnostics()


class OpenAIWebDiscoveryService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        prompt_path: Path,
        timeout_seconds: float,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._prompt_path = prompt_path
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    async def discover(self, request: WebDiscoveryRequest) -> WebDiscoveryOutcome:
        client = self._client
        if client is None:
            if not self._api_key:
                raise WebDiscoveryError("OpenAI API key is not configured.")
            client = AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
        try:
            instructions = self._prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WebDiscoveryError(
                f"Could not read web-discovery prompt at {self._prompt_path}."
            ) from exc

        started = monotonic()
        correction = ""
        for attempt in range(1, 3):
            try:
                response = await client.responses.parse(
                    model=self._model,
                    instructions=instructions,
                    input=request.model_dump_json(exclude_none=False) + correction,
                    text_format=WebDiscoveryResult,
                    tools=[
                        {
                            "type": "web_search",
                            "search_context_size": "low",
                            "user_location": {
                                "type": "approximate",
                                "city": request.user_context.base_location.name,
                                "region": "California",
                                "country": "US",
                                "timezone": request.user_context.base_location.timezone,
                            },
                        }
                    ],
                    tool_choice="required",
                    max_tool_calls=6,
                    reasoning={"effort": "low"},
                    store=False,
                )
            except Exception as exc:
                provider = _provider_error_diagnostics(exc)
                raise WebDiscoveryError(
                    _provider_failure_message(exc, provider),
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                    provider=provider,
                ) from exc
            if response.status == "incomplete" or response.error is not None:
                raise WebDiscoveryError(
                    "OpenAI web discovery response was incomplete or erroneous.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
            tool_calls = _web_search_call_count(response.output)
            if tool_calls == 0:
                raise WebDiscoveryError(
                    "OpenAI web discovery completed without a web_search_call.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
            result = response.output_parsed
            if not isinstance(result, WebDiscoveryResult):
                raise WebDiscoveryError(
                    "OpenAI web discovery returned no valid structured result.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
            try:
                _validate_discoveries(request, result.discoveries)
            except ValueError as exc:
                if attempt == 1:
                    correction = (
                        "\n\nCORRECTION REQUIRED: Return unique discovery IDs, official or "
                        "credible evidence URLs, timezone-aware start times inside the supplied "
                        "weekend window, and no more than 12 discoveries. Do not fabricate facts."
                    )
                    continue
                raise WebDiscoveryError(
                    "Web discovery remained invalid after one corrective retry.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                ) from exc

            valid, duplicates = remove_exact_web_duplicates(
                result.discoveries,
                [],
                timezone=request.user_context.base_location.timezone,
            )
            usage = response.usage
            diagnostics = AIStageDiagnostics(
                stage="web_event_discovery",
                model=self._model,
                success=True,
                input_count=len(request.existing_events),
                result_count=len(valid),
                attempts=attempt,
                latency_seconds=monotonic() - started,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                tool_calls=tool_calls,
            )
            _log(diagnostics)
            return WebDiscoveryOutcome(
                result=result,
                valid_discoveries=valid,
                duplicates_removed=duplicates,
                diagnostics=diagnostics,
            )
        raise WebDiscoveryError("Web discovery produced no valid result.")


async def discover_events_with_fallback(
    service: OpenAIWebDiscoveryService,
    request: WebDiscoveryRequest,
) -> WebDiscoveryOutcome:
    try:
        return await service.discover(request)
    except WebDiscoveryError as exc:
        diagnostics = AIStageDiagnostics(
            stage="web_event_discovery",
            model=service.model,
            success=False,
            fallback_reason=str(exc),
            input_count=len(request.existing_events),
            result_count=0,
            attempts=exc.attempts,
            latency_seconds=exc.latency_seconds,
            tool_calls=0,
            provider_status_code=exc.provider.status_code,
            provider_error_type=exc.provider.error_type,
            provider_error_code=exc.provider.error_code,
            provider_error_param=exc.provider.parameter,
            provider_error_message=exc.provider.message,
        )
        _log(diagnostics)
        return WebDiscoveryOutcome(
            result=None,
            valid_discoveries=[],
            duplicates_removed=0,
            diagnostics=diagnostics,
        )


def _web_search_call_count(output: object) -> int:
    if not isinstance(output, list):
        return 0
    return sum(getattr(item, "type", None) == "web_search_call" for item in output)


def _provider_error_diagnostics(exc: Exception) -> ProviderErrorDiagnostics:
    if not isinstance(exc, APIStatusError):
        return ProviderErrorDiagnostics(error_type=type(exc).__name__)
    body = exc.body
    payload = body.get("error", body) if isinstance(body, dict) else None

    def field(name: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get(name)
        return _sanitize_provider_value(value)

    return ProviderErrorDiagnostics(
        status_code=exc.status_code,
        error_type=field("type") or type(exc).__name__,
        error_code=field("code"),
        parameter=field("param"),
        message=field("message"),
    )


def _provider_failure_message(
    exc: Exception,
    diagnostics: ProviderErrorDiagnostics,
) -> str:
    parts = [f"OpenAI web event-discovery request failed ({type(exc).__name__})"]
    if diagnostics.status_code is not None:
        parts.append(f"HTTP {diagnostics.status_code}")
    if diagnostics.error_type is not None:
        parts.append(f"type={diagnostics.error_type}")
    if diagnostics.error_code is not None:
        parts.append(f"code={diagnostics.error_code}")
    if diagnostics.parameter is not None:
        parts.append(f"param={diagnostics.parameter}")
    if diagnostics.message is not None:
        parts.append(f"message={diagnostics.message}")
    return "; ".join(parts) + "."


def _sanitize_provider_value(value: object) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    compact = " ".join(str(value).split())
    return compact[:500] if compact else None


def _validate_discoveries(
    request: WebDiscoveryRequest,
    discoveries: list[DiscoveredEvent],
) -> None:
    identifiers = [discovery.discovery_id for discovery in discoveries]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Web discovery IDs must be unique.")
    for discovery in discoveries:
        if not request.weekend_start <= discovery.start_time < request.weekend_end:
            raise ValueError("Discovered event falls outside the requested weekend.")
        if discovery.end_time is not None and discovery.end_time <= discovery.start_time:
            raise ValueError("Discovered event end time must follow its start.")
        if (
            discovery.price_min is not None
            and discovery.price_max is not None
            and discovery.price_max < discovery.price_min
        ):
            raise ValueError("Discovered event has an invalid price range.")


def _log(diagnostics: AIStageDiagnostics) -> None:
    latency = (
        f"{diagnostics.latency_seconds:.2f}s" if diagnostics.latency_seconds is not None else "n/a"
    )
    provider = ""
    if diagnostics.provider_error_type is not None:
        provider = (
            f" provider_http={diagnostics.provider_status_code}"
            f" provider_type={diagnostics.provider_error_type or 'unknown'}"
            f" provider_code={diagnostics.provider_error_code or 'unknown'}"
            f" provider_param={diagnostics.provider_error_param or 'unknown'}"
            f" provider_message={diagnostics.provider_error_message or 'unavailable'}"
        )
    print(
        "AI stage=web_event_discovery "
        f"status={'success' if diagnostics.success else 'fallback'} "
        f"model={diagnostics.model} result={diagnostics.result_count} "
        f"searches={diagnostics.tool_calls or 0} attempts={diagnostics.attempts} "
        f"latency={latency} "
        f"tokens={diagnostics.total_tokens if diagnostics.total_tokens is not None else 'n/a'}"
        f"{provider}"
    )
