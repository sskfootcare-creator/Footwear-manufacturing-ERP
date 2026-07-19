"""Finished Goods Inventory & Movements Pydantic Models."""

from typing import Optional, Literal
from pydantic import BaseModel

MovementType = Literal[
    "production_in", "reserved", "unreserved", "dispatched",
    "return_in", "return_restocked", "return_damaged",
    "liquidation_out", "adjustment"
]

ReferenceType = Literal["job", "online_order", "return", "manual"]

AdjustmentField = Literal[
    "ready_stock_qty", "reserved_qty", "in_transit_qty",
    "return_qty", "damaged_qty", "liquidation_qty"
]


class SizeMatrixCell(BaseModel):
    qty:      int = 0
    reserved: int = 0


class FgInventoryIn(BaseModel):
    style_id: str
    color: str
    size: str
    ready_stock_qty: Optional[int] = 0
    reserved_qty: Optional[int] = 0
    in_transit_qty: Optional[int] = 0
    return_qty: Optional[int] = 0
    damaged_qty: Optional[int] = 0
    liquidation_qty: Optional[int] = 0
    min_stock_level: Optional[int] = 25


class FgInventoryUpdate(BaseModel):
    ready_stock_qty: Optional[int] = None
    reserved_qty: Optional[int] = None
    in_transit_qty: Optional[int] = None
    return_qty: Optional[int] = None
    damaged_qty: Optional[int] = None
    liquidation_qty: Optional[int] = None
    min_stock_level: Optional[int] = None


class StockReservation(BaseModel):
    style_id: str
    color: str
    size: str
    quantity: int


class StockRelease(BaseModel):
    style_id: str
    color: str
    size: str
    quantity: int
    release_type: Literal["ship", "cancel"]


class FgStockMovementIn(BaseModel):
    style_id: str
    color: str
    size: str
    movement_type: MovementType
    quantity: int
    reference_type: ReferenceType = "manual"
    reference_id: Optional[str] = ""
    notes: Optional[str] = ""
    adjustment_field: Optional[AdjustmentField] = None
    online_order_id: Optional[str] = None


class InventoryReservationIn(BaseModel):
    style_id: str
    color: str
    size: str
    qty: int
    online_order_id: str
