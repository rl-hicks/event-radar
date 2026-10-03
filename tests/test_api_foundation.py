from collections.abc import Iterator
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from event_radar.api.app import create_app
from event_radar.auth.supabase import AuthenticatedUser, get_current_user
from event_radar.db.base import Base
from event_radar.db.session import get_session


def _app_with_database() -> tuple[TestClient, Session, FastAPI]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    def override_session() -> Iterator[Session]:
        yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    return TestClient(app), session, app


def test_health_proves_database_roundtrip() -> None:
    client, session, _app = _app_with_database()
    try:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
    finally:
        session.close()


def test_api_me_rejects_unauthenticated_request() -> None:
    client, session, _app = _app_with_database()
    try:
        response = client.get("/api/me")
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Authentication required."
    finally:
        session.close()


def test_api_me_uses_authenticated_identity_not_client_user_id() -> None:
    client, session, app = _app_with_database()
    authenticated_id = uuid4()
    attempted_id = uuid4()

    def override_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=authenticated_id, email="user@example.com")

    app.dependency_overrides[get_current_user] = override_user
    try:
        response = client.get(f"/api/me?user_id={attempted_id}")
        assert response.status_code == 200
        body = response.json()
        assert UUID(body["id"]) == authenticated_id
        assert UUID(body["id"]) != attempted_id
        assert body["database_roundtrip"] is True
    finally:
        session.close()


def test_two_authenticated_users_get_distinct_rows() -> None:
    client, session, app = _app_with_database()
    user_a = uuid4()
    user_b = uuid4()
    active = {"id": user_a}

    def override_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=active["id"])

    app.dependency_overrides[get_current_user] = override_user
    try:
        first = client.get("/api/me")
        active["id"] = user_b
        second = client.get("/api/me")
        assert first.status_code == 200
        assert second.status_code == 200
        assert UUID(first.json()["id"]) == user_a
        assert UUID(second.json()["id"]) == user_b
        assert first.json()["id"] != second.json()["id"]
    finally:
        session.close()
