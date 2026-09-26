import argparse
import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from event_radar.config import settings
from event_radar.models.curation import CurationDiagnostics, CurationOutcome, RecommendationContext
from event_radar.services.audit import write_audit_artifacts
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
from event_radar.services.event_analysis import OpenAIEventAnalysisService
from event_radar.services.event_evaluation import format_selection_diagnostics
from event_radar.services.hike_suitability import format_hike_diagnostics
from event_radar.services.llm_curation import OpenAICurationService, curate_with_fallback
from event_radar.services.pipeline import (
    EventIntelligenceResult,
    RecommendationPipelineResult,
    build_event_intelligence,
    build_event_intelligence_without_ai,
    build_recommendation_pipeline,
)
from event_radar.services.recommendation_context import recommendation_context_size
from event_radar.services.telegram import TelegramClient
from event_radar.services.telegram_updates import (
    TelegramUpdateClient,
    is_authorized_owner_direction,
    parse_direction,
)
from event_radar.services.user_context import UserContextRepository
from event_radar.services.weather import format_weather_diagnostics
from event_radar.services.web_event_discovery import OpenAIWebDiscoveryService

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


async def run() -> None:
    pipeline = await _build_current_pipeline()
    intelligence = await _build_event_intelligence(pipeline)
    outcome = await _curate_context(intelligence.context)
    _print_pipeline_diagnostics(pipeline, intelligence, outcome)
    packet = render_chatgpt_packet(intelligence.context, outcome)
    packet_path = write_chatgpt_packet(
        packet,
        output_directory=settings.curation_output_dir,
        weekend_start=pipeline.weekend_start,
    )
    summary = render_telegram_curation_summary(intelligence.context, outcome)
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


async def run_audit(*, run_llm: bool = True) -> None:
    pipeline = await _build_current_pipeline()
    llm_requested = run_llm and settings.openai_api_key is not None
    if llm_requested:
        intelligence = await _build_event_intelligence(pipeline)
        outcome = await _curate_context(intelligence.context)
    else:
        reason = (
            "Audit AI stages disabled by --no-llm."
            if not run_llm
            else "OpenAI API key is not configured; audit AI stages were not run."
        )
        intelligence = build_event_intelligence_without_ai(
            pipeline,
            model=settings.resolved_event_analysis_model,
            reason=reason,
        )
        outcome = _uncurated_outcome(intelligence.context, reason)
    _print_pipeline_diagnostics(pipeline, intelligence, outcome)
    audit = write_audit_artifacts(
        pipeline,
        intelligence,
        outcome,
        llm_requested=llm_requested,
    )
    print(f"Audit artifacts: {audit.output_directory}")
    print(
        "Audit summary: "
        f"Sonoma Tourism={len(pipeline.sonoma_tourism_events)}, "
        f"Happening Sonoma={len(pipeline.happening_sonoma_events)}, "
        f"deduplicated={len(pipeline.deduplication.events)}, "
        f"sent to AI #1={len(pipeline.valid_events)}, "
        f"scraped cards={len(intelligence.scraped_event_cards)}, "
        f"web cards={len(intelligence.web_event_cards)}, "
        f"combined={len(intelligence.combined_event_cards)}, "
        f"hikes={len(intelligence.context.hike_candidates)}, "
        f"retained={audit.retained_option_count}"
    )


async def _build_current_pipeline() -> RecommendationPipelineResult:
    generated_at = datetime.now(PACIFIC_TIME)
    user_context = UserContextRepository(settings.user_context_path).load()
    return await build_recommendation_pipeline(
        generated_at=generated_at,
        user_context=user_context,
        permanent_directions=load_permanent_directions(),
        temporary_directions=load_temporary_directions(),
        runtime_settings=settings,
    )


async def _build_event_intelligence(
    pipeline: RecommendationPipelineResult,
) -> EventIntelligenceResult:
    key = (
        settings.openai_api_key.get_secret_value() if settings.openai_api_key is not None else None
    )
    return await build_event_intelligence(
        pipeline,
        analysis_service=OpenAIEventAnalysisService(
            api_key=key,
            model=settings.resolved_event_analysis_model,
            prompt_path=settings.event_analysis_prompt_path,
            timeout_seconds=settings.openai_timeout_seconds,
        ),
        web_service=OpenAIWebDiscoveryService(
            api_key=key,
            model=settings.resolved_web_discovery_model,
            prompt_path=settings.web_discovery_prompt_path,
            timeout_seconds=settings.openai_timeout_seconds,
        ),
    )


async def _curate_context(context: RecommendationContext) -> CurationOutcome:
    service = OpenAICurationService(
        api_key=(
            settings.openai_api_key.get_secret_value()
            if settings.openai_api_key is not None
            else None
        ),
        model=settings.resolved_curation_model,
        prompt_path=settings.curation_prompt_path,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    return await curate_with_fallback(service, context)


def _uncurated_outcome(context: RecommendationContext, reason: str) -> CurationOutcome:
    return CurationOutcome(
        curation=None,
        diagnostics=CurationDiagnostics(
            model=settings.resolved_curation_model,
            success=False,
            fallback_reason=reason,
            input_event_cards=len(context.event_cards),
            input_hike_candidates=len(context.hike_candidates),
            retained_options=0,
            attempts=0,
        ),
    )


def _print_pipeline_diagnostics(
    pipeline: RecommendationPipelineResult,
    intelligence: EventIntelligenceResult,
    outcome: CurationOutcome,
) -> None:
    print("Public source status:")
    for name, status in (
        ("Sonoma County Tourism", pipeline.sonoma_tourism_status),
        ("Happening Sonoma", pipeline.happening_sonoma_status),
    ):
        detail = f", reason={status.failure_reason}" if status.failure_reason else ""
        print(
            f"- {name}: {'success' if status.success else 'unavailable'}, "
            f"count={status.count}{detail}"
        )
    if pipeline.weather_failure_reason is not None:
        print(f"- Weather: unavailable, reason={pipeline.weather_failure_reason}")
    else:
        print("- Weather: success")
    print("Legacy deterministic event evaluation (diagnostic only):")
    print(format_selection_diagnostics(pipeline.legacy_event_selection))
    if pipeline.baseline_weather is not None:
        print(format_weather_diagnostics(pipeline.baseline_weather))
    print(
        format_hike_diagnostics(
            pipeline.hike_selection,
            catalog_size=pipeline.hike_catalog_size,
        )
    )
    characters, tokens = recommendation_context_size(intelligence.context)
    print(
        f"Recommendation context: {characters} characters (~{tokens} tokens), "
        f"{len(intelligence.context.event_cards)} event cards, "
        f"{len(intelligence.context.hike_candidates)} hikes"
    )
    stages = [
        intelligence.analysis_outcome.diagnostics,
        intelligence.web_outcome.diagnostics,
    ]
    stage_tokens = sum(item.total_tokens or 0 for item in stages)
    stage_latency = sum(item.latency_seconds or 0 for item in stages)
    total_tokens = stage_tokens + (outcome.diagnostics.total_tokens or 0)
    total_latency = stage_latency + (outcome.diagnostics.latency_seconds or 0)
    print("AI stages:")
    for item in stages:
        latency = f"{item.latency_seconds:.2f}s" if item.latency_seconds is not None else "n/a"
        print(
            f"- {item.stage}: {'success' if item.success else 'fallback'}, "
            f"model={item.model}, attempts={item.attempts}, result={item.result_count}, "
            f"tokens={item.total_tokens if item.total_tokens is not None else 'n/a'}, "
            f"latency={latency}"
        )
    print(
        f"- final_curation: {'success' if outcome.diagnostics.success else 'fallback'}, "
        f"model={outcome.diagnostics.model}, attempts={outcome.diagnostics.attempts}, "
        f"retained={outcome.diagnostics.retained_options}, "
        f"tokens={outcome.diagnostics.total_tokens or 'n/a'}, "
        f"latency={outcome.diagnostics.latency_seconds or 0:.2f}s"
    )
    print(f"- aggregate: total_tokens={total_tokens}, total_latency={total_latency:.2f}s")


async def deliver_weekend_digest(
    telegram: WeekendDeliveryClient,
    *,
    summary: str,
    packet_filename: str,
    packet_content: bytes,
) -> None:
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
        if isinstance(update_id, int) and (
            highest_update_id is None or update_id > highest_update_id
        ):
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


async def execute(*, audit: bool = False, run_llm: bool = True) -> None:
    if audit:
        await run_audit(run_llm=run_llm)
        return
    await read_directions()
    await run()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Event Radar.")
    parser.add_argument("--audit", action="store_true", help="Run the read-only local audit.")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip all three OpenAI stages during --audit.",
    )
    args = parser.parse_args(argv)
    if args.no_llm and not args.audit:
        parser.error("--no-llm is only valid with --audit")
    asyncio.run(execute(audit=args.audit, run_llm=not args.no_llm))


if __name__ == "__main__":
    main()
