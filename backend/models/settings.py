"""Application Settings & SLA Pydantic Models."""

from typing import Dict
from pydantic import BaseModel

# Sensible factory defaults (in hours)
DEFAULT_STAGE_HOURS: Dict[str, float] = {
    "procurement": 24,
    "cutting": 24,
    "folding": 8,
    "attachment": 8,
    "stitching": 48,
    "lasting": 24,
    "sole_pasting": 12,
    "finishing": 12,
    "qc_pack": 12,
    "dispatched": 0,
}


class StageDurationsIn(BaseModel):
    hours: Dict[str, float]
