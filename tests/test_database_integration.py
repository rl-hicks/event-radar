"""Opt-in real PostgreSQL proof, restricted to the disposable test service."""

from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import DateTime, Engine, inspect
from sqlalchemy.dialects.postgresql import UUID

from alembic import command
from event_radar.db.health import check_database
from event_radar.db.models import AppUser, Base
from event_radar.db.session import build_session_factory, session_scope


def test_migration_roundtrip_and_metadata(database: tuple[Engine, Config]) -> None:
    engine, config = database
    for _ in range(2):
        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {
            "app_users",
            "regional_universes",
            "regional_universe_snapshots",
            "regional_research_runs",
            "alembic_version",
        }
        columns = {column["name"]: column for column in inspector.get_columns("app_users")}
        assert set(columns) == {"id", "created_at", "updated_at"}
        assert isinstance(columns["id"]["type"], UUID)
        assert columns["id"]["default"] is None
        assert inspector.get_pk_constraint("app_users")["constrained_columns"] == ["id"]
        assert all(not column["nullable"] for column in columns.values())
        for name in ("created_at", "updated_at"):
            assert isinstance(columns[name]["type"], DateTime)
            assert columns[name]["type"].timezone
            assert columns[name]["default"] == "now()"
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_server_default": True})
            assert context.get_current_revision() == "0002_regional_universes"
            assert compare_metadata(context, Base.metadata) == []
        command.downgrade(config, "base")
        inspector = inspect(engine)
        assert not inspector.has_table("app_users")
        assert not inspector.has_table("regional_universes")
        assert not inspector.has_table("regional_universe_snapshots")
        assert not inspector.has_table("regional_research_runs")


def test_identity_persistence_and_session_lifecycle(database: tuple[Engine, Config]) -> None:
    engine, config = database
    command.upgrade(config, "head")
    assert check_database(engine)
    factory = build_session_factory(engine)
    first_id, second_id, rolled_back_id = uuid4(), uuid4(), uuid4()
    with session_scope(factory) as session:
        session.add(AppUser(id=first_id))
    with session_scope(factory) as session:
        first = session.get(AppUser, first_id)
        assert first is not None
        assert first.created_at.tzinfo is not None
        assert first.updated_at == first.created_at
        session.add(AppUser(id=second_id))
    with pytest.raises(RuntimeError, match="force rollback"):
        with session_scope(factory) as session:
            session.add(AppUser(id=rolled_back_id))
            session.flush()
            raise RuntimeError("force rollback")
    with session_scope(factory) as session:
        first = session.get(AppUser, first_id)
        second = session.get(AppUser, second_id)
        assert first is not None and second is not None
        assert first.id != second.id
        assert session.get(AppUser, rolled_back_id) is None
    assert engine.pool.checkedout() == 0
