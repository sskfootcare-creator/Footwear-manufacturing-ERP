"""Vendors & Accounts Payable Pydantic Models."""

from typing import List, Optional, Literal
from pydantic import BaseModel

DEFAULT_CREDIT_DAYS = 45
PAYMENT_MODES = ["Bank Transfer", "RTGS", "NEFT", "Cheque", "UPI", "Cash", "Adjustment"]


class GRNLineItem(BaseModel):
    style_code: str = ""
    description: str = ""
    color: str = ""
    size: str = ""
    dispatched_qty: int = 0
    received_qty: int = 0
    accepted_qty: int = 0
    rejected_qty: int = 0
    rejection_reason: str = ""


class GRNIn(BaseModel):
    invoice_id: str
    grn_date: str
    received_date: Optional[str] = ""
    client_reference: Optional[str] = ""
    notes: Optional[str] = ""
    line_items: List[GRNLineItem]


class PaymentIn(BaseModel):
    invoice_ids: List[str]
    amount: float
    payment_date: str
    mode: Literal["Bank Transfer", "RTGS", "NEFT", "Cheque", "UPI", "Cash", "Adjustment"]
    reference: Optional[str] = ""
    bank: Optional[str] = ""
    notes: Optional[str] = ""


class VendorIn(BaseModel):
    name: str
    gstin: Optional[str] = ""
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""
    payment_terms_days: int = 30
    active: bool = True
    notes: Optional[str] = ""


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms_days: Optional[int] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class VendorPOLineItem(BaseModel):
    material_id: str
    quantity: float
    rate: float
    amount: float
    received_quantity: float = 0.0


class VendorPOIn(BaseModel):
    vendor_id: str
    line_items: List[VendorPOLineItem]
    status: Literal["draft", "sent", "partially_received", "received", "cancelled"] = "draft"
    expected_delivery_date: Optional[str] = ""
    notes: Optional[str] = ""


class VendorPOUpdate(BaseModel):
    vendor_id: Optional[str] = None
    line_items: Optional[List[VendorPOLineItem]] = None
    status: Optional[Literal["draft", "sent", "partially_received", "received", "cancelled"]] = None
    expected_delivery_date: Optional[str] = None
    notes: Optional[str] = None


class VendorPOReceiveItem(BaseModel):
    material_id: str
    quantity: float


class VendorPOReceiveIn(BaseModel):
    receipt_id: str
    items: List[VendorPOReceiveItem]


class DefectIn(BaseModel):
    po_number: str
    article: Optional[str] = ""
    stage: str
    defect_type: str
    description: str
    defective_qty: int
    root_cause: Optional[str] = ""
    responsible_dept: Optional[str] = ""
    corrective_action: Optional[str] = ""
    rework_qty: int = 0
    rework_completed: bool = False
    final_rejection_qty: int = 0
    cost: float = 0
    status: Literal["open", "in_progress", "closed"] = "open"
