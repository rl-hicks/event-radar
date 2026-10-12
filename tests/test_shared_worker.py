"""Fail-closed CLI configuration and worker budget validation."""

import pytest

from event_radar.shared_worker import main
from tests.test_shared_worker_integration import budget


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), 3601])
def test_invalid_worker_deadline(seconds):
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(budget(), timeout_seconds=seconds)


@pytest.mark.parametrize(
    "change",
    [
        ["--weekend", "2026-10-10"],
        ["--as-of", "2026-10-08T12:00:00"],
        ["--policy-version", "regional-v1"],
    ],
)
def test_cli_rejects_invalid_scope_before_database(monkeypatch, capsys, change):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    args = [
        "--synthetic",
        "--region",
        "sonoma-county-ca",
        "--weekend",
        "2026-10-09",
        "--as-of",
        "2026-10-08T12:00:00-07:00",
        "--policy-version",
        "synthetic-wp7",
    ]
    assert main(args + change) == 2
    assert capsys.readouterr().out == '{"status": "failed", "failure_code": "unavailable"}\n'


def test_cli_does_not_use_database_url_or_provider_credentials(monkeypatch, capsys):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    assert (
        main(
            [
                "--synthetic",
                "--region",
                "sonoma-county-ca",
                "--weekend",
                "2026-10-09",
                "--as-of",
                "2026-10-08T12:00:00-07:00",
                "--policy-version",
                "synthetic-wp7",
            ]
        )
        == 2
    )
    assert "must-not-be-used" not in capsys.readouterr().out
