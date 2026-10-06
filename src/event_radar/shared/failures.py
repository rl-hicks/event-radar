"""Safe classifications only: never exception text, payloads or arbitrary class names."""

import asyncio
from math import isfinite

from pydantic import ValidationError

from event_radar.models.regional import FailureCategory, FailureCode
from event_radar.models.token_usage import TokenUsage


def classify_failure(error: BaseException) -> tuple[FailureCode, FailureCategory]:
    if isinstance(error, asyncio.CancelledError):
        return "unavailable", "cancelled"
    if isinstance(error, TimeoutError):
        return "timeout", "timeout"
    if isinstance(error, ValidationError):
        return "invalid_response", "local_validation"
    return "invalid_response", "local_invariant"


def safe_usage(usage: TokenUsage) -> TokenUsage:
    """Retain known numeric subtotals; inconsistent fields remain unknown.

    This also prevents malformed provider telemetry from breaking the failure
    reporter itself. Unknown totals are never claimed as complete accounting.
    """

    def count(value: object) -> int | None:
        return value if type(value) is int and value >= 0 else None

    inputs = count(usage.input_tokens)
    cached = count(usage.cached_input_tokens)
    outputs = count(usage.output_tokens)
    total = count(usage.total_tokens)
    if cached is not None and inputs is not None and cached > inputs:
        cached = None
    if (
        total is not None
        and inputs is not None
        and outputs is not None
        and total != inputs + outputs
    ):
        total = None
    cost = usage.estimated_model_cost_usd
    if cost is not None and (not isfinite(cost) or cost < 0):
        cost = None
    return TokenUsage(
        input_tokens=inputs,
        cached_input_tokens=cached,
        output_tokens=outputs,
        total_tokens=total,
        estimated_model_cost_usd=cost,
    )
