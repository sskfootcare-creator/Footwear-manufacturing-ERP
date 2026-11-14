"""Sample Development & Tracking System Models.

Footwear sampling & product development (PD) pipeline:
- Upload inspiration / reference photos (kept isolated from Style Master and Material photos)
- Generate temporary style codes (SMP-YYYY-XXXX)
- Capture rich footwear technical specs across Upper, Insole/Socks, and Sole/Heel
- Approve or Discard / Reject samples
- 1-Click Transfer to Style Master with auto-generated BOM items and Labor operations
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError


SampleStatus = Literal[
    "draft",
    "in_sampling",
    "sample_ready",
    "approved",
    "rejected",
    "transferred_to_style",
]


class SamplePhoto(BaseModel):
    photo_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    url: str
    thumbnail_url: Optional[str] = None
    file_id: Optional[str] = None
    caption: Optional[str] = ""
    is_primary: bool = False
    uploaded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: str = "sample_inspiration"


class UpperMaterialItem(BaseModel):
    """Multiple material specifications for upper top (Primary, Secondary, Trim, Accent, Strap, etc.)."""
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    material_code: Optional[str] = None
    color_to_develop: Optional[str] = ""
    placement: Optional[str] = "Primary"  # Primary, Secondary, Trim, Accent, Strap, Overlay, Counter, Toe Cap
    photo_url: Optional[str] = None


class UpperSpec(BaseModel):
    materials: List[UpperMaterialItem] = Field(default_factory=list)
    upper_top_material_id: Optional[str] = None
    upper_top_material_name: Optional[str] = None
    upper_top_material_code: Optional[str] = None
    upper_color_to_develop: Optional[str] = ""
    canvas_backing: Optional[str] = ""
    lining_material_id: Optional[str] = None
    lining_material_name: Optional[str] = None
    lining_material_code: Optional[str] = None
    cutting_operation: Literal["folding", "die_cut", "both"] = "die_cut"
    stitching_operation: Literal["stitching", "no_stitching"] = "stitching"
    edge_treatment: Literal["edge_coloring", "folded_edge", "raw_edge", "none"] = "none"
    has_buckle: bool = False
    buckle_spec: Optional[str] = ""
    buckle_photo_url: Optional[str] = None
    other_hardware: Optional[str] = ""


class InsoleSpec(BaseModel):
    profile_type: Literal["flat", "heeled"] = "flat"
    heeled_category: Optional[Literal["platforms", "pumps", "wedges", "block_heel", "other"]] = None
    insole_style_code_shape: Optional[str] = ""
    flat_mould_name_shape: Optional[str] = ""
    base_board: Literal["paper_board", "cellulose_board"] = "paper_board"
    shank_reinforced: bool = False
    cushioning_type: Literal["eva", "pu_foam", "both"] = "eva"
    cushioning_thickness_mm: str = "3mm"
    socks_covering_type: Literal["matching", "custom"] = "matching"
    socks_material_id: Optional[str] = None
    socks_material_name: Optional[str] = None
    socks_material_code: Optional[str] = None
    socks_color: Optional[str] = ""
    surface_detailing: Literal["none", "patchwork", "stitching", "both"] = "none"
    embossing: Literal["none", "gold_foil", "silver_foil", "blind_deboss", "heat_emboss"] = "none"
    embossing_details: Optional[str] = ""
    printing: Literal["none", "screen_printing", "heat_transfer", "digital_pad"] = "none"
    printing_details: Optional[str] = ""


class SoleSpec(BaseModel):
    sole_material: Literal["PVC", "PU", "TPR", "Neolite", "Sheet Sole", "Rubber", "EVA", "Other"] = "TPR"
    sole_type: Literal["ready_made", "die_cut"] = "ready_made"
    mould_name: Optional[str] = ""
    sole_shape: Optional[str] = "Round"
    velting: bool = False
    grinding: bool = False
    gripping: bool = False
    attaching_top_piece: bool = False
    other_processing: Optional[str] = ""
    heel_type: Optional[Literal["platform_gola", "block_heel", "spool", "stiletto", "wedge", "just_heel", "none"]] = "none"
    heel_mould_name: Optional[str] = ""
    heel_height: Optional[str] = ""
    heel_finish: Literal["colored", "covered", "none"] = "none"
    heel_covering_type: Literal["matching", "custom"] = "matching"
    heel_covering_material_id: Optional[str] = None
    heel_covering_material_name: Optional[str] = None


class SampleCreateIn(BaseModel):
    sample_name: str
    profile: Literal["flat", "heeled"] = "flat"
    category: Optional[str] = "Footwear"
    season: Optional[str] = ""
    target_gender: Optional[str] = "women"
    target_cost: Optional[float] = 0.0
    target_date: Optional[str] = ""
    assigned_karigar_id: Optional[str] = None
    assigned_karigar_name: Optional[str] = None
    notes: Optional[str] = ""
    inspiration_photos: List[SamplePhoto] = Field(default_factory=list)
    upper_spec: UpperSpec = Field(default_factory=UpperSpec)
    insole_spec: InsoleSpec = Field(default_factory=InsoleSpec)
    sole_spec: SoleSpec = Field(default_factory=SoleSpec)

    @field_validator("sample_name")
    @classmethod
    def _validate_name(cls, v):
        if not v or not v.strip():
            raise PydanticCustomError("sample_name_empty", "Sample name cannot be empty")
        return v.strip()


class SampleUpdateIn(BaseModel):
    sample_name: Optional[str] = None
    profile: Optional[Literal["flat", "heeled"]] = None
    category: Optional[str] = None
    season: Optional[str] = None
    target_gender: Optional[str] = None
    target_cost: Optional[float] = None
    target_date: Optional[str] = None
    assigned_karigar_id: Optional[str] = None
    assigned_karigar_name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[SampleStatus] = None
    rejection_reason: Optional[str] = None
    inspiration_photos: Optional[List[SamplePhoto]] = None
    upper_spec: Optional[UpperSpec] = None
    insole_spec: Optional[InsoleSpec] = None
    sole_spec: Optional[SoleSpec] = None


class TransferToStyleIn(BaseModel):
    style_code: str
    name: Optional[str] = None
    category: Optional[str] = "Footwear"
    base_size: Optional[str] = "7"
    margin_pct: Optional[float] = 25.0
    gst_pct: Optional[float] = 5.0
    material_yields: Optional[Dict[str, float]] = Field(default_factory=dict)
    labor_rates: Optional[Dict[str, float]] = Field(default_factory=dict)
    use_sample_photo_as_primary: bool = True

    @field_validator("style_code")
    @classmethod
    def _validate_style_code(cls, v):
        if not v or not v.strip():
            raise PydanticCustomError("style_code_empty", "Official ERP Style Code cannot be empty")
        return v.strip().upper()
