"""Small public error vocabulary; exception text is never sent to clients."""

from fastapi import Request
from starlette.responses import JSONResponse


class DatabaseUnavailable(Exception):
    pass


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request.state.error_code = code
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )
