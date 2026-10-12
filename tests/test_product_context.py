"""Product context limits, safe errors and client isolation."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from event_radar.api.app import create_app
from event_radar.models.product_context import ProductUserContext

MINIMAL = {"base_location": {"locality": "Santa Rosa", "timezone": "America/Los_Angeles"}}


def test_minimal_profile_does_not_invent_preferences():
    parsed = ProductUserContext.model_validate(MINIMAL)
    assert parsed.interests is None and parsed.cost is None and parsed.travel is None
    assert parsed.base_location.latitude is None
    assert parsed.schema_version == "user-context-v1"
    assert ProductUserContext.model_validate(parsed.model_dump(mode="json")) == parsed


@pytest.mark.parametrize(
    "change",
    [
        {"interests": ["x" * 401]},
        {"interests": ["x"] * 21},
        {"objectives": ["   "]},
        {"user_id": "not-an-authority"},
        {"weekend_intent": "this week only"},
        {"telegram_chat_id": "unverified"},
        {"schema_version": "unknown"},
        {"base_location": {"locality": "Town", "timezone": "Unknown/Zone"}},
        {"base_location": {"locality": "Town", "timezone": "UTC", "latitude": 0}},
        {"travel": {"maximum_one_way_minutes": True}},
        {"cost": {"maximum_per_activity": "25.00"}},
        {"cost": {"maximum_per_activity": "-1", "currency": "USD"}},
        {
            "recurring_availability": [
                {"weekday": "friday", "start": "18:00", "end": "09:00", "disposition": "available"}
            ]
        },
        {
            "recurring_availability": [
                {
                    "weekday": "friday",
                    "start": "08:00Z",
                    "end": "09:00Z",
                    "disposition": "available",
                }
            ]
        },
    ],
)
def test_invalid_context_is_rejected(change):
    with pytest.raises(ValidationError):
        ProductUserContext.model_validate({**MINIMAL, **change})


@pytest.mark.parametrize("method", ["GET", "POST", "PUT"])
def test_context_requires_auth_before_database(method, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()
    calls = []

    def forbidden():
        calls.append(True)
        raise AssertionError("Database must not be reached")

    app.state.database.engine = forbidden
    with TestClient(app) as client:
        response = client.request(method, "/api/me/context", json=MINIMAL)
    assert response.status_code == 401
    assert not calls
    assert "Santa Rosa" not in response.text


def test_context_cors_is_explicit(monkeypatch):
    monkeypatch.setenv("WEB_ORIGINS", "https://web.example.test")
    with TestClient(create_app()) as client:
        for origin, status in [("https://web.example.test", 200), ("https://evil.example", 400)]:
            response = client.options(
                "/api/me/context",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert response.status_code == status
