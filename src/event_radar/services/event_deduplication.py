import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from event_radar.models.event import Event, EventSource

_NON_WORD_PATTERN = re.compile(r"[^\w]+", re.UNICODE)


@dataclass(frozen=True)
class DeduplicationResult:
    events: list[Event]
    duplicates_removed: int


def deduplicate_events(events: Iterable[Event]) -> DeduplicationResult:
    """Conservatively merge matching cross-source event occurrences."""
    deduplicated: list[Event] = []
    duplicates_removed = 0

    for candidate in sorted(events, key=lambda event: event.start_time):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(deduplicated)
                if _are_duplicates(existing, candidate)
            ),
            None,
        )
        if duplicate_index is None:
            deduplicated.append(candidate)
            continue

        deduplicated[duplicate_index] = _merge_provenance(deduplicated[duplicate_index], candidate)
        duplicates_removed += 1

    return DeduplicationResult(events=deduplicated, duplicates_removed=duplicates_removed)


def _are_duplicates(first: Event, second: Event) -> bool:
    if first.source_name == second.source_name:
        return False
    if _normalize(first.title) != _normalize(second.title):
        return False
    if first.start_time != second.start_time:
        return False
    if _normalize(first.city) != _normalize(second.city):
        return False
    if first.venue and second.venue:
        return _normalize(first.venue) == _normalize(second.venue)
    return True


def _merge_provenance(first: Event, second: Event) -> Event:
    if _completeness(second) > _completeness(first):
        primary, alternate = second, first
    else:
        primary, alternate = first, second

    all_sources = [
        EventSource(
            source_name=alternate.source_name,
            source_id=alternate.source_id,
            source_url=alternate.source_url,
        ),
        *alternate.alternate_sources,
        *primary.alternate_sources,
    ]
    unique_sources: dict[tuple[str, str | None, str], EventSource] = {}
    for source in all_sources:
        key = (source.source_name, source.source_id, str(source.source_url))
        if source.source_name != primary.source_name or source.source_id != primary.source_id:
            unique_sources[key] = source

    return primary.model_copy(update={"alternate_sources": list(unique_sources.values())})


def _completeness(event: Event) -> int:
    return sum(
        value is not None
        for value in (
            event.description,
            event.end_time,
            event.venue,
            event.price_min,
            event.price_max,
        )
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _NON_WORD_PATTERN.split(normalized) if part)
