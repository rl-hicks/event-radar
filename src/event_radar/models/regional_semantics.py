"""Structured output contracts for user-neutral regional semantic analysis."""

from pydantic import BaseModel, ConfigDict, model_validator

from event_radar.models.regional import Identifier, SemanticDescriptor


class SemanticContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class OpportunitySemanticAnalysis(SemanticContract):
    opportunity_id: Identifier
    descriptors: tuple[SemanticDescriptor, ...]


class RegionalSemanticAnalysis(SemanticContract):
    opportunities: tuple[OpportunitySemanticAnalysis, ...]

    @model_validator(mode="after")
    def unique_opportunity_ids(self) -> "RegionalSemanticAnalysis":
        ids = tuple(item.opportunity_id for item in self.opportunities)
        if len(ids) != len(set(ids)):
            raise ValueError("Semantic analysis opportunity IDs must be unique.")
        return self
