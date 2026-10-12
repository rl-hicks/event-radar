from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from event_radar.models.regional import RegionalWeekendUniverse
from event_radar.shared.collection import (
    RegionalSourceDescriptor,
    RegionalSourceFailure,
    RegionalSourceResult,
    SourceRegistration,
    SourceRegistry,
    collect_registered_sources,
)

FIXTURE = Path(__file__).parent / "fixtures/regional/universe.json"
PACIFIC = ZoneInfo("America/Los_Angeles")


def fixture_universe() -> RegionalWeekendUniverse:
    return RegionalWeekendUniverse.model_validate_json(FIXTURE.read_text())


class FakeAdapter:
    def __init__(
        self,
        source_id: str,
        *,
        opportunities=(),
        source_class="regional_calendar",
        failure=None,
    ) -> None:
        self.descriptor = RegionalSourceDescriptor(
            source_id=source_id,
            source_class=source_class,
            mechanism="api",
            coverage_description=f"Synthetic coverage for {source_id}",
            opportunity_kinds=("event",),
        )
        self._opportunities = tuple(opportunities)
        self._failure = failure
        self.calls = 0

    async def collect(self, scope, *, observed_at):
        self.calls += 1
        if self._failure is not None:
            raise RegionalSourceFailure(self._failure)
        return RegionalSourceResult(opportunities=self._opportunities)


@pytest.mark.asyncio
async def test_registry_runs_added_adapter_without_orchestration_changes() -> None:
    universe = fixture_universe()
    first = FakeAdapter("first", opportunities=(universe.opportunities[0],))
    second = FakeAdapter(
        "second",
        opportunities=(universe.opportunities[1],),
        source_class="other",
    )
    registry = SourceRegistry((SourceRegistration(first), SourceRegistration(second)))
    batch = await collect_registered_sources(
        universe.scope,
        registry,
        observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
    )
    assert [o.opportunity_id for o in batch.opportunities] == [
        "community-workshop",
        "synthetic-ridge-route",
    ]
    assert first.calls == second.calls == 1
    assert batch.coverage.successful_source_ids == ("first", "second")
    assert set(batch.coverage.searched_source_classes) == {"regional_calendar", "other"}


def test_registry_rejects_duplicate_source_ids() -> None:
    first = FakeAdapter("same")
    second = FakeAdapter("same")
    with pytest.raises(ValueError, match="unique"):
        SourceRegistry((SourceRegistration(first), SourceRegistration(second)))


@pytest.mark.asyncio
async def test_expected_source_failure_degrades_without_erasing_success() -> None:
    universe = fixture_universe()
    good = FakeAdapter("good", opportunities=(universe.opportunities[0],))
    bad = FakeAdapter("bad", failure="timeout")
    batch = await collect_registered_sources(
        universe.scope,
        SourceRegistry((SourceRegistration(good), SourceRegistration(bad))),
        observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
    )
    assert len(batch.opportunities) == 1
    assert batch.coverage.successful_source_ids == ("good",)
    assert batch.coverage.failed_source_ids == ("bad",)
    assert batch.sources[1].status == "failed"
    assert batch.sources[1].failure_code == "timeout"


@pytest.mark.asyncio
async def test_disabled_and_known_empty_sources_remain_distinct() -> None:
    universe = fixture_universe()
    empty = FakeAdapter("empty")
    disabled = FakeAdapter("disabled", source_class="community_calendar")
    batch = await collect_registered_sources(
        universe.scope,
        SourceRegistry(
            (
                SourceRegistration(empty),
                SourceRegistration(disabled, enabled=False),
            )
        ),
        observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
    )
    assert batch.coverage.known_empty_source_ids == ("empty",)
    assert batch.coverage.disabled_source_ids == ("disabled",)
    assert batch.coverage.unsearched_source_classes == ("community_calendar",)
    assert disabled.calls == 0


@pytest.mark.asyncio
async def test_unexpected_adapter_error_is_not_masked() -> None:
    universe = fixture_universe()

    class Broken(FakeAdapter):
        async def collect(self, scope, *, observed_at):
            raise AssertionError("programming defect")

    with pytest.raises(AssertionError, match="programming defect"):
        await collect_registered_sources(
            universe.scope,
            SourceRegistry((SourceRegistration(Broken("broken")),)),
            observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
        )
