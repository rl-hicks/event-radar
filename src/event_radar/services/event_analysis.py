from pathlib import Path
from time import monotonic

from openai import AsyncOpenAI

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.event_analysis import (
    ScrapedEventAnalysis,
    ScrapedEventAnalysisOutcome,
    ScrapedEventAnalysisRequest,
)
from event_radar.services.event_cards import (
    EventAnalysisReferenceError,
    validate_scraped_analysis,
)


class EventAnalysisError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        latency_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.latency_seconds = latency_seconds


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

    async def analyze(
        self,
        request: ScrapedEventAnalysisRequest,
    ) -> ScrapedEventAnalysisOutcome:
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
            raise EventAnalysisError(
                f"Could not read event-analysis prompt at {self._prompt_path}."
            ) from exc

        started = monotonic()
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
                raise EventAnalysisError(
                    f"OpenAI scraped-event analysis request failed ({type(exc).__name__}).",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                ) from exc
            if response.status == "incomplete" or response.error is not None:
                raise EventAnalysisError(
                    "OpenAI scraped-event analysis response was incomplete or erroneous.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
            analysis = response.output_parsed
            if analysis is None:
                raise EventAnalysisError(
                    "OpenAI scraped-event analysis returned no structured result.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
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
                raise EventAnalysisError(
                    "Scraped-event analysis remained invalid after one corrective retry.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                ) from exc

            usage = response.usage
            diagnostics = AIStageDiagnostics(
                stage="scraped_event_analysis",
                model=self._model,
                success=True,
                input_count=len(request.events),
                result_count=len(analysis.events),
                attempts=attempt,
                latency_seconds=monotonic() - started,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
            )
            _log(diagnostics)
            return ScrapedEventAnalysisOutcome(analysis=analysis, diagnostics=diagnostics)
        raise EventAnalysisError("Scraped-event analysis produced no valid result.")


async def analyze_scraped_events_with_fallback(
    service: OpenAIEventAnalysisService,
    request: ScrapedEventAnalysisRequest,
) -> ScrapedEventAnalysisOutcome:
    try:
        return await service.analyze(request)
    except EventAnalysisError as exc:
        diagnostics = AIStageDiagnostics(
            stage="scraped_event_analysis",
            model=service.model,
            success=False,
            fallback_reason=str(exc),
            input_count=len(request.events),
            result_count=0,
            attempts=exc.attempts,
            latency_seconds=exc.latency_seconds,
        )
        _log(diagnostics)
        return ScrapedEventAnalysisOutcome(analysis=None, diagnostics=diagnostics)


def _log(diagnostics: AIStageDiagnostics) -> None:
    latency = (
        f"{diagnostics.latency_seconds:.2f}s" if diagnostics.latency_seconds is not None else "n/a"
    )
    print(
        "AI stage=scraped_event_analysis "
        f"status={'success' if diagnostics.success else 'fallback'} "
        f"model={diagnostics.model} input={diagnostics.input_count} "
        f"result={diagnostics.result_count} attempts={diagnostics.attempts} "
        f"latency={latency} "
        f"tokens={diagnostics.total_tokens if diagnostics.total_tokens is not None else 'n/a'}"
    )
