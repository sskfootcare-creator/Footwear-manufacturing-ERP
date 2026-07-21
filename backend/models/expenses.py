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


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    date: Optional[str] = None
    payee: Optional[str] = None
    notes: Optional[str] = None
    receipt: Optional[Any] = None
