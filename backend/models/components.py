"""Component Master & Inventory Pydantic Models."""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel


class ComponentUpdate(BaseModel):
    upper_done: Optional[bool] = None
    bottom_done: Optional[bool] = None
    sole_done: Optional[bool] = None
    notes: Optional[str] = ""


class ComponentIn(BaseModel):
    component_code:     str
    component_name:     str
    component_category: Literal[
        "Upper", "Sole", "Insole", "Sockliner", "Bottom",
        "Lace", "Box", "Tag", "Label", "Packaging", "Other",
    ]
    color:              Optional[str] = ""
    size:               Optional[str] = ""
    vendor:             Optional[str] = ""
    unit:               Optional[str] = "pair"
    current_stock:      int = 0
    reorder_level:      int = 0
    minimum_stock:      int = 0
    lead_time_days:     int = 0
    active:             bool = True


class ComponentMasterUpdate(BaseModel):
    component_name:     Optional[str] = None
    component_category: Optional[Literal[
        "Upper", "Sole", "Insole", "Sockliner", "Bottom",
        "Lace", "Box", "Tag", "Label", "Packaging", "Other",
    ]] = None
    vendor:             Optional[str] = None
    unit:               Optional[str] = None
    reorder_level:      Optional[int] = None
    minimum_stock:      Optional[int] = None
    lead_time_days:     Optional[int] = None
    active:             Optional[bool] = None


class ComponentBulkMatrix(BaseModel):
    component_code:     str
    component_name:     str
    component_category: Literal[
        "Upper", "Sole", "Insole", "Sockliner", "Bottom",
        "Lace", "Box", "Tag", "Label", "Packaging", "Other",
    ]
    vendor:             Optional[str] = ""
    unit:               Optional[str] = "pair"
    reorder_level:      int = 0
    minimum_stock:      int = 0
    lead_time_days:     int = 0
    rows: List[Dict[str, Any]]


class ComponentMovementIn(BaseModel):
    component_id:   str
    movement_type:  Literal[
        "purchase_in", "return_in", "adjustment",
        "production_reserve", "online_reserve", "unreserve",
        "production_issue", "online_issue",
    ]
    quantity:       int
    adjustment_dir: Optional[Literal["increase", "decrease"]] = None
    reference_type: Optional[str] = "manual"
    reference_id:   Optional[str] = ""
    style_id:       Optional[str] = ""
    notes:          Optional[str] = ""


class StyleComponentMappingIn(BaseModel):
    style_id:           str
    component_id:       str
    quantity_per_pair:  float = 1.0
    wastage_percent:    float = 0.0
    active:             bool  = True


class StyleComponentMappingUpdate(BaseModel):
    quantity_per_pair:  Optional[float] = None
    wastage_percent:    Optional[float] = None
    active:             Optional[bool]  = None
