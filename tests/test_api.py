"""Deterministic route/security contracts; PostgreSQL behavior is tested separately."""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from event_radar.api import routes
from event_radar.api.app import create_app
from event_radar.api.dependencies import database_healthy, get_session
from event_radar.auth.identity import AuthenticatedUser, get_current_user
from event_radar.db.models import AppUser


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("WEB_ORIGINS", "http://localhost:5173,https://web.example.test")
    return create_app()


@pytest.mark.parametrize("healthy,status", [(True, 200), (False, 503)])
def test_health(app: FastAPI, healthy: bool, status: int) -> None:
    app.dependency_overrides[database_healthy] = lambda: healthy
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == status
    assert response.json()["database"] == ("ok" if healthy else "unavailable")
    assert set(response.json()) <= {"status", "database", "error"}


def test_missing_or_bad_database_is_safe(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        assert client.get("/health").status_code == 503
        monkeypatch.setenv("DATABASE_URL", "invalid://secret-user:secret-password@secret-host/db")
        response = client.get("/health")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_authentication_fails_closed_before_database(app: FastAPI) -> None:
    def forbidden_session() -> None:
        raise AssertionError("Unauthenticated request reached DB")

    # Guard engine construction while retaining the real authentication-first dependency.
    app.state.database.engine = forbidden_session
    with TestClient(app) as client:
        response = client.get(
            f"/api/me?user_id={uuid4()}",
            headers={"Authorization": "Bearer arbitrary-token", "X-User-ID": str(uuid4())},
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "code": "authentication_required",
            "message": "Authentication required.",
        }
    }


def test_two_identities_repeat_and_request_manipulation(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users: dict[UUID, AppUser] = {}
    current = AuthenticatedUser(id=uuid4(), email="a@example.test")
    first_id, second_id = current.id, uuid4()

    def fake_store(session: object, authenticated_id: UUID) -> AppUser:
        if authenticated_id not in users:
            users[authenticated_id] = AppUser(
                id=authenticated_id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        return users[authenticated_id]

    app.dependency_overrides[get_current_user] = lambda: current
    app.dependency_overrides[get_session] = lambda: object()
    monkeypatch.setattr(routes, "get_or_create_user", fake_store)
    with TestClient(app) as client:
        first = client.get("/api/me").json()
        assert client.get("/api/me").json() == first
        current = AuthenticatedUser(id=second_id, email="b@example.test")
        second = client.request(
            "GET",
            f"/api/me?user_id={first_id}",
            json={"user_id": str(first_id)},
            headers={"X-User-ID": str(first_id), "Authorization": f"Bearer {first_id}"},
        ).json()
    assert first["id"] == str(first_id)
    assert second["id"] == str(second_id)
    assert second["email"] == "b@example.test"
    assert set(users) == {first_id, second_id}
    assert set(first) == {"id", "email", "created_at", "database_roundtrip"}


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (SQLAlchemyError("secret database URL and token"), 503, "database_unavailable"),
        (RuntimeError("secret internal detail"), 500, "internal_error"),
    ],
)
def test_error_and_log_redaction(
    app: FastAPI,
    failure: Exception,
    status: int,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail() -> bool:
        raise failure

    app.dependency_overrides[database_healthy] = fail
    caplog.set_level(logging.INFO, logger="event_radar.api")
    with TestClient(app) as client:
        response = client.get(
            "/health?token=secret-query", headers={"Authorization": "secret-token"}
        )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    records = [r for r in caplog.records if r.name == "event_radar.api"]
    assert len(records) == 1
    data = json.loads(records[0].message)
    assert data["path"] == "/health" and data["method"] == "GET"
    assert data["status"] == status and data["error_code"] == code
    assert data["duration_ms"] >= 0
    assert "secret" not in response.text + records[0].message
    assert records[0].exc_info is None


def test_commit_failure_cannot_return_success(app: FastAPI) -> None:
    def session() -> Iterator[object]:
        yield object()
        raise SQLAlchemyError("secret commit failure")

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=uuid4())
    app.dependency_overrides[get_session] = session
    # A test-only route exercises function-scoped dependency teardown before send.
    from typing import Annotated

    from fastapi import Depends

    @app.get("/test-commit")
    def commit_probe(value: Annotated[object, Depends(get_session, scope="function")]) -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/test-commit")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_cors_and_error_envelopes(app: FastAPI) -> None:
    with TestClient(app) as client:
        allowed = client.get("/api/me", headers={"Origin": "http://localhost:5173"})
        denied = client.get("/api/me", headers={"Origin": "https://evil.example"})
        preflight = client.options(
            "/api/me",
            headers={
                "Origin": "https://web.example.test",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        forbidden_method = client.options(
            "/api/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        missing = client.get("/missing")
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers
    assert "access-control-allow-credentials" not in allowed.headers
    assert preflight.status_code == 200
    assert forbidden_method.status_code == 400
    assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "origins", ["*", "https://*.example", "https://user:password@host", "https://host/path"]
)
def test_reject_unsafe_cors_configuration(monkeypatch: pytest.MonkeyPatch, origins: str) -> None:
    monkeypatch.setenv("WEB_ORIGINS", origins)
    with pytest.raises(ValueError, match="WEB_ORIGINS"):
        create_app()


def test_validation_error_does_not_echo_input(app: FastAPI) -> None:
    @app.get("/test-validation")
    def validation_probe(count: int) -> dict:
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/test-validation?count=secret-input")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "secret-input" not in response.text
