from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from event_radar.collectors.happening_sonoma import (
    HappeningSonomaCollector,
    HappeningSonomaCollectorError,
    parse_happening_sonoma_event,
)

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def _event_record(
    *,
    event_id: int,
    title: str,
    start_utc: str,
    end_utc: str,
    city: str | None = "Santa Rosa",
    all_day: bool = False,
) -> dict[str, object]:
    venue: dict[str, object] = {"venue": "Example Hall", "state": "CA"}
    if city is not None:
        venue["city"] = city
    return {
        "id": event_id,
        "url": f"https://happeningsonomacounty.com/event/example-{event_id}/",
        "title": title,
        "description": "<p>A local <strong>community</strong> event.</p>",
        "all_day": all_day,
        "utc_start_date": start_utc,
        "utc_end_date": end_utc,
        "venue": venue,
        "categories": [{"slug": "live-music"}],
    }


def test_parse_event_normalizes_api_record() -> None:
    event = parse_happening_sonoma_event(
        _event_record(
            event_id=72461,
            title="Summer Music &#8211; Live",
            start_utc="2026-08-08 01:00:00",
            end_utc="2026-08-08 04:00:00",
            city="Sebastopol",
        )
    )

    assert event is not None
    assert event.source_name == "Happening in Sonoma County"
    assert event.source_id == "72461"
    assert str(event.source_url) == "https://happeningsonomacounty.com/event/example-72461/"
    assert event.title == "Summer Music – Live"
    assert event.description == "A local community event."
    assert event.start_time == datetime(2026, 8, 8, 1, 0, tzinfo=ZoneInfo("UTC"))
    assert event.end_time == datetime(2026, 8, 8, 4, 0, tzinfo=ZoneInfo("UTC"))
    assert event.venue == "Example Hall"
    assert event.city == "Sebastopol"
    assert event.categories == {"live-music"}


def test_parse_event_skips_all_day_or_locationless_records() -> None:
    all_day = _event_record(
        event_id=1,
        title="All Day Event",
        start_utc="2026-08-08 07:00:00",
        end_utc="2026-08-09 06:59:59",
        all_day=True,
    )
    locationless = _event_record(
        event_id=2,
        title="Location Pending",
        start_utc="2026-08-08 17:00:00",
        end_utc="2026-08-08 18:00:00",
        city=None,
    )

    assert parse_happening_sonoma_event(all_day) is None
    assert parse_happening_sonoma_event(locationless) is None


def test_parse_event_discards_nonpositive_end_without_inventing_one() -> None:
    event = parse_happening_sonoma_event(
        _event_record(
            event_id=3,
            title="Late Night Event",
            start_utc="2026-08-09 04:00:00",
            end_utc="2026-08-09 04:00:00",
        )
    )

    assert event is not None
    assert event.start_time == datetime(2026, 8, 9, 4, 0, tzinfo=ZoneInfo("UTC"))
    assert event.end_time is None


@pytest.mark.asyncio
async def test_collect_paginates_and_applies_exclusive_end_filter() -> None:
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requested_pages.append(page)
        if page == 1:
            events = [
                _event_record(
                    event_id=10,
                    title="Saturday Event",
                    start_utc="2026-08-08 17:00:00",
                    end_utc="2026-08-08 18:00:00",
                )
            ]
        else:
            events = [
                _event_record(
                    event_id=11,
                    title="Boundary Event",
                    start_utc="2026-08-10 07:00:00",
                    end_utc="2026-08-10 08:00:00",
                )
            ]
        return httpx.Response(200, json={"events": events, "total_pages": 2})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = HappeningSonomaCollector(user_agent="EventRadar/Test", client=client)
        events = await collector.collect(
            start=datetime(2026, 8, 8, tzinfo=PACIFIC_TIME),
            end=datetime(2026, 8, 10, tzinfo=PACIFIC_TIME),
        )

    assert requested_pages == [1, 2]
    assert [event.title for event in events] == ["Saturday Event"]


@pytest.mark.asyncio
async def test_collect_preserves_separate_occurrences_that_reuse_an_event_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        events = [
            _event_record(
                event_id=20,
                title="Recurring Event",
                start_utc="2026-08-08 17:00:00",
                end_utc="2026-08-08 18:00:00",
            ),
            _event_record(
                event_id=20,
                title="Recurring Event",
                start_utc="2026-08-09 17:00:00",
                end_utc="2026-08-09 18:00:00",
            ),
        ]
        return httpx.Response(200, json={"events": events, "total_pages": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = HappeningSonomaCollector(user_agent="EventRadar/Test", client=client)
        events = await collector.collect(
            start=datetime(2026, 8, 8, tzinfo=PACIFIC_TIME),
            end=datetime(2026, 8, 10, tzinfo=PACIFIC_TIME),
        )

    assert len(events) == 2
    assert events[0].source_id == events[1].source_id == "20"
    assert events[0].start_time != events[1].start_time


@pytest.mark.asyncio
async def test_collect_rejects_invalid_source_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "value"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = HappeningSonomaCollector(user_agent="EventRadar/Test", client=client)
        with pytest.raises(HappeningSonomaCollectorError, match="missing pagination"):
            await collector.collect(
                start=datetime(2026, 8, 8, tzinfo=PACIFIC_TIME),
                end=datetime(2026, 8, 9, tzinfo=PACIFIC_TIME),
            )
