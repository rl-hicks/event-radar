import httpx

TELEGRAM_MESSAGE_LIMIT = 4000


class TelegramError(RuntimeError):
    """Raised when Telegram rejects a message."""


class TelegramClient:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._timeout = timeout_seconds

    async def send_message(self, message: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for chunk in split_telegram_message(message):
                response = await client.post(
                    self._url,
                    json={
                        "chat_id": self._chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    },
                )

                if response.is_error:
                    raise TelegramError(
                        f"Telegram returned {response.status_code}: {response.text}"
                    )


def split_telegram_message(
    message: str,
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    """Split long messages at readable boundaries within Telegram's limit."""
    if limit < 1:
        raise ValueError("Telegram message limit must be positive.")
    if len(message) <= limit:
        return [message]

    chunks: list[str] = []
    remaining = message
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit + 2)
        if split_at > limit:
            split_at = -1
        if split_at < 1:
            split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at < 1:
            split_at = limit

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")

    if remaining:
        chunks.append(remaining)
    return chunks
