"""Keep E0 read-only CORS; enable writes only on the context resource."""

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class ProductCORSMiddleware:
    def __init__(self, app: ASGIApp, *, origins: list[str]) -> None:
        self.read_only = CORSMiddleware(
            app,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Authorization"],
        )
        self.context = CORSMiddleware(
            app,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        middleware = (
            self.context
            if (
                scope.get("path") == "/api/me/context"
                or scope.get("path", "").startswith("/api/me/delivery/")
            )
            else self.read_only
        )
        await middleware(scope, receive, send)
