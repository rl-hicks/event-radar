import asyncio
from datetime import UTC, datetime
from typing import cast

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl, ValidationError

from event_radar.collectors.base import EventCollector
from event_radar.models.event import Event
from event_radar.services.event_price import normalize_event_price

SOURCE_NAME = "Happening in Sonoma County"
EVENTS_ENDPOINT = "https://happeningsonomacounty.com/wp-json/tribe/events/v1/events"
PAGE_SIZE = 50
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = (0.25, 0.75)
MAX_RETRY_AFTER_SECONDS = 5.0


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
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff_seconds: tuple[float, ...] = DEFAULT_RETRY_BACKOFF_SECONDS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("Happening Sonoma max_attempts must be at least 1.")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

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
        params: dict[str, str | int] = {
            "start_date": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "per_page": PAGE_SIZE,
            "page": page,
        }
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await client.get(
                    EVENTS_ENDPOINT,
                    params=params,
                    headers={"User-Agent": self._user_agent},
                    timeout=self._timeout_seconds,
                    follow_redirects=True,
                )
            except httpx.RequestError as exc:
                detail = _network_diagnostics(exc, page)
                if attempt < self._max_attempts:
                    await self._wait_before_retry(attempt, detail)
                    continue
                raise HappeningSonomaCollectorError(
                    "Happening in Sonoma County network failure after "
                    f"{attempt} attempt(s) ({detail})."
                ) from exc

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = _response_diagnostics(response, page, type(exc).__name__)
                if _is_transient_status(response.status_code) and attempt < self._max_attempts:
                    await self._wait_before_retry(attempt, detail, response=response)
                    continue
                raise HappeningSonomaCollectorError(
                    "Happening in Sonoma County HTTP status failure after "
                    f"{attempt} attempt(s) ({detail})."
                ) from exc

            try:
                payload = cast(object, response.json())
            except ValueError as exc:
                detail = _response_diagnostics(response, page, type(exc).__name__)
                if attempt < self._max_attempts:
                    await self._wait_before_retry(attempt, detail, response=response)
                    continue
                raise HappeningSonomaCollectorError(
                    "Happening in Sonoma County returned invalid JSON after "
                    f"{attempt} attempt(s) ({detail})."
                ) from exc

            try:
                return _parse_page_payload(payload)
            except ValueError as exc:
                detail = _response_diagnostics(response, page, type(exc).__name__)
                if attempt < self._max_attempts:
                    await self._wait_before_retry(attempt, detail, response=response)
                    continue
                raise HappeningSonomaCollectorError(
                    "Happening in Sonoma County returned an invalid schema/payload after "
                    f"{attempt} attempt(s): {exc} ({detail})."
                ) from exc

        raise AssertionError("Happening Sonoma retry loop exited unexpectedly.")

    async def _wait_before_retry(
        self,
        attempt: int,
        detail: str,
        *,
        response: httpx.Response | None = None,
    ) -> None:
        delay = _retry_delay(
            attempt,
            self._retry_backoff_seconds,
            response.headers.get("Retry-After") if response is not None else None,
        )
        print(
            "Happening in Sonoma County transient fetch failure; "
            f"retrying after {delay:.2f}s ({detail})."
        )
        if delay > 0:
            await asyncio.sleep(delay)


def _parse_page_payload(payload: object) -> tuple[list[dict[str, object]], int]:
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")

    typed_payload = cast(dict[str, object], payload)
    raw_events = typed_payload.get("events")
    raw_total_pages = typed_payload.get("total_pages")
    if not isinstance(raw_events, list) or not isinstance(raw_total_pages, int):
        raise ValueError("response was missing pagination or events")

    records = [
        cast(dict[str, object], raw_event)
        for raw_event in raw_events
        if isinstance(raw_event, dict)
    ]
    return records, max(raw_total_pages, 0)


def _is_transient_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _response_diagnostics(
    response: httpx.Response,
    page: int,
    exception_class: str,
) -> str:
    content_type = response.headers.get("Content-Type", "unknown")
    retry_after = response.headers.get("Retry-After")
    values = [
        f"page={page}",
        f"url={response.request.url}",
        f"status={response.status_code}",
        f"content_type={content_type!r}",
        f"bytes={len(response.content)}",
        f"exception={exception_class}",
    ]
    if retry_after is not None:
        values.append(f"retry_after={retry_after!r}")
    return ", ".join(values)


def _network_diagnostics(exc: httpx.RequestError, page: int) -> str:
    return (
        f"page={page}, url={exc.request.url}, status=unavailable, "
        f"content_type=unavailable, bytes=unavailable, exception={type(exc).__name__}"
    )


def _retry_delay(
    attempt: int,
    backoff_seconds: tuple[float, ...],
    retry_after: str | None,
) -> float:
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0.0), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass
    if not backoff_seconds:
        return 0.0
    return max(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)], 0.0)


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
    price = normalize_event_price(
        structured_price=_first_nonempty_string(
            record.get("cost"),
            record.get("ticket_price"),
            record.get("price"),
        ),
        structured_details=record.get("cost_details"),
        description=description,
    )

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
            price_min=price.minimum if price is not None else None,
            price_max=price.maximum if price is not None else None,
            price_currency=price.currency if price is not None else None,
            price_details=price.source_text if price is not None else None,
            price_conflict=price.conflict if price is not None else False,
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
