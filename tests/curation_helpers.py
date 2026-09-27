from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from event_radar.models.curation import RecommendationContext
from event_radar.models.direction import Direction, DirectionType
from event_radar.models.event import Event
from event_radar.models.event_analysis import (
    EventOrigin,
    SemanticConfidence,
    WeekendEventCard,
)
from event_radar.models.hike_recommendation import (
    HikeAccessContext,
    HikeCandidate,
    HikeCandidateSelection,
    HikeWindowEvaluation,
    HikeWindowWeather,
)
from event_radar.models.user_context import UserContext
from event_radar.models.weather import (
    DailyWeather,
    HourlyWeather,
    WeatherCondition,
    WeatherLocation,
    WeekendWeather,
)
from event_radar.services.event_cards import event_occurrence_fact
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.personal_context import (
    PersonalContextStage,
    PersonalExperienceContext,
)
from event_radar.services.recommendation_context import build_recommendation_context
from event_radar.services.user_context import UserContextRepository

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
START = datetime(2026, 8, 8, tzinfo=PACIFIC_TIME)
END = datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)


def personal_context_markdown(*, include_version: bool = False) -> str:
    headings = {
        1: "PRIMARY WEEKEND OBJECTIVE",
        2: "DEMOGRAPHIC AND SOCIAL FIT",
        3: "SOCIAL ARCHITECTURE",
        4: "HOW SOCIAL VALUE INTERACTS WITH EXPERIENCE VALUE",
        5: "INCLUSION THRESHOLD",
        6: "CORE EXPERIENCE PULL",
        7: "MUSIC",
        8: "FOOD EVENTS",
        9: "FESTIVALS, MARKETS, AND OPEN EVENTS",
        10: "COMEDY",
        11: "LOCAL WEIRDNESS AND TRADITIONS",
        12: "VOLUNTEERING",
        13: "WELLNESS AND FITNESS EVENTS",
        14: "DANCE",
        15: "WEAK-PULL CATEGORIES",
        16: "HISTORY AND CULTURE",
        17: "ANIMALS AND NATURE OBSERVATION",
        18: "ADULT / LIFE-STAGE FIT",
        19: "ATMOSPHERE",
        20: "FRIEND VS. SOLO ASSUMPTIONS",
        21: "EXPERIENCE MULTIPLIERS",
        22: "EXPERIENCE PENALTIES",
        23: "COST AND FRICTION",
        24: "DISCOVERY POSTURE",
        25: "DO NOT CONFUSE THESE PAIRS",
        26: "THE “WOULD I ACTUALLY CARE?” TEST",
        27: "PACKET COMPOSITION",
        28: "FINAL CURATION PRINCIPLE",
    }
    details = {
        1: "Surface experiences with social value and intrinsic value.",
        3: "Distinguish co-presence, circulation, and natural interaction.",
        5: "Worth surfacing is a lower threshold than likely to attend.",
        6: "Active exploration and useful capability have strong pull.",
        15: "Generic crafts and generic workshops have weak pull.",
        24: "Favor broad discovery when there is a credible path to personal value.",
        25: "Do not confuse active with appealing, workshop with desirable participation, "
        "or unusual with interesting.",
        26: "Ask: Would I Actually Care? Generic virtues are not enough.",
        27: "Normally surface roughly 12-18 varied events.",
        28: "Act as a knowledgeable scout and preserve real choices.",
    }
    sections = ["# PERSONAL EXPERIENCE PREFERENCE CONTEXT — EVENT RADAR"]
    if include_version:
        sections.extend(["", "Context-Version: 1"])
    sections.extend(
        [
            "",
            "## Purpose",
            "",
            "Surface worthwhile discoveries; independent hikes are additive to events.",
        ]
    )
    for number, heading in headings.items():
        sections.extend(
            [
                "",
                f"# {number}. {heading}",
                "",
                details.get(number, f"Deterministic fixture guidance for section {number}."),
            ]
        )
    return "\n".join(sections) + "\n"


def example_personal_context() -> PersonalExperienceContext:
    return PersonalExperienceContext.from_markdown(
        personal_context_markdown(),
        source_path=Path("tests/fixtures/personal_experience_preference_context.md"),
    )


def example_user_context() -> UserContext:
    return UserContextRepository(Path("config/user_context.example.json")).load()


def event(
    *,
    title: str = "Community Night Market",
    start_time: datetime | None = None,
    description: str | None = "A circulating public market with food and participatory art.",
    price: Decimal | None = None,
    price_details: str | None = None,
    source_id: str = "market-series",
) -> Event:
    start_time = start_time or datetime(2026, 8, 8, 18, tzinfo=PACIFIC_TIME)
    return Event(
        source_name="Example Source",
        source_id=source_id,
        source_url=HttpUrl(f"https://example.com/events/{source_id}"),
        title=title,
        description=description,
        start_time=start_time,
        end_time=start_time + timedelta(hours=3),
        venue="Town Square",
        city="Santa Rosa",
        categories={"market", "community"},
        price_min=price,
        price_max=price,
        price_currency="USD" if price is not None else None,
        price_details=price_details,
    )


def event_card(source_event: Event | None = None) -> WeekendEventCard:
    source_event = source_event or event()
    occurrence = event_occurrence_fact(source_event)
    return WeekendEventCard(
        candidate_id=occurrence.event_id,
        origin=EventOrigin.SCRAPED,
        title=source_event.title,
        occurrences=[occurrence],
        experience_summary="A public market with circulation and participatory art.",
        experience_modes=["market", "participatory art"],
        interaction_architecture="Circulation and shared activities create conversation hooks.",
        solo_viability="Normal to attend solo.",
        active_value="Light walking and exploration.",
        distinctiveness="A locally grounded community gathering.",
        social_opportunity="Plausible but not guaranteed.",
        friction_summary="Local and comparatively low-friction.",
        schedule_observation="No known recurring-availability conflict.",
        uncertainties=["Attendance is unknown."],
        source_confidence=SemanticConfidence.HIGH,
        semantic_analysis_available=True,
    )


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
    values = events or [event()]
    return build_recommendation_context(
        generated_at=START,
        weekend_start=START,
        weekend_end=END,
        user_context=example_user_context(),
        personal_experience_context=example_personal_context().projection(
            PersonalContextStage.FINAL_CURATION
        ),
        permanent_directions=directions,
        temporary_directions=temporary,
        baseline_weather=baseline_weather(),
        event_cards=[event_card(value) for value in values],
        hike_selection=hike_selection(),
    )
