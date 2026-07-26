from datetime import datetime
from decimal import Decimal

from pydantic import HttpUrl

from event_radar.collectors.base import EventCollector
from event_radar.models.event import Event


class ExampleCollector(EventCollector):
    """Temporary collector used to test the end-to-end pipeline."""

    async def collect(
        self,
        start: datetime,
        end: datetime,
    ) -> list[Event]:
        return [
            Event(
                source_name="Example Events",
                source_id="example-001",
                source_url=HttpUrl("https://example.com/events/example-001"),
                title="Friday Night Live Music",
                description="A temporary event used to test Event Radar.",
                start_time=start,
                end_time=None,
                venue="Example Venue",
                city="Santa Rosa",
                categories={"live_music", "social"},
                price_min=Decimal("10"),
                price_max=Decimal("10"),
            )
        ]
