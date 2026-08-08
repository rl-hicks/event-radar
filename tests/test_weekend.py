from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from event_radar.services.weekend import upcoming_weekend_window

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def test_weekend_window_on_thursday_starts_friday() -> None:
    start, end = upcoming_weekend_window(datetime(2026, 8, 6, 18, 30, tzinfo=PACIFIC_TIME))

    assert start == datetime(2026, 8, 7, tzinfo=PACIFIC_TIME)
    assert end == datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)


def test_weekend_window_on_saturday_excludes_elapsed_time() -> None:
    now = datetime(2026, 8, 8, 14, 30, tzinfo=PACIFIC_TIME)

    start, end = upcoming_weekend_window(now)

    assert start == now
    assert end == datetime(2026, 8, 10, tzinfo=PACIFIC_TIME)


def test_weekend_window_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        upcoming_weekend_window(datetime(2026, 8, 6, 18, 30))
