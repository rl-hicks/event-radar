import asyncio
from dataclasses import dataclass
from datetime import datetime

import httpx

from event_radar.collectors.happening_sonoma import (
    HappeningSonomaCollector,
    HappeningSonomaCollectorError,
)
from event_radar.collectors.sonoma_county import SonomaCountyCollector, SonomaCountyCollectorError
from event_radar.config import Settings
from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.curation import RecommendationContext
from event_radar.models.direction import Direction
from event_radar.models.event import Event
from event_radar.models.event_analysis import (
    ScrapedEventAnalysisOutcome,
    ScrapedEventAnalysisRequest,
    WeekendEventCard,
)
from event_radar.models.hike_recommendation import HikeCandidateSelection
from event_radar.models.recommendation import CandidateSelection
from event_radar.models.user_context import UserContext
from event_radar.models.weather import WeatherLocation, WeekendWeather
from event_radar.models.web_discovery import WebDiscoveryOutcome, WebDiscoveryRequest
from event_radar.services.event_analysis import (
    OpenAIEventAnalysisService,
    analyze_scraped_events_with_fallback,
)
from event_radar.services.event_cards import (
    build_scraped_analysis_request,
    build_scraped_event_cards,
    build_web_discovery_request,
    build_web_event_cards,
    remove_exact_web_duplicates,
)
from event_radar.services.event_deduplication import DeduplicationResult, deduplicate_events
from event_radar.services.event_evaluation import select_event_candidates
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.hike_suitability import build_hike_candidate_selection
from event_radar.services.hike_weather import collect_trailhead_weather
from event_radar.services.personal_context import (
    PersonalContextStage,
    PersonalExperienceContext,
)
from event_radar.services.recommendation_context import build_recommendation_context
from event_radar.services.weather import (
    OpenMeteoWeatherClient,
    WeatherProviderError,
    filter_weather_to_window,
    forecast_dates_for_window,
)
from event_radar.services.web_event_discovery import (
    OpenAIWebDiscoveryService,
    discover_events_with_fallback,
)
from event_radar.services.weekend import upcoming_weekend_window


@dataclass(frozen=True)
class ExternalSourceStatus:
    success: bool
    count: int
    failure_reason: str | None = None


@dataclass(frozen=True)
class EventSourceCollection:
    events: list[Event]
    status: ExternalSourceStatus


@dataclass(frozen=True)
class WeatherFetchResult:
    weather: WeekendWeather | None
    failure_reason: str | None = None


@dataclass(frozen=True)
class RecommendationPipelineResult:
    generated_at: datetime
    weekend_start: datetime
    weekend_end: datetime
    user_context: UserContext
    personal_context: PersonalExperienceContext
    permanent_directions: list[Direction]
    temporary_directions: list[Direction]
    sonoma_tourism_events: list[Event]
    happening_sonoma_events: list[Event]
    sonoma_tourism_status: ExternalSourceStatus
    happening_sonoma_status: ExternalSourceStatus
    weather_failure_reason: str | None
    deduplication: DeduplicationResult
    valid_events: list[Event]
    factual_rejections: dict[str, list[str]]
    legacy_event_selection: CandidateSelection
    hike_selection: HikeCandidateSelection
    hike_catalog_size: int
    baseline_weather: WeekendWeather | None


@dataclass(frozen=True)
class EventIntelligenceResult:
    analysis_request: ScrapedEventAnalysisRequest
    web_request: WebDiscoveryRequest
    analysis_outcome: ScrapedEventAnalysisOutcome
    web_outcome: WebDiscoveryOutcome
    scraped_event_cards: list[WeekendEventCard]
    web_event_cards: list[WeekendEventCard]
    combined_event_cards: list[WeekendEventCard]
    context: RecommendationContext


async def fetch_baseline_weather(
    client: OpenMeteoWeatherClient,
    location: WeatherLocation,
    start: datetime,
    end: datetime,
) -> WeekendWeather | None:
    """Fetch weather without making a provider outage suppress the event digest."""
    return (await fetch_baseline_weather_with_status(client, location, start, end)).weather


async def fetch_baseline_weather_with_status(
    client: OpenMeteoWeatherClient,
    location: WeatherLocation,
    start: datetime,
    end: datetime,
) -> WeatherFetchResult:
    forecast_start, forecast_end = forecast_dates_for_window(start, end, location)
    try:
        weather = await client.get_forecast(location, forecast_start, forecast_end)
    except WeatherProviderError as exc:
        reason = str(exc)
        print(f"Weather unavailable: {reason}")
        return WeatherFetchResult(weather=None, failure_reason=reason)
    return WeatherFetchResult(
        weather=filter_weather_to_window(weather, start, end),
        failure_reason=None,
    )


async def collect_event_sources(
    sonoma_collector: SonomaCountyCollector,
    happening_collector: HappeningSonomaCollector,
    *,
    start: datetime,
    end: datetime,
) -> tuple[EventSourceCollection, EventSourceCollection]:
    """Collect fixed feeds independently, degrading only known provider failures."""

    async def collect_sonoma() -> EventSourceCollection:
        try:
            events = await sonoma_collector.collect(start=start, end=end)
        except SonomaCountyCollectorError as exc:
            reason = str(exc)
            print(f"Sonoma County Tourism unavailable: {reason}")
            return EventSourceCollection(
                events=[],
                status=ExternalSourceStatus(success=False, count=0, failure_reason=reason),
            )
        return EventSourceCollection(
            events=events,
            status=ExternalSourceStatus(success=True, count=len(events)),
        )

    async def collect_happening() -> EventSourceCollection:
        try:
            events = await happening_collector.collect(start=start, end=end)
        except HappeningSonomaCollectorError as exc:
            reason = str(exc)
            print(f"Happening in Sonoma County unavailable: {reason}")
            return EventSourceCollection(
                events=[],
                status=ExternalSourceStatus(success=False, count=0, failure_reason=reason),
            )
        return EventSourceCollection(
            events=events,
            status=ExternalSourceStatus(success=True, count=len(events)),
        )

    sonoma_result, happening_result = await asyncio.gather(
        collect_sonoma(),
        collect_happening(),
    )
    return sonoma_result, happening_result


async def build_recommendation_pipeline(
    *,
    generated_at: datetime,
    user_context: UserContext,
    personal_context: PersonalExperienceContext,
    permanent_directions: list[Direction],
    temporary_directions: list[Direction],
    runtime_settings: Settings,
) -> RecommendationPipelineResult:
    """Collect factual inventory/weather/hikes; legacy scoring is diagnostic only."""
    start, end = upcoming_weekend_window(generated_at)
    sonoma_collector = SonomaCountyCollector(
        user_agent=runtime_settings.user_agent,
        timeout_seconds=runtime_settings.request_timeout_seconds,
    )
    happening_collector = HappeningSonomaCollector(
        user_agent=runtime_settings.user_agent,
        timeout_seconds=runtime_settings.request_timeout_seconds,
    )
    weather_location = WeatherLocation(
        name=runtime_settings.weather_location_name,
        latitude=runtime_settings.weather_latitude,
        longitude=runtime_settings.weather_longitude,
        timezone=runtime_settings.weather_timezone,
    )
    hike_catalog = HikeCatalogRepository(runtime_settings.hike_catalog_path).load()
    async with httpx.AsyncClient() as weather_http_client:
        weather_client = OpenMeteoWeatherClient(
            user_agent=runtime_settings.user_agent,
            timeout_seconds=runtime_settings.request_timeout_seconds,
            client=weather_http_client,
        )
        source_results, weather_result, hike_weather = await asyncio.gather(
            collect_event_sources(
                sonoma_collector,
                happening_collector,
                start=start,
                end=end,
            ),
            fetch_baseline_weather_with_status(weather_client, weather_location, start, end),
            collect_trailhead_weather(
                hike_catalog.hikes,
                weather_client,
                start,
                end,
                timezone=runtime_settings.weather_timezone,
            ),
        )

    sonoma_result, happening_result = source_results
    sonoma_events = sonoma_result.events
    happening_events = happening_result.events
    weather = weather_result.weather
    deduplication = deduplicate_events([*sonoma_events, *happening_events])
    valid_events: list[Event] = []
    factual_rejections: dict[str, list[str]] = {}
    for event in deduplication.events:
        reasons = _factual_rejection_reasons(event, start, end)
        if reasons:
            factual_rejections[event.source_id or str(event.source_url)] = reasons
        else:
            valid_events.append(event)

    legacy_selection = select_event_candidates(valid_events, start=start, end=end)
    hike_selection = build_hike_candidate_selection(
        hike_catalog.hikes,
        hike_weather,
        start,
        end,
        timezone=runtime_settings.weather_timezone,
    )
    return RecommendationPipelineResult(
        generated_at=generated_at,
        weekend_start=start,
        weekend_end=end,
        user_context=user_context,
        personal_context=personal_context,
        permanent_directions=permanent_directions,
        temporary_directions=temporary_directions,
        sonoma_tourism_events=sonoma_events,
        happening_sonoma_events=happening_events,
        sonoma_tourism_status=sonoma_result.status,
        happening_sonoma_status=happening_result.status,
        weather_failure_reason=weather_result.failure_reason,
        deduplication=deduplication,
        valid_events=valid_events,
        factual_rejections=factual_rejections,
        legacy_event_selection=legacy_selection,
        hike_selection=hike_selection,
        hike_catalog_size=len(hike_catalog.hikes),
        baseline_weather=weather,
    )


async def build_event_intelligence(
    pipeline: RecommendationPipelineResult,
    *,
    analysis_service: OpenAIEventAnalysisService,
    web_service: OpenAIWebDiscoveryService,
) -> EventIntelligenceResult:
    request = _analysis_request(pipeline)
    web_request = build_web_discovery_request(
        request,
        personal_experience_context=pipeline.personal_context.projection(
            PersonalContextStage.WEB_EVENT_DISCOVERY
        ),
    )
    if request.events:
        analysis_outcome, web_outcome = await asyncio.gather(
            analyze_scraped_events_with_fallback(analysis_service, request),
            discover_events_with_fallback(web_service, web_request),
        )
    else:
        analysis_outcome = ScrapedEventAnalysisOutcome(
            analysis=None,
            diagnostics=AIStageDiagnostics(
                stage="scraped_event_analysis",
                model=analysis_service.model,
                success=False,
                fallback_reason=(
                    "No fixed-feed events were available; AI #1 was intentionally skipped."
                ),
                input_count=0,
                result_count=0,
                attempts=0,
            ),
        )
        web_outcome = await discover_events_with_fallback(web_service, web_request)
    web_discoveries, duplicate_count = remove_exact_web_duplicates(
        web_outcome.valid_discoveries,
        request.events,
        timezone=pipeline.user_context.base_location.timezone,
    )
    if duplicate_count:
        web_outcome = web_outcome.model_copy(
            update={
                "valid_discoveries": web_discoveries,
                "duplicates_removed": web_outcome.duplicates_removed + duplicate_count,
                "diagnostics": web_outcome.diagnostics.model_copy(
                    update={"result_count": len(web_discoveries)}
                ),
            }
        )
    scraped_cards = build_scraped_event_cards(request, analysis_outcome.analysis)
    web_cards = build_web_event_cards(web_outcome.valid_discoveries)
    scraped_card_ids = {card.candidate_id for card in scraped_cards}
    unique_web_cards = [card for card in web_cards if card.candidate_id not in scraped_card_ids]
    id_collisions = len(web_cards) - len(unique_web_cards)
    if id_collisions:
        retained_discoveries = {card.candidate_id for card in unique_web_cards}
        web_outcome = web_outcome.model_copy(
            update={
                "valid_discoveries": [
                    discovery
                    for discovery in web_outcome.valid_discoveries
                    if discovery.discovery_id in retained_discoveries
                ],
                "duplicates_removed": web_outcome.duplicates_removed + id_collisions,
                "diagnostics": web_outcome.diagnostics.model_copy(
                    update={"result_count": len(unique_web_cards)}
                ),
            }
        )
    return _intelligence_result(
        pipeline,
        request=request,
        web_request=web_request,
        analysis_outcome=analysis_outcome,
        web_outcome=web_outcome,
        scraped_cards=scraped_cards,
        web_cards=unique_web_cards,
    )


def build_event_intelligence_without_ai(
    pipeline: RecommendationPipelineResult,
    *,
    model: str,
    reason: str,
) -> EventIntelligenceResult:
    request = _analysis_request(pipeline)
    web_request = build_web_discovery_request(
        request,
        personal_experience_context=pipeline.personal_context.projection(
            PersonalContextStage.WEB_EVENT_DISCOVERY
        ),
    )
    analysis_outcome = ScrapedEventAnalysisOutcome(
        analysis=None,
        diagnostics=AIStageDiagnostics(
            stage="scraped_event_analysis",
            model=model,
            success=False,
            fallback_reason=reason,
            input_count=len(request.events),
            result_count=0,
            attempts=0,
        ),
    )
    web_outcome = WebDiscoveryOutcome(
        result=None,
        valid_discoveries=[],
        duplicates_removed=0,
        diagnostics=AIStageDiagnostics(
            stage="web_event_discovery",
            model=model,
            success=False,
            fallback_reason=reason,
            input_count=len(request.events),
            result_count=0,
            attempts=0,
            tool_calls=0,
        ),
    )
    return _intelligence_result(
        pipeline,
        request=request,
        web_request=web_request,
        analysis_outcome=analysis_outcome,
        web_outcome=web_outcome,
        scraped_cards=build_scraped_event_cards(request, None),
        web_cards=[],
    )


def _intelligence_result(
    pipeline: RecommendationPipelineResult,
    *,
    request: ScrapedEventAnalysisRequest,
    web_request: WebDiscoveryRequest,
    analysis_outcome: ScrapedEventAnalysisOutcome,
    web_outcome: WebDiscoveryOutcome,
    scraped_cards: list[WeekendEventCard],
    web_cards: list[WeekendEventCard],
) -> EventIntelligenceResult:
    combined = [*scraped_cards, *web_cards]
    notes = _provider_research_notes(pipeline)
    if not analysis_outcome.diagnostics.success:
        if request.events:
            notes.append(
                "Scraped-event semantic analysis was unavailable; broad factual scraped cards "
                "were preserved without pretending analysis succeeded."
            )
        else:
            notes.append(
                "AI #1 scraped-event analysis was skipped because no fixed-feed events "
                "were available."
            )
    if not web_outcome.diagnostics.success:
        notes.append("Web discovery was unavailable; no web-discovered event cards were added.")
    context = build_recommendation_context(
        generated_at=pipeline.generated_at,
        weekend_start=pipeline.weekend_start,
        weekend_end=pipeline.weekend_end,
        user_context=pipeline.user_context,
        personal_experience_context=pipeline.personal_context.projection(
            PersonalContextStage.FINAL_CURATION
        ),
        permanent_directions=pipeline.permanent_directions,
        temporary_directions=pipeline.temporary_directions,
        baseline_weather=pipeline.baseline_weather,
        event_cards=combined,
        hike_selection=pipeline.hike_selection,
        event_pipeline_notes=notes,
    )
    return EventIntelligenceResult(
        analysis_request=request,
        web_request=web_request,
        analysis_outcome=analysis_outcome,
        web_outcome=web_outcome,
        scraped_event_cards=scraped_cards,
        web_event_cards=web_cards,
        combined_event_cards=combined,
        context=context,
    )


def _provider_research_notes(pipeline: RecommendationPipelineResult) -> list[str]:
    sonoma_ok = pipeline.sonoma_tourism_status.success
    happening_ok = pipeline.happening_sonoma_status.success
    notes: list[str] = []
    if not sonoma_ok and not happening_ok:
        notes.append(
            "Both fixed event feeds were unavailable "
            f"(Sonoma Tourism: {_concise_source_reason(pipeline.sonoma_tourism_status)}; "
            "Happening Sonoma: "
            f"{_concise_source_reason(pipeline.happening_sonoma_status)}); "
            "this run relies on web discovery and curated hikes."
        )
    elif not sonoma_ok:
        notes.append(
            "Sonoma County Tourism was unavailable "
            f"({_concise_source_reason(pipeline.sonoma_tourism_status)}); "
            "this run used Happening Sonoma and web discovery."
        )
    elif not happening_ok:
        notes.append(
            "Happening Sonoma was unavailable after bounded retries "
            f"({_concise_source_reason(pipeline.happening_sonoma_status)}); "
            "this run used Sonoma County Tourism and web discovery."
        )
    if pipeline.weather_failure_reason is not None:
        notes.append("Weather unavailable; weather-sensitive judgments are degraded.")
    return notes


def _concise_source_reason(status: ExternalSourceStatus) -> str:
    reason = (status.failure_reason or "").casefold()
    if "invalid json" in reason:
        return "invalid JSON response"
    if "schema/payload" in reason or "event listing" in reason:
        return "malformed provider payload"
    if "http status" in reason:
        return "HTTP status error"
    if "network failure" in reason or "timed out" in reason:
        return "network failure"
    return "provider request failed"


def _analysis_request(
    pipeline: RecommendationPipelineResult,
) -> ScrapedEventAnalysisRequest:
    return build_scraped_analysis_request(
        generated_at=pipeline.generated_at,
        weekend_start=pipeline.weekend_start,
        weekend_end=pipeline.weekend_end,
        user_context=pipeline.user_context,
        personal_experience_context=pipeline.personal_context.projection(
            PersonalContextStage.SCRAPED_EVENT_ANALYSIS
        ),
        permanent_directions=pipeline.permanent_directions,
        temporary_directions=pipeline.temporary_directions,
        events=pipeline.valid_events,
    )


def _factual_rejection_reasons(
    event: Event,
    start: datetime,
    end: datetime,
) -> list[str]:
    reasons: list[str] = []
    if event.start_time.utcoffset() is None:
        reasons.append("missing timezone-aware start time")
    elif not start <= event.start_time < end:
        reasons.append("outside requested date window")
    if event.end_time is not None:
        if event.end_time.utcoffset() is None:
            reasons.append("missing timezone-aware end time")
        elif event.end_time <= event.start_time:
            reasons.append("end time is not after start time")
    if not event.city.strip():
        reasons.append("missing usable city/location")
    return reasons
