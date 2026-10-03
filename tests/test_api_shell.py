"""Regression guard for the new runtime's separation from personal execution."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_api_import_and_lifespan_are_independent_of_private_runtime(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    script = textwrap.dedent(
        """
        import importlib.abc
        import os
        import sys

        blocked = (
            "event_radar.config", "event_radar.main", "event_radar.services",
            "event_radar.collectors", "openai", "psycopg",
        )

        class NoLegacyImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
                    raise AssertionError("Unexpected runtime import: " + fullname)

        def guard(event, args):
            if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
                raise AssertionError("Unexpected external activity: " + event)
            if event == "open":
                path, mode, flags = args
                if isinstance(path, (str, bytes, os.PathLike)):
                    name = os.fsdecode(path).replace(chr(92), "/")
                    if any(part in name.split("/") for part in (".env", "state", ".private-state")):
                        raise AssertionError("Unexpected private runtime access")
                    private_names = ("user_context.json",
                                     "personal_experience_preference_context.md")
                    if name.endswith(private_names):
                        raise AssertionError("Unexpected personal context access")
                if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & 3:
                    raise AssertionError("Unexpected filesystem write")

        sys.meta_path.insert(0, NoLegacyImports())
        sys.addaudithook(guard)
        from event_radar.api.app import create_app
        from event_radar import auth
        from event_radar.db.base import Base
        from fastapi.testclient import TestClient

        assert not Base.metadata.tables
        app = create_app()
        assert not app.routes
        with TestClient(app) as client:
            assert client.get("/").status_code == 404
            assert client.get("/health").status_code == 404
            assert client.get("/api/me").status_code == 404
        assert not any(name in sys.modules for name in blocked)
        print("Isolated imports and ASGI startup/shutdown passed")
        """
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(source),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
