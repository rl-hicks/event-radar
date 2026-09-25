import pytest

import event_radar.main as main_module
from event_radar.main import deliver_weekend_digest
from event_radar.services.telegram import TelegramError, split_telegram_message


class FakeTelegram:
    def __init__(self, *, fail_summary: bool = False, fail_document: bool = False) -> None:
        self.fail_summary = fail_summary
        self.fail_document = fail_document
        self.messages: list[str] = []
        self.documents: list[tuple[str, bytes, str | None]] = []

    async def send_message(self, message: str) -> None:
        self.messages.append(message)
        if self.fail_summary:
            raise TelegramError("summary failed")

    async def send_document(
        self,
        *,
        filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> None:
        self.documents.append((filename, content, caption))
        if self.fail_document:
            raise TelegramError("document failed")


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


@pytest.mark.asyncio
async def test_complete_delivery_sends_summary_and_document_then_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr(main_module, "clear_temporary_directions", lambda: cleared.append(True))
    telegram = FakeTelegram()

    await deliver_weekend_digest(
        telegram,
        summary="summary",
        packet_filename="packet.md",
        packet_content=b"# packet",
    )

    assert telegram.messages == ["summary"]
    assert telegram.documents == [
        ("packet.md", b"# packet", "Event Radar ChatGPT weekend decision packet")
    ]
    assert cleared == [True]


@pytest.mark.asyncio
async def test_summary_failure_preserves_temporary_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr(main_module, "clear_temporary_directions", lambda: cleared.append(True))
    telegram = FakeTelegram(fail_summary=True)

    with pytest.raises(TelegramError, match="summary failed"):
        await deliver_weekend_digest(
            telegram,
            summary="summary",
            packet_filename="packet.md",
            packet_content=b"# packet",
        )

    assert telegram.documents == []
    assert cleared == []


@pytest.mark.asyncio
async def test_document_failure_after_summary_preserves_temporary_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleared: list[bool] = []
    monkeypatch.setattr(main_module, "clear_temporary_directions", lambda: cleared.append(True))
    telegram = FakeTelegram(fail_document=True)

    with pytest.raises(TelegramError, match="document failed"):
        await deliver_weekend_digest(
            telegram,
            summary="summary",
            packet_filename="packet.md",
            packet_content=b"# packet",
        )

    assert telegram.messages == ["summary"]
    assert len(telegram.documents) == 1
    assert cleared == []
