from decimal import Decimal

import pytest

from event_radar.services.event_price import normalize_event_price


@pytest.mark.parametrize(
    ("description", "minimum", "maximum"),
    [
        ("Free admission for everyone.", Decimal("0"), Decimal("0")),
        ("General admission tickets are $10.", Decimal("10"), Decimal("10")),
        ("Tickets are $25-$50.", Decimal("25"), Decimal("50")),
        (
            "Tickets: $10 general, $5 students and youth.",
            Decimal("5"),
            Decimal("10"),
        ),
    ],
)
def test_explicit_admission_prices_are_normalized(
    description: str,
    minimum: Decimal,
    maximum: Decimal,
) -> None:
    price = normalize_event_price(description=description)

    assert price is not None
    assert price.minimum == minimum
    assert price.maximum == maximum
    assert price.currency == "USD"


@pytest.mark.parametrize(
    "description",
    [
        "Parking fee is $10.",
        "Food and drinks cost $15.",
        "Tickets cost $ten.",
        "A suggested donation supports the venue.",
    ],
)
def test_non_admission_and_malformed_prices_remain_unknown(description: str) -> None:
    assert normalize_event_price(description=description) is None


def test_structured_source_price_is_preferred_over_description() -> None:
    price = normalize_event_price(
        structured_price="$25 - $50",
        structured_details={"currency_code": "USD", "values": [25, 50]},
        description="Advance tickets are $10.",
    )

    assert price is not None
    assert price.minimum == Decimal("25")
    assert price.maximum == Decimal("50")
    assert price.source_text == "$25 - $50"


def test_structured_details_are_used_when_display_price_is_unparseable() -> None:
    price = normalize_event_price(
        structured_price="See ticket site",
        structured_details={"currency_code": "USD", "values": ["5", "10"]},
    )

    assert price is not None
    assert price.minimum == Decimal("5")
    assert price.maximum == Decimal("10")
    assert price.source_text == "$5\u2013$10"


def test_unparseable_structured_price_does_not_fall_back_to_description() -> None:
    assert (
        normalize_event_price(
            structured_price="See ticket site",
            description="Admission tickets are $10.",
        )
        is None
    )
