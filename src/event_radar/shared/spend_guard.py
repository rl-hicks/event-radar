"""One in-memory call/estimate guard shared by both semantic stages and WP5.

This is a post-response estimate, not prepaid billing enforcement. No retries.
Unknown usage or a failed call closes this guard for the rest of the attempt.
"""

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from event_radar.models.regional import RegionalAnalysisRequest
from event_radar.models.regional_discovery import (
    DiscoveredEventCandidate,
    DiscoveryContext,
    DiscoveryPlan,
    DiscoveryResearchResult,
    DiscoveryTask,
    DiscoveryVerificationResult,
)
from event_radar.models.token_usage import TokenUsage
from event_radar.shared.discovery import (
    DiscoveryPlanner,
    DiscoveryProviderFailure,
    DiscoveryProviderResponse,
    DiscoveryResearcher,
    DiscoveryVerifier,
)
from event_radar.shared.semantic_analysis import (
    RegionalSemanticProvider,
    SemanticProviderFailure,
    SemanticProviderResponse,
)
from event_radar.shared.worker import WorkerDependencies


class WholeWorkerLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    max_model_calls: Annotated[int, Field(ge=1, le=200, strict=True)]
    max_estimated_model_cost_usd: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


@dataclass
class SpendGuard:
    limits: WholeWorkerLimits
    calls: int = 0
    cost: Decimal = Decimal(0)
    complete: bool = True

    def reserve(self) -> bool:
        if (
            not self.complete
            or self.calls >= self.limits.max_model_calls
            or self.cost >= self.limits.max_estimated_model_cost_usd
        ):
            return False
        self.calls += 1
        return True

    def observe(self, usage: TokenUsage) -> None:
        values = (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
            usage.total_tokens,
            usage.estimated_model_cost_usd,
        )
        self.complete = self.complete and all(value is not None for value in values)
        if usage.estimated_model_cost_usd is not None:
            self.cost += Decimal(str(usage.estimated_model_cost_usd))


ZERO = TokenUsage(
    input_tokens=0,
    cached_input_tokens=0,
    output_tokens=0,
    total_tokens=0,
    estimated_model_cost_usd=0,
)


@dataclass
class GuardedSemantics:
    provider: RegionalSemanticProvider
    guard: SpendGuard

    model_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.model_id = self.provider.model_id

    async def analyze(
        self, request: RegionalAnalysisRequest, *, correction: str | None = None
    ) -> SemanticProviderResponse:
        if not self.guard.reserve():
            raise SemanticProviderFailure(
                "rate_limited", attempts=0, usage=ZERO, category="configuration"
            )
        try:
            result = await self.provider.analyze(request, correction=correction)
        except BaseException:
            self.guard.complete = False
            raise
        self.guard.observe(result.usage)
        return result


@dataclass
class GuardedDiscovery:
    planner: DiscoveryPlanner
    researcher: DiscoveryResearcher
    verifier: DiscoveryVerifier
    guard: SpendGuard

    model_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.model_id = self.planner.model_id

    def reserve(self) -> None:
        if not self.guard.reserve():
            raise DiscoveryProviderFailure(
                "rate_limited",
                attempts=0,
                usage=ZERO,
                category="configuration",
                reason="configuration",
                tool_calls=0,
                tool_calls_complete=True,
            )

    async def plan(self, context: DiscoveryContext) -> DiscoveryProviderResponse[DiscoveryPlan]:
        self.reserve()
        try:
            result = await self.planner.plan(context)
        except BaseException:
            self.guard.complete = False
            raise
        self.guard.observe(result.usage)
        return result

    async def research(
        self, context: DiscoveryContext, task: DiscoveryTask, *, max_web_search_calls: int
    ) -> DiscoveryProviderResponse[DiscoveryResearchResult]:
        self.reserve()
        try:
            result = await self.researcher.research(
                context, task, max_web_search_calls=max_web_search_calls
            )
        except BaseException:
            self.guard.complete = False
            raise
        self.guard.observe(result.usage)
        return result

    async def verify(
        self,
        context: DiscoveryContext,
        candidates: tuple[DiscoveredEventCandidate, ...],
        *,
        max_web_search_calls: int,
    ) -> DiscoveryProviderResponse[DiscoveryVerificationResult]:
        self.reserve()
        try:
            result = await self.verifier.verify(
                context, candidates, max_web_search_calls=max_web_search_calls
            )
        except BaseException:
            self.guard.complete = False
            raise
        self.guard.observe(result.usage)
        return result


def guard_dependencies(deps: WorkerDependencies, limits: WholeWorkerLimits) -> WorkerDependencies:
    guard = SpendGuard(limits)
    discovery = GuardedDiscovery(deps.planner, deps.researcher, deps.verifier, guard)
    return replace(
        deps,
        semantic_provider=GuardedSemantics(deps.semantic_provider, guard),
        planner=discovery,
        researcher=discovery,
        verifier=discovery,
    )
