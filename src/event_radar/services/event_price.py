import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

_AMOUNT = r"(?:0|[1-9]\d*)(?:\.\d{1,2})?"
_RANGE_PATTERN = re.compile(
    rf"\$\s*(?P<minimum>{_AMOUNT})\s*(?:-|–|—|\bto\b)\s*"
    rf"\$?\s*(?P<maximum>{_AMOUNT})",
    re.IGNORECASE,
)
_AMOUNT_PATTERN = re.compile(rf"\$\s*(?P<amount>{_AMOUNT})")
_ADMISSION_CONTEXT_PATTERN = re.compile(
    r"\b(?:admission|advance|cost|entry|fee|general|member|nonmember|"
    r"non-member|pricing|registration|student|ticket|tickets|youth)\b",
    re.IGNORECASE,
)
_EXCLUDED_CONTEXT_PATTERN = re.compile(
    r"\b(?:beer|beverage|cocktail|dinner|drink|food|meal|merchandise|parking|wine)\b",
    re.IGNORECASE,
)
_FREE_ADMISSION_PATTERN = re.compile(
    r"(?:\bfree\s+(?:admission|entry|event|registration|tickets?)\b|"
    r"\b(?:admission|entry|registration|tickets?)\s+(?:is|are|:)?\s*free\b|"
    r"(?:^|[.;]\s*)free(?:[.!;]|$|\s+donations?\b))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NormalizedEventPrice:
    minimum: Decimal
    maximum: Decimal
    currency: str
    source_text: str


def normalize_event_price(
    *,
    structured_price: object = None,
    structured_details: object = None,
    description: str | None = None,
) -> NormalizedEventPrice | None:
    """Normalize explicit admission prices, preferring provider-owned fields."""
    price_text = structured_price.strip() if isinstance(structured_price, str) else ""
    currency = _structured_currency(structured_details)
    has_structured_price = bool(price_text) or _has_structured_values(structured_details)

    if price_text:
        parsed = _parse_price_text(
            price_text,
            currency=currency,
            require_admission_context=False,
        )
        if parsed is not None:
            return parsed

    details_price = _price_from_structured_details(structured_details)
    if details_price is not None:
        return details_price
    if has_structured_price:
        return None

    if description:
        return _parse_price_text(
            description,
            currency="USD",
            require_admission_context=True,
        )
    return None


def _parse_price_text(
    value: str,
    *,
    currency: str,
    require_admission_context: bool,
) -> NormalizedEventPrice | None:
    text = " ".join(value.split())
    amounts: list[Decimal] = []
    accepted_spans: list[tuple[int, int]] = []

    for match in _RANGE_PATTERN.finditer(text):
        if not _accept_match(text, match.start(), match.end(), require_admission_context):
            continue
        amounts.extend(
            (
                Decimal(match.group("minimum")),
                Decimal(match.group("maximum")),
            )
        )
        accepted_spans.append(match.span())

    for match in _AMOUNT_PATTERN.finditer(text):
        if any(start <= match.start() < end for start, end in accepted_spans):
            continue
        if not _accept_match(text, match.start(), match.end(), require_admission_context):
            continue
        amounts.append(Decimal(match.group("amount")))
        accepted_spans.append(match.span())

    if amounts:
        return NormalizedEventPrice(
            minimum=min(amounts),
            maximum=max(amounts),
            currency=currency,
            source_text=_source_excerpt(text, accepted_spans),
        )

    free_match = _FREE_ADMISSION_PATTERN.search(text)
    if free_match is not None and _accept_match(
        text,
        free_match.start(),
        free_match.end(),
        require_admission_context=False,
    ):
        return NormalizedEventPrice(
            minimum=Decimal("0"),
            maximum=Decimal("0"),
            currency=currency,
            source_text="Free",
        )
    if not require_admission_context and text.casefold() == "free":
        return NormalizedEventPrice(
            minimum=Decimal("0"),
            maximum=Decimal("0"),
            currency=currency,
            source_text="Free",
        )
    return None


def _accept_match(
    text: str,
    start: int,
    end: int,
    require_admission_context: bool,
) -> bool:
    nearby = text[max(0, start - 70) : min(len(text), end + 70)]
    immediate = text[max(0, start - 35) : min(len(text), end + 20)]
    if _EXCLUDED_CONTEXT_PATTERN.search(immediate):
        return False
    return not require_admission_context or _ADMISSION_CONTEXT_PATTERN.search(nearby) is not None


def _source_excerpt(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text[:200]
    start = max(text.rfind(".", 0, spans[0][0]) + 1, text.rfind(";", 0, spans[0][0]) + 1)
    final_end = spans[-1][1]
    sentence_end_candidates = [
        position
        for position in (text.find(".", final_end), text.find(";", final_end))
        if position >= 0
    ]
    end = min(sentence_end_candidates) + 1 if sentence_end_candidates else len(text)
    excerpt = text[start:end].strip()
    return excerpt if len(excerpt) <= 200 else excerpt[:197].rstrip() + "..."


def _structured_currency(value: object) -> str:
    if isinstance(value, dict):
        details = cast(dict[object, object], value)
        currency_code = details.get("currency_code")
        if isinstance(currency_code, str) and len(currency_code.strip()) == 3:
            return currency_code.strip().upper()
    return "USD"


def _has_structured_values(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    details = cast(dict[object, object], value)
    values = details.get("values")
    return isinstance(values, list) and bool(values)


def _price_from_structured_details(value: object) -> NormalizedEventPrice | None:
    if not isinstance(value, dict):
        return None
    details = cast(dict[object, object], value)
    raw_values = details.get("values")
    if not isinstance(raw_values, list):
        return None

    amounts: list[Decimal] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, (str, int, float)) or isinstance(raw_value, bool):
            continue
        try:
            amount = Decimal(str(raw_value))
        except InvalidOperation:
            continue
        if amount >= 0:
            amounts.append(amount)

    if not amounts:
        return None

    currency = _structured_currency(value)
    minimum = min(amounts)
    maximum = max(amounts)
    if minimum == maximum == 0:
        source_text = "Free"
    elif minimum == maximum:
        source_text = "$" + f"{minimum:g}"
    else:
        source_text = "$" + f"{minimum:g}" + "–$" + f"{maximum:g}"
    return NormalizedEventPrice(
        minimum=minimum,
        maximum=maximum,
        currency=currency,
        source_text=source_text,
    )
