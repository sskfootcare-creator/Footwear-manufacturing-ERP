"""Notification document model (in-app only — no push/WhatsApp/email)."""

from typing import Optional
from pydantic import BaseModel


class NotificationIn(BaseModel):
    """Internal: created automatically by the ready-for-pickup endpoint."""
    type: str = "pickup_ready"
    job_id: str
    style_code: str
    stage: str
    worker_id: str
    worker_name: str
    completed_qty: int
    at: str
    notes: Optional[str] = ""
    read: bool = False
    read_by: Optional[str] = None
    read_at: Optional[str] = None
