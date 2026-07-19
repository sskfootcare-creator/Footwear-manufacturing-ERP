"""B2B Purchase Orders & Production Job Stage Pydantic Models."""

from typing import List, Optional, Literal
from pydantic import BaseModel

PRODUCTION_STAGES = [
    "procurement", "cutting", "folding", "attachment",
    "stitching", "lasting", "sole_pasting", "finishing", "qc_pack", "dispatched",
]


class POLineItem(BaseModel):
    style_code: str
    external_sku: Optional[str] = ""
    description: Optional[str] = ""
    color: Optional[str] = ""
    size: Optional[str] = ""
    hsn_code: Optional[str] = ""
    quantity: int
    unit_price: float
    amount: float


class POIn(BaseModel):
    po_number: str
    po_date: str
    client_name: str
    client_address: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    client_gstin: Optional[str] = ""
    client_state: Optional[str] = ""
    client_state_code: Optional[str] = ""
    delivery_date: Optional[str] = ""
    payment_terms: Optional[str] = ""
    currency: str = "INR"
    line_items: List[POLineItem]
    subtotal: float = 0
    cgst_rate: float = 0
    cgst_amount: float = 0
    sgst_rate: float = 0
    sgst_amount: float = 0
    igst_rate: float = 0
    igst_amount: float = 0
    grand_total: float = 0
    total_quantity: int = 0
    notes: Optional[str] = ""


class ProductionStageUpdate(BaseModel):
    stage: Literal["procurement", "cutting", "folding", "attachment",
                   "stitching", "lasting", "sole_pasting", "finishing", "qc_pack", "dispatched"]
    completed_qty: Optional[int] = None
    rejected_qty: Optional[int] = None
    qc_pass: Optional[bool] = None
    notes: Optional[str] = ""
    confirm_skip: bool = False
