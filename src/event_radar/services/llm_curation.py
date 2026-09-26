from pathlib import Path
from time import monotonic

from openai import AsyncOpenAI

from event_radar.curation_config import DEFAULT_CURATION_CONFIG, CurationConfig
from event_radar.models.curation import (
    CandidateType,
    CurationDiagnostics,
    CurationOutcome,
    RecommendationContext,
    WeekendCuration,
)


class CurationError(RuntimeError):
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


class CurationReferenceError(CurationError):
    """Raised for semantic candidate-reference errors that permit one correction."""


class OpenAICurationService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-5.6",
        prompt_path: Path = Path("prompts/weekend_curation.md"),
        timeout_seconds: float = 20.0,
        client: AsyncOpenAI | None = None,
        config: CurationConfig = DEFAULT_CURATION_CONFIG,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._prompt_path = prompt_path
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._config = config

    @property
    def model(self) -> str:
        return self._model

    async def curate(self, context: RecommendationContext) -> CurationOutcome:
        client = self._client
        if client is None:
            if not self._api_key:
                raise CurationError("OpenAI API key is not configured.")
            client = AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
        try:
            instructions = self._prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CurationError(f"Could not read curation prompt at {self._prompt_path}.") from exc

        input_text = context.model_dump_json(exclude_none=False)
        started = monotonic()
        correction = ""
        for attempt in range(1, 3):
            try:
                response = await client.responses.parse(
                    model=self._model,
                    instructions=instructions,
                    input=input_text + correction,
                    text_format=WeekendCuration,
                    reasoning={"effort": self._config.reasoning_effort},
                    store=False,
                )
            except Exception as exc:
                raise CurationError(
                    f"OpenAI final-curation request failed ({type(exc).__name__}).",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                ) from exc
            if response.status == "incomplete" or response.error is not None:
                raise CurationError(
                    "OpenAI final-curation response was incomplete or erroneous.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
            curation = response.output_parsed
            if curation is None:
                raise CurationError(
                    "OpenAI final curation returned no structured result.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                )
            try:
                validate_curation_references(
                    context,
                    curation,
                    maximum_options=self._config.maximum_retained_options,
                )
            except CurationReferenceError as exc:
                if attempt == 1:
                    correction = (
                        "\n\nCORRECTION REQUIRED: Use only supplied candidate IDs, preserve "
                        "candidate_type, use each candidate at most once, do not repeat a retained "
                        "option as a near-miss, and respect the option maximum."
                    )
                    continue
                raise CurationError(
                    "Final curation remained invalid after one corrective retry.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                ) from exc

            usage = response.usage
            diagnostics = CurationDiagnostics(
                model=self._model,
                success=True,
                input_event_cards=len(context.event_cards),
                input_hike_candidates=len(context.hike_candidates),
                retained_options=len(curation.options),
                attempts=attempt,
                latency_seconds=monotonic() - started,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
            )
            _log_diagnostics(diagnostics)
            return CurationOutcome(curation=curation, diagnostics=diagnostics)
        raise CurationError("OpenAI final curation produced no valid result.")


async def curate_with_fallback(
    service: OpenAICurationService,
    context: RecommendationContext,
) -> CurationOutcome:
    try:
        return await service.curate(context)
    except CurationError as exc:
        diagnostics = CurationDiagnostics(
            model=service.model,
            success=False,
            fallback_reason=str(exc),
            input_event_cards=len(context.event_cards),
            input_hike_candidates=len(context.hike_candidates),
            retained_options=0,
            attempts=exc.attempts,
            latency_seconds=exc.latency_seconds,
        )
        _log_diagnostics(diagnostics)
        return CurationOutcome(curation=None, diagnostics=diagnostics)


def validate_curation_references(
    context: RecommendationContext,
    curation: WeekendCuration,
    *,
    maximum_options: int = 18,
) -> None:
    if len(curation.options) > maximum_options:
        raise CurationReferenceError("Curation exceeded the option maximum.")
    allowed: dict[str, CandidateType] = {
        candidate.candidate_id: CandidateType.EVENT for candidate in context.event_cards
    }
    allowed.update(
        {candidate.candidate_id: CandidateType.HIKE for candidate in context.hike_candidates}
    )
    retained: set[str] = set()
    for option in curation.options:
        expected_type = allowed.get(option.candidate_id)
        if expected_type is None:
            raise CurationReferenceError("Curation referenced an unknown candidate ID.")
        if option.candidate_type is not expected_type:
            raise CurationReferenceError("Curation used the wrong candidate type.")
        if option.candidate_id in retained:
            raise CurationReferenceError("Curation retained a candidate more than once.")
        retained.add(option.candidate_id)
    near_misses: set[str] = set()
    for near_miss in curation.notable_near_misses:
        expected_type = allowed.get(near_miss.candidate_id)
        if expected_type is None:
            raise CurationReferenceError("Near-miss referenced an unknown candidate ID.")
        if near_miss.candidate_type is not expected_type:
            raise CurationReferenceError("Near-miss used the wrong candidate type.")
        if near_miss.candidate_id in retained:
            raise CurationReferenceError("A retained candidate was also listed as a near-miss.")
        if near_miss.candidate_id in near_misses:
            raise CurationReferenceError("A near-miss candidate was repeated.")
        near_misses.add(near_miss.candidate_id)


def _log_diagnostics(diagnostics: CurationDiagnostics) -> None:
    latency = (
        f"{diagnostics.latency_seconds:.2f}s" if diagnostics.latency_seconds is not None else "n/a"
    )
    print(
        "AI stage=final_curation "
        f"status={'success' if diagnostics.success else 'fallback'} "
        f"model={diagnostics.model} events={diagnostics.input_event_cards} "
        f"hikes={diagnostics.input_hike_candidates} retained={diagnostics.retained_options} "
        f"attempts={diagnostics.attempts} latency={latency} "
        f"tokens={diagnostics.total_tokens if diagnostics.total_tokens is not None else 'n/a'}"
    )
