from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import HttpUrl

from event_radar.models.event import Event
from event_radar.models.regional import RegionalWeekendUniverse
from event_radar.shared.collection import RegionalSourceDescriptor, RegionalSourceFailure
from event_radar.shared.event_sources import EventCollectorRegionalAdapter

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PACIFIC = ZoneInfo("America/Los_Angeles")


def scope():
    return RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text()).scope


class FakeCollector:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error
        self.calls = []

    async def collect(self, start, end):
        self.calls.append((start, end))
        if self.error:
            raise self.error
        return self.events


@pytest.mark.asyncio
async def test_event_collector_adapter_normalizes_public_facts_without_personal_policy() -> None:
    event = Event(
        source_name="Synthetic",
        source_id="42",
        source_url=HttpUrl("https://www.sonomacounty.com/events/synthetic/"),
        title="Synthetic Workshop",
        description="A guided public workshop.",
        start_time=datetime(2026, 10, 3, 14, 0, tzinfo=PACIFIC),
        end_time=datetime(2026, 10, 3, 16, 0, tzinfo=PACIFIC),
        venue="Community Hall",
        city="Petaluma",
        categories={"workshop"},
        price_min=Decimal("15"),
        price_max=Decimal("15"),
        price_currency="USD",
        price_details="$15",
    )
    collector = FakeCollector([event])
    adapter = EventCollectorRegionalAdapter(
        descriptor=RegionalSourceDescriptor(
            source_id="synthetic-source",
            source_class="regional_calendar",
            mechanism="api",
            coverage_description="Synthetic county calendar",
            opportunity_kinds=("event",),
        ),
        collector=collector,
    )
    result = await adapter.collect(
        scope(),
        observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
    )
    opportunity = result.opportunities[0]
    assert opportunity.title == "Synthetic Workshop"
    assert opportunity.semantics is None
    assert opportunity.categories.value == ("workshop",)
    assert opportunity.occurrences[0].price.quotes[0].minimum == 15
    assert {u.kind for u in opportunity.unknowns} >= {
        "availability",
        "semantic_analysis",
    }
    assert collector.calls == [(scope().window.start, scope().window.end)]


@pytest.mark.asyncio
async def test_expected_legacy_collector_failure_becomes_bounded_source_failure() -> None:
    class Expected(RuntimeError):
        pass

    collector = FakeCollector(error=Expected("offline"))
    adapter = EventCollectorRegionalAdapter(
        descriptor=RegionalSourceDescriptor(
            source_id="synthetic-source",
            source_class="regional_calendar",
            mechanism="api",
            coverage_description="Synthetic county calendar",
            opportunity_kinds=("event",),
        ),
        collector=collector,
        expected_failures=(Expected,),
    )
    with pytest.raises(RegionalSourceFailure) as caught:
        await adapter.collect(
            scope(),
            observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
        )
    assert caught.value.failure_code == "unavailable"
