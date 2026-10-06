"""Explicit public-only runtime composition. Import and configuration never run research."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy.engine import URL

from event_radar.collectors.regional_sources import default_sonoma_source_registry
from event_radar.db.config import postgres_url
from event_radar.db.session import build_engine
from event_radar.models.regional import Identifier, ResearchScope
from event_radar.models.regional_discovery import DiscoveryBudget
from event_radar.models.token_usage import ModelTokenPricing
from event_radar.services.adaptive_regional_discovery import OpenAIAdaptiveDiscoveryProvider
from event_radar.services.hike_catalog import HikeCatalogRepository
from event_radar.services.regional_semantic_analysis import OpenAIRegionalSemanticProvider
from event_radar.shared.worker import (
    ResearchBudget,
    WorkerDependencies,
    WorkerResult,
    run_regional_worker,
)

DATABASE_ENV = "EVENT_RADAR_RESEARCH_DATABASE_URL"
API_KEY_ENV = "EVENT_RADAR_RESEARCH_OPENAI_API_KEY"
ASSET_ROOT = Path(__file__).resolve().parents[2]
PROMPT_NAMES = (
    "regional_semantic_analysis.md",
    "regional_discovery_plan.md",
    "regional_discovery_research.md",
    "regional_discovery_verify.md",
)


class TokenPricing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    input_usd_per_million: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    cached_input_usd_per_million: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    output_usd_per_million: Annotated[float, Field(gt=0, allow_inf_nan=False)]

    def rates(self) -> ModelTokenPricing:
        return ModelTokenPricing(
            self.input_usd_per_million,
            self.cached_input_usd_per_million,
            self.output_usd_per_million,
        )


class RealRuntimeConfig(BaseModel):
    """No defaults for live inputs. An acknowledgement is not owner authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    scope: ResearchScope
    database_url: SecretStr
    api_key: SecretStr
    semantic_model: Identifier
    discovery_model: Identifier
    timeout_seconds: Annotated[float, Field(gt=0, le=3600, allow_inf_nan=False)]
    semantic_batch_size: Annotated[int, Field(ge=1, strict=True)]
    discovery_budget: DiscoveryBudget
    semantic_pricing: TokenPricing
    discovery_pricing: TokenPricing
    database_session_mode: Literal["direct", "session"]
    acknowledge_live_run: Literal[True]

    @model_validator(mode="after")
    def validate_runtime(self) -> RealRuntimeConfig:
        if not self.api_key.get_secret_value().strip():
            raise ValueError("Dedicated research API key is required.")
        if self.scope.research_policy_version.startswith("synthetic-"):
            raise ValueError("Real runs cannot use the synthetic policy namespace.")
        self.postgres_url()
        return self

    def postgres_url(self) -> URL:
        url = postgres_url(self.database_url.get_secret_value())
        if (
            not url.host
            or not url.username
            or not url.password
            or not url.database
            or url.port is None
            or not 1 <= url.port <= 65535
            or url.port == 6543
            or set(url.query) - {"sslmode"}
        ):
            raise ValueError("Explicit direct/session PostgreSQL target is required.")
        local = url.host in {"localhost", "127.0.0.1", "::1"}
        if not local and url.query.get("sslmode") != "verify-full":
            raise ValueError("Remote research PostgreSQL requires sslmode=verify-full.")
        if local and url.query.get("sslmode") not in (None, "disable", "require", "verify-full"):
            raise ValueError("Unsupported local PostgreSQL SSL mode.")
        return url

    def research_budget(self) -> ResearchBudget:
        return ResearchBudget(
            discovery=self.discovery_budget,
            timeout_seconds=self.timeout_seconds,
            semantic_batch_size=self.semantic_batch_size,
        )


def research_secrets(environment: Mapping[str, str]) -> dict[str, SecretStr]:
    """Read only named worker secrets; reject libpq target redirection."""
    if any(name.startswith("PG") for name in environment):
        raise ValueError("Remove libpq overrides before shared research.")
    database = environment.get(DATABASE_ENV, "")
    key = environment.get(API_KEY_ENV, "")
    if not database.strip() or not key.strip():
        raise ValueError("Dedicated shared-research credentials are required.")
    return {"database_url": SecretStr(database), "api_key": SecretStr(key)}


def build_real_dependencies(
    config: RealRuntimeConfig,
    *,
    client: AsyncOpenAI,
) -> WorkerDependencies:
    """Construct production components without connections or provider calls.

    Caller owns the injected client and returned engine. Paths are repository
    assets, independent of the invoking shell's cwd. No private state is read.
    """
    prompts = tuple(ASSET_ROOT / "prompts" / name for name in PROMPT_NAMES)
    catalog = ASSET_ROOT / "data" / "hikes.json"
    if not all(path.is_file() for path in (*prompts, catalog)):
        raise ValueError("Required public research assets are missing.")
    registry = default_sonoma_source_registry(
        user_agent="EventRadarSharedResearch/1.0",
        timeout_seconds=config.timeout_seconds,
        hike_repository=HikeCatalogRepository(catalog),
    )
    semantic = OpenAIRegionalSemanticProvider(
        api_key=None,
        model_id=config.semantic_model,
        prompt_path=prompts[0],
        timeout_seconds=config.timeout_seconds,
        client=client,
        pricing=config.semantic_pricing.rates(),
    )
    discovery = OpenAIAdaptiveDiscoveryProvider(
        api_key=None,
        model_id=config.discovery_model,
        planning_prompt_path=prompts[1],
        research_prompt_path=prompts[2],
        verification_prompt_path=prompts[3],
        timeout_seconds=config.timeout_seconds,
        max_web_search_calls_per_request=max(1, config.discovery_budget.max_web_search_calls),
        client=client,
        pricing=config.discovery_pricing.rates(),
    )
    return WorkerDependencies(
        engine=build_engine(config.postgres_url()),
        registry=registry,
        semantic_provider=semantic,
        planner=discovery,
        researcher=discovery,
        verifier=discovery,
    )


async def execute_real(config: RealRuntimeConfig, *, refresh: bool = False) -> WorkerResult:
    """Execution boundary; call only for a separately owner-authorized envelope."""
    # Explicit endpoint and transport avoid ambient OpenAI base URL/proxy settings.
    async with httpx.AsyncClient(trust_env=False, timeout=config.timeout_seconds) as transport:
        async with AsyncOpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url="https://api.openai.com/v1",
            timeout=config.timeout_seconds,
            max_retries=0,
            http_client=transport,
        ) as client:
            dependencies = build_real_dependencies(config, client=client)
            try:
                return await run_regional_worker(
                    config.scope,
                    dependencies,
                    budget=config.research_budget(),
                    refresh=refresh,
                )
            finally:
                dependencies.engine.dispose()
