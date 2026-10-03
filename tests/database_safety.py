"""Fail closed before any integration-test connection or destructive migration."""

from sqlalchemy.engine import URL

from event_radar.db.config import postgres_url


def isolated_test_url(value: str) -> URL:
    url = postgres_url(value)
    if (
        url.host != "127.0.0.1"
        or url.port != 55432
        or url.database != "event_radar_test"
        or url.username != "event_radar_test"
        or url.query
    ):
        raise ValueError("TEST_DATABASE_URL must target the dedicated local test service.")
    return url
