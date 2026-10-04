"""Adapt a curated hike catalog into neutral regional opportunities."""

from __future__ import annotations

import hashlib
from datetime import date, datetime

from event_radar.models.hike import Hike, HikeCatalog
from event_radar.models.regional import (
    ImportantUnknown,
    Location,
    Observation,
    RegionalOpportunity,
    ResearchScope,
    RouteFacts,
    SourceEvidence,
)
from event_radar.shared.collection import RegionalSourceDescriptor, RegionalSourceResult


class HikeCatalogRegionalAdapter:
    def __init__(
        self,
        *,
        descriptor: RegionalSourceDescriptor,
        catalog: HikeCatalog,
    ) -> None:
        if descriptor.opportunity_kinds != ("hike",):
            raise ValueError("Hike catalog adapters must declare only hike opportunities.")
        self.descriptor = descriptor
        self._catalog = catalog

    async def collect(
        self,
        scope: ResearchScope,
        *,
        observed_at: datetime,
    ) -> RegionalSourceResult:
        cutoff = self._catalog.catalog_metadata.research_cutoff_date
        opportunities = tuple(
            hike_to_regional_opportunity(
                hike,
                source_id=self.descriptor.source_id,
                scope=scope,
                observed_at=observed_at,
                research_cutoff=cutoff,
            )
            for hike in self._catalog.hikes
            if hike.county == scope.region.county
        )
        return RegionalSourceResult(opportunities=opportunities)


def hike_to_regional_opportunity(
    hike: Hike,
    *,
    source_id: str,
    scope: ResearchScope,
    observed_at: datetime,
    research_cutoff: date,
) -> RegionalOpportunity:
    if hike.county != scope.region.county:
        raise ValueError("Hike is outside the regional research boundary.")

    evidence_id = _stable_id("evidence", source_id, hike.id)
    opportunity_id = _stable_id("hike", source_id, hike.id)
    evidence = SourceEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        url=hike.official_source_url,
        source_record_id=hike.id,
        observed_at=observed_at,
        published_at=None,
        claims=("existence", "location", "route", "description"),
        summary=(
            f"Curated route record for {hike.name}; "
            f"catalog research cutoff {research_cutoff.isoformat()}."
        ),
        confidence=hike.data_quality.overall_confidence.value,
        occurrence_start=None,
        occurrence_end=None,
    )
    location = Location(
        country_code="US",
        subdivision_code="CA",
        county=hike.county,
        city=hike.nearest_city,
        venue=hike.trailhead_name,
        evidence_ids=(evidence_id,),
    )
    unknowns = [
        ImportantUnknown(
            kind="access",
            detail="Current access and trail conditions require fresh verification.",
        ),
        ImportantUnknown(
            kind="semantic_analysis",
            detail="Shared semantic enrichment has not run yet.",
        ),
    ]
    unknowns.extend(
        ImportantUnknown(kind="route", detail=item)
        for item in hike.data_quality.uncertainties
        if item.strip()
    )
    route_description = (
        f"{hike.route_type.value} route from {hike.route_start} to {hike.route_end}; "
        f"{hike.distance_miles:g} miles and {hike.elevation_gain_ft} ft elevation gain."
    )
    return RegionalOpportunity(
        opportunity_id=opportunity_id,
        kind="hike",
        title=hike.name,
        location=location,
        evidence=(evidence,),
        semantics=None,
        categories=Observation[tuple[str, ...]](
            state="known",
            value=tuple(sorted(set(hike.setting))),
            evidence_ids=(evidence_id,),
        ),
        occurrences=(),
        route=RouteFacts(
            distance_miles=str(hike.distance_miles),
            elevation_gain_ft=hike.elevation_gain_ft,
            route_description=route_description,
            evidence_ids=(evidence_id,),
        ),
        access_open=Observation[bool](
            state="unknown",
            value=None,
            evidence_ids=(),
        ),
        unknowns=tuple(unknowns),
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}-{digest}"
