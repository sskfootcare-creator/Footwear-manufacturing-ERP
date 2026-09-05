"""Workers & Payroll Pydantic Models."""

from typing import List, Optional, Literal
from pydantic import BaseModel, field_validator


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


# ── Worker PIN & login ────────────────────────────────────────────────────────

class SetPinIn(BaseModel):
    """Admin/manager: set or reset a 4–6 digit numeric PIN for a worker."""
    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or not (4 <= len(v) <= 6):
            raise ValueError("PIN must be 4–6 digits")
        return v


class WorkerLoginIn(BaseModel):
    """Worker self-login: phone number + numeric PIN."""
    phone: str
    pin: str


class ReadyForPickupIn(BaseModel):
    """Worker marks a job or grouped job ready for the manager to collect."""
    completed_qty: Optional[int] = None
    notes: Optional[str] = ""
    size_breakdown: Optional[dict] = None  # e.g. {"4": 120, "5": 120, "6": 240} or {job_id: qty}


class WagePaymentIn(BaseModel):
    worker_id: str
    worker_name: Optional[str] = ""
    amount: float
    period_from: str
    period_to: str
    paid_via: Literal["cash", "bank_transfer", "upi"]
    cash_ledger_id: Optional[str] = None
    bank_account_id: Optional[str] = None
    upi_reference: Optional[str] = None
    linked_expense_id: Optional[str] = None
    date: str
    paid_by: Optional[str] = ""
    notes: Optional[str] = ""
    override_reason: Optional[str] = None



