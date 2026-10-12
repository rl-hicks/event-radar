"""Standalone shared-worker CLI. Explicit synthetic or guarded real mode."""

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal

from event_radar.db.config import postgres_url
from event_radar.db.session import build_engine
from event_radar.models.regional import SONOMA_COUNTY, ResearchScope, WeekendWindow
from event_radar.models.regional_discovery import DiscoveryBudget
from event_radar.shared.collection import SourceRegistration, SourceRegistry
from event_radar.shared.synthetic import SyntheticDiscovery, SyntheticSemantics, SyntheticSource
from event_radar.shared.worker import ResearchBudget, WorkerDependencies, run_regional_worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=["sonoma-county-ca"], required=True)
    parser.add_argument(
        "--weekend", type=date.fromisoformat, required=True, help="Friday YYYY-MM-DD"
    )
    parser.add_argument(
        "--as-of", type=datetime.fromisoformat, required=True, help="Aware ISO timestamp"
    )
    parser.add_argument(
        "--policy-version", required=True, help="Synthetic mode requires synthetic- prefix"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true")
    mode.add_argument("--real", action="store_true")
    parser.add_argument(
        "--acknowledge-live-run",
        action="store_true",
        help="Runtime guard only; does not grant owner authorization",
    )
    parser.add_argument("--database-session-mode", choices=["direct", "session"])
    parser.add_argument("--semantic-model")
    parser.add_argument("--discovery-model")
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--semantic-batch-size", type=int)
    parser.add_argument("--max-waves", type=int)
    parser.add_argument("--max-model-calls", type=int)
    parser.add_argument("--max-web-search-calls", type=int)
    parser.add_argument("--max-model-cost-usd", type=Decimal)
    parser.add_argument(
        "--semantic-pricing",
        type=float,
        nargs=3,
        metavar=("INPUT", "CACHED_INPUT", "OUTPUT"),
        help="Explicit USD per million model tokens",
    )
    parser.add_argument(
        "--discovery-pricing",
        type=float,
        nargs=3,
        metavar=("INPUT", "CACHED_INPUT", "OUTPUT"),
        help="Explicit USD per million model tokens",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Explicitly research an existing key again"
    )
    args = parser.parse_args(argv)
    engine = None
    try:
        if args.synthetic and not args.policy_version.startswith("synthetic-"):
            raise ValueError("Synthetic runs require a separate policy namespace.")
        scope = ResearchScope(
            region=SONOMA_COUNTY,
            window=WeekendWindow(friday=args.weekend, timezone=SONOMA_COUNTY.timezone),
            research_policy_version=args.policy_version,
            as_of=args.as_of,
        )
        if args.real:
            # Lazy import keeps the existing synthetic process isolated from providers.
            from event_radar.shared_runtime import (
                RealRuntimeConfig,
                execute_real,
                research_secrets,
            )

            rates = (
                "input_usd_per_million",
                "cached_input_usd_per_million",
                "output_usd_per_million",
            )
            config = RealRuntimeConfig.model_validate(
                {
                    "scope": scope,
                    **research_secrets(os.environ),
                    "semantic_model": args.semantic_model,
                    "discovery_model": args.discovery_model,
                    "timeout_seconds": args.timeout_seconds,
                    "semantic_batch_size": args.semantic_batch_size,
                    "discovery_budget": {
                        "max_waves": args.max_waves,
                        "max_model_calls": args.max_model_calls,
                        "max_web_search_calls": args.max_web_search_calls,
                        "max_model_cost_usd": args.max_model_cost_usd,
                    },
                    "semantic_pricing": dict(zip(rates, args.semantic_pricing or (), strict=True)),
                    "discovery_pricing": dict(
                        zip(rates, args.discovery_pricing or (), strict=True)
                    ),
                    "database_session_mode": args.database_session_mode,
                    "acknowledge_live_run": args.acknowledge_live_run,
                }
            )
            result = asyncio.run(execute_real(config, refresh=args.refresh))
        else:
            # Do not load .env or allow a synthetic smoke command to touch hosted state.
            # This deliberately mirrors the repository's disposable database boundary.
            url = postgres_url(os.environ.get("TEST_DATABASE_URL", ""))
            if (
                (url.host, url.port, url.database, url.username)
                != ("127.0.0.1", 55432, "event_radar_test", "event_radar_test")
                or url.query
                or any(name.startswith("PG") for name in os.environ)
            ):
                raise ValueError("Synthetic CLI requires the dedicated disposable database.")
            engine = build_engine(url)
            discovery = SyntheticDiscovery()
            result = asyncio.run(
                run_regional_worker(
                    scope,
                    WorkerDependencies(
                        engine=engine,
                        registry=SourceRegistry((SourceRegistration(SyntheticSource()),)),
                        semantic_provider=SyntheticSemantics(),
                        planner=discovery,
                        researcher=discovery,
                        verifier=discovery,
                    ),
                    budget=ResearchBudget(
                        discovery=DiscoveryBudget(
                            max_waves=2,
                            max_model_calls=4,
                            max_web_search_calls=2,
                            max_model_cost_usd=Decimal("0.01"),
                        ),
                        timeout_seconds=60,
                    ),
                    refresh=args.refresh,
                )
            )
        print(json.dumps(asdict(result), default=str, sort_keys=True))
        return 0 if result.status in ("success", "replayed") else 2
    except Exception:
        print(json.dumps({"status": "failed", "failure_code": "unavailable"}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
