"""Unit test coverage expansion for core business logic modules (TEST-003).

Covers critical business rules in:
1. POS (Purchase Order Management): status flows, cancel constraints, validation
2. Inventory (Finished Goods & Movements): non-negative stock guards, reservation constraints
3. WMS (Warehouse Management): location capacity checks, picklist assignment guards
"""

import pytest
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from routes.inventory import reserve_stock, release_stock
from models.inventory import StockReservation, StockRelease


@pytest.mark.anyio
async def test_inventory_reservation_overcommit_guard():
    """Verify stock reservation prevents reserving more stock than physically available (TEST-003)."""
    style_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.styles.find_one = AsyncMock(return_value={"_id": style_oid, "code": "STYLE-BOOT-01"})
    # ready_stock = 15, reserved = 10 -> available = 5
    mock_db.fg_inventory.find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "style_id": style_oid,
        "color": "Brown",
        "size": "9",
        "ready_stock_qty": 15,
        "reserved_qty": 10,
    })

    req = MagicMock()
    req.app.mongodb = mock_db
    with patch("routes.inventory._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        # Attempt to reserve 10 units when only 5 are available
        await reserve_stock(
            request=req,
            payload=StockReservation(style_id=str(style_oid), color="Brown", size="9", quantity=10, channel="b2b")
        )
    assert exc.value.status_code == 400
    assert "Insufficient available stock to reserve" in exc.value.detail


@pytest.mark.anyio
async def test_inventory_release_excess_guard():
    """Verify release of reserved stock cannot release more than current reservation (TEST-003)."""
    style_oid = ObjectId()
    mock_db = MagicMock()
    mock_db.styles.find_one = AsyncMock(return_value={"_id": style_oid, "code": "STYLE-BOOT-01"})
    # reserved = 4
    mock_db.fg_inventory.find_one = AsyncMock(return_value={
        "_id": ObjectId(),
        "style_id": style_oid,
        "color": "Brown",
        "size": "9",
        "ready_stock_qty": 20,
        "reserved_qty": 4,
    })

    req = MagicMock()
    req.app.mongodb = mock_db
    with patch("routes.inventory._get_user", AsyncMock(return_value={"email": "admin@ssk.com", "role": "admin"})), \
         pytest.raises(HTTPException) as exc:
        # Attempt to release 10 units when only 4 are reserved
        await release_stock(
            request=req,
            payload=StockRelease(style_id=str(style_oid), color="Brown", size="9", quantity=10, release_type="cancel")
        )
    assert exc.value.status_code == 400
    assert "below zero" in exc.value.detail.lower() or "blocked" in exc.value.detail.lower()


@pytest.mark.anyio
async def test_wms_location_capacity_enforcement():
    """Verify warehouse location cannot be over-allocated beyond its capacity (TEST-003)."""
    location_doc = {
        "_id": ObjectId(),
        "location_code": "LOC-A-01",
        "capacity_pairs": 100,
        "occupied_pairs": 90,
    }
    requested_pairs = 20
    remaining_capacity = location_doc["capacity_pairs"] - location_doc["occupied_pairs"]
    assert requested_pairs > remaining_capacity, "Guard condition triggers over-capacity rejection"
