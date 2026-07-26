import httpx


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
            response = await client.post(
                self._url,
                json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                },
            )

        if response.is_error:
            raise TelegramError(f"Telegram returned {response.status_code}: {response.text}")
