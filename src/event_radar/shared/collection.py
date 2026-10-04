"""Source-agnostic regional collection registry and orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Literal, Protocol

from event_radar.models.regional import (
    FactualExclusion,
    FailureCode,
    RegionalOpportunity,
    ResearchScope,
    SourceCoverage,
)

SourceClass = Literal[
    "regional_calendar",
    "direct_organizer",
    "ticketing_platform",
    "community_calendar",
    "outdoor_catalog",
    "weather",
    "other",
]
CollectionMechanism = Literal[
    "api",
    "html",
    "structured_data",
    "calendar",
    "catalog",
    "weather",
]
OpportunityKind = Literal["event", "hike"]


@dataclass(frozen=True, slots=True)
class RegionalSourceDescriptor:
    source_id: str
    source_class: SourceClass
    mechanism: CollectionMechanism
    coverage_description: str
    opportunity_kinds: tuple[OpportunityKind, ...]
    region_ids: tuple[str, ...] = ("sonoma-county-ca",)

    def __post_init__(self) -> None:
        if re.fullmatch(r"^[a-z0-9][a-z0-9._-]{0,119}$", self.source_id) is None:
            raise ValueError("Source ID must use the regional identifier format.")
        if not self.coverage_description.strip():
            raise ValueError("Source coverage description must be non-empty.")
        if not self.opportunity_kinds:
            raise ValueError("Source must declare at least one opportunity kind.")
        if len(self.opportunity_kinds) != len(set(self.opportunity_kinds)):
            raise ValueError("Source opportunity kinds must be unique.")
        if not self.region_ids or len(self.region_ids) != len(set(self.region_ids)):
            raise ValueError("Source region IDs must be non-empty and unique.")


@dataclass(frozen=True, slots=True)
class RegionalSourceResult:
    opportunities: tuple[RegionalOpportunity, ...]
    exclusions: tuple[FactualExclusion, ...] = ()


class RegionalSourceAdapter(Protocol):
    descriptor: RegionalSourceDescriptor

    async def collect(
        self,
        scope: ResearchScope,
        *,
        observed_at: datetime,
    ) -> RegionalSourceResult: ...


class RegionalSourceFailure(RuntimeError):
    """Expected bounded source failure that should degrade independently."""

    def __init__(self, failure_code: FailureCode) -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    adapter: RegionalSourceAdapter
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SourceCoverageAssessment:
    enabled_source_ids: tuple[str, ...]
    disabled_source_ids: tuple[str, ...]
    attempted_source_ids: tuple[str, ...]
    successful_source_ids: tuple[str, ...]
    failed_source_ids: tuple[str, ...]
    known_empty_source_ids: tuple[str, ...]
    searched_source_classes: tuple[SourceClass, ...]
    unsearched_source_classes: tuple[SourceClass, ...]


@dataclass(frozen=True, slots=True)
class RegionalCollectionBatch:
    opportunities: tuple[RegionalOpportunity, ...]
    exclusions: tuple[FactualExclusion, ...]
    sources: tuple[SourceCoverage, ...]
    coverage: SourceCoverageAssessment


class SourceRegistry:
    def __init__(self, registrations: tuple[SourceRegistration, ...]) -> None:
        ids = tuple(item.adapter.descriptor.source_id for item in registrations)
        if len(ids) != len(set(ids)):
            raise ValueError("Regional source IDs must be unique.")
        self._registrations = registrations

    @property
    def registrations(self) -> tuple[SourceRegistration, ...]:
        return self._registrations


async def collect_registered_sources(
    scope: ResearchScope,
    registry: SourceRegistry,
    *,
    observed_at: datetime,
) -> RegionalCollectionBatch:
    """Collect every enabled source independently without source-name branches.

    Expected source failures are captured as coverage state. Unexpected exceptions
    propagate so programming defects are not disguised as ordinary degradation.
    """
    if observed_at.utcoffset() is None:
        raise ValueError("Collection observation time must be timezone-aware.")
    if observed_at.astimezone(UTC) > scope.as_of.astimezone(UTC):
        raise ValueError("Collection observation cannot follow the scope as_of cutoff.")

    opportunities: list[RegionalOpportunity] = []
    exclusions: list[FactualExclusion] = []
    coverages: list[SourceCoverage] = []
    attempted: list[str] = []
    successful: list[str] = []
    failed: list[str] = []
    known_empty: list[str] = []

    enabled = [item for item in registry.registrations if item.enabled]
    disabled = [item for item in registry.registrations if not item.enabled]

    for registration in enabled:
        adapter = registration.adapter
        descriptor = adapter.descriptor
        if scope.region.region_id not in descriptor.region_ids:
            coverages.append(
                SourceCoverage(
                    source_id=descriptor.source_id,
                    channel=_coverage_channel(descriptor),
                    scope=descriptor.coverage_description,
                    status="not_attempted",
                    observed_at=None,
                    result_count=None,
                    failure_code="not_configured",
                )
            )
            continue

        attempted.append(descriptor.source_id)
        try:
            result = await adapter.collect(scope, observed_at=observed_at)
        except RegionalSourceFailure as exc:
            failed.append(descriptor.source_id)
            coverages.append(
                SourceCoverage(
                    source_id=descriptor.source_id,
                    channel=_coverage_channel(descriptor),
                    scope=descriptor.coverage_description,
                    status="failed",
                    observed_at=observed_at,
                    result_count=None,
                    failure_code=exc.failure_code,
                )
            )
            continue

        successful.append(descriptor.source_id)
        count = len(result.opportunities)
        if count == 0:
            known_empty.append(descriptor.source_id)
        opportunities.extend(result.opportunities)
        exclusions.extend(result.exclusions)
        coverages.append(
            SourceCoverage(
                source_id=descriptor.source_id,
                channel=_coverage_channel(descriptor),
                scope=descriptor.coverage_description,
                status="success",
                observed_at=observed_at,
                result_count=count,
                failure_code=None,
            )
        )

    attempted_ids = set(attempted)
    searched_classes = tuple(
        sorted(
            {
                item.adapter.descriptor.source_class
                for item in enabled
                if item.adapter.descriptor.source_id in attempted_ids
            }
        )
    )
    unsearched_classes = tuple(
        sorted(
            {
                item.adapter.descriptor.source_class
                for item in registry.registrations
                if item.adapter.descriptor.source_id not in attempted_ids
                and item.adapter.descriptor.source_class not in searched_classes
            }
        )
    )
    return RegionalCollectionBatch(
        opportunities=tuple(opportunities),
        exclusions=tuple(exclusions),
        sources=tuple(coverages),
        coverage=SourceCoverageAssessment(
            enabled_source_ids=tuple(item.adapter.descriptor.source_id for item in enabled),
            disabled_source_ids=tuple(item.adapter.descriptor.source_id for item in disabled),
            attempted_source_ids=tuple(attempted),
            successful_source_ids=tuple(successful),
            failed_source_ids=tuple(failed),
            known_empty_source_ids=tuple(known_empty),
            searched_source_classes=searched_classes,
            unsearched_source_classes=unsearched_classes,
        ),
    )


def _coverage_channel(
    descriptor: RegionalSourceDescriptor,
) -> Literal["fixed_feed", "hike_catalog", "weather"]:
    if "hike" in descriptor.opportunity_kinds:
        return "hike_catalog"
    if descriptor.source_class == "weather":
        return "weather"
    return "fixed_feed"
