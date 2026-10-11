"""Linux/Docker offline durability regression. Run after uv sync, with Docker/root access.

Creates only uniquely named disposable resources. Never touches the retained evidence
service or historical container. Network namespace has no external interfaces.
"""

import hashlib
import json
import os
import pwd
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
NAME = "event-radar-wp7-restart-test-" + uuid4().hex
VOLUME = NAME + "-data"
URL = (
    "postgresql+psycopg://event_radar_evidence:synthetic-test-only"
    "@127.0.0.1:55433/event_radar_evidence"
)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def local(*args):
    pid = run("docker", "inspect", "-f", "{{.State.Pid}}", NAME)
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    environment.update(DATABASE_URL=URL, EVIDENCE_DATABASE_URL=URL, PYTHONPATH=str(ROOT / "src"))
    return run(
        "nsenter",
        "-t",
        pid,
        "-n",
        "runuser",
        "-u",
        pwd.getpwuid(ROOT.stat().st_uid).pw_name,
        "--",
        *args,
        cwd=ROOT,
        env=environment,
    )


def ready():
    for _ in range(60):
        result = subprocess.run(
            [
                "docker",
                "exec",
                NAME,
                "pg_isready",
                "-U",
                "event_radar_evidence",
                "-d",
                "event_radar_evidence",
                "-p",
                "55433",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("Disposable PostgreSQL not ready")


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run with root/Docker access for an isolated network namespace.")
    python = str(ROOT / ".venv/bin/python")
    try:
        run(
            "docker",
            "run",
            "-d",
            "--name",
            NAME,
            "--network",
            "none",
            "-e",
            "POSTGRES_DB=event_radar_evidence",
            "-e",
            "POSTGRES_USER=event_radar_evidence",
            "-e",
            "POSTGRES_PASSWORD=synthetic-test-only",
            "-v",
            VOLUME + ":/var/lib/postgresql/data",
            "postgres:17",
            "-p",
            "55433",
        )
        ready()
        local(str(ROOT / ".venv/bin/alembic"), "upgrade", "head")
        print(local(str(ROOT / ".venv/bin/alembic"), "current"))
        snapshot = local(
            python,
            "-c",
            """
from pathlib import Path
from sqlalchemy.orm import Session
from event_radar.db.session import build_engine
from event_radar.db.config import database_url
from event_radar.db.regional import begin_regional_research_run, complete_regional_research_run
from event_radar.models.regional import RegionalWeekendUniverse
fixture = Path('tests/fixtures/regional/universe.json').read_text()
u = RegionalWeekendUniverse.model_validate_json(fixture)
engine = build_engine(database_url())
with Session(engine) as s, s.begin():
    r = begin_regional_research_run(s, u.scope)
    snapshot = complete_regional_research_run(
        s, r.id, u, quality_status='success', diagnostics=u.diagnostics
    )
    print(snapshot.id)
engine.dispose()
""",
        )

        def export():
            file = local(
                python,
                "-m",
                "event_radar.development_evidence",
                "export",
                "--snapshot-id",
                snapshot,
            )
            return json.loads((ROOT / file).read_text())

        before = export()
        assert before["payload"]["availability"] == "exported"
        run("docker", "stop", NAME)
        run("docker", "start", NAME)
        ready()
        after = export()
        assert before == after, "Snapshot evidence changed across stop/start"
        diagnostic_file = local(
            python,
            "-m",
            "event_radar.development_evidence",
            "discover-offline",
            "--snapshot-id",
            snapshot,
        )
        diagnostic = json.loads((ROOT / diagnostic_file).read_text())["payload"]
        assert diagnostic["execution_mode"] == "offline-synthetic"
        assert diagnostic["research_results"] and diagnostic["verification_results"]
        assert export() == before, "Diagnostic mutated stored evidence"
        failed_run = local(
            python,
            "-c",
            """
from pathlib import Path
from sqlalchemy.orm import Session
from event_radar.db.session import build_engine
from event_radar.db.config import database_url
from event_radar.db.regional import begin_regional_research_run, fail_regional_research_run
from event_radar.models.regional import RegionalWeekendUniverse
u = RegionalWeekendUniverse.model_validate_json(
    Path('tests/fixtures/regional/universe.json').read_text()
)
scope = u.scope.model_copy(update={'research_policy_version': 'synthetic-failed-export'})
engine = build_engine(database_url())
with Session(engine) as s, s.begin():
    r = begin_regional_research_run(s, scope)
    fail_regional_research_run(s, r.id, failure_code='unavailable')
    print(r.id)
engine.dispose()
""",
        )
        for run_id in (failed_run, before["payload"]["related_identity_runs"][0]["run_id"]):
            file = local(
                python,
                "-m",
                "event_radar.development_evidence",
                "export-run",
                "--run-id",
                run_id,
            )
            exported = json.loads((ROOT / file).read_text())
            payload = exported["payload"]
            assert payload["record"]["run_id"] == run_id
            assert (payload["snapshot"] is None) == (run_id == failed_run)
            canonical = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            assert exported["sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
        print("PASS: real CLI run-ID exports with and without snapshots; integrity verified.")
        print(
            "PASS: fresh migrations, synthetic persistence, stop/start, validated readback, "
            "export integrity, fake CLI discovery, immutable base, no external network."
        )
        print("Synthetic diagnostic artifact:", diagnostic_file)
    finally:
        # Only this invocation's generated disposable names, never retained evidence resources.
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
        subprocess.run(["docker", "volume", "rm", VOLUME], capture_output=True)


if __name__ == "__main__":
    main()
