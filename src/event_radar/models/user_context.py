from datetime import time
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class PreferenceStrength(StrEnum):
    STRONG = "strong"
    POSITIVE = "positive"
    NEUTRAL_POSITIVE = "neutral_to_positive"
    CONDITIONAL = "conditional"
    WEAK_NEUTRAL = "weak_to_neutral"
    WEAK = "weak"


class SoloFriction(StrEnum):
    NONE = "none"
    MILD = "mild"
    MILD_MODERATE = "mild_to_moderate"
    MODERATE = "moderate"
    SUBSTANTIAL = "substantial"


class UserBaseLocation(BaseModel):
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Base-location timezone must be a valid IANA timezone.") from exc
        return value


class DriveToleranceBand(BaseModel):
    maximum_minutes: int | None = Field(default=None, gt=0)
    posture: str = Field(min_length=1)


class CostToleranceBand(BaseModel):
    maximum_dollars: Decimal | None = Field(default=None, ge=0)
    posture: str = Field(min_length=1)


class SocialPosture(BaseModel):
    objective: str = Field(min_length=1)
    interaction_architecture_signals: list[str] = Field(min_length=1)
    safeguards: list[str] = Field(min_length=1)


class PeerContext(BaseModel):
    approximate_min_age: int = Field(ge=18)
    approximate_max_age: int = Field(ge=18)
    soft_signal_only: Literal[True] = True
    restrictions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> "PeerContext":
        if self.approximate_max_age < self.approximate_min_age:
            raise ValueError("Peer-context maximum age must not precede minimum age.")
        return self


class CategoryPreference(BaseModel):
    strength: PreferenceStrength
    notes: str = Field(min_length=1)


class AvailabilityStatus(StrEnum):
    OPEN = "open"
    SOFT_ANCHOR = "soft_anchor"
    UNKNOWN = "unknown"
    HARD_BLOCK = "hard_block"


class AvailabilityWindow(BaseModel):
    id: str = Field(min_length=1)
    day_of_week: Literal[
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    start_time: time | None = None
    end_time: time | None = None
    status: AvailabilityStatus
    description: str = Field(min_length=1)
    override_policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> "AvailabilityWindow":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("Availability end time must follow start time.")
        return self


class HikingPosture(BaseModel):
    desired_difficulties: list[Literal["easy", "moderate", "hard"]] = Field(min_length=1)
    normal_profile: Literal["easy", "moderate", "hard"]
    local_regional_default: str = Field(min_length=1)
    destination_posture: str = Field(min_length=1)


class OutputPreferences(BaseModel):
    normal_target_minimum: int = Field(ge=0)
    normal_target_maximum: int = Field(ge=1, le=18)
    absolute_maximum: Literal[18] = 18
    quota_is_required: Literal[False] = False
    rigid_itinerary: Literal[False] = False
    posture: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_range(self) -> "OutputPreferences":
        if self.normal_target_minimum > self.normal_target_maximum:
            raise ValueError("Output target minimum must not exceed its maximum.")
        return self


class UserContext(BaseModel):
    """Stable, private recommendation policy for one future-compatible profile."""

    profile_id: str = Field(min_length=1)
    profile_label: str = Field(min_length=1)
    base_location: UserBaseLocation
    core_objective: str = Field(min_length=1)
    action_posture: list[str] = Field(min_length=1)
    social_posture: SocialPosture
    peer_context: PeerContext
    meeting_people_posture: list[str] = Field(min_length=1)
    drive_tolerance: list[DriveToleranceBand] = Field(min_length=1)
    cost_tolerance: list[CostToleranceBand] = Field(min_length=1)
    solo_attendance: dict[str, SoloFriction] = Field(min_length=1)
    nightlife_posture: list[str] = Field(min_length=1)
    crowd_posture: list[str] = Field(min_length=1)
    hiking_posture: HikingPosture
    recurring_availability: list[AvailabilityWindow] = Field(min_length=1)
    category_priors: dict[str, CategoryPreference] = Field(min_length=1)
    output_preferences: OutputPreferences
    anti_objectives: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_structured_policy(self) -> "UserContext":
        availability_ids = [window.id for window in self.recurring_availability]
        if len(availability_ids) != len(set(availability_ids)):
            raise ValueError("Availability window IDs must be unique.")
        if self.drive_tolerance[-1].maximum_minutes is not None:
            raise ValueError("Drive tolerance must end with an open-ended band.")
        if self.cost_tolerance[-1].maximum_dollars is not None:
            raise ValueError("Cost tolerance must end with an open-ended band.")
        return self


class StructuredRuntimeContext(BaseModel):
    """Factual/operational user fields supplied to AI; taste lives in private Markdown."""

    profile_id: str = Field(min_length=1)
    profile_label: str = Field(min_length=1)
    base_location: UserBaseLocation
    drive_tolerance: list[DriveToleranceBand] = Field(min_length=1)
    cost_tolerance: list[CostToleranceBand] = Field(min_length=1)
    hiking_posture: HikingPosture
    recurring_availability: list[AvailabilityWindow] = Field(min_length=1)


def structured_runtime_context(context: UserContext) -> StructuredRuntimeContext:
    return StructuredRuntimeContext(
        profile_id=context.profile_id,
        profile_label=context.profile_label,
        base_location=context.base_location,
        drive_tolerance=context.drive_tolerance,
        cost_tolerance=context.cost_tolerance,
        hiking_posture=context.hiking_posture,
        recurring_availability=context.recurring_availability,
    )
