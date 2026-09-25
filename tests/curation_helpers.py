from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from event_radar.models.curation import RecommendationContext
from event_radar.models.direction import Direction, DirectionType
from event_radar.models.event import Event
from event_radar.models.hike_recommendation import (
    HikeAccessContext,
    HikeCandidate,
    HikeCandidateSelection,
    HikeWindowEvaluation,
    HikeWindowWeather,
)
from event_radar.models.recommendation import CandidateSelection, EventEvaluation
from event_radar.models.user_context import ScheduleAnchor, UserContext
from event_radar.models.weather import (
    DailyWeather,
    HourlyWeather,
    WeatherCondition,
    WeatherLocation,
    WeekendWeather,
)
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.recommendation_context import build_recommendation_context
from event_radar.services.user_context import UserContextRepository

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
START = datetime(2026, 8, 8, tzinfo=PACIFIC_TIME)
END = datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)


def example_user_context() -> UserContext:
    context = UserContextRepository(Path("config/user_context.example.json")).load()
    climbing = ScheduleAnchor(
        id="saturday-climbing",
        day_of_week="saturday",
        start_time="08:00:00",
        end_time="12:00:00",
        strength="soft",
        description="Saturday morning through noon is normally reserved for indoor climbing.",
        displacement_policy="Only unusually strong options should displace climbing.",
    )
    return context.model_copy(update={"schedule_anchors": [climbing]})


def event(
    *,
    title: str = "Community Night Market",
    start_time: datetime | None = None,
    description: str | None = "A circulating public market with food and participatory art.",
    price: Decimal | None = None,
) -> Event:
    start_time = start_time or datetime(2026, 8, 8, 18, tzinfo=PACIFIC_TIME)
    return Event(
        source_name="Example Source",
        source_id="market-series",
        source_url=HttpUrl("https://example.com/events/market"),
        title=title,
        description=description,
        start_time=start_time,
        end_time=start_time + timedelta(hours=3),
        venue="Town Square",
        city="Santa Rosa",
        categories={"market", "community"},
        price_min=price,
        price_max=price,
    )


def event_selection(events: list[Event] | None = None) -> CandidateSelection:
    values = events or [event()]
    evaluations = [
        EventEvaluation(
            event=value,
            eligible=True,
            score=17 - index,
            reasons=["public market [title]", "evening timing"],
            activity_type="market",
        )
        for index, value in enumerate(values)
    ]
    return CandidateSelection(evaluations=evaluations, candidates=evaluations)


def hike_selection() -> HikeCandidateSelection:
    hike = HikeCatalogRepository().load().hikes[0]
    start = datetime(2026, 8, 9, 8, tzinfo=PACIFIC_TIME)
    weather = HikeWindowWeather(
        minimum_temperature_f=55,
        maximum_temperature_f=68,
        maximum_apparent_temperature_f=67,
        maximum_precipitation_probability=5,
        precipitation_inches=0,
        maximum_wind_speed_mph=6,
        maximum_wind_gust_mph=10,
        conditions=[WeatherCondition.CLEAR],
        hourly_points=3,
    )
    window = HikeWindowEvaluation(
        start_time=start,
        estimated_finish_time=start + timedelta(hours=3),
        eligible=True,
        score=36,
        reasons=["favorable window temperature", "light wind"],
        cautions=[],
        weather=weather,
    )
    access = HikeAccessContext(
        parking_notes=hike.parking_notes,
        access_baseline_notes=hike.access_baseline_notes,
        seasonal_access_notes=hike.seasonal_access_notes,
        important_route_notes=hike.important_route_notes,
    )
    candidate = HikeCandidate(
        hike=hike,
        best_day=start.date(),
        best_window=window,
        score=36,
        reasons=window.reasons,
        cautions=[],
        access=access,
    )
    return HikeCandidateSelection(
        day_evaluations=[],
        candidates=[candidate],
        unique_weather_locations_requested=1,
        weather_location_failures=0,
    )


def baseline_weather() -> WeekendWeather:
    sunrise = datetime(2026, 8, 8, 6, 20, tzinfo=PACIFIC_TIME)
    sunset = datetime(2026, 8, 8, 20, 10, tzinfo=PACIFIC_TIME)
    hourly = HourlyWeather(
        time=datetime(2026, 8, 8, 12, tzinfo=PACIFIC_TIME),
        temperature_f=75,
        apparent_temperature_f=74,
        precipitation_probability=5,
        precipitation_inches=0,
        weather_code=0,
        condition=WeatherCondition.CLEAR,
        wind_speed_mph=7,
        wind_gust_mph=12,
    )
    day = DailyWeather(
        date=sunrise.date(),
        temperature_high_f=78,
        temperature_low_f=52,
        apparent_temperature_high_f=77,
        apparent_temperature_low_f=51,
        precipitation_probability_max=5,
        precipitation_inches=0,
        weather_code=0,
        condition=WeatherCondition.CLEAR,
        max_wind_speed_mph=10,
        max_wind_gust_mph=16,
        sunrise=sunrise,
        sunset=sunset,
        daylight_duration_seconds=49800,
        hourly=[hourly],
    )
    return WeekendWeather(
        location=WeatherLocation(
            name="Santa Rosa, CA",
            latitude=38.44047,
            longitude=-122.71443,
            timezone="America/Los_Angeles",
        ),
        provider_timezone="America/Los_Angeles",
        utc_offset_seconds=-25200,
        generated_at=START,
        days=[day],
    )


def recommendation_context(*, events: list[Event] | None = None) -> RecommendationContext:
    directions = [
        Direction(
            type=DirectionType.PERMANENT,
            text="Prefer participatory activities.",
            telegram_user_id=1,
            created_at=START,
            update_id=1,
        )
    ]
    temporary = [
        Direction(
            type=DirectionType.TEMPORARY,
            text="A friend may join Sunday.",
            telegram_user_id=1,
            created_at=START,
            update_id=2,
        )
    ]
    return build_recommendation_context(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        permanent_directions=directions,
        temporary_directions=temporary,
        baseline_weather=baseline_weather(),
        event_selection=event_selection(events),
        hike_selection=hike_selection(),
    )
