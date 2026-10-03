"""Real PostgreSQL API proof using the same guarded disposable WP2 database."""

from uuid import uuid4

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from alembic import command
from event_radar.api.app import create_app
from event_radar.auth.identity import AuthenticatedUser, get_current_user
from event_radar.db.models import AppUser
from event_radar.db.session import build_session_factory, session_scope


def test_api_identity_postgres_roundtrip(database: tuple[Engine, Config]) -> None:
    engine, config = database
    command.upgrade(config, "head")
    app = create_app()
    first_id, second_id = uuid4(), uuid4()
    current = AuthenticatedUser(id=first_id, email="a@example.test")
    app.dependency_overrides[get_current_user] = lambda: current
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "database": "ok"}
        first = client.get("/api/me")
        assert first.status_code == 200
        assert client.get("/api/me").json() == first.json()
        current = AuthenticatedUser(id=second_id, email="b@example.test")
        second = client.request(
            "GET",
            f"/api/me?user_id={first_id}",
            json={"user_id": str(first_id)},
            headers={"X-User-ID": str(first_id), "Authorization": f"Bearer {first_id}"},
        )
        assert second.status_code == 200
        assert first.json()["id"] == str(first_id)
        assert second.json()["id"] == str(second_id)
        assert second.json()["email"] == "b@example.test"
        assert first.json()["database_roundtrip"] is True
        app.dependency_overrides.clear()
        assert client.get("/api/me").status_code == 401
    with session_scope(build_session_factory(engine)) as session:
        assert set(session.scalars(select(AppUser.id))) == {first_id, second_id}
    assert engine.pool.checkedout() == 0


def test_concurrent_identity_creation(database: tuple[Engine, Config]) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from event_radar.db.users import get_or_create_user

    engine, config = database
    command.upgrade(config, "head")
    identity = uuid4()
    barrier = Barrier(2)
    factory = build_session_factory(engine)

    def create() -> object:
        with session_scope(factory) as session:
            barrier.wait(timeout=10)
            return get_or_create_user(session, identity).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert results == [identity, identity]
    with session_scope(factory) as session:
        assert list(session.scalars(select(AppUser.id))) == [identity]
