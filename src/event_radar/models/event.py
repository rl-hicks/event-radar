from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl


class Event(BaseModel):
    """A normalized event gathered from an external source."""

    source_name: str = Field(min_length=1)
    source_id: str | None = None
    source_url: HttpUrl

    title: str = Field(min_length=1)
    description: str | None = None

    start_time: datetime
    end_time: datetime | None = None

    venue: str | None = None
    city: str
    state: str = "CA"

    categories: set[str] = Field(default_factory=set)

    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)

    def is_free(self) -> bool:
        return self.price_min == Decimal("0")
