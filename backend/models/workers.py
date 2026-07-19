"""Workers & Payroll Pydantic Models."""

from typing import List, Optional, Literal
from pydantic import BaseModel


class WorkerIn(BaseModel):
    name: str
    phone: Optional[str] = ""
    skill: str = "general"
    rate_per_pair: float = 0
    active: bool = True
    notes: Optional[str] = ""
    bonus_pct: float = 0
    target_cycle_days: float = 0


class AssignmentUpdate(BaseModel):
    role: str
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    rate_per_pair: Optional[float] = None


class BulkAssign(BaseModel):
    job_ids: List[str]
    role: str
    worker_id: Optional[str] = None
    rate_per_pair: Optional[float] = None


class AdvanceIn(BaseModel):
    worker_id: str
    amount: float
    date: Optional[str] = ""
    notes: Optional[str] = ""
    txn_type: Literal["advance", "payment", "bonus", "adjustment"] = "advance"
