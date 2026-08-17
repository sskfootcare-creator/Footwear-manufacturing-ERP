import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, date, timedelta
from bson import ObjectId

import server
from server import app, oid, now_iso, _decorate_invoice, _due_iso


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
        elif isinstance(v, dict) and "$ne" in v:
            if val == v["$ne"]:
                return False
        else:
            if val != v:
                return False
    return True


class MockCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, filter_dict, *args, **kwargs):
        sort_clause = kwargs.get("sort")
        matching = [d for d in self.docs if match_filter(d, filter_dict)]
        if sort_clause:
            k, direction = sort_clause[0]
            matching.sort(key=lambda d: d.get(k, "") or "", reverse=(direction == -1))
        if matching:
            return matching[0]
        return None

    def find(self, filter_dict=None, *args, **kwargs):
        matching = [d for d in self.docs if match_filter(d, filter_dict or {})]
        return MockFindCursor(matching)

    async def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs.append(doc)
        class InsertResult:
            inserted_id = doc["_id"]
        return InsertResult()

    async def update_one(self, filter_dict, update_dict, upsert=False):
        for doc in self.docs:
            if match_filter(doc, filter_dict):
                if "$set" in update_dict:
                    for k, v in update_dict["$set"].items():
                        doc[k] = v
                return
        if upsert:
            new_doc = {}
            if "$set" in update_dict:
                new_doc.update(update_dict["$set"])
            new_doc.update({k: v for k, v in filter_dict.items() if not k.startswith("$")})
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self.docs.append(new_doc)

    async def delete_one(self, filter_dict):
        before_len = len(self.docs)
        self.docs = [d for d in self.docs if not match_filter(d, filter_dict)]
        class DeleteResult:
            deleted_count = before_len - len(self.docs)
        return DeleteResult()

    async def find_one_and_update(self, filter_dict, update_dict, upsert=False, return_document=True):
        for doc in self.docs:
            if match_filter(doc, filter_dict):
                if "$inc" in update_dict:
                    for k, v in update_dict["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                return doc
        if upsert:
            new_doc = {"_id": filter_dict.get("_id", "seq")}
            if "$inc" in update_dict:
                for k, v in update_dict["$inc"].items():
                    new_doc[k] = v
            self.docs.append(new_doc)
            return new_doc
        return None


class MockDB:
    def __init__(self):
        self.pos = MockCollection()
        self.invoices = MockCollection()
        self.grns = MockCollection()
        self.payments = MockCollection()
        self.counters = MockCollection()
        self.clients = MockCollection()
        self.packing_cartons = MockCollection()
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


def test_decorate_invoice_awaiting_grn():
    """When no GRN has been recorded, due_date is None and grn_recorded is False."""
    doc = {
        "_id": ObjectId(),
        "invoice_no": "SSK26-27-100",
        "invoice_date": "16/08/2026",
        "grand_total": 50000.0,
        "payment_terms_days": 45,
    }
    decorated = _decorate_invoice(doc)
    assert decorated["due_date"] is None
    assert decorated["grn_date"] is None
    assert decorated["grn_recorded"] is False
    assert decorated["status"] == "pending"
    assert decorated["days_to_due"] is None


def test_decorate_invoice_with_grn():
    """When GRN date is recorded, due date is 45 days after GRN date."""
    grn_date = "2026-08-20"
    doc = {
        "_id": ObjectId(),
        "invoice_no": "SSK26-27-101",
        "invoice_date": "16/08/2026",
        "grn_date": grn_date,
        "grn_no": "GRN-2026-0001",
        "grand_total": 50000.0,
        "payment_terms_days": 45,
    }
    decorated = _decorate_invoice(doc)
    assert decorated["grn_recorded"] is True
    assert decorated["grn_date"] == grn_date
    # 2026-08-20 + 45 days = 2026-10-04
    expected_due = (datetime.strptime(grn_date, "%Y-%m-%d") + timedelta(days=45)).date().isoformat()
    assert decorated["due_date"] == expected_due
    assert decorated["due_date"] == "2026-10-04"


@pytest.mark.anyio
async def test_grn_creation_and_due_date_update(mock_db, mock_user_override, async_client):
    """Creating a GRN calculates and updates the invoice due_date to grn_date + 45 days."""
    inv_doc = {
        "invoice_no": "SSK26-27-102",
        "invoice_date": "16/08/2026",
        "invoice_iso_date": "2026-08-16",
        "due_date": None,
        "grn_date": None,
        "grn_recorded": False,
        "payment_terms_days": 45,
        "po_number": "PO-SIYARAM-001",
        "client_name": "SIYARAM SILK MILLS LTD.",
        "grand_total": 85680.0,
        "line_items_snapshot": [
            {
                "style_code": "STYLE-1",
                "color": "Black",
                "size": "8",
                "quantity": 100,
                "unit_price": 856.8,
            }
        ],
    }
    res = await mock_db.invoices.insert_one(inv_doc)
    inv_id = str(res.inserted_id)

    # 1. Post a GRN with grn_date = 2026-08-20
    grn_payload = {
        "invoice_id": inv_id,
        "grn_date": "2026-08-20",
        "client_reference": "SIYARAM/GRN/2026/089",
        "notes": "Goods received in full",
        "line_items": [
            {
                "style_code": "STYLE-1",
                "color": "Black",
                "size": "8",
                "dispatched_qty": 100,
                "received_qty": 100,
                "accepted_qty": 100,
                "rejected_qty": 0,
            }
        ],
    }
    r = await async_client.post("/api/grns", json=grn_payload)
    assert r.status_code == 200, f"Error: {r.text}"
    grn_data = r.json()
    grn_id = grn_data["id"]

    # 2. Check updated invoice in DB
    updated_inv = await mock_db.invoices.find_one({"_id": oid(inv_id)})
    assert updated_inv["grn_recorded"] is True
    assert updated_inv["grn_date"] == "2026-08-20"
    assert updated_inv["due_date"] == "2026-10-04"

    # 3. GET /api/invoices and check decorated response
    r_list = await async_client.get("/api/invoices")
    assert r_list.status_code == 200
    invoices = r_list.json()
    matched = next((i for i in invoices if i["id"] == inv_id), None)
    assert matched is not None
    assert matched["due_date"] == "2026-10-04"
    assert matched["grn_date"] == "2026-08-20"
    assert matched["grn_recorded"] is True

    # 4. Delete GRN and verify invoice due_date is reset
    r_del = await async_client.delete(f"/api/grns/{grn_id}")
    assert r_del.status_code == 200

    inv_after_del = await mock_db.invoices.find_one({"_id": oid(inv_id)})
    assert inv_after_del["grn_recorded"] is False
    assert inv_after_del["grn_date"] is None
    assert inv_after_del["due_date"] is None


@pytest.mark.anyio
async def test_cash_forecast_endpoint(mock_db, mock_user_override, async_client):
    """Verify /api/invoices/cash-forecast returns weekly buckets, exact dates and awaiting GRN."""
    # Invoice 1 with GRN (due in ~45 days)
    await mock_db.invoices.insert_one({
        "invoice_no": "SSK26-27-010",
        "invoice_date": "10/08/2026",
        "due_date": "2026-09-24",
        "grn_date": "2026-08-10",
        "grn_recorded": True,
        "payment_terms_days": 45,
        "client_name": "SIYARAM SILK MILLS LTD.",
        "grand_total": 125000.0,
    })
    # Invoice 2 awaiting GRN
    await mock_db.invoices.insert_one({
        "invoice_no": "SSK26-27-011",
        "invoice_date": "16/08/2026",
        "due_date": None,
        "grn_date": None,
        "grn_recorded": False,
        "payment_terms_days": 45,
        "client_name": "RELIANCE RETAIL",
        "grand_total": 50000.0,
    })

    r = await async_client.get("/api/invoices/cash-forecast")
    assert r.status_code == 200
    data = r.json()
    assert "total_scheduled" in data
    assert data["total_scheduled"] == 125000.0
    assert data["awaiting_grn"]["total_amount"] == 50000.0
    assert data["awaiting_grn"]["invoice_count"] == 1
    assert len(data["by_date"]) == 1
    assert data["by_date"][0]["date"] == "2026-09-24"
    assert data["by_date"][0]["total_amount"] == 125000.0
    assert len(data["weeks"]) > 0
