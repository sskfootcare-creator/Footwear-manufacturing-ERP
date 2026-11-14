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
    material_id:        Optional[str] = ""
    image_url:           Optional[str] = ""
    image_display_url:   Optional[str] = ""
    image_thumbnail_url: Optional[str] = ""


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
    material_id:        Optional[str] = None
    image_url:           Optional[str] = None
    image_display_url:   Optional[str] = None
    image_thumbnail_url: Optional[str] = None


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
    material_id:        Optional[str] = ""
    image_url:           Optional[str] = ""
    image_display_url:   Optional[str] = ""
    image_thumbnail_url: Optional[str] = ""
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


MANDATORY_FOOTWEAR_CATEGORIES = {
    "upper": "Upper",
    "insole_socks": "Insole/Socks",
    "sole": "Sole",
}


def classify_footwear_component(comp_doc: Optional[dict] = None, bom_item: Optional[dict] = None) -> str:
    """Classify component into one of the 3 essential footwear assembly pillars or other:
    - 'upper' (Upper, lining, vamp, strap, rexine, leather)
    - 'insole_socks' (Insole, sockliner, bottom board, strobel, socks, texon)
    - 'sole' (Sole, outsole, TPR, PVC, sheet)
    - 'other' (Box, tag, label, packaging, lace, etc.)
    """
    comp_doc = comp_doc or {}
    bom_item = bom_item or {}
    cat = str(comp_doc.get("component_category") or bom_item.get("component_category") or "").strip().lower()
    code = str(comp_doc.get("component_code") or bom_item.get("component_code") or "").strip().lower()
    name = str(comp_doc.get("component_name") or bom_item.get("component_name") or "").strip().lower()
    blob = f"{cat} {code} {name}"

    if any(w in blob for w in ("sole", "outsole", "tpr")) and "insole" not in blob:
        return "sole"
    if any(w in blob for w in ("insole", "sockliner", "bottom", "socks", "texon", "shank", "board")):
        return "insole_socks"
    if any(w in blob for w in ("upper", "lining", "vamp", "quarter", "collar", "strap", "rexine", "leather")):
        return "upper"
    if cat == "upper":
        return "upper"
    if cat in ("insole", "sockliner", "bottom"):
        return "insole_socks"
    if cat == "sole":
        return "sole"
    return "other"

