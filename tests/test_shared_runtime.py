"""Real composition proofs: fake credentials/clients only; all sockets blocked."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from event_radar.collectors.regional_sources import CuratedHikeCatalogSource
from event_radar.services.adaptive_regional_discovery import OpenAIAdaptiveDiscoveryProvider
from event_radar.services.regional_semantic_analysis import OpenAIRegionalSemanticProvider
from event_radar.shared.worker import WorkerResult
from event_radar.shared_runtime import (
    API_KEY_ENV,
    ASSET_ROOT,
    DATABASE_ENV,
    RealRuntimeConfig,
    build_real_dependencies,
    execute_real,
    research_secrets,
)
from event_radar.shared_worker import main

LOCAL_DB = (
    "postgresql+psycopg://event_radar_test:event_radar_test_local@127.0.0.1:55432/event_radar_test"
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network is prohibited in real composition tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)


def payload():
    return {
        "scope": {
            "region": {
                "region_id": "sonoma-county-ca",
                "country_code": "US",
                "subdivision_code": "CA",
                "county": "Sonoma County",
                "timezone": "America/Los_Angeles",
            },
            "window": {"friday": "2026-10-09", "timezone": "America/Los_Angeles"},
            "research_policy_version": "regional-v1",
            "as_of": "2026-10-08T12:00:00-07:00",
        },
        "database_url": LOCAL_DB,
        "api_key": "synthetic-api-key",
        "semantic_model": "semantic-test",
        "discovery_model": "discovery-test",
        "timeout_seconds": 60,
        "semantic_batch_size": 10,
        "discovery_budget": {
            "max_waves": 2,
            "max_model_calls": 5,
            "max_web_search_calls": 3,
            "max_model_cost_usd": "0.05",
        },
        "semantic_pricing": {
            "input_usd_per_million": 1,
            "cached_input_usd_per_million": 0.1,
            "output_usd_per_million": 2,
        },
        "discovery_pricing": {
            "input_usd_per_million": 2,
            "cached_input_usd_per_million": 0.2,
            "output_usd_per_million": 3,
        },
        "database_session_mode": "direct",
        "acknowledge_live_run": True,
    }


def arguments():
    return [
        "--real",
        "--acknowledge-live-run",
        "--database-session-mode",
        "direct",
        "--region",
        "sonoma-county-ca",
        "--weekend",
        "2026-10-09",
        "--as-of",
        "2026-10-08T12:00:00-07:00",
        "--policy-version",
        "regional-v1",
        "--semantic-model",
        "semantic-test",
        "--discovery-model",
        "discovery-test",
        "--timeout-seconds",
        "60",
        "--semantic-batch-size",
        "10",
        "--max-waves",
        "2",
        "--max-model-calls",
        "5",
        "--max-web-search-calls",
        "3",
        "--max-model-cost-usd",
        "0.05",
        "--semantic-pricing",
        "1",
        "0.1",
        "2",
        "--discovery-pricing",
        "2",
        "0.2",
        "3",
    ]


def set_environment(monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("PG"):
            monkeypatch.delenv(key)
    monkeypatch.setenv(DATABASE_ENV, LOCAL_DB)
    monkeypatch.setenv(API_KEY_ENV, "synthetic-api-key")


class FakeClient:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.responses = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def parse(self, **kwargs):
        from event_radar.models.regional_discovery import DiscoveryPlan
        from event_radar.models.regional_semantics import (
            OpportunitySemanticAnalysis,
            RegionalSemanticAnalysis,
        )

        self.calls.append(kwargs)
        if kwargs["text_format"] is RegionalSemanticAnalysis:
            request = json.loads(kwargs["input"])
            value = RegionalSemanticAnalysis(
                opportunities=tuple(
                    OpportunitySemanticAnalysis(
                        opportunity_id=item["opportunity_id"], descriptors=()
                    )
                    for item in request["opportunities"]
                )
            )
        else:
            value = DiscoveryPlan(
                gaps=(), tasks=(), should_continue=False, rationale="Offline test"
            )
        return SimpleNamespace(
            status="completed",
            error=None,
            output_parsed=value,
            output=[],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
        )


def test_exact_production_composition_is_inert_and_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = FakeClient()
    config = RealRuntimeConfig.model_validate(payload())
    deps = build_real_dependencies(config, client=client)
    try:
        assert [item.adapter.descriptor.source_id for item in deps.registry.registrations] == [
            "sonoma-county-tourism",
            "happening-sonoma-county",
            "curated-sonoma-hikes",
        ]
        assert all(item.enabled for item in deps.registry.registrations)
        assert isinstance(deps.registry.registrations[2].adapter, CuratedHikeCatalogSource)
        assert (
            deps.registry.registrations[2].adapter._repository._path
            == ASSET_ROOT / "data/hikes.json"
        )
        assert isinstance(deps.semantic_provider, OpenAIRegionalSemanticProvider)
        assert isinstance(deps.planner, OpenAIAdaptiveDiscoveryProvider)
        assert deps.planner is deps.researcher is deps.verifier
        assert deps.semantic_provider.model_id == "semantic-test"
        assert deps.planner.model_id == "discovery-test"
        assert deps.semantic_provider._client is deps.planner._client is client
        assert deps.semantic_provider._pricing.input_usd_per_million == 1
        assert deps.planner._pricing.input_usd_per_million == 2
        assert deps.planner._max_web_search_calls_per_request == 3
        assert (
            deps.semantic_provider._prompt_path
            == ASSET_ROOT / "prompts/regional_semantic_analysis.md"
        )
        assert not client.calls
    finally:
        deps.engine.dispose()


async def test_real_adapters_serialize_selected_models_with_injected_fake_client():
    from event_radar.models.regional import RegionalAnalysisRequest
    from event_radar.models.regional_discovery import DiscoveryContext, RegionalCoverageSnapshot
    from event_radar.shared.synthetic import SyntheticSource

    config = RealRuntimeConfig.model_validate(payload())
    client = FakeClient()
    deps = build_real_dependencies(config, client=client)
    try:
        source = await SyntheticSource().collect(config.scope, observed_at=config.scope.as_of)
        semantic = await deps.semantic_provider.analyze(
            RegionalAnalysisRequest(scope=config.scope, opportunities=source.opportunities)
        )
        assert semantic.usage.estimated_model_cost_usd is not None
        context = DiscoveryContext(
            scope=config.scope,
            existing_opportunities=source.opportunities,
            coverage=RegionalCoverageSnapshot(
                searched_source_classes=(),
                unsearched_source_classes=(),
                successful_source_ids=(),
                failed_source_ids=(),
                known_empty_source_ids=(),
                event_count=1,
                hike_count=0,
                event_counts_by_city=(),
                event_counts_by_local_day=(),
            ),
        )
        discovered = await deps.planner.plan(context)
        assert discovered.usage.estimated_model_cost_usd is not None
        assert [call["model"] for call in client.calls] == ["semantic-test", "discovery-test"]
        assert all(call["store"] is False for call in client.calls)
    finally:
        deps.engine.dispose()


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "database_url",
        "semantic_model",
        "discovery_model",
        "timeout_seconds",
        "semantic_batch_size",
        "discovery_budget",
        "semantic_pricing",
        "discovery_pricing",
        "database_session_mode",
        "acknowledge_live_run",
    ],
)
def test_config_requires_every_live_field(field):
    value = payload()
    del value[field]
    with pytest.raises(ValueError):
        RealRuntimeConfig.model_validate(value)


@pytest.mark.parametrize(
    "field",
    [
        "max_waves",
        "max_model_calls",
        "max_web_search_calls",
        "max_model_cost_usd",
    ],
)
def test_budget_cannot_be_partial(field):
    value = payload()
    del value["discovery_budget"][field]
    with pytest.raises(ValueError):
        RealRuntimeConfig.model_validate(value)


@pytest.mark.parametrize(
    "update",
    [
        {"api_key": " "},
        {"acknowledge_live_run": False},
        {"semantic_model": ""},
        {"timeout_seconds": float("nan")},
        {"semantic_batch_size": 0},
        {"database_url": "sqlite:///not-postgres"},
        {"database_url": LOCAL_DB.replace(":55432/", ":6543/")},
        {"database_url": LOCAL_DB + "?host=elsewhere"},
        {"database_url": LOCAL_DB.replace("127.0.0.1", "db.example.org")},
        {"database_session_mode": "transaction"},
    ],
)
def test_invalid_real_config_fails_closed(update):
    with pytest.raises(ValueError):
        RealRuntimeConfig.model_validate({**payload(), **update})


def test_remote_target_requires_verified_tls_and_secret_repr():
    value = payload()
    value["database_url"] = LOCAL_DB.replace("127.0.0.1", "db.example.org") + "?sslmode=verify-full"
    config = RealRuntimeConfig.model_validate(value)
    assert config.postgres_url().query["sslmode"] == "verify-full"
    assert "synthetic-api-key" not in repr(config)
    assert "event_radar_test_local" not in repr(config)


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"OPENAI_API_KEY": "ambient-key", "DATABASE_URL": LOCAL_DB},
        {DATABASE_ENV: LOCAL_DB},
        {API_KEY_ENV: "synthetic-api-key"},
        {DATABASE_ENV: LOCAL_DB, API_KEY_ENV: "synthetic-api-key", "PGHOSTADDR": "127.0.0.1"},
    ],
)
def test_only_dedicated_environment_is_used(environment):
    with pytest.raises(ValueError):
        research_secrets(environment)


@pytest.mark.parametrize(
    "flag",
    [
        "--acknowledge-live-run",
        "--semantic-model",
        "--discovery-model",
        "--database-session-mode",
        "--timeout-seconds",
        "--semantic-batch-size",
        "--max-waves",
        "--max-model-calls",
        "--max-web-search-calls",
        "--max-model-cost-usd",
        "--semantic-pricing",
        "--discovery-pricing",
    ],
)
def test_cli_incomplete_real_config_never_executes(monkeypatch, capsys, flag):
    set_environment(monkeypatch)
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Incomplete config cannot execute")

    monkeypatch.setattr("event_radar.shared_runtime.execute_real", forbidden)
    args = arguments()
    index = args.index(flag)
    count = 1 if flag == "--acknowledge-live-run" else 4 if flag.endswith("-pricing") else 2
    del args[index : index + count]
    assert main(args) == 2
    assert not calls
    assert "synthetic-api-key" not in capsys.readouterr().out


def test_valid_real_cli_routes_to_existing_worker_with_explicit_config(monkeypatch, capsys):
    set_environment(monkeypatch)
    calls = []

    async def fake_execute(config, *, refresh):
        calls.append((config, refresh))
        return WorkerResult("replayed")

    monkeypatch.setattr("event_radar.shared_runtime.execute_real", fake_execute)
    assert main(arguments() + ["--refresh"]) == 0
    assert len(calls) == 1 and calls[0][1] is True
    config = calls[0][0]
    assert config.discovery_budget.max_model_calls == 5
    assert config.research_budget().semantic_batch_size == 10
    assert '"status": "replayed"' in capsys.readouterr().out


async def test_execution_owns_client_and_engine_and_uses_existing_orchestrator(monkeypatch):
    client = FakeClient()
    constructors, workers, engines = [], [], []

    def fake_openai(**kwargs):
        constructors.append(kwargs)
        return client

    async def fake_worker(scope, deps, *, budget, refresh):
        engines.append(deps.engine)
        workers.append((scope, deps, budget, refresh))
        return WorkerResult("replayed")

    monkeypatch.setattr("event_radar.shared_runtime.AsyncOpenAI", fake_openai)
    monkeypatch.setattr("event_radar.shared_runtime.run_regional_worker", fake_worker)
    result = await execute_real(RealRuntimeConfig.model_validate(payload()))
    assert result.status == "replayed"
    assert client.closed and not client.calls
    assert len(workers) == 1
    assert constructors[0]["base_url"] == "https://api.openai.com/v1"
    assert constructors[0]["max_retries"] == 0
    assert workers[0][1].semantic_provider._client is client


def test_real_composition_fresh_process_blocks_personal_state_and_network(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = """
import sys
def guard(event, args):
    if event == "socket.connect":
        raise AssertionError("Network forbidden")
    if event == "import" and args[0].startswith((
        "event_radar.config", "event_radar.main", "event_radar.api",
        "event_radar.services.pipeline", "event_radar.services.telegram",
        "event_radar.services.personal_context", "event_radar.services.user_context",
        "event_radar.services.direction_store", "event_radar.services.llm_curation",
        "event_radar.models.user_context",
    )):
        raise AssertionError("Personal dependency")
    if event == "open" and any(part in str(args[0]) for part in (
        ".private-state", ".env", "user_context", "permanent_directions", "temporary_directions",
    )):
        raise AssertionError("Private file")
sys.addaudithook(guard)
from event_radar.shared_runtime import RealRuntimeConfig, build_real_dependencies
config = RealRuntimeConfig.model_validate_json(sys.argv[1])
deps = build_real_dependencies(config, client=object())
assert len(deps.registry.registrations) == 3
deps.engine.dispose()
print("offline composition passed")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, json.dumps(payload())],
        cwd=tmp_path,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(root / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "offline composition passed" in result.stdout


@pytest.mark.parametrize("missing", [DATABASE_ENV, API_KEY_ENV])
def test_cli_missing_secret_stops_before_execution(monkeypatch, capsys, missing):
    set_environment(monkeypatch)
    monkeypatch.delenv(missing)
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Missing secrets cannot execute")

    monkeypatch.setattr("event_radar.shared_runtime.execute_real", forbidden)
    assert main(arguments()) == 2
    assert not calls
    assert "synthetic-api-key" not in capsys.readouterr().out
