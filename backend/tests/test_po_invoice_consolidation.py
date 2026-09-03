"""Unit tests for invoice generation convergence and single source of truth (db.invoices)."""
import pytest
from httpx import AsyncClient, ASGITransport
import base64
from bson import ObjectId

import server
from server import app, oid, now_iso


class MockFindCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        reverse = (direction == -1)
        self._docs.sort(key=lambda d: d.get(key, "") or "", reverse=reverse)
        return self

    async def to_list(self, limit=None):
        if limit:
            return self._docs[:limit]
        return self._docs


def match_filter(doc, filter_dict):
    if not filter_dict:
        return True
    if "_id" in filter_dict:
        if str(doc.get("_id")) != str(filter_dict["_id"]):
            return False
    if "$or" in filter_dict:
        if not any(match_filter(doc, sub) for sub in filter_dict["$or"]):
            return False
    for k, v in filter_dict.items():
        if k in ("_id", "$or"):
            continue
        val = doc.get(k)
        if isinstance(v, dict) and "$in" in v:
            target_list = v["$in"]
            if isinstance(val, list):
                if not any(item in target_list for item in val):
                    return False
            else:
                if val not in target_list:
                    return False
        else:
            if val != v:
                return False
    return True


class MockCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, filter_dict):
        for d in self.docs:
            if match_filter(d, filter_dict):
                return d
        return None

    def find(self, filter_dict=None, projection=None):
        res = [d for d in self.docs if match_filter(d, filter_dict or {})]
        return MockFindCursor(res)

    async def insert_one(self, doc):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        self.docs.append(doc_copy)
        class InsertResult:
            inserted_id = doc_copy["_id"]
        return InsertResult()

    async def update_one(self, filter_dict, update, upsert=False):
        target = await self.find_one(filter_dict)
        if not target and upsert:
            target = dict(filter_dict)
            self.docs.append(target)
        if target and "$set" in update:
            target.update(update["$set"])
        class UpdateResult:
            modified_count = 1 if target else 0
        return UpdateResult()

    async def find_one_and_update(self, filter_dict, update, upsert=False, return_document=False):
        target = await self.find_one(filter_dict)
        if not target and upsert:
            target = dict(filter_dict)
            self.docs.append(target)
        if target and "$inc" in update:
            for k, inc_val in update["$inc"].items():
                target[k] = target.get(k, 0) + inc_val
        if target and "$set" in update:
            target.update(update["$set"])
        return target

    async def count_documents(self, filter_dict):
        res = [d for d in self.docs if match_filter(d, filter_dict)]
        return len(res)

    async def delete_one(self, filter_dict):
        target = await self.find_one(filter_dict)
        if target:
            self.docs.remove(target)


class MockDB:
    def __init__(self):
        self.pos = MockCollection()
        self.invoices = MockCollection()
        self.dispatch_records = MockCollection()
        self.payments = MockCollection()
        self.grns = MockCollection()
        self.counters = MockCollection()
        self.production_jobs = MockCollection()


@pytest.fixture
def mock_db(monkeypatch):
    mdb = MockDB()
    monkeypatch.setattr(server, "db", mdb)
    return mdb


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def mock_user_override(monkeypatch):
    async def mock_get_current_user(request=None):
        return {
            "id": "admin_test_id",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "roles": ["admin"],
        }
    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)


@pytest.mark.anyio
async def test_po_invoice_zero_invoices_creates_doc(mock_db, mock_user_override, async_client):
    """When 0 invoices exist in db.invoices, po_invoice generates new invoice and inserts record into db.invoices."""
    po_doc = {
        "po_number": f"PO-TEST-001-{ObjectId()}",
        "po_date": "09/08/2026",
        "client_name": "Test Client A",
        "total_quantity": 10,
        "grand_total": 1000.0,
        "subtotal": 952.38,
        "cgst_amount": 23.81,
        "sgst_amount": 23.81,
        "igst_amount": 0.0,
        "line_items": [
            {
                "style_code": "STYLE-A",
                "description": "Test Shoe A",
                "color": "Black",
                "hsn_code": "6403",
                "quantity": 10,
                "unit_price": 100.0,
                "amount": 1000.0,
                "mrp": 150.0,
            }
        ],
        "created_at": now_iso(),
    }
    res = await mock_db.pos.insert_one(po_doc)
    pid = str(res.inserted_id)

    # 1. Verify 0 invoices initially in db.invoices
    inv_count_before = await mock_db.invoices.count_documents({"po_id": pid})
    assert inv_count_before == 0

    # 2. Call GET /api/pos/{pid}/invoice.pdf
    response = await async_client.get(f"/api/pos/{pid}/invoice.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 0

    # 3. Verify exactly 1 invoice document now exists in db.invoices
    inv_docs = await mock_db.invoices.find({"po_id": pid}).to_list(10)
    assert len(inv_docs) == 1
    inv = inv_docs[0]

    assert inv["po_id"] == pid
    assert inv["po_number"] == po_doc["po_number"]
    assert inv["client_name"] == "Test Client A"
    assert "file_b64" in inv and len(inv["file_b64"]) > 0
    assert inv["invoice_no"] is not None


@pytest.mark.anyio
async def test_po_invoice_single_existing_serves_same(mock_db, mock_user_override, async_client):
    """When 1 invoice already exists in db.invoices, po_invoice serves it and does not generate a new invoice."""
    po_doc = {
        "po_number": f"PO-TEST-002-{ObjectId()}",
        "po_date": "09/08/2026",
        "client_name": "Test Client B",
        "total_quantity": 5,
        "grand_total": 500.0,
        "created_at": now_iso(),
    }
    res_po = await mock_db.pos.insert_one(po_doc)
    pid = str(res_po.inserted_id)

    dummy_pdf_b64 = base64.b64encode(b"%PDF-1.4 Dummy PDF Content").decode("ascii")
    inv_doc = {
        "invoice_no": "INV-EXISTING-999",
        "invoice_date": "09/08/2026",
        "po_id": pid,
        "po_number": po_doc["po_number"],
        "po_numbers": [po_doc["po_number"]],
        "client_name": "Test Client B",
        "job_ids": ["job_101"],
        "grand_total": 500.0,
        "file_b64": dummy_pdf_b64,
        "created_at": now_iso(),
    }
    res_inv = await mock_db.invoices.insert_one(inv_doc)

    # Call GET /api/pos/{pid}/invoice.pdf
    response = await async_client.get(f"/api/pos/{pid}/invoice.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 Dummy PDF Content"

    # Confirm count in db.invoices is still 1
    count = await mock_db.invoices.count_documents({"po_id": pid})
    assert count == 1


@pytest.mark.anyio
async def test_po_invoice_multiple_existing_returns_json(mock_db, mock_user_override, async_client):
    """When multiple invoices exist in db.invoices for a PO, po_invoice returns JSON listing them."""
    po_doc = {
        "po_number": f"PO-TEST-003-{ObjectId()}",
        "po_date": "09/08/2026",
        "client_name": "Test Client C",
        "total_quantity": 20,
        "grand_total": 2000.0,
        "created_at": now_iso(),
    }
    res_po = await mock_db.pos.insert_one(po_doc)
    pid = str(res_po.inserted_id)

    inv1 = {
        "invoice_no": "INV-BATCH-1",
        "invoice_date": "08/08/2026",
        "po_id": pid,
        "po_number": po_doc["po_number"],
        "po_numbers": [po_doc["po_number"]],
        "client_name": "Test Client C",
        "job_ids": ["job_1"],
        "grand_total": 1000.0,
        "file_b64": base64.b64encode(b"%PDF-1").decode("ascii"),
        "created_at": "2026-08-08T10:00:00Z",
    }
    inv2 = {
        "invoice_no": "INV-BATCH-2",
        "invoice_date": "09/08/2026",
        "po_id": pid,
        "po_number": po_doc["po_number"],
        "po_numbers": [po_doc["po_number"]],
        "client_name": "Test Client C",
        "job_ids": ["job_2"],
        "grand_total": 1000.0,
        "file_b64": base64.b64encode(b"%PDF-2").decode("ascii"),
        "created_at": "2026-08-09T10:00:00Z",
    }
    await mock_db.invoices.insert_one(inv1)
    await mock_db.invoices.insert_one(inv2)

    # Call GET /api/pos/{pid}/invoice.pdf
    response = await async_client.get(f"/api/pos/{pid}/invoice.pdf")
    assert response.status_code == 200
    data = response.json()

    assert data.get("multiple") is True
    assert "invoices" in data
    assert len(data["invoices"]) == 2
    inv_nos = [i["invoice_no"] for i in data["invoices"]]
    assert "INV-BATCH-1" in inv_nos
    assert "INV-BATCH-2" in inv_nos

    # Call GET /api/pos/{pid}/invoices
    res_list = await async_client.get(f"/api/pos/{pid}/invoices")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert len(list_data) == 2


@pytest.mark.anyio
async def test_invoice_for_jobs_idempotency_with_dispatch_record(mock_db, mock_user_override, async_client):
    """POST /invoices/job returns existing dispatch invoice when job_ids are already in dispatch_records."""
    po_doc = {
        "po_number": f"PO-DISPATCH-{ObjectId()}",
        "po_date": "09/08/2026",
        "client_name": "Dispatch Client",
        "line_items": [{"style_code": "STYLE-D", "description": "Shoe D", "color": "Black", "hsn_code": "6403", "quantity": 5, "unit_price": 100.0, "amount": 500.0, "mrp": 150.0}],
    }
    res_po = await mock_db.pos.insert_one(po_doc)
    pid = str(res_po.inserted_id)

    dummy_pdf_b64 = base64.b64encode(b"%PDF-1.4 Dispatch Invoice Content").decode("ascii")
    dr_doc = {
        "invoice_no": "SSK26-27-999",
        "po_id": pid,
        "job_ids": ["job_dispatch_1"],
        "invoice_file_b64": dummy_pdf_b64,
        "dispatched_at": now_iso(),
    }
    await mock_db.dispatch_records.insert_one(dr_doc)

    # Calling POST /api/invoices/job for job_dispatch_1 should return the existing dispatch invoice PDF
    res = await async_client.post("/api/invoices/job", json={"po_id": pid, "job_ids": ["job_dispatch_1"]})
    assert res.status_code == 200
    assert res.content == b"%PDF-1.4 Dispatch Invoice Content"
    assert res.headers.get("X-Invoice-No") == "SSK26-27-999"

    # Confirm count in db.invoices remains 0 (no new invoice generated)
    count = await mock_db.invoices.count_documents({"po_id": pid})
    assert count == 0
