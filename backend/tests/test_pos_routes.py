import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from bson import ObjectId
from datetime import datetime, timezone

import server
from routes.pos import (
    pos_router,
    validate_po_styles,
    _sync_po_sku_mappings,
    _flag_jobs,
    _archive_if_complete,
    _build_client_ledger,
    compute_po_profitability,
)
from models.orders import POIn, POLineItem, ProductionStageUpdate
from models.vendors import GRNIn, GRNLineItem, PaymentIn, DefectIn
from models.workers import AssignmentUpdate, BulkAssign


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


class GenericMockCollection:
    def __init__(self):
        self.store = {}

    def _matches(self, doc, q):
        if not q:
            return True
        for k, v in q.items():
            if k == "_id" and not isinstance(v, dict):
                if str(doc.get("_id")) != str(v):
                    return False
            elif k == "$or":
                if not any(self._matches(doc, subq) for subq in v):
                    return False
            elif isinstance(v, dict):
                if "$in" in v:
                    doc_val = doc.get(k)
                    str_in = [str(x) for x in v["$in"]]
                    if isinstance(doc_val, list):
                        if not any(str(x) in str_in or x in v["$in"] for x in doc_val):
                            return False
                    else:
                        if str(doc_val) not in str_in and doc_val not in v["$in"]:
                            return False
                if "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        return False
                if "$regex" in v:
                    pattern = v["$regex"].lstrip("^").rstrip("$")
                    if pattern.lower() not in str(doc.get(k, "")).lower():
                        return False
            else:
                doc_val = doc.get(k)
                if isinstance(doc_val, list) and not isinstance(v, list):
                    if v not in doc_val and str(v) not in [str(x) for x in doc_val]:
                        return False
                elif doc_val != v:
                    return False
        return True

    def find(self, q=None, proj=None, sort=None):
        res = [d for d in self.store.values() if self._matches(d, q)]
        return MockCursor(res)

    async def find_one(self, q=None, sort=None):
        for d in self.store.values():
            if self._matches(d, q):
                return dict(d)
        return None

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.store[str(d["_id"])] = d
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def insert_many(self, docs):
        inserted_ids = []
        for doc in docs:
            d = dict(doc)
            if "_id" not in d:
                d["_id"] = ObjectId()
            self.store[str(d["_id"])] = d
            inserted_ids.append(d["_id"])
        res = MagicMock()
        res.inserted_ids = inserted_ids
        return res

    async def update_one(self, q, update):
        target = None
        for k, d in list(self.store.items()):
            if self._matches(d, q):
                target = d
                break
        if not target:
            res = MagicMock()
            res.modified_count = 0
            return res
        if "$set" in update:
            target.update(update["$set"])
        if "$inc" in update:
            for ik, iv in update["$inc"].items():
                target[ik] = target.get(ik, 0) + iv
        if "$unset" in update:
            for uk in update["$unset"].keys():
                target.pop(uk, None)
        if "$push" in update:
            for pk, pv in update["$push"].items():
                if pk not in target:
                    target[pk] = []
                target[pk].append(pv)
        self.store[str(target["_id"])] = target
        res = MagicMock()
        res.modified_count = 1
        return res

    async def update_many(self, q, update):
        count = 0
        for k, d in list(self.store.items()):
            if self._matches(d, q):
                if "$set" in update:
                    d.update(update["$set"])
                if "$push" in update:
                    for pk, pv in update["$push"].items():
                        if pk not in d:
                            d[pk] = []
                        d[pk].append(pv)
                self.store[k] = d
                count += 1
        res = MagicMock()
        res.modified_count = count
        return res

    async def delete_one(self, q):
        target_k = None
        for k, d in self.store.items():
            if self._matches(d, q):
                target_k = k
                break
        if target_k:
            del self.store[target_k]
            res = MagicMock()
            res.deleted_count = 1
            return res
        res = MagicMock()
        res.deleted_count = 0
        return res

    async def delete_many(self, q):
        to_del = [k for k, d in self.store.items() if self._matches(d, q)]
        for k in to_del:
            del self.store[k]
        res = MagicMock()
        res.deleted_count = len(to_del)
        return res

    async def count_documents(self, q=None):
        return sum(1 for d in self.store.values() if self._matches(d, q))


class MockPosDB:
    def __init__(self):
        self.pos = GenericMockCollection()
        self.styles = GenericMockCollection()
        self.sku_map = GenericMockCollection()
        self.production_jobs = GenericMockCollection()
        self.invoices = GenericMockCollection()
        self.grns = GenericMockCollection()
        self.payments = GenericMockCollection()
        self.clients = GenericMockCollection()
        self.workers = GenericMockCollection()
        self.defects = GenericMockCollection()
        self.materials = GenericMockCollection()
        self.inventory_movements = GenericMockCollection()
        self.component_stock_movements = GenericMockCollection()
        self.component_master = GenericMockCollection()
        self.advances = GenericMockCollection()
        self.settings = GenericMockCollection()
        self.counters = GenericMockCollection()
        self.dispatch_records = GenericMockCollection()


@pytest.fixture
def mock_pos_env(monkeypatch):
    mock_db = MockPosDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "roles": ["admin", "manager", "sales", "production"],
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    monkeypatch.setattr(server, "log_activity", AsyncMock())
    return mock_db


@pytest.fixture
def client(mock_pos_env):
    test_app = FastAPI()
    test_app.include_router(pos_router)
    return TestClient(test_app)


# -------------------- PO TESTS --------------------

def test_validate_po_styles_success(mock_pos_env):
    asyncio.run(mock_pos_env.styles.insert_one({"code": "ART-101", "name": "Derby Classic"}))
    payload = POIn(
        po_number="PO-1001",
        client_name="Test Retailer",
        po_date="2026-03-01",
        line_items=[
            POLineItem(style_code="art-101", quantity=50, unit_price=450.0, amount=22500.0)
        ]
    )
    asyncio.run(validate_po_styles(payload))
    assert payload.line_items[0].style_code == "ART-101"


def test_validate_po_styles_unresolved_raises_422(mock_pos_env):
    asyncio.run(mock_pos_env.styles.insert_one({"code": "ART-101", "name": "Derby Classic"}))
    payload = POIn(
        po_number="PO-1002",
        client_name="Test Retailer",
        po_date="2026-03-01",
        line_items=[
            POLineItem(style_code="UNKNOWN-CODE", quantity=10, unit_price=500.0, amount=5000.0)
        ]
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(validate_po_styles(payload))
    assert exc_info.value.status_code == 422
    assert "unresolved_line_items" in exc_info.value.detail


def test_create_and_get_po(client, mock_pos_env):
    # Setup style
    asyncio.run(mock_pos_env.styles.insert_one({"code": "ART-200", "name": "Oxford Sneaker", "bom": []}))

    po_data = {
        "po_number": "PO-TEST-01",
        "client_name": "Metro Shoes",
        "po_date": "2026-03-01",
        "line_items": [
            {"style_code": "ART-200", "quantity": 100, "unit_price": 600.0, "amount": 60000.0, "color": "Black", "size": "8"}
        ]
    }

    # Create PO
    resp = client.post("/api/pos", json=po_data)
    assert resp.status_code == 200
    po_doc = resp.json()
    po_id = po_doc["id"]
    assert po_doc["po_number"] == "PO-TEST-01"
    assert po_doc["total_quantity"] == 100

    # Production job auto-created
    jobs = list(mock_pos_env.production_jobs.store.values())
    assert len(jobs) == 1
    assert jobs[0]["style_code"] == "ART-200"
    assert jobs[0]["quantity"] == 100
    assert jobs[0]["stage"] == "procurement"

    # Get PO
    get_resp = client.get(f"/api/pos/{po_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == po_id


def test_delete_po_with_reversal_movements(client, mock_pos_env, monkeypatch):
    monkeypatch.setattr(server, "_compute_material_inventory_summary", AsyncMock(return_value={"balance": 100.0, "weighted_avg_rate": 50.0, "last_rate": 50.0}))

    # Create style, material, PO, and movement
    mat_id = str(ObjectId())
    asyncio.run(mock_pos_env.materials.insert_one({"_id": ObjectId(mat_id), "code": "LEATHER-01", "name": "Black Leather", "balance": 50.0, "rate": 50.0}))

    po_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({"_id": ObjectId(po_id), "po_number": "PO-DEL-01", "client_name": "Test Client"}))

    job_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({"_id": ObjectId(job_id), "po_id": po_id, "po_number": "PO-DEL-01", "quantity": 20}))

    asyncio.run(mock_pos_env.inventory_movements.insert_one({
        "material_id": mat_id,
        "type": "out",
        "quantity": 10.0,
        "rate": 50.0,
        "job_id": job_id,
        "po_id": po_id,
    }))

    # Delete PO
    del_resp = client.delete(f"/api/pos/{po_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["reversed_movements_count"] == 1

    # Check compensating movement
    rev_movs = [m for m in mock_pos_env.inventory_movements.store.values() if m.get("is_reversal")]
    assert len(rev_movs) == 1
    assert rev_movs[0]["type"] == "in"
    assert rev_movs[0]["quantity"] == 10.0

    # PO and jobs removed
    assert po_id not in mock_pos_env.pos.store
    assert len(mock_pos_env.production_jobs.store) == 0


def test_delete_po_rejected_when_dispatch_record_exists(client, mock_pos_env):
    # Setup PO, Job, and Dispatch Record
    po_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({"_id": ObjectId(po_id), "po_number": "PO-DISPATCHED-01", "client_name": "Test Client"}))
    job_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({"_id": ObjectId(job_id), "po_id": po_id, "po_number": "PO-DISPATCHED-01", "quantity": 50}))
    dr_id = str(ObjectId())
    asyncio.run(mock_pos_env.dispatch_records.insert_one({
        "_id": ObjectId(dr_id),
        "po_id": po_id,
        "po_ids": [po_id],
        "job_ids": [job_id],
        "invoice_no": "INV-2026-999",
    }))

    # Attempt delete
    del_resp = client.delete(f"/api/pos/{po_id}")
    assert del_resp.status_code == 409
    assert "Cannot delete PO — it has dispatch/invoice history" in del_resp.json()["detail"]

    # Verify PO, jobs, and dispatch records are all untouched
    assert po_id in mock_pos_env.pos.store
    assert job_id in mock_pos_env.production_jobs.store
    assert dr_id in mock_pos_env.dispatch_records.store


def test_delete_po_rejected_when_invoice_exists(client, mock_pos_env):
    # Setup PO, Job, and Invoice
    po_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({"_id": ObjectId(po_id), "po_number": "PO-INVOICED-01", "client_name": "Test Client"}))
    job_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({"_id": ObjectId(job_id), "po_id": po_id, "po_number": "PO-INVOICED-01", "quantity": 50}))
    inv_id = str(ObjectId())
    asyncio.run(mock_pos_env.invoices.insert_one({
        "_id": ObjectId(inv_id),
        "po_id": po_id,
        "invoice_no": "INV-2026-888",
    }))

    # Attempt delete
    del_resp = client.delete(f"/api/pos/{po_id}")
    assert del_resp.status_code == 409
    assert "Cannot delete PO — it has dispatch/invoice history" in del_resp.json()["detail"]

    # Verify PO, jobs, and invoices are all untouched
    assert po_id in mock_pos_env.pos.store
    assert job_id in mock_pos_env.production_jobs.store
    assert inv_id in mock_pos_env.invoices.store


# -------------------- GRN & PAYMENT TESTS --------------------

def test_grn_workflow(client, mock_pos_env, monkeypatch):
    from routes import pos as pos_module
    monkeypatch.setattr(pos_module, "next_grn_no", AsyncMock(return_value="GRN-00001"))

    # Create an invoice
    inv_id = str(ObjectId())
    asyncio.run(mock_pos_env.invoices.insert_one({
        "_id": ObjectId(inv_id),
        "invoice_no": "INV-2026-001",
        "grand_total": 50000.0,
        "client_name": "ABC Retailers",
        "payment_terms_days": 30,
    }))

    grn_payload = {
        "invoice_id": inv_id,
        "grn_date": "2026-03-10",
        "line_items": [
            {
                "style_code": "ART-101",
                "dispatched_qty": 100,
                "received_qty": 100,
                "accepted_qty": 95,
                "rejected_qty": 5,
                "rejection_reason": "Defective stitching",
            }
        ]
    }

    # Create GRN
    resp = client.post("/api/grns", json=grn_payload)
    assert resp.status_code == 200
    grn_doc = resp.json()
    assert grn_doc["grn_no"] == "GRN-00001"
    assert grn_doc["total_accepted"] == 95
    assert grn_doc["total_rejected"] == 5

    # Verify invalid received > dispatched fails
    invalid_payload = dict(grn_payload)
    invalid_payload["line_items"] = [{"style_code": "ART-101", "dispatched_qty": 50, "received_qty": 60}]
    bad_resp = client.post("/api/grns", json=invalid_payload)
    assert bad_resp.status_code == 400


def test_payment_and_client_ledger(client, mock_pos_env, monkeypatch):
    from routes import pos as pos_module
    monkeypatch.setattr(pos_module, "next_payment_no", AsyncMock(return_value="PAY-00001"))

    # Create invoice
    inv_id = str(ObjectId())
    asyncio.run(mock_pos_env.invoices.insert_one({
        "_id": ObjectId(inv_id),
        "invoice_no": "INV-2026-002",
        "client_name": "Metro Shoes",
        "grand_total": 20000.0,
        "net_amount": 20000.0,
        "invoice_date": "2026-03-01",
        "due_date": "2026-03-31",
    }))

    pay_payload = {
        "amount": 15000.0,
        "payment_date": "2026-03-15",
        "mode": "NEFT",
        "reference": "UTR12345678",
        "invoice_ids": [inv_id],
    }

    resp = client.post("/api/payments", json=pay_payload)
    assert resp.status_code == 200
    pay_doc = resp.json()
    assert pay_doc["payment_no"] == "PAY-00001"
    assert pay_doc["allocations"][inv_id] == 15000.0

    # Query client ledger
    ledger_resp = client.get(f"/api/clients/Metro%20Shoes/ledger")
    assert ledger_resp.status_code == 200
    ledger = ledger_resp.json()
    assert ledger["client_name"] == "Metro Shoes"
    assert ledger["total_invoiced"] == 20000.0
    assert ledger["total_received"] == 15000.0
    assert ledger["closing_balance"] == 5000.0


# -------------------- PRODUCTION JOBS & GATING TESTS --------------------

def test_production_job_procurement_gating(client, mock_pos_env, monkeypatch):
    import routes.materials as mat_module
    monkeypatch.setattr(mat_module, "_auto_consume_inventory", AsyncMock(return_value=True))

    # Create style with BOM
    asyncio.run(mock_pos_env.styles.insert_one({
        "code": "ART-GATED",
        "name": "Gated Shoe",
        "bom": [{"material_code": "MAT-1", "consumption": 1.0}]
    }))

    job_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(job_id),
        "style_code": "ART-GATED",
        "stage": "procurement",
        "quantity": 50,
        "inventory_consumed": True,
        "components": {"upper_done": False, "bottom_done": False}
    }))

    # Move to cutting (next stage) -> should succeed
    patch_resp = client.patch(f"/api/production/jobs/{job_id}", json={"stage": "cutting"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["stage"] == "cutting"

    # Try moving to lasting without upper and bottom -> should fail
    lasting_fail = client.patch(f"/api/production/jobs/{job_id}", json={"stage": "lasting"})
    assert lasting_fail.status_code == 400
    assert "upper and bottom" in lasting_fail.json()["detail"]

    # Complete components
    comp_resp = client.patch(f"/api/production/jobs/{job_id}/components", json={"upper_done": True, "bottom_done": True})
    assert comp_resp.status_code == 200

    # Now move to lasting -> should succeed
    lasting_ok = client.patch(f"/api/production/jobs/{job_id}", json={"stage": "lasting"})
    assert lasting_ok.status_code == 200
    assert lasting_ok.json()["stage"] == "lasting"


# -------------------- PO COMPLETION STATUS & FILTERING TESTS --------------------

def test_po_completed_status_when_all_jobs_dispatched_and_invoiced(client, mock_pos_env):
    po_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({
        "_id": ObjectId(po_id),
        "po_number": "PO-COMP-101",
        "client_name": "Full Client",
        "total_quantity": 100,
        "grand_total": 50000.0,
    }))

    # 2 jobs, both dispatched/archived
    j1_id = str(ObjectId())
    j2_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j1_id),
        "po_id": po_id,
        "po_number": "PO-COMP-101",
        "stage": "dispatched",
        "archived": True,
        "invoice_generated_at": "2026-03-01T10:00:00Z",
    }))
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j2_id),
        "po_id": po_id,
        "po_number": "PO-COMP-101",
        "stage": "dispatched",
        "archived": True,
        "invoice_generated_at": "2026-03-01T10:00:00Z",
    }))

    # 1 invoice
    inv_id = str(ObjectId())
    asyncio.run(mock_pos_env.invoices.insert_one({
        "_id": ObjectId(inv_id),
        "po_id": po_id,
        "po_number": "PO-COMP-101",
        "invoice_no": "INV-2026-COMP",
    }))

    # Query single PO
    get_resp = client.get(f"/api/pos/{po_id}")
    assert get_resp.status_code == 200
    po_data = get_resp.json()
    assert po_data["is_completed"] is True
    assert po_data["status"] == "completed"

    # Query list
    list_resp = client.get("/api/pos")
    assert list_resp.status_code == 200
    all_pos = list_resp.json()
    matched = [p for p in all_pos if p["id"] == po_id]
    assert len(matched) == 1
    assert matched[0]["is_completed"] is True
    assert matched[0]["status"] == "completed"


def test_po_active_status_when_partially_dispatched(client, mock_pos_env):
    po_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({
        "_id": ObjectId(po_id),
        "po_number": "PO-PART-202",
        "client_name": "Partial Client",
        "total_quantity": 100,
        "grand_total": 50000.0,
    }))

    # 2 jobs: 1 dispatched, 1 still in stitching
    j1_id = str(ObjectId())
    j2_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j1_id),
        "po_id": po_id,
        "po_number": "PO-PART-202",
        "stage": "dispatched",
        "archived": True,
        "invoice_generated_at": "2026-03-01T10:00:00Z",
    }))
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j2_id),
        "po_id": po_id,
        "po_number": "PO-PART-202",
        "stage": "stitching",
        "archived": False,
    }))

    # Invoice exists for the partial shipment
    inv_id = str(ObjectId())
    asyncio.run(mock_pos_env.invoices.insert_one({
        "_id": ObjectId(inv_id),
        "po_id": po_id,
        "po_number": "PO-PART-202",
        "invoice_no": "INV-2026-PART",
    }))

    get_resp = client.get(f"/api/pos/{po_id}")
    assert get_resp.status_code == 200
    po_data = get_resp.json()
    assert po_data["is_completed"] is False
    assert po_data["status"] != "completed"


def test_po_active_status_when_all_jobs_dispatched_without_invoice(client, mock_pos_env):
    po_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({
        "_id": ObjectId(po_id),
        "po_number": "PO-NOINV-303",
        "client_name": "No Invoice Client",
        "total_quantity": 50,
        "grand_total": 25000.0,
    }))

    # Job is dispatched but no invoice or dispatch record exists
    j1_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j1_id),
        "po_id": po_id,
        "po_number": "PO-NOINV-303",
        "stage": "dispatched",
        "archived": True,
    }))

    get_resp = client.get(f"/api/pos/{po_id}")
    assert get_resp.status_code == 200
    po_data = get_resp.json()
    assert po_data["is_completed"] is False
    assert po_data["status"] != "completed"


def test_list_pos_status_filter_query(client, mock_pos_env):
    # PO 1: Completed (job dispatched + invoice)
    po1_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({
        "_id": ObjectId(po1_id),
        "po_number": "PO-FILT-COMP",
        "client_name": "Client A",
    }))
    j1_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j1_id),
        "po_id": po1_id,
        "po_number": "PO-FILT-COMP",
        "stage": "dispatched",
        "archived": True,
        "invoice_generated_at": "2026-03-01T10:00:00Z",
    }))
    inv1_id = str(ObjectId())
    asyncio.run(mock_pos_env.invoices.insert_one({
        "_id": ObjectId(inv1_id),
        "po_id": po1_id,
        "po_number": "PO-FILT-COMP",
    }))

    # PO 2: Active (job in assembly, no invoice)
    po2_id = str(ObjectId())
    asyncio.run(mock_pos_env.pos.insert_one({
        "_id": ObjectId(po2_id),
        "po_number": "PO-FILT-ACT",
        "client_name": "Client B",
    }))
    j2_id = str(ObjectId())
    asyncio.run(mock_pos_env.production_jobs.insert_one({
        "_id": ObjectId(j2_id),
        "po_id": po2_id,
        "po_number": "PO-FILT-ACT",
        "stage": "assembly",
    }))

    # Filter ?status=active
    active_resp = client.get("/api/pos?status=active")
    assert active_resp.status_code == 200
    active_ids = [p["id"] for p in active_resp.json()]
    assert po2_id in active_ids
    assert po1_id not in active_ids

    # Filter ?status=completed
    comp_resp = client.get("/api/pos?status=completed")
    assert comp_resp.status_code == 200
    comp_ids = [p["id"] for p in comp_resp.json()]
    assert po1_id in comp_ids
    assert po2_id not in comp_ids
