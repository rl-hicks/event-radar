from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from event_radar.hike_config import DEFAULT_HIKE_SUITABILITY_CONFIG
from event_radar.models.hike import (
    DurationRange,
    ScenicValue,
    ThreeLevel,
    TimeOfDay,
)
from event_radar.models.hike_recommendation import AccessStatus
from event_radar.models.weather import (
    DailyWeather,
    HourlyWeather,
    WeatherCondition,
)
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.hike_suitability import (
    evaluate_hike_day,
    format_hike_candidates,
    select_hike_candidates,
)

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
SATURDAY = date(2026, 8, 8)
SUNDAY = date(2026, 8, 9)
WINDOW_START = datetime(2026, 8, 8, tzinfo=PACIFIC_TIME)
WINDOW_END = datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)
BASE_HIKE = HikeCatalogRepository().load().hikes[0]


def _hike(**updates: object):
    defaults: dict[str, object] = {
        "id": "test-hike",
        "name": "Test Hike",
        "estimated_duration_minutes": DurationRange(min=60, max=120),
        "minimum_reasonable_daylight_minutes": 120,
        "preferred_months": [8],
        "acceptable_months": [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12],
        "poor_months": [],
        "best_time_of_day": [TimeOfDay.FLEXIBLE],
        "scenic_value": ScenicValue.MODERATE,
    }
    defaults.update(updates)
    return BASE_HIKE.model_copy(update=defaults)


def _daily(
    forecast_date: date = SATURDAY,
    *,
    temperatures: dict[int, float] | None = None,
    wind_speed: float = 5,
    wind_gust: float = 10,
    condition: WeatherCondition = WeatherCondition.CLEAR,
    precipitation_probability: float = 0,
    precipitation_inches: float = 0,
    sunrise_hour: int = 6,
    sunset_hour: int = 20,
) -> DailyWeather:
    temperatures = temperatures or {hour: 72 for hour in range(6, 21)}
    hourly = [
        HourlyWeather(
            time=datetime.combine(
                forecast_date,
                datetime.min.time(),
                tzinfo=PACIFIC_TIME,
            )
            + timedelta(hours=hour),
            temperature_f=temperature,
            apparent_temperature_f=temperature,
            precipitation_probability=precipitation_probability,
            precipitation_inches=precipitation_inches,
            weather_code=0,
            condition=condition,
            wind_speed_mph=wind_speed,
            wind_gust_mph=wind_gust,
        )
        for hour, temperature in sorted(temperatures.items())
    ]
    return DailyWeather(
        date=forecast_date,
        temperature_high_f=max(temperatures.values()),
        temperature_low_f=min(temperatures.values()),
        apparent_temperature_high_f=max(temperatures.values()),
        apparent_temperature_low_f=min(temperatures.values()),
        precipitation_probability_max=precipitation_probability,
        precipitation_inches=precipitation_inches * len(hourly),
        weather_code=0,
        condition=condition,
        max_wind_speed_mph=wind_speed,
        max_wind_gust_mph=wind_gust,
        sunrise=datetime(
            forecast_date.year,
            forecast_date.month,
            forecast_date.day,
            sunrise_hour,
            tzinfo=PACIFIC_TIME,
        ),
        sunset=datetime(
            forecast_date.year,
            forecast_date.month,
            forecast_date.day,
            sunset_hour,
            tzinfo=PACIFIC_TIME,
        ),
        daylight_duration_seconds=(sunset_hour - sunrise_hour) * 3600,
        hourly=hourly,
    )


def _window(evaluation, hour: int):
    return next(
        window for window in evaluation.window_evaluations if window.start_time.hour == hour
    )


def test_shaded_low_heat_sensitivity_hike_remains_viable_when_warm() -> None:
    hike = _hike(
        shade=ThreeLevel.HIGH,
        exposure=ThreeLevel.LOW,
        heat_sensitivity=ThreeLevel.LOW,
    )

    evaluation = evaluate_hike_day(
        hike,
        _daily(temperatures={hour: 88 for hour in range(6, 21)}),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.eligible is True
    assert "favorable window temperature" in evaluation.reasons


def test_exposed_heat_sensitive_hike_penalizes_afternoon_but_keeps_early_start() -> None:
    hike = _hike(
        shade=ThreeLevel.LOW,
        exposure=ThreeLevel.HIGH,
        heat_sensitivity=ThreeLevel.HIGH,
        best_time_of_day=[TimeOfDay.AFTERNOON],
    )
    temperatures = {hour: (68 if hour < 11 else 82 if hour < 14 else 91) for hour in range(6, 21)}

    evaluation = evaluate_hike_day(
        hike,
        _daily(temperatures=temperatures),
        WINDOW_START,
        WINDOW_END,
    )

    early = _window(evaluation, 7)
    afternoon = _window(evaluation, 14)
    assert early.eligible is True
    assert "favorable window temperature" in early.reasons
    assert afternoon.eligible is False
    assert "poor heat fit for this start window" in afternoon.exclusion_reasons
    assert evaluation.best_window is not None
    assert evaluation.best_window.start_time.hour < 11


def test_wind_sensitive_exposed_hike_scores_below_sheltered_hike() -> None:
    exposed = _hike(
        id="coastal",
        name="Coastal",
        exposure=ThreeLevel.HIGH,
        wind_sensitivity=ThreeLevel.HIGH,
    )
    sheltered = _hike(
        id="forest",
        name="Forest",
        exposure=ThreeLevel.LOW,
        wind_sensitivity=ThreeLevel.LOW,
    )
    weather = _daily(wind_speed=17, wind_gust=28)

    exposed_evaluation = evaluate_hike_day(exposed, weather, WINDOW_START, WINDOW_END)
    sheltered_evaluation = evaluate_hike_day(sheltered, weather, WINDOW_START, WINDOW_END)

    assert exposed_evaluation.score < sheltered_evaluation.score
    assert "strong wind penalty" in exposed_evaluation.reasons
    assert "light wind" in sheltered_evaluation.reasons


def test_active_rain_strongly_penalizes_rain_sensitive_hike() -> None:
    hike = _hike(rain_sensitivity=ThreeLevel.HIGH)

    evaluation = evaluate_hike_day(
        hike,
        _daily(
            condition=WeatherCondition.RAIN,
            precipitation_probability=85,
            precipitation_inches=0.12,
        ),
        WINDOW_START,
        WINDOW_END,
    )

    assert evaluation.eligible is True
    assert "active forecast rain penalty" in evaluation.reasons
    assert "heavy precipitation penalty" in evaluation.reasons
    assert evaluation.score < DEFAULT_HIKE_SUITABILITY_CONFIG.minimum_candidate_score


def test_dry_forecast_preserves_unknown_recent_mud_caution() -> None:
    hike = _hike(mud_sensitivity=ThreeLevel.HIGH)

    evaluation = evaluate_hike_day(hike, _daily(), WINDOW_START, WINDOW_END)

    assert evaluation.eligible is True
    assert "dry forecast window" in evaluation.reasons
    assert "Recent-rain and mud conditions are unknown." in evaluation.cautions
    assert all("currently dry" not in caution for caution in evaluation.cautions)


def test_poor_month_is_penalty_not_exclusion_and_preferred_month_is_boost() -> None:
    preferred = _hike(id="preferred")
    poor = _hike(
        id="poor",
        preferred_months=[],
        acceptable_months=[1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12],
        poor_months=[8],
    )

    preferred_evaluation = evaluate_hike_day(preferred, _daily(), WINDOW_START, WINDOW_END)
    poor_evaluation = evaluate_hike_day(poor, _daily(), WINDOW_START, WINDOW_END)

    assert poor_evaluation.eligible is True
    assert "poor-season prior" in poor_evaluation.reasons
    assert "preferred season" in preferred_evaluation.reasons
    assert preferred_evaluation.score - poor_evaluation.score == 10


def test_insufficient_daylight_hard_excludes_hike_day() -> None:
    hike = _hike(
        estimated_duration_minutes=DurationRange(min=180, max=240),
        minimum_reasonable_daylight_minutes=300,
    )
    late_start = datetime(2026, 8, 8, 17, tzinfo=PACIFIC_TIME)

    evaluation = evaluate_hike_day(hike, _daily(), late_start, WINDOW_END)

    assert evaluation.eligible is False
    assert evaluation.best_window is None
    assert "insufficient remaining daylight" in evaluation.exclusion_reasons[0]


def test_long_hike_is_not_scheduled_too_close_to_sunset() -> None:
    hike = _hike(
        estimated_duration_minutes=DurationRange(min=240, max=300),
        minimum_reasonable_daylight_minutes=300,
    )

    evaluation = evaluate_hike_day(hike, _daily(), WINDOW_START, WINDOW_END)

    assert evaluation.eligible is True
    assert evaluation.window_evaluations
    assert all(
        window.estimated_finish_time <= datetime(2026, 8, 8, 19, 15, tzinfo=PACIFIC_TIME)
        for window in evaluation.window_evaluations
    )
    assert all(window.start_time.hour <= 14 for window in evaluation.window_evaluations)


def test_best_time_of_day_softly_changes_window_ranking() -> None:
    hike = _hike(best_time_of_day=[TimeOfDay.AFTERNOON])

    evaluation = evaluate_hike_day(hike, _daily(), WINDOW_START, WINDOW_END)

    morning = _window(evaluation, 8)
    afternoon = _window(evaluation, 14)
    assert afternoon.score - morning.score == 3
    assert evaluation.best_window is not None
    assert evaluation.best_window.start_time.hour == 14


def test_each_day_selects_its_strongest_window_and_days_can_differ() -> None:
    hike = _hike(
        exposure=ThreeLevel.HIGH,
        heat_sensitivity=ThreeLevel.HIGH,
        best_time_of_day=[TimeOfDay.MORNING],
    )
    saturday = _daily(
        SATURDAY,
        temperatures={hour: (65 if hour < 10 else 82) for hour in range(6, 21)},
    )
    sunday = _daily(
        SUNDAY,
        temperatures={hour: 95 for hour in range(6, 21)},
    )

    saturday_evaluation = evaluate_hike_day(hike, saturday, WINDOW_START, WINDOW_END)
    sunday_evaluation = evaluate_hike_day(hike, sunday, WINDOW_START, WINDOW_END)

    assert saturday_evaluation.eligible is True
    assert saturday_evaluation.best_window is not None
    assert saturday_evaluation.best_window.start_time.hour < 10
    assert sunday_evaluation.eligible is False


def test_candidate_selection_keeps_best_day_per_hike_and_access_unchecked() -> None:
    hike = _hike()
    saturday = evaluate_hike_day(hike, _daily(SATURDAY), WINDOW_START, WINDOW_END)
    sunday = evaluate_hike_day(
        hike,
        _daily(SUNDAY, wind_speed=16, wind_gust=25),
        WINDOW_START,
        WINDOW_END,
    )

    selection = select_hike_candidates([sunday, saturday])

    assert len(selection.candidates) == 1
    candidate = selection.candidates[0]
    assert candidate.best_day == SATURDAY
    assert len(candidate.alternate_day_evaluations) == 1
    assert candidate.access.status is AccessStatus.UNCHECKED
    assert candidate.access.dynamic_status_verified is False
    assert "open" not in format_hike_candidates(selection).casefold()
    assert "access status: not checked" in format_hike_candidates(selection).casefold()


def test_candidate_cap_works_and_sparse_inventory_is_not_padded() -> None:
    evaluations = [
        evaluate_hike_day(
            _hike(id=f"hike-{index}", name=f"Hike {index}", region=f"Region {index}"),
            _daily(),
            WINDOW_START,
            WINDOW_END,
        )
        for index in range(5)
    ]
    capped_config = replace(
        DEFAULT_HIKE_SUITABILITY_CONFIG,
        maximum_candidates=2,
        diversity_soft_cap_per_setting=10,
        diversity_soft_cap_per_region=10,
    )

    capped = select_hike_candidates(evaluations, config=capped_config)
    sparse = select_hike_candidates([evaluations[0]], config=capped_config)

    assert len(capped.candidates) == 2
    assert len(sparse.candidates) == 1


def test_light_diversity_prefers_an_alternate_setting() -> None:
    coastal_one = _hike(
        id="coastal-one",
        name="Coastal One",
        setting=["coastal", "bluff"],
        region="Coast",
    )
    coastal_two = _hike(
        id="coastal-two",
        name="Coastal Two",
        setting=["coastal", "bluff"],
        region="Coast",
    )
    forest = _hike(
        id="forest",
        name="Forest",
        setting=["redwood", "forest"],
        region="Forest",
    )
    evaluations = [
        evaluate_hike_day(hike, _daily(), WINDOW_START, WINDOW_END)
        for hike in (coastal_one, coastal_two, forest)
    ]
    config = replace(
        DEFAULT_HIKE_SUITABILITY_CONFIG,
        maximum_candidates=2,
        diversity_soft_cap_per_setting=1,
        diversity_soft_cap_per_region=2,
    )

    selection = select_hike_candidates(evaluations, config=config)

    assert {candidate.hike.id for candidate in selection.candidates} == {
        "coastal-one",
        "forest",
    }


def test_candidate_order_is_deterministic() -> None:
    alpha = evaluate_hike_day(
        _hike(id="alpha", name="Alpha"),
        _daily(),
        WINDOW_START,
        WINDOW_END,
    )
    beta = evaluate_hike_day(
        _hike(id="beta", name="Beta"),
        _daily(),
        WINDOW_START,
        WINDOW_END,
    )

    first = select_hike_candidates([beta, alpha])
    second = select_hike_candidates([alpha, beta])

    assert [item.hike.id for item in first.candidates] == ["alpha", "beta"]
    assert [item.hike.id for item in second.candidates] == ["alpha", "beta"]


def test_deferred_diversity_refill_is_returned_in_score_order() -> None:
    high = evaluate_hike_day(
        _hike(id="high", name="High", setting=["lake"]),
        _daily(),
        WINDOW_START,
        WINDOW_END,
    )
    deferred = high.model_copy(
        update={
            "hike": _hike(id="deferred", name="Deferred", setting=["lake"]),
            "score": high.score - 1,
        }
    )
    alternate = high.model_copy(
        update={
            "hike": _hike(id="alternate", name="Alternate", setting=["forest"]),
            "score": high.score - 2,
        }
    )
    config = replace(
        DEFAULT_HIKE_SUITABILITY_CONFIG,
        maximum_candidates=3,
        diversity_soft_cap_per_setting=1,
    )

    selection = select_hike_candidates([alternate, deferred, high], config=config)

    assert [candidate.score for candidate in selection.candidates] == sorted(
        [candidate.score for candidate in selection.candidates],
        reverse=True,
    )
