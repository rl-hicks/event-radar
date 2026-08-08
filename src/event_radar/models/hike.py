from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

Month = Annotated[int, Field(ge=1, le=12)]


class Difficulty(StrEnum):
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


class RouteType(StrEnum):
    LOOP = "loop"
    OUT_AND_BACK = "out-and-back"
    POINT_TO_POINT = "point-to-point"
    NETWORK_VARIABLE = "network/variable"


class ThreeLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class SoloFit(StrEnum):
    STRONG = "strong"
    NORMAL = "normal"
    WEAK = "weak"


class ScenicValue(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class TimeOfDay(StrEnum):
    MORNING = "morning"
    MIDDAY = "midday"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    FLEXIBLE = "flexible"


class DriveFriction(StrEnum):
    VERY_CLOSE = "very_close"
    REGIONAL = "regional"
    DESTINATION = "destination"


class CoordinatePrecision(StrEnum):
    MAPPED_TRAILHEAD = "mapped_trailhead"
    APPROXIMATE_TRAILHEAD = "approximate_trailhead"


class Confidence(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class BaselineLocation(BaseModel):
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class CatalogUnits(BaseModel):
    distance: str = Field(min_length=1)
    elevation_gain: str = Field(min_length=1)
    duration: str = Field(min_length=1)
    coordinates: str = Field(min_length=1)


class ControlledVocabularies(BaseModel):
    difficulty: list[Difficulty]
    route_type: list[RouteType]
    three_level_scale: list[ThreeLevel]
    solo_fit: list[SoloFit]
    scenic_value: list[ScenicValue]
    best_time_of_day: list[TimeOfDay]
    drive_friction_from_santa_rosa: list[DriveFriction]
    coordinate_precision: list[CoordinatePrecision]
    confidence: list[Confidence]


class HikeCatalogMetadata(BaseModel):
    catalog_name: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    research_cutoff_date: date
    baseline_location: BaselineLocation
    record_count: int = Field(ge=0)
    units: CatalogUnits
    controlled_vocabularies: ControlledVocabularies
    schema_notes: list[str] = Field(min_length=1)


class DurationRange(BaseModel):
    min: int = Field(gt=0)
    max: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "DurationRange":
        if self.max < self.min:
            raise ValueError("Duration maximum must be at least the minimum.")
        return self


class HikeProvenance(BaseModel):
    directly_sourced_fields: list[str]
    derived_fields: list[str]
    derivation_basis: str = Field(min_length=1)
    source_notes: str = Field(min_length=1)


class HikeDataQuality(BaseModel):
    coordinate_confidence: Confidence
    overall_confidence: Confidence
    uncertainties: list[str]


class Hike(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    park_or_area: str = Field(min_length=1)
    managing_agency: str = Field(min_length=1)
    region: str = Field(min_length=1)
    nearest_city: str = Field(min_length=1)

    trailhead_name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    coordinate_precision: CoordinatePrecision

    official_source_url: HttpUrl
    secondary_source_urls: list[HttpUrl]

    distance_miles: float = Field(gt=0, allow_inf_nan=False)
    elevation_gain_ft: int = Field(ge=0)
    estimated_duration_minutes: DurationRange
    difficulty: Difficulty
    route_type: RouteType
    route_start: str = Field(min_length=1)
    route_end: str = Field(min_length=1)
    trail_sequence: list[str] = Field(min_length=1)

    setting: list[str] = Field(min_length=1)
    shade: ThreeLevel
    exposure: ThreeLevel
    heat_sensitivity: ThreeLevel
    wind_sensitivity: ThreeLevel
    mud_sensitivity: ThreeLevel
    rain_sensitivity: ThreeLevel

    preferred_months: list[Month]
    acceptable_months: list[Month]
    poor_months: list[Month]
    best_time_of_day: list[TimeOfDay] = Field(min_length=1)
    minimum_reasonable_daylight_minutes: int = Field(gt=0)

    solo_fit: SoloFit
    scenic_value: ScenicValue
    experience_tags: list[str] = Field(min_length=1)
    drive_friction_from_santa_rosa: DriveFriction

    parking_notes: str = Field(min_length=1)
    access_baseline_notes: str = Field(min_length=1)
    seasonal_access_notes: str = Field(min_length=1)
    important_route_notes: str = Field(min_length=1)
    dynamic_status_check_required: Literal[True]

    provenance: HikeProvenance
    data_quality: HikeDataQuality

    @field_validator(
        "setting",
        "experience_tags",
        "preferred_months",
        "acceptable_months",
        "poor_months",
        "best_time_of_day",
    )
    @classmethod
    def validate_unique_lists(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("Catalog list values must not contain duplicates.")
        return value

    @field_validator("trail_sequence", "setting", "experience_tags")
    @classmethod
    def validate_nonempty_strings(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("Catalog string lists must not contain blank values.")
        return value

    @model_validator(mode="after")
    def validate_month_partition(self) -> "Hike":
        months = [
            *self.preferred_months,
            *self.acceptable_months,
            *self.poor_months,
        ]
        if len(months) != 12 or set(months) != set(range(1, 13)):
            raise ValueError("Preferred, acceptable, and poor months must partition all 12 months.")
        return self


class HikeCatalog(BaseModel):
    catalog_metadata: HikeCatalogMetadata
    hikes: list[Hike]

    @model_validator(mode="after")
    def validate_catalog_invariants(self) -> "HikeCatalog":
        if self.catalog_metadata.record_count != len(self.hikes):
            raise ValueError("Catalog metadata record_count does not match hike count.")

        ids = [hike.id for hike in self.hikes]
        if len(ids) != len(set(ids)):
            raise ValueError("Hike IDs must be unique.")

        route_identities = [
            (
                _normalize(hike.name),
                _normalize(hike.park_or_area),
                _normalize(hike.route_start),
                _normalize(hike.route_end),
                tuple(_normalize(item) for item in hike.trail_sequence),
            )
            for hike in self.hikes
        ]
        if len(route_identities) != len(set(route_identities)):
            raise ValueError("Duplicate hike route identity detected.")

        _validate_vocabularies(self.catalog_metadata.controlled_vocabularies)
        return self


def _validate_vocabularies(vocabularies: ControlledVocabularies) -> None:
    expected: tuple[tuple[str, set[StrEnum], set[StrEnum]], ...] = (
        ("difficulty", set(vocabularies.difficulty), set(Difficulty)),
        ("route_type", set(vocabularies.route_type), set(RouteType)),
        ("three_level_scale", set(vocabularies.three_level_scale), set(ThreeLevel)),
        ("solo_fit", set(vocabularies.solo_fit), set(SoloFit)),
        ("scenic_value", set(vocabularies.scenic_value), set(ScenicValue)),
        ("best_time_of_day", set(vocabularies.best_time_of_day), set(TimeOfDay)),
        (
            "drive_friction_from_santa_rosa",
            set(vocabularies.drive_friction_from_santa_rosa),
            set(DriveFriction),
        ),
        (
            "coordinate_precision",
            set(vocabularies.coordinate_precision),
            set(CoordinatePrecision),
        ),
        ("confidence", set(vocabularies.confidence), set(Confidence)),
    )
    for name, actual, defined in expected:
        if actual != defined:
            raise ValueError(f"Catalog controlled vocabulary {name} does not match schema.")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
