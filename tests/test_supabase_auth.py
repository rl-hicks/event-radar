from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from event_radar.auth.supabase import SupabaseTokenVerifier


def _token(*, secret: str, subject: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "email": "person@example.com",
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )


def test_legacy_hs256_token_is_validated_when_backend_secret_is_configured() -> None:
    secret = "test-secret-that-never-leaves-the-backend"
    user_id = uuid4()
    verifier = SupabaseTokenVerifier(
        supabase_url="https://example.supabase.co",
        audience="authenticated",
        jwt_secret=secret,
    )

    user = verifier.verify(_token(secret=secret, subject=str(user_id)))

    assert user.id == user_id
    assert user.email == "person@example.com"


def test_invalid_subject_is_rejected() -> None:
    secret = "test-secret-that-never-leaves-the-backend"
    verifier = SupabaseTokenVerifier(
        supabase_url="https://example.supabase.co",
        audience="authenticated",
        jwt_secret=secret,
    )

    with pytest.raises(HTTPException) as exc_info:
        verifier.verify(_token(secret=secret, subject="not-a-uuid"))

    assert exc_info.value.status_code == 401
