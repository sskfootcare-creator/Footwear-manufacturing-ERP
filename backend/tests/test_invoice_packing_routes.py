"""Unit & End-to-End Tests for Invoice, Packing List, Carton Labels & Dispatch Domain."""

import io
import zipfile
import base64
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.invoice_packing import (
    invoice_packing_router,
    next_invoice_no,
    _get_max_invoice_seq,
    _compute_invoice_totals,
    _decorate_invoice,
    _extract_credit_days,
    _enrich_cartons_with_mapped_sku,
)
from models.invoice_packing import (
    InvoiceGenerate,
    DispatchCreate,
    PackingListGenerate,
    MergedPackingListGenerate,
    PackingTemplateIn,
)


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def skip(self, count):
        return self

    async def to_list(self, limit=10000):
        return self.docs[:limit]


class MockInvoiceDB:
    def __init__(self):
        self.invoices_store = {}
        self.dispatch_records_store = {}
        self.packing_cartons_store = {}
        self.packing_lists_store = {}
        self.packing_templates_store = {}
        self.sku_ean_codes_store = {}
        self.production_jobs_store = {}
        self.pos_store = {}
        self.counters_store = {}
        self.payments_store = {}
        self.grns_store = {}
        self.settings_store = {}
        self.sku_map_store = {}
        self.audit_logs_store = []

        self.invoices = MagicMock()
        self.invoices.find = MagicMock(side_effect=self._find_invoices)
        self.invoices.find_one = AsyncMock(side_effect=self._find_one_invoice)
        self.invoices.insert_one = AsyncMock(side_effect=self._insert_invoice)
        self.invoices.update_one = AsyncMock(side_effect=self._update_invoice)
        self.invoices.delete_one = AsyncMock(side_effect=self._delete_invoice)

        self.dispatch_records = MagicMock()
        self.dispatch_records.find = MagicMock(side_effect=self._find_dispatches)
        self.dispatch_records.find_one = AsyncMock(side_effect=self._find_one_dispatch)
        self.dispatch_records.insert_one = AsyncMock(side_effect=self._insert_dispatch)
        self.dispatch_records.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))

        self.packing_cartons = MagicMock()
        self.packing_cartons.find = MagicMock(side_effect=self._find_cartons)
        self.packing_cartons.find_one = AsyncMock(side_effect=self._find_one_carton)
        self.packing_cartons.insert_one = AsyncMock(side_effect=self._insert_carton)
        self.packing_cartons.insert_many = AsyncMock(side_effect=self._insert_many_cartons)
        self.packing_cartons.update_one = AsyncMock(side_effect=self._update_carton)
        self.packing_cartons.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
        self.packing_cartons.delete_one = AsyncMock(side_effect=self._delete_carton)
        self.packing_cartons.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))

        self.packing_lists = MagicMock()
        self.packing_lists.find = MagicMock(side_effect=self._find_packing_lists)
        self.packing_lists.find_one = AsyncMock(side_effect=self._find_one_packing_list)
        self.packing_lists.insert_one = AsyncMock(side_effect=self._insert_packing_list)

        self.packing_templates = MagicMock()
        self.packing_templates.find = MagicMock(side_effect=self._find_packing_templates)
        self.packing_templates.find_one = AsyncMock(side_effect=self._find_one_packing_template)
        self.packing_templates.insert_one = AsyncMock(side_effect=self._insert_packing_template)
        self.packing_templates.delete_one = AsyncMock(side_effect=self._delete_packing_template)

        self.sku_ean_codes = MagicMock()
        self.sku_ean_codes.find = MagicMock(side_effect=self._find_ean_codes)
        self.sku_ean_codes.find_one = AsyncMock(side_effect=self._find_one_ean_code)
        self.sku_ean_codes.insert_one = AsyncMock(side_effect=self._insert_ean_code)
        self.sku_ean_codes.update_one = AsyncMock(side_effect=self._update_ean_code)

        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=self._find_jobs)
        self.production_jobs.find_one = AsyncMock(side_effect=self._find_one_job)
        self.production_jobs.update_one = AsyncMock(side_effect=self._update_job)
        self.production_jobs.update_many = AsyncMock(side_effect=self._update_many_jobs)

        self.pos = MagicMock()
        self.pos.find_one = AsyncMock(side_effect=self._find_one_po)
        self.pos.find = MagicMock(side_effect=self._find_pos)
        self.pos.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        self.counters = MagicMock()
        self.counters.find_one = AsyncMock(side_effect=self._find_one_counter)
        self.counters.update_one = AsyncMock(side_effect=self._update_counter)
        self.counters.find_one_and_update = AsyncMock(side_effect=self._find_and_update_counter)

        self.payments = MagicMock()
        self.payments.find = MagicMock(return_value=MockCursor([]))
        self.payments.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))

        self.grns = MagicMock()
        self.grns.find = MagicMock(return_value=MockCursor([]))

        self.settings = MagicMock()
        self.settings.find_one = AsyncMock(return_value=None)

        self.sku_map = MagicMock()
        self.sku_map.find = MagicMock(return_value=MockCursor([]))

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    def _find_invoices(self, q=None, proj=None):
        return MockCursor(list(self.invoices_store.values()))

    async def _find_one_invoice(self, q, proj=None):
        if "_id" in q:
            return self.invoices_store.get(str(q["_id"]))
        if "job_ids" in q:
            for inv in self.invoices_store.values():
                if any(j in (inv.get("job_ids") or []) for j in q["job_ids"].get("$in", [])):
                    return inv
        return None

    async def _insert_invoice(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.invoices_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_invoice(self, match, update):
        oid_str = str(match.get("_id"))
        doc = self.invoices_store.get(oid_str)
        if doc and "$set" in update:
            doc.update(update["$set"])
        return MagicMock(matched_count=1, modified_count=1)

    async def _delete_invoice(self, match):
        oid_str = str(match.get("_id"))
        self.invoices_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_dispatches(self, q=None, proj=None):
        return MockCursor(list(self.dispatch_records_store.values()))

    async def _find_one_dispatch(self, q, proj=None):
        if "_id" in q:
            return self.dispatch_records_store.get(str(q["_id"]))
        return None

    async def _insert_dispatch(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.dispatch_records_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    def _find_cartons(self, q=None):
        docs = list(self.packing_cartons_store.values())
        if q and "job_id" in q:
            if isinstance(q["job_id"], dict) and "$in" in q["job_id"]:
                jids = [str(x) for x in q["job_id"]["$in"]]
                docs = [d for d in docs if str(d.get("job_id")) in jids]
            else:
                docs = [d for d in docs if str(d.get("job_id")) == str(q["job_id"])]
        return MockCursor(docs)

    async def _find_one_carton(self, q):
        if "_id" in q:
            return self.packing_cartons_store.get(str(q["_id"]))
        return None

    async def _insert_carton(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.packing_cartons_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _insert_many_cartons(self, docs):
        ids = []
        for d in docs:
            oid = ObjectId()
            d["_id"] = oid
            self.packing_cartons_store[str(oid)] = d
            ids.append(oid)
        return MagicMock(inserted_ids=ids)

    async def _update_carton(self, match, update):
        oid_str = str(match.get("_id"))
        doc = self.packing_cartons_store.get(oid_str)
        if doc and "$set" in update:
            doc.update(update["$set"])
        return MagicMock(matched_count=1, modified_count=1)

    async def _delete_carton(self, match):
        oid_str = str(match.get("_id"))
        self.packing_cartons_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_packing_lists(self, q=None, proj=None):
        return MockCursor(list(self.packing_lists_store.values()))

    async def _find_one_packing_list(self, q):
        if "_id" in q:
            return self.packing_lists_store.get(str(q["_id"]))
        return None

    async def _insert_packing_list(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.packing_lists_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    def _find_packing_templates(self, q=None, proj=None):
        return MockCursor(list(self.packing_templates_store.values()))

    async def _find_one_packing_template(self, q):
        if "_id" in q:
            return self.packing_templates_store.get(str(q["_id"]))
        return None

    async def _insert_packing_template(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.packing_templates_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _delete_packing_template(self, match):
        oid_str = str(match.get("_id"))
        self.packing_templates_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_ean_codes(self, q=None):
        return MockCursor(list(self.sku_ean_codes_store.values()))

    async def _find_one_ean_code(self, q):
        for doc in self.sku_ean_codes_store.values():
            if doc.get("style_id") == q.get("style_id") and doc.get("size") == q.get("size"):
                return doc
        return None

    async def _insert_ean_code(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.sku_ean_codes_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_ean_code(self, match, update):
        return MagicMock(matched_count=1, modified_count=1)

    def _find_jobs(self, q=None):
        docs = list(self.production_jobs_store.values())
        if q and "_id" in q and "$in" in q["_id"]:
            oids = [str(x) for x in q["_id"]["$in"]]
            docs = [d for d in docs if str(d.get("_id")) in oids]
        return MockCursor(docs)

    async def _find_one_job(self, q):
        if "_id" in q:
            return self.production_jobs_store.get(str(q["_id"]))
        return None

    async def _update_job(self, match, update):
        oid_str = str(match.get("_id"))
        doc = self.production_jobs_store.get(oid_str)
        if doc and "$set" in update:
            doc.update(update["$set"])
        return MagicMock(matched_count=1, modified_count=1)

    async def _update_many_jobs(self, match, update):
        oids = [str(x) for x in match.get("_id", {}).get("$in", [])]
        count = 0
        for o in oids:
            doc = self.production_jobs_store.get(o)
            if doc:
                if "$set" in update:
                    doc.update(update["$set"])
                count += 1
        return MagicMock(modified_count=count)

    async def _find_one_po(self, q):
        if "_id" in q:
            return self.pos_store.get(str(q["_id"]))
        return None

    def _find_pos(self, q=None):
        return MockCursor(list(self.pos_store.values()))

    async def _find_one_counter(self, q):
        return self.counters_store.get(str(q.get("_id")))

    async def _update_counter(self, match, update, upsert=False):
        cid = str(match.get("_id"))
        doc = self.counters_store.setdefault(cid, {"_id": cid, "seq": 0})
        if "$set" in update:
            doc.update(update["$set"])
        return MagicMock(matched_count=1, modified_count=1)

    async def _find_and_update_counter(self, match, update, upsert=False, return_document=True):
        cid = str(match.get("_id"))
        doc = self.counters_store.setdefault(cid, {"_id": cid, "seq": 0})
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        return doc


@pytest.fixture
def mock_invoice_env(monkeypatch):
    mock_db = MockInvoiceDB()
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
def client(mock_invoice_env):
    test_app = FastAPI()
    test_app.include_router(invoice_packing_router)
    test_app.mongodb = mock_invoice_env
    return TestClient(test_app)


def test_invoice_sequence_generation_and_resync(client, mock_invoice_env):
    # 1. Resync invoice sequence
    res = client.post("/api/admin/resync-invoice-sequence")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert "next_invoice_will_be" in body

    # 2. Extract credit days helper
    assert _extract_credit_days("Net 30 days") == 30
    assert _extract_credit_days("Payment in 45 d") == 45
    assert _extract_credit_days("") == 45


def test_end_to_end_dispatch_invoice_carton_flow(client, mock_invoice_env):
    """End-to-end test of the entire QC Pack -> Unified Dispatch -> Invoice -> Carton Label -> ZIP archive flow."""
    # 1. Create a PO
    po_oid = ObjectId()
    poid = str(po_oid)
    mock_invoice_env.pos_store[poid] = {
        "_id": po_oid,
        "po_number": "PO-TEST-001",
        "client_name": "ZECODE BANGALORE",
        "client_address": "Bangalore Depot",
        "client_gstin": "29AAACS6995D2ZX",
        "payment_terms": "30 days",
        "cgst_rate": 6.0,
        "sgst_rate": 6.0,
        "igst_rate": 0.0,
        "line_items": [
            {
                "style_code": "SK-100",
                "color": "Black",
                "size": "40",
                "quantity": 20,
                "unit_price": 500.0,
                "description": "Formal Loafer Black 40",
                "hsn_code": "64029990",
            },
            {
                "style_code": "SK-100",
                "color": "Black",
                "size": "41",
                "quantity": 20,
                "unit_price": 500.0,
                "description": "Formal Loafer Black 41",
                "hsn_code": "64029990",
            }
        ]
    }

    # 2. Create Production Jobs
    job1_oid = ObjectId()
    j1 = str(job1_oid)
    mock_invoice_env.production_jobs_store[j1] = {
        "_id": job1_oid,
        "po_id": poid,
        "po_number": "PO-TEST-001",
        "style_id": "style_sk100",
        "style_code": "SK-100",
        "color": "Black",
        "size": "40",
        "quantity": 20,
        "completed_qty": 20,
        "stage": "qc_pack",
    }

    job2_oid = ObjectId()
    j2 = str(job2_oid)
    mock_invoice_env.production_jobs_store[j2] = {
        "_id": job2_oid,
        "po_id": poid,
        "po_number": "PO-TEST-001",
        "style_id": "style_sk100",
        "style_code": "SK-100",
        "color": "Black",
        "size": "41",
        "quantity": 20,
        "completed_qty": 20,
        "stage": "qc_pack",
    }

    # 3. Pack cartons via /packing/cartons
    res1 = client.post("/api/packing/cartons", json={"job_id": j1, "size": "40", "qty": 20})
    assert res1.status_code == 200, res1.text
    res2 = client.post("/api/packing/cartons", json={"job_id": j2, "size": "41", "qty": 20})
    assert res2.status_code == 200, res2.text
    assert len(mock_invoice_env.packing_cartons_store) == 2

    # 4. Trigger unified dispatch: POST /api/dispatch
    res_dispatch = client.post("/api/dispatch", json={
        "po_id": poid,
        "job_ids": [j1, j2],
        "transport_mode": "Road",
        "vehicle_no": "KA-01-AB-1234",
        "transporter": "VRL Logistics",
        "carton_dim": "60x50x30 CMS",
    })
    assert res_dispatch.status_code == 200, res_dispatch.text
    assert res_dispatch.headers["content-type"] == "application/zip"
    dr_id = res_dispatch.headers.get("X-Dispatch-Record-Id")
    inv_no = res_dispatch.headers.get("X-Invoice-No")
    assert dr_id is not None
    assert inv_no is not None

    # Verify ZIP contents
    zip_bytes = res_dispatch.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        file_list = zf.namelist()
        assert any(f.startswith("Invoice-") and f.endswith(".pdf") for f in file_list)
        assert any(f.startswith("PackingList-") and f.endswith(".xlsx") for f in file_list)
        assert any(f.startswith("CartonLabels-") and f.endswith(".pdf") for f in file_list)
        assert any(f.startswith("CartonList-") and f.endswith(".xlsx") for f in file_list)

    # 5. Verify database updates post-dispatch
    # A. Cartons marked dispatched with sequential box numbers
    cartons = list(mock_invoice_env.packing_cartons_store.values())
    assert all(c["status"] == "dispatched" for c in cartons)
    box_numbers = sorted([c["box_number"] for c in cartons])
    assert box_numbers == [1, 2]

    # B. Jobs marked dispatched
    assert mock_invoice_env.production_jobs_store[j1]["stage"] == "dispatched"
    assert mock_invoice_env.production_jobs_store[j2]["stage"] == "dispatched"

    # C. Invoices collection populated
    assert len(mock_invoice_env.invoices_store) == 1
    inv_doc = list(mock_invoice_env.invoices_store.values())[0]
    assert inv_doc["invoice_no"] == inv_no
    assert inv_doc["grand_total"] == 22400.0  # 40 * 500 = 20,000 + 12% GST = 22,400

    # D. Dispatch records populated
    assert dr_id in mock_invoice_env.dispatch_records_store

    # 6. Test re-downloading files from the dispatch record
    res_inv = client.get(f"/api/dispatch-records/{dr_id}/invoice")
    assert res_inv.status_code == 200
    assert res_inv.headers["content-type"] == "application/pdf"

    res_pl = client.get(f"/api/dispatch-records/{dr_id}/packing-list")
    assert res_pl.status_code == 200

    res_cl = client.get(f"/api/dispatch-records/{dr_id}/carton-labels")
    assert res_cl.status_code == 200

    res_reprint = client.post(f"/api/dispatch-records/{dr_id}/reprint")
    assert res_reprint.status_code == 200
    assert res_reprint.headers["content-type"] == "application/zip"


def test_merged_invoice_flow(client, mock_invoice_env):
    """Test merged invoice generation across jobs from same PO/client."""
    po_oid = ObjectId()
    poid = str(po_oid)
    mock_invoice_env.pos_store[poid] = {
        "_id": po_oid,
        "po_number": "PO-MERGE-01",
        "client_name": "RETAIL CORP",
        "client_address": "Retail Hub",
        "payment_terms": "45 days",
        "cgst_rate": 6.0,
        "sgst_rate": 6.0,
        "igst_rate": 0.0,
        "line_items": [
            {"style_code": "M-1", "color": "Brown", "size": "38", "quantity": 10, "unit_price": 600.0, "description": "M-1 Brown 38"},
            {"style_code": "M-1", "color": "Brown", "size": "39", "quantity": 15, "unit_price": 600.0, "description": "M-1 Brown 39"},
        ]
    }

    j1 = str(ObjectId())
    mock_invoice_env.production_jobs_store[j1] = {
        "_id": ObjectId(j1),
        "po_id": poid,
        "po_number": "PO-MERGE-01",
        "style_code": "M-1",
        "color": "Brown",
        "size": "38",
        "quantity": 10,
        "completed_qty": 10,
        "stage": "qc_pack",
    }
    j2 = str(ObjectId())
    mock_invoice_env.production_jobs_store[j2] = {
        "_id": ObjectId(j2),
        "po_id": poid,
        "po_number": "PO-MERGE-01",
        "style_code": "M-1",
        "color": "Brown",
        "size": "39",
        "quantity": 15,
        "completed_qty": 15,
        "stage": "qc_pack",
    }

    # Merged invoice request
    res = client.post("/api/invoices/merged", json={
        "entries": [{"po_id": poid, "job_ids": [j1, j2]}],
        "transport_mode": "Road",
        "vehicle_no": "KA-50-Z-9999",
        "supply_date": "2026-08-26",
    })
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    assert "X-Invoice-Id" in res.headers

    # Check that invoice doc was created as merged
    inv_id = res.headers["X-Invoice-Id"]
    inv_doc = mock_invoice_env.invoices_store.get(inv_id)
    assert inv_doc is not None
    assert inv_doc["merged"] is True
    assert inv_doc["total_quantity"] == 25
    assert inv_doc["subtotal"] == 15000.0


def test_packing_templates_and_merged_packing_lists(client, mock_invoice_env):
    # 1. Preview packing list
    res_preview = client.post("/api/packing-list/preview", json={
        "po": {
            "po_number": "PO-888",
            "client_name": "Test Client",
            "line_items": [
                {"style_code": "ST-1", "color": "Tan", "size": "39", "quantity": 40}
            ]
        },
        "pcs_per_box": 20
    })
    assert res_preview.status_code == 200
    pdata = res_preview.json()
    assert pdata["grand_total"]["total_pcs"] == 40
    assert pdata["grand_total"]["total_cartons"] == 2

    # 2. Validate packing list
    res_val = client.post("/api/packing-list/validate", json={
        "po": {
            "po_number": "PO-888",
            "line_items": [{"style_code": "ST-1", "quantity": 10}]
        },
        "carton_dim": "60x50x30 CMS"
    })
    assert res_val.status_code == 200
    assert res_val.json()["valid"] is True
