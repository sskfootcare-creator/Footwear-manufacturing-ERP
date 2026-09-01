from typing import Optional, Literal, Dict, List, Any
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError
from models.sku_map import SheetLocator, HeaderLocator

STATEMENT_CANONICAL_FIELDS = [
    "date",
    "narration",
    "reference",
    "debit_amount",
    "credit_amount",
    "balance",
]


class StatementImportConfigIn(BaseModel):
    sheet_locator: SheetLocator = Field(default_factory=lambda: SheetLocator(type="first_sheet"))
    header_locator: HeaderLocator = Field(default_factory=lambda: HeaderLocator(type="fixed_row", row=0))
    skip_rows_after_header: int = 0
    column_map: Dict[str, Optional[str]]
    date_format: Optional[str] = None  # e.g. "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"
    notes: Optional[str] = ""

    @field_validator("column_map")
    @classmethod
    def _validate_column_map(cls, v):
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        if not v.get("date") or not v.get("narration"):
            raise PydanticCustomError(
                "column_map_required_fields",
                "column_map must at minimum configure 'date' and 'narration'"
            )
        return v


class StatementImportConfigUpdate(BaseModel):
    sheet_locator: Optional[SheetLocator] = None
    header_locator: Optional[HeaderLocator] = None
    skip_rows_after_header: Optional[int] = None
    column_map: Optional[Dict[str, Optional[str]]] = None
    date_format: Optional[str] = None
    notes: Optional[str] = None


class BankAccountIn(BaseModel):
    name: str = Field(..., description="Account name e.g. HDFC - Online, UCO Bank - Offline")
    bank_name: str = Field(..., description="Bank name e.g. HDFC, UCO Bank")
    account_number_last4: str = Field(..., min_length=2, max_length=10, description="Last 4 digits of account number")
    account_number: Optional[str] = Field(None, description="Full bank account number")
    ifsc: Optional[str] = Field(None, description="Bank branch IFSC code e.g. UCBA0001860")
    branch: Optional[str] = Field(None, description="Bank branch name")
    account_type: Literal["online_channel", "b2b_client"] = Field("b2b_client", description="online_channel | b2b_client")
    opening_balance: float = Field(0.0, description="Opening balance in INR")
    opening_balance_date: Optional[str] = Field(None, description="Opening balance date (YYYY-MM-DD)")
    statement_format: Optional[StatementImportConfigIn] = Field(None, description="Configured statement column-mapping import format")
    active: bool = Field(True, description="Whether the bank account is active")


class BankAccountUpdate(BaseModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number_last4: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    branch: Optional[str] = None
    account_type: Optional[Literal["online_channel", "b2b_client"]] = None
    opening_balance: Optional[float] = None
    opening_balance_date: Optional[str] = None
    statement_format: Optional[StatementImportConfigUpdate] = None
    active: Optional[bool] = None


class MatchedTo(BaseModel):
    type: Literal["payment", "settlement", "expense", "vendor_payment", "transfer", "cash_withdrawal"]
    ref_id: str


class BankStatementLineIn(BaseModel):
    bank_account_id: str = Field(..., description="ID of the bank_accounts document")
    date: str = Field(..., description="Statement transaction date (YYYY-MM-DD)")
    narration: str = Field(..., description="Raw description from the statement")
    reference_no: Optional[str] = Field("", description="Transaction / UTR reference number")
    debit_amount: float = Field(0.0, ge=0, description="Debit amount (money out)")
    credit_amount: float = Field(0.0, ge=0, description="Credit amount (money in)")
    running_balance: Optional[float] = Field(None, description="Running balance reported by bank")
    match_status: Literal["unmatched", "matched", "transfer", "ignored"] = Field("unmatched", description="Reconciliation status")
    matched_to: Optional[MatchedTo] = Field(None, description="Linked internal record reference")
    remarks: Optional[str] = ""
    imported_at: Optional[str] = None
    imported_by: Optional[str] = None


class BankStatementLineUpdate(BaseModel):
    match_status: Optional[Literal["unmatched", "matched", "transfer", "ignored"]] = None
    matched_to: Optional[MatchedTo] = None
    narration: Optional[str] = None
    reference_no: Optional[str] = None
    remarks: Optional[str] = ""


class TransferConfirmIn(BaseModel):
    from_line_id: str = Field(..., description="ID of the debit statement line (sending account)")
    to_line_id: str = Field(..., description="ID of the credit statement line (receiving account)")
    notes: Optional[str] = ""


class CashWithdrawalConfirmIn(BaseModel):
    statement_line_id: str = Field(..., description="ID of the debit statement line (withdrawn from bank)")
    existing_cash_ledger_id: Optional[str] = Field(None, description="Optional ID of existing manual cash ledger entry to link to")
    notes: Optional[str] = Field("", description="Optional notes or reference for the cash ledger entry")


class CashLedgerCreateIn(BaseModel):
    bank_account_id: str = Field(..., description="ID of the bank account where cash was withdrawn")
    amount: float = Field(..., gt=0, description="Cash withdrawal amount (must be > 0)")
    date: str = Field(..., description="Date of cash withdrawal (YYYY-MM-DD)")
    notes: Optional[str] = Field("", description="Optional notes or reference for the cash ledger entry")


class PeriodLockIn(BaseModel):
    bank_account_id: Optional[str] = Field(None, description="Specific bank account ID or 'all' / None for all accounts")
    period_from: str = Field(..., description="Start date of the lock period (YYYY-MM-DD)")
    period_to: str = Field(..., description="End date of the lock period (YYYY-MM-DD)")
    reason: Optional[str] = Field("Monthly reconciliation finalized", description="Reason for locking period")


class PeriodUnlockIn(BaseModel):
    bank_account_id: Optional[str] = Field(None, description="Specific bank account ID or 'all' / None for all accounts")
    period_from: str = Field(..., description="Start date of the locked period to unlock (YYYY-MM-DD)")
    period_to: str = Field(..., description="End date of the locked period to unlock (YYYY-MM-DD)")
    reason: str = Field("Admin correction", description="Reason for unlocking period (audit logged)")



