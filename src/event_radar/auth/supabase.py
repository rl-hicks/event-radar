from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient

from event_radar.config import settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None = None


class SupabaseAuthConfigurationError(RuntimeError):
    pass


class SupabaseTokenVerifier:
    def __init__(
        self,
        *,
        supabase_url: str,
        audience: str,
        jwt_secret: str | None = None,
    ) -> None:
        self._audience = audience
        self._jwt_secret = jwt_secret
        self._issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self._jwks = PyJWKClient(f"{self._issuer}/.well-known/jwks.json")

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm == "HS256":
                if self._jwt_secret is None:
                    raise InvalidTokenError("Legacy JWT secret is not configured.")
                key: Any = self._jwt_secret
                algorithms = ["HS256"]
            elif algorithm in {"RS256", "ES256"}:
                key = self._jwks.get_signing_key_from_jwt(token).key
                algorithms = [algorithm]
            else:
                raise InvalidTokenError("Unsupported JWT signing algorithm.")

            payload = jwt.decode(
                token,
                key=key,
                algorithms=algorithms,
                audience=self._audience,
                issuer=self._issuer,
            )
        except (InvalidTokenError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token is missing a valid subject.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            user_id = UUID(subject)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token subject is invalid.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        email_value = payload.get("email")
        email = email_value if isinstance(email_value, str) else None
        return AuthenticatedUser(id=user_id, email=email)


@lru_cache(maxsize=1)
def _configured_verifier() -> SupabaseTokenVerifier:
    if not settings.supabase_url:
        raise SupabaseAuthConfigurationError("SUPABASE_URL is not configured.")
    secret = (
        settings.supabase_jwt_secret.get_secret_value()
        if settings.supabase_jwt_secret is not None
        else None
    )
    return SupabaseTokenVerifier(
        supabase_url=settings.supabase_url,
        audience=settings.supabase_jwt_audience,
        jwt_secret=secret,
    )


_bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def get_current_user(credentials: BearerCredentials) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _configured_verifier().verify(credentials.credentials)
