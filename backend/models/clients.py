"""Pydantic models for Client Master and Direct Invoice creation."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ClientAddress(BaseModel):
    address_line: str = ""
    city: str = ""
    state: str = "Uttar Pradesh"
    state_code: str = "09"
    pincode: str = ""


class ClientIn(BaseModel):
    company_name: str = Field(..., description="Client company / trade name")
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    gstin: Optional[str] = ""
    pan: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    state: Optional[str] = "Uttar Pradesh"
    state_code: Optional[str] = "09"
    payment_terms_days: Optional[int] = 30
    notes: Optional[str] = ""
    is_active: Optional[bool] = True


class DirectInvoiceLineItem(BaseModel):
    style_code: str = Field(..., description="Style code or product name")
    color: Optional[str] = ""
    size: Optional[str] = ""
    description: Optional[str] = ""
    hsn_code: Optional[str] = "6403"
    qty: int = Field(..., gt=0, description="Quantity in pairs")
    unit_price: float = Field(..., ge=0, description="Rate per pair")


class DirectInvoiceIn(BaseModel):
    # Client info
    client_id: Optional[str] = None
    client_name: str = Field(..., description="Client company / business name")
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    client_gstin: Optional[str] = ""
    pan: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    place_of_supply: Optional[str] = "09-Uttar Pradesh"
    client_state_code: Optional[str] = "09"

    # Invoice parameters
    invoice_date: Optional[str] = None  # DD/MM/YYYY or YYYY-MM-DD
    payment_terms_days: Optional[int] = 30
    due_date: Optional[str] = None      # Optional override; auto-computed if omitted

    # Dispatch / Logistics details (optional)
    transport_mode: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    supply_date: Optional[str] = ""
    notes: Optional[str] = ""

    # Tax configuration (Norms: Footwear 5% default: 2.5% CGST + 2.5% SGST or 5% IGST)
    gst_rate: Optional[float] = 5.0
    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    igst_rate: Optional[float] = None

    # Line Items
    line_items: List[DirectInvoiceLineItem] = Field(..., min_length=1)

    # Master saving option
    save_client_to_master: Optional[bool] = True
