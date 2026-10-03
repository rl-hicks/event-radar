"""Supabase user access-token verification. No network work on construction."""

from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from event_radar.auth.config import AuthConfig, AuthUnavailable

ALGORITHMS = {"ES256", "RS256", "HS256"}


def token_algorithm(token: str) -> str:
    if len(token) > 16384 or token.count(".") != 2:
        raise InvalidTokenError
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or algorithm not in ALGORITHMS or header.get("crit"):
        raise InvalidTokenError
    return str(algorithm)


def subject(claims: dict[str, Any]) -> UUID:
    if claims.get("role") != "authenticated":
        raise InvalidTokenError
    try:
        return UUID(claims["sub"])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise InvalidTokenError from None


class SupabaseVerifier:
    def __init__(self, config: AuthConfig) -> None:
        self.config = config
        self.jwks = PyJWKClient(
            config.issuer + "/.well-known/jwks.json",
            timeout=5,
            cache_jwk_set=True,
            lifespan=300,
            cache_keys=False,
        )

    def verify(self, token: str) -> tuple[UUID, str | None]:
        algorithm = token_algorithm(token)
        if algorithm == "HS256":
            return self._legacy_user(token)
        header = jwt.get_unverified_header(token)
        if not isinstance(header.get("kid"), str) or not 1 <= len(header["kid"]) <= 256:
            raise InvalidTokenError
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
        except (PyJWKClientConnectionError, ValueError):
            raise AuthUnavailable from None
        except PyJWKClientError:
            raise InvalidTokenError from None
        if key.algorithm_name != algorithm:
            raise InvalidTokenError
        claims = jwt.decode(
            token,
            key.key,
            algorithms=[algorithm],
            issuer=self.config.issuer,
            audience=self.config.audience,
            options={"require": ["exp", "iss", "aud", "sub", "role"]},
        )
        identifier = subject(claims)
        email = claims.get("email")
        if email is not None and not isinstance(email, str):
            raise InvalidTokenError
        return identifier, email

    def _legacy_user(self, token: str) -> tuple[UUID, str | None]:
        # Auth-server verification replaces local HMAC verification. No shared
        # signing secret exists here, and failed asymmetric tokens never fall back.
        try:
            response = httpx.get(
                self.config.issuer + "/user",
                headers={"apikey": self.config.publishable_key, "Authorization": "Bearer " + token},
                timeout=5,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise AuthUnavailable from None
        if response.status_code in {401, 403}:
            raise InvalidTokenError
        if response.status_code != 200:
            raise AuthUnavailable
        try:
            user = response.json()
            if not isinstance(user, dict) or user.get("role") != "authenticated":
                raise InvalidTokenError
            identifier = UUID(user["id"])
            email = user.get("email")
            if email is not None and not isinstance(email, str):
                raise InvalidTokenError
            # Only after authoritative /user acceptance, enforce our additional
            # project/audience/expiry/subject policy on this exact accepted token.
            claims = jwt.decode(
                token,
                algorithms=["HS256"],
                issuer=self.config.issuer,
                audience=self.config.audience,
                options={
                    "verify_signature": False,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_sub": True,
                    "verify_nbf": True,
                    "require": ["exp", "iss", "aud", "sub", "role"],
                },
            )
            if subject(claims) != identifier:
                raise InvalidTokenError
            return identifier, email
        except (ValueError, TypeError, KeyError, AttributeError):
            raise InvalidTokenError from None


@lru_cache(maxsize=8)
def get_verifier(config: AuthConfig) -> SupabaseVerifier:
    # Bounded verifier instances retain PyJWT's expiring JWKS cache, not tokens.
    return SupabaseVerifier(config)
