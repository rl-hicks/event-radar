import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from event_radar.hike_config import (
    DEFAULT_HIKE_SUITABILITY_CONFIG,
    HikeSuitabilityConfig,
)
from event_radar.models.hike import Hike
from event_radar.models.weather import WeatherLocation, WeekendWeather
from event_radar.services.weather import (
    WeatherProviderError,
    filter_weather_to_window,
    forecast_dates_for_window,
)

WeatherLocationKey = tuple[float, float, str]


class WeatherForecastClient(Protocol):
    async def get_forecast(
        self,
        location: WeatherLocation,
        start_date: date,
        end_date: date,
    ) -> WeekendWeather: ...


@dataclass(frozen=True)
class HikeWeatherCollection:
    forecasts: dict[WeatherLocationKey, WeekendWeather]
    errors: dict[WeatherLocationKey, str]
    unique_locations_requested: int


async def collect_trailhead_weather(
    hikes: list[Hike],
    client: WeatherForecastClient,
    start: datetime,
    end: datetime,
    *,
    timezone: str,
    config: HikeSuitabilityConfig = DEFAULT_HIKE_SUITABILITY_CONFIG,
) -> HikeWeatherCollection:
    """Fetch trailhead forecasts with coordinate reuse and bounded concurrency."""
    if config.maximum_weather_concurrency < 1:
        raise ValueError("Hike weather concurrency must be positive.")

    hikes_by_location: dict[WeatherLocationKey, Hike] = {}
    for hike in hikes:
        key = weather_location_key(hike, timezone)
        hikes_by_location.setdefault(key, hike)

    semaphore = asyncio.Semaphore(config.maximum_weather_concurrency)

    async def fetch(
        key: WeatherLocationKey,
        hike: Hike,
    ) -> tuple[WeatherLocationKey, WeekendWeather | None, str | None]:
        location = WeatherLocation(
            name=f"{hike.name} — {hike.trailhead_name}",
            latitude=hike.latitude,
            longitude=hike.longitude,
            timezone=timezone,
        )
        forecast_start, forecast_end = forecast_dates_for_window(start, end, location)
        try:
            async with semaphore:
                weather = await client.get_forecast(
                    location,
                    forecast_start,
                    forecast_end,
                )
        except WeatherProviderError as exc:
            return key, None, str(exc)
        return key, filter_weather_to_window(weather, start, end), None

    results = await asyncio.gather(*(fetch(key, hike) for key, hike in hikes_by_location.items()))
    forecasts: dict[WeatherLocationKey, WeekendWeather] = {}
    errors: dict[WeatherLocationKey, str] = {}
    for key, weather, error in results:
        if weather is not None:
            forecasts[key] = weather
        elif error is not None:
            errors[key] = error

    return HikeWeatherCollection(
        forecasts=forecasts,
        errors=errors,
        unique_locations_requested=len(hikes_by_location),
    )


def weather_location_key(hike: Hike, timezone: str) -> WeatherLocationKey:
    return hike.latitude, hike.longitude, timezone
