import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from event_radar.collectors.example import ExampleCollector
from event_radar.config import settings
from event_radar.models.event import Event
from event_radar.services.telegram import TelegramClient

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def format_event(event: Event) -> str:
    date_text = event.start_time.astimezone(PACIFIC_TIME).strftime("%A, %B %-d at %-I:%M %p")

    location_parts = [part for part in (event.venue, event.city) if part]
    location = ", ".join(location_parts)

    return "\n".join(
        [
            f"📍 {event.title}",
            date_text,
            location,
            str(event.source_url),
        ]
    )


async def run() -> None:
    now = datetime.now(PACIFIC_TIME)
    end = now + timedelta(days=7)

    collector = ExampleCollector()
    events = await collector.collect(start=now, end=end)

    message_parts = ["Event Radar test digest", ""]

    for event in events:
        message_parts.append(format_event(event))
        message_parts.append("")

    message = "\n".join(message_parts).strip()

    if settings.telegram_bot_token is None or settings.telegram_chat_id is None:
        print(message)
        print("\nTelegram credentials are not configured.")
        return

    telegram = TelegramClient(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )

    await telegram.send_message(message)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
