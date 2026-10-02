from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from event_radar.models.ai import AIStageDiagnostics
from event_radar.models.user_context import StructuredRuntimeContext


def _aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Event occurrence datetimes must be timezone-aware.")
    return value


def _aware_optional(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None


class EventDisposition(StrEnum):
    RETAIN = "retain"
    BORDERLINE = "borderline"
    REJECT = "reject"


class SemanticConfidence(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNKNOWN = "unknown"


class EventOrigin(StrEnum):
    SCRAPED = "scraped"
    WEB_DISCOVERED = "web_discovered"


class EventEvidenceClaim(StrEnum):
    EVENT_EXISTENCE = "event_existence"
    DATE_TIME = "date_time"
    LOCATION = "location"
    PRICE = "price"
    EXPERIENCE_DESCRIPTION = "experience_description"


class EventSourceFact(BaseModel):
    source_name: str = Field(min_length=1)
    source_id: str | None
    source_url: HttpUrl
    supported_claims: list[EventEvidenceClaim] = Field(default_factory=list)
    source_confidence: SemanticConfidence | None = None


class EventOccurrenceFact(BaseModel):
    event_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    start_time: datetime
    end_time: datetime | None
    venue: str | None
    city: str = Field(min_length=1)
    state: str = Field(min_length=1)
    categories: list[str]
    description: str | None
    price_min: Decimal | None
    price_max: Decimal | None
    price_currency: str | None
    price_details: str | None
    price_conflict: bool = False
    sources: list[EventSourceFact] = Field(min_length=1)

    _start_is_aware = field_validator("start_time")(_aware)
    _end_is_aware = field_validator("end_time")(_aware_optional)


class ScrapedEventAnalysisRequest(BaseModel):
    generated_at: datetime
    weekend_start: datetime
    weekend_end: datetime
    user_context: StructuredRuntimeContext
    personal_experience_context: str = Field(min_length=1)
    permanent_directions: list[str]
    temporary_directions: list[str]
    events: list[EventOccurrenceFact]

    _generated_is_aware = field_validator("generated_at")(_aware)
    _weekend_start_is_aware = field_validator("weekend_start")(_aware)
    _weekend_end_is_aware = field_validator("weekend_end")(_aware)


class ScrapedEventJudgment(BaseModel):
    event_id: str = Field(min_length=1)
    disposition: EventDisposition
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
    experience_group_id: str | None = None
    reason_for_disposition: str = Field(min_length=1)
    confidence: SemanticConfidence


class ExperienceGroupProposal(BaseModel):
    group_id: str = Field(min_length=1)
    occurrence_ids: list[str] = Field(min_length=2)
    experience_summary: str = Field(min_length=1)


class ScrapedEventAnalysis(BaseModel):
    events: list[ScrapedEventJudgment]
    experience_groups: list[ExperienceGroupProposal]


class ScrapedAnalysisBatchDiagnostics(AIStageDiagnostics):
    batch_index: int


class ScrapedAnalysisDiagnostics(AIStageDiagnostics):
    status: Literal["success", "partial", "fallback", "skipped"]
    batch_size: int
    batch_count: int
    successful_batch_count: int
    failed_batch_count: int
    fallback_event_count: int
    batches: list[ScrapedAnalysisBatchDiagnostics]


class ScrapedEventAnalysisOutcome(BaseModel):
    analysis: ScrapedEventAnalysis | None
    diagnostics: ScrapedAnalysisDiagnostics | AIStageDiagnostics
    fallback_event_ids: list[str] = Field(default_factory=list)

    @property
    def status(self) -> Literal["success", "partial", "fallback", "skipped"]:
        """Prefer the explicit batched status; support older/non-AI outcomes."""
        if isinstance(self.diagnostics, ScrapedAnalysisDiagnostics):
            return self.diagnostics.status
        if self.diagnostics.success:
            return "success"
        return "skipped" if self.diagnostics.input_count == 0 else "fallback"


class WeekendEventCard(BaseModel):
    candidate_type: Literal["event"] = "event"
    candidate_id: str = Field(min_length=1)
    origin: EventOrigin
    title: str = Field(min_length=1)
    occurrences: list[EventOccurrenceFact] = Field(min_length=1)
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
    source_confidence: SemanticConfidence
    verification_confidence: SemanticConfidence | None = None
    semantic_analysis_available: bool

    @model_validator(mode="after")
    def validate_occurrence_identity(self) -> "WeekendEventCard":
        occurrence_ids = [occurrence.event_id for occurrence in self.occurrences]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("Event card occurrence IDs must be unique.")
        return self
