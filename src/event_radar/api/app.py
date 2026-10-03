"""ASGI application shell. Product routes are added in later work packages."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build an application without loading private state or external clients."""
    return FastAPI(title="Event Radar", docs_url=None, redoc_url=None, openapi_url=None)
