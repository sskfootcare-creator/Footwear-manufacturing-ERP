"""
Tests for GET /api/b2b-profitability endpoint & rollups logic:
- Per-line profit calculation: unit_price - bom_cost - labor_cost - packing_cost
- Rollup consistency: sum(by_client) == sum(by_style) == summary total
- Actual vs Estimated labor separation (confirmed_profit vs estimated_profit)
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import get_b2b_profitability, compute_po_profitability


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction):
        return self

    async def to_list(self, limit):
        return self._docs


class _Jobs:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query):
        matching = []
        for j in self._docs:
            if "$or" in query:
                for cond in query["$or"]:
                    if "style_id" in cond and j.get("style_id") == cond["style_id"]:
                        matching.append(j)
                        break
                    if "style_code" in cond and j.get("style_code") == cond["style_code"]:
                        matching.append(j)
                        break
            elif query.get("style_id") == j.get("style_id") or query.get("style_code") == j.get("style_code"):
                matching.append(j)
        return _Cursor(matching)


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query=None, projection=None):
        return _Cursor(self._docs)


class _DB:
    def __init__(self, invoices=None, pos=None, styles=None, jobs=None):
        self.invoices = _Collection(invoices or [])
        self.pos = _Collection(pos or [])
        self.styles = _Collection(styles or [])
        self.production_jobs = _Jobs(jobs or [])


class _Request:
    def __init__(self):
        self.state = type("State", (), {"user": {"email": "admin@example.com", "role": "admin"}})()


def test_b2b_profitability_rollups_and_labor_split():
    styles = [
        {
            "_id": "style_actual_id",
            "code": "STYLE_ACTUAL",
            "name": "Actual Production Style",
            "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Stitching", "rate": 30.0}],
            "packing_cost": 10.0,
            "overhead_pct": 0,
            "margin_pct": 0,
            "gst_pct": 0,
        },
        {
            "_id": "style_est_id",
            "code": "STYLE_ESTIMATED",
            "name": "Brand New Style",
            "bom": [{"rate": 80.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Cutting", "rate": 20.0}],
            "packing_cost": 5.0,
            "overhead_pct": 0,
            "margin_pct": 0,
            "gst_pct": 0,
        },
    ]

    jobs = [
        {
            "style_id": "style_actual_id",
            "style_code": "STYLE_ACTUAL",
            "assignments": {
                "cutting": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 15.0},
                "stitching": {"worker_id": "w2", "worker_name": "Suresh", "rate_per_pair": 25.0},
            },
        }
    ]

    invoices = [
        {
            "_id": "inv_1",
            "invoice_no": "INV-2026-001",
            "invoice_date": "2026-08-01",
            "po_number": "PO-101",
            "client_name": "Client Alpha",
            "line_items_snapshot": [
                {
                    "style_code": "STYLE_ACTUAL",
                    "quantity": 100,
                    "unit_price": 200.0,
                }
            ],
        },
        {
            "_id": "inv_2",
            "invoice_no": "INV-2026-002",
            "invoice_date": "2026-08-05",
            "po_number": "PO-102",
            "client_name": "Client Beta",
            "line_items_snapshot": [
                {
                    "style_code": "STYLE_ESTIMATED",
                    "quantity": 50,
                    "unit_price": 150.0,
                }
            ],
        },
    ]

    db = _DB(invoices=invoices, styles=styles, jobs=jobs)
    req = _Request()

    async def _run():
        return await get_b2b_profitability(
            request=req,
            date_from="2026-08-01",
            date_to="2026-08-31",
            db_override=db,
        )

    res = asyncio.run(_run())

    summary = res["summary"]
    by_client = res["by_client"]
    by_style = res["by_style"]
    lines = res["lines"]

    # 1. Spot check per-line calculations:
    # Line 1 (STYLE_ACTUAL):
    # unit_price = 200, bom = 100, actual labor = 15+25=40, packing = 10 -> total unit cost = 150
    # unit profit = 50. Total profit for 100 pairs = 5000.
    line_actual = next(l for l in lines if l["style_code"] == "STYLE_ACTUAL")
    assert line_actual["unit_price"] == 200.0
    assert line_actual["bom_cost"] == 100.0
    assert line_actual["labor_cost"] == 40.0
    assert line_actual["packing_cost"] == 10.0
    assert line_actual["unit_total_cost"] == 150.0
    assert line_actual["line_revenue"] == 20000.0
    assert line_actual["line_profit"] == 5000.0
    assert line_actual["is_estimated"] is False
    assert line_actual["labor_source"] == "actual"

    # Line 2 (STYLE_ESTIMATED):
    # unit_price = 150, bom = 80, estimated labor = 20, packing = 5 -> total unit cost = 105
    # unit profit = 45. Total profit for 50 pairs = 2250.
    line_est = next(l for l in lines if l["style_code"] == "STYLE_ESTIMATED")
    assert line_est["unit_price"] == 150.0
    assert line_est["bom_cost"] == 80.0
    assert line_est["labor_cost"] == 20.0
    assert line_est["packing_cost"] == 5.0
    assert line_est["unit_total_cost"] == 105.0
    assert line_est["line_revenue"] == 7500.0
    assert line_est["line_profit"] == 2250.0
    assert line_est["is_estimated"] is True
    assert line_est["labor_source"] == "estimated"

    # 2. Confirm summary totals & actual vs estimated split:
    assert summary["total_revenue"] == 27500.0
    assert summary["total_profit"] == 7250.0
    assert summary["confirmed_profit"] == 5000.0
    assert summary["confirmed_lines_count"] == 1
    assert summary["estimated_profit"] == 2250.0
    assert summary["estimated_lines_count"] == 1

    # 3. Confirm rollups sum consistency:
    client_profit_sum = sum(c["total_profit"] for c in by_client)
    style_profit_sum = sum(s["total_profit"] for s in by_style)
    assert client_profit_sum == summary["total_profit"]
    assert style_profit_sum == summary["total_profit"]
