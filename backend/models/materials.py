"""Raw Materials & BOM Pydantic Models."""

from typing import Optional, Literal
from pydantic import BaseModel


class MaterialIn(BaseModel):
    code: str
    name: str
    category: Literal["upper", "sole", "lining", "accessory", "consumable", "packing", "other"]
    unit: str
    rate: float
    reorder_level: float = 0
    notes: Optional[str] = ""
    preferred_vendor_id: Optional[str] = ""
    image_url:           Optional[str] = ""
    image_display_url:   Optional[str] = ""
    image_thumbnail_url: Optional[str] = ""


class BomItem(BaseModel):
    material_id: str
    material_name: str
    material_code: str
    unit: str
    rate: float
    quantity: float
    yield_per_unit: float = 1
    waste_pct: float = 0
    section: str = "Other"
    component: Optional[str] = None


class LaborItem(BaseModel):
    name: str
    rate: float


class QuantityUpdate(BaseModel):
    quantity: Optional[int] = None
    completed_qty: Optional[int] = None
    rejected_qty: Optional[int] = None
    reason: Optional[str] = ""


class InventoryMovement(BaseModel):
    material_id: str
    type: Literal["in", "out", "adjustment"]
    quantity: float
    rate: Optional[float] = None
    party: Optional[str] = ""
    job_id: Optional[str] = None
    notes: Optional[str] = ""
    date: Optional[str] = ""
