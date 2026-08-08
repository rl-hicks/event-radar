from datetime import UTC, datetime
from typing import cast

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl, ValidationError

from event_radar.collectors.base import EventCollector
from event_radar.models.event import Event

SOURCE_NAME = "Happening in Sonoma County"
EVENTS_ENDPOINT = "https://happeningsonomacounty.com/wp-json/tribe/events/v1/events"
PAGE_SIZE = 50


class HappeningSonomaCollectorError(RuntimeError):
    """Raised when Happening in Sonoma County event data cannot be collected."""


class HappeningSonomaCollector(EventCollector):
    """Collect occurrences from Happening in Sonoma County's public event API."""

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
        page = 1
        total_pages = 1

        while page <= total_pages:
            records, total_pages = await self._fetch_page(client, start, end, page)
            for record in records:
                event = parse_happening_sonoma_event(record)
                if event is not None and start <= event.start_time < end:
                    events.append(event)
            page += 1

        return sorted(events, key=lambda event: event.start_time)

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        start: datetime,
        end: datetime,
        page: int,
    ) -> tuple[list[dict[str, object]], int]:
        try:
            response = await client.get(
                EVENTS_ENDPOINT,
                params={
                    "start_date": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                    "end_date": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
                    "per_page": PAGE_SIZE,
                    "page": page,
                },
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HappeningSonomaCollectorError(
                f"Could not fetch Happening in Sonoma County events page {page}."
            ) from exc

        try:
            payload = cast(object, response.json())
        except ValueError as exc:
            raise HappeningSonomaCollectorError(
                "Happening in Sonoma County returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise HappeningSonomaCollectorError(
                "Happening in Sonoma County returned invalid event data."
            )

        typed_payload = cast(dict[str, object], payload)
        raw_events = typed_payload.get("events")
        raw_total_pages = typed_payload.get("total_pages")
        if not isinstance(raw_events, list) or not isinstance(raw_total_pages, int):
            raise HappeningSonomaCollectorError(
                "Happening in Sonoma County response was missing pagination or events."
            )

        records: list[dict[str, object]] = []
        for raw_event in raw_events:
            if isinstance(raw_event, dict):
                records.append(cast(dict[str, object], raw_event))

        return records, max(raw_total_pages, 0)


def parse_happening_sonoma_event(record: dict[str, object]) -> Event | None:
    """Normalize one occurrence returned by The Events Calendar API."""
    if record.get("all_day") is not False:
        return None

    source_id_value = record.get("id")
    title_value = record.get("title")
    url_value = record.get("url")
    if (
        not isinstance(source_id_value, (int, str))
        or isinstance(source_id_value, bool)
        or not isinstance(title_value, str)
        or not isinstance(url_value, str)
    ):
        return None

    start_time = _parse_utc_datetime(record.get("utc_start_date"))
    end_time = _parse_utc_datetime(record.get("utc_end_date"))
    if start_time is None:
        return None
    if end_time is not None and end_time <= start_time:
        end_time = None

    venue_value = record.get("venue")
    if not isinstance(venue_value, dict):
        return None
    venue_record = cast(dict[str, object], venue_value)

    city_value = venue_record.get("city")
    if not isinstance(city_value, str) or not city_value.strip():
        return None

    venue_name_value = venue_record.get("venue")
    venue_name = _html_text(venue_name_value)

    state = _first_nonempty_string(
        venue_record.get("state"),
        venue_record.get("stateprovince"),
        venue_record.get("province"),
    )
    description = _html_text(record.get("description"))

    try:
        return Event(
            source_name=SOURCE_NAME,
            source_id=str(source_id_value),
            source_url=HttpUrl(url_value),
            title=_html_text(title_value) or title_value.strip(),
            description=description,
            start_time=start_time,
            end_time=end_time,
            venue=venue_name,
            city=city_value.strip(),
            state=state or "CA",
            categories=_category_slugs(record.get("categories")),
        )
    except ValidationError:
        return None


def _parse_utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _first_nonempty_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _html_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return text or None


def _category_slugs(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()

    slugs: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        slug = cast(dict[str, object], item).get("slug")
        if isinstance(slug, str) and slug:
            slugs.add(slug)
    return slugs


def _validate_window(start: datetime, end: datetime) -> None:
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Event collection requires timezone-aware boundaries.")
    if end <= start:
        raise ValueError("Event collection end must be after start.")
