import re
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from typing import cast
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from event_radar.collectors.base import EventCollector
from event_radar.models.event import Event

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
SOURCE_NAME = "Sonoma County Tourism"
EVENTS_ENDPOINT = "https://www.sonomacounty.com/wp-admin/admin-ajax.php"

_TIME_RANGE_PATTERN = re.compile(
    r"^(?P<start>\d{1,2}(?::\d{2})?\s*[ap]m)"
    r"(?:\s*-\s*(?P<end>\d{1,2}(?::\d{2})?\s*[ap]m))?$",
    re.IGNORECASE,
)


class SonomaCountyCollectorError(RuntimeError):
    """Raised when Sonoma County Tourism event data cannot be collected."""


class SonomaCountyCollector(EventCollector):
    """Collect public events from the Sonoma County Tourism calendar."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def collect(self, start: datetime, end: datetime) -> list[Event]:
        _validate_window(start, end)

        if self._client is not None:
            return await self._collect_with_client(self._client, start, end)

        async with httpx.AsyncClient() as client:
            return await self._collect_with_client(client, start, end)

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        start: datetime,
        end: datetime,
    ) -> list[Event]:
        events: list[Event] = []

        for month in _months_in_window(start, end):
            listing = await self._fetch_month(client, month)
            events.extend(parse_sonoma_county_listing(listing))

        return sorted(
            (event for event in events if start <= event.start_time < end),
            key=lambda event: event.start_time,
        )

    async def _fetch_month(self, client: httpx.AsyncClient, month: str) -> str:
        try:
            response = await client.get(
                EVENTS_ENDPOINT,
                params={
                    "action": "dataengine-events",
                    "_view": "month",
                    "_supertag": "",
                    "_city": "",
                    "_type": "",
                    "_month": month,
                },
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SonomaCountyCollectorError(
                f"Could not fetch Sonoma County Tourism events for {month}."
            ) from exc

        payload = cast(object, response.json())
        if not isinstance(payload, dict):
            raise SonomaCountyCollectorError("Sonoma County Tourism returned invalid event data.")

        listing = cast(dict[str, object], payload).get("listing")
        if not isinstance(listing, str):
            raise SonomaCountyCollectorError(
                "Sonoma County Tourism response did not contain an event listing."
            )

        return listing


def parse_sonoma_county_listing(listing_html: str) -> list[Event]:
    """Normalize the calendar's HTML table fragment into event occurrences."""
    soup = BeautifulSoup(listing_html, "html.parser")
    current_date: date | None = None
    events: list[Event] = []

    for row in soup.select("tr"):
        date_value = row.get("data-date")
        if isinstance(date_value, str):
            try:
                current_date = date.fromisoformat(date_value)
            except ValueError:
                current_date = None
            continue

        if current_date is None:
            continue

        event = _parse_event_row(row, current_date)
        if event is not None:
            events.append(event)

    return events


def _parse_event_row(row: Tag, event_date: date) -> Event | None:
    time_element = row.select_one(".list-event-time")
    link = row.select_one(".list-event-title a[href]")
    title_element = row.select_one(".event-title")
    city_element = row.select_one(".event-city")

    if time_element is None or link is None or title_element is None or city_element is None:
        return None

    parsed_times = _parse_time_range(time_element.get_text(" ", strip=True))
    href = link.get("href")
    if parsed_times is None or not isinstance(href, str):
        return None

    city, state = _parse_city(city_element.get_text(" ", strip=True))
    if not city:
        return None

    start_clock, end_clock = parsed_times
    start_time = datetime.combine(event_date, start_clock, tzinfo=PACIFIC_TIME)
    end_time = (
        datetime.combine(event_date, end_clock, tzinfo=PACIFIC_TIME)
        if end_clock is not None
        else None
    )
    if end_time is not None and end_time <= start_time:
        end_time += timedelta(days=1)

    return Event(
        source_name=SOURCE_NAME,
        source_id=_source_id(href, start_time),
        source_url=HttpUrl(href),
        title=title_element.get_text(" ", strip=True),
        start_time=start_time,
        end_time=end_time,
        city=city,
        state=state,
    )


def _parse_time_range(value: str) -> tuple[time, time | None] | None:
    match = _TIME_RANGE_PATTERN.fullmatch(value.strip())
    if match is None:
        return None

    start = _parse_clock(match.group("start"))
    end_value = match.group("end")
    end = _parse_clock(end_value) if end_value is not None else None
    return start, end


def _parse_clock(value: str) -> time:
    normalized = value.lower().replace(" ", "")
    time_format = "%I:%M%p" if ":" in normalized else "%I%p"
    return datetime.strptime(normalized, time_format).time()


def _parse_city(value: str) -> tuple[str, str]:
    city, separator, state = value.rpartition(",")
    if not separator:
        return value.strip(), "CA"
    return city.strip(), state.strip() or "CA"


def _source_id(url: str, start_time: datetime) -> str:
    slug = urlparse(url).path.rstrip("/").rsplit("/", maxsplit=1)[-1]
    return f"{slug}:{start_time.isoformat()}"


def _months_in_window(start: datetime, end: datetime) -> Iterator[str]:
    start_local = start.astimezone(PACIFIC_TIME)
    last_local = (end - timedelta(microseconds=1)).astimezone(PACIFIC_TIME)
    current = date(start_local.year, start_local.month, 1)
    last = date(last_local.year, last_local.month, 1)

    while current <= last:
        yield current.strftime("%Y%m")
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _validate_window(start: datetime, end: datetime) -> None:
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Event collection requires timezone-aware boundaries.")
    if end <= start:
        raise ValueError("Event collection end must be after start.")
