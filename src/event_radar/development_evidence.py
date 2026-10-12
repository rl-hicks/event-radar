"""Local public-evidence CLI. Offline discovery has no live composition path."""

import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from event_radar.db.config import postgres_url
from event_radar.db.evidence import export_run, export_snapshot, integrity_envelope
from event_radar.db.session import build_engine
from event_radar.models.regional_discovery import (
    CoverageGap,
    DiscoveryBudget,
    DiscoveryContext,
    DiscoveryPlan,
    DiscoveryTask,
)
from event_radar.shared.discovery import DiscoveryProviderResponse
from event_radar.shared.discovery_only import diagnose_snapshot
from event_radar.shared.synthetic import SyntheticDiscovery, synthetic_usage


class OfflineDiscovery(SyntheticDiscovery):
    """One deterministic fake wave regardless of the persisted inventory size."""

    def __init__(self) -> None:
        self.planned = False

    async def plan(self, context: DiscoveryContext) -> DiscoveryProviderResponse[DiscoveryPlan]:
        first = not self.planned
        self.planned = True
        return DiscoveryProviderResponse(
            value=DiscoveryPlan(
                gaps=(
                    CoverageGap(
                        gap_id="offline-exercise",
                        dimension="general",
                        priority="low",
                        description="Synthetic harness exercise; not a real coverage finding.",
                        rationale="Exercise the existing research and verification contracts.",
                    ),
                )
                if first
                else (),
                tasks=(
                    DiscoveryTask(
                        task_id="offline-task",
                        gap_ids=("offline-exercise",),
                        search_goal="Return an in-process synthetic candidate only.",
                    ),
                )
                if first
                else (),
                should_continue=first,
                rationale="Deterministic offline diagnostic, not regional completeness.",
            ),
            usage=synthetic_usage(),
            latency_seconds=0,
        )


def evidence_url(value: str) -> URL:
    url = postgres_url(value)
    if (
        url.host != "127.0.0.1"
        or url.port != 55433
        or url.database != "event_radar_evidence"
        or url.username != "event_radar_evidence"
        or url.query
    ):
        raise ValueError("Evidence URL must target the dedicated local evidence service.")
    if any(name.startswith("PG") for name in os.environ):
        raise ValueError("Remove libpq PG* overrides before evidence operations.")
    return url


def install_offline_guard() -> None:
    """Process-lifetime guard for this CLI, before composing any dependencies."""

    def audit(event: str, args: tuple[object, ...]) -> None:
        if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"):
            raise RuntimeError("Offline diagnostic prohibits external I/O.")
        if event == "import" and str(args[0]).startswith(
            (
                "openai",
                "event_radar.services.",
                "event_radar.shared_runtime",
                "event_radar.shared_worker",
                "event_radar.config",
            )
        ):
            raise RuntimeError("Offline diagnostic prohibits live adapter imports.")

    sys.addaudithook(audit)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "discover-offline"):
        commands.add_parser(name).add_argument("--snapshot-id", type=UUID, required=True)
    commands.add_parser("export-run").add_argument("--run-id", type=UUID, required=True)
    args = parser.parse_args()
    try:
        if args.command == "discover-offline":
            install_offline_guard()
        url = evidence_url(os.environ.get("EVIDENCE_DATABASE_URL", ""))
        engine = build_engine(url)
        try:
            with Session(engine) as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                identity = session.execute(text("SELECT current_database(), current_user")).one()
                if tuple(identity) != ("event_radar_evidence", "event_radar_evidence"):
                    raise ValueError("Evidence database identity mismatch.")
                if args.command == "export-run":
                    payload = export_run(session, args.run_id)
                elif args.command == "export":
                    payload = export_snapshot(session, args.snapshot_id)
                else:
                    # Fixed in-process fake composition. No environment-selected adapter, model,
                    # dynamic import, shared worker, collection, or initial semantic service.
                    fake = OfflineDiscovery()
                    report = asyncio.run(
                        diagnose_snapshot(
                            session,
                            args.snapshot_id,
                            fake,
                            fake,
                            fake,
                            budget=DiscoveryBudget(
                                max_waves=2,
                                max_model_calls=8,
                                max_web_search_calls=4,
                                max_model_cost_usd=Decimal("1"),
                            ),
                        )
                    )
                    report["execution_mode"] = "offline-synthetic"
                    payload = integrity_envelope(report)
        finally:
            engine.dispose()
        directory = Path("output/development-evidence")
        directory.mkdir(parents=True, exist_ok=True)
        identifier = args.run_id if args.command == "export-run" else args.snapshot_id
        target = directory / f"{args.command}-{identifier}-{uuid4()}.json"
        with target.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        print(target)
        return 0
    except Exception:
        # Never emit DB connection strings, provider exception bodies or validation input.
        print(
            "Evidence operation failed; check local target, migration state and snapshot integrity."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
