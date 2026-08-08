from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from event_radar.collectors.sonoma_county import (
    SonomaCountyCollector,
    SonomaCountyCollectorError,
    parse_sonoma_county_listing,
)

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def _listing(date_value: str, rows: str) -> str:
    return f"""
    <table>
      <tr data-date="{date_value}"><th>{date_value}</th></tr>
      {rows}
    </table>
    """


def _event_row(
    *,
    title: str,
    time_text: str,
    city: str,
    slug: str,
) -> str:
    return f"""
    <tr>
      <td class="list-event-time">{time_text}</td>
      <td class="list-event-title">
        <a href="https://www.sonomacounty.com/events/{slug}/">
          <h3 class="event-title">{title}</h3>
          <small class="event-city">{city}, CA</small>
        </a>
      </td>
    </tr>
    """


def test_parse_listing_normalizes_timed_events_and_skips_unknown_times() -> None:
    listing = _listing(
        "2026-08-08",
        _event_row(
            title="Night Market",
            time_text="8:00pm - 1:00am",
            city="Santa Rosa",
            slug="night-market",
        )
        + _event_row(
            title="Schedule Pending",
            time_text="See Details",
            city="Sebastopol",
            slug="schedule-pending",
        ),
    )

    events = parse_sonoma_county_listing(listing)

    assert len(events) == 1
    event = events[0]
    assert event.source_name == "Sonoma County Tourism"
    assert event.source_id == "night-market:2026-08-08T20:00:00-07:00"
    assert str(event.source_url) == "https://www.sonomacounty.com/events/night-market/"
    assert event.title == "Night Market"
    assert event.start_time == datetime(2026, 8, 8, 20, 0, tzinfo=PACIFIC_TIME)
    assert event.end_time == datetime(2026, 8, 9, 1, 0, tzinfo=PACIFIC_TIME)
    assert event.city == "Santa Rosa"
    assert event.state == "CA"


@pytest.mark.asyncio
async def test_collect_queries_each_month_and_filters_to_requested_window() -> None:
    requested_months: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        month = request.url.params["_month"]
        requested_months.append(month)
        if month == "202608":
            listing = _listing(
                "2026-08-31",
                _event_row(
                    title="August Event",
                    time_text="6pm - 8pm",
                    city="Petaluma",
                    slug="august-event",
                ),
            )
        else:
            listing = _listing(
                "2026-09-01",
                _event_row(
                    title="September Event",
                    time_text="7:00pm - 9:00pm",
                    city="Sonoma",
                    slug="september-event",
                ),
            ) + _listing(
                "2026-09-02",
                _event_row(
                    title="Outside Window",
                    time_text="12am - 1am",
                    city="Windsor",
                    slug="outside-window",
                ),
            )
        return httpx.Response(200, json={"listing": listing})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = SonomaCountyCollector(user_agent="EventRadar/Test", client=client)
        events = await collector.collect(
            start=datetime(2026, 8, 31, tzinfo=PACIFIC_TIME),
            end=datetime(2026, 9, 2, tzinfo=PACIFIC_TIME),
        )

    assert requested_months == ["202608", "202609"]
    assert [event.title for event in events] == ["August Event", "September Event"]


@pytest.mark.asyncio
async def test_collect_rejects_invalid_source_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "value"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = SonomaCountyCollector(user_agent="EventRadar/Test", client=client)
        with pytest.raises(SonomaCountyCollectorError, match="did not contain"):
            await collector.collect(
                start=datetime(2026, 8, 8, tzinfo=PACIFIC_TIME),
                end=datetime(2026, 8, 9, tzinfo=PACIFIC_TIME),
            )
