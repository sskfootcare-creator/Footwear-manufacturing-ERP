import uuid
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


def _gen_line_id() -> str:
    return uuid.uuid4().hex[:8]


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
    with_eva:            Optional[bool] = None
    is_component:       Optional[bool] = False
    component_category: Optional[str] = None
    default_yield_per_unit: Optional[float] = None
    color:               Optional[str] = ""
    weighted_avg_rate:   Optional[float] = None
    last_purchase_rate:  Optional[float] = None
    balance:             Optional[float] = 0.0


class BomItem(BaseModel):
    line_id: Optional[str] = Field(default_factory=_gen_line_id)
    material_id: Optional[str] = ""
    material_name: Optional[str] = ""
    material_code: Optional[str] = ""
    unit: Optional[str] = ""
    rate: float = 0.0
    quantity: float = 0.0
    yield_per_unit: float = 1.0
    waste_pct: float = 0.0
    section: str = "Other"
    component: Optional[str] = None
    with_eva: Optional[bool] = None
    color: Optional[str] = ""   # the specific color chosen for THIS style's BOM line — free text

    @field_validator("line_id", mode="before")
    @classmethod
    def _ensure_line_id(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return _gen_line_id()
        return str(v).strip()

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)


class ColorMaterialOverride(BaseModel):
    material_id: str
    material_name: str
    material_code: str
    rate: float
    quantity: Optional[float] = None

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)


class BomLineOverride(BaseModel):
    line_id: Optional[str] = None   # references a base BOM line's line_id to override; None = this is a brand-new line added only for this color
    removed: bool = False           # true = drop this base line entirely for this color (e.g. a component not used in one color)
    # all fields below: None = inherit from the base line; set = override it
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    material_code: Optional[str] = None
    unit: Optional[str] = None
    rate: Optional[float] = None
    quantity: Optional[float] = None
    yield_per_unit: Optional[float] = None
    waste_pct: Optional[float] = None
    section: Optional[str] = None
    component: Optional[str] = None
    with_eva: Optional[bool] = None
    color: Optional[str] = None



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
