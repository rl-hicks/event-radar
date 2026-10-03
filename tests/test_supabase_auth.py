"""Real cryptographic unit tests and mocked Supabase protocol checks."""

import logging
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from event_radar.api import routes
from event_radar.api.app import create_app
from event_radar.api.dependencies import get_session
from event_radar.auth import identity
from event_radar.auth.config import AuthUnavailable
from event_radar.auth.verifier import SupabaseVerifier
from event_radar.db.models import AppUser
from tests.auth_helpers import CONFIG, signed, signing_fixture


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_valid_asymmetric_and_cached_jwks(monkeypatch: pytest.MonkeyPatch, algorithm: str) -> None:
    key, claims, verifier = signing_fixture(monkeypatch, algorithm)
    token = signed(key, claims, algorithm)
    assert verifier.verify(token) == (UUID(claims["sub"]), "verified@example.test")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("JWKS was not cached")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    assert verifier.verify(token)[0] == UUID(claims["sub"])


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
@pytest.mark.parametrize(
    "change", ["signature", "expired", "issuer", "audience", "subject", "role", "missing_exp"]
)
def test_invalid_claims_and_signature(
    monkeypatch: pytest.MonkeyPatch, algorithm: str, change: str
) -> None:
    key, claims, verifier = signing_fixture(monkeypatch, algorithm)

    def forbidden_fallback(*a: object, **kw: object) -> None:
        raise AssertionError("Asymmetric verification must not fall back to /user")

    monkeypatch.setattr(httpx, "get", forbidden_fallback)
    if change == "signature":
        key_for_token = key
        # Serve a different public key, leaving the signed token invalid.
        signing_fixture(monkeypatch, algorithm)
    else:
        key_for_token = key
    if change == "expired":
        claims["exp"] = int(time.time()) - 60
    if change == "issuer":
        claims["iss"] = "https://other.example/auth/v1"
    if change == "audience":
        claims["aud"] = "service_role"
    if change == "subject":
        claims["sub"] = "not-a-uuid"
    if change == "role":
        claims["role"] = "service_role"
    if change == "missing_exp":
        claims.pop("exp")
    with pytest.raises(jwt.InvalidTokenError):
        verifier.verify(signed(key_for_token, claims, algorithm))


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Basic abc",
        "Bearer",
        "Bearer sb_publishable_test",
        "Bearer arbitrary",
        "Bearer a.b.c",
        "Bearer a b",
    ],
)
def test_bearer_rejections(header: str | None) -> None:
    with TestClient(create_app()) as client:
        response = client.get(
            "/api/me", headers={} if header is None else {"Authorization": header}
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("algorithm", ["none", "HS384"])
def test_unsupported_algorithm(algorithm: str) -> None:
    token = jwt.encode(
        {"sub": str(uuid4())}, None if algorithm == "none" else "test" * 16, algorithm=algorithm
    )
    with TestClient(create_app()) as client:
        assert (
            client.get("/api/me", headers={"Authorization": "Bearer " + token}).status_code == 401
        )


def legacy_token(**updates: object) -> tuple[str, dict]:
    claims = {
        "sub": str(uuid4()),
        "iss": CONFIG.issuer,
        "aud": "authenticated",
        "exp": int(time.time()) + 300,
        "role": "authenticated",
        "email": "untrusted@example.test",
    }
    claims.update(updates)
    return jwt.encode(claims, "ephemeral-unit-fixture-only-32-bytes", algorithm="HS256"), claims


def test_legacy_auth_server_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    token, claims = legacy_token()

    def get(url: str, **kwargs: object) -> httpx.Response:
        assert url == CONFIG.issuer + "/user"
        assert kwargs["headers"] == {
            "apikey": CONFIG.publishable_key,
            "Authorization": "Bearer " + token,
        }
        assert kwargs["timeout"] == 5 and kwargs["follow_redirects"] is False
        return httpx.Response(
            200,
            json={
                "id": claims["sub"],
                "role": "authenticated",
                "email": "authoritative@example.test",
            },
        )

    monkeypatch.setattr(httpx, "get", get)
    assert SupabaseVerifier(CONFIG).verify(token) == (
        UUID(claims["sub"]),
        "authoritative@example.test",
    )


@pytest.mark.parametrize("status", [401, 403, 500, 429])
def test_legacy_rejection_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    token, _ = legacy_token()
    monkeypatch.setattr(
        httpx, "get", lambda *a, **kw: httpx.Response(status, text="provider-secret")
    )
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: SupabaseVerifier(CONFIG))
    caplog.set_level(logging.INFO, logger="event_radar.api")
    with TestClient(create_app()) as client:
        response = client.get("/api/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == (401 if status in {401, 403} else 503)
    messages = "".join(r.message for r in caplog.records if r.name == "event_radar.api")
    for value in (token, CONFIG.publishable_key, "provider-secret"):
        assert value not in response.text + messages


def test_legacy_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*a: object, **kw: object) -> None:
        raise httpx.ReadTimeout("provider-secret")

    monkeypatch.setattr(httpx, "get", timeout)
    with pytest.raises(AuthUnavailable):
        SupabaseVerifier(CONFIG).verify(legacy_token()[0])


@pytest.mark.parametrize("change", ["issuer", "audience", "expired", "subject"])
def test_legacy_additional_policy(monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    token, claims = legacy_token(
        **{
            "issuer": {"iss": "https://wrong.example/auth/v1"},
            "audience": {"aud": "wrong"},
            "expired": {"exp": 1},
            "subject": {"sub": "bad"},
        }[change]
    )
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **kw: httpx.Response(200, json={"id": claims["sub"], "role": "authenticated"}),
    )
    with pytest.raises(jwt.InvalidTokenError):
        SupabaseVerifier(CONFIG).verify(token)


def test_validated_token_identity_ignores_client_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    key, claims, verifier = signing_fixture(monkeypatch)
    token = signed(key, claims)
    monkeypatch.setattr(identity, "auth_config", lambda: CONFIG)
    monkeypatch.setattr(identity, "get_verifier", lambda _: verifier)
    monkeypatch.setattr(
        routes,
        "get_or_create_user",
        lambda session, identifier: AppUser(id=identifier, created_at=datetime.now(UTC)),
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: object()
    other = str(uuid4())
    with TestClient(app) as client:
        response = client.request(
            "GET",
            f"/api/me?user_id={other}",
            json={"user_id": other, "email": "fake"},
            headers={"Authorization": "Bearer " + token, "X-User-ID": other, "X-Email": "fake"},
        )
    assert response.status_code == 200
    assert response.json()["id"] == claims["sub"]
    assert response.json()["email"] == claims["email"]


def test_unconfigured_auth_and_jwks_timeout_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    key, claims, verifier = signing_fixture(monkeypatch)
    token = signed(key, claims)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    with TestClient(create_app()) as client:
        response = client.get("/api/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_unavailable"

    def timeout(*a: object, **kw: object) -> None:
        raise TimeoutError("provider-secret")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", timeout)
    with pytest.raises(AuthUnavailable):
        verifier.verify(token)


@pytest.mark.parametrize(
    "header",
    [{}, {"alg": ["ES256"]}, {"alg": "unknown"}, {"alg": "ES256", "crit": ["unrecognized"]}],
)
def test_malformed_algorithm_headers(header: dict) -> None:
    import base64
    import json

    encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    with TestClient(create_app()) as client:
        response = client.get(
            "/api/me", headers={"Authorization": "Bearer " + encoded + ".e30.signature"}
        )
    assert response.status_code == 401


def test_duplicate_authorization_headers_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.get(
            "/api/me",
            headers=[("Authorization", "Bearer first"), ("Authorization", "Bearer second")],
        )
    assert response.status_code == 401
