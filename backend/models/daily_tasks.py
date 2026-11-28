"""Pydantic models for Daily Tasks, Partner To-Do, and Expense-Linked Shopping Lists."""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class PhotoAttachment(BaseModel):
    url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = ""
    uploaded_by: Optional[str] = ""
    uploaded_at: Optional[str] = ""


class VoiceNoteAttachment(BaseModel):
    url: str
    duration_sec: Optional[float] = 0
    mime_type: Optional[str] = "audio/webm"
    uploaded_by: Optional[str] = ""
    uploaded_at: Optional[str] = ""


class DailyTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = ""
    task_type: Literal["staff_task", "partner_todo"] = "staff_task"
    priority: Literal["P0", "P1", "P2"] = "P1"
    project: Optional[str] = "Factory Ops"
    task_date: Optional[str] = None
    due_time: Optional[str] = "17:30"
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_role: Optional[str] = None
    approver_id: Optional[str] = None
    approver_name: Optional[str] = None
    erp_ref_type: Optional[Literal["po", "sample", "picklist", "invoice"]] = None
    erp_ref_label: Optional[str] = None
    photos: List[PhotoAttachment] = Field(default_factory=list)
    voice_notes: List[VoiceNoteAttachment] = Field(default_factory=list)


class NonCompletionReason(BaseModel):
    category: str = Field(..., min_length=1)
    note: Optional[str] = ""


class DailyTaskStatusUpdate(BaseModel):
    status: Literal[
        "pending",
        "in_progress",
        "needs_input",
        "pending_approval",
        "done",
        "reopened",
        "carried_forward",
    ]
    note: Optional[str] = ""
    non_completion_reason: Optional[NonCompletionReason] = None


class DailyTaskCommentCreate(BaseModel):
    message: Optional[str] = ""
    mentions: List[str] = Field(default_factory=list)
    photos: List[PhotoAttachment] = Field(default_factory=list)
    voice_notes: List[VoiceNoteAttachment] = Field(default_factory=list)


class DailyListCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    list_type: Literal["shopping", "checklist"] = "shopping"
    project: Optional[str] = "Factory Ops"


class DailyListItemCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=250)
    qty: Optional[str] = ""
    expense_category: str = "Other Expenses"
    estimated_amount: Optional[float] = 0.0
    actual_amount: Optional[float] = None
    shop_note: Optional[str] = ""


class DailyListItemUpdate(BaseModel):
    text: Optional[str] = None
    qty: Optional[str] = None
    expense_category: Optional[str] = None
    estimated_amount: Optional[float] = None
    actual_amount: Optional[float] = None
    shop_note: Optional[str] = None
    done: Optional[bool] = None


class DailyListSettleIn(BaseModel):
    settlement_mode: Literal["bank_transfer", "cash_withdrawal"] = "bank_transfer"
    bank_account_id: str = Field(..., min_length=1)
    date: Optional[str] = None
    payee: Optional[str] = None
    notes: Optional[str] = ""
