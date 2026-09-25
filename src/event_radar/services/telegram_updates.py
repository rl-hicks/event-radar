from datetime import UTC, datetime
from typing import TypeGuard

import httpx

from event_radar.models.direction import Direction, DirectionType


class TelegramUpdateError(RuntimeError):
    """Raised when Telegram updates cannot be retrieved."""


class TelegramUpdateClient:
    def __init__(
        self,
        bot_token: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        self._timeout = timeout_seconds

    async def get_updates(
        self,
        offset: int | None = None,
    ) -> list[dict[str, object]]:
        params: dict[str, int] = {}

        if offset is not None:
            params["offset"] = offset

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                self._url,
                params=params,
            )

        if response.is_error:
            raise TelegramUpdateError(f"Telegram returned {response.status_code}: {response.text}")

        payload = response.json()

        if payload.get("ok") is not True:
            raise TelegramUpdateError("Telegram returned an unsuccessful response")

        result = payload.get("result", [])

        if not isinstance(result, list):
            raise TelegramUpdateError("Telegram returned an invalid update list")

        return result


def parse_direction(
    update: dict[str, object],
) -> Direction | None:
    message = update.get("message")

    if not isinstance(message, dict):
        return None

    text = message.get("text")

    if not isinstance(text, str):
        return None

    sender = message.get("from")

    if not isinstance(sender, dict):
        return None

    user_id = sender.get("id")

    if not _is_telegram_id(user_id):
        return None

    chat = message.get("chat")

    if not isinstance(chat, dict):
        return None

    chat_id = chat.get("id")
    chat_type = chat.get("type")

    if not _is_telegram_id(chat_id) or not isinstance(chat_type, str):
        return None

    update_id = update.get("update_id")

    if not isinstance(update_id, int):
        return None

    command, separator, instruction = text.strip().partition(" ")

    if not separator or not instruction.strip():
        return None

    # Telegram may include the bot username in an addressed command token.
    command = command.split("@", maxsplit=1)[0].lower()

    if command == "/temp":
        direction_type = DirectionType.TEMPORARY
    elif command == "/permanent":
        direction_type = DirectionType.PERMANENT
    else:
        return None

    return Direction(
        type=direction_type,
        text=instruction.strip(),
        telegram_user_id=user_id,
        telegram_chat_id=chat_id,
        telegram_chat_type=chat_type,
        created_at=datetime.now(UTC),
        update_id=update_id,
    )


def is_authorized_owner_direction(
    direction: Direction,
    *,
    owner_user_id: int | None,
    owner_chat_id: str | int | None,
) -> bool:
    """Require the configured owner identity in the configured private chat."""
    if owner_user_id is None or owner_chat_id is None:
        return False
    if direction.telegram_chat_type != "private":
        return False
    if direction.telegram_chat_id is None:
        return False
    return direction.telegram_user_id == owner_user_id and str(direction.telegram_chat_id) == str(
        owner_chat_id
    )


def _is_telegram_id(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
