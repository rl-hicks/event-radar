import math
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from event_radar.models.weather import (
    DailyWeather,
    HourlyWeather,
    WeatherLocation,
    WeekendWeather,
    weather_condition_from_code,
)

OPEN_METEO_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_gusts_10m",
)

DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "sunrise",
    "sunset",
    "daylight_duration",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
)


class WeatherProviderError(RuntimeError):
    """Raised when Open-Meteo cannot provide a valid normalized forecast."""


class OpenMeteoWeatherClient:
    """Coordinate-based client for Open-Meteo's best-match forecast."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def get_forecast(
        self,
        location: WeatherLocation,
        start_date: date,
        end_date: date,
    ) -> WeekendWeather:
        """Fetch an inclusive local-date forecast for arbitrary coordinates."""
        if end_date < start_date:
            raise ValueError("Weather forecast end date must not precede start date.")

        if self._client is not None:
            return await self._get_forecast_with_client(
                self._client,
                location,
                start_date,
                end_date,
            )

        async with httpx.AsyncClient() as client:
            return await self._get_forecast_with_client(
                client,
                location,
                start_date,
                end_date,
            )

    async def _get_forecast_with_client(
        self,
        client: httpx.AsyncClient,
        location: WeatherLocation,
        start_date: date,
        end_date: date,
    ) -> WeekendWeather:
        try:
            response = await client.get(
                OPEN_METEO_FORECAST_ENDPOINT,
                params={
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "timezone": location.timezone,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "hourly": ",".join(HOURLY_VARIABLES),
                    "daily": ",".join(DAILY_VARIABLES),
                },
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise WeatherProviderError("Could not fetch the Open-Meteo forecast.") from exc

        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            if response.is_error:
                raise WeatherProviderError(
                    f"Open-Meteo returned HTTP {response.status_code}."
                ) from exc
            raise WeatherProviderError("Open-Meteo returned invalid JSON.") from exc

        if isinstance(payload, dict) and payload.get("error") is True:
            reason = payload.get("reason")
            detail = reason if isinstance(reason, str) and reason else "unknown provider error"
            raise WeatherProviderError(f"Open-Meteo error: {detail}.")

        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WeatherProviderError(f"Open-Meteo returned HTTP {response.status_code}.") from exc

        if not isinstance(payload, dict):
            raise WeatherProviderError("Open-Meteo returned an invalid forecast payload.")

        return parse_open_meteo_forecast(
            cast(dict[str, object], payload),
            location=location,
            start_date=start_date,
            end_date=end_date,
        )


def forecast_dates_for_window(
    start: datetime,
    end: datetime,
    location: WeatherLocation,
) -> tuple[date, date]:
    """Derive inclusive local forecast dates from the canonical [start, end) window."""
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Weather window requires timezone-aware boundaries.")
    if end <= start:
        raise ValueError("Weather window end must be after start.")

    timezone = ZoneInfo(location.timezone)
    first_date = start.astimezone(timezone).date()
    last_date = (end - timedelta(microseconds=1)).astimezone(timezone).date()
    return first_date, last_date


def filter_weather_to_window(
    weather: WeekendWeather,
    start: datetime,
    end: datetime,
) -> WeekendWeather:
    """Keep full daily summaries and only hourly intervals overlapping [start, end)."""
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Weather window requires timezone-aware boundaries.")
    if end <= start:
        raise ValueError("Weather window end must be after start.")

    filtered_days = []
    for day in weather.days:
        filtered_hours = [
            hour
            for hour in day.hourly
            if hour.time < end and hour.time + timedelta(hours=1) > start
        ]
        filtered_days.append(day.model_copy(update={"hourly": filtered_hours}))

    return weather.model_copy(update={"days": filtered_days})


def parse_open_meteo_forecast(
    payload: dict[str, object],
    *,
    location: WeatherLocation,
    start_date: date,
    end_date: date,
) -> WeekendWeather:
    """Strictly normalize one Open-Meteo forecast response."""
    provider_timezone = payload.get("timezone")
    if not isinstance(provider_timezone, str):
        raise WeatherProviderError("Open-Meteo response was missing its timezone.")
    if provider_timezone != location.timezone:
        raise WeatherProviderError(
            f"Open-Meteo returned timezone {provider_timezone!r}; expected {location.timezone!r}."
        )
    timezone = ZoneInfo(provider_timezone)

    raw_utc_offset = payload.get("utc_offset_seconds")
    if not isinstance(raw_utc_offset, int) or isinstance(raw_utc_offset, bool):
        raise WeatherProviderError("Open-Meteo response had an invalid UTC offset.")

    hourly_block = _required_mapping(payload, "hourly")
    daily_block = _required_mapping(payload, "daily")
    hourly_arrays = _validated_arrays(hourly_block, ("time", *HOURLY_VARIABLES), "hourly")
    daily_arrays = _validated_arrays(daily_block, ("time", *DAILY_VARIABLES), "daily")

    requested_dates = _inclusive_dates(start_date, end_date)
    requested_date_set = set(requested_dates)
    hourly_by_date: dict[date, list[HourlyWeather]] = {
        requested_date: [] for requested_date in requested_dates
    }
    seen_hourly_times: set[datetime] = set()

    for index in range(len(hourly_arrays["time"])):
        hour = _parse_hourly(hourly_arrays, index, timezone)
        if hour.time in seen_hourly_times:
            raise WeatherProviderError(
                f"Open-Meteo returned duplicate hourly timestamp {hour.time.isoformat()}."
            )
        seen_hourly_times.add(hour.time)
        if hour.time.date() in requested_date_set:
            hourly_by_date[hour.time.date()].append(hour)

    daily_by_date: dict[date, DailyWeather] = {}
    for index in range(len(daily_arrays["time"])):
        forecast_date = _parse_date(
            daily_arrays["time"][index],
            f"daily.time[{index}]",
        )
        if forecast_date not in requested_date_set:
            continue
        if forecast_date in daily_by_date:
            raise WeatherProviderError(
                f"Open-Meteo returned duplicate daily forecast for {forecast_date}."
            )
        daily_by_date[forecast_date] = _parse_daily(
            daily_arrays,
            index,
            forecast_date,
            timezone,
            sorted(hourly_by_date[forecast_date], key=lambda item: item.time),
        )

    missing_dates = [item for item in requested_dates if item not in daily_by_date]
    if missing_dates:
        joined_dates = ", ".join(item.isoformat() for item in missing_dates)
        raise WeatherProviderError(
            f"Open-Meteo response was missing requested date(s): {joined_dates}."
        )

    missing_hourly_dates = [item for item in requested_dates if not hourly_by_date[item]]
    if missing_hourly_dates:
        joined_dates = ", ".join(item.isoformat() for item in missing_hourly_dates)
        raise WeatherProviderError(f"Open-Meteo response had no hourly data for: {joined_dates}.")

    try:
        return WeekendWeather(
            location=location,
            provider_timezone=provider_timezone,
            utc_offset_seconds=raw_utc_offset,
            generated_at=datetime.now(UTC),
            days=[daily_by_date[item] for item in requested_dates],
        )
    except ValidationError as exc:
        raise WeatherProviderError("Open-Meteo forecast failed schema validation.") from exc


def format_weekend_weather(weather: WeekendWeather | None) -> str:
    """Format compact weather context for the Telegram digest."""
    if weather is None:
        return "Weekend weather\nWeather unavailable."

    lines = [f"Weekend weather — {weather.location.name}"]
    for day in weather.days:
        lines.extend(
            [
                "",
                day.date.strftime("%A"),
                day.condition.value.capitalize(),
                (
                    f"High {_format_temperature(day.temperature_high_f)}"
                    f" · Low {_format_temperature(day.temperature_low_f)}"
                ),
            ]
        )

        precipitation_parts: list[str] = []
        if day.precipitation_probability_max is not None:
            precipitation_parts.append(f"Rain {day.precipitation_probability_max:.0f}%")
        if day.precipitation_inches is not None:
            precipitation_parts.append(f"{day.precipitation_inches:.2f} in")
        if precipitation_parts:
            lines.append(" · ".join(precipitation_parts))

        wind_parts: list[str] = []
        if day.max_wind_speed_mph is not None:
            wind_parts.append(f"Wind up to {day.max_wind_speed_mph:.0f} mph")
        if day.max_wind_gust_mph is not None:
            wind_parts.append(f"Gusts {day.max_wind_gust_mph:.0f} mph")
        if wind_parts:
            lines.append(" · ".join(wind_parts))

        lines.append(f"Sunrise {_format_clock(day.sunrise)} · Sunset {_format_clock(day.sunset)}")

    return "\n".join(lines)


def format_weather_diagnostics(
    weather: WeekendWeather,
    *,
    sample_hours: Iterable[int] = (),
) -> str:
    """Format local diagnostics with optional exact-hour samples."""
    requested_sample_hours = tuple(sample_hours)
    if any(hour < 0 or hour > 23 for hour in requested_sample_hours):
        raise ValueError("Weather diagnostic sample hours must be between 0 and 23.")

    lines = [
        f"Weather location: {weather.location.name}",
        (f"Coordinates: {weather.location.latitude:.5f}, {weather.location.longitude:.5f}"),
        f"Provider timezone: {weather.provider_timezone}",
        f"Forecast days: {len(weather.days)}",
    ]

    for day in weather.days:
        lines.extend(
            [
                "",
                f"{day.date.strftime('%A')} ({day.date.isoformat()}):",
                f"Condition: {day.condition.value}",
                f"High: {_format_temperature(day.temperature_high_f)}",
                f"Low: {_format_temperature(day.temperature_low_f)}",
                (
                    "Precipitation probability: "
                    + _format_optional(day.precipitation_probability_max, "%", 0)
                ),
                ("Precipitation: " + _format_optional(day.precipitation_inches, " in", 2)),
                ("Max wind: " + _format_optional(day.max_wind_speed_mph, " mph", 1)),
                ("Max gust: " + _format_optional(day.max_wind_gust_mph, " mph", 1)),
                f"Sunrise: {_format_clock(day.sunrise)}",
                f"Sunset: {_format_clock(day.sunset)}",
                ("Daylight: " + _format_daylight(day.daylight_duration_seconds)),
                f"Hourly points: {len(day.hourly)}",
            ]
        )

        for sample_hour in requested_sample_hours:
            sample = next(
                (hour for hour in day.hourly if hour.time.hour == sample_hour),
                None,
            )
            if sample is None:
                lines.append(f"{_format_hour_label(sample_hour)}: unavailable")
                continue
            lines.append(
                f"{_format_hour_label(sample_hour)}: "
                f"{_format_temperature(sample.temperature_f)}, "
                f"feels {_format_optional(sample.apparent_temperature_f, '°F', 0)}, "
                f"rain {_format_optional(sample.precipitation_probability, '%', 0)}, "
                f"{sample.condition.value}, "
                f"wind {sample.wind_speed_mph:.1f} mph, "
                f"gusts {_format_optional(sample.wind_gust_mph, ' mph', 1)}"
            )

    return "\n".join(lines)


def _parse_hourly(
    arrays: dict[str, list[object]],
    index: int,
    timezone: ZoneInfo,
) -> HourlyWeather:
    timestamp = _parse_local_datetime(
        arrays["time"][index],
        timezone,
        f"hourly.time[{index}]",
    )
    weather_code = _required_int(
        arrays["weather_code"][index],
        f"hourly.weather_code[{index}]",
    )
    try:
        return HourlyWeather(
            time=timestamp,
            temperature_f=_required_float(
                arrays["temperature_2m"][index],
                f"hourly.temperature_2m[{index}]",
            ),
            apparent_temperature_f=_optional_float(
                arrays["apparent_temperature"][index],
                f"hourly.apparent_temperature[{index}]",
            ),
            precipitation_probability=_optional_float(
                arrays["precipitation_probability"][index],
                f"hourly.precipitation_probability[{index}]",
            ),
            precipitation_inches=_optional_float(
                arrays["precipitation"][index],
                f"hourly.precipitation[{index}]",
            ),
            weather_code=weather_code,
            condition=weather_condition_from_code(weather_code),
            wind_speed_mph=_required_float(
                arrays["wind_speed_10m"][index],
                f"hourly.wind_speed_10m[{index}]",
            ),
            wind_gust_mph=_optional_float(
                arrays["wind_gusts_10m"][index],
                f"hourly.wind_gusts_10m[{index}]",
            ),
        )
    except ValidationError as exc:
        raise WeatherProviderError(
            f"Open-Meteo hourly forecast at index {index} failed validation."
        ) from exc


def _parse_daily(
    arrays: dict[str, list[object]],
    index: int,
    forecast_date: date,
    timezone: ZoneInfo,
    hourly: list[HourlyWeather],
) -> DailyWeather:
    sunrise = _parse_local_datetime(
        arrays["sunrise"][index],
        timezone,
        f"daily.sunrise[{index}]",
    )
    sunset = _parse_local_datetime(
        arrays["sunset"][index],
        timezone,
        f"daily.sunset[{index}]",
    )
    if sunrise.date() != forecast_date or sunset.date() != forecast_date:
        raise WeatherProviderError(f"Open-Meteo sunrise or sunset did not match {forecast_date}.")

    weather_code = _required_int(
        arrays["weather_code"][index],
        f"daily.weather_code[{index}]",
    )
    try:
        return DailyWeather(
            date=forecast_date,
            temperature_high_f=_required_float(
                arrays["temperature_2m_max"][index],
                f"daily.temperature_2m_max[{index}]",
            ),
            temperature_low_f=_required_float(
                arrays["temperature_2m_min"][index],
                f"daily.temperature_2m_min[{index}]",
            ),
            apparent_temperature_high_f=_optional_float(
                arrays["apparent_temperature_max"][index],
                f"daily.apparent_temperature_max[{index}]",
            ),
            apparent_temperature_low_f=_optional_float(
                arrays["apparent_temperature_min"][index],
                f"daily.apparent_temperature_min[{index}]",
            ),
            precipitation_probability_max=_optional_float(
                arrays["precipitation_probability_max"][index],
                f"daily.precipitation_probability_max[{index}]",
            ),
            precipitation_inches=_optional_float(
                arrays["precipitation_sum"][index],
                f"daily.precipitation_sum[{index}]",
            ),
            weather_code=weather_code,
            condition=weather_condition_from_code(weather_code),
            max_wind_speed_mph=_optional_float(
                arrays["wind_speed_10m_max"][index],
                f"daily.wind_speed_10m_max[{index}]",
            ),
            max_wind_gust_mph=_optional_float(
                arrays["wind_gusts_10m_max"][index],
                f"daily.wind_gusts_10m_max[{index}]",
            ),
            sunrise=sunrise,
            sunset=sunset,
            daylight_duration_seconds=_optional_float(
                arrays["daylight_duration"][index],
                f"daily.daylight_duration[{index}]",
            ),
            hourly=hourly,
        )
    except ValidationError as exc:
        raise WeatherProviderError(
            f"Open-Meteo daily forecast for {forecast_date} failed validation."
        ) from exc


def _required_mapping(
    payload: dict[str, object],
    field: str,
) -> dict[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise WeatherProviderError(f"Open-Meteo response was missing the {field} block.")
    return cast(dict[str, object], value)


def _validated_arrays(
    block: dict[str, object],
    fields: tuple[str, ...],
    block_name: str,
) -> dict[str, list[object]]:
    arrays: dict[str, list[object]] = {}
    for field in fields:
        value = block.get(field)
        if not isinstance(value, list):
            raise WeatherProviderError(f"Open-Meteo {block_name} block was missing {field}.")
        arrays[field] = cast(list[object], value)

    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1:
        raise WeatherProviderError(f"Open-Meteo {block_name} arrays had mismatched lengths.")
    return arrays


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise WeatherProviderError(f"Open-Meteo {field} was not a date string.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise WeatherProviderError(f"Open-Meteo {field} was invalid.") from exc


def _parse_local_datetime(
    value: object,
    timezone: ZoneInfo,
    field: str,
) -> datetime:
    if not isinstance(value, str):
        raise WeatherProviderError(f"Open-Meteo {field} was not a timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise WeatherProviderError(f"Open-Meteo {field} was invalid.") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)

    localized = parsed.astimezone(timezone)
    if localized.replace(tzinfo=None) != parsed.replace(tzinfo=None):
        raise WeatherProviderError(f"Open-Meteo {field} had an unexpected timezone.")
    return localized


def _required_float(value: object, field: str) -> float:
    result = _optional_float(value, field)
    if result is None:
        raise WeatherProviderError(f"Open-Meteo {field} was missing.")
    return result


def _optional_float(value: object, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise WeatherProviderError(f"Open-Meteo {field} was not numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise WeatherProviderError(f"Open-Meteo {field} was not finite.")
    return result


def _required_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise WeatherProviderError(f"Open-Meteo {field} was not an integer.")
    return value


def _inclusive_dates(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("Weather forecast end date must not precede start date.")
    day_count = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(day_count + 1)]


def _format_temperature(value: float) -> str:
    return f"{value:.0f}°F"


def _format_clock(value: datetime) -> str:
    return value.strftime("%-I:%M %p")


def _format_optional(
    value: float | None,
    suffix: str,
    precision: int,
) -> str:
    if value is None:
        return "unavailable"
    return f"{value:.{precision}f}{suffix}"


def _format_daylight(value: float | None) -> str:
    if value is None:
        return "unavailable"
    hours, remainder = divmod(round(value), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m"


def _format_hour_label(hour: int) -> str:
    return datetime(2000, 1, 1, hour).strftime("%-I %p")
