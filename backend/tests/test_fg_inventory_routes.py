"""Unit tests for Finished Goods Inventory, Movements & Negative-Stock Guard."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
import re
from routes.inventory import (
    inventory_router,
    _apply_movement,
    _seed_fg_inventory_for_lifecycle,
    _get_or_create_fg_row,
    _resolve_style_by_code,
    _clean_color_str,
    _validate_and_clean_size,
    _resolve_canonical_color,
)
from models.inventory import FgStockMovementIn


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def skip(self, count):
        return self

    async def to_list(self, limit=10000):
        return self.docs[:limit]


class MockFgDB:
    def __init__(self):
        self.fg_inventory_store = {}
        self.fg_movements_store = {}
        self.reservations_store = {}
        self.styles_store = {}
        self.color_master_store = []
        self.style_lifecycle_store = {}
        self.audit_logs_store = []

        self.fg_inventory = MagicMock()
        self.fg_inventory.find = MagicMock(side_effect=self._find_inventory)
        self.fg_inventory.find_one = AsyncMock(side_effect=self._find_one_inventory)
        self.fg_inventory.insert_one = AsyncMock(side_effect=self._insert_inventory)
        self.fg_inventory.update_one = AsyncMock(side_effect=self._update_inventory)
        self.fg_inventory.delete_one = AsyncMock(side_effect=self._delete_inventory)
        self.fg_inventory.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        self.fg_inventory.update_many = AsyncMock(return_value=MagicMock(modified_count=0))

        self.fg_stock_movements = MagicMock()
        self.fg_stock_movements.find = MagicMock(side_effect=self._find_movements)
        self.fg_stock_movements.find_one = AsyncMock(side_effect=self._find_one_movement)
        self.fg_stock_movements.insert_one = AsyncMock(side_effect=self._insert_movement)

        self.inventory_reservations = MagicMock()
        self.inventory_reservations.find = MagicMock(side_effect=self._find_reservations)
        self.inventory_reservations.insert_one = AsyncMock(side_effect=self._insert_reservation)
        self.inventory_reservations.update_many = AsyncMock(side_effect=self._update_reservations)

        self.styles = MagicMock()
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        self.color_master = MagicMock()
        self.color_master.find = MagicMock(side_effect=lambda *args, **kwargs: MockCursor(self.color_master_store))

        self.style_lifecycle = MagicMock()
        self.style_lifecycle.find_one = AsyncMock(side_effect=lambda q, *a, **k: self.style_lifecycle_store.get(str(q.get("style_id"))))

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    def _find_inventory(self, q=None, *args, **kwargs):
        docs = list(self.fg_inventory_store.values())
        if q:
            if "style_id" in q:
                docs = [d for d in docs if str(d.get("style_id")) == str(q["style_id"])]
            if "color" in q:
                cq = q["color"]
                if isinstance(cq, dict) and "$regex" in cq:
                    flags = re.IGNORECASE if "i" in cq.get("$options", "") else 0
                    docs = [d for d in docs if re.search(cq["$regex"], d.get("color", ""), flags)]
                else:
                    docs = [d for d in docs if d.get("color") == cq]
            if "size" in q:
                docs = [d for d in docs if d.get("size") == q["size"]]
        return MockCursor(docs)

    async def _find_one_inventory(self, q):
        if "_id" in q:
            return self.fg_inventory_store.get(str(q["_id"]))
        if "style_id" in q and "color" in q and "size" in q:
            cq = q["color"]
            for doc in self.fg_inventory_store.values():
                if str(doc.get("style_id")) != str(q["style_id"]):
                    continue
                if doc.get("size") != q["size"]:
                    continue
                doc_color = doc.get("color", "")
                if isinstance(cq, dict) and "$regex" in cq:
                    flags = re.IGNORECASE if "i" in cq.get("$options", "") else 0
                    if re.search(cq["$regex"], doc_color, flags):
                        return doc
                elif doc_color == cq:
                    return doc
        return None

    async def _insert_inventory(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.fg_inventory_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_inventory(self, match_filter, update):
        oid_str = str(match_filter.get("_id"))
        doc = self.fg_inventory_store.get(oid_str)
        if not doc:
            return MagicMock(matched_count=0, modified_count=0)

        # Check concurrency guard: match on fields in match_filter
        for field, expected_val in match_filter.items():
            if field != "_id":
                if doc.get(field, 0) != expected_val:
                    return MagicMock(matched_count=0, modified_count=0)

        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        if "$set" in update:
            doc.update(update["$set"])
        return MagicMock(matched_count=1, modified_count=1)

    async def _delete_inventory(self, query):
        oid_str = str(query.get("_id"))
        self.fg_inventory_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_movements(self, q=None):
        return MockCursor(list(self.fg_movements_store.values()))

    async def _find_one_movement(self, q):
        if "_id" in q:
            return self.fg_movements_store.get(str(q["_id"]))
        return None

    async def _insert_movement(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.fg_movements_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    def _find_reservations(self, q=None):
        docs = list(self.reservations_store.values())
        if q and "style_id" in q:
            docs = [d for d in docs if str(d.get("style_id")) == str(q["style_id"])]
        return MockCursor(docs)

    async def _insert_reservation(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.reservations_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_reservations(self, q, update):
        count = 0
        for doc in self.reservations_store.values():
            match = True
            for k, v in q.items():
                if str(doc.get(k)) != str(v):
                    match = False
                    break
            if match and "$set" in update:
                doc.update(update["$set"])
                count += 1
        return MagicMock(modified_count=count)

    async def _find_one_style(self, q):
        if "_id" in q:
            return self.styles_store.get(str(q["_id"]))
        if "code" in q:
            for s in self.styles_store.values():
                if s.get("code") == q["code"]:
                    return s
        return None


@pytest.fixture
def mock_fg_env(monkeypatch):
    mock_db = MockFgDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_fg_env):
    test_app = FastAPI()
    test_app.include_router(inventory_router)
    test_app.mongodb = mock_fg_env
    return TestClient(test_app)


def test_fg_inventory_crud_and_patch_restrictions(client, mock_fg_env):
    # Seed style
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "SSK-33-1065",
        "name": "Classic Loafer",
    }

    # 1. Create FG inventory record
    res = client.post("/api/fg-inventory", json={
        "style_id": sid,
        "color": "Tan",
        "size": "40",
        "ready_stock_qty": 0,
        "min_stock_level": 30,
    })
    assert res.status_code == 200, res.text
    item = res.json()
    item_id = item["id"]
    assert item["style_code"] == "SSK-33-1065"
    assert item["is_low_stock"] is True

    # 2. Get item
    res = client.get(f"/api/fg-inventory/{item_id}")
    assert res.status_code == 200
    assert res.json()["color"] == "Tan"

    # 3. Patch item - updating min_stock_level should succeed
    res = client.patch(f"/api/fg-inventory/{item_id}", json={
        "min_stock_level": 50,
    })
    assert res.status_code == 200
    assert res.json()["min_stock_level"] == 50

    # 4. Patch item - direct edit to ready_stock_qty MUST BE REJECTED with 400
    res = client.patch(f"/api/fg-inventory/{item_id}", json={
        "ready_stock_qty": 100,
    })
    assert res.status_code == 400
    assert "Direct edits to" in res.json()["detail"]


def test_negative_stock_guard_near_zero(client, mock_fg_env):
    """Specifically test stock deductions near zero balance to confirm the
    negative-stock guard blocks illegal deductions.
    """
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "SSK-SPORT-02",
        "name": "Sport Sneaker",
    }

    # 1. Production In 5 pairs
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "movement_type": "production_in",
        "quantity": 5,
        "notes": "Lot 1"
    })
    assert res.status_code == 200, res.text
    inv = res.json()["inventory"]
    assert inv["ready_stock_qty"] == 5
    assert inv["available_qty"] == 5

    # 2. Reserve 3 pairs
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "movement_type": "reserved",
        "quantity": 3,
        "online_order_id": "ORD-501"
    })
    assert res.status_code == 200
    inv = res.json()["inventory"]
    assert inv["ready_stock_qty"] == 5
    assert inv["reserved_qty"] == 3
    assert inv["available_qty"] == 2

    # 3. Try to dispatch 4 pairs (must fail because reserved_qty is only 3, 3 - 4 = -1)
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "movement_type": "dispatched",
        "quantity": 4,
        "online_order_id": "ORD-501"
    })
    assert res.status_code == 400
    assert "Movement would push reserved_qty below zero" in res.json()["detail"]

    # 4. Dispatch exactly 3 pairs (succeeds -> ready=2, reserved=0)
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "movement_type": "dispatched",
        "quantity": 3,
        "online_order_id": "ORD-501"
    })
    assert res.status_code == 200
    inv = res.json()["inventory"]
    assert inv["ready_stock_qty"] == 2
    assert inv["reserved_qty"] == 0

    # 5. Liquidate exactly 2 pairs (ready drops to 0, liquidation=2)
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "movement_type": "liquidation_out",
        "quantity": 2,
    })
    assert res.status_code == 200
    inv = res.json()["inventory"]
    assert inv["ready_stock_qty"] == 0
    assert inv["liquidation_qty"] == 2

    # 6. Negative-stock guard at zero: Try to liquidate 1 more pair from 0 ready_stock
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "movement_type": "liquidation_out",
        "quantity": 1,
    })
    assert res.status_code == 400
    assert "Movement would push ready_stock_qty below zero" in res.json()["detail"]


def test_bulk_size_matrix_and_csv_flow(client, mock_fg_env):
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "33-1065-ME",
        "name": "Metallic Loafer",
    }

    # 1. Put size matrix
    res = client.put("/api/fg-inventory/size-matrix", json={
        "style_id": sid,
        "color": "SILVER",
        "movement_type": "production_in",
        "size_matrix": {
            "36": 10,
            "37": 20,
            "38": 0  # 0 should be skipped
        }
    })
    assert res.status_code == 200, res.text
    matrix_res = res.json()
    assert matrix_res["success"] == 2

    # 2. Query by-style
    res = client.get(f"/api/fg-inventory/by-style/{sid}")
    assert res.status_code == 200
    style_view = res.json()
    assert style_view["style"]["code"] == "33-1065-ME"
    assert "SILVER" in style_view["colors"]

    # 3. CSV template endpoint
    res = client.get("/api/fg-inventory/csv-template")
    assert res.status_code == 200
    assert "style_code,color,size,movement_type" in res.text

    # 4. Import CSV (dry run)
    csv_data = (
        "style_code,color,size,movement_type,quantity\n"
        "33-1065-ME,SILVER,39,production_in,15\n"
        "33-1065-ME,GOLD,39,production_in,25\n"
    )
    files = {"file": ("test.csv", csv_data.encode("utf-8"), "text/csv")}
    res = client.post("/api/fg-inventory/import-csv?dry_run=true", files=files)
    assert res.status_code == 200
    assert res.json()["dry_run"] is True
    assert res.json()["summary"]["valid"] == 2

    # 5. Import CSV (live commit)
    files = {"file": ("test.csv", csv_data.encode("utf-8"), "text/csv")}
    res = client.post("/api/fg-inventory/import-csv", files=files)
    assert res.status_code == 200
    assert res.json()["committed"] is True
    assert res.json()["summary"]["success"] == 2


@pytest.mark.anyio
async def test_seed_fg_inventory_for_lifecycle(mock_fg_env):
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "SSK-BOOT-99",
        "name": "Combat Boot",
    }

    lifecycle_doc = {
        "style_id": sid,
        "style_code": "SSK-BOOT-99",
        "planned_colors": ["Brown", "Black"],
        "planned_sizes": ["40", "41", "42"],
        "planned_min_stock": 35,
    }

    # 1. Seed
    res = await _seed_fg_inventory_for_lifecycle(lifecycle_doc, "admin@sskfootcare.com", db=mock_fg_env)
    assert res["created"] == 6
    assert res["pairs"] == 6
    assert len(mock_fg_env.fg_inventory_store) == 6

    # 2. Re-seed (idempotent: updates min_stock_level without recreating)
    lifecycle_doc["planned_min_stock"] = 40
    res2 = await _seed_fg_inventory_for_lifecycle(lifecycle_doc, "admin@sskfootcare.com", db=mock_fg_env)
    assert res2["created"] == 0
    assert res2["updated"] == 6


def test_delete_fg_inventory_success_and_validations(client, mock_fg_env):
    # Seed style
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "SSK-TEST-DEL",
        "name": "Delete Test Shoe",
    }

    # 1. Create FG inventory record with non-zero ready stock
    res = client.post("/api/fg-inventory", json={
        "style_id": sid,
        "color": "Black",
        "size": "42",
        "ready_stock_qty": 10,
        "min_stock_level": 20,
    })
    assert res.status_code == 200, res.text
    item_id = res.json()["id"]

    # 2. Attempt to delete non-zero record -> should return 400
    res = client.delete(f"/api/fg-inventory/{item_id}")
    assert res.status_code == 400
    assert "Cannot delete inventory record with non-zero stock quantities" in res.json()["detail"]
    assert "POST /fg-inventory/movements" in res.json()["detail"]

    # 3. Attempt to delete non-existent ID -> should return 404
    non_existent = str(ObjectId())
    res = client.delete(f"/api/fg-inventory/{non_existent}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    # 4. Attempt to delete with invalid ID format -> should return 400
    res = client.delete("/api/fg-inventory/invalid-oid-123")
    assert res.status_code == 400

    # 5. Zero out stock fields directly in mock store to simulate zero stock after movements
    mock_fg_env.fg_inventory_store[item_id]["ready_stock_qty"] = 0
    mock_fg_env.fg_inventory_store[item_id]["reserved_qty"] = 0
    mock_fg_env.fg_inventory_store[item_id]["in_transit_qty"] = 0
    mock_fg_env.fg_inventory_store[item_id]["return_qty"] = 0
    mock_fg_env.fg_inventory_store[item_id]["damaged_qty"] = 0
    mock_fg_env.fg_inventory_store[item_id]["liquidation_qty"] = 0

    # 6. Delete zero-stock record -> should succeed with 200
    res = client.delete(f"/api/fg-inventory/{item_id}")
    assert res.status_code == 200
    assert res.json()["message"] == "Inventory record deleted successfully"
    assert res.json()["id"] == item_id

    # 7. Verify document was removed from DB
    assert item_id not in mock_fg_env.fg_inventory_store


def test_clean_color_str_and_validate_size():
    from fastapi import HTTPException

    # _clean_color_str
    assert _clean_color_str("  navy   blue  ") == "navy blue"
    assert _clean_color_str(None) == ""
    assert _clean_color_str("") == ""

    # _validate_and_clean_size valid
    assert _validate_and_clean_size(" 42 ") == "42"
    assert _validate_and_clean_size(42) == "42"
    assert _validate_and_clean_size("9.5") == "9.5"

    # _validate_and_clean_size invalid cases
    with pytest.raises(HTTPException) as exc:
        _validate_and_clean_size(None)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        _validate_and_clean_size("   ")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        _validate_and_clean_size("38,39,40")
    assert exc.value.status_code == 400
    assert "comma-separated" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        _validate_and_clean_size("38;39")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        _validate_and_clean_size("A" * 15)
    assert exc.value.status_code == 400
    assert "too long" in exc.value.detail


@pytest.mark.anyio
async def test_resolve_canonical_color_sources(mock_fg_env):
    s_oid = ObjectId()
    sid = str(s_oid)

    # 1. Existing fg row matching
    mock_fg_env.fg_inventory_store["fg_1"] = {
        "_id": ObjectId(),
        "style_id": s_oid,
        "color": "Tan Brown",
        "size": "42",
    }
    c1 = await _resolve_canonical_color(mock_fg_env, sid, "tan brown")
    assert c1 == "Tan Brown"

    # 2. Planned colors in styles
    s_oid2 = ObjectId()
    sid2 = str(s_oid2)
    mock_fg_env.styles_store[sid2] = {
        "_id": s_oid2,
        "code": "SSK-PLANNED-1",
        "planned_colors": ["Dark Olive", "Navy"],
    }
    c2 = await _resolve_canonical_color(mock_fg_env, sid2, "dark olive")
    assert c2 == "Dark Olive"

    # 3. Color master collection
    mock_fg_env.color_master_store = [
        {"color_name": "Royal Blue", "color_code": "RB-01", "active": True}
    ]
    s_oid3 = ObjectId()
    sid3 = str(s_oid3)
    c3 = await _resolve_canonical_color(mock_fg_env, sid3, "royal blue")
    assert c3 == "Royal Blue"
    c3_code = await _resolve_canonical_color(mock_fg_env, sid3, "RB-01")
    assert c3_code == "Royal Blue"

    # 4. Fuzzy typo correction
    c4 = await _resolve_canonical_color(mock_fg_env, sid2, "Navvy")
    assert c4 == "Navy"

    # 5. Default fallback preserves clean string
    c5 = await _resolve_canonical_color(mock_fg_env, sid3, "  Custom Fuchsia  ")
    assert c5 == "Custom Fuchsia"


def test_movement_rejects_composite_and_empty_size(client, mock_fg_env):
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "SSK-SIZE-TEST",
        "name": "Size Test Shoe",
    }

    # Comma-separated size in movement
    res = client.post("/api/fg-inventory/movements", json={
        "style_id": sid,
        "color": "Black",
        "size": "39,40,41",
        "movement_type": "production_in",
        "quantity": 10,
    })
    assert res.status_code == 400
    assert "comma-separated" in res.json()["detail"]


def test_create_fg_inventory_rejects_case_insensitive_duplicate(client, mock_fg_env):
    s_oid = ObjectId()
    sid = str(s_oid)
    mock_fg_env.styles_store[sid] = {
        "_id": s_oid,
        "code": "SSK-DUP-TEST",
        "name": "Dup Test Shoe",
    }

    # 1. Create first row
    res = client.post("/api/fg-inventory", json={
        "style_id": sid,
        "color": "Cognac",
        "size": "41",
        "ready_stock_qty": 5,
        "min_stock_level": 15,
    })
    assert res.status_code == 200, res.text

    # 2. Attempt to create duplicate with variant case "cognac"
    res2 = client.post("/api/fg-inventory", json={
        "style_id": sid,
        "color": "cognac",
        "size": "41",
        "ready_stock_qty": 2,
        "min_stock_level": 15,
    })
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()


