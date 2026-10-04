from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from event_radar.collectors.regional_sources import CuratedHikeCatalogSource
from event_radar.models.regional import SONOMA_COUNTY, ResearchScope, WeekendWindow
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.shared.collection import SourceRegistration, SourceRegistry, collect_registered_sources
from event_radar.shared.hike_sources import HikeCatalogRegionalAdapter

PACIFIC = ZoneInfo("America/Los_Angeles")


def scope() -> ResearchScope:
    return ResearchScope(
        region=SONOMA_COUNTY,
        window=WeekendWindow(
            friday=datetime(2026, 10, 2).date(),
            timezone="America/Los_Angeles",
        ),
        research_policy_version="regional-v1",
        as_of=datetime(2026, 10, 2, 13, 0, tzinfo=PACIFIC),
    )


@pytest.mark.asyncio
async def test_curated_catalog_emits_only_sonoma_routes_without_personal_policy() -> None:
    catalog = HikeCatalogRepository().load()
    adapter = HikeCatalogRegionalAdapter(
        descriptor=CuratedHikeCatalogSource.descriptor,
        catalog=catalog,
    )
    result = await adapter.collect(
        scope(),
        observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
    )

    assert len(result.opportunities) == 25
    assert all(item.kind == "hike" for item in result.opportunities)
    assert all(item.location.county == "Sonoma County" for item in result.opportunities)
    assert all(item.occurrences == () for item in result.opportunities)
    assert all(item.semantics is None for item in result.opportunities)
    assert all(item.access_open.state == "unknown" for item in result.opportunities)

    wire = "\n".join(item.model_dump_json() for item in result.opportunities)
    for prohibited in (
        "solo_fit",
        "scenic_value",
        "drive_friction_from_santa_rosa",
        "preferred_months",
        "best_time_of_day",
        "minimum_reasonable_daylight_minutes",
    ):
        assert prohibited not in wire


@pytest.mark.asyncio
async def test_curated_hikes_participate_in_generic_registry_coverage() -> None:
    source = CuratedHikeCatalogSource()
    batch = await collect_registered_sources(
        scope(),
        SourceRegistry((SourceRegistration(source),)),
        observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
    )

    assert len(batch.opportunities) == 25
    assert batch.sources[0].source_id == "curated-sonoma-hikes"
    assert batch.sources[0].channel == "hike_catalog"
    assert batch.sources[0].result_count == 25
    assert batch.coverage.searched_source_classes == ("outdoor_catalog",)
    assert batch.duplicates_removed == 0
