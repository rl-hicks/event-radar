import asyncio
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

from event_radar.collectors.happening_sonoma import HappeningSonomaCollector
from event_radar.collectors.sonoma_county import SonomaCountyCollector
from event_radar.config import settings
from event_radar.models.weather import WeatherLocation, WeekendWeather
from event_radar.services.curation_rendering import (
    render_chatgpt_packet,
    render_telegram_curation_summary,
    write_chatgpt_packet,
)
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
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.hike_suitability import (
    build_hike_candidate_selection,
    format_hike_diagnostics,
)
from event_radar.services.hike_weather import collect_trailhead_weather
from event_radar.services.llm_curation import OpenAICurationService, curate_with_fallback
from event_radar.services.recommendation_context import (
    build_recommendation_context,
    recommendation_context_size,
)
from event_radar.services.telegram import TelegramClient
from event_radar.services.telegram_updates import (
    TelegramUpdateClient,
    is_authorized_owner_direction,
    parse_direction,
)
from event_radar.services.user_context import UserContextRepository
from event_radar.services.weather import (
    OpenMeteoWeatherClient,
    WeatherProviderError,
    filter_weather_to_window,
    forecast_dates_for_window,
    format_weather_diagnostics,
)
from event_radar.services.weekend import upcoming_weekend_window

PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


class WeekendDeliveryClient(Protocol):
    async def send_message(self, message: str) -> None: ...

    async def send_document(
        self,
        *,
        filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> None: ...


async def fetch_baseline_weather(
    client: OpenMeteoWeatherClient,
    location: WeatherLocation,
    start: datetime,
    end: datetime,
) -> WeekendWeather | None:
    """Fetch weather without making a provider outage suppress the event digest."""
    forecast_start, forecast_end = forecast_dates_for_window(start, end, location)
    try:
        weather = await client.get_forecast(location, forecast_start, forecast_end)
    except WeatherProviderError as exc:
        print(f"Weather unavailable: {exc}")
        return None
    return filter_weather_to_window(weather, start, end)


async def run() -> None:
    now = datetime.now(PACIFIC_TIME)
    start, end = upcoming_weekend_window(now)
    user_context = UserContextRepository(settings.user_context_path).load()
    permanent_directions = load_permanent_directions()
    temporary_directions = load_temporary_directions()

    sonoma_county_collector = SonomaCountyCollector(
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
    )
    happening_sonoma_collector = HappeningSonomaCollector(
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
    )
    weather_location = WeatherLocation(
        name=settings.weather_location_name,
        latitude=settings.weather_latitude,
        longitude=settings.weather_longitude,
        timezone=settings.weather_timezone,
    )
    hike_catalog = HikeCatalogRepository(settings.hike_catalog_path).load()
    async with httpx.AsyncClient() as weather_http_client:
        weather_client = OpenMeteoWeatherClient(
            user_agent=settings.user_agent,
            timeout_seconds=settings.request_timeout_seconds,
            client=weather_http_client,
        )
        (
            sonoma_county_events,
            happening_sonoma_events,
            weather,
            hike_weather,
        ) = await asyncio.gather(
            sonoma_county_collector.collect(start=start, end=end),
            happening_sonoma_collector.collect(start=start, end=end),
            fetch_baseline_weather(weather_client, weather_location, start, end),
            collect_trailhead_weather(
                hike_catalog.hikes,
                weather_client,
                start,
                end,
                timezone=settings.weather_timezone,
            ),
        )

    deduplication = deduplicate_events([*sonoma_county_events, *happening_sonoma_events])
    selection = select_event_candidates(deduplication.events, start=start, end=end)
    hike_selection = build_hike_candidate_selection(
        hike_catalog.hikes,
        hike_weather,
        start,
        end,
        timezone=settings.weather_timezone,
    )
    print(format_selection_diagnostics(selection))
    if weather is not None:
        print(format_weather_diagnostics(weather))
    print(
        format_hike_diagnostics(
            hike_selection,
            catalog_size=len(hike_catalog.hikes),
        )
    )

    context = build_recommendation_context(
        generated_at=now,
        weekend_start=start,
        weekend_end=end,
        user_context=user_context,
        permanent_directions=permanent_directions,
        temporary_directions=temporary_directions,
        baseline_weather=weather,
        event_selection=selection,
        hike_selection=hike_selection,
    )
    context_characters, approximate_tokens = recommendation_context_size(context)
    print(
        f"Recommendation context: {context_characters} characters "
        f"(~{approximate_tokens} tokens), {len(context.event_candidates)} events, "
        f"{len(context.hike_candidates)} hikes"
    )
    curation_service = OpenAICurationService(
        api_key=(
            settings.openai_api_key.get_secret_value()
            if settings.openai_api_key is not None
            else None
        ),
        model=settings.openai_model,
        prompt_path=settings.curation_prompt_path,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    outcome = await curate_with_fallback(curation_service, context)
    packet = render_chatgpt_packet(context, outcome)
    packet_path = write_chatgpt_packet(
        packet,
        output_directory=settings.curation_output_dir,
        weekend_start=start,
    )
    summary = render_telegram_curation_summary(context, outcome)

    if settings.telegram_bot_token is None or settings.telegram_chat_id is None:
        print(summary)
        print(f"ChatGPT packet written to {packet_path}.")
        print("\nTelegram credentials are not configured.")
        return

    telegram = TelegramClient(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
        timeout_seconds=settings.request_timeout_seconds,
    )

    await deliver_weekend_digest(
        telegram,
        summary=summary,
        packet_filename=packet_path.name,
        packet_content=packet.encode("utf-8"),
    )
    print("Sent summary and ChatGPT packet to the configured owner Telegram chat.")


async def deliver_weekend_digest(
    telegram: WeekendDeliveryClient,
    *,
    summary: str,
    packet_filename: str,
    packet_content: bytes,
) -> None:
    """Clear temporary directions only after summary and document both succeed."""
    await telegram.send_message(summary)
    await telegram.send_document(
        filename=packet_filename,
        content=packet_content,
        caption="Event Radar ChatGPT weekend decision packet",
    )
    clear_temporary_directions()


async def read_directions() -> None:
    if settings.telegram_bot_token is None:
        print("Telegram bot token is not configured.")
        return

    if settings.telegram_owner_user_id is None or not settings.telegram_chat_id:
        print("Telegram owner user ID and private chat ID are not configured.")
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
        if direction.telegram_chat_type != "private":
            print("Ignored non-private Telegram command.")
            continue
        if not is_authorized_owner_direction(
            direction,
            owner_user_id=settings.telegram_owner_user_id,
            owner_chat_id=settings.telegram_chat_id,
        ):
            print("Ignored unauthorized Telegram update.")
            continue

        save_direction(direction)
        print(f"Saved {direction.type.value} Telegram direction (update={direction.update_id}).")

    if highest_update_id is not None:
        save_offset(highest_update_id + 1)


async def execute() -> None:
    await read_directions()
    await run()


def main() -> None:
    asyncio.run(execute())


if __name__ == "__main__":
    main()
