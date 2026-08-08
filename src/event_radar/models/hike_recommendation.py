from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from event_radar.models.hike import Hike
from event_radar.models.weather import WeatherCondition


class AccessStatus(StrEnum):
    UNCHECKED = "unchecked"


class HikeAccessContext(BaseModel):
    status: AccessStatus = AccessStatus.UNCHECKED
    dynamic_status_verified: Literal[False] = False
    parking_notes: str
    access_baseline_notes: str
    seasonal_access_notes: str
    important_route_notes: str


class HikeWindowWeather(BaseModel):
    minimum_temperature_f: float
    maximum_temperature_f: float
    maximum_apparent_temperature_f: float
    maximum_precipitation_probability: float | None = Field(default=None, ge=0, le=100)
    precipitation_inches: float | None = Field(default=None, ge=0)
    maximum_wind_speed_mph: float = Field(ge=0)
    maximum_wind_gust_mph: float | None = Field(default=None, ge=0)
    conditions: list[WeatherCondition]
    hourly_points: int = Field(gt=0)


class HikeWindowEvaluation(BaseModel):
    start_time: datetime
    estimated_finish_time: datetime
    eligible: bool
    score: int
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)
    weather: HikeWindowWeather


class HikeDayEvaluation(BaseModel):
    hike: Hike
    date: date
    eligible: bool
    score: int
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)
    best_window: HikeWindowEvaluation | None = None
    window_evaluations: list[HikeWindowEvaluation] = Field(default_factory=list)
    access: HikeAccessContext


class HikeCandidate(BaseModel):
    hike: Hike
    best_day: date
    best_window: HikeWindowEvaluation
    score: int
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    alternate_day_evaluations: list[HikeDayEvaluation] = Field(default_factory=list)
    access: HikeAccessContext


class HikeCandidateSelection(BaseModel):
    day_evaluations: list[HikeDayEvaluation]
    candidates: list[HikeCandidate]
    unique_weather_locations_requested: int
    weather_location_failures: int

    @property
    def viable_day_count(self) -> int:
        return sum(evaluation.eligible for evaluation in self.day_evaluations)

    @property
    def hard_infeasible_day_count(self) -> int:
        return sum(
            not evaluation.eligible
            and "trailhead weather unavailable" not in evaluation.exclusion_reasons
            for evaluation in self.day_evaluations
        )

    @property
    def weather_unavailable_day_count(self) -> int:
        return sum(
            "trailhead weather unavailable" in evaluation.exclusion_reasons
            for evaluation in self.day_evaluations
        )
