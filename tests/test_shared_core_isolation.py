"""Fresh-process proof that the E1 shared entry surface avoids legacy settings."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_shared_core_import_and_use_do_not_construct_legacy_runtime(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    fixture = (Path(__file__).parent / "fixtures/regional/universe.json").read_text()
    script = textwrap.dedent(
        """
        import sys
        from types import SimpleNamespace

        from event_radar.shared import (
            ModelTokenPricing,
            RegionalWeekendUniverse,
            TokenUsage,
            aggregate_token_usage,
            parse_token_usage,
        )

        universe = RegionalWeekendUniverse.model_validate_json(sys.argv[1])
        assert universe.scope.identity.key == "sonoma-county-ca/2026-10-02/regional-v1"

        pricing = ModelTokenPricing(2.0, 0.1, 10.0)
        raw = SimpleNamespace(
            input_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=40),
            output_tokens=20,
            total_tokens=120,
        )
        usage = parse_token_usage(raw, pricing)
        assert usage.total_tokens == 120
        assert aggregate_token_usage([TokenUsage(), usage]) == usage

        blocked = (
            "event_radar.config",
            "event_radar.main",
            "event_radar.services",
            "event_radar.collectors",
        )
        assert not any(name in sys.modules for name in blocked)
        """
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(source),
        "PYTHONDONTWRITEBYTECODE": "1",
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
