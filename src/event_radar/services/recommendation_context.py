import hashlib
import re
import unicodedata
from datetime import UTC, datetime

from event_radar.curation_config import DEFAULT_CURATION_CONFIG, CurationConfig
from event_radar.models.curation import (
    BaselineWeatherContext,
    DailyWeatherContext,
    HikeCandidateContext,
    HikeWeatherContext,
    ImportantUnknown,
    ImportantUnknownKind,
    RecommendationContext,
)
from event_radar.models.direction import Direction
from event_radar.models.event import Event
from event_radar.models.event_analysis import WeekendEventCard
from event_radar.models.hike_recommendation import HikeCandidate, HikeCandidateSelection
from event_radar.models.user_context import UserContext, structured_runtime_context
from event_radar.models.weather import WeekendWeather

_NON_WORD_PATTERN = re.compile(r"[^\w]+", re.UNICODE)


def build_recommendation_context(
    *,
    generated_at: datetime,
    weekend_start: datetime,
    weekend_end: datetime,
    user_context: UserContext,
    personal_experience_context: str,
    permanent_directions: list[Direction],
    temporary_directions: list[Direction],
    baseline_weather: WeekendWeather | None,
    event_cards: list[WeekendEventCard],
    hike_selection: HikeCandidateSelection,
    event_pipeline_notes: list[str] | None = None,
    config: CurationConfig = DEFAULT_CURATION_CONFIG,
) -> RecommendationContext:
    hike_candidates = [
        _hike_context(candidate)
        for candidate in hike_selection.candidates[: config.maximum_hike_candidates]
    ]
    notes = event_pipeline_notes or []
    known_unknowns = _known_unknowns(
        event_cards=event_cards,
        hike_candidates=hike_candidates,
        baseline_weather=baseline_weather,
        hike_weather_failures=hike_selection.weather_location_failures,
        event_pipeline_notes=notes,
    )
    return RecommendationContext(
        generated_at=generated_at,
        weekend_start=weekend_start,
        weekend_end=weekend_end,
        user_context=structured_runtime_context(user_context),
        personal_experience_context=personal_experience_context,
        permanent_directions=[direction.text for direction in permanent_directions],
        temporary_directions=[direction.text for direction in temporary_directions],
        baseline_weather=_weather_context(baseline_weather),
        event_cards=event_cards,
        hike_candidates=hike_candidates,
        known_unknowns=known_unknowns,
        event_pipeline_notes=notes,
    )


def event_candidate_id(event: Event) -> str:
    """Build a stable occurrence identity independent of candidate ordering."""
    identity = "|".join(
        (
            _normalize(event.title),
            event.start_time.astimezone(UTC).isoformat(),
            _normalize(event.city),
            _normalize(event.source_name),
            event.source_id or str(event.source_url),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"event_{digest}"


def recommendation_context_size(context: RecommendationContext) -> tuple[int, int]:
    characters = len(context.model_dump_json())
    return characters, (characters + 3) // 4


def _hike_context(candidate: HikeCandidate) -> HikeCandidateContext:
    hike = candidate.hike
    window = candidate.best_window
    weather = window.weather
    return HikeCandidateContext(
        candidate_id=hike.id,
        name=hike.name,
        park_or_area=hike.park_or_area,
        region=hike.region,
        nearest_city=hike.nearest_city,
        day=candidate.best_day,
        best_start_time=window.start_time,
        estimated_finish_time=window.estimated_finish_time,
        distance_miles=hike.distance_miles,
        elevation_gain_ft=hike.elevation_gain_ft,
        duration_min_minutes=hike.estimated_duration_minutes.min,
        duration_max_minutes=hike.estimated_duration_minutes.max,
        difficulty=hike.difficulty.value,
        settings=hike.setting,
        shade=hike.shade.value,
        exposure=hike.exposure.value,
        scenic_value=hike.scenic_value.value,
        experience_tags=hike.experience_tags,
        solo_fit=hike.solo_fit.value,
        drive_friction=hike.drive_friction_from_santa_rosa.value,
        deterministic_score=candidate.score,
        weather=HikeWeatherContext(
            temperature_min_f=weather.minimum_temperature_f,
            temperature_max_f=weather.maximum_temperature_f,
            apparent_temperature_max_f=weather.maximum_apparent_temperature_f,
            precipitation_probability_max=weather.maximum_precipitation_probability,
            precipitation_inches=weather.precipitation_inches,
            wind_speed_max_mph=weather.maximum_wind_speed_mph,
            wind_gust_max_mph=weather.maximum_wind_gust_mph,
            conditions=weather.conditions,
        ),
        deterministic_reasons=candidate.reasons,
        cautions=candidate.cautions,
        official_source_url=hike.official_source_url,
        parking_notes=candidate.access.parking_notes,
        access_baseline_notes=candidate.access.access_baseline_notes,
        seasonal_access_notes=candidate.access.seasonal_access_notes,
        important_route_notes=candidate.access.important_route_notes,
    )


def _weather_context(weather: WeekendWeather | None) -> BaselineWeatherContext | None:
    if weather is None:
        return None
    return BaselineWeatherContext(
        location_name=weather.location.name,
        provider_timezone=weather.provider_timezone,
        days=[
            DailyWeatherContext(
                date=day.date,
                condition=day.condition,
                temperature_high_f=day.temperature_high_f,
                temperature_low_f=day.temperature_low_f,
                precipitation_probability_max=day.precipitation_probability_max,
                precipitation_inches=day.precipitation_inches,
                max_wind_speed_mph=day.max_wind_speed_mph,
                max_wind_gust_mph=day.max_wind_gust_mph,
                sunrise=day.sunrise,
                sunset=day.sunset,
            )
            for day in weather.days
        ],
    )


def _known_unknowns(
    *,
    event_cards: list[WeekendEventCard],
    hike_candidates: list[HikeCandidateContext],
    baseline_weather: WeekendWeather | None,
    hike_weather_failures: int,
    event_pipeline_notes: list[str],
) -> list[ImportantUnknown]:
    unknowns: list[ImportantUnknown] = []
    occurrences = [occurrence for card in event_cards for occurrence in card.occurrences]
    if any(
        occurrence.price_min is None and occurrence.price_max is None for occurrence in occurrences
    ):
        unknowns.append(
            ImportantUnknown(
                kind=ImportantUnknownKind.EVENT_PRICE,
                detail="Event prices remain unknown where source evidence does not provide them.",
            )
        )
    if event_cards or hike_candidates:
        unknowns.extend(
            [
                ImportantUnknown(
                    kind=ImportantUnknownKind.TRAVEL_TIME,
                    detail="Travel times are not calculated; no routing service is active.",
                ),
                ImportantUnknown(
                    kind=ImportantUnknownKind.DEMOGRAPHICS,
                    detail=(
                        "Attendance, crowd density, demographics, gender composition, "
                        "and relationship status are unknown."
                    ),
                ),
            ]
        )
    if event_cards:
        unknowns.append(
            ImportantUnknown(
                kind=ImportantUnknownKind.EVENT_AVAILABILITY,
                detail="Ticket and registration availability is not verified.",
            )
        )
    for note in event_pipeline_notes:
        kind = (
            ImportantUnknownKind.WEB_DISCOVERY
            if "web discovery" in note.casefold()
            else ImportantUnknownKind.EVENT_ANALYSIS
        )
        unknowns.append(ImportantUnknown(kind=kind, detail=note))
    if hike_candidates:
        unknowns.extend(
            [
                ImportantUnknown(
                    kind=ImportantUnknownKind.HIKE_ACCESS,
                    detail=(
                        "Hike access, closures, reservations, parking availability, "
                        "and route conditions are not verified."
                    ),
                ),
                ImportantUnknown(
                    kind=ImportantUnknownKind.RECENT_PRECIPITATION,
                    detail="Recent trail moisture and mud conditions are unknown.",
                ),
            ]
        )
        if any(
            {"coast", "beach"} & {tag.casefold() for tag in hike.experience_tags}
            for hike in hike_candidates
        ):
            unknowns.append(
                ImportantUnknown(
                    kind=ImportantUnknownKind.TIDE_SURF,
                    detail="Tide and surf status is not verified where relevant.",
                )
            )
    weather_details: list[str] = []
    if baseline_weather is None:
        weather_details.append("Regional baseline weather is unavailable")
    if hike_weather_failures:
        weather_details.append(
            f"trailhead forecasts failed for {hike_weather_failures} location(s)"
        )
    if weather_details:
        unknowns.append(
            ImportantUnknown(
                kind=ImportantUnknownKind.WEATHER_AVAILABILITY,
                detail="; ".join(weather_details) + ".",
            )
        )
    by_kind: dict[ImportantUnknownKind, ImportantUnknown] = {}
    for unknown in unknowns:
        by_kind.setdefault(unknown.kind, unknown)
    return list(by_kind.values())


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _NON_WORD_PATTERN.split(normalized) if part)
