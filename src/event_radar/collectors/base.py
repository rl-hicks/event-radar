from abc import ABC, abstractmethod
from datetime import datetime

from event_radar.models.event import Event


class EventCollector(ABC):
    """Interface implemented by every external event source."""

    @abstractmethod
    async def collect(
        self,
        start: datetime,
        end: datetime,
    ) -> list[Event]:
        """Collect events within the requested time window."""
