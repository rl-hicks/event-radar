from decimal import Decimal

from event_radar.collectors.happening_sonoma import parse_happening_sonoma_event


def test_happening_collector_resolves_structured_free_admission_conflict() -> None:
    record: dict[str, object] = {
        "id": 80423,
        "url": "https://happeningsonomacounty.com/event/haunted-tour/",
        "title": "Haunted Wine Tour & Tasting",
        "description": "<p>Tickets are $75 per guest and $60 for members.</p>",
        "all_day": False,
        "utc_start_date": "2026-09-27 01:00:00",
        "utc_end_date": "2026-09-27 03:00:00",
        "venue": {"venue": "Winery", "city": "Santa Rosa", "state": "CA"},
        "categories": [{"slug": "tour"}],
        "cost": "Free",
        "cost_details": {"currency_code": "USD", "values": [0]},
    }

    event = parse_happening_sonoma_event(record)

    assert event is not None
    assert event.price_min == Decimal("60")
    assert event.price_max == Decimal("75")
    assert event.price_conflict is True
    assert event.price_details is not None
    assert "conflicts with structured" in event.price_details
