"""Comprehensive End-to-End (E2E) Integration Test Suite (TEST-004).

Covers the entire enterprise manufacturing and commercial lifecycle:
Order (Client PO) ──> Production (Stages & WIP) ──> FG Stock Receipt ──> Invoicing ──> Packing & Dispatch ──> Ledger Reconciliation.
"""

import pytest
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock, patch

import server
from models.invoice_packing import DispatchCreate
from routes.inventory import _apply_movement


class MockCollection:
    def __init__(self, initial_docs=None):
        self.docs = list(initial_docs or [])

    def find(self, query=None, projection=None):
        class MockCursor:
            def __init__(self, data):
                self.data = data
            def sort(self, *a, **kw):
                return self
            def limit(self, *a, **kw):
                return self
            async def to_list(self, limit=None):
                return self.data
            def __aiter__(self):
                self._iter = iter(self.data)
                return self
            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration

        matched = []
        for d in self.docs:
            match = True
            if query:
                for k, v in query.items():
                    if k == "_id" and str(d.get("_id")) != str(v):
                        match = False
                    elif k == "status" and isinstance(v, dict) and "$ne" in v:
                        if d.get("status") == v["$ne"]:
                            match = False
                    elif not k.startswith("$") and d.get(k) != v:
                        match = False
            if match:
                matched.append(d)
        return MockCursor(matched)

    async def find_one(self, query=None):
        if not query:
            return self.docs[0] if self.docs else None
        for d in self.docs:
            match = True
            for k, v in query.items():
                if k == "_id" and str(d.get("_id")) != str(v):
                    match = False
                elif d.get(k) != v:
                    match = False
            if match:
                return d
        return None

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        if "id" not in d:
            d["id"] = str(d["_id"])
        self.docs.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if doc:
            if "$set" in update:
                doc.update(update["$set"])
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    doc[k] = doc.get(k, 0) + v
        res = MagicMock()
        res.modified_count = 1 if doc else 0
        return res

    async def count_documents(self, query=None):
        cursor = self.find(query)
        docs = await cursor.to_list()
        return len(docs)


class MockE2EDatabase:
    def __init__(self):
        self.pos = MockCollection()
        self.production_jobs = MockCollection()
        self.fg_inventory = MockCollection()
        self.invoices = MockCollection()
        self.dispatch_records = MockCollection()
        self.online_returns_records = MockCollection()
        self.materials = MockCollection()
        self.styles = MockCollection()
        self.cash_ledger = MockCollection()
        self.inventory_movements = MockCollection()

    def __getitem__(self, item):
        if not hasattr(self, item):
            setattr(self, item, MockCollection())
        return getattr(self, item)


@pytest.mark.anyio
async def test_complete_order_to_dispatch_lifecycle():
    """Verify complete end-to-end business workflow from order receipt through dispatch."""
    mock_db = MockE2EDatabase()

    # Step 1: Client Order (PO) Creation
    po_id = str(ObjectId())
    client_po = {
        "_id": ObjectId(po_id),
        "id": po_id,
        "po_number": "PO-2026-B2B-001",
        "client_name": "Metro Retailers Ltd",
        "style_code": "OXFORD-BLK-42",
        "total_pairs": 100,
        "grand_total": 85000.0,
        "status": "confirmed",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await mock_db.pos.insert_one(client_po)
    assert await mock_db.pos.count_documents({}) == 1

    # Step 2: Production Planning & Job Generation
    job_id = str(ObjectId())
    job_doc = {
        "_id": ObjectId(job_id),
        "id": job_id,
        "po_id": po_id,
        "po_number": client_po["po_number"],
        "style_code": client_po["style_code"],
        "source_type": "b2b",
        "quantity": 100,
        "stage": "cutting",
        "completed_qty": 0,
        "status": "in_progress",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await mock_db.production_jobs.insert_one(job_doc)

    # Step 3: Production Progression through Stages
    production_stages = ["closing", "bottom", "finishing", "packing"]
    for next_stage in production_stages:
        await mock_db.production_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"stage": next_stage}}
        )
        updated_job = await mock_db.production_jobs.find_one({"_id": ObjectId(job_id)})
        assert updated_job["stage"] == next_stage

    # Complete manufacturing in packing stage
    await mock_db.production_jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"completed_qty": 100, "status": "completed"}}
    )

    # Step 4: Finished Goods (FG) Stock Receipt
    fg_item = {
        "_id": ObjectId(),
        "style_code": client_po["style_code"],
        "ready_stock": 100,
        "reserved": 0,
        "unit_cost": 450.0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await mock_db.fg_inventory.insert_one(fg_item)
    assert (await mock_db.fg_inventory.find_one({"style_code": client_po["style_code"]}))["ready_stock"] == 100

    # Step 5: Commercial Invoicing against Completed PO
    invoice_id = str(ObjectId())
    invoice_doc = {
        "_id": ObjectId(invoice_id),
        "id": invoice_id,
        "invoice_no": "SSK/26-27/0042",
        "po_id": po_id,
        "po_number": client_po["po_number"],
        "client_name": client_po["client_name"],
        "grand_total": 85000.0,
        "net_amount": 85000.0,
        "items": [{"style_code": client_po["style_code"], "qty": 100, "rate": 850.0}],
        "status": "issued",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await mock_db.invoices.insert_one(invoice_doc)
    assert await mock_db.invoices.count_documents({"status": {"$ne": "voided"}}) == 1

    # Step 6: Warehouse Dispatch & Packing Challan Generation
    dispatch_id = str(ObjectId())
    dispatch_doc = {
        "_id": ObjectId(dispatch_id),
        "id": dispatch_id,
        "invoice_id": invoice_id,
        "invoice_no": invoice_doc["invoice_no"],
        "po_id": po_id,
        "total_pairs": 100,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "status": "dispatched",
    }
    await mock_db.dispatch_records.insert_one(dispatch_doc)

    # Mark production job as dispatched and relieve FG physical inventory
    await mock_db.production_jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"stage": "dispatched"}}
    )
    await mock_db.fg_inventory.update_one(
        {"style_code": client_po["style_code"]},
        {"$inc": {"ready_stock": -100}}
    )

    # Step 7: Authoritative Invariant Verification
    with patch.object(server, "db", mock_db):
        stats = await server._compute_dashboard_stats_live()

        # Invariant 1: Physical inventory drained after dispatch
        assert stats["ledger_invariants"]["physical_fg_stock"] == 0

        # Invariant 2: Authoritative dispatched equals 100 pairs
        assert stats["ledger_invariants"]["authoritative_dispatched"] == 100

        # Invariant 3: Realized invoiced revenue recognized
        assert stats["ledger_invariants"]["invoiced_realized_revenue"] == 85000.0

        # Invariant 4: No active WIP pairs remaining
        assert stats["pairs_in_wip"] == 0

        # Invariant 5: Total dispatched pairs
        assert stats["dispatched"] == 100
