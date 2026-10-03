"""Backend identity seam. Real token verification belongs to WP4."""

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    email: str | None = None


def get_current_user() -> AuthenticatedUser:
    # Never infer identity from query parameters, headers, or unverified tokens.
    raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})
