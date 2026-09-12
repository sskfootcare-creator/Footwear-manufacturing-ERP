import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.vendors import vendors_router
from routes.pos import pos_router
from routes.materials import materials_router, _compute_material_requirement
from models.orders import GeneratePlanningVendorPOsIn, MaterialAllocationItem, ProductionStageUpdate


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        return self

    async def to_list(self, limit):
        return self.docs


class MockPlanningDB:
    def __init__(self):
        self.vendors_store = {}
        self.vendor_pos_store = {}
        self.production_jobs_store = {}
        self.materials_store = {}
        self.styles_store = {}
        self.counters_store = {"vendor_po_seq": {"v": 5}}
        self.audit_logs_store = []
        self.counters = MagicMock()
        self.counters.find_one_and_update = AsyncMock(side_effect=self._inc_counter)

        # Vendors
        self.vendors = MagicMock()
        self.vendors.find = MagicMock(side_effect=self._find_vendors)
        self.vendors.find_one = AsyncMock(side_effect=self._find_one_vendor)

        # Vendor POs
        self.vendor_purchase_orders = MagicMock()
        self.vendor_purchase_orders.find = MagicMock(side_effect=self._find_vendor_pos)
        self.vendor_purchase_orders.find_one = AsyncMock(side_effect=self._find_one_vendor_po)
        self.vendor_purchase_orders.insert_one = AsyncMock(side_effect=self._insert_vendor_po)

        # Production Jobs
        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=self._find_jobs)
        self.production_jobs.find_one = AsyncMock(side_effect=self._find_one_job)
        self.production_jobs.update_one = AsyncMock(side_effect=self._update_one_job)
        self.production_jobs.update_many = AsyncMock(side_effect=self._update_many_jobs)

        # Materials & Styles
        self.materials = MagicMock()
        self.materials.find = MagicMock(side_effect=self._find_materials)
        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=self._find_styles)
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        # Audit
        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(side_effect=lambda doc: self.audit_logs_store.append(doc))

    async def _inc_counter(self, filter_q, update_q, upsert=True, return_document=True):
        cid = filter_q.get("_id")
        doc = self.counters_store.setdefault(cid, {"v": 0})
        doc["v"] += update_q.get("$inc", {}).get("v", 1)
        return dict(doc)

    def _find_vendors(self, query=None):
        docs = list(self.vendors_store.values())
        return MockCursor(docs)

    async def _find_one_vendor(self, query):
        if "_id" in query:
            return self.vendors_store.get(str(query["_id"]))
        return None

    def _find_vendor_pos(self, query=None):
        docs = list(self.vendor_pos_store.values())
        return MockCursor(docs)

    async def _find_one_vendor_po(self, query):
        if "_id" in query:
            return self.vendor_pos_store.get(str(query["_id"]))
        return None

    async def _insert_vendor_po(self, doc):
        oid_str = str(ObjectId())
        doc_copy = dict(doc)
        doc_copy["_id"] = ObjectId(oid_str)
        self.vendor_pos_store[oid_str] = doc_copy
        res = MagicMock()
        res.inserted_id = ObjectId(oid_str)
        return res

    def _find_jobs(self, query=None):
        docs = list(self.production_jobs_store.values())
        if query and "_id" in query and "$in" in query["_id"]:
            allowed = {str(o) for o in query["_id"]["$in"]}
            docs = [d for d in docs if str(d["_id"]) in allowed]
        return MockCursor(docs)

    async def _find_one_job(self, query):
        if "_id" in query:
            return self.production_jobs_store.get(str(query["_id"]))
        return None

    async def _update_one_job(self, query, update_doc):
        jid = str(query["_id"])
        job = self.production_jobs_store.get(jid)
        if not job:
            return MagicMock(matched_count=0)
        if "$set" in update_doc:
            job.update(update_doc["$set"])
        if "$unset" in update_doc:
            for k in update_doc["$unset"]:
                job.pop(k, None)
        if "$push" in update_doc:
            for k, val in update_doc["$push"].items():
                job.setdefault(k, []).append(val)
        return MagicMock(matched_count=1)

    async def _update_many_jobs(self, query, update_doc):
        matched = 0
        allowed = None
        if "_id" in query and "$in" in query["_id"]:
            allowed = {str(o) for o in query["_id"]["$in"]}
        for jid, job in self.production_jobs_store.items():
            if allowed is None or jid in allowed:
                matched += 1
                if "$set" in update_doc:
                    job.update(update_doc["$set"])
                if "$addToSet" in update_doc:
                    for k, val in update_doc["$addToSet"].items():
                        job.setdefault(k, [])
                        if "$each" in val:
                            for item in val["$each"]:
                                if item not in job[k]:
                                    job[k].append(item)
                        elif val not in job[k]:
                            job[k].append(val)
                if "$push" in update_doc:
                    for k, val in update_doc["$push"].items():
                        job.setdefault(k, []).append(val)
        return MagicMock(matched_count=matched)

    def _find_materials(self, query=None):
        return MockCursor(list(self.materials_store.values()))

    def _find_styles(self, query=None):
        return MockCursor(list(self.styles_store.values()))

    async def _find_one_style(self, query):
        if "_id" in query:
            return self.styles_store.get(str(query["_id"]))
        if "code" in query:
            for s in self.styles_store.values():
                if s.get("code") == query["code"]:
                    return s
        return None


@pytest.fixture
def mock_app():
    app = FastAPI()
    db = MockPlanningDB()
    app.mongodb = db
    server.db = db

    app.include_router(vendors_router)
    app.include_router(pos_router)
    app.include_router(materials_router)

    # Seed vendor 1 & vendor 2
    v1_id = str(ObjectId())
    db.vendors_store[v1_id] = {
        "_id": ObjectId(v1_id),
        "name": "Leather Corp",
        "email": "leather@corp.com",
        "active": True,
    }
    v2_id = str(ObjectId())
    db.vendors_store[v2_id] = {
        "_id": ObjectId(v2_id),
        "name": "Sole Masters Ltd",
        "email": "soles@masters.com",
        "active": True,
    }

    # Seed materials
    m1_id = str(ObjectId())
    db.materials_store[m1_id] = {
        "_id": ObjectId(m1_id),
        "code": "MAT-UPP-01",
        "name": "Brown Upper Leather",
        "unit": "sqft",
        "rate": 120.0,
        "category": "Upper",
        "preferred_vendor_id": v1_id,
        "current_stock": 500.0,
    }
    m2_id = str(ObjectId())
    db.materials_store[m2_id] = {
        "_id": ObjectId(m2_id),
        "code": "MAT-SOL-01",
        "name": "TPR Lug Sole",
        "unit": "pair",
        "rate": 180.0,
        "category": "Sole",
        "preferred_vendor_id": v2_id,
        "current_stock": 200.0,
    }

    # Seed production jobs in planning stage
    j1_id = str(ObjectId())
    db.production_jobs_store[j1_id] = {
        "_id": ObjectId(j1_id),
        "po_number": "PO-TEST-001",
        "client_name": "Test Retail Ltd",
        "style_code": "SSK_00034",
        "color": "Brown",
        "size": "7",
        "quantity": 50,
        "stage": "planning",
        "planning_notes": "Urgent festive run",
        "vendor_po_ids": [],
        "vendor_po_numbers": [],
        "history": [],
    }
    j2_id = str(ObjectId())
    db.production_jobs_store[j2_id] = {
        "_id": ObjectId(j2_id),
        "po_number": "PO-TEST-001",
        "client_name": "Test Retail Ltd",
        "style_code": "SSK_00034",
        "color": "Brown",
        "size": "8",
        "quantity": 50,
        "stage": "planning",
        "planning_notes": "Urgent festive run",
        "vendor_po_ids": [],
        "vendor_po_numbers": [],
        "history": [],
    }

    # Fake admin user
    async def fake_get_user(request):
        return {"email": "admin@ssk.com", "name": "Admin", "role": "admin"}

    server.get_current_user = fake_get_user

    return app, db, {
        "v1_id": v1_id,
        "v2_id": v2_id,
        "m1_id": m1_id,
        "m2_id": m2_id,
        "j1_id": j1_id,
        "j2_id": j2_id,
    }


def test_generate_planning_vendor_pos_success(mock_app):
    app, db, ids = mock_app
    client = TestClient(app)

    payload = {
        "job_ids": [ids["j1_id"], ids["j2_id"]],
        "customer_po_number": "PO-TEST-001",
        "style_code": "SSK_00034",
        "color": "Brown",
        "expected_delivery_date": "2026-10-01",
        "notes": "Planning stage allocation test",
        "allocations": [
            {
                "material_id": ids["m1_id"],
                "material_code": "MAT-UPP-01",
                "material_name": "Brown Upper Leather",
                "unit": "sqft",
                "color": "Brown",
                "quantity": 250.0,
                "rate": 120.0,
                "amount": 30000.0,
                "vendor_id": ids["v1_id"],
                "vendor_name": "Leather Corp",
            },
            {
                "material_id": ids["m2_id"],
                "material_code": "MAT-SOL-01",
                "material_name": "TPR Lug Sole",
                "unit": "pair",
                "color": "",
                "quantity": 100.0,
                "rate": 180.0,
                "amount": 18000.0,
                "vendor_id": ids["v2_id"],
                "vendor_name": "Sole Masters Ltd",
            },
        ],
    }

    res = client.post("/api/production/planning/generate-vendor-pos", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["ok"] is True
    assert data["count"] == 2
    assert len(data["vendor_po_numbers"]) == 2

    # Check vendor purchase orders created in DB
    assert len(db.vendor_pos_store) == 2
    vpos = list(db.vendor_pos_store.values())

    vpo_leather = next(v for v in vpos if v["vendor_id"] == ids["v1_id"])
    assert vpo_leather["customer_po_number"] == "PO-TEST-001"
    assert vpo_leather["style_code"] == "SSK_00034"
    assert vpo_leather["total_amount"] == 30000.0
    assert len(vpo_leather["line_items"]) == 1
    assert vpo_leather["line_items"][0]["material_code"] == "MAT-UPP-01"

    vpo_sole = next(v for v in vpos if v["vendor_id"] == ids["v2_id"])
    assert vpo_sole["customer_po_number"] == "PO-TEST-001"
    assert vpo_sole["total_amount"] == 18000.0
    assert len(vpo_sole["line_items"]) == 1

    # Check jobs were updated with allocations and vendor PO references
    j1 = db.production_jobs_store[ids["j1_id"]]
    assert len(j1["vendor_po_numbers"]) == 2
    assert "material_vendor_allocations" in j1
    assert "MAT-UPP-01_Brown" in j1["material_vendor_allocations"]
    assert any("Generated Vendor PO" in h["notes"] for h in j1["history"])


def test_generate_planning_vendor_pos_consolidation_same_vendor(mock_app):
    """Multiple materials for the same vendor must consolidate into a SINGLE vendor PO."""
    app, db, ids = mock_app
    client = TestClient(app)

    payload = {
        "job_ids": [ids["j1_id"]],
        "customer_po_number": "PO-TEST-001",
        "style_code": "SSK_00034",
        "color": "Brown",
        "allocations": [
            {
                "material_id": ids["m1_id"],
                "material_code": "MAT-UPP-01",
                "material_name": "Brown Upper Leather",
                "unit": "sqft",
                "quantity": 100.0,
                "rate": 120.0,
                "amount": 12000.0,
                "vendor_id": ids["v1_id"],
            },
            {
                "material_id": ids["m2_id"],
                "material_code": "MAT-UPP-02",
                "material_name": "Lining Leather",
                "unit": "sqft",
                "quantity": 50.0,
                "rate": 80.0,
                "amount": 4000.0,
                "vendor_id": ids["v1_id"],  # Same vendor!
            },
        ],
    }

    res = client.post("/api/production/planning/generate-vendor-pos", json=payload)
    assert res.status_code == 201
    data = res.json()

    # Should consolidate into 1 PO with 2 line items
    assert data["count"] == 1
    vpos = list(db.vendor_pos_store.values())
    assert len(vpos) == 1
    assert vpos[0]["total_amount"] == 16000.0
    assert len(vpos[0]["line_items"]) == 2


def test_planning_notes_and_stage_transition(mock_app):
    app, db, ids = mock_app
    client = TestClient(app)

    # 1. Update planning notes
    patch_res = client.patch(
        f"/api/production/jobs/{ids['j1_id']}",
        json={"planning_notes": "Revised: client requested premium burnish finish"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["planning_notes"] == "Revised: client requested premium burnish finish"

    # 2. Advance stage from planning to procurement
    stage_res = client.patch(
        f"/api/production/jobs/{ids['j1_id']}",
        json={"stage": "procurement"},
    )
    assert stage_res.status_code == 200
    assert stage_res.json()["stage"] == "procurement"
