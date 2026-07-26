from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from event_radar.models.event import Event


def test_event_reports_free_price() -> None:
    event = Event(
        source_name="Test Source",
        source_url=HttpUrl("https://example.com/event"),
        title="Free Event",
        start_time=datetime(
            2026,
            7,
            31,
            18,
            0,
            tzinfo=ZoneInfo("America/Los_Angeles"),
        ),
        city="Santa Rosa",
        price_min=Decimal("0"),
    )

    assert event.is_free() is True
