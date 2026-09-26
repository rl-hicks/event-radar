from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class EventSource(BaseModel):
    """Provenance for an additional source matched to an event."""

    source_name: str = Field(min_length=1)
    source_id: str | None = None
    source_url: HttpUrl


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
    price_currency: str | None = Field(default=None, min_length=3, max_length=3)
    price_details: str | None = Field(default=None, min_length=1)
    price_conflict: bool = False
    alternate_sources: list[EventSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_price_range(self) -> "Event":
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_max < self.price_min
        ):
            raise ValueError("Event maximum price must not be below minimum price.")
        if self.price_currency is not None:
            self.price_currency = self.price_currency.upper()
        return self

    def is_free(self) -> bool:
        return self.price_min == Decimal("0") and self.price_max in (None, Decimal("0"))
