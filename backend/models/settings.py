"""Application Settings & SLA Pydantic Models."""

from typing import Dict
from pydantic import BaseModel


class StageDurationsIn(BaseModel):
    hours: Dict[str, float]
