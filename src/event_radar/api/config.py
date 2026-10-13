"""Non-secret API configuration; independent of personal runtime settings."""

import os
from urllib.parse import urlsplit


def web_origins() -> list[str]:
    values = os.environ.get("WEB_ORIGINS", "http://localhost:5173")
    origins = []
    for value in values.split(","):
        origin = value.strip()
        if not origin:
            continue
        try:
            parsed = urlsplit(origin)
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
                and "*" not in origin
            )
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("WEB_ORIGINS must contain explicit HTTP(S) origins without paths.")
        if origin not in origins:
            origins.append(origin)
    return origins


def packet_research_policy() -> str:
    """Server-selected pilot policy; never rewrite or accept a browser-supplied identity."""
    value = os.environ.get("PACKET_RESEARCH_POLICY", "e1-weekly-sonoma-v1")
    if value not in {"e1-weekly-sonoma-v1", "e1-wp7-liveproof-2026-10-16-v1"}:
        raise ValueError("Unsupported packet research policy.")
    return value
