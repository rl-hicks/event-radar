from pydantic import BaseModel, Field

from event_radar.models.event import Event


class EventEvaluation(BaseModel):
    """Inspectable deterministic eligibility and relevance result."""

    event: Event
    eligible: bool
    score: int
    reasons: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)
    activity_type: str = "other"


class CandidateSelection(BaseModel):
    """Full evaluation output plus the bounded set for downstream synthesis."""

    evaluations: list[EventEvaluation]
    candidates: list[EventEvaluation]

    @property
    def eligible_count(self) -> int:
        return sum(evaluation.eligible for evaluation in self.evaluations)

    @property
    def excluded_count(self) -> int:
        return len(self.evaluations) - self.eligible_count

    @property
    def events(self) -> list[Event]:
        return [evaluation.event for evaluation in self.candidates]
