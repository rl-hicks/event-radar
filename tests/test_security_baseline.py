"""Synthetic checks for the bounded security scanner, never real credentials."""

import base64
import json
import subprocess
import sys
from pathlib import Path

from scripts.check_security import browser_env_findings, findings, private_path


def test_public_config_and_local_examples_are_not_secrets() -> None:
    assert not findings("sb_publishable_" + "public-example-value" * 2)
    assert not findings(
        "postgresql+psycopg://event_radar:event_radar_local@127.0.0.1:5432/event_radar"
    )
    assert not browser_env_findings("import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY")


def test_unsafe_credentials_and_browser_access_are_rejected() -> None:
    assert findings("sb_secret_" + "synthetic" * 8)
    assert findings("postgresql://" + "user:synthetic-password@remote.example/db")
    payload = (
        base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
    )
    assert findings("eyJhbGciOiJIUzI1NiJ9." + payload + ".syntheticSignature")
    assert browser_env_findings("import.meta.env." + "VITE_DATABASE_URL")
    assert browser_env_findings("import.meta.env['VITE_API_URL']")
    assert browser_env_findings("const values = import.meta.env")


def test_private_paths_and_artifacts_are_rejected() -> None:
    for path in ["web/.vercel/project.json", "web/.env.local", "state/telegram_offset.json"]:
        assert private_path(path)
    assert not private_path("web/.env.example")
    assert findings("postgresql://localhost/db", artifact=True)
    assert findings("user_context.json", artifact=True)


def test_unsafe_artifact_command_fails_without_echoing_value(tmp_path: Path) -> None:
    secret = "sb_secret_" + "synthetic" * 8
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "unsafe.js").write_text(secret)
    script = Path(__file__).resolve().parents[1] / "scripts/check_security.py"
    result = subprocess.run(
        [sys.executable, str(script), "--dist", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Supabase privileged key" in result.stdout
    assert secret not in result.stdout + result.stderr
