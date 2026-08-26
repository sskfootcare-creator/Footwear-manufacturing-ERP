import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.vendors import vendors_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        return self

    async def to_list(self, limit):
        return self.docs


class MockVendorsDB:
    def __init__(self):
        self.vendors_store = {}
        self.vendor_pos_store = {}
        self.receives_store = []
        self.payments_store = []
        self.movements_store = []
        self.materials_store = {}
        self.counters_store = {"payment_seq": {"v": 10}, "vendor_po_seq": {"v": 20}}
        self.audit_logs_store = []

        self.vendors = MagicMock()
        self.vendors.find = MagicMock(side_effect=self._find_vendors)
        self.vendors.find_one = AsyncMock(side_effect=self._find_one_vendor)
        self.vendors.insert_one = AsyncMock(side_effect=self._insert_vendor)
        self.vendors.update_one = AsyncMock(side_effect=self._update_vendor)

        self.vendor_purchase_orders = MagicMock()
        self.vendor_purchase_orders.find = MagicMock(side_effect=self._find_vendor_pos)
        self.vendor_purchase_orders.find_one = AsyncMock(side_effect=self._find_one_vendor_po)
        self.vendor_purchase_orders.insert_one = AsyncMock(side_effect=self._insert_vendor_po)
        self.vendor_purchase_orders.update_one = AsyncMock(side_effect=self._update_vendor_po)
        self.vendor_purchase_orders.delete_one = AsyncMock(side_effect=self._delete_vendor_po)

        self.vendor_po_receives = MagicMock()
        self.vendor_po_receives.find = MagicMock(return_value=MockCursor([]))
        self.vendor_po_receives.insert_one = AsyncMock(side_effect=self._insert_receive)

        self.payments = MagicMock()
        self.payments.find = MagicMock(return_value=MockCursor([]))
        self.payments.insert_one = AsyncMock(side_effect=self._insert_payment)

        self.inventory_movements = MagicMock()
        self.inventory_movements.find = MagicMock(return_value=MockCursor([]))
        self.inventory_movements.insert_many = AsyncMock(return_value=MagicMock(inserted_ids=["mov1"]))

        self.materials = MagicMock()
        self.materials.find = MagicMock(side_effect=self._find_materials)
        self.materials.find_one = AsyncMock(return_value=None)
        self.materials.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

        self.counters = MagicMock()
        self.counters.find_one_and_update = AsyncMock(side_effect=self._inc_counter)

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit1"))

    def _find_vendors(self, query=None):
        return MockCursor(list(self.vendors_store.values()))

    async def _find_one_vendor(self, query):
        oid_str = str(query.get("_id"))
        return self.vendors_store.get(oid_str)

    async def _insert_vendor(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.vendors_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_vendor(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.vendors_store:
            self.vendors_store[oid_str].update(update.get("$set", {}))
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    def _find_vendor_pos(self, query=None):
        return MockCursor(list(self.vendor_pos_store.values()))

    async def _find_one_vendor_po(self, query):
        oid_str = str(query.get("_id"))
        return self.vendor_pos_store.get(oid_str)

    async def _insert_vendor_po(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.vendor_pos_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_vendor_po(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.vendor_pos_store:
            self.vendor_pos_store[oid_str].update(update.get("$set", {}))
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def _delete_vendor_po(self, query):
        oid_str = str(query.get("_id"))
        if oid_str in self.vendor_pos_store:
            self.vendor_pos_store.pop(oid_str)
            return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    async def _insert_receive(self, doc):
        self.receives_store.append(doc)
        return MagicMock(inserted_id="rec1")

    async def _insert_payment(self, doc):
        self.payments_store.append(doc)
        return MagicMock(inserted_id="pay1")

    def _find_materials(self, query=None):
        return MockCursor(list(self.materials_store.values()))

    async def _inc_counter(self, query, update, upsert=False, return_document=True):
        cid = query.get("_id")
        if cid not in self.counters_store:
            self.counters_store[cid] = {"v": 0}
        self.counters_store[cid]["v"] += 1
        return self.counters_store[cid]


@pytest.fixture
def mock_vendors_env(monkeypatch):
    mock_db = MockVendorsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User"
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_vendors_env):
    test_app = FastAPI()
    test_app.include_router(vendors_router)
    test_app.mongodb = mock_vendors_env
    return TestClient(test_app)


def test_vendor_crud_and_aging(client, mock_vendors_env):
    # 1. Create Vendor
    res = client.post("/api/vendors", json={
        "name": "Apex Leather Corp",
        "gstin": "07AAAAA0000A1Z5",
        "contact_person": "Vikram Singh",
        "phone": "9811122233",
        "address": "Agra Industrial Area",
        "payment_terms_days": 30,
        "active": True
    })
    assert res.status_code == 201
    vdata = res.json()
    assert vdata["name"] == "Apex Leather Corp"
    vid = vdata["id"]

    # 2. Get Vendor
    res = client.get(f"/api/vendors/{vid}")
    assert res.status_code == 200
    assert res.json()["name"] == "Apex Leather Corp"

    # 3. List Vendors
    res = client.get("/api/vendors")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 4. Patch Vendor
    res = client.patch(f"/api/vendors/{vid}", json={"phone": "9811199999"})
    assert res.status_code == 200
    assert res.json()["phone"] == "9811199999"

    # 5. Vendor Ledger & Ageing
    res = client.get(f"/api/vendors/{vid}/ledger")
    assert res.status_code == 200
    assert res.json()["vendor_id"] == vid
    assert res.json()["current_balance"] == 0.0

    res = client.get("/api/vendors/ageing")
    assert res.status_code == 200
    assert "summary" in res.json()
    assert "vendors" in res.json()

    # 6. Create Vendor Payment
    res = client.post(f"/api/vendors/{vid}/payments", json={
        "amount": 25000.0,
        "payment_date": "2026-08-26",
        "mode": "NEFT",
        "reference": "UTR12345678"
    })
    assert res.status_code == 201
    assert res.json()["amount"] == 25000.0
    assert res.json()["payment_no"].startswith("RCT-")

    # 7. Delete (Deactivate) Vendor
    res = client.delete(f"/api/vendors/{vid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_vendor_po_flow(client, mock_vendors_env):
    # Setup vendor and material
    vid = str(ObjectId())
    mid = str(ObjectId())
    mock_vendors_env.vendors_store[vid] = {
        "_id": ObjectId(vid),
        "name": "Sole Material Supply",
        "active": True
    }
    mock_vendors_env.materials_store[mid] = {
        "_id": ObjectId(mid),
        "code": "TPR-BLK-01",
        "name": "TPR Sole Black",
        "unit": "prs",
        "rate": 120.0
    }

    # 1. Create Vendor PO
    res = client.post("/api/vendor-pos", json={
        "vendor_id": vid,
        "line_items": [
            {
                "material_id": mid,
                "quantity": 100.0,
                "rate": 120.0,
                "amount": 12000.0,
                "received_quantity": 0.0
            }
        ],
        "status": "draft",
        "expected_delivery_date": "2026-09-01",
        "notes": "Urgent delivery"
    })
    assert res.status_code == 201
    po = res.json()
    assert po["po_number"].startswith("PO-VEN-")
    poid = po["id"]

    # 2. Get Vendor PO
    res = client.get(f"/api/vendor-pos/{poid}")
    assert res.status_code == 200
    assert res.json()["vendor_name"] == "Sole Material Supply"

    # 3. Update Vendor PO
    res = client.patch(f"/api/vendor-pos/{poid}", json={"status": "sent"})
    assert res.status_code == 200
    assert res.json()["status"] == "sent"

    # 4. Receive materials against Vendor PO
    res = client.post(f"/api/vendor-pos/{poid}/receive", json={
        "receipt_id": "REC-001",
        "receipt_date": "2026-08-26",
        "items": [
            {
                "material_id": mid,
                "quantity": 50.0
            }
        ]
    })
    assert res.status_code == 200
    rec_po = res.json()
    assert rec_po["status"] == "partially_received"
    assert rec_po["line_items"][0]["received_quantity"] == 50.0

    # 5. Delete Vendor PO
    res = client.delete(f"/api/vendor-pos/{poid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True
