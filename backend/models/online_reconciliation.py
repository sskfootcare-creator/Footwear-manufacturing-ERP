"""Online Reconciliation Pydantic Models."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DailyPaymentRow(BaseModel):
    neft_ref: Optional[str] = ""
    settled_amount: float = 0.0
    commission: float = 0.0
    shipping_fee: float = 0.0
    tds: float = 0.0
    payment_type: str = "postpaid"  # prepaid or postpaid
    order_type: str = "Forward"     # Forward or Reverse
    order_release_id: Optional[str] = ""
    seller_order_id: Optional[str] = ""
    order_line_id: Optional[str] = ""
    return_id: Optional[str] = ""
    payment_date: Optional[str] = ""


class DailyPaymentImportIn(DailyPaymentRow):
    pass


class SettlementImportIn(BaseModel):
    order_release_id: Optional[str] = ""
    seller_order_id: Optional[str] = ""
    sku_id: Optional[str] = ""
    style_id: Optional[str] = ""
    settled_amount_postpaid: float = 0.0
    settled_amount_prepaid: float = 0.0
    amount_pending_settlement_postpaid: float = 0.0
    amount_pending_settlement_prepaid: float = 0.0
    commission: float = 0.0
    logistics_cost_forward: float = 0.0
    logistics_cost_reverse: float = 0.0
    reverse_additional_charges: float = 0.0
    fixed_fee: float = 0.0
    pick_and_pack_fees: float = 0.0
    tech_enablement_charges: float = 0.0
    tds: float = 0.0
    tcs: float = 0.0
    gst: float = 0.0
    return_date: Optional[str] = ""
    return_type: Optional[str] = ""
    neft_ref: Optional[str] = ""


class NonOrderDeductionRow(BaseModel):
    seller_id: Optional[str] = ""
    settlement_amount: float = 0.0
    settlement_type: Optional[str] = ""
    utr: Optional[str] = ""
    invoice_ref: Optional[str] = ""
    settlement_date: Optional[str] = ""
    settlement_description: Optional[str] = ""


class NonOrderDeductionIn(NonOrderDeductionRow):
    pass


class MonthlyOrderRow(BaseModel):
    seller_order_id: str
    order_release_id: Optional[str] = ""
    sku_id: Optional[str] = ""
    style_id: Optional[str] = ""
    seller_sku_code: Optional[str] = ""
    size: Optional[str] = ""
    order_status: str = ""
    packed_on: Optional[str] = ""
    shipped_on: Optional[str] = ""
    delivered_on: Optional[str] = ""
    cancelled_on: Optional[str] = ""
    rto_return_creation_date: Optional[str] = ""
    final_amount: float = 0.0
    seller_price: float = 0.0


class StyleCostSnapshotIn(BaseModel):
    style_id: Optional[str] = None
    style_code: str
    effective_date: str  # YYYY-MM-DD
    total_cost: float = Field(..., gt=0)
    material_cost: float = 0.0
    labor_cost: float = 0.0
    notes: Optional[str] = ""


class ReconciliationRunIn(BaseModel):
    platform: str = "myntra"
    aged_pending_days: int = 30
    from_date: Optional[str] = None
    to_date: Optional[str] = None

