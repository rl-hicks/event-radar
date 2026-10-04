from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from event_radar.collectors.regional_sources import (
    happening_sonoma_adapter,
    sonoma_county_tourism_adapter,
)
from event_radar.models.regional import ResearchScope, SONOMA_COUNTY, WeekendWindow
from event_radar.shared.collection import SourceRegistration, SourceRegistry, collect_registered_sources

PACIFIC = ZoneInfo("America/Los_Angeles")


def scope() -> ResearchScope:
    return ResearchScope(
        region=SONOMA_COUNTY,
        window=WeekendWindow(friday=datetime(2026, 10, 2).date(), timezone="America/Los_Angeles"),
        research_policy_version="regional-v1",
        as_of=datetime(2026, 10, 2, 13, 0, tzinfo=PACIFIC),
    )


@pytest.mark.asyncio
async def test_initial_sonoma_collectors_run_through_source_agnostic_registry() -> None:
    def tourism_handler(request: httpx.Request) -> httpx.Response:
        listing = """
        <table>
          <tr data-date="2026-10-03"><th>2026-10-03</th></tr>
          <tr>
            <td class="list-event-time">2pm - 4pm</td>
            <td class="list-event-title">
              <a href="https://www.sonomacounty.com/events/synthetic-tourism/">
                <h3 class="event-title">Synthetic Tourism Event</h3>
                <small class="event-city">Petaluma, CA</small>
              </a>
            </td>
          </tr>
        </table>
        """
        return httpx.Response(200, json={"listing": listing})

    def happening_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "id": 101,
                        "url": "https://happeningsonomacounty.com/event/synthetic-happening/",
                        "title": "Synthetic Happening Event",
                        "description": "<p>Public community event.</p>",
                        "all_day": False,
                        "utc_start_date": "2026-10-03 21:00:00",
                        "utc_end_date": "2026-10-03 23:00:00",
                        "venue": {
                            "venue": "Synthetic Hall",
                            "city": "Santa Rosa",
                            "state": "CA",
                        },
                        "categories": [{"slug": "community"}],
                        "cost": "",
                        "cost_details": {},
                    }
                ],
                "total_pages": 1,
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(tourism_handler)) as tourism_client,
        httpx.AsyncClient(transport=httpx.MockTransport(happening_handler)) as happening_client,
    ):
        registry = SourceRegistry(
            (
                SourceRegistration(
                    sonoma_county_tourism_adapter(
                        user_agent="EventRadar/Test",
                        client=tourism_client,
                    )
                ),
                SourceRegistration(
                    happening_sonoma_adapter(
                        user_agent="EventRadar/Test",
                        client=happening_client,
                    )
                ),
            )
        )
        batch = await collect_registered_sources(
            scope(),
            registry,
            observed_at=datetime(2026, 10, 2, 12, 30, tzinfo=PACIFIC),
        )

    assert {item.title for item in batch.opportunities} == {
        "Synthetic Tourism Event",
        "Synthetic Happening Event",
    }
    assert batch.coverage.successful_source_ids == (
        "sonoma-county-tourism",
        "happening-sonoma-county",
    )
    assert all(source.status == "success" for source in batch.sources)
    assert all(opportunity.semantics is None for opportunity in batch.opportunities)
