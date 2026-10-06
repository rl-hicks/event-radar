"""Standalone shared-worker CLI. Currently exposes only a no-spend synthetic mode."""

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
    parser.add_argument("--synthetic", action="store_true", required=True)
    parser.add_argument(
        "--refresh", action="store_true", help="Explicitly research an existing key again"
    )
    args = parser.parse_args(argv)
    engine = None
    try:
        if not args.policy_version.startswith("synthetic-"):
            raise ValueError("Synthetic runs require a separate policy namespace.")
        scope = ResearchScope(
            region=SONOMA_COUNTY,
            window=WeekendWindow(friday=args.weekend, timezone=SONOMA_COUNTY.timezone),
            research_policy_version=args.policy_version,
            as_of=args.as_of,
        )
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
