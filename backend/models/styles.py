"""Style & Color Master Pydantic Models."""

from enum import Enum
from typing import List, Optional, Dict, Literal, Any
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from models.materials import BomItem, BomLineOverride, LaborItem

OnlineStatus = Literal[
    "draft", "sample_approved", "photoshoot_completed", "catalog_completed",
    "price_finalized", "ready_for_launch", "live",
    "liquidation_candidate", "archived",
]


class OnlineStatusEnum(str, Enum):
    """All valid online lifecycle statuses. Mirrors ONLINE_STATUS_SEQUENCE + side-branches."""
    draft                 = "draft"
    sample_approved       = "sample_approved"
    photoshoot_completed  = "photoshoot_completed"
    catalog_completed     = "catalog_completed"
    price_finalized       = "price_finalized"
    ready_for_launch      = "ready_for_launch"
    live                  = "live"
    liquidation_candidate = "liquidation_candidate"
    archived              = "archived"


ONLINE_STATUS_SEQUENCE = [
    "draft", "sample_approved", "photoshoot_completed", "catalog_completed",
    "price_finalized", "ready_for_launch", "live",
]

ONLINE_STATUS_SIDE_BRANCHES = {"liquidation_candidate", "archived"}

PLANNED_COMPONENTS = ["upper", "bottom", "sole", "insole", "lace", "box"]


class StyleIn(BaseModel):
    code: Optional[str] = ""
    name: str
    category: Optional[str] = "Footwear"
    image_url: Optional[str] = ""
    image_display_url:   Optional[str] = ""
    image_thumbnail_url: Optional[str] = ""
    description: Optional[str] = ""
    base_size: Optional[str] = "7"
    insole_mould_name: Optional[str] = None   # die/mold used to cut insole pieces
    sole_mould_name:   Optional[str] = None   # mold used for the sole
    bom: List[BomItem] = []
    labor: List[LaborItem] = []
    overhead_pct: float = 0
    packing_cost: float = 0
    margin_pct: float = 25
    gst_pct: float = 5
    default_pairs_per_carton: Optional[Dict[str, Any]] = None
    color_bom_overrides: Optional[Dict[str, List[BomLineOverride]]] = Field(default_factory=dict)

    @field_validator("color_bom_overrides", mode="before")
    @classmethod
    def _validate_color_bom_overrides(cls, v):
        if v is None:
            return {}
        if not isinstance(v, dict):
            return v
        cleaned = {}
        for k, lines in v.items():
            if not isinstance(k, str) or not k.strip():
                raise PydanticCustomError("color_name_empty", "Color override key cannot be empty")
            cleaned[k.strip()] = lines
        return cleaned


class PlannedComponent(BaseModel):
    component: Literal["upper", "bottom", "sole", "insole", "lace", "box"]
    planned_qty: int = 0


class StyleLifecycleUpsert(BaseModel):
    sale_channels:            Optional[List[Literal["myntra", "flipkart", "nykaa", "website"]]] = None
    mrp:                      Optional[float] = None
    online_selling_price:     Optional[float] = None
    platform_commission_pct:  Optional[Dict[str, float]] = None
    planned_min_stock:        Optional[int] = None
    planned_components:       Optional[List[PlannedComponent]] = None
    planned_colors:           Optional[List[str]] = None
    planned_sizes:            Optional[List[str]] = None
    sole_mould_name:          Optional[str] = None
    sole_shape:               Optional[str] = None
    pattern_number:           Optional[str] = None
    photoshoot_link:          Optional[str] = None
    catalogue_link:           Optional[str] = None


class OnlineStatusPatchIn(BaseModel):
    to_status: OnlineStatusEnum
    notes:     Optional[str] = ""


class ColorMasterIn(BaseModel):
    color_name: str
    color_code: str
    active: bool = True

    @field_validator("color_code")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not (2 <= len(v) <= 3) or not v.isalpha():
            raise PydanticCustomError(
                "color_code_format",
                "color_code must be 2-3 uppercase letters (e.g. TN, GN)",
            )
        return v

    @field_validator("color_name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise PydanticCustomError("color_name_empty", "color_name is required")
        return v


class ColorMasterUpdate(BaseModel):
    color_name: Optional[str] = None
    color_code: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("color_code")
    @classmethod
    def _upper_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if not (2 <= len(v) <= 3) or not v.isalpha():
            raise PydanticCustomError(
                "color_code_format",
                "color_code must be 2-3 uppercase letters (e.g. TN, GN)",
            )
        return v

    @field_validator("color_name")
    @classmethod
    def _clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise PydanticCustomError("color_name_empty", "color_name cannot be empty")
        return v
