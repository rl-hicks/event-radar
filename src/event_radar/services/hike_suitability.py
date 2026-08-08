import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from event_radar.hike_config import (
    DEFAULT_HIKE_SUITABILITY_CONFIG,
    HeatThresholds,
    HikeSuitabilityConfig,
    WindThresholds,
)
from event_radar.models.hike import (
    CoordinatePrecision,
    Hike,
    ScenicValue,
    ThreeLevel,
    TimeOfDay,
)
from event_radar.models.hike_recommendation import (
    HikeAccessContext,
    HikeCandidate,
    HikeCandidateSelection,
    HikeDayEvaluation,
    HikeWindowEvaluation,
    HikeWindowWeather,
)
from event_radar.models.weather import DailyWeather, HourlyWeather
from event_radar.services.hike_weather import (
    HikeWeatherCollection,
    weather_location_key,
)


def evaluate_hike_day(
    hike: Hike,
    weather: DailyWeather,
    start: datetime,
    end: datetime,
    config: HikeSuitabilityConfig = DEFAULT_HIKE_SUITABILITY_CONFIG,
) -> HikeDayEvaluation:
    """Evaluate every feasible hourly start for one hike on one local day."""
    _validate_window(start, end)
    access = _access_context(hike)
    duration = timedelta(minutes=hike.estimated_duration_minutes.max)
    daylight_end = min(
        weather.sunset - timedelta(minutes=config.daylight_buffer_minutes),
        end,
    )
    daylight_start = max(weather.sunrise, start)
    remaining_daylight_minutes = max(
        0,
        int((daylight_end - daylight_start).total_seconds() // 60),
    )
    required_daylight_minutes = max(
        hike.minimum_reasonable_daylight_minutes,
        hike.estimated_duration_minutes.max,
    )
    if remaining_daylight_minutes < required_daylight_minutes:
        return HikeDayEvaluation(
            hike=hike,
            date=weather.date,
            eligible=False,
            score=0,
            exclusion_reasons=["insufficient remaining daylight for route requirements and buffer"],
            access=access,
        )

    earliest_start = _ceil_to_hour(daylight_start)
    window_evaluations: list[HikeWindowEvaluation] = []
    for hour in weather.hourly:
        if hour.time < earliest_start or hour.time.date() != weather.date:
            continue
        finish = hour.time + duration
        if finish > daylight_end:
            continue
        hourly_weather = [item for item in weather.hourly if hour.time <= item.time < finish]
        expected_points = math.ceil(duration.total_seconds() / 3600)
        if len(hourly_weather) < expected_points or not _is_contiguous(hourly_weather):
            continue
        window_evaluations.append(_evaluate_window(hike, hour.time, finish, hourly_weather, config))

    viable_windows = [window for window in window_evaluations if window.eligible]
    if not viable_windows:
        exclusion_reasons = ["no suitable hourly start window"]
        if window_evaluations:
            detailed_reasons = {
                reason for window in window_evaluations for reason in window.exclusion_reasons
            }
            exclusion_reasons.extend(sorted(detailed_reasons))
        return HikeDayEvaluation(
            hike=hike,
            date=weather.date,
            eligible=False,
            score=0,
            exclusion_reasons=exclusion_reasons,
            window_evaluations=window_evaluations,
            access=access,
        )

    best_window = min(
        viable_windows,
        key=lambda window: (-window.score, window.start_time),
    )
    return HikeDayEvaluation(
        hike=hike,
        date=weather.date,
        eligible=True,
        score=best_window.score,
        reasons=best_window.reasons,
        cautions=best_window.cautions,
        best_window=best_window,
        window_evaluations=window_evaluations,
        access=access,
    )


def build_hike_candidate_selection(
    hikes: list[Hike],
    weather_collection: HikeWeatherCollection,
    start: datetime,
    end: datetime,
    *,
    timezone: str,
    config: HikeSuitabilityConfig = DEFAULT_HIKE_SUITABILITY_CONFIG,
) -> HikeCandidateSelection:
    """Evaluate every hike/day, then retain each hike's best viable option."""
    _validate_window(start, end)
    expected_dates = _dates_in_window(start, end, ZoneInfo(timezone))
    evaluations: list[HikeDayEvaluation] = []

    for hike in hikes:
        forecast = weather_collection.forecasts.get(weather_location_key(hike, timezone))
        if forecast is None:
            evaluations.extend(
                _weather_unavailable_evaluation(hike, item) for item in expected_dates
            )
            continue

        weather_by_date = {day.date: day for day in forecast.days}
        for item in expected_dates:
            day_weather = weather_by_date.get(item)
            if day_weather is None:
                evaluations.append(_weather_unavailable_evaluation(hike, item))
            else:
                evaluations.append(evaluate_hike_day(hike, day_weather, start, end, config))

    return select_hike_candidates(
        evaluations,
        unique_weather_locations_requested=weather_collection.unique_locations_requested,
        weather_location_failures=len(weather_collection.errors),
        config=config,
    )


def select_hike_candidates(
    day_evaluations: list[HikeDayEvaluation],
    *,
    unique_weather_locations_requested: int = 0,
    weather_location_failures: int = 0,
    config: HikeSuitabilityConfig = DEFAULT_HIKE_SUITABILITY_CONFIG,
) -> HikeCandidateSelection:
    """Select a bounded, lightly diverse set using each hike's best day."""
    if config.maximum_candidates < 1:
        raise ValueError("Maximum hike candidate count must be positive.")
    if config.diversity_soft_cap_per_setting < 1:
        raise ValueError("Hike setting diversity cap must be positive.")
    if config.diversity_soft_cap_per_region < 1:
        raise ValueError("Hike region diversity cap must be positive.")

    grouped: dict[str, list[HikeDayEvaluation]] = defaultdict(list)
    for evaluation in day_evaluations:
        grouped[evaluation.hike.id].append(evaluation)

    candidate_pool: list[HikeCandidate] = []
    for evaluations in grouped.values():
        viable = [
            evaluation
            for evaluation in evaluations
            if evaluation.eligible
            and evaluation.score >= config.minimum_candidate_score
            and evaluation.best_window is not None
        ]
        if not viable:
            continue
        best = min(viable, key=_day_sort_key)
        assert best.best_window is not None
        candidate_pool.append(
            HikeCandidate(
                hike=best.hike,
                best_day=best.date,
                best_window=best.best_window,
                score=best.score,
                reasons=best.reasons,
                cautions=best.cautions,
                alternate_day_evaluations=sorted(
                    (evaluation for evaluation in evaluations if evaluation is not best),
                    key=lambda evaluation: evaluation.date,
                ),
                access=best.access,
            )
        )

    candidate_pool.sort(key=_candidate_sort_key)
    selected: list[HikeCandidate] = []
    deferred: list[HikeCandidate] = []
    setting_counts: dict[str, int] = defaultdict(int)
    region_counts: dict[str, int] = defaultdict(int)

    for candidate in candidate_pool:
        setting = _setting_bucket(candidate.hike)
        region = candidate.hike.region
        if (
            setting_counts[setting] >= config.diversity_soft_cap_per_setting
            or region_counts[region] >= config.diversity_soft_cap_per_region
        ):
            deferred.append(candidate)
            continue
        selected.append(candidate)
        setting_counts[setting] += 1
        region_counts[region] += 1
        if len(selected) == config.maximum_candidates:
            break

    if len(selected) < config.maximum_candidates:
        selected_ids = {candidate.hike.id for candidate in selected}
        for candidate in deferred:
            if candidate.hike.id in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate.hike.id)
            if len(selected) == config.maximum_candidates:
                break

    selected.sort(key=_candidate_sort_key)
    return HikeCandidateSelection(
        day_evaluations=sorted(
            day_evaluations,
            key=lambda evaluation: (
                evaluation.date,
                evaluation.hike.name.casefold(),
                evaluation.hike.id,
            ),
        ),
        candidates=selected,
        unique_weather_locations_requested=unique_weather_locations_requested,
        weather_location_failures=weather_location_failures,
    )


def format_hike_candidates(selection: HikeCandidateSelection) -> str:
    """Format compact, appropriately caveated Telegram hike options."""
    lines = ["Hike options"]
    if not selection.candidates:
        if selection.weather_location_failures:
            lines.append("Hike recommendations unavailable from current trailhead forecasts.")
        else:
            lines.append("No sufficiently strong hike-weather matches for this weekend.")
        lines.append("Access and closure status was not checked.")
        return "\n".join(lines)

    if selection.weather_location_failures:
        lines.append(
            f"Partial trailhead weather: {selection.weather_location_failures} "
            "location request(s) unavailable."
        )

    for index, candidate in enumerate(selection.candidates, start=1):
        weather = candidate.best_window.weather
        rain = (
            f"{weather.maximum_precipitation_probability:.0f}%"
            if weather.maximum_precipitation_probability is not None
            else "unknown"
        )
        lines.extend(
            [
                "",
                f"{index}. {candidate.hike.name}",
                (
                    f"{candidate.best_day.strftime('%A')} · "
                    f"around {_format_clock(candidate.best_window.start_time)}"
                ),
                (
                    f"{candidate.hike.distance_miles:g} mi · "
                    f"{candidate.hike.elevation_gain_ft:,} ft gain · "
                    f"{candidate.hike.difficulty.value}"
                ),
                _fit_label(candidate.score),
                (
                    "Trailhead forecast: "
                    f"{weather.minimum_temperature_f:.0f}–"
                    f"{weather.maximum_temperature_f:.0f}°F · "
                    f"feels up to {weather.maximum_apparent_temperature_f:.0f}°F · "
                    f"rain {rain} · wind up to "
                    f"{weather.maximum_wind_speed_mph:.0f} mph"
                ),
                f"Why: {'; '.join(candidate.reasons[:3])}.",
            ]
        )
        if candidate.cautions:
            lines.append(f"Caution: {'; '.join(candidate.cautions[:2])}.")
        lines.extend(
            [
                f"Route note: {candidate.access.important_route_notes}",
                "Access status: not checked — verify before leaving.",
            ]
        )

    return "\n".join(lines)


def format_hike_diagnostics(
    selection: HikeCandidateSelection,
    *,
    catalog_size: int,
    top_limit: int = 10,
) -> str:
    lines = [
        f"Hike catalog: {catalog_size}",
        (f"Unique weather locations requested: {selection.unique_weather_locations_requested}"),
        f"Weather location failures: {selection.weather_location_failures}",
        f"Hike-day evaluations: {len(selection.day_evaluations)}",
        f"Hard-infeasible hike-days: {selection.hard_infeasible_day_count}",
        f"Weather-unavailable hike-days: {selection.weather_unavailable_day_count}",
        f"Viable hike-days: {selection.viable_day_count}",
        f"Final hike candidates: {len(selection.candidates)}",
        "",
        "Top hike candidates:",
    ]
    for index, candidate in enumerate(selection.candidates[:top_limit], start=1):
        weather = candidate.best_window.weather
        lines.extend(
            [
                (
                    f"{index}. {candidate.hike.name} — {candidate.best_day.isoformat()} "
                    f"around {_format_clock(candidate.best_window.start_time)} "
                    f"— score {candidate.score}"
                ),
                (
                    "   forecast: "
                    f"{weather.minimum_temperature_f:.0f}–"
                    f"{weather.maximum_temperature_f:.0f}°F, "
                    f"apparent max {weather.maximum_apparent_temperature_f:.0f}°F, "
                    f"wind {weather.maximum_wind_speed_mph:.1f} mph, "
                    f"gusts {_optional_number(weather.maximum_wind_gust_mph)} mph, "
                    "rain "
                    f"{_optional_number(weather.maximum_precipitation_probability)}%"
                ),
                f"   reasons: {', '.join(candidate.reasons)}",
                f"   cautions: {', '.join(candidate.cautions) or 'none'}",
                "   dynamic status: unchecked",
            ]
        )
    return "\n".join(lines)


def _evaluate_window(
    hike: Hike,
    start_time: datetime,
    finish_time: datetime,
    hourly: list[HourlyWeather],
    config: HikeSuitabilityConfig,
) -> HikeWindowEvaluation:
    weather = _summarize_weather(hourly)
    reasons: list[str] = []
    cautions = _base_cautions(hike)
    exclusions: list[str] = []
    score = config.base_window_score

    if start_time.month in hike.preferred_months:
        score += config.preferred_month_boost
        reasons.append("preferred season")
    elif start_time.month in hike.poor_months:
        score += config.poor_month_penalty
        reasons.append("poor-season prior")

    if _matches_preferred_time(hike, start_time, config):
        score += config.preferred_time_boost
        reasons.append("preferred time of day")
    elif TimeOfDay.FLEXIBLE in hike.best_time_of_day:
        score += config.flexible_time_boost
        reasons.append("flexible timing")

    heat_thresholds = _heat_thresholds(hike.heat_sensitivity, config)
    adjusted_heat = weather.maximum_apparent_temperature_f
    if hike.shade is ThreeLevel.HIGH:
        adjusted_heat += config.high_shade_temperature_modifier_f
    if hike.exposure is ThreeLevel.HIGH:
        adjusted_heat += config.high_exposure_temperature_modifier_f

    if adjusted_heat >= heat_thresholds.infeasible_at_f:
        exclusions.append("poor heat fit for this start window")
    elif adjusted_heat > heat_thresholds.hot_max_f:
        score += config.hot_temperature_penalty
        reasons.append("high heat exposure")
        cautions.append("This window has a substantial heat penalty.")
    elif adjusted_heat > heat_thresholds.comfortable_max_f:
        score += config.warm_temperature_adjustment
        reasons.append("warm but plausible temperature window")
    else:
        score += config.favorable_temperature_boost
        reasons.append("favorable window temperature")

    wind_thresholds = _wind_thresholds(hike.wind_sensitivity, config)
    adjusted_wind = weather.maximum_wind_speed_mph
    adjusted_gust = weather.maximum_wind_gust_mph
    if hike.exposure is ThreeLevel.HIGH:
        adjusted_wind += config.high_exposure_wind_modifier_mph
        if adjusted_gust is not None:
            adjusted_gust += config.high_exposure_wind_modifier_mph

    gust_is_calm = adjusted_gust is None or adjusted_gust <= wind_thresholds.calm_gust_max_mph
    gust_is_strong = adjusted_gust is not None and adjusted_gust >= wind_thresholds.strong_gust_mph
    if adjusted_wind >= wind_thresholds.strong_wind_mph or gust_is_strong:
        score += config.strong_wind_penalty
        reasons.append("strong wind penalty")
        cautions.append("Trailhead forecast is a poor wind fit for this route.")
    elif adjusted_wind > wind_thresholds.calm_wind_max_mph or not gust_is_calm:
        score += config.moderate_wind_penalty
        reasons.append("wind exposure penalty")
    else:
        score += config.calm_wind_boost
        reasons.append("light wind")

    hard_conditions = set(weather.conditions).intersection(config.hard_weather_conditions)
    if hard_conditions:
        exclusions.append("significant forecast weather condition")

    active_precipitation = bool(
        set(weather.conditions).intersection(config.active_precipitation_conditions)
    )
    probability = weather.maximum_precipitation_probability
    amount = weather.precipitation_inches
    rain_threshold_reached = (
        active_precipitation
        or (probability is not None and probability >= config.precipitation_probability_threshold)
        or (amount is not None and amount >= config.precipitation_amount_threshold_inches)
    )
    if rain_threshold_reached:
        score += _rain_penalty(hike.rain_sensitivity, config)
        reasons.append("active forecast rain penalty")
        cautions.append("Forecast rain may reduce route suitability.")
        heavy_rain = (
            probability is not None
            and probability >= config.heavy_precipitation_probability_threshold
        ) or (amount is not None and amount >= config.heavy_precipitation_amount_inches)
        if heavy_rain:
            score += config.heavy_rain_additional_penalty
            reasons.append("heavy precipitation penalty")
    elif probability is not None and amount is not None and probability <= 15 and amount == 0:
        score += config.dry_forecast_boost
        reasons.append("dry forecast window")

    if hike.scenic_value is ScenicValue.HIGH:
        score += config.scenic_high_boost
        reasons.append("high scenic value")

    return HikeWindowEvaluation(
        start_time=start_time,
        estimated_finish_time=finish_time,
        eligible=not exclusions,
        score=score if not exclusions else 0,
        reasons=reasons,
        cautions=cautions,
        exclusion_reasons=exclusions,
        weather=weather,
    )


def _summarize_weather(hourly: list[HourlyWeather]) -> HikeWindowWeather:
    apparent_temperatures = [
        item.apparent_temperature_f
        if item.apparent_temperature_f is not None
        else item.temperature_f
        for item in hourly
    ]
    probabilities = [
        item.precipitation_probability
        for item in hourly
        if item.precipitation_probability is not None
    ]
    precipitation_values = [
        item.precipitation_inches for item in hourly if item.precipitation_inches is not None
    ]
    gusts = [item.wind_gust_mph for item in hourly if item.wind_gust_mph is not None]
    conditions = list(dict.fromkeys(item.condition for item in hourly))
    return HikeWindowWeather(
        minimum_temperature_f=min(item.temperature_f for item in hourly),
        maximum_temperature_f=max(item.temperature_f for item in hourly),
        maximum_apparent_temperature_f=max(apparent_temperatures),
        maximum_precipitation_probability=max(probabilities) if probabilities else None,
        precipitation_inches=sum(precipitation_values) if precipitation_values else None,
        maximum_wind_speed_mph=max(item.wind_speed_mph for item in hourly),
        maximum_wind_gust_mph=max(gusts) if gusts else None,
        conditions=conditions,
        hourly_points=len(hourly),
    )


def _heat_thresholds(
    sensitivity: ThreeLevel,
    config: HikeSuitabilityConfig,
) -> HeatThresholds:
    if sensitivity is ThreeLevel.LOW:
        return config.low_heat_thresholds
    if sensitivity is ThreeLevel.HIGH:
        return config.high_heat_thresholds
    return config.moderate_heat_thresholds


def _wind_thresholds(
    sensitivity: ThreeLevel,
    config: HikeSuitabilityConfig,
) -> WindThresholds:
    if sensitivity is ThreeLevel.LOW:
        return config.low_wind_thresholds
    if sensitivity is ThreeLevel.HIGH:
        return config.high_wind_thresholds
    return config.moderate_wind_thresholds


def _rain_penalty(
    sensitivity: ThreeLevel,
    config: HikeSuitabilityConfig,
) -> int:
    if sensitivity is ThreeLevel.LOW:
        return config.low_rain_penalty
    if sensitivity is ThreeLevel.HIGH:
        return config.high_rain_penalty
    return config.moderate_rain_penalty


def _matches_preferred_time(
    hike: Hike,
    start: datetime,
    config: HikeSuitabilityConfig,
) -> bool:
    hour = start.hour
    if config.morning_start_hour <= hour < config.midday_start_hour:
        period = TimeOfDay.MORNING
    elif config.midday_start_hour <= hour < config.afternoon_start_hour:
        period = TimeOfDay.MIDDAY
    elif config.afternoon_start_hour <= hour < config.evening_start_hour:
        period = TimeOfDay.AFTERNOON
    elif config.evening_start_hour <= hour < config.night_start_hour:
        period = TimeOfDay.EVENING
    else:
        return False
    return period in hike.best_time_of_day


def _base_cautions(hike: Hike) -> list[str]:
    cautions: list[str] = []
    if hike.mud_sensitivity is ThreeLevel.HIGH:
        cautions.append("Recent-rain and mud conditions are unknown.")
    if hike.coordinate_precision is CoordinatePrecision.APPROXIMATE_TRAILHEAD:
        cautions.append("Trailhead coordinate is approximate; confirm the route start.")
    return cautions


def _access_context(hike: Hike) -> HikeAccessContext:
    return HikeAccessContext(
        parking_notes=hike.parking_notes,
        access_baseline_notes=hike.access_baseline_notes,
        seasonal_access_notes=hike.seasonal_access_notes,
        important_route_notes=hike.important_route_notes,
    )


def _weather_unavailable_evaluation(
    hike: Hike,
    forecast_date: date,
) -> HikeDayEvaluation:
    return HikeDayEvaluation(
        hike=hike,
        date=forecast_date,
        eligible=False,
        score=0,
        exclusion_reasons=["trailhead weather unavailable"],
        access=_access_context(hike),
    )


def _setting_bucket(hike: Hike) -> str:
    settings = set(hike.setting)
    if settings.intersection({"coastal", "beach", "bluff", "headland", "rocky-shore"}):
        return "coastal"
    if settings.intersection({"redwood", "forest", "creek"}):
        return "forest"
    if settings.intersection({"mountain", "ridge", "grassland"}):
        return "ridge"
    if settings.intersection({"lake", "lagoon", "wetland", "river"}):
        return "water"
    return "mixed"


def _day_sort_key(
    evaluation: HikeDayEvaluation,
) -> tuple[int, date, datetime, str]:
    assert evaluation.best_window is not None
    return (
        -evaluation.score,
        evaluation.date,
        evaluation.best_window.start_time,
        evaluation.hike.id,
    )


def _candidate_sort_key(
    candidate: HikeCandidate,
) -> tuple[int, date, datetime, str, str]:
    return (
        -candidate.score,
        candidate.best_day,
        candidate.best_window.start_time,
        candidate.hike.name.casefold(),
        candidate.hike.id,
    )


def _dates_in_window(
    start: datetime,
    end: datetime,
    timezone: ZoneInfo,
) -> list[date]:
    first = start.astimezone(timezone).date()
    last = (end - timedelta(microseconds=1)).astimezone(timezone).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _ceil_to_hour(value: datetime) -> datetime:
    rounded = value.replace(minute=0, second=0, microsecond=0)
    if rounded < value:
        rounded += timedelta(hours=1)
    return rounded


def _is_contiguous(hourly: list[HourlyWeather]) -> bool:
    return all(
        current.time - previous.time == timedelta(hours=1)
        for previous, current in zip(hourly, hourly[1:], strict=False)
    )


def _validate_window(start: datetime, end: datetime) -> None:
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Hike suitability requires timezone-aware boundaries.")
    if end <= start:
        raise ValueError("Hike suitability end must be after start.")


def _fit_label(score: int) -> str:
    if score >= 32:
        return "Strong forecast fit"
    if score >= 24:
        return "Good forecast fit"
    return "Viable forecast fit"


def _format_clock(value: datetime) -> str:
    return value.strftime("%-I %p")


def _optional_number(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "unknown"
