"""Unit & End-to-End Tests for Warehouse Management System (WMS) Domain."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.wms import (
    wms_router,
    _make_location_code,
    _recompute_status,
    _seed_warehouse_locations,
    _allocate_to_locations,
    _deduct_from_locations,
    _deduct_from_specific_location,
    _generate_picklist_for_order,
    _next_picklist_no,
    _sync_warehouse_locations,
    _find_style_home_cell,
    _pick_new_cell_for_style,
    WAREHOUSE_ROWS,
    RACKS_PER_ROW,
    CELLS_PER_RACK,
    CAPACITY,
)
from models.wms import (
    PicklistItemIn,
    PicklistIn,
    PickItemIn,
    PicklistPatchIn,
    LocationBlockIn,
    ProduceCellIn,
    ProductionCardIn,
)
from models.inventory import FgStockMovementIn


class MockCursor:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
        return self

    async def to_list(self, limit=10000):
        return self.docs[:limit]

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockWmsDB:
    def __init__(self):
        self.warehouse_locations_store = {}
        self.fg_location_inventory_store = {}
        self.picklists_store = {}
        self.styles_store = {}
        self.component_master_store = {}
        self.style_component_mapping_store = {}
        self.production_jobs_store = {}
        self.short_production_log_store = []
        self.audit_logs_store = []
        self.inventory_reservations_store = {}
        self.fg_movements_store = []
        self.pending_list_snapshots_store = {}

    @property
    def warehouse_locations(self):
        m = MagicMock()
        m.find = lambda q=None, proj=None, sort=None: MockCursor(
            [d for d in self.warehouse_locations_store.values() if self._matches_loc(d, q)]
        )
        m.find_one = AsyncMock(side_effect=lambda q, sort=None: self._find_one_loc(q))
        m.update_one = AsyncMock(side_effect=self._update_loc)
        m.update_many = AsyncMock(side_effect=self._update_many_loc)
        m.delete_many = AsyncMock(side_effect=self._delete_many_loc)
        m.count_documents = AsyncMock(side_effect=lambda q: sum(1 for d in self.warehouse_locations_store.values() if self._matches_loc(d, q)))
        return m

    def _matches_loc(self, doc, q):
        if not q:
            return True
        for k, v in q.items():
            if k == "_id":
                if str(doc.get("_id")) != str(v):
                    return False
            elif k == "location_code":
                if isinstance(v, dict) and "$in" in v:
                    if doc.get("location_code") not in v["$in"]:
                        return False
                elif isinstance(v, dict) and "$regex" in v:
                    if v["$regex"].lower() not in doc.get("location_code", "").lower():
                        return False
                elif doc.get("location_code") != v:
                    return False
            elif k == "available_pairs":
                if isinstance(v, dict) and "$gt" in v:
                    if doc.get("available_pairs", 0) <= v["$gt"]:
                        return False
            elif k == "status":
                if isinstance(v, dict) and "$ne" in v:
                    if doc.get("status") == v["$ne"]:
                        return False
                elif doc.get("status") != v:
                    return False
            elif k == "rack":
                if doc.get("rack") != v:
                    return False
            elif k == "zone":
                if doc.get("zone") != v:
                    return False
        return True

    def _find_one_loc(self, q):
        for d in self.warehouse_locations_store.values():
            if self._matches_loc(d, q):
                return dict(d)
        return None

    def _update_loc(self, q, upd, upsert=False):
        doc = self._find_one_loc(q)
        if not doc:
            if upsert:
                code = q.get("location_code")
                new_doc = {"_id": ObjectId(), "location_code": code}
                if "$setOnInsert" in upd:
                    new_doc.update(upd["$setOnInsert"])
                if "$set" in upd:
                    new_doc.update(upd["$set"])
                self.warehouse_locations_store[str(new_doc["_id"])] = new_doc
                res = MagicMock()
                res.upserted_id = new_doc["_id"]
                res.modified_count = 0
                return res
            res = MagicMock()
            res.modified_count = 0
            return res
        
        # Check condition for optimistic locking
        if "available_pairs" in q:
            if doc.get("available_pairs") != q["available_pairs"]:
                res = MagicMock()
                res.modified_count = 0
                return res

        if "$set" in upd:
            self.warehouse_locations_store[str(doc["_id"])].update(upd["$set"])
        res = MagicMock()
        res.modified_count = 1
        res.upserted_id = None
        return res

    def _update_many_loc(self, q, upd):
        count = 0
        for doc in list(self.warehouse_locations_store.values()):
            if self._matches_loc(doc, q):
                if isinstance(upd, list):
                    for step in upd:
                        if "$set" in step:
                            doc.update(step["$set"])
                elif "$set" in upd:
                    doc.update(upd["$set"])
                count += 1
        res = MagicMock()
        res.modified_count = count
        return res

    def _delete_many_loc(self, q):
        count = len(self.warehouse_locations_store)
        self.warehouse_locations_store.clear()
        res = MagicMock()
        res.deleted_count = count
        return res

    @property
    def fg_location_inventory(self):
        m = MagicMock()
        m.find = lambda q=None, proj=None, sort=None: MockCursor(
            [d for d in self.fg_location_inventory_store.values() if self._matches_fg_loc(d, q)]
        )
        m.find_one = AsyncMock(side_effect=lambda q, sort=None: self._find_one_fg_loc(q))
        m.update_one = AsyncMock(side_effect=self._update_fg_loc)
        m.delete_one = AsyncMock(side_effect=self._delete_fg_loc)
        m.aggregate = lambda p: MockCursor(self._aggregate_fg_loc(p))
        m.distinct = AsyncMock(side_effect=lambda f: list({d.get(f) for d in self.fg_location_inventory_store.values() if d.get(f)}))
        return m

    def _matches_fg_loc(self, doc, q):
        if not q:
            return True
        for k, v in q.items():
            if k == "$or":
                matched_any = False
                for branch in v:
                    if self._matches_fg_loc(doc, branch):
                        matched_any = True
                        break
                if not matched_any:
                    return False
            elif k == "style_id":
                if str(doc.get("style_id")) != str(v):
                    return False
            elif k == "color":
                if isinstance(v, dict) and "$regex" in v:
                    clean = v["$regex"].strip("^$")
                    if clean.lower() != str(doc.get("color", "")).lower():
                        return False
                elif str(doc.get("color")) != str(v):
                    return False
            elif k == "size":
                if isinstance(v, dict) and "$regex" in v:
                    clean = v["$regex"].strip("^$")
                    if clean.lower() != str(doc.get("size", "")).lower():
                        return False
                elif str(doc.get("size")) != str(v):
                    return False
            elif k == "location_code":
                if isinstance(v, dict) and "$in" in v:
                    if doc.get("location_code") not in v["$in"]:
                        return False
                elif doc.get("location_code") != v:
                    return False
            elif k == "qty":
                if isinstance(v, dict) and "$gt" in v:
                    if int(doc.get("qty", 0)) <= v["$gt"]:
                        return False
        return True

    def _find_one_fg_loc(self, q):
        for d in self.fg_location_inventory_store.values():
            if self._matches_fg_loc(d, q):
                return dict(d)
        return None

    def _update_fg_loc(self, q, upd, upsert=False):
        doc = None
        if "_id" in q:
            doc = self.fg_location_inventory_store.get(str(q["_id"]))
        else:
            doc = self._find_one_fg_loc(q)
        
        if not doc:
            if upsert:
                new_doc = {
                    "_id": ObjectId(),
                    "style_id": q.get("style_id"),
                    "color": q.get("color"),
                    "size": q.get("size"),
                    "location_code": q.get("location_code"),
                    "qty": 0,
                    "reserved_qty": 0,
                }
                if "$setOnInsert" in upd:
                    new_doc.update(upd["$setOnInsert"])
                if "$inc" in upd:
                    for ik, iv in upd["$inc"].items():
                        new_doc[ik] = new_doc.get(ik, 0) + iv
                if "$set" in upd:
                    new_doc.update(upd["$set"])
                self.fg_location_inventory_store[str(new_doc["_id"])] = new_doc
                res = MagicMock()
                res.upserted_id = new_doc["_id"]
                res.modified_count = 0
                return res
            res = MagicMock()
            res.modified_count = 0
            return res

        # Guard checks: qty and reserved_qty
        if "qty" in q and isinstance(q["qty"], dict) and "$gte" in q["qty"]:
            if int(doc.get("qty", 0)) < q["qty"]["$gte"]:
                res = MagicMock()
                res.modified_count = 0
                return res
        if "reserved_qty" in q and isinstance(q["reserved_qty"], dict) and "$gte" in q["reserved_qty"]:
            if int(doc.get("reserved_qty", 0)) < q["reserved_qty"]["$gte"]:
                res = MagicMock()
                res.modified_count = 0
                return res
        if "$expr" in q:
            expr = q["$expr"]
            if "$gte" in expr:
                take = expr["$gte"][1]
                free = int(doc.get("qty", 0)) - int(doc.get("reserved_qty", 0) or 0)
                if free < take:
                    res = MagicMock()
                    res.modified_count = 0
                    return res

        target = self.fg_location_inventory_store[str(doc["_id"])]
        if "$inc" in upd:
            for ik, iv in upd["$inc"].items():
                target[ik] = target.get(ik, 0) + iv
        if "$set" in upd:
            target.update(upd["$set"])
        res = MagicMock()
        res.modified_count = 1
        return res

    def _delete_fg_loc(self, q):
        doc = None
        if "_id" in q:
            doc = self.fg_location_inventory_store.pop(str(q["_id"]), None)
        res = MagicMock()
        res.deleted_count = 1 if doc else 0
        return res

    def _aggregate_fg_loc(self, pipeline):
        counts = {}
        for d in self.fg_location_inventory_store.values():
            if d.get("qty", 0) > 0:
                loc = d.get("location_code")
                counts[loc] = counts.get(loc, 0) + d["qty"]
        sorted_locs = sorted(counts.items(), key=lambda x: -x[1])
        return [{"_id": loc, "total": tot} for loc, tot in sorted_locs]

    @property
    def picklists(self):
        m = MagicMock()
        m.find = lambda q=None, proj=None, sort=None: MockCursor(
            [d for d in self.picklists_store.values() if self._matches_pl(d, q)]
        )
        m.find_one = AsyncMock(side_effect=lambda q, sort=None: self._find_one_pl(q))
        m.insert_one = AsyncMock(side_effect=self._insert_pl)
        m.update_one = AsyncMock(side_effect=self._update_pl)
        m.delete_one = AsyncMock(side_effect=self._delete_pl)
        m.count_documents = AsyncMock(side_effect=lambda q: sum(1 for d in self.picklists_store.values() if self._matches_pl(d, q)))
        return m

    def _matches_pl(self, doc, q):
        if not q:
            return True
        for k, v in q.items():
            if k == "_id":
                if str(doc.get("_id")) != str(v):
                    return False
            elif k == "picklist_no":
                if isinstance(v, dict) and "$regex" in v:
                    prefix = v["$regex"].lstrip("^")
                    if not doc.get("picklist_no", "").startswith(prefix):
                        return False
                elif doc.get("picklist_no") != v:
                    return False
            elif k == "status":
                if isinstance(v, dict) and "$in" in v:
                    if doc.get("status") not in v["$in"]:
                        return False
                elif isinstance(v, dict) and "$nin" in v:
                    if doc.get("status") in v["$nin"]:
                        return False
                elif doc.get("status") != v:
                    return False
            elif k == "order_id" and doc.get("order_id") != v:
                return False
            elif k == "channel" and doc.get("channel") != v:
                return False
            elif k == "picker" and doc.get("picker") != v:
                return False
        return True

    def _find_one_pl(self, q):
        for d in self.picklists_store.values():
            if self._matches_pl(d, q):
                return dict(d)
        return None

    def _insert_pl(self, doc):
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.picklists_store[str(doc["_id"])] = doc
        res = MagicMock()
        res.inserted_id = doc["_id"]
        return res

    def _update_pl(self, q, upd):
        doc = self._find_one_pl(q)
        if not doc:
            res = MagicMock()
            res.matched_count = 0
            res.modified_count = 0
            return res
        target = self.picklists_store[str(doc["_id"])]
        if "$set" in upd:
            for sk, sv in upd["$set"].items():
                if sk.startswith("items."):
                    parts = sk.split(".")
                    idx = int(parts[1])
                    field = parts[2]
                    target["items"][idx][field] = sv
                else:
                    target[sk] = sv
        res = MagicMock()
        res.matched_count = 1
        res.modified_count = 1
        return res

    def _delete_pl(self, q):
        doc = self._find_one_pl(q)
        if doc:
            self.picklists_store.pop(str(doc["_id"]), None)
            res = MagicMock()
            res.deleted_count = 1
            return res
        res = MagicMock()
        res.deleted_count = 0
        return res

    @property
    def styles(self):
        m = MagicMock()
        m.find = lambda q=None, proj=None: MockCursor(list(self.styles_store.values()))
        m.find_one = AsyncMock(side_effect=lambda q: self._find_one_generic(self.styles_store, q))
        return m

    @property
    def component_master(self):
        m = MagicMock()
        m.find_one = AsyncMock(side_effect=lambda q: self._find_one_generic(self.component_master_store, q))
        m.update_one = AsyncMock(side_effect=self._update_component_master)
        return m

    def _update_component_master(self, q, upd):
        doc = self._find_one_generic(self.component_master_store, q)
        if doc and "$set" in upd:
            self.component_master_store[str(doc["_id"])].update(upd["$set"])
        res = MagicMock()
        res.modified_count = 1 if doc else 0
        return res

    @property
    def style_component_mapping(self):
        m = MagicMock()
        m.find = lambda q=None: MockCursor([d for d in self.style_component_mapping_store.values() if self._matches_generic(d, q)])
        m.insert_one = AsyncMock(side_effect=self._insert_scm)
        m.update_many = AsyncMock(side_effect=self._update_many_scm)
        return m

    def _insert_scm(self, doc):
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.style_component_mapping_store[str(doc["_id"])] = doc
        res = MagicMock()
        res.inserted_id = doc["_id"]
        return res

    def _update_many_scm(self, q, upd):
        for doc in self.style_component_mapping_store.values():
            if self._matches_generic(doc, q):
                if "$set" in upd:
                    doc.update(upd["$set"])
        res = MagicMock()
        res.modified_count = 1
        return res

    @property
    def production_jobs(self):
        m = MagicMock()
        m.find = lambda q=None, proj=None: MockCursor([d for d in self.production_jobs_store.values() if self._matches_generic(d, q)])
        m.find_one = AsyncMock(side_effect=lambda q: self._find_one_generic(self.production_jobs_store, q))
        m.update_one = AsyncMock(side_effect=self._update_prod_job)
        return m

    def _update_prod_job(self, q, upd):
        doc = self._find_one_generic(self.production_jobs_store, q)
        if doc and "$set" in upd:
            self.production_jobs_store[str(doc["_id"])].update(upd["$set"])
        res = MagicMock()
        res.modified_count = 1 if doc else 0
        return res

    @property
    def short_production_log(self):
        m = MagicMock()
        m.insert_one = AsyncMock(side_effect=lambda d: self.short_production_log_store.append(d))
        m.find = lambda q=None: MockCursor(self.short_production_log_store)
        return m

    @property
    def audit_logs(self):
        m = MagicMock()
        m.insert_one = AsyncMock(side_effect=lambda d: self.audit_logs_store.append(d))
        return m

    @property
    def inventory_reservations(self):
        m = MagicMock()
        m.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
        return m

    @property
    def style_lifecycle(self):
        m = MagicMock()
        m.find_one = AsyncMock(return_value=None)
        return m

    @property
    def pending_list_snapshots(self):
        m = MagicMock()
        m.insert_one = AsyncMock(side_effect=self._insert_snapshot)
        m.find = lambda q=None, proj=None: MockCursor(list(self.pending_list_snapshots_store.values()))
        m.find_one = AsyncMock(side_effect=lambda q: self._find_one_generic(self.pending_list_snapshots_store, q))
        return m

    def _insert_snapshot(self, doc):
        doc = dict(doc)
        doc["_id"] = ObjectId()
        self.pending_list_snapshots_store[str(doc["_id"])] = doc
        res = MagicMock()
        res.inserted_id = doc["_id"]
        return res

    def _matches_generic(self, doc, q):
        if not q:
            return True
        for k, v in q.items():
            if k == "$or":
                matched = any(self._matches_generic(doc, b) for b in v)
                if not matched: return False
            elif k == "_id":
                if str(doc.get("_id")) != str(v): return False
            elif k == "style_id":
                if str(doc.get("style_id")) != str(v): return False
            elif k == "color" and doc.get("color") != v:
                return False
            elif k == "size" and doc.get("size") != v:
                return False
            elif k == "stage":
                if isinstance(v, dict) and "$ne" in v:
                    if doc.get("stage") == v["$ne"]: return False
                elif doc.get("stage") != v: return False
            elif k == "active":
                if isinstance(v, dict) and "$ne" in v:
                    if doc.get("active") == v["$ne"]: return False
                elif doc.get("active") != v: return False
        return True

    def _find_one_generic(self, store, q):
        for d in store.values():
            if self._matches_generic(d, q):
                return dict(d)
        return None


@pytest.fixture
def mock_wms_env(monkeypatch):
    mock_db = MockWmsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "warehouse_mgr@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_wms_env):
    test_app = FastAPI()
    test_app.include_router(wms_router)
    test_app.mongodb = mock_wms_env
    return TestClient(test_app)


# ═══════════════════════════════════════════════════════════════════════
# 1. Location Seeding, Formatting, and Layout Tests
# ═══════════════════════════════════════════════════════════════════════

def test_location_code_formatting():
    assert _make_location_code(1, 1, 1) == "R01-RK1-C01"
    assert _make_location_code(10, 3, 8) == "R10-RK3-C08"


def test_status_recomputation():
    assert _recompute_status(0, 40) == "empty"
    assert _recompute_status(20, 40) == "partial"
    assert _recompute_status(40, 40) == "full"
    assert _recompute_status(50, 40) == "full"


def test_seed_warehouse_locations(mock_wms_env):
    inserted = asyncio.run(_seed_warehouse_locations(db=mock_wms_env))
    expected_cells = WAREHOUSE_ROWS * RACKS_PER_ROW * CELLS_PER_RACK  # 10 * 3 * 8 = 240
    assert inserted == expected_cells
    assert len(mock_wms_env.warehouse_locations_store) == expected_cells

    sample = list(mock_wms_env.warehouse_locations_store.values())[0]
    assert sample["capacity_pairs"] == CAPACITY
    assert sample["available_pairs"] == CAPACITY
    assert sample["occupied_pairs"] == 0
    assert sample["status"] == "empty"
    assert sample["zone"] == "main"


def test_warehouse_locations_api_and_blocking(client, mock_wms_env):
    # Seed locations
    res_seed = client.post("/api/warehouse/seed-locations")
    assert res_seed.status_code == 200, res_seed.text
    assert res_seed.json()["inserted"] == 240

    # List locations
    res_list = client.get("/api/warehouse/locations")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 240

    # Block a cell
    res_block = client.patch(
        "/api/warehouse/locations/R01-RK1-C01/block",
        json={"blocked": True, "reason": "Rack damaged"},
    )
    assert res_block.status_code == 200
    assert res_block.json()["status"] == "blocked"
    assert res_block.json()["block_reason"] == "Rack damaged"

    # Get cell details
    res_get = client.get("/api/warehouse/locations/R01-RK1-C01")
    assert res_get.status_code == 200
    assert res_get.json()["location"]["status"] == "blocked"

    # Unblock the cell
    res_unblock = client.patch(
        "/api/warehouse/locations/R01-RK1-C01/block",
        json={"blocked": False},
    )
    assert res_unblock.status_code == 200
    assert res_unblock.json()["status"] == "empty"
    assert res_unblock.json()["block_reason"] is None


# ═══════════════════════════════════════════════════════════════════════
# 2. Allocation & FIFO Deduction Tests
# ═══════════════════════════════════════════════════════════════════════

def test_allocation_and_fifo_deduction(mock_wms_env):
    asyncio.run(_seed_warehouse_locations(db=mock_wms_env))
    style_id = ObjectId()
    
    # 1. Allocate 60 pairs (should spill across 2 cells: 40 in R01-RK1-C01, 20 in R01-RK1-C02)
    alloc = asyncio.run(_allocate_to_locations(
        style_id=str(style_id),
        style_code="SSK-001",
        color="Tan",
        size="8",
        qty=60,
        user_email="admin@ssk.com",
        db=mock_wms_env,
    ))
    assert alloc["placed_qty"] == 60
    assert alloc["unplaced_qty"] == 0
    assert len(alloc["placements"]) == 2
    assert alloc["placements"][0]["location_code"] == "R01-RK1-C01"
    assert alloc["placements"][0]["qty"] == 40
    assert alloc["placements"][1]["location_code"] == "R01-RK1-C02"
    assert alloc["placements"][1]["qty"] == 20

    # Verify inventory store
    fg_rows = list(mock_wms_env.fg_location_inventory_store.values())
    assert len(fg_rows) == 2
    assert sum(r["qty"] for r in fg_rows) == 60

    # 2. Deduct 50 pairs via FIFO (should clear R01-RK1-C01 (40) and deduct 10 from R01-RK1-C02)
    deduct = asyncio.run(_deduct_from_locations(
        style_id=str(style_id),
        color="Tan",
        size="8",
        qty=50,
        user_email="admin@ssk.com",
        db=mock_wms_env,
    ))
    assert deduct["deducted_qty"] == 50
    assert deduct["shortfall"] == 0
    assert len(deduct["removals"]) == 2
    assert deduct["removals"][0]["location_code"] == "R01-RK1-C01"
    assert deduct["removals"][0]["qty"] == 40
    assert deduct["removals"][1]["location_code"] == "R01-RK1-C02"
    assert deduct["removals"][1]["qty"] == 10

    # Remaining in R01-RK1-C02 should be 10
    remaining_fg = list(mock_wms_env.fg_location_inventory_store.values())
    assert len(remaining_fg) == 1
    assert remaining_fg[0]["qty"] == 10
    assert remaining_fg[0]["location_code"] == "R01-RK1-C02"


# ═══════════════════════════════════════════════════════════════════════
# 3. Online Order Import → Picklist Auto-Generation & Pick Flow End-to-End
# ═══════════════════════════════════════════════════════════════════════

def test_online_order_picklist_generation_and_picking_e2e(client, mock_wms_env):
    asyncio.run(_seed_warehouse_locations(db=mock_wms_env))
    style_id = ObjectId()
    style_oid_str = str(style_id)
    
    mock_wms_env.styles_store[style_oid_str] = {
        "_id": style_id,
        "code": "SSK-M-01",
        "name": "Classic Derby Tan",
    }

    # Stock 15 pairs at R01-RK1-C01
    asyncio.run(_allocate_to_locations(
        style_id=style_oid_str,
        style_code="SSK-M-01",
        color="Tan",
        size="9",
        qty=15,
        user_email="wms@ssk.com",
        db=mock_wms_env,
    ))

    # Auto-generate picklist for an order of 10 pairs
    order_lines = [{
        "style_id": style_oid_str,
        "style_code": "SSK-M-01",
        "color": "Tan",
        "size": "9",
        "quantity": 10,
    }]
    
    picklist_doc, covered, uncovered = asyncio.run(_generate_picklist_for_order(
        order_id="ORD-MYNTRA-9001",
        channel="myntra",
        order_lines=order_lines,
        user_email="system@ssk.com",
        db=mock_wms_env,
    ))

    assert picklist_doc["picklist_no"].startswith("PL-")
    assert picklist_doc["total_qty"] == 10
    assert covered[(style_oid_str, "Tan", "9")] == 10
    assert len(uncovered) == 0

    # Verify reserved_qty was incremented on location record
    loc_record = list(mock_wms_env.fg_location_inventory_store.values())[0]
    assert loc_record["qty"] == 15
    assert loc_record["reserved_qty"] == 10

    pid = str(picklist_doc["_id"])

    # 1. Test scan mismatch error
    res_mismatch = client.post(
        f"/api/picklists/{pid}/pick-item",
        json={"item_index": 0, "scanned_location": "R01-RK1-C99"},
    )
    assert res_mismatch.status_code == 400
    assert "Scan mismatch" in res_mismatch.json()["detail"]

    # 2. Confirm valid scan & pick item
    res_pick = client.post(
        f"/api/picklists/{pid}/pick-item",
        json={"item_index": 0, "scanned_location": "R01-RK1-C01"},
    )
    assert res_pick.status_code == 200, res_pick.text
    updated_pl = res_pick.json()
    assert updated_pl["status"] == "completed"
    assert updated_pl["items"][0]["picked"] is True

    # After picking: physical qty = 15 - 10 = 5, reserved_qty = 10 - 10 = 0
    updated_loc = list(mock_wms_env.fg_location_inventory_store.values())[0]
    assert updated_loc["qty"] == 5
    assert updated_loc["reserved_qty"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 4. Picklist Deletion / Cancellation & Reservation Rollback Test
# ═══════════════════════════════════════════════════════════════════════

def test_picklist_cancellation_rollback(client, mock_wms_env):
    asyncio.run(_seed_warehouse_locations(db=mock_wms_env))
    style_id = ObjectId()
    style_oid_str = str(style_id)

    # Stock 20 pairs
    asyncio.run(_allocate_to_locations(
        style_id=style_oid_str,
        style_code="SSK-002",
        color="Black",
        size="7",
        qty=20,
        user_email="wms@ssk.com",
        db=mock_wms_env,
    ))

    # Generate picklist for 8 pairs
    order_lines = [{"style_id": style_oid_str, "style_code": "SSK-002", "color": "Black", "size": "7", "quantity": 8}]
    pl_doc, _, _ = asyncio.run(_generate_picklist_for_order("ORD-AMZ-101", "amazon", order_lines, "wms@ssk.com", db=mock_wms_env))
    
    loc_record = list(mock_wms_env.fg_location_inventory_store.values())[0]
    assert loc_record["reserved_qty"] == 8

    # Cancel / Delete picklist
    pid = str(pl_doc["_id"])
    res_del = client.delete(f"/api/picklists/{pid}")
    assert res_del.status_code == 200
    assert res_del.json()["ok"] is True

    # Reserved qty must be released back to 0
    loc_record_after = list(mock_wms_env.fg_location_inventory_store.values())[0]
    assert loc_record_after["reserved_qty"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 5. Production Matrix & Produce-Cell Tests
# ═══════════════════════════════════════════════════════════════════════

def test_produce_cell_with_bom_and_shortfall(client, mock_wms_env):
    style_id = ObjectId()
    sid_str = str(style_id)
    comp_id = ObjectId()
    cid_str = str(comp_id)

    mock_wms_env.styles_store[sid_str] = {"_id": style_id, "code": "SSK-BOM-01", "name": "BOM Test Shoe"}
    mock_wms_env.component_master_store[cid_str] = {
        "_id": comp_id,
        "component_code": "SOLE-EVA-01",
        "component_name": "EVA Sole 8mm",
        "current_stock": 100,
        "reserved_stock": 0,
    }
    mock_wms_env.style_component_mapping_store["map1"] = {
        "_id": ObjectId(),
        "style_id": style_id,
        "component_id": comp_id,
        "quantity_per_pair": 1.0,
        "wastage_percent": 0.0,
        "active": True,
    }

    # Add a pending production job of 20 pairs
    job_id = ObjectId()
    mock_wms_env.production_jobs_store[str(job_id)] = {
        "_id": job_id,
        "style_id": style_id,
        "color": "Brown",
        "size": "9",
        "quantity": 20,
        "completed_qty": 0,
        "stage": "assembly",
        "source_type": "online_channel",
        "created_at": "2026-08-20T10:00:00Z",
    }

    # 1. Test Short Production: Produce 12 pairs with reason
    res_short = client.post(
        "/api/production/produce-cell",
        json={
            "style_id": sid_str,
            "color": "Brown",
            "size": "9",
            "produced_qty": 12,
            "reason": "Machine needle breakage",
            "use_components": True,
        },
    )
    assert res_short.status_code == 200, res_short.text
    data = res_short.json()
    assert data["ok"] is True
    assert data["produced"] == 12
    assert data["shortfall"] == 8
    assert len(data["bom_components_used"]) == 1
    assert data["bom_components_used"][0]["deducted"] == 12

    # Check component stock was reduced: 100 - 12 = 88
    comp = mock_wms_env.component_master_store[cid_str]
    assert comp["current_stock"] == 88

    # Check short log recorded
    assert len(mock_wms_env.short_production_log_store) == 1
    assert mock_wms_env.short_production_log_store[0]["reason"] == "Machine needle breakage"
    assert mock_wms_env.short_production_log_store[0]["shortfall"] == 8

    # 2. Test Over Production: Produce remaining 8 + 5 excess pairs = 13 pairs
    res_over = client.post(
        "/api/production/produce-cell",
        json={
            "style_id": sid_str,
            "color": "Brown",
            "size": "9",
            "produced_qty": 13,
            "use_components": True,
        },
    )
    assert res_over.status_code == 200, res_over.text
    data_over = res_over.json()
    assert data_over["excess"] == 5
    assert data_over["excess_placed_at"] is not None

    # Check component stock: 88 - 13 = 75
    assert mock_wms_env.component_master_store[cid_str]["current_stock"] == 75


def test_bom_feasibility_and_production_card_api(client, mock_wms_env):
    style_id = ObjectId()
    sid_str = str(style_id)
    comp_id = ObjectId()
    cid_str = str(comp_id)

    mock_wms_env.styles_store[sid_str] = {"_id": style_id, "code": "SSK-FEAS-01"}
    mock_wms_env.component_master_store[cid_str] = {
        "_id": comp_id,
        "component_code": "UPPER-LEA-01",
        "component_name": "Leather Upper",
        "current_stock": 50,
    }

    # Create Production Card BOM
    res_card = client.post(
        "/api/production/production-card",
        json={
            "style_id": sid_str,
            "components": [{"component_id": cid_str, "quantity_per_pair": 2.0, "wastage_percent": 0.0}],
        },
    )
    assert res_card.status_code == 200, res_card.text
    assert res_card.json()["count"] == 1

    # Check feasibility for 20 pairs (needs 40 uppers, available 50 -> FEASIBLE)
    res_feas_ok = client.get(f"/api/production/bom-feasibility/{sid_str}?pairs=20")
    assert res_feas_ok.status_code == 200
    assert res_feas_ok.json()["feasible"] is True

    # Check feasibility for 30 pairs (needs 60 uppers, available 50 -> NOT FEASIBLE)
    res_feas_short = client.get(f"/api/production/bom-feasibility/{sid_str}?pairs=30")
    assert res_feas_short.status_code == 200
    assert res_feas_short.json()["feasible"] is False
    assert res_feas_short.json()["components"][0]["shortfall"] == 10


# ═══════════════════════════════════════════════════════════════════════
# 6. Warehouse Dashboard & Capacity Reports Tests
# ═══════════════════════════════════════════════════════════════════════

def test_warehouse_dashboard_and_reports(client, mock_wms_env):
    res_seed = client.post("/api/warehouse/seed-locations")
    assert res_seed.status_code == 200

    res_dash = client.get("/api/warehouse/dashboard")
    assert res_dash.status_code == 200, res_dash.text
    dash_data = res_dash.json()
    assert dash_data["total_cells"] == 240
    assert dash_data["total_capacity"] == 9600
    assert dash_data["empty_cells"] == 240

    res_cap = client.get("/api/warehouse/reports/capacity")
    assert res_cap.status_code == 200, res_cap.text
    assert res_cap.json()["total_capacity"] == 9600
    assert len(res_cap.json()["by_rack"]) == 3

    res_util = client.get("/api/warehouse/reports/location-utilization")
    assert res_util.status_code == 200, res_util.text
    assert len(res_util.json()["rows"]) == 240
