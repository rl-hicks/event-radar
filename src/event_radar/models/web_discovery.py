from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, field_validator, model_validator

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.event_analysis import EventEvidenceClaim, SemanticConfidence
from event_radar.models.user_context import StructuredRuntimeContext


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
    user_context: StructuredRuntimeContext
    personal_experience_context: str = Field(min_length=1)
    permanent_directions: list[str]
    temporary_directions: list[str]
    existing_events: list[ExistingEventIdentity]


class WebEvidenceSource(BaseModel):
    source_url: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    supported_claims: list[EventEvidenceClaim] = Field(min_length=1)
    source_confidence: SemanticConfidence
    evidence_summary: str = Field(min_length=1)
    occurrence_start_time: datetime | None = None
    occurrence_end_time: datetime | None = None

    _start_is_aware = field_validator("occurrence_start_time")(_aware_optional)
    _end_is_aware = field_validator("occurrence_end_time")(_aware_optional)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        """Validate HTTP evidence without emitting unsupported JSON Schema uri format."""
        return str(TypeAdapter(HttpUrl).validate_python(value))

    @model_validator(mode="after")
    def validate_claim_evidence(self) -> "WebEvidenceSource":
        if len(self.supported_claims) != len(set(self.supported_claims)):
            raise ValueError("Web evidence source claims must be unique.")
        supports_time = EventEvidenceClaim.DATE_TIME in self.supported_claims
        if supports_time and self.occurrence_start_time is None:
            raise ValueError(
                "Date/time evidence must include the occurrence start time shown by the source."
            )
        if not supports_time and (
            self.occurrence_start_time is not None or self.occurrence_end_time is not None
        ):
            raise ValueError(
                "Occurrence timestamps may only be supplied by date/time evidence sources."
            )
        if (
            self.occurrence_start_time is not None
            and self.occurrence_end_time is not None
            and self.occurrence_end_time <= self.occurrence_start_time
        ):
            raise ValueError("Evidence occurrence end time must follow its start time.")
        return self


class DiscoveredEvent(BaseModel):
    discovery_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    evidence_sources: list[WebEvidenceSource] = Field(min_length=1)
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

    _start_is_aware = field_validator("start_time")(_aware)
    _end_is_aware = field_validator("end_time")(_aware_optional)

    @model_validator(mode="after")
    def validate_unique_evidence_urls(self) -> "DiscoveredEvent":
        urls = [source.source_url for source in self.evidence_sources]
        if len(urls) != len(set(urls)):
            raise ValueError("Web discovery evidence source URLs must be unique.")
        return self


class WebDiscoveryResult(BaseModel):
    discoveries: list[DiscoveredEvent] = Field(max_length=12)


class WebDiscoveryOutcome(BaseModel):
    result: WebDiscoveryResult | None
    valid_discoveries: list[DiscoveredEvent]
    duplicates_removed: int = Field(ge=0)
    diagnostics: AIStageDiagnostics
