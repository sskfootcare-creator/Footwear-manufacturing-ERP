"""Investor entity, advances, repayments, and portal Pydantic models."""

from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class InvestorIn(BaseModel):
    name: str = Field(..., description="Investor full name or organization")
    contact: Optional[str] = Field("", description="Primary contact info / phone / email")
    phone: Optional[str] = Field("", description="Phone number for portal login")
    email: Optional[str] = Field("", description="Email address")
    default_margin_per_pair: float = Field(10.0, ge=0.0, description="Default negotiated margin per pair in INR")
    active: bool = True
    notes: Optional[str] = ""
    pin: Optional[str] = None

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "":
            v = str(v).strip()
            if not v.isdigit() or not (4 <= len(v) <= 6):
                raise ValueError("PIN must be 4–6 digits")
            return v
        return None


class InvestorUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    default_margin_per_pair: Optional[float] = Field(None, ge=0.0)
    active: Optional[bool] = None
    notes: Optional[str] = None


class InvestorAdvanceCreateIn(BaseModel):
    po_id: Optional[str] = Field(None, description="Purchase Order MongoDB ObjectId or string id")
    po_ids: Optional[List[str]] = Field(None, description="Optional list of Purchase Order IDs to fund in batch")
    include_opex: bool = Field(False, description="Whether to include investor opex recurring templates once")
    margin_per_pair: Optional[float] = Field(None, ge=0.0, description="Optional negotiable margin per pair override")
    advance_date: Optional[str] = Field(None, description="Advance date (YYYY-MM-DD)")
    bank_account_id: Optional[str] = Field(None, description="Company bank account receiving the investor funding")
    payment_mode: Optional[str] = Field("Bank Transfer", description="Inflow mode: NEFT, RTGS, IMPS, Bank Transfer, Cheque")
    reference: Optional[str] = Field("", description="Transaction UTR / payment reference")
    notes: Optional[str] = ""


class InvestorBatchAdvanceCreateIn(BaseModel):
    po_ids: List[str] = Field(..., min_length=1, description="List of Purchase Order IDs to fund simultaneously")
    include_opex: bool = Field(False, description="Whether to include investor opex recurring templates once across the batch")
    margin_per_pair: Optional[float] = Field(None, ge=0.0, description="Optional negotiable margin per pair override")
    advance_date: Optional[str] = Field(None, description="Advance date (YYYY-MM-DD)")
    bank_account_id: Optional[str] = Field(None, description="Company bank account receiving the investor funding")
    payment_mode: Optional[str] = Field("Bank Transfer", description="Inflow mode: NEFT, RTGS, IMPS, Bank Transfer, Cheque")
    reference: Optional[str] = Field("", description="Transaction UTR / payment reference")
    notes: Optional[str] = ""


class InvestorRepayActionIn(BaseModel):
    action: Literal["repay_in_full", "reinvest"] = Field(..., description="Action to perform: repay_in_full or reinvest")
    target_po_id: Optional[str] = Field(None, description="Target PO ID to reinvest into (required if action is reinvest)")
    margin_per_pair_override: Optional[float] = Field(None, ge=0.0, description="Optional negotiated margin override")
    payout_date: Optional[str] = Field(None, description="Payout / Reinvestment date (YYYY-MM-DD)")
    mode: Optional[str] = Field("Bank Transfer", description="Payment mode for margin/principal")
    payment_mode: Optional[str] = Field(None, description="Alias for mode")
    reference: Optional[str] = Field("", description="UTR or banking reference number")
    bank_account_id: Optional[str] = None
    include_opex_for_reinvestment: Optional[bool] = Field(False, description="Include opex in reinvestment advance calculation")
    notes: Optional[str] = ""


class InvestorBulkRepayActionIn(BaseModel):
    advance_ids: List[str] = Field(..., min_length=1, description="List of advance IDs to settle simultaneously")
    action: Literal["repay_in_full", "reinvest"] = Field(..., description="Action to perform: repay_in_full or reinvest")
    target_po_id: Optional[str] = Field(None, description="Target PO ID to reinvest into if action is reinvest")
    margin_per_pair_override: Optional[float] = Field(None, ge=0.0, description="Optional negotiated margin override")
    payout_date: Optional[str] = Field(None, description="Payout / Reinvestment date (YYYY-MM-DD)")
    mode: Optional[str] = Field("Bank Transfer", description="Payment mode for margin/principal")
    payment_mode: Optional[str] = Field(None, description="Alias for mode")
    reference: Optional[str] = Field("", description="UTR or banking reference number")
    bank_account_id: Optional[str] = None
    include_opex_for_reinvestment: Optional[bool] = Field(False, description="Include opex in reinvestment advance calculation")
    notes: Optional[str] = ""


class SetInvestorPinIn(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        v = str(v).strip()
        if not v.isdigit() or not (4 <= len(v) <= 6):
            raise ValueError("PIN must be 4–6 digits")
        return v


class InvestorLoginIn(BaseModel):
    """Investor portal login: phone or email + numeric PIN."""
    identifier: str = Field(..., description="Phone number or email address")
    pin: str = Field(..., description="Numeric PIN")
