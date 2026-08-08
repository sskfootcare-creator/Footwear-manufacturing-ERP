"""PLM (Product Lifecycle Management) & Digital Style Folder Models."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_PLM_FOLDERS = [
    {"code": "01", "name": "01 Reference Images", "description": "Inspiration, moodboards & reference photos"},
    {"code": "02", "name": "02 Tech Pack", "description": "Specification sheets, tech packs & spec drawings"},
    {"code": "03", "name": "03 Upper Patterns", "description": "Upper shell, vamp, quarter & tongue pattern CAD/2D files"},
    {"code": "04", "name": "04 Lining Patterns", "description": "Lining & padding patterns"},
    {"code": "05", "name": "05 Insole Patterns", "description": "Insole board, sockliner & arch cushion patterns"},
    {"code": "06", "name": "06 Bottom Patterns", "description": "Outsole, welt, midsole & heel patterns"},
    {"code": "07", "name": "07 Sole Drawings", "description": "2D/3D sole engineering drawings & cross sections"},
    {"code": "08", "name": "08 Sole Mould", "description": "Mould specifications, cavity drawings & maintenance logs"},
    {"code": "09", "name": "09 Last Details", "description": "Last profile, toe shape, spring & measurements"},
    {"code": "10", "name": "10 Cutting Dies", "description": "Clicking die / metal die specifications & nested markers"},
    {"code": "11", "name": "11 Embossing Dies", "description": "Branding, logo & texture embossing plates"},
    {"code": "12", "name": "12 Printing Screens", "description": "Silk screen & transfer printing artworks"},
    {"code": "13", "name": "13 CAD Files", "description": "Raw DXF, DWG, Shoemaster & Gerber CAD files"},
    {"code": "14", "name": "14 BOM", "description": "Bill of Materials snapshots & revisions"},
    {"code": "15", "name": "15 Cost Sheet", "description": "Pre-costing & final production cost breakdowns"},
    {"code": "16", "name": "16 Sample Images", "description": "Prototypes, trial sample photos & approval shots"},
    {"code": "17", "name": "17 Customer Artwork", "description": "Client logos, custom labels & buyer tech specs"},
    {"code": "18", "name": "18 Packaging Artwork", "description": "Inner box, tissue paper, hangtag & master carton artwork"},
    {"code": "19", "name": "19 QC Documents", "description": "Lab test reports, flexing tests & inspection certificates"},
    {"code": "20", "name": "20 Production Notes", "description": "Factory guidelines, stitch counts & lasting notes"},
    {"code": "21", "name": "21 Vendor Documents", "description": "Material datasheets & supplier compliance certificates"},
    {"code": "22", "name": "22 Compliance Documents", "description": "REACH, RoHS, SATRA & safety test certificates"},
    {"code": "23", "name": "23 Revision History", "description": "ECO / ECN engineering change orders & version history"},
]

PATTERN_CATEGORIES = [
    "Upper Pattern",
    "Lining Pattern",
    "Insole Pattern",
    "Bottom Pattern",
    "Sock Pattern",
    "Toe Puff Pattern",
    "Counter Pattern",
    "Reinforcement Pattern",
    "Size Grading Sheet",
    "Pattern Nesting",
    "Pattern Marker",
]

TOOLING_CATEGORIES = [
    "Sole Mould",
    "Heel Mould",
    "Last",
    "Upper Die",
    "Insole Die",
    "Bottom Die",
    "Metal Cutting Die",
    "Embossing Plate",
    "Laser Tool",
    "Punch Tool",
    "Screen Printing Plate",
]


class ScanningMetadata(BaseModel):
    dpi: int = 300
    auto_crop: bool = True
    deskew: bool = True
    background_cleaned: bool = True
    ocr_ready: bool = True
    format: str = "pdf"


class DocumentVersion(BaseModel):
    version: int = 1
    file_name: str
    file_type: str = "application/pdf"
    file_size: int = 0
    url: str
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    imagekit_file_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    checksum: Optional[str] = None
    uploaded_by: str = "System"
    uploaded_at: str = Field(default_factory=now_iso)
    remarks: Optional[str] = ""


class PLMDocumentIn(BaseModel):
    style_id: str
    style_code: str
    folder_code: str
    folder_name: str
    document_name: str
    document_type: str = "other"
    pattern_category: Optional[str] = None
    file_name: str
    file_type: str = "application/pdf"
    file_size: int = 0
    url: str
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    imagekit_file_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    checksum: Optional[str] = None
    scanning_metadata: Optional[ScanningMetadata] = Field(default_factory=ScanningMetadata)
    tags: List[str] = []
    remarks: Optional[str] = ""


class PLMPatternIn(BaseModel):
    style_id: str
    style_code: str
    pattern_name: str
    category: str
    linked_die_code: Optional[str] = None
    linked_punch_tool: Optional[str] = None
    linked_embossing_tool: Optional[str] = None
    document_id: Optional[str] = None
    grading_sizes: List[str] = []
    nesting_yield_pct: Optional[float] = None
    remarks: Optional[str] = ""


class MaintenanceLog(BaseModel):
    date: str = Field(default_factory=now_iso)
    technician: str = "Maintenance Tech"
    notes: str
    cost: float = 0.0


class PLMToolingIn(BaseModel):
    tool_code: str
    tool_name: str
    tool_category: str
    vendor: Optional[str] = "Internal / Supplier"
    material_code: Optional[str] = None
    drawing_url: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    life_cycle_status: str = "Active"
    max_usage: int = 100000
    current_usage: int = 0
    storage_location: str = "RACK-A-01"
    compatible_styles: List[str] = []
    compatible_sizes: List[str] = []
    compatible_colors: List[str] = []
    linked_patterns: List[str] = []
    remarks: Optional[str] = ""
