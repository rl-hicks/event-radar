from pathlib import Path
from time import monotonic

from openai import AsyncOpenAI

from event_radar.config import DEFAULT_OPENAI_MODEL, settings
from event_radar.curation_config import DEFAULT_CURATION_CONFIG, CurationConfig
from event_radar.models.curation import (
    CandidateType,
    CurationDiagnostics,
    CurationOutcome,
    RecommendationContext,
    WeekendCuration,
)
from event_radar.models.token_usage import (
    ModelTokenPricing,
    TokenUsage,
    aggregate_token_usage,
    format_token_usage,
    parse_token_usage,
    token_usage_fields,
)


class CurationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        latency_seconds: float | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.latency_seconds = latency_seconds
        self.usage = usage or TokenUsage()


class CurationReferenceError(CurationError):
    """Raised for semantic candidate-reference errors that permit one correction."""


class OpenAICurationService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = DEFAULT_OPENAI_MODEL,
        prompt_path: Path = Path("prompts/weekend_curation.md"),
        timeout_seconds: float = 20.0,
        client: AsyncOpenAI | None = None,
        pricing: ModelTokenPricing | None = None,
        config: CurationConfig = DEFAULT_CURATION_CONFIG,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._prompt_path = prompt_path
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._pricing = pricing or ModelTokenPricing.from_settings(settings, model)
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
        usage = TokenUsage()
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
                    usage=usage,
                ) from exc
            usage = aggregate_token_usage(
                [usage, parse_token_usage(getattr(response, "usage", None), self._pricing)]
            )
            if response.status == "incomplete" or response.error is not None:
                raise CurationError(
                    "OpenAI final-curation response was incomplete or erroneous.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                    usage=usage,
                )
            curation = response.output_parsed
            if curation is None:
                raise CurationError(
                    "OpenAI final curation returned no structured result.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                    usage=usage,
                )
            try:
                validate_curation_references(
                    context,
                    curation,
                    maximum_event_options=self._config.maximum_event_options,
                    maximum_hike_options=self._config.maximum_hike_options,
                )
            except CurationReferenceError as exc:
                if attempt == 1:
                    correction = (
                        "\n\nCORRECTION REQUIRED: Use only supplied candidate IDs, preserve "
                        "candidate_type, place events only in event_options and independent hikes "
                        "only in hike_options, use each candidate at most once, do not repeat a "
                        "retained option as a near-miss, and respect the separate "
                        "collection maxima."
                    )
                    continue
                raise CurationError(
                    "Final curation remained invalid after one corrective retry.",
                    attempts=attempt,
                    latency_seconds=monotonic() - started,
                    usage=usage,
                ) from exc

            diagnostics = CurationDiagnostics(
                model=self._model,
                success=True,
                input_event_cards=len(context.event_cards),
                input_hike_candidates=len(context.hike_candidates),
                retained_event_count=len(curation.event_options),
                retained_hike_count=len(curation.hike_options),
                retained_total_count=len(curation.event_options) + len(curation.hike_options),
                attempts=attempt,
                latency_seconds=monotonic() - started,
                **token_usage_fields(usage),
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
            retained_event_count=0,
            retained_hike_count=0,
            retained_total_count=0,
            attempts=exc.attempts,
            latency_seconds=exc.latency_seconds,
            **token_usage_fields(exc.usage),
        )
        _log_diagnostics(diagnostics)
        return CurationOutcome(curation=None, diagnostics=diagnostics)


def validate_curation_references(
    context: RecommendationContext,
    curation: WeekendCuration,
    *,
    maximum_event_options: int = 22,
    maximum_hike_options: int = 6,
) -> None:
    if len(curation.event_options) > maximum_event_options:
        raise CurationReferenceError("Curation exceeded the event-option maximum.")
    if len(curation.hike_options) > maximum_hike_options:
        raise CurationReferenceError("Curation exceeded the hike-option maximum.")

    allowed_events = {candidate.candidate_id for candidate in context.event_cards}
    allowed_hikes = {candidate.candidate_id for candidate in context.hike_candidates}
    retained: set[str] = set()
    for event_option in curation.event_options:
        if event_option.candidate_id not in allowed_events:
            raise CurationReferenceError(
                "Event curation referenced an unknown or non-event candidate ID."
            )
        if event_option.candidate_id in retained:
            raise CurationReferenceError("Curation retained a candidate more than once.")
        retained.add(event_option.candidate_id)
    for hike_option in curation.hike_options:
        if hike_option.candidate_id not in allowed_hikes:
            raise CurationReferenceError(
                "Hike curation referenced an unknown or non-hike candidate ID."
            )
        if hike_option.candidate_id in retained:
            raise CurationReferenceError("Curation retained a candidate more than once.")
        retained.add(hike_option.candidate_id)

    allowed: dict[str, CandidateType] = {
        **{candidate_id: CandidateType.EVENT for candidate_id in allowed_events},
        **{candidate_id: CandidateType.HIKE for candidate_id in allowed_hikes},
    }
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
        f"hikes={diagnostics.input_hike_candidates} "
        f"retained_events={diagnostics.retained_event_count} "
        f"retained_hikes={diagnostics.retained_hike_count} "
        f"retained_total={diagnostics.retained_total_count} "
        f"attempts={diagnostics.attempts} latency={latency} "
        f"tokens={diagnostics.total_tokens if diagnostics.total_tokens is not None else 'n/a'} "
        f"{format_token_usage(diagnostics)}"
    )
