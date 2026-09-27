from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from event_radar.models.event_analysis import WeekendEventCard
from event_radar.models.user_context import StructuredRuntimeContext
from event_radar.models.weather import WeatherCondition


def _aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Curation datetimes must be timezone-aware.")
    return value


class CandidateType(StrEnum):
    EVENT = "event"
    HIKE = "hike"


class ImportantUnknownKind(StrEnum):
    EVENT_PRICE = "event_price"
    TRAVEL_TIME = "travel_time"
    DEMOGRAPHICS = "demographics"
    EVENT_AVAILABILITY = "event_availability"
    HIKE_ACCESS = "hike_access"
    RECENT_PRECIPITATION = "recent_precipitation"
    TIDE_SURF = "tide_surf"
    WEATHER_AVAILABILITY = "weather_availability"
    EVENT_ANALYSIS = "event_analysis"
    WEB_DISCOVERY = "web_discovery"


class ImportantUnknown(BaseModel):
    kind: ImportantUnknownKind
    detail: str = Field(min_length=1)


class HikeWeatherContext(BaseModel):
    temperature_min_f: float
    temperature_max_f: float
    apparent_temperature_max_f: float
    precipitation_probability_max: float | None
    precipitation_inches: float | None
    wind_speed_max_mph: float
    wind_gust_max_mph: float | None
    conditions: list[WeatherCondition]


class HikeCandidateContext(BaseModel):
    candidate_type: Literal[CandidateType.HIKE] = CandidateType.HIKE
    candidate_id: str
    name: str
    park_or_area: str
    region: str
    nearest_city: str
    day: date
    best_start_time: datetime
    estimated_finish_time: datetime
    distance_miles: float
    elevation_gain_ft: int
    duration_min_minutes: int
    duration_max_minutes: int
    difficulty: str
    settings: list[str]
    shade: str
    exposure: str
    scenic_value: str
    experience_tags: list[str]
    solo_fit: str
    drive_friction: str
    deterministic_score: int
    weather: HikeWeatherContext
    deterministic_reasons: list[str]
    cautions: list[str]
    official_source_url: HttpUrl
    access_status: Literal["unchecked"] = "unchecked"
    access_warning: Literal[
        "Access status not verified - check official source before leaving."
    ] = "Access status not verified - check official source before leaving."
    parking_notes: str
    access_baseline_notes: str
    seasonal_access_notes: str
    important_route_notes: str

    _start_is_aware = field_validator("best_start_time")(_aware)
    _finish_is_aware = field_validator("estimated_finish_time")(_aware)


class DailyWeatherContext(BaseModel):
    date: date
    condition: WeatherCondition
    temperature_high_f: float
    temperature_low_f: float
    precipitation_probability_max: float | None
    precipitation_inches: float | None
    max_wind_speed_mph: float | None
    max_wind_gust_mph: float | None
    sunrise: datetime
    sunset: datetime

    _sunrise_is_aware = field_validator("sunrise")(_aware)
    _sunset_is_aware = field_validator("sunset")(_aware)


class BaselineWeatherContext(BaseModel):
    location_name: str
    provider_timezone: str
    days: list[DailyWeatherContext]


class RecommendationContext(BaseModel):
    """Authoritative facts plus unscored semantic event cards for final curation."""

    generated_at: datetime
    weekend_start: datetime
    weekend_end: datetime
    user_context: StructuredRuntimeContext
    personal_experience_context: str = Field(min_length=1)
    permanent_directions: list[str]
    temporary_directions: list[str]
    baseline_weather: BaselineWeatherContext | None
    event_cards: list[WeekendEventCard]
    hike_candidates: list[HikeCandidateContext]
    known_unknowns: list[ImportantUnknown]
    event_pipeline_notes: list[str] = Field(default_factory=list)

    _generated_is_aware = field_validator("generated_at")(_aware)
    _weekend_start_is_aware = field_validator("weekend_start")(_aware)
    _weekend_end_is_aware = field_validator("weekend_end")(_aware)

    @model_validator(mode="after")
    def validate_context_identity(self) -> "RecommendationContext":
        if self.weekend_end <= self.weekend_start:
            raise ValueError("Recommendation weekend end must follow its start.")
        candidate_ids = [
            *(candidate.candidate_id for candidate in self.event_cards),
            *(candidate.candidate_id for candidate in self.hike_candidates),
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Recommendation candidate IDs must be unique.")
        return self


class CurationRole(StrEnum):
    STANDOUT = "standout"
    STRONG = "strong"
    DISTINCT = "distinct"
    LOW_FRICTION = "low_friction"
    SCHEDULE_CONFLICT = "schedule_conflict"
    BACKUP = "backup"


class CurationConfidence(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class CuratedOption(BaseModel):
    candidate_type: CandidateType
    candidate_id: str = Field(min_length=1)
    role: CurationRole
    why_it_survived: str = Field(min_length=1)
    tradeoffs: list[str]
    social_observation: str = Field(min_length=1)
    solo_observation: str = Field(min_length=1)
    friction_observation: str = Field(min_length=1)
    schedule_observation: str = Field(min_length=1)
    confidence: CurationConfidence


class EventCuratedOption(CuratedOption):
    candidate_type: Literal[CandidateType.EVENT] = CandidateType.EVENT


class HikeCuratedOption(CuratedOption):
    candidate_type: Literal[CandidateType.HIKE] = CandidateType.HIKE


class NearMiss(BaseModel):
    candidate_type: CandidateType
    candidate_id: str = Field(min_length=1)
    reason_not_retained: str = Field(min_length=1)


class WeekendCuration(BaseModel):
    weekend_read: list[str] = Field(max_length=6)
    event_options: list[EventCuratedOption] = Field(max_length=22)
    hike_options: list[HikeCuratedOption] = Field(max_length=6)
    notable_near_misses: list[NearMiss] = Field(max_length=10)
    important_unknowns: list[ImportantUnknown] = Field(max_length=12)


class CurationDiagnostics(BaseModel):
    model: str
    success: bool
    fallback_reason: str | None = None
    input_event_cards: int
    input_hike_candidates: int
    retained_event_count: int
    retained_hike_count: int
    retained_total_count: int
    attempts: int
    latency_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class CurationOutcome(BaseModel):
    curation: WeekendCuration | None
    diagnostics: CurationDiagnostics
