from pathlib import Path
from time import monotonic
from typing import Literal

from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.event_analysis import (
    ScrapedAnalysisBatchDiagnostics,
    ScrapedAnalysisDiagnostics,
    ScrapedEventAnalysis,
    ScrapedEventAnalysisOutcome,
    ScrapedEventAnalysisRequest,
)
from event_radar.services.event_cards import EventAnalysisReferenceError, validate_scraped_analysis

SCRAPED_EVENT_ANALYSIS_BATCH_SIZE = 35


class EventAnalysisError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        latency_seconds: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        provider_error_type: str | None = None,
        provider_error_code: str | None = None,
        provider_status_code: int | None = None,
        provider_error_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.latency_seconds = latency_seconds
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.provider_error_type = provider_error_type
        self.provider_error_code = provider_error_code
        self.provider_status_code = provider_status_code
        self.provider_error_message = provider_error_message


# Fixed messages avoid provider text that can echo prompts or private context.
_PROVIDER_MESSAGES = {
    "insufficient_quota": "Provider quota is exhausted.",
    "rate_limit_exceeded": "Provider rate limit exceeded.",
    "context_length_exceeded": "Provider context limit exceeded.",
    "invalid_api_key": "Provider rejected authentication.",
    "server_error": "Provider server error.",
    "invalid_prompt": "Provider rejected the request.",
    "vector_store_timeout": "Provider resource timed out.",
    "max_output_tokens": "Provider output token limit reached.",
    "content_filter": "Provider content filter interrupted the response.",
}


def _safe_provider_details(exc: Exception) -> tuple[str, str | None, int | None, str]:
    code = getattr(exc, "code", None)
    safe_code = code if isinstance(code, str) and code in _PROVIDER_MESSAGES else None
    message = (
        _PROVIDER_MESSAGES[safe_code]
        if safe_code
        else "Provider request failed; raw message withheld."
    )
    if isinstance(exc, APITimeoutError):
        message = "Provider request timed out."
    elif isinstance(exc, ValidationError):
        message = "Provider returned malformed structured output."
    status = exc.status_code if isinstance(exc, APIStatusError) else None
    return type(exc).__name__, safe_code, status, message


class OpenAIEventAnalysisService:
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

    async def analyze(self, request: ScrapedEventAnalysisRequest) -> ScrapedEventAnalysisOutcome:
        client = self._client
        if client is None:
            if not self._api_key:
                raise EventAnalysisError("OpenAI API key is not configured.")
            client = AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
        try:
            instructions = self._prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EventAnalysisError("Could not read event-analysis prompt.") from exc

        started = monotonic()
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None

        def failure(message: str, attempt: int, exc: Exception | None = None) -> EventAnalysisError:
            error_type, code, status, safe_message = (
                _safe_provider_details(exc)
                if exc is not None
                else ("MalformedOutput", None, None, message)
            )
            return EventAnalysisError(
                message,
                attempts=attempt,
                latency_seconds=monotonic() - started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                provider_error_type=error_type,
                provider_error_code=code,
                provider_status_code=status,
                provider_error_message=safe_message,
            )

        correction = ""
        for attempt in range(1, 3):
            try:
                response = await client.responses.parse(
                    model=self._model,
                    instructions=instructions,
                    input=request.model_dump_json(exclude_none=False) + correction,
                    text_format=ScrapedEventAnalysis,
                    reasoning={"effort": "low"},
                    store=False,
                )
            except Exception as exc:
                raise failure(type(exc).__name__, attempt, exc) from exc
            usage = response.usage
            if usage:
                input_tokens = (input_tokens or 0) + usage.input_tokens
                output_tokens = (output_tokens or 0) + usage.output_tokens
                total_tokens = (total_tokens or 0) + usage.total_tokens
            if response.status == "incomplete" or response.error is not None:
                error = failure(
                    "ProviderResponseError" if response.error is not None else "IncompleteResponse",
                    attempt,
                )
                error.provider_error_type = (
                    "ProviderResponseError" if response.error is not None else "IncompleteResponse"
                )
                code = (
                    response.error.code
                    if response.error is not None
                    else getattr(getattr(response, "incomplete_details", None), "reason", None)
                )
                if isinstance(code, str) and code in _PROVIDER_MESSAGES:
                    error.provider_error_code = code
                    error.provider_error_message = _PROVIDER_MESSAGES[code]
                raise error
            analysis = response.output_parsed
            if analysis is None:
                raise failure("MissingStructuredOutput", attempt)
            try:
                validate_scraped_analysis(request, analysis)
            except EventAnalysisReferenceError as exc:
                if attempt == 1:
                    correction = (
                        "\n\nCORRECTION REQUIRED: Analyze every supplied event_id exactly once. "
                        "Use no invented IDs. Experience groups may reference only supplied IDs, "
                        "and each grouped occurrence must use the matching experience_group_id."
                    )
                    continue
                raise failure("InvalidBatchReferences", attempt) from exc
            diagnostics = AIStageDiagnostics(
                stage="scraped_event_analysis",
                model=self._model,
                success=True,
                input_count=len(request.events),
                result_count=len(analysis.events),
                attempts=attempt,
                latency_seconds=monotonic() - started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
            return ScrapedEventAnalysisOutcome(analysis=analysis, diagnostics=diagnostics)
        raise EventAnalysisError("Scraped-event analysis produced no valid result.")


async def analyze_scraped_events_with_fallback(
    service: OpenAIEventAnalysisService,
    request: ScrapedEventAnalysisRequest,
    *,
    batch_size: int = SCRAPED_EVENT_ANALYSIS_BATCH_SIZE,
) -> ScrapedEventAnalysisOutcome:
    if batch_size < 1:
        raise ValueError("Analysis batch size must be positive.")
    ids = [event.event_id for event in request.events]
    if len(ids) != len(set(ids)):
        raise EventAnalysisReferenceError("Analysis input event IDs must be unique.")
    batches: list[ScrapedAnalysisBatchDiagnostics] = []
    merged = ScrapedEventAnalysis(events=[], experience_groups=[])
    fallback_ids: list[str] = []
    batch_count = (len(ids) + batch_size - 1) // batch_size
    for offset in range(0, len(ids), batch_size):
        batch = request.model_copy(update={"events": request.events[offset : offset + batch_size]})
        index = len(batches) + 1
        try:
            outcome = await service.analyze(batch)
            if outcome.analysis is None:
                raise EventAnalysisError("MissingStructuredOutput")
            validate_scraped_analysis(batch, outcome.analysis)
        except (EventAnalysisError, EventAnalysisReferenceError) as exc:
            details = vars(exc) if isinstance(exc, EventAnalysisError) else {}
            diagnostic = AIStageDiagnostics(
                stage="scraped_event_analysis",
                model=service.model,
                success=False,
                fallback_reason=(
                    str(exc) if isinstance(exc, EventAnalysisError) else "InvalidBatchReferences"
                ),
                input_count=len(batch.events),
                result_count=0,
                **({"attempts": 0} | details),
            )
            fallback_ids.extend(event.event_id for event in batch.events)
        else:
            diagnostic = outcome.diagnostics
            judgments = {item.event_id: item for item in outcome.analysis.events}
            names = {
                group.group_id: f"batch-{index}:{group.group_id}"
                for group in outcome.analysis.experience_groups
            }
            merged.events.extend(
                judgments[event.event_id].model_copy(
                    update={
                        "experience_group_id": names.get(
                            judgments[event.event_id].experience_group_id or ""
                        )
                    }
                )
                for event in batch.events
            )
            order = {event.event_id: position for position, event in enumerate(batch.events)}
            merged.experience_groups.extend(
                group.model_copy(
                    update={
                        "group_id": names[group.group_id],
                        "occurrence_ids": sorted(group.occurrence_ids, key=order.__getitem__),
                    }
                )
                for group in sorted(
                    outcome.analysis.experience_groups,
                    key=lambda group: min(order[event_id] for event_id in group.occurrence_ids),
                )
            )
        batch_diagnostic = ScrapedAnalysisBatchDiagnostics(
            **diagnostic.model_dump(),
            batch_index=index,
        )
        batches.append(batch_diagnostic)
        _log(batch_diagnostic, batch=f"{index}/{batch_count}")

    successful = sum(batch.success for batch in batches)
    failed = len(batches) - successful
    status: Literal["success", "partial", "fallback", "skipped"] = (
        "skipped"
        if not batches
        else "success"
        if not failed
        else "partial"
        if successful
        else "fallback"
    )

    def token_sum(field: str) -> int | None:
        values = [getattr(batch, field) for batch in batches]
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    diagnostics = ScrapedAnalysisDiagnostics(
        stage="scraped_event_analysis",
        model=service.model,
        success=status == "success",
        status=status,
        input_count=len(ids),
        result_count=len(merged.events),
        fallback_reason=(
            f"{failed}/{len(batches)} batches failed; see batch diagnostics."
            if failed
            else "No scraped events; analysis skipped."
            if not batches
            else None
        ),
        attempts=sum(batch.attempts for batch in batches),
        latency_seconds=sum(batch.latency_seconds or 0 for batch in batches),
        input_tokens=token_sum("input_tokens"),
        output_tokens=token_sum("output_tokens"),
        total_tokens=token_sum("total_tokens"),
        batch_size=batch_size,
        batch_count=len(batches),
        successful_batch_count=successful,
        failed_batch_count=failed,
        fallback_event_count=len(fallback_ids),
        batches=batches,
    )
    _log(diagnostics)
    return ScrapedEventAnalysisOutcome(
        analysis=merged if successful else None,
        fallback_event_ids=fallback_ids,
        diagnostics=diagnostics,
    )


def _log(diagnostics: AIStageDiagnostics, *, batch: str | None = None) -> None:
    latency = (
        f"{diagnostics.latency_seconds:.2f}s" if diagnostics.latency_seconds is not None else "n/a"
    )
    status = (
        diagnostics.status
        if isinstance(diagnostics, ScrapedAnalysisDiagnostics)
        else "success"
        if diagnostics.success
        else "fallback"
    )
    summary = (
        f" batches={diagnostics.batch_count} batch_size={diagnostics.batch_size}"
        f" successful_batches={diagnostics.successful_batch_count}"
        f" failed_batches={diagnostics.failed_batch_count}"
        f" fallback_events={diagnostics.fallback_event_count}"
        if isinstance(diagnostics, ScrapedAnalysisDiagnostics)
        else ""
    )
    error = (
        f" fallback_reason={diagnostics.fallback_reason}"
        f" error_type={diagnostics.provider_error_type or 'n/a'}"
        f" provider_code={diagnostics.provider_error_code or 'n/a'}"
        f" provider_message={diagnostics.provider_error_message or 'n/a'}"
        if diagnostics.fallback_reason
        else ""
    )
    print(
        "AI stage=scraped_event_analysis "
        + (f"batch={batch} " if batch else "")
        + f"status={status} model={diagnostics.model} input={diagnostics.input_count} "
        f"result={diagnostics.result_count} attempts={diagnostics.attempts} "
        f"latency={latency} "
        f"tokens={diagnostics.total_tokens if diagnostics.total_tokens is not None else 'n/a'}"
        + summary
        + error
    )
