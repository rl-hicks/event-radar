import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from event_radar.collectors.happening_sonoma import HappeningSonomaCollector
from event_radar.collectors.sonoma_county import SonomaCountyCollector
from event_radar.config import settings
from event_radar.models.event import Event
from event_radar.services.direction_store import (
    clear_temporary_directions,
    load_offset,
    load_permanent_directions,
    load_temporary_directions,
    save_direction,
    save_offset,
)
from event_radar.services.event_deduplication import deduplicate_events
from event_radar.services.event_evaluation import (
    format_selection_diagnostics,
    select_event_candidates,
)
from event_radar.services.telegram import TelegramClient
from event_radar.services.telegram_updates import (
    TelegramUpdateClient,
    parse_direction,
)
from event_radar.services.weekend import upcoming_weekend_window

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def format_event(event: Event) -> str:
    date_text = event.start_time.astimezone(PACIFIC_TIME).strftime("%A, %B %-d at %-I:%M %p")

    location_parts = [part for part in (event.venue, event.city) if part]
    location = ", ".join(location_parts)

    lines = [
        f"📍 {event.title}",
        date_text,
        location,
        f"Source: {event.source_name}",
        str(event.source_url),
    ]
    for source in event.alternate_sources:
        lines.extend([f"Also listed by: {source.source_name}", str(source.source_url)])

    return "\n".join(lines)


def format_directions() -> str:
    permanent = load_permanent_directions()
    temporary = load_temporary_directions()

    lines = ["Active directions"]

    if permanent:
        lines.append("\nPermanent:")
        for direction in permanent:
            lines.append(f"- {direction.text}")

    if temporary:
        lines.append("\nTemporary for this digest:")
        for direction in temporary:
            lines.append(f"- {direction.text}")

    if not permanent and not temporary:
        lines.append("- None")

    return "\n".join(lines)


async def run() -> None:
    now = datetime.now(PACIFIC_TIME)
    start, end = upcoming_weekend_window(now)

    sonoma_county_collector = SonomaCountyCollector(
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
    )
    happening_sonoma_collector = HappeningSonomaCollector(
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
    )
    sonoma_county_events, happening_sonoma_events = await asyncio.gather(
        sonoma_county_collector.collect(start=start, end=end),
        happening_sonoma_collector.collect(start=start, end=end),
    )
    deduplication = deduplicate_events([*sonoma_county_events, *happening_sonoma_events])
    selection = select_event_candidates(deduplication.events, start=start, end=end)
    events = selection.events
    print(format_selection_diagnostics(selection))

    message_parts = [
        "Event Radar",
        "",
        format_directions(),
        "",
        "--------------------",
        "",
        "Recommended weekend candidates",
        "",
    ]

    if events:
        for event in events:
            message_parts.append(format_event(event))
            message_parts.append("")
    else:
        message_parts.append("No matching events found for this weekend.")

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
    print(f"Sent digest to Telegram chat {settings.telegram_chat_id}.")
    clear_temporary_directions()


async def read_directions() -> None:
    if settings.telegram_bot_token is None:
        print("Telegram bot token is not configured.")
        return

    client = TelegramUpdateClient(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        timeout_seconds=settings.request_timeout_seconds,
    )

    offset = load_offset()
    updates = await client.get_updates(offset=offset)

    print(f"Received {len(updates)} new Telegram update(s).")

    highest_update_id: int | None = None

    for update in updates:
        update_id = update.get("update_id")

        if isinstance(update_id, int):
            if highest_update_id is None or update_id > highest_update_id:
                highest_update_id = update_id

        direction = parse_direction(update)

        if direction is None:
            continue
        if (
            settings.telegram_owner_user_id is None
            or direction.telegram_user_id != settings.telegram_owner_user_id
        ):
            print(f"Ignored unauthorized direction from user={direction.telegram_user_id}")
            continue

        save_direction(direction)

        print(
            f"saved {direction.type.value}: "
            f"{direction.text} "
            f"(user={direction.telegram_user_id}, "
            f"update={direction.update_id})"
        )

    if highest_update_id is not None:
        save_offset(highest_update_id + 1)


async def execute() -> None:
    await read_directions()
    await run()


def main() -> None:
    asyncio.run(execute())


if __name__ == "__main__":
    main()
