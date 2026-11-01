from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    title: str
    start: datetime  # naive, in the configured time zone
    end: datetime
    location: str = ""
    notes: str = ""
    all_day: bool = False  # start/end are then midnights, end exclusive

    @property
    def key(self) -> str:
        """Identity of the event across runs (the feed's UID): same day, title and start time."""
        return f"{self.start.date().isoformat()}|{self.title}|{self.start:%H%M}"
