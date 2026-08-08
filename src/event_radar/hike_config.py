from dataclasses import dataclass

from event_radar.models.weather import WeatherCondition


@dataclass(frozen=True)
class HeatThresholds:
    comfortable_max_f: float
    hot_max_f: float
    infeasible_at_f: float


@dataclass(frozen=True)
class WindThresholds:
    calm_wind_max_mph: float
    strong_wind_mph: float
    calm_gust_max_mph: float
    strong_gust_mph: float


@dataclass(frozen=True)
class HikeSuitabilityConfig:
    """Inspectable deterministic weather-suitability configuration."""

    maximum_candidates: int = 10
    minimum_candidate_score: int = 15
    maximum_weather_concurrency: int = 5

    diversity_soft_cap_per_setting: int = 3
    diversity_soft_cap_per_region: int = 3

    daylight_buffer_minutes: int = 45

    base_window_score: int = 20
    preferred_month_boost: int = 4
    poor_month_penalty: int = -6
    preferred_time_boost: int = 3
    flexible_time_boost: int = 1
    scenic_high_boost: int = 2

    favorable_temperature_boost: int = 6
    warm_temperature_adjustment: int = 1
    hot_temperature_penalty: int = -8
    high_shade_temperature_modifier_f: float = -3
    high_exposure_temperature_modifier_f: float = 3

    low_heat_thresholds: HeatThresholds = HeatThresholds(86, 98, 108)
    moderate_heat_thresholds: HeatThresholds = HeatThresholds(80, 90, 100)
    high_heat_thresholds: HeatThresholds = HeatThresholds(76, 84, 94)

    calm_wind_boost: int = 3
    moderate_wind_penalty: int = -4
    strong_wind_penalty: int = -10
    high_exposure_wind_modifier_mph: float = 2

    low_wind_thresholds: WindThresholds = WindThresholds(18, 30, 28, 45)
    moderate_wind_thresholds: WindThresholds = WindThresholds(14, 24, 22, 36)
    high_wind_thresholds: WindThresholds = WindThresholds(10, 18, 18, 30)

    dry_forecast_boost: int = 2
    precipitation_probability_threshold: float = 35
    heavy_precipitation_probability_threshold: float = 70
    precipitation_amount_threshold_inches: float = 0.03
    heavy_precipitation_amount_inches: float = 0.20
    low_rain_penalty: int = -3
    moderate_rain_penalty: int = -6
    high_rain_penalty: int = -10
    heavy_rain_additional_penalty: int = -10

    morning_start_hour: int = 5
    midday_start_hour: int = 11
    afternoon_start_hour: int = 14
    evening_start_hour: int = 17
    night_start_hour: int = 21

    hard_weather_conditions: tuple[WeatherCondition, ...] = (
        WeatherCondition.FREEZING_RAIN,
        WeatherCondition.SNOW,
        WeatherCondition.SNOW_SHOWERS,
        WeatherCondition.THUNDERSTORM,
        WeatherCondition.THUNDERSTORM_WITH_HAIL,
    )
    active_precipitation_conditions: tuple[WeatherCondition, ...] = (
        WeatherCondition.DRIZZLE,
        WeatherCondition.FREEZING_DRIZZLE,
        WeatherCondition.RAIN,
        WeatherCondition.FREEZING_RAIN,
        WeatherCondition.RAIN_SHOWERS,
        WeatherCondition.SNOW,
        WeatherCondition.SNOW_SHOWERS,
        WeatherCondition.THUNDERSTORM,
        WeatherCondition.THUNDERSTORM_WITH_HAIL,
    )


DEFAULT_HIKE_SUITABILITY_CONFIG = HikeSuitabilityConfig()
