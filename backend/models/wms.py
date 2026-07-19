"""Warehouse Management (WMS) & Packing Pydantic Models."""

from typing import List, Optional, Literal
from pydantic import BaseModel


class PicklistItemIn(BaseModel):
    style_id: Optional[str] = None
    style_code: str
    color: str
    size: str
    qty: int
    location_code: str
    rack: Optional[int] = None
    row: Optional[int] = None
    cell: Optional[int] = None
    picked: bool = False


class PicklistIn(BaseModel):
    order_id: str
    channel: str
    picker: Optional[str] = None
    items: List[PicklistItemIn] = []


class PickItemIn(BaseModel):
    item_index: int
    scanned_location: str


class PicklistPatchIn(BaseModel):
    picker: Optional[str] = None
    status: Optional[Literal["pending", "in_progress", "completed", "cancelled"]] = None


class EanCodeIn(BaseModel):
    style_id: str
    color: str
    size: str
    ean_code: str


class CartonIn(BaseModel):
    job_id: str
    size: str
    qty: int


class EanCodeSimple(BaseModel):
    size: str
    ean_code: str


class CartonRowSimple(BaseModel):
    size: str
    qty: int


class QcPackConfirmIn(BaseModel):
    job_ids: List[str]
    eans: List[EanCodeSimple]
    cartons: List[CartonRowSimple]


class LocationBlockIn(BaseModel):
    blocked: bool
    reason: Optional[str] = None


class ProduceCellIn(BaseModel):
    style_id:      str
    color:         str
    size:          str
    produced_qty:  int
    reason:        Optional[str] = ""
    use_components: bool          = True
    channel_filter: Optional[str] = None
    dispatch_stage: Optional[str] = "dispatched"
    force_negative_stock: bool    = False


class ProductionCardIn(BaseModel):
    style_id:   str
    components: List[dict]
