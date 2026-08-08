from datetime import date, datetime
from typing import cast
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import ValidationError

from event_radar.main import fetch_baseline_weather
from event_radar.models.weather import (
    WeatherCondition,
    WeatherLocation,
    weather_condition_from_code,
)
from event_radar.services.weather import (
    DAILY_VARIABLES,
    HOURLY_VARIABLES,
    OpenMeteoWeatherClient,
    WeatherProviderError,
    filter_weather_to_window,
    forecast_dates_for_window,
    format_weather_diagnostics,
    format_weekend_weather,
    parse_open_meteo_forecast,
)

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
LOCATION = WeatherLocation(
    name="Santa Rosa, CA",
    latitude=38.44047,
    longitude=-122.71443,
    timezone="America/Los_Angeles",
)
START_DATE = date(2026, 8, 8)
END_DATE = date(2026, 8, 9)


def _forecast_payload(
    *,
    start_date: date = START_DATE,
    day_count: int = 2,
) -> dict[str, object]:
    dates = [date.fromordinal(start_date.toordinal() + offset) for offset in range(day_count)]
    hourly_times = [
        f"{forecast_date.isoformat()}T{hour:02d}:00"
        for forecast_date in dates
        for hour in range(24)
    ]
    hourly_count = len(hourly_times)

    return {
        "latitude": 38.4375,
        "longitude": -122.7125,
        "generationtime_ms": 0.2,
        "utc_offset_seconds": -25200,
        "timezone": "America/Los_Angeles",
        "timezone_abbreviation": "GMT-7",
        "hourly": {
            "time": hourly_times,
            "temperature_2m": [52.0 + index / 2 for index in range(hourly_count)],
            "apparent_temperature": [51.0 + index / 2 for index in range(hourly_count)],
            "precipitation_probability": [
                5.0 if index < 24 else 35.0 for index in range(hourly_count)
            ],
            "precipitation": [0.0 if index < 24 else 0.01 for index in range(hourly_count)],
            "weather_code": [0 if index < 24 else 61 for index in range(hourly_count)],
            "wind_speed_10m": [6.5 for _ in range(hourly_count)],
            "wind_gusts_10m": [12.0 for _ in range(hourly_count)],
        },
        "daily": {
            "time": [item.isoformat() for item in dates],
            "weather_code": [0 if index == 0 else 61 for index in range(day_count)],
            "temperature_2m_max": [75.4 + index for index in range(day_count)],
            "temperature_2m_min": [51.6 + index for index in range(day_count)],
            "apparent_temperature_max": [74.0 + index for index in range(day_count)],
            "apparent_temperature_min": [50.5 + index for index in range(day_count)],
            "precipitation_probability_max": [
                5.0 if index == 0 else 35.0 for index in range(day_count)
            ],
            "precipitation_sum": [0.0 if index == 0 else 0.08 for index in range(day_count)],
            "sunrise": [
                f"{item.isoformat()}T06:{20 + index:02d}" for index, item in enumerate(dates)
            ],
            "sunset": [
                f"{item.isoformat()}T20:{10 - index:02d}" for index, item in enumerate(dates)
            ],
            "daylight_duration": [49800.0 - index * 120 for index in range(day_count)],
            "wind_speed_10m_max": [11.2 + index for index in range(day_count)],
            "wind_gusts_10m_max": [18.4 + index for index in range(day_count)],
        },
    }


@pytest.mark.asyncio
async def test_client_requests_units_and_parses_multi_day_forecast() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_forecast_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        weather = await OpenMeteoWeatherClient(
            user_agent="EventRadar/Test",
            client=client,
        ).get_forecast(LOCATION, START_DATE, END_DATE)

    assert len(requests) == 1
    params = requests[0].url.params
    assert params["latitude"] == "38.44047"
    assert params["longitude"] == "-122.71443"
    assert params["timezone"] == "America/Los_Angeles"
    assert params["start_date"] == "2026-08-08"
    assert params["end_date"] == "2026-08-09"
    assert params["temperature_unit"] == "fahrenheit"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert set(params["hourly"].split(",")) == set(HOURLY_VARIABLES)
    assert set(params["daily"].split(",")) == set(DAILY_VARIABLES)
    assert "models" not in params

    assert weather.location == LOCATION
    assert weather.provider_timezone == "America/Los_Angeles"
    assert weather.generated_at.utcoffset() is not None
    assert [day.date for day in weather.days] == [START_DATE, END_DATE]

    saturday, sunday = weather.days
    assert saturday.temperature_high_f == 75.4
    assert saturday.temperature_low_f == 51.6
    assert saturday.apparent_temperature_high_f == 74.0
    assert saturday.apparent_temperature_low_f == 50.5
    assert saturday.precipitation_probability_max == 5.0
    assert sunday.precipitation_inches == 0.08
    assert saturday.max_wind_speed_mph == 11.2
    assert saturday.max_wind_gust_mph == 18.4
    assert saturday.sunrise == datetime(2026, 8, 8, 6, 20, tzinfo=PACIFIC_TIME)
    assert saturday.sunset == datetime(2026, 8, 8, 20, 10, tzinfo=PACIFIC_TIME)
    assert saturday.sunrise.utcoffset() is not None
    assert saturday.sunset.utcoffset() is not None
    assert len(saturday.hourly) == 24
    assert len(sunday.hourly) == 24
    assert all(hour.time.date() == START_DATE for hour in saturday.hourly)
    assert all(hour.time.date() == END_DATE for hour in sunday.hourly)
    assert saturday.hourly[8].time == datetime(2026, 8, 8, 8, tzinfo=PACIFIC_TIME)
    assert saturday.hourly[8].precipitation_probability == 5.0
    assert saturday.hourly[8].wind_speed_mph == 6.5
    assert saturday.hourly[8].wind_gust_mph == 12.0
    assert saturday.condition is WeatherCondition.CLEAR
    assert sunday.condition is WeatherCondition.RAIN


@pytest.mark.parametrize(
    ("code", "condition"),
    [
        (0, WeatherCondition.CLEAR),
        (1, WeatherCondition.MAINLY_CLEAR),
        (2, WeatherCondition.PARTLY_CLOUDY),
        (3, WeatherCondition.OVERCAST),
        (45, WeatherCondition.FOG),
        (53, WeatherCondition.DRIZZLE),
        (56, WeatherCondition.FREEZING_DRIZZLE),
        (63, WeatherCondition.RAIN),
        (66, WeatherCondition.FREEZING_RAIN),
        (73, WeatherCondition.SNOW),
        (81, WeatherCondition.RAIN_SHOWERS),
        (85, WeatherCondition.SNOW_SHOWERS),
        (95, WeatherCondition.THUNDERSTORM),
        (99, WeatherCondition.THUNDERSTORM_WITH_HAIL),
        (999, WeatherCondition.UNKNOWN),
    ],
)
def test_wmo_condition_mapping(
    code: int,
    condition: WeatherCondition,
) -> None:
    assert weather_condition_from_code(code) is condition


def test_parser_filters_daily_and_hourly_values_to_requested_dates() -> None:
    payload = _forecast_payload(day_count=3)

    weather = parse_open_meteo_forecast(
        payload,
        location=LOCATION,
        start_date=START_DATE,
        end_date=END_DATE,
    )

    assert [day.date for day in weather.days] == [START_DATE, END_DATE]
    assert [len(day.hourly) for day in weather.days] == [24, 24]


def test_forecast_dates_follow_the_existing_exclusive_weekend_window() -> None:
    start = datetime(2026, 8, 7, 18, 30, tzinfo=PACIFIC_TIME)
    end = datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)

    assert forecast_dates_for_window(start, end, LOCATION) == (
        date(2026, 8, 7),
        date(2026, 8, 9),
    )


def test_window_filter_keeps_daily_summary_and_only_overlapping_hours() -> None:
    weather = parse_open_meteo_forecast(
        _forecast_payload(),
        location=LOCATION,
        start_date=START_DATE,
        end_date=END_DATE,
    )

    filtered = filter_weather_to_window(
        weather,
        datetime(2026, 8, 8, 14, 30, tzinfo=PACIFIC_TIME),
        datetime(2026, 8, 10, tzinfo=PACIFIC_TIME),
    )

    assert len(filtered.days) == 2
    assert filtered.days[0].temperature_high_f == 75.4
    assert filtered.days[0].hourly[0].time.hour == 14
    assert len(filtered.days[0].hourly) == 10
    assert len(filtered.days[1].hourly) == 24


def test_mismatched_hourly_array_lengths_fail_cleanly() -> None:
    payload = _forecast_payload()
    hourly = cast(dict[str, object], payload["hourly"])
    gusts = cast(list[object], hourly["wind_gusts_10m"])
    gusts.pop()

    with pytest.raises(WeatherProviderError, match="hourly arrays had mismatched"):
        parse_open_meteo_forecast(
            payload,
            location=LOCATION,
            start_date=START_DATE,
            end_date=END_DATE,
        )


def test_mismatched_daily_array_lengths_fail_cleanly() -> None:
    payload = _forecast_payload()
    daily = cast(dict[str, object], payload["daily"])
    highs = cast(list[object], daily["temperature_2m_max"])
    highs.pop()

    with pytest.raises(WeatherProviderError, match="daily arrays had mismatched"):
        parse_open_meteo_forecast(
            payload,
            location=LOCATION,
            start_date=START_DATE,
            end_date=END_DATE,
        )


@pytest.mark.asyncio
async def test_http_errors_raise_weather_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "temporarily unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WeatherProviderError, match="HTTP 503"):
            await OpenMeteoWeatherClient(
                user_agent="EventRadar/Test",
                client=client,
            ).get_forecast(LOCATION, START_DATE, END_DATE)


@pytest.mark.asyncio
async def test_explicit_open_meteo_error_fails_cleanly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": True, "reason": "Invalid date range"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WeatherProviderError, match="Invalid date range"):
            await OpenMeteoWeatherClient(
                user_agent="EventRadar/Test",
                client=client,
            ).get_forecast(LOCATION, START_DATE, END_DATE)


@pytest.mark.parametrize(
    ("block", "field", "message"),
    [
        (None, "daily", "missing the daily block"),
        (None, "hourly", "missing the hourly block"),
        ("hourly", "temperature_2m", "hourly block was missing temperature_2m"),
        ("daily", "sunrise", "daily block was missing sunrise"),
    ],
)
def test_missing_required_weather_data_fails_cleanly(
    block: str | None,
    field: str,
    message: str,
) -> None:
    payload = _forecast_payload()
    if block is None:
        payload.pop(field)
    else:
        cast(dict[str, object], payload[block]).pop(field)

    with pytest.raises(WeatherProviderError, match=message):
        parse_open_meteo_forecast(
            payload,
            location=LOCATION,
            start_date=START_DATE,
            end_date=END_DATE,
        )


def test_invalid_timestamp_fails_cleanly() -> None:
    payload = _forecast_payload()
    hourly = cast(dict[str, object], payload["hourly"])
    times = cast(list[object], hourly["time"])
    times[0] = "not-a-timestamp"

    with pytest.raises(WeatherProviderError, match=r"hourly.time\[0\] was invalid"):
        parse_open_meteo_forecast(
            payload,
            location=LOCATION,
            start_date=START_DATE,
            end_date=END_DATE,
        )


def test_provider_timezone_mismatch_fails_cleanly() -> None:
    payload = _forecast_payload()
    payload["timezone"] = "UTC"

    with pytest.raises(WeatherProviderError, match="expected 'America/Los_Angeles'"):
        parse_open_meteo_forecast(
            payload,
            location=LOCATION,
            start_date=START_DATE,
            end_date=END_DATE,
        )


def test_requested_date_absent_from_response_fails_cleanly() -> None:
    payload = _forecast_payload(start_date=date(2026, 8, 9), day_count=1)

    with pytest.raises(WeatherProviderError, match="missing requested date"):
        parse_open_meteo_forecast(
            payload,
            location=LOCATION,
            start_date=START_DATE,
            end_date=END_DATE,
        )


def test_weather_location_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="Unknown timezone"):
        WeatherLocation(
            name="Unknown",
            latitude=0,
            longitude=0,
            timezone="Not/A_Real_Zone",
        )


def test_weather_formatters_are_compact_and_support_hourly_samples() -> None:
    weather = parse_open_meteo_forecast(
        _forecast_payload(),
        location=LOCATION,
        start_date=START_DATE,
        end_date=END_DATE,
    )

    digest = format_weekend_weather(weather)
    diagnostics = format_weather_diagnostics(weather, sample_hours=(8, 12, 16, 20))

    assert "Weekend weather — Santa Rosa, CA" in digest
    assert "High 75°F · Low 52°F" in digest
    assert "Sunrise 6:20 AM · Sunset 8:10 PM" in digest
    assert "Hourly points" not in digest
    assert "Provider timezone: America/Los_Angeles" in diagnostics
    assert "Hourly points: 24" in diagnostics
    assert "8 AM: 56°F, feels 55°F, rain 5%, clear" in diagnostics
    assert format_weekend_weather(None) == "Weekend weather\nWeather unavailable."


@pytest.mark.asyncio
async def test_baseline_weather_failure_returns_none_without_raising(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingClient:
        async def get_forecast(
            self,
            location: WeatherLocation,
            start_date: date,
            end_date: date,
        ) -> None:
            raise WeatherProviderError("forecast service timed out")

    client = cast(OpenMeteoWeatherClient, FailingClient())
    weather = await fetch_baseline_weather(
        client,
        LOCATION,
        datetime(2026, 8, 8, tzinfo=PACIFIC_TIME),
        datetime(2026, 8, 10, tzinfo=PACIFIC_TIME),
    )

    assert weather is None
    assert "Weather unavailable: forecast service timed out" in capsys.readouterr().out
