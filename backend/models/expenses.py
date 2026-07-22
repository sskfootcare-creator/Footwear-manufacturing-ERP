"""Expense models for SSK Footcare ERP."""

from typing import Optional, Any
from pydantic import BaseModel, Field


EXPENSE_CATEGORIES = [
    "Rent & Utilities",
    "Raw Materials",
    "Machinery & Maintenance",
    "Labor & Wages",
    "Transport & Logistics",
    "Packaging & Printing",
    "Office & Administrative",
    "Marketing & Sales",
    "Tax & Professional Fees",
    "Other Expenses"
]


class ExpenseIn(BaseModel):
    category: str = Field(..., description="Expense category")
    amount: float = Field(..., gt=0, description="Expense amount in INR")
    date: str = Field(..., description="Expense date (YYYY-MM-DD)")
    payee: str = Field(..., description="Payee / Recipient name")
    notes: Optional[str] = ""
    receipt: Optional[Any] = None
    is_recurring: bool = False
    recurring_expense_id: Optional[str] = None
    status: str = "confirmed"  # confirmed, due, overdue


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    date: Optional[str] = None
    payee: Optional[str] = None
    notes: Optional[str] = None
    receipt: Optional[Any] = None
    is_recurring: Optional[bool] = None
    recurring_expense_id: Optional[str] = None
    status: Optional[str] = None


class RecurringExpenseIn(BaseModel):
    category: str = Field(..., description="rent/electricity/salary/EMI/other")
    payee: str = Field(..., description="Payee / Recipient name")
    amount: float = Field(..., gt=0, description="Base amount in INR")
    frequency: str = Field("monthly", description="monthly/quarterly/yearly")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    due_day: int = Field(..., ge=1, le=31, description="Day of month (1-31)")
    end_date: Optional[str] = None
    active: bool = True
    notes: Optional[str] = ""


class RecurringExpenseUpdate(BaseModel):
    category: Optional[str] = None
    payee: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    frequency: Optional[str] = None
    start_date: Optional[str] = None
    due_day: Optional[int] = Field(None, ge=1, le=31)
    end_date: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
