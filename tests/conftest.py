"""Shared opt-in disposable PostgreSQL fixture; no database work during collection."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

from alembic import command
from event_radar.db.session import build_engine
from tests.database_safety import isolated_test_url


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Config]]:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to opt into disposable PostgreSQL integration tests")
    url = isolated_test_url(value)
    # libpq variables such as PGHOSTADDR/PGSERVICE must not redirect this target.
    for name in tuple(os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)
    # Never use inherited DATABASE_URL (which could be a development or remote DB).
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    engine = build_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()
            assert tuple(identity) == ("event_radar_test", "event_radar_test")
            assert set(inspect(connection).get_table_names()) <= {
                "app_users",
                "regional_universes",
                "regional_universe_snapshots",
                "regional_research_runs",
                "alembic_version",
            }
        # The URL and live identity guards precede every destructive test migration.
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        try:
            yield engine, config
        finally:
            command.downgrade(config, "base")
    finally:
        engine.dispose()
