"""A fresh process proves regional contracts cannot enter the personal runtime."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_regional_contract_import_and_construction_are_environment_independent(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src"
    fixture = (Path(__file__).parent / "fixtures/regional/universe.json").read_text()
    script = textwrap.dedent("""
        import importlib.abc
        import os
        import sys

        blocked = (
            "event_radar.config", "event_radar.main", "event_radar.services",
            "event_radar.collectors", "event_radar.api", "event_radar.auth",
            "event_radar.db", "pydantic_settings", "openai", "psycopg",
            "sqlalchemy", "alembic",
        )

        class NoRuntimeImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                legacy_model = fullname.startswith("event_radar.models.") and (
                    fullname != "event_radar.models.regional"
                )
                if legacy_model or any(
                    fullname == name or fullname.startswith(name + ".") for name in blocked
                ):
                    raise AssertionError("Unexpected runtime import: " + fullname)

        def guard(event, args):
            if event in ("socket.connect", "socket.getaddrinfo", "socket.bind", "subprocess.Popen"):
                raise AssertionError("Unexpected external activity")
            if event == "open":
                path, mode, flags = args
                if isinstance(path, (str, bytes, os.PathLike)):
                    name = os.fsdecode(path).replace(chr(92), "/")
                    parts = name.split("/")
                    if any(part.startswith(".env") or part in (
                        "state", ".private-state", ".vercel", "output", "audit"
                    ) for part in parts) or name.endswith((
                        "user_context.json", "personal_experience_preference_context.md"
                    )):
                        raise AssertionError("Unexpected private/provider access")
                if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & 3:
                    raise AssertionError("Unexpected filesystem write")
            if event in ("os.mkdir", "os.remove", "os.rename", "os.rmdir"):
                raise AssertionError("Unexpected filesystem mutation")

        sys.meta_path.insert(0, NoRuntimeImports())
        sys.addaudithook(guard)
        from event_radar.models.regional import (
            RegionalWeekendUniverse, RegionalAnalysisRequest, RegionalDiscoveryRequest,
        )
        universe = RegionalWeekendUniverse.model_validate_json(sys.argv[1])
        assert len(universe.opportunities) == 2
        assert universe.scope.identity.key == "sonoma-county-ca/2026-10-02/regional-v1"
        for model in (RegionalWeekendUniverse, RegionalAnalysisRequest, RegionalDiscoveryRequest):
            model.model_json_schema()
        assert RegionalWeekendUniverse.model_validate_json(universe.model_dump_json()) == universe
        assert not any(name in sys.modules for name in blocked)
    """)
    # No inherited provider credentials, paths, account identity or user context.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(source),
        "PYTHONDONTWRITEBYTECODE": "1",
        # Poisoned non-secret legacy setting: any accidental settings construction fails.
        "OPENAI_MODEL_PRICING": "not-valid-json",
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, fixture],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []
    assert json.loads(fixture)["scope"]["region"]["region_id"] == "sonoma-county-ca"
