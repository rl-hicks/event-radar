"""Identity derives exclusively from a verified Supabase user access token."""

from uuid import UUID

from fastapi import HTTPException, Request
from jwt import InvalidTokenError, PyJWTError
from pydantic import BaseModel, ConfigDict

from event_radar.auth.config import auth_config
from event_radar.auth.verifier import get_verifier, token_algorithm


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    email: str | None = None


def get_current_user(request: Request) -> AuthenticatedUser:
    try:
        headers = request.headers.getlist("authorization")
        if len(headers) != 1:
            raise InvalidTokenError
        parts = headers[0].split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise InvalidTokenError
        token = parts[1]
        token_algorithm(token)  # Reject malformed/API keys before configuration or I/O.
        identifier, email = get_verifier(auth_config()).verify(token)
        return AuthenticatedUser(id=identifier, email=email)
    except PyJWTError:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"}) from None
