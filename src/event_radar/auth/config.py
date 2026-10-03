"""Explicit Supabase configuration; no legacy settings or dotenv loading."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class AuthUnavailable(Exception):
    """Sanitized configuration/provider availability failure."""


@dataclass(frozen=True)
class AuthConfig:
    url: str
    publishable_key: str = field(repr=False)
    audience: str = "authenticated"

    @property
    def issuer(self) -> str:
        return self.url + "/auth/v1"


def auth_config() -> AuthConfig:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    audience = os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")
    try:
        parsed = urlsplit(url)
        local = parsed.hostname in {"localhost", "127.0.0.1"}
        valid = (
            parsed.hostname
            and (parsed.scheme == "https" or (local and parsed.scheme == "http"))
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
            and key.startswith("sb_publishable_")
            and audience == "authenticated"
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise AuthUnavailable
    return AuthConfig(url=url, publishable_key=key, audience=audience)
