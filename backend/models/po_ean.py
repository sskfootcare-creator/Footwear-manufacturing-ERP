"""Models for PO-level client EAN / Barcode storage and configurable import."""

from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError
from models.sku_map import SheetLocator, HeaderLocator


class PoEanCodeIn(BaseModel):
    po_id: str
    po_number: str
    style_code: str
    color: str
    size: str
    ean_code: str
    imported_at: Optional[str] = None
    imported_by: Optional[str] = None


class PoEanCodeDoc(BaseModel):
    id: Optional[str] = None
    po_id: str
    po_number: str
    style_code: str
    color: str
    size: str
    ean_code: str
    imported_at: str
    imported_by: Optional[str] = None


class PoEanImportFormatConfigIn(BaseModel):
    name: str
    client_name: Optional[str] = ""
    sheet_locator: SheetLocator = Field(default_factory=lambda: SheetLocator(type="first_sheet"))
    header_locator: HeaderLocator = Field(default_factory=lambda: HeaderLocator(type="fixed_row", row=0))
    skip_rows_after_header: int = 0
    column_map: Dict[str, Optional[str]]
    notes: Optional[str] = ""
    active: bool = True

    @field_validator("column_map")
    @classmethod
    def _validate_column_map(cls, v):
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        # Ensure at least style_code (or external_style), size, and ean_code are defined
        required_fields = ["style_code", "size", "ean_code"]
        for f in required_fields:
            if not v.get(f):
                # allow style_code fallback to external_sku or style_ref
                if f == "style_code" and (v.get("external_sku") or v.get("style_ref") or v.get("sku")):
                    continue
                raise PydanticCustomError(
                    f"column_map_{f}",
                    f"column_map.{f} is required for PO Barcode EAN files"
                )
        return v


class PoEanImportFormatConfigUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    sheet_locator: Optional[SheetLocator] = None
    header_locator: Optional[HeaderLocator] = None
    skip_rows_after_header: Optional[int] = None
    column_map: Optional[Dict[str, Optional[str]]] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class PoEanImportItem(BaseModel):
    style_code: str
    color: str
    size: str
    ean_code: str
    po_number: Optional[str] = None
    raw_row: Optional[dict] = None


class PoEanImportRequest(BaseModel):
    po_id: Optional[str] = None
    po_number: Optional[str] = None
    items: List[PoEanImportItem]
    overwrite_existing: bool = False


class PoEanImportResult(BaseModel):
    ok: bool
    po_id: Optional[str] = None
    po_number: Optional[str] = None
    total_rows: int = 0
    imported: int = 0
    skipped_duplicates: int = 0
    unmatched_count: int = 0
    unmatched_rows: List[dict] = Field(default_factory=list)
    conflicts: List[dict] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
