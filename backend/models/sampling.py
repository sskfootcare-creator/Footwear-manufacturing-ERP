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
    display_url: Optional[str] = None
    file_id: Optional[str] = None
    storage: Optional[str] = "imagekit"
    caption: Optional[str] = ""
    is_primary: bool = False
    uploaded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: str = "sample_inspiration"


class PatternPiece(BaseModel):
    piece_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    piece_name: str = "Upper Vamp"
    component: Optional[str] = "upper"  # upper, lining, trim, counter, insole_covering
    component_type: Optional[str] = "vamp"  # vamp, quarter, strap, counter, tongue, collar, lace, custom
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    material_code: Optional[str] = None
    placement: Optional[str] = None  # Tech pack placement: Primary, Secondary, Trim, Accent, Strap, Lining, etc.
    area_sqcm: float = 0.0
    length_mm: float = 0.0
    width_mm: float = 0.0
    oriented_length_mm: Optional[float] = None
    oriented_width_mm: Optional[float] = None
    perimeter_mm: Optional[float] = None
    aspect_ratio: Optional[float] = None
    pieces_per_pair: int = 2
    cutting_direction: Optional[str] = "inherit"  # inherit, length_up (warp), width_up (weft), both
    measurement_unit: Optional[str] = "mm"  # mm, cm, inch
    svg_polygon: Optional[str] = ""
    local_svg_polygon: Optional[str] = ""
    points_mm: Optional[List[List[float]]] = None
    local_points_mm: Optional[List[List[float]]] = None
    bbox_page: Optional[Dict[str, Any]] = None


class StandardStripItem(BaseModel):
    """Standard linear folded strap / lace / unfolded strip component."""
    strip_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Folded Lace 8mm"
    strip_type: Optional[Literal["folded", "unfolded"]] = "folded"
    cut_orientation: Optional[Literal["along_length", "across_width"]] = "along_length"
    strip_width_mm: Optional[float] = None     # User-defined width for unfolded strip (e.g. 10mm, 15mm, 25.4mm)
    strip_width_label: Optional[str] = None
    folded_width_mm: float = 8.0               # 4mm, 8mm, 10mm, 0.5" (12.7mm), etc.
    folded_width_label: Optional[str] = "8mm"  # display label
    cut_width_mm: float = 16.0                 # Formula: 2 * folded_width_mm (or strip_width_mm for unfolded)
    length_mm: float = 650.0                   # Length per piece in mm (defaults to material width if cut in width)
    pieces_per_pair: int = 2                   # Left + Right = 2
    component: str = "upper"                   # upper, trim, binding
    cutting_direction: Optional[str] = "length_up"  # length_up (warp/machine direction)
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    material_code: Optional[str] = None
    material_rate: Optional[float] = None
    material_form: Optional[str] = "roll"
    material_width: Optional[float] = 50.0
    material_width_unit: Optional[str] = "inch"
    material_width_mm: Optional[float] = 1270.0
    material_length: Optional[float] = 1.0
    material_length_unit: Optional[str] = "meter"
    material_length_meters: Optional[float] = 1.0
    lanes_across_roll: Optional[int] = 0
    total_lace_meters_per_roll_meter: Optional[float] = 0.0
    laces_yield_per_meter: Optional[float] = 0.0  # Laces yielded from 1 meter of roll
    pairs_per_meter: Optional[float] = 0.0        # Pairs yielded from 1 meter of roll
    total_laces_full_roll: Optional[float] = 0.0
    total_pairs_full_roll: Optional[float] = 0.0
    consumption_per_pair: float = 0.0
    yield_per_unit: float = 0.0
    net_area_sqcm: float = 0.0
    cost_per_pair: Optional[float] = 0.0
    formula_note: Optional[str] = ""


class StandardPresetComponent(BaseModel):
    """Preset component with fixed standard factory yield (not recalculated from scan, e.g. die-cut insole/bottom)."""
    component_key: str
    name: str
    material_type: str = "sheet"
    is_standard_preset: bool = True
    consumption_per_pair: float = 0.0
    consumption_unit: str = "sheet"
    yield_per_unit: float = 0.0
    yield_unit_label: str = "pairs / sheet"
    waste_pct: float = 0.0
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    notes: Optional[str] = ""


class SampleYieldCalculation(BaseModel):
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    material_type: Literal["roll", "sheet"] = "roll"
    roll_width_inches: Optional[float] = 54.0
    custom_roll_width_mm: Optional[float] = None
    roll_length_meters: Optional[float] = 1.0
    total_pairs_per_roll: Optional[float] = None
    sheet_length_mm: Optional[float] = None
    sheet_width_mm: Optional[float] = None
    selvage_margin_mm: float = 20.0
    kerf_spacing_mm: float = 3.0
    waste_allowance_pct: float = 5.0
    cutting_direction: str = "length_up"  # length_up (warp - no stretch), width_up (weft), both
    measurement_unit: str = "mm"  # mm, cm, inch
    expected_pieces_count: Optional[int] = None
    consumption_per_pair: float = 0.0
    consumption_unit: str = "meter"
    yield_per_unit: float = 0.0
    yield_unit_label: str = "pairs / meter"
    utilization_pct: float = 0.0
    waste_pct: float = 0.0
    net_area_sqcm_per_pair: float = 0.0
    gross_area_sqcm_per_pair: float = 0.0
    pieces_analysis: Optional[List[Dict[str, Any]]] = None
    standard_strips: List[StandardStripItem] = Field(default_factory=list)
    standard_presets: List[Dict[str, Any]] = Field(default_factory=list)
    component_breakdown: Optional[Dict[str, Any]] = None
    material_breakdown: Optional[List[Dict[str, Any]]] = None
    visual_nesting_preview: Optional[Dict[str, Any]] = None
    calculated_at: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CalculateYieldIn(BaseModel):
    material_type: Literal["roll", "sheet"] = "roll"
    material_id: Optional[str] = None
    material_name: Optional[str] = None
    roll_width_inches: Optional[float] = 54.0
    custom_roll_width_mm: Optional[float] = None
    roll_length_meters: Optional[float] = 1.0
    sheet_length_mm: Optional[float] = None
    sheet_width_mm: Optional[float] = None
    selvage_margin_mm: Optional[float] = 20.0
    kerf_spacing_mm: Optional[float] = 3.0
    waste_allowance_pct: Optional[float] = 5.0
    cutting_direction: Optional[Literal["length_up", "width_up", "both"]] = "length_up"
    measurement_unit: Optional[str] = "mm"
    expected_pieces_count: Optional[int] = None
    pieces: Optional[List[PatternPiece]] = None
    standard_strips: Optional[List[StandardStripItem]] = None
    standard_presets: Optional[List[Dict[str, Any]]] = None
    upper_spec: Optional[Dict[str, Any]] = None
    canvas_backing: Optional[str] = None
    lining_material_id: Optional[str] = None
    lining_material_name: Optional[str] = None
    lining_material_code: Optional[str] = None


class ImportPatternIn(BaseModel):
    pattern_code: Optional[str] = None
    pattern_id: Optional[str] = None


class SaveToLibraryIn(BaseModel):
    pattern_name: str
    pattern_code: Optional[str] = None
    category: Optional[str] = "Upper Pattern"


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
    pattern_pieces: List[PatternPiece] = Field(default_factory=list)
    standard_strips: List[StandardStripItem] = Field(default_factory=list)
    linked_pattern_code: Optional[str] = None
    yield_spec: Optional[SampleYieldCalculation] = None
    pattern_scan_url: Optional[str] = None
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
    pattern_pieces: Optional[List[PatternPiece]] = None
    standard_strips: Optional[List[StandardStripItem]] = None
    linked_pattern_code: Optional[str] = None
    yield_spec: Optional[SampleYieldCalculation] = None
    pattern_scan_url: Optional[str] = None
    upper_spec: Optional[UpperSpec] = None
    insole_spec: Optional[InsoleSpec] = None
    sole_spec: Optional[SoleSpec] = None


class TransferToStyleIn(BaseModel):
    style_code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = "Footwear"
    base_size: Optional[str] = "7"
    margin_pct: Optional[float] = 25.0
    gst_pct: Optional[float] = 5.0
    material_yields: Optional[Dict[str, float]] = Field(default_factory=dict)
    labor_rates: Optional[Dict[str, float]] = Field(default_factory=dict)
    use_sample_photo_as_primary: bool = True
    actual_photo_url: Optional[str] = None
    actual_photo: Optional[Dict[str, Any]] = None

    @field_validator("style_code")
    @classmethod
    def _validate_style_code(cls, v):
        if v is None:
            return None
        return str(v).strip().upper() or None
