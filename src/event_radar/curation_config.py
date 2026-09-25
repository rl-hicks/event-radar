from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CurationConfig:
    event_description_max_characters: int = 1_200
    maximum_event_candidates: int = 28
    maximum_hike_candidates: int = 10
    maximum_retained_options: int = 18
    reasoning_effort: Literal["low", "medium", "high"] = "medium"


DEFAULT_CURATION_CONFIG = CurationConfig()
