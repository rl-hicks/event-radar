from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from event_radar.models.event import Event
from event_radar.services.event_deduplication import deduplicate_events

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def _event(
    *,
    source: str,
    title: str = "Night Market",
    city: str = "Santa Rosa",
    venue: str | None = None,
    hour: int = 18,
    description: str | None = None,
) -> Event:
    slug = source.lower().replace(" ", "-")
    return Event(
        source_name=source,
        source_id=f"{slug}-1",
        source_url=HttpUrl(f"https://example.com/{slug}/event"),
        title=title,
        description=description,
        start_time=datetime(2026, 8, 8, hour, tzinfo=PACIFIC_TIME),
        venue=venue,
        city=city,
    )


def test_deduplicate_merges_cross_source_match_and_preserves_provenance() -> None:
    first = _event(source="First Source", title="Night Market!")
    second = _event(
        source="Second Source",
        title="night market",
        venue="Courthouse Square",
        description="Food and music.",
    )

    result = deduplicate_events([first, second])

    assert result.duplicates_removed == 1
    assert len(result.events) == 1
    event = result.events[0]
    assert event.source_name == "Second Source"
    assert event.venue == "Courthouse Square"
    assert [source.source_name for source in event.alternate_sources] == ["First Source"]


def test_deduplicate_keeps_events_with_material_differences() -> None:
    baseline = _event(source="First Source", venue="Venue One")
    different_time = _event(source="Second Source", venue="Venue One", hour=19)
    different_city = _event(source="Third Source", venue="Venue One", city="Sebastopol")
    different_venue = _event(source="Fourth Source", venue="Venue Two")

    result = deduplicate_events([baseline, different_time, different_city, different_venue])

    assert result.duplicates_removed == 0
    assert len(result.events) == 4
