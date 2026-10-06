"""Explicit source registration for the initial Sonoma County regional run.

Source-specific construction belongs here; shared orchestration consumes only the
RegionalSourceAdapter contract and never branches on these source names.
"""

from datetime import datetime

import httpx

from event_radar.collectors.happening_sonoma import (
    HappeningSonomaCollector,
    HappeningSonomaCollectorError,
)
from event_radar.collectors.sonoma_county import (
    SonomaCountyCollector,
    SonomaCountyCollectorError,
)
from event_radar.models.regional import ResearchScope
from event_radar.services.hike_catalog import HikeCatalogError, HikeCatalogRepository
from event_radar.shared.collection import (
    RegionalSourceDescriptor,
    RegionalSourceFailure,
    RegionalSourceResult,
    SourceRegistration,
    SourceRegistry,
)
from event_radar.shared.event_sources import EventCollectorRegionalAdapter
from event_radar.shared.hike_sources import HikeCatalogRegionalAdapter


def sonoma_county_tourism_adapter(
    *,
    user_agent: str,
    timeout_seconds: float = 20.0,
    client: httpx.AsyncClient | None = None,
) -> EventCollectorRegionalAdapter:
    return EventCollectorRegionalAdapter(
        descriptor=RegionalSourceDescriptor(
            source_id="sonoma-county-tourism",
            source_class="regional_calendar",
            mechanism="html",
            coverage_description=(
                "Sonoma County Tourism public events calendar for the requested weekend."
            ),
            opportunity_kinds=("event",),
        ),
        collector=SonomaCountyCollector(
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            client=client,
        ),
        expected_failures=(SonomaCountyCollectorError,),
    )


def happening_sonoma_adapter(
    *,
    user_agent: str,
    timeout_seconds: float = 20.0,
    client: httpx.AsyncClient | None = None,
) -> EventCollectorRegionalAdapter:
    return EventCollectorRegionalAdapter(
        descriptor=RegionalSourceDescriptor(
            source_id="happening-sonoma-county",
            source_class="regional_calendar",
            mechanism="api",
            coverage_description=(
                "Happening in Sonoma County public event API for the requested weekend."
            ),
            opportunity_kinds=("event",),
        ),
        collector=HappeningSonomaCollector(
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            client=client,
        ),
        expected_failures=(HappeningSonomaCollectorError,),
    )


class CuratedHikeCatalogSource:
    descriptor = RegionalSourceDescriptor(
        source_id="curated-sonoma-hikes",
        source_class="outdoor_catalog",
        mechanism="catalog",
        coverage_description=(
            "Curated hike catalog routes explicitly classified in Sonoma County."
        ),
        opportunity_kinds=("hike",),
    )

    def __init__(self, repository: HikeCatalogRepository | None = None) -> None:
        self._repository = repository or HikeCatalogRepository()

    async def collect(
        self,
        scope: ResearchScope,
        *,
        observed_at: datetime,
    ) -> RegionalSourceResult:
        try:
            catalog = self._repository.load()
        except HikeCatalogError as exc:
            raise RegionalSourceFailure("invalid_response") from exc
        return await HikeCatalogRegionalAdapter(
            descriptor=self.descriptor,
            catalog=catalog,
        ).collect(scope, observed_at=observed_at)


def default_sonoma_source_registry(
    *,
    user_agent: str,
    timeout_seconds: float = 20.0,
    hike_repository: HikeCatalogRepository | None = None,
) -> SourceRegistry:
    """Initial registry composition; adding a source means registering an adapter."""
    return SourceRegistry(
        (
            SourceRegistration(
                sonoma_county_tourism_adapter(
                    user_agent=user_agent,
                    timeout_seconds=timeout_seconds,
                )
            ),
            SourceRegistration(
                happening_sonoma_adapter(
                    user_agent=user_agent,
                    timeout_seconds=timeout_seconds,
                )
            ),
            SourceRegistration(CuratedHikeCatalogSource(hike_repository)),
        )
    )
