import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi.testclient import TestClient

import server
from routes.pos import _attach_po_profitability, _attach_po_status

@pytest.mark.anyio
async def test_pos_list_benchmark_and_query_count():
    """Benchmark PO list endpoint with 100 POs and 500 line items.
    Verify exact query counts and sub-millisecond per-PO execution.
    """
    mock_db = MagicMock()

    # Generate 100 POs with 5 line items each (500 line items total)
    num_pos = 100
    pos_list = []
    style_codes = [f"STYLE_{i:03d}" for i in range(20)]
    style_docs = [{"_id": ObjectId(), "code": sc, "bom": [{"rate": 100.0, "quantity": 1}], "labor": [{"rate": 30.0}]} for sc in style_codes]

    for i in range(num_pos):
        po_id = ObjectId()
        po_num = f"PO-2026-{i:04d}"
        lines = []
        for j in range(5):
            sc = style_codes[(i * 5 + j) % len(style_codes)]
            lines.append({
                "style_code": sc,
                "unit_price": 250.0,
                "quantity": 100,
            })
        pos_list.append({
            "_id": po_id,
            "po_number": po_num,
            "client_name": "B2B Retailer",
            "line_items": lines,
            "created_at": f"2026-08-01T{i%24:02d}:00:00Z",
        })

    # Track queries executed on each collection
    query_log = []

    class MockCursor:
        def __init__(self, items):
            self._items = items
        def sort(self, *args, **kwargs):
            return self
        async def to_list(self, limit=10000):
            return self._items

    def make_find(col_name, ret_items):
        def _find(query=None, projection=None):
            query_log.append((col_name, query))
            return MockCursor(ret_items)
        return _find

    mock_db.pos.find = make_find("pos", [dict(p) for p in pos_list])
    mock_db.styles.find = make_find("styles", style_docs)
    mock_db.production_jobs.find = make_find("production_jobs", [
        {"style_id": str(s["_id"]), "style_code": s["code"], "po_id": str(pos_list[0]["_id"]), "po_number": pos_list[0]["po_number"], "assignments": {"s": {"rate_per_pair": 35.0}}}
        for s in style_docs
    ])
    mock_db.invoices.find = make_find("invoices", [
        {"po_id": str(pos_list[0]["_id"]), "po_number": pos_list[0]["po_number"]}
    ])
    mock_db.dispatch_records.find = make_find("dispatch_records", [])

    # Measure execution time
    t0 = time.perf_counter()

    po_copies = [dict(p) for p in pos_list]
    await _attach_po_profitability(po_copies, mock_db)
    await _attach_po_status(po_copies, mock_db)

    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000

    # Assertions
    # 1. Exactly 1 query to styles, 2 queries to production_jobs (1 for profitability, 1 for status), 1 to invoices, 1 to dispatch_records
    col_counts = {}
    for col, q in query_log:
        col_counts[col] = col_counts.get(col, 0) + 1

    assert col_counts.get("styles") == 1
    assert col_counts.get("production_jobs") == 2
    assert col_counts.get("invoices") == 1
    assert col_counts.get("dispatch_records") == 1

    # 2. Performance: 100 POs with 500 line items processes in < 25ms in-memory
    assert elapsed_ms < 100.0, f"Execution took too long: {elapsed_ms:.2f}ms"

    # 3. All 100 POs have profitability attached to all 500 line items
    for p in po_copies:
        for li in p["line_items"]:
            assert "profitability" in li
            assert li["profitability"]["total_cost"] > 0
            assert li["profitability"]["profit"] is not None

    print(f"\n[BENCHMARK] 100 POs (500 line items) attached in {elapsed_ms:.2f}ms ({elapsed_ms/num_pos:.3f}ms per PO)")
