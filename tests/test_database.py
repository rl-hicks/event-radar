"""Configuration safety and lazy resource construction without a database."""

import pytest
from sqlalchemy import event

from event_radar.db.config import database_url
from event_radar.db.session import build_engine, build_session_factory
from tests.database_safety import isolated_test_url

TEST_URL = (
    "postgresql+psycopg://event_radar_test:event_radar_test_local@127.0.0.1:55432/event_radar_test"
)


def test_database_configuration_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        database_url()
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    assert database_url() == isolated_test_url(TEST_URL)


@pytest.mark.parametrize(
    "value",
    [
        TEST_URL.replace("55432", "5432"),
        TEST_URL.replace("127.0.0.1", "production.example.com"),
        TEST_URL.replace("/event_radar_test", "/event_radar"),
        TEST_URL.replace("//event_radar_test:", "//event_radar:"),
        TEST_URL + "?host=production.example.com",
        TEST_URL.replace("postgresql+psycopg", "sqlite"),
    ],
)
def test_integration_target_rejects_unsafe_urls(value: str) -> None:
    with pytest.raises(ValueError):
        isolated_test_url(value)


def test_engine_and_session_construction_do_not_connect() -> None:
    engine = build_engine(TEST_URL)

    @event.listens_for(engine, "do_connect")
    def no_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("Construction must not connect")

    try:
        factory = build_session_factory(engine)
        with factory() as session:
            assert not session.in_transaction()
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
