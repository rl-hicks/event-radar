from collections import Counter
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from event_radar.models.curation import (
    CandidateType,
    CuratedOption,
    CurationOutcome,
    CurationRole,
    HikeCandidateContext,
    ImportantUnknown,
    RecommendationContext,
)
from event_radar.models.event_analysis import EventOccurrenceFact, WeekendEventCard

_ROLE_HEADINGS = {
    CurationRole.STANDOUT: "Standout opportunities",
    CurationRole.DISTINCT: "Distinct / unusual options",
    CurationRole.LOW_FRICTION: "Low-friction options",
    CurationRole.SCHEDULE_CONFLICT: "Schedule-conflicting but notable",
    CurationRole.BACKUP: "Credible backups",
}


def render_chatgpt_packet(context: RecommendationContext, outcome: CurationOutcome) -> str:
    timezone = ZoneInfo(context.user_context.base_location.timezone)
    lines = [
        "# Event Radar - Weekend Decision Packet",
        "",
        "## Weekend",
        "",
        f"{_format_datetime(context.weekend_start, timezone)} through "
        f"{_format_datetime(context.weekend_end, timezone)} (exclusive end)",
        "",
        "## How to use this packet",
        "",
        "This is a curated decision set, not a predetermined itinerary.",
        "",
        "## User context",
        "",
        f"- Profile: {context.user_context.profile_label}",
        f"- Home base: {context.user_context.base_location.name}",
        f"- Objective: {context.user_context.core_objective}",
        f"- Social posture: {context.user_context.social_posture.objective}",
        f"- Hiking posture: {context.user_context.hiking_posture.destination_posture}",
    ]
    for window in context.user_context.recurring_availability:
        time_range = _availability_time_range(window.start_time, window.end_time)
        lines.append(
            f"- {window.day_of_week.title()} availability ({window.status.value}"
            f"{time_range}): {window.description}"
        )
    lines.extend(_direction_section("Permanent directions", context.permanent_directions))
    lines.extend(_direction_section("Temporary directions", context.temporary_directions))
    if context.event_pipeline_notes:
        lines.extend(["", "## Event research status", ""])
        lines.extend(_bullets(context.event_pipeline_notes, "No degraded stages."))

    if outcome.curation is None:
        lines.extend(
            [
                "",
                "## Automated curation status",
                "",
                "**Automated final LLM curation unavailable for this run.**",
                "",
                "The broad factual event-card inventory is preserved below without fabricated "
                "final judgments.",
            ]
        )
    else:
        lines.extend(["", "## Weekend read", ""])
        lines.extend(_bullets(outcome.curation.weekend_read, "No overall observations returned."))

    lines.extend(_weather_section(context))
    if outcome.curation is None:
        lines.extend(_fallback_candidates(context, timezone))
    else:
        lines.extend(_curated_candidates(context, outcome.curation.options, timezone))
        lines.extend(["", "## Important unknowns", ""])
        lines.extend(
            _bullets(
                _important_unknown_details(
                    context.known_unknowns,
                    outcome.curation.important_unknowns,
                ),
                "None noted.",
            )
        )
        if outcome.curation.notable_near_misses:
            event_lookup, hike_lookup = _candidate_lookups(context)
            lines.extend(["", "## Notable near-misses", ""])
            for near_miss in outcome.curation.notable_near_misses:
                name = _candidate_name(near_miss.candidate_id, event_lookup, hike_lookup)
                lines.append(f"- **{name}**: {near_miss.reason_not_retained}")

    lines.extend(
        [
            "",
            "## Hike verification requirement",
            "",
            "Access status is not verified for any hike. Check the linked official source "
            "before leaving, including closures, gates, reservations, parking, tides, surf, "
            "fire restrictions, and route-specific alerts as relevant.",
            "",
            "## ChatGPT handoff instructions",
            "",
            "- Treat this packet as the current weekend research basis, not final truth.",
            "- Help the user decide interactively using current mood, energy, companionship, "
            "and schedule changes.",
            "- Preserve the Saturday climbing soft anchor unless there is a concrete reason.",
            "- Never claim unchecked hike access is verified.",
            "- Distinguish authoritative facts from AI experiential interpretation.",
            "- Do not treat any upstream semantic analysis as authoritative.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def render_telegram_curation_summary(
    context: RecommendationContext,
    outcome: CurationOutcome,
) -> str:
    timezone = ZoneInfo(context.user_context.base_location.timezone)
    lines = ["EVENT RADAR - THIS WEEKEND", ""]
    if outcome.curation is None:
        lines.extend(
            [
                "Automated final curation was unavailable.",
                "The attached packet preserves the broad event and hike inventory.",
                "",
                f"Event cards included: {len(context.event_cards)}",
                f"Hikes included: {len(context.hike_candidates)}",
            ]
        )
    else:
        event_lookup, hike_lookup = _candidate_lookups(context)
        counts = Counter(option.candidate_type for option in outcome.curation.options)
        lines.append("Weekend read")
        lines.extend(f"- {item}" for item in outcome.curation.weekend_read[:3])
        lines.extend(
            [
                "",
                f"Curated decision set: {len(outcome.curation.options)} worthwhile possibilities",
                f"Events retained: {counts[CandidateType.EVENT]}",
                f"Hikes retained: {counts[CandidateType.HIKE]}",
            ]
        )
        standouts = [
            option for option in outcome.curation.options if option.role is CurationRole.STANDOUT
        ]
        if standouts:
            lines.extend(["", "Standouts"])
            lines.extend(
                "- "
                + _telegram_candidate_label(
                    option.candidate_id, event_lookup, hike_lookup, timezone
                )
                for option in standouts[:5]
            )
    lines.extend(
        [
            "",
            "Full ChatGPT decision packet attached.",
            "This is not a final recommendation - use the packet with ChatGPT to decide.",
        ]
    )
    return "\n".join(lines)


def write_chatgpt_packet(
    packet: str,
    *,
    output_directory: Path,
    weekend_start: datetime,
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"event-radar-{weekend_start.date().isoformat()}.md"
    path.write_text(packet, encoding="utf-8")
    return path


def _curated_candidates(
    context: RecommendationContext,
    options: list[CuratedOption],
    timezone: ZoneInfo,
) -> list[str]:
    event_lookup, hike_lookup = _candidate_lookups(context)
    sections: list[tuple[str, list[CuratedOption]]] = [
        (
            "Standout opportunities",
            [option for option in options if option.role is CurationRole.STANDOUT],
        ),
        (
            "Strong event candidates",
            [
                option
                for option in options
                if option.role is CurationRole.STRONG
                and option.candidate_type is CandidateType.EVENT
            ],
        ),
        (
            "Strong hike candidates",
            [
                option
                for option in options
                if option.role is CurationRole.STRONG
                and option.candidate_type is CandidateType.HIKE
            ],
        ),
    ]
    for role, heading in _ROLE_HEADINGS.items():
        if role is not CurationRole.STANDOUT:
            sections.append((heading, [option for option in options if option.role is role]))
    lines: list[str] = []
    rendered: set[str] = set()
    for heading, values in sections:
        values = [value for value in values if value.candidate_id not in rendered]
        if not values:
            continue
        lines.extend(["", f"## {heading}", ""])
        for option in values:
            rendered.add(option.candidate_id)
            event = event_lookup.get(option.candidate_id)
            if event is not None:
                lines.extend(_render_event(event, option, timezone))
            else:
                lines.extend(_render_hike(hike_lookup[option.candidate_id], option, timezone))
    return lines


def _fallback_candidates(context: RecommendationContext, timezone: ZoneInfo) -> list[str]:
    lines = ["", "## Broad event-card inventory", ""]
    for event in context.event_cards:
        lines.extend(_render_event(event, None, timezone))
    if not context.event_cards:
        lines.append("No factual event cards were available.")
    lines.extend(["", "## Deterministic hike candidates", ""])
    for hike in context.hike_candidates:
        lines.extend(_render_hike(hike, None, timezone))
    if not context.hike_candidates:
        lines.append("No hike candidates were available.")
    lines.extend(["", "## Important unknowns", ""])
    lines.extend(_bullets(_important_unknown_details(context.known_unknowns), "None noted."))
    return lines


def _render_event(
    card: WeekendEventCard,
    option: CuratedOption | None,
    timezone: ZoneInfo,
) -> list[str]:
    lines = [
        f"### {card.title}",
        "",
        f"- Candidate ID: `{card.candidate_id}`",
        f"- Origin: {card.origin.value}",
        f"- Experience summary: {card.experience_summary}",
        f"- Experience modes: {_joined(card.experience_modes)}",
        f"- Interaction architecture: {card.interaction_architecture}",
        f"- Solo viability: {card.solo_viability}",
        f"- Active value: {card.active_value}",
        f"- Distinctiveness: {card.distinctiveness}",
        f"- Social opportunity: {card.social_opportunity}",
        f"- Friction: {card.friction_summary}",
        f"- Schedule: {card.schedule_observation}",
        f"- Uncertainties: {_joined(card.uncertainties)}",
    ]
    for index, occurrence in enumerate(card.occurrences, start=1):
        lines.extend(_render_occurrence(occurrence, index, timezone))
    if option is not None:
        lines.extend(_ai_observations(option))
    lines.append("")
    return lines


def _render_occurrence(
    occurrence: EventOccurrenceFact,
    index: int,
    timezone: ZoneInfo,
) -> list[str]:
    location = ", ".join(
        part for part in (occurrence.venue, occurrence.city, occurrence.state) if part
    )
    source_links = "; ".join(
        f"[{source.source_name}]({source.source_url})" for source in occurrence.sources
    )
    rendered_time = format_event_time_range(occurrence.start_time, occurrence.end_time, timezone)
    lines = [
        f"- Occurrence {index}: `{occurrence.event_id}`",
        f"  - When: {rendered_time}",
        f"  - Where: {location}",
        f"  - Categories: {', '.join(occurrence.categories) or 'unknown'}",
        f"  - Price: {_price(occurrence)}",
        f"  - Sources: {source_links}",
    ]
    if occurrence.description:
        lines.append(f"  - Source description: {occurrence.description}")
    return lines


def _render_hike(
    hike: HikeCandidateContext,
    option: CuratedOption | None,
    timezone: ZoneInfo,
) -> list[str]:
    weather = hike.weather
    lines = [
        f"### {hike.name}",
        "",
        f"- Candidate ID: `{hike.candidate_id}`",
        f"- Area: {hike.park_or_area} ({hike.region})",
        f"- Best window: {hike.best_start_time.astimezone(timezone).strftime('%A')}, "
        f"{_format_clock(hike.best_start_time, timezone)}-"
        f"{_format_clock(hike.estimated_finish_time, timezone)}",
        f"- Route: {hike.distance_miles:g} mi, {hike.elevation_gain_ft:,} ft gain, "
        f"{hike.difficulty}; {hike.duration_min_minutes}-{hike.duration_max_minutes} min",
        f"- Trailhead weather: {', '.join(item.value for item in weather.conditions)}; "
        f"{weather.temperature_min_f:.0f}-{weather.temperature_max_f:.0f} F; "
        f"rain {_optional(weather.precipitation_probability_max, '%')}",
        f"- Deterministic hike score: {hike.deterministic_score}",
        f"- Deterministic hike reasons: {_joined(hike.deterministic_reasons)}",
        f"- Cautions: {_joined(hike.cautions)}",
        f"- Official source: [verify route and access]({hike.official_source_url})",
        f"- **{hike.access_warning}**",
    ]
    if option is not None:
        lines.extend(_ai_observations(option))
    lines.append("")
    return lines


def _ai_observations(option: CuratedOption) -> list[str]:
    return [
        f"- Final curation role/confidence: {option.role.value} / {option.confidence.value}",
        f"- Why it survived: {option.why_it_survived}",
        f"- Tradeoffs: {_joined(option.tradeoffs)}",
        f"- Social observation: {option.social_observation}",
        f"- Solo observation: {option.solo_observation}",
        f"- Friction observation: {option.friction_observation}",
        f"- Schedule observation: {option.schedule_observation}",
    ]


def _weather_section(context: RecommendationContext) -> list[str]:
    lines = ["", "## Weather context", ""]
    weather = context.baseline_weather
    if weather is None:
        lines.append("Weather unavailable.")
        return lines
    lines.append(f"Baseline: {weather.location_name}")
    for day in weather.days:
        lines.append(
            f"- {day.date.strftime('%A')}: {day.condition.value}; "
            f"high {day.temperature_high_f:.0f} F / low {day.temperature_low_f:.0f} F; "
            f"rain {_optional(day.precipitation_probability_max, '%')}; "
            f"wind {_optional(day.max_wind_speed_mph, ' mph')}"
        )
    return lines


def _candidate_lookups(
    context: RecommendationContext,
) -> tuple[dict[str, WeekendEventCard], dict[str, HikeCandidateContext]]:
    return (
        {candidate.candidate_id: candidate for candidate in context.event_cards},
        {candidate.candidate_id: candidate for candidate in context.hike_candidates},
    )


def _candidate_name(
    candidate_id: str,
    events: dict[str, WeekendEventCard],
    hikes: dict[str, HikeCandidateContext],
) -> str:
    event = events.get(candidate_id)
    return event.title if event is not None else hikes[candidate_id].name


def _telegram_candidate_label(
    candidate_id: str,
    events: dict[str, WeekendEventCard],
    hikes: dict[str, HikeCandidateContext],
    timezone: ZoneInfo,
) -> str:
    event = events.get(candidate_id)
    if event is None:
        return hikes[candidate_id].name
    first = event.occurrences[0]
    return f"{event.title} - {format_event_time_range(first.start_time, first.end_time, timezone)}"


def format_event_time_range(
    start: datetime,
    end: datetime | None,
    local_timezone: ZoneInfo | str,
) -> str:
    timezone = ZoneInfo(local_timezone) if isinstance(local_timezone, str) else local_timezone
    local_start = start.astimezone(timezone)
    rendered = _format_datetime(local_start, timezone)
    if end is None:
        return rendered
    local_end = end.astimezone(timezone)
    if local_end.date() == local_start.date():
        return f"{rendered} to {_format_clock(local_end, timezone)} {local_end.tzname()}"
    return f"{rendered} to {_format_datetime(local_end, timezone)}"


def _price(event: EventOccurrenceFact) -> str:
    if event.price_details:
        return event.price_details
    if event.price_min is None and event.price_max is None:
        return "UNKNOWN"
    symbol = "$" if event.price_currency in (None, "USD") else f"{event.price_currency} "
    if event.price_min == event.price_max == Decimal("0"):
        return "Free"
    if (
        event.price_min is not None
        and event.price_max is not None
        and event.price_min != event.price_max
    ):
        return symbol + f"{event.price_min:g}-" + symbol + f"{event.price_max:g}"
    value = event.price_min if event.price_min is not None else event.price_max
    return symbol + f"{value:g}" if value is not None else "UNKNOWN"


def _format_datetime(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).strftime("%A, %B %-d at %-I:%M %p %Z")


def _format_clock(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).strftime("%-I:%M %p")


def _availability_time_range(start: time | None, end: time | None) -> str:
    if start is None and end is None:
        return ""
    start_text = start.strftime("%-I:%M %p") if start else "start of day"
    end_text = end.strftime("%-I:%M %p") if end else "end of day"
    return f", {start_text}-{end_text}"


def _direction_section(title: str, directions: list[str]) -> list[str]:
    return ["", f"## {title}", "", *_bullets(directions, "None.")]


def _bullets(items: list[str], empty: str) -> list[str]:
    return [f"- {item}" for item in items] if items else [f"- {empty}"]


def _joined(items: list[str]) -> str:
    return "; ".join(items) if items else "none"


def _important_unknown_details(*groups: list[ImportantUnknown]) -> list[str]:
    by_kind: dict[object, str] = {}
    for group in groups:
        for unknown in group:
            by_kind.setdefault(unknown.kind, unknown.detail)
    return list(by_kind.values())


def _optional(value: float | None, suffix: str) -> str:
    return f"{value:.0f}{suffix}" if value is not None else "UNKNOWN"
