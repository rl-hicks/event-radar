from datetime import UTC, datetime

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

    if not isinstance(user_id, int):
        return None

    update_id = update.get("update_id")

    if not isinstance(update_id, int):
        return None

    command, separator, instruction = text.strip().partition(" ")

    if not separator or not instruction.strip():
        return None

    # Telegram group commands may look like:
    # /temp@robot_event_radar_bot
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
        created_at=datetime.now(UTC),
        update_id=update_id,
    )
