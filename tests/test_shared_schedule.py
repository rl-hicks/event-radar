"""Deterministic schedule/activation/whole-worker budget regressions."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from event_radar.models.token_usage import TokenUsage
from event_radar.shared.spend_guard import SpendGuard, WholeWorkerLimits
from event_radar.shared_schedule import ScheduleEnvelope, main, scheduled_scope, upcoming_friday

CONFIG = Path("config/shared-research-envelope.json")


@pytest.mark.parametrize(
    "anchor,friday",
    [
        ("2026-03-05T20:15:00+00:00", "2026-03-06"),
        ("2026-03-12T19:15:00+00:00", "2026-03-13"),
        ("2026-10-29T19:15:00+00:00", "2026-10-30"),
        ("2026-11-05T20:15:00+00:00", "2026-11-06"),
        ("2026-12-31T20:15:00+00:00", "2027-01-01"),
        ("2026-10-16T06:59:00+00:00", "2026-10-16"),
        ("2026-10-16T07:01:00+00:00", "2026-10-16"),
    ],
)
def test_pacific_weekend_and_dst(anchor, friday):
    trigger = datetime.fromisoformat(anchor)
    first = scheduled_scope(trigger, trigger, "synthetic-schedule")
    rerun = scheduled_scope(trigger, trigger + timedelta(hours=1), "synthetic-schedule")
    assert first.identity == rerun.identity
    assert first.identity.friday.isoformat() == friday
    assert first.window.timezone == "America/Los_Angeles"
    assert first.as_of != rerun.as_of


def test_stale_or_invalid_trigger_fails_closed():
    trigger = datetime.fromisoformat("2026-10-15T12:15:00-07:00")
    for now in (trigger - timedelta(seconds=1), trigger + timedelta(days=7)):
        with pytest.raises(ValueError):
            scheduled_scope(trigger, now, "synthetic-schedule")
    with pytest.raises(ValueError):
        upcoming_friday(datetime(2026, 10, 15))
    with pytest.raises(ValueError):
        scheduled_scope(trigger, trigger, "synthetic-schedule", datetime(2026, 10, 23).date())
    monday = datetime.fromisoformat("2026-10-12T12:00:00-07:00")
    with pytest.raises(ValueError):
        scheduled_scope(monday, monday, "synthetic-schedule")


@pytest.mark.parametrize(
    "calls,cost,unknown", [(1, "1", False), (10, "0.01", False), (10, "1", True)]
)
def test_whole_worker_guard_stops_calls_cost_or_unknown(calls, cost, unknown):
    guard = SpendGuard(
        WholeWorkerLimits(max_model_calls=calls, max_estimated_model_cost_usd=Decimal(cost))
    )
    assert guard.reserve()
    guard.observe(
        TokenUsage()
        if unknown
        else TokenUsage(
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=1,
            total_tokens=2,
            estimated_model_cost_usd=0.02,
        )
    )
    assert not guard.reserve()
    assert guard.calls == 1


def test_proposed_envelope_is_not_authorization(tmp_path, monkeypatch, capsys):
    config = ScheduleEnvelope.model_validate_json(CONFIG.read_text())
    copied = tmp_path / "envelope.json"
    copied.write_text(config.model_dump_json())
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVENT_RADAR_SCHEDULE_APPROVED", raising=False)

    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("No engine or provider should be constructed")

    monkeypatch.setattr("event_radar.shared_schedule.build_engine", forbidden)
    # Export needs DB configuration but never authorization for model work.
    assert main(["export", "--config", str(copied), "--weekend", "2026-10-16"]) == 2
    from tests.test_shared_worker_integration import scope

    monkeypatch.setattr("event_radar.shared_schedule.scheduled_scope", lambda *args: scope())
    monkeypatch.setenv("EVENT_RADAR_RESEARCH_OPENAI_API_KEY", "SECRET_SENTINEL")
    assert (
        main(
            [
                "execute",
                "--config",
                str(copied),
                "--triggered-at",
                "2026-10-15T12:15:00-07:00",
                "--acknowledge-live-run",
            ]
        )
        == 2
    )
    assert not calls
    assert "SECRET_SENTINEL" not in capsys.readouterr().out
    outputs = list((tmp_path / "output/development-evidence").glob("*.json"))
    assert outputs
    assert all("password" not in p.read_text() for p in outputs)


def test_workflow_is_inert_and_separate():
    wire = Path(".github/workflows/product-weekly-research.yml").read_text()
    active = "\n".join(line for line in wire.splitlines() if not line.lstrip().startswith("#"))
    assert "schedule:" not in active
    assert "if: ${{ false }}" in active
    assert "cancel-in-progress: false" in wire
    assert "--refresh" not in wire
    assert "event_radar.main" not in wire and "TELEGRAM" not in wire
    assert "--acknowledge-live-run" in wire
    assert "retention-days: 30" in wire
    assert "created_at" in wire and "run_attempt" in wire
    envelope = json.loads(CONFIG.read_text())
    assert envelope["whole_worker_limits"]["max_model_calls"] == 24


def test_schedule_plan_imports_no_live_or_personal_dependencies(tmp_path):
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    script = """
import sys
from datetime import datetime
def guard(event, args):
    if event == "socket.connect":
        raise AssertionError("Network forbidden")
    if event == "import" and args[0].startswith((
        "openai", "event_radar.shared_runtime", "event_radar.config",
        "event_radar.main", "event_radar.api", "event_radar.services.telegram",
        "event_radar.services.personal_context", "event_radar.services.user_context",
        "event_radar.models.user_context", "event_radar.services.llm_curation",
    )):
        raise AssertionError("Live or personal dependency")
    if event == "open" and any(part in str(args[0]) for part in (
        ".private-state", ".env", "user_context", "permanent_directions",
    )):
        raise AssertionError("Private file")
sys.addaudithook(guard)
from event_radar.shared_schedule import scheduled_scope, ScheduleEnvelope
config = ScheduleEnvelope.model_validate_json(open(sys.argv[1]).read())
now = datetime.fromisoformat("2026-10-15T12:15:00-07:00")
scope = scheduled_scope(now, now, config.policy_version)
assert scope.identity.friday.isoformat() == "2026-10-16"
assert "openai" not in sys.modules
print("isolated plan passed")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(CONFIG.resolve())],
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "isolated plan passed" in result.stdout
