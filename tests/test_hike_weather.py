import asyncio
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from event_radar.hike_config import DEFAULT_HIKE_SUITABILITY_CONFIG
from event_radar.models.weather import (
    DailyWeather,
    HourlyWeather,
    WeatherCondition,
    WeatherLocation,
    WeekendWeather,
)
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.hike_weather import collect_trailhead_weather
from event_radar.services.weather import WeatherProviderError

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
START = datetime(2026, 8, 8, tzinfo=PACIFIC_TIME)
END = datetime(2026, 8, 9, tzinfo=PACIFIC_TIME)


def _weather(location: WeatherLocation) -> WeekendWeather:
    hour = HourlyWeather(
        time=datetime(2026, 8, 8, 8, tzinfo=PACIFIC_TIME),
        temperature_f=65,
        apparent_temperature_f=65,
        precipitation_probability=0,
        precipitation_inches=0,
        weather_code=0,
        condition=WeatherCondition.CLEAR,
        wind_speed_mph=5,
        wind_gust_mph=8,
    )
    day = DailyWeather(
        date=date(2026, 8, 8),
        temperature_high_f=75,
        temperature_low_f=50,
        weather_code=0,
        condition=WeatherCondition.CLEAR,
        sunrise=datetime(2026, 8, 8, 6, tzinfo=PACIFIC_TIME),
        sunset=datetime(2026, 8, 8, 20, tzinfo=PACIFIC_TIME),
        hourly=[hour],
    )
    return WeekendWeather(
        location=location,
        provider_timezone="America/Los_Angeles",
        utc_offset_seconds=-25200,
        generated_at=datetime.now(UTC),
        days=[day],
    )


@pytest.mark.asyncio
async def test_trailhead_weather_deduplicates_coordinates_and_bounds_concurrency() -> None:
    catalog = HikeCatalogRepository().load()
    hikes = [
        next(hike for hike in catalog.hikes if hike.id == "taylor-mountain-summit"),
        next(hike for hike in catalog.hikes if hike.id == "taylor-colgan-creek-loop"),
        next(hike for hike in catalog.hikes if hike.id == "spring-lake-loop"),
    ]

    class RecordingClient:
        def __init__(self) -> None:
            self.calls: list[tuple[float, float]] = []
            self.active = 0
            self.maximum_active = 0

        async def get_forecast(
            self,
            location: WeatherLocation,
            start_date: date,
            end_date: date,
        ) -> WeekendWeather:
            self.calls.append((location.latitude, location.longitude))
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            await asyncio.sleep(0)
            self.active -= 1
            return _weather(location)

    client = RecordingClient()
    config = DEFAULT_HIKE_SUITABILITY_CONFIG
    collection = await collect_trailhead_weather(
        hikes,
        client,
        START,
        END,
        timezone="America/Los_Angeles",
        config=config,
    )

    assert collection.unique_locations_requested == 2
    assert len(client.calls) == 2
    assert len(collection.forecasts) == 2
    assert collection.errors == {}
    assert client.maximum_active <= config.maximum_weather_concurrency


@pytest.mark.asyncio
async def test_trailhead_weather_preserves_partial_provider_failures() -> None:
    catalog = HikeCatalogRepository().load()
    hikes = catalog.hikes[:2]
    failing_latitude = hikes[0].latitude

    class PartialClient:
        async def get_forecast(
            self,
            location: WeatherLocation,
            start_date: date,
            end_date: date,
        ) -> WeekendWeather:
            if location.latitude == failing_latitude:
                raise WeatherProviderError("temporary provider failure")
            return _weather(location)

    collection = await collect_trailhead_weather(
        hikes,
        PartialClient(),
        START,
        END,
        timezone="America/Los_Angeles",
    )

    assert collection.unique_locations_requested == 2
    assert len(collection.errors) == 1
    assert len(collection.forecasts) == 1
    assert next(iter(collection.errors.values())) == "temporary provider failure"
