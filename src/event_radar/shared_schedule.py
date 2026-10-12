"""Shared schedule planning/execution/evidence. No consumer or personal inputs."""

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from event_radar.db.config import research_database_url
from event_radar.db.evidence import export_run, export_snapshot, integrity_envelope
from event_radar.db.models import RegionalResearchRun, RegionalUniverse
from event_radar.db.session import build_engine
from event_radar.models.regional import SONOMA_COUNTY, Identifier, ResearchScope, WeekendWindow
from event_radar.models.regional_discovery import DiscoveryBudget
from event_radar.shared.spend_guard import WholeWorkerLimits

PACIFIC = ZoneInfo("America/Los_Angeles")
Rate = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class ScheduleEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    policy_version: Identifier
    semantic_model: Identifier
    discovery_model: Identifier
    semantic_pricing: tuple[Rate, Rate, Rate]
    discovery_pricing: tuple[Rate, Rate, Rate]
    semantic_batch_size: Annotated[int, Field(ge=1, le=100, strict=True)]
    timeout_seconds: Annotated[int, Field(ge=1, le=1800, strict=True)]
    database_session_mode: Literal["direct", "session"]
    discovery_budget: DiscoveryBudget
    whole_worker_limits: WholeWorkerLimits


def upcoming_friday(triggered_at: datetime) -> date:
    if triggered_at.tzinfo is None or triggered_at.utcoffset() is None:
        raise ValueError("An aware trigger timestamp is required.")
    day = triggered_at.astimezone(PACIFIC).date()
    return day + timedelta(days=(4 - day.weekday()) % 7)


def scheduled_scope(
    triggered_at: datetime,
    now: datetime,
    policy: str,
    weekend: date | None = None,
) -> ResearchScope:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("An aware execution timestamp is required.")
    friday = upcoming_friday(triggered_at)
    # Late/manual runs cannot silently roll an old workflow into another weekend.
    if not timedelta(0) <= now - triggered_at <= timedelta(hours=24):
        raise ValueError("Stale or future trigger requires operator review.")
    if triggered_at.astimezone(PACIFIC).weekday() not in (3, 4):
        raise ValueError("Weekly research starts on Pacific Thursday or Friday.")
    if weekend is not None and weekend != friday:
        raise ValueError("Explicit Friday must match the anchored research week.")
    return ResearchScope(
        region=SONOMA_COUNTY,
        window=WeekendWindow(friday=friday, timezone=PACIFIC.key),
        research_policy_version=policy,
        as_of=now.astimezone(PACIFIC),
    )


def database_preflight(engine: Engine, *, database: str, user: str) -> None:
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        if tuple(session.execute(text("SELECT current_database(), current_user")).one()) != (
            database,
            user,
        ):
            raise ValueError("Research database identity mismatch.")
        # 0003/0004 add private product state; regional schema remains compatible.
        if session.scalars(text("SELECT version_num FROM alembic_version")).all() not in (
            ["0002_regional_universes"],
            ["0003_user_context"],
            ["0004_weekend_packets"],
        ):
            raise ValueError("Required migration missing; no automatic migrations.")


def retained_evidence(engine: Engine, scope: ResearchScope) -> dict[str, object]:
    """Read only explicit public run/snapshot contracts, including an abandoned attempt."""
    with Session(engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        runs = session.scalars(
            select(RegionalResearchRun)
            .join(RegionalUniverse, RegionalResearchRun.universe_id == RegionalUniverse.id)
            .where(
                RegionalUniverse.region_id == scope.identity.region_id,
                RegionalUniverse.weekend_friday == scope.identity.friday,
                RegionalUniverse.research_policy_version == scope.identity.research_policy_version,
            )
            .order_by(RegionalResearchRun.started_at, RegionalResearchRun.id)
        ).all()
        return integrity_envelope(
            {
                "identity": scope.identity.model_dump(mode="json"),
                "availability": "exported" if runs else "unavailable",
                "runs": [export_run(session, run.id) for run in runs],
                "snapshots": [
                    export_snapshot(session, identifier)
                    for identifier in dict.fromkeys(
                        run.snapshot_id for run in runs if run.snapshot_id
                    )
                ],
            }
        )


def accounting_review(evidence: dict[str, object]) -> dict[str, object]:
    """Latest attempt only; never double-count exports of historical runs."""
    payload = cast(dict[str, object], evidence["payload"])
    runs = cast(list[dict[str, object]], payload["runs"])
    if not runs:
        return {"known_model_cost_usd": None, "incomplete": True, "web_search_fees_usd": None}
    run_payload = cast(dict[str, object], runs[-1]["payload"])
    record = cast(dict[str, object], run_payload["record"])
    stages = cast(list[dict[str, object]], record["diagnostics"])
    active = [stage for stage in stages if stage["status"] != "skipped"]
    known = sum(
        (
            Decimal(str(stage["estimated_model_cost_usd"]))
            for stage in active
            if stage["estimated_model_cost_usd"] is not None
        ),
        Decimal(0),
    )
    incomplete = not active or any(not stage["usage_complete"] for stage in active)
    summary = cast(dict[str, object] | None, record["discovery_summary"])
    usage = cast(dict[str, object], summary["usage"]) if summary else {}
    searches = usage.get("web_search_calls")
    tools_complete = bool(usage.get("web_search_calls_complete"))
    return {
        "known_model_cost_usd": str(known),
        "incomplete": incomplete or (summary is not None and not tools_complete),
        "web_search_calls": searches,
        "web_search_calls_complete": tools_complete,
        "web_search_fees_usd": "0" if searches == 0 and tools_complete else None,
        "billing_total_usd": None,
    }


def save_public(directory: Path, prefix: str, value: dict[str, object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{prefix}-{uuid4()}.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "execute", "export"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--triggered-at", type=datetime.fromisoformat)
    parser.add_argument("--weekend", type=date.fromisoformat)
    parser.add_argument("--acknowledge-live-run", action="store_true")
    args = parser.parse_args(argv)
    started = datetime.now(UTC)
    directory = Path("output/development-evidence")
    scope = None
    engine = None
    receipt: dict[str, object] = {"started_at": started.isoformat(), "status": "failed"}
    exit_code = 2
    try:
        envelope = ScheduleEnvelope.model_validate_json(args.config.read_text())
        if args.command == "export":
            if args.weekend is None:
                raise ValueError("Read-only recovery export requires explicit Friday.")
            scope = ResearchScope(
                region=SONOMA_COUNTY,
                window=WeekendWindow(friday=args.weekend, timezone=PACIFIC.key),
                research_policy_version=envelope.policy_version,
                as_of=started,
            )
        else:
            if args.triggered_at is None:
                raise ValueError("Immutable workflow creation time is required.")
            scope = scheduled_scope(
                args.triggered_at, started, envelope.policy_version, args.weekend
            )
        receipt["identity"] = scope.identity.model_dump(mode="json")
        receipt["requested_as_of"] = scope.as_of.isoformat()
        receipt["envelope"] = envelope.model_dump(mode="json")
        if args.command == "plan":
            print(
                json.dumps(
                    {
                        "weekend": scope.identity.friday.isoformat(),
                        "key": scope.identity.key,
                        "paid_execution": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "execute" and (
            not args.acknowledge_live_run
            or os.environ.get("EVENT_RADAR_SCHEDULE_APPROVED") != "true"
        ):
            raise ValueError("Separate operating approval is required.")
        if any(name.startswith("PG") for name in os.environ):
            raise ValueError("Remove libpq overrides.")
        url = research_database_url(os.environ.get("EVENT_RADAR_RESEARCH_DATABASE_URL", ""))
        if url.host != os.environ.get("EVENT_RADAR_RESEARCH_EXPECTED_HOST"):
            raise ValueError("Research host mismatch.")
        if url.host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Hosted schedule requires an explicitly approved remote target.")
        engine = build_engine(url)
        database_preflight(
            engine,
            database=os.environ.get("EVENT_RADAR_RESEARCH_EXPECTED_DATABASE", ""),
            user=os.environ.get("EVENT_RADAR_RESEARCH_EXPECTED_USER", ""),
        )
        receipt["database_status"] = "ready"
        if args.command == "execute":
            # Import live composition only past acknowledgement, target and migration checks.
            from event_radar.shared_runtime import (
                RealRuntimeConfig,
                TokenPricing,
                execute_real,
                research_secrets,
            )

            def pricing(values: tuple[float, float, float]) -> TokenPricing:
                return TokenPricing(
                    input_usd_per_million=values[0],
                    cached_input_usd_per_million=values[1],
                    output_usd_per_million=values[2],
                )

            config = RealRuntimeConfig(
                scope=scope,
                **research_secrets(os.environ),
                semantic_model=envelope.semantic_model,
                discovery_model=envelope.discovery_model,
                semantic_pricing=pricing(envelope.semantic_pricing),
                discovery_pricing=pricing(envelope.discovery_pricing),
                timeout_seconds=envelope.timeout_seconds,
                semantic_batch_size=envelope.semantic_batch_size,
                discovery_budget=envelope.discovery_budget,
                database_session_mode=envelope.database_session_mode,
                acknowledge_live_run=True,
            )
            result = asyncio.run(
                execute_real(
                    config,
                    attempt_once=True,
                    whole_worker_limits=envelope.whole_worker_limits,
                )
            )
            receipt.update(json.loads(json.dumps(asdict(result), default=str)))
            exit_code = 0 if result.status in ("success", "replayed") else 2
        else:
            receipt["status"] = "read_only"
            exit_code = 0
    except Exception:
        # No exception body, SQL/connection string, provider payload, or secret.
        receipt["status"] = "failed"
        receipt["failure_code"] = "unavailable"
    finally:
        if args.command != "plan":
            if (
                engine is not None
                and scope is not None
                and receipt.get("database_status") == "ready"
            ):
                try:
                    evidence = retained_evidence(engine, scope)
                    receipt["evidence_path"] = str(
                        save_public(directory, "schedule-evidence", evidence)
                    )
                    receipt["evidence_status"] = "saved"
                    accounting = accounting_review(evidence)
                    receipt["accounting"] = accounting
                    if accounting["incomplete"]:
                        receipt["attention_required"] = "incomplete_accounting"
                        exit_code = 2
                except Exception:
                    receipt["evidence_status"] = "unavailable"
                    exit_code = 2
                finally:
                    engine.dispose()
            if engine is not None and receipt.get("database_status") != "ready":
                engine.dispose()
            receipt["finished_at"] = datetime.now(UTC).isoformat()
            save_public(directory, "schedule-receipt", integrity_envelope(receipt))
            # Only bounded status in public logs; full public evidence is in explicit artifacts.
            print(json.dumps({"status": receipt["status"], "exit_code": exit_code}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
