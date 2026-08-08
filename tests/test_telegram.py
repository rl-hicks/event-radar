import pytest

from event_radar.services.telegram import split_telegram_message


def test_split_telegram_message_leaves_short_message_unchanged() -> None:
    assert split_telegram_message("Short digest", limit=20) == ["Short digest"]


def test_split_telegram_message_prefers_paragraph_boundaries() -> None:
    message = "First event\n\nSecond event\n\nThird event"

    chunks = split_telegram_message(message, limit=25)

    assert chunks == ["First event\n\nSecond event", "Third event"]
    assert all(len(chunk) <= 25 for chunk in chunks)


def test_split_telegram_message_hard_wraps_long_unbroken_text() -> None:
    chunks = split_telegram_message("x" * 25, limit=10)

    assert chunks == ["x" * 10, "x" * 10, "x" * 5]


def test_split_telegram_message_requires_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        split_telegram_message("digest", limit=0)
