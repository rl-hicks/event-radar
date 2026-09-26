from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, field_validator

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.event_analysis import SemanticConfidence
from event_radar.models.user_context import UserContext


def _aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Discovered event start time must be timezone-aware.")
    return value


def _aware_optional(value: datetime | None) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise ValueError("Discovered event end time must be timezone-aware when supplied.")
    return value


class ExistingEventIdentity(BaseModel):
    title: str
    start_time: datetime
    city: str
    venue: str | None
    source_urls: list[HttpUrl]


class WebDiscoveryRequest(BaseModel):
    generated_at: datetime
    weekend_start: datetime
    weekend_end: datetime
    user_context: UserContext
    permanent_directions: list[str]
    temporary_directions: list[str]
    existing_events: list[ExistingEventIdentity]


class DiscoveredEvent(BaseModel):
    discovery_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime | None
    venue: str | None
    city: str = Field(min_length=1)
    state: str = "CA"
    description_evidence: str = Field(min_length=1)
    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, min_length=3, max_length=3)
    price_details: str | None = None
    why_it_may_fit: str = Field(min_length=1)
    experience_summary: str = Field(min_length=1)
    experience_modes: list[str]
    interaction_architecture: str = Field(min_length=1)
    solo_viability: str = Field(min_length=1)
    active_value: str = Field(min_length=1)
    distinctiveness: str = Field(min_length=1)
    social_opportunity: str = Field(min_length=1)
    friction_summary: str = Field(min_length=1)
    schedule_observation: str = Field(min_length=1)
    uncertainties: list[str]
    verification_confidence: SemanticConfidence
    source_confidence: SemanticConfidence

    _start_is_aware = field_validator("start_time")(_aware)
    _end_is_aware = field_validator("end_time")(_aware_optional)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        """Validate HTTP evidence without emitting unsupported JSON Schema uri format."""
        return str(TypeAdapter(HttpUrl).validate_python(value))


class WebDiscoveryResult(BaseModel):
    discoveries: list[DiscoveredEvent] = Field(max_length=12)


class WebDiscoveryOutcome(BaseModel):
    result: WebDiscoveryResult | None
    valid_discoveries: list[DiscoveredEvent]
    duplicates_removed: int = Field(ge=0)
    diagnostics: AIStageDiagnostics
