from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class WeatherCondition(StrEnum):
    """Human-readable WMO weather interpretation used by the application."""

    CLEAR = "clear"
    MAINLY_CLEAR = "mainly clear"
    PARTLY_CLOUDY = "partly cloudy"
    OVERCAST = "overcast"
    FOG = "fog"
    DRIZZLE = "drizzle"
    FREEZING_DRIZZLE = "freezing drizzle"
    RAIN = "rain"
    FREEZING_RAIN = "freezing rain"
    SNOW = "snow"
    RAIN_SHOWERS = "rain showers"
    SNOW_SHOWERS = "snow showers"
    THUNDERSTORM = "thunderstorm"
    THUNDERSTORM_WITH_HAIL = "thunderstorm with hail"
    UNKNOWN = "unknown"


def weather_condition_from_code(code: int) -> WeatherCondition:
    """Map an Open-Meteo WMO weather code to an application condition."""
    if code == 0:
        return WeatherCondition.CLEAR
    if code == 1:
        return WeatherCondition.MAINLY_CLEAR
    if code == 2:
        return WeatherCondition.PARTLY_CLOUDY
    if code == 3:
        return WeatherCondition.OVERCAST
    if code in {45, 48}:
        return WeatherCondition.FOG
    if code in {51, 53, 55}:
        return WeatherCondition.DRIZZLE
    if code in {56, 57}:
        return WeatherCondition.FREEZING_DRIZZLE
    if code in {61, 63, 65}:
        return WeatherCondition.RAIN
    if code in {66, 67}:
        return WeatherCondition.FREEZING_RAIN
    if code in {71, 73, 75, 77}:
        return WeatherCondition.SNOW
    if code in {80, 81, 82}:
        return WeatherCondition.RAIN_SHOWERS
    if code in {85, 86}:
        return WeatherCondition.SNOW_SHOWERS
    if code == 95:
        return WeatherCondition.THUNDERSTORM
    if code in {96, 99}:
        return WeatherCondition.THUNDERSTORM_WITH_HAIL
    return WeatherCondition.UNKNOWN


def _validate_timezone_name(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {value}") from exc
    return value


def _validate_aware_datetime(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Weather datetimes must be timezone-aware.")
    return value


class WeatherLocation(BaseModel):
    """A forecastable coordinate and its expected local timezone."""

    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    timezone: str = Field(min_length=1)

    _timezone_is_valid = field_validator("timezone")(_validate_timezone_name)


class HourlyWeather(BaseModel):
    """Normalized forecast values for one local hour."""

    time: datetime
    temperature_f: float
    apparent_temperature_f: float | None = None
    precipitation_probability: float | None = Field(default=None, ge=0, le=100)
    precipitation_inches: float | None = Field(default=None, ge=0)
    weather_code: int
    condition: WeatherCondition
    wind_speed_mph: float = Field(ge=0)
    wind_gust_mph: float | None = Field(default=None, ge=0)

    _time_is_aware = field_validator("time")(_validate_aware_datetime)


class DailyWeather(BaseModel):
    """Normalized daily summary with hourly detail for future reasoning."""

    date: date
    temperature_high_f: float
    temperature_low_f: float
    apparent_temperature_high_f: float | None = None
    apparent_temperature_low_f: float | None = None
    precipitation_probability_max: float | None = Field(default=None, ge=0, le=100)
    precipitation_inches: float | None = Field(default=None, ge=0)
    weather_code: int
    condition: WeatherCondition
    max_wind_speed_mph: float | None = Field(default=None, ge=0)
    max_wind_gust_mph: float | None = Field(default=None, ge=0)
    sunrise: datetime
    sunset: datetime
    daylight_duration_seconds: float | None = Field(default=None, ge=0)
    hourly: list[HourlyWeather] = Field(default_factory=list)

    _sunrise_is_aware = field_validator("sunrise")(_validate_aware_datetime)
    _sunset_is_aware = field_validator("sunset")(_validate_aware_datetime)


class WeekendWeather(BaseModel):
    """Application-owned weather context for a requested date range."""

    location: WeatherLocation
    provider_timezone: str
    utc_offset_seconds: int
    generated_at: datetime
    days: list[DailyWeather]

    _provider_timezone_is_valid = field_validator("provider_timezone")(_validate_timezone_name)
    _generated_at_is_aware = field_validator("generated_at")(_validate_aware_datetime)
