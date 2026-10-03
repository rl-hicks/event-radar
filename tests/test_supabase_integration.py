"""Opt-in real staging auth and cryptographic/PostgreSQL integration proofs."""

import os
from uuid import UUID, uuid4

import httpx
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from alembic import command
from event_radar.api.app import create_app
from event_radar.auth import identity
from event_radar.auth.config import auth_config
from event_radar.db.models import AppUser
from event_radar.db.session import build_session_factory, session_scope
from tests.auth_helpers import CONFIG, signed, signing_fixture


def exercise_users(engine: Engine, tokens: list[str], identifiers: list[str]) -> None:
    assert identifiers[0] != identifiers[1]
    with TestClient(create_app()) as client:
        a = client.get("/api/me", headers={"Authorization": "Bearer " + tokens[0]})
        assert a.status_code == 200, "User A API authentication failed"
        assert a.json()["id"] == identifiers[0]
        repeated = client.get("/api/me", headers={"Authorization": "Bearer " + tokens[0]})
        assert repeated.json() == a.json()
        b = client.request(
            "GET",
            f"/api/me?user_id={identifiers[0]}",
            headers={
                "Authorization": "Bearer " + tokens[1],
                "X-User-ID": identifiers[0],
                "X-Email": "fake",
            },
            json={"user_id": identifiers[0], "email": "fake"},
        )
        assert b.status_code == 200, "User B API authentication failed"
        assert b.json()["id"] == identifiers[1]
    with session_scope(build_session_factory(engine)) as session:
        assert set(session.scalars(select(AppUser.id))) == {UUID(value) for value in identifiers}


def test_signed_tokens_through_api_postgres(
    database: tuple[Engine, Config], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, config = database
    command.upgrade(config, "head")
    key, claims, verifier = signing_fixture(monkeypatch)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    identifiers = [claims["sub"], str(uuid4())]
    tokens = [signed(key, {**claims, "sub": identifier}) for identifier in identifiers]
    exercise_users(engine, tokens, identifiers)


@pytest.fixture
def staging_credentials() -> list[tuple[str, str]]:
    names = ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"] + [
        f"SUPABASE_TEST_USER_{user}_{field}"
        for user in ("A", "B")
        for field in ("EMAIL", "PASSWORD")
    ]
    if not all(os.environ.get(name) for name in names):
        pytest.skip("Real staging Supabase configuration and two confirmed test users required")
    return [
        (
            os.environ[f"SUPABASE_TEST_USER_{user}_EMAIL"],
            os.environ[f"SUPABASE_TEST_USER_{user}_PASSWORD"],
        )
        for user in ("A", "B")
    ]


def _real_supabase_users(
    staging_credentials: list[tuple[str, str]], database: tuple[Engine, Config]
) -> None:
    engine, migration = database
    command.upgrade(migration, "head")
    config = auth_config()
    tokens, identifiers = [], []
    for email, password in staging_credentials:
        try:
            response = httpx.post(
                config.issuer + "/token",
                params={"grant_type": "password"},
                headers={"apikey": config.publishable_key},
                json={"email": email, "password": password},
                timeout=10,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            pytest.fail("Staging sign-in transport failed", pytrace=False)
        if response.status_code != 200:
            pytest.fail("Staging sign-in rejected; check confirmed test accounts", pytrace=False)
        payload = response.json()
        tokens.append(payload["access_token"])
        identifiers.append(payload["user"]["id"])
    exercise_users(engine, tokens, identifiers)


def test_real_supabase_users(
    staging_credentials: list[tuple[str, str]], database: tuple[Engine, Config]
) -> None:
    try:
        _real_supabase_users(staging_credentials, database)
    except Exception:
        pytest.fail(
            "Real Supabase identity roundtrip failed; sensitive diagnostics suppressed",
            pytrace=False,
        )
