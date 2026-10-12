"""Versioned product User Context. No historical profile or private-file dependency."""

from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=400)
]
Items = Annotated[tuple[Text, ...], Field(max_length=20)]
Minutes = Annotated[int, Field(strict=True, ge=0, le=1440)]


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class BaseLocation(ContextModel):
    locality: Text
    timezone: Annotated[str, StringConstraints(strict=True, max_length=100)]
    latitude: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid IANA timezone.") from None
        return value

    @model_validator(mode="after")
    def coordinate_pair(self) -> "BaseLocation":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates must be supplied together.")
        return self


class TravelPreferences(ContextModel):
    maximum_one_way_minutes: Minutes | None = None
    modes: Items | None = None
    exceptional_experience_tradeoffs: Text | None = None


class CostPreferences(ContextModel):
    maximum_per_activity: (
        Annotated[Decimal, Field(ge=0, le=100000, max_digits=8, decimal_places=2)] | None
    ) = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    tradeoffs: Text | None = None

    @model_validator(mode="after")
    def amount_currency(self) -> "CostPreferences":
        if self.maximum_per_activity is not None and self.currency is None:
            raise ValueError("An amount requires an explicit currency.")
        return self


class RecurringAvailability(ContextModel):
    weekday: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    start: time
    end: time
    disposition: Literal["available", "unavailable", "prefer"]
    note: Text | None = None

    @model_validator(mode="after")
    def valid_interval(self) -> "RecurringAvailability":
        if self.start.tzinfo is not None or self.end.tzinfo is not None or self.end <= self.start:
            raise ValueError("Use an increasing same-day local time interval.")
        return self


class OutputPreferences(ContextModel):
    maximum_recommendations: Annotated[int, Field(strict=True, ge=1, le=18)] | None = None
    detail: Literal["brief", "balanced", "detailed"] | None = None
    priorities: Items | None = None


class ProductUserContext(ContextModel):
    schema_version: Literal["user-context-v1"] = "user-context-v1"
    base_location: BaseLocation
    interests: Items | None = None
    activity_preferences: Items | None = None
    exclusions: Items | None = None
    desired_experiences: Items | None = None
    objectives: Items | None = None
    social_preferences: Items | None = None
    participation_preferences: Items | None = None
    accessibility_constraints: Items | None = None
    novelty_preferences: Text | None = None
    solo_considerations: Items | None = None
    travel: TravelPreferences | None = None
    cost: CostPreferences | None = None
    recurring_availability: (
        Annotated[tuple[RecurringAvailability, ...], Field(max_length=21)] | None
    ) = None
    output: OutputPreferences | None = None


class ContextUpdate(ContextModel):
    expected_revision_id: UUID
    context: ProductUserContext


class ContextRevision(ContextModel):
    revision_id: UUID
    revision: int
    created_at: datetime
    content_hash: str
    context: ProductUserContext
