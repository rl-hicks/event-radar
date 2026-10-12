from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, TypedDict, cast

from pydantic import BaseModel


class ModelPricingRatesLike(Protocol):
    input_usd_per_million: float
    cached_input_usd_per_million: float | None
    output_usd_per_million: float


@dataclass(frozen=True)
class ModelTokenPricing:
    input_usd_per_million: float
    cached_input_usd_per_million: float | None
    output_usd_per_million: float

    @classmethod
    def from_rates(cls, rates: ModelPricingRatesLike | None) -> "ModelTokenPricing | None":
        if rates is None:
            return None
        return cls(
            rates.input_usd_per_million,
            rates.cached_input_usd_per_million,
            rates.output_usd_per_million,
        )

    @classmethod
    def from_mapping(
        cls, pricing: Mapping[str, ModelPricingRatesLike], model: str
    ) -> "ModelTokenPricing | None":
        return cls.from_rates(pricing.get(model))

    @classmethod
    def from_settings(cls, config: Any, model: str) -> "ModelTokenPricing | None":
        """Compatibility adapter without importing the legacy Settings module."""
        pricing = cast(
            Mapping[str, ModelPricingRatesLike],
            config.openai_model_pricing,
        )
        return cls.from_mapping(pricing, model)


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_model_cost_usd: float | None = None


def parse_token_usage(usage: object, pricing: ModelTokenPricing | None) -> TokenUsage:
    """Missing counts remain unknown; absent cache details assume no cache discount.

    Estimates cover model tokens only, excluding web-search fees and tier premiums.
    """

    def count(source: object, name: str) -> int | None:
        value = getattr(source, name, None)
        return value if type(value) is int and value >= 0 else None

    result = TokenUsage(
        input_tokens=count(usage, "input_tokens"),
        cached_input_tokens=count(getattr(usage, "input_tokens_details", None), "cached_tokens"),
        output_tokens=count(usage, "output_tokens"),
        total_tokens=count(usage, "total_tokens"),
    )
    if pricing is not None and result.input_tokens is not None and result.output_tokens is not None:
        cached = result.cached_input_tokens or 0
        if cached and pricing.cached_input_usd_per_million is None:
            return result
        normal = max(result.input_tokens - cached, 0)
        result.estimated_model_cost_usd = float(
            (
                normal * Decimal(str(pricing.input_usd_per_million))
                + cached * Decimal(str(pricing.cached_input_usd_per_million or 0))
                + result.output_tokens * Decimal(str(pricing.output_usd_per_million))
            )
            / Decimal(1_000_000)
        )
    return result


def aggregate_token_usage(items: Iterable[TokenUsage]) -> TokenUsage:
    """Sum available telemetry, never treating an entirely unknown field as zero.

    With missing responses these are known subtotals, not a complete billing total.
    Costs are summed per request so missing cache fields cannot shift cache discounts
    between requests. Preserve unrounded costs until human-readable formatting.
    """
    values = list(items)
    totals: dict[str, int | float | None] = {}
    for field in TokenUsage.model_fields:
        known = [getattr(item, field) for item in values if getattr(item, field) is not None]
        totals[field] = (
            float(sum(Decimal(str(value)) for value in known))
            if known and field == "estimated_model_cost_usd"
            else sum(known)
            if known
            else None
        )
    return TokenUsage.model_validate(totals)


class TokenUsageFields(TypedDict):
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_model_cost_usd: float | None


def token_usage_fields(usage: TokenUsage) -> TokenUsageFields:
    return TokenUsageFields(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        estimated_model_cost_usd=usage.estimated_model_cost_usd,
    )


def format_token_usage(usage: TokenUsage) -> str:
    fields = []
    for field in TokenUsage.model_fields:
        value = getattr(usage, field)
        formatted = (
            "n/a"
            if value is None
            else f"{value:.4f}"
            if field == "estimated_model_cost_usd"
            else str(value)
        )
        fields.append(f"{field}={formatted}")
    return " ".join(fields)
