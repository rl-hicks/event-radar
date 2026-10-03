from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str


class MeResponse(BaseModel):
    id: UUID
    email: str | None
    created_at: datetime
    database_roundtrip: bool
