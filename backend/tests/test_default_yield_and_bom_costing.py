"""
Tests for:
- compute_style_costing with BOM-only (no labor) styles
- default_yield_per_unit fallback in BOM costing
- compute_po_profitability with negotiated unit_price
- PO profitability for a BOM-only/no-labor style
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import compute_po_profitability, compute_style_costing


# ---------------------------------------------------------------------------
# Helpers — minimal mock DB that returns job lists synchronously
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, limit):
        return self._docs


class _Jobs:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query):
        return _Cursor(self._docs)


class _DB:
    def __init__(self, jobs=None):
        self.production_jobs = _Jobs(jobs or [])


# ---------------------------------------------------------------------------
# 1. BOM-only style, no labor — cost sheet clarity
# ---------------------------------------------------------------------------

def test_bom_only_no_labor_costing():
    """Style with materials but NO labor: labor_is_set should be False and
    labor_cost should be 0. total_cost must still be correct."""
    style = {
        "bom": [
            {"rate": 200.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0},
            {"rate": 50.0,  "quantity": 2, "yield_per_unit": 1, "waste_pct": 0},
        ],
        "labor": [],           # ← no labor operations
        "overhead_pct": 10.0,
        "packing_cost": 15.0,
        "margin_pct": 25.0,
        "gst_pct": 5.0,
    }
    c = compute_style_costing(style)

    # Materials: 200 + (50*2) = 300
    assert c["materials_cost"] == 300.0
    # No labor
    assert c["labor_cost"] == 0.0
    assert c["labor_is_set"] is False
    # base_cost = 300 (labor excluded when not set)
    # overhead = 300 * 10% = 30
    assert c["overhead_cost"] == 30.0
    assert c["packing_cost"] == 15.0
    # total = 300 + 30 + 15 = 345
    assert c["total_cost"] == 345.0
    # margin = 345 * 25% = 86.25
    assert c["suggested_margin_amount"] == 86.25
    assert c["suggested_target_price"] == 431.25


def test_bom_only_no_labor_costing_save():
    """Saving a BOM-only style (labor=[]) must not raise — the function must
    return a well-formed dict with all required keys."""
    style = {
        "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [],
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    result = compute_style_costing(style)
    required_keys = {
        "materials_cost", "labor_cost", "labor_is_set",
        "overhead_cost", "packing_cost", "total_cost",
        "suggested_margin_amount", "suggested_target_price",
        "gst_amount", "suggested_target_price_with_gst",
    }
    assert required_keys.issubset(result.keys()), (
        f"Missing keys: {required_keys - result.keys()}"
    )
    assert result["labor_is_set"] is False
    assert result["total_cost"] == 100.0


# ---------------------------------------------------------------------------
# 2. default_yield_per_unit fallback
# ---------------------------------------------------------------------------

def test_default_yield_applied_when_no_explicit_yield():
    """BOM line with no explicit yield_per_unit but a default_yield_per_unit
    on the line (backend embeds it) should use the default, not 1.0."""
    style = {
        "bom": [
            {
                "rate": 100.0,
                "quantity": 1,
                # no "yield_per_unit" key — simulates backend not storing it
                "default_yield_per_unit": 2.0,
                "waste_pct": 0,
            }
        ],
        "labor": [],
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    c = compute_style_costing(style)
    # cost = rate * qty / yield = 100 * 1 / 2 = 50
    assert c["materials_cost"] == 50.0


def test_explicit_yield_overrides_default():
    """When both yield_per_unit and default_yield_per_unit are set, the
    explicit per-line yield_per_unit takes precedence."""
    style = {
        "bom": [
            {
                "rate": 100.0,
                "quantity": 1,
                "yield_per_unit": 4.0,           # explicit override
                "default_yield_per_unit": 2.0,   # should be ignored
                "waste_pct": 0,
            }
        ],
        "labor": [],
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    c = compute_style_costing(style)
    # cost = 100 * 1 / 4 = 25 (uses explicit yield=4, not default=2)
    assert c["materials_cost"] == 25.0


def test_fallback_to_one_when_no_yield():
    """When neither yield_per_unit nor default_yield_per_unit is present,
    the function must fall back to 1.0 (not raise)."""
    style = {
        "bom": [{"rate": 80.0, "quantity": 1, "waste_pct": 0}],
        "labor": [],
        "overhead_pct": 0,
        "packing_cost": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    c = compute_style_costing(style)
    # cost = 80 * 1 / 1 = 80
    assert c["materials_cost"] == 80.0


# ---------------------------------------------------------------------------
# 3. PO profitability — negotiated unit_price, correct profit + label
# ---------------------------------------------------------------------------

def test_po_profitability_negotiated_price_estimated():
    """PO line with a negotiated unit_price and no actual job data falls back
    to estimated labor from style.labor[]. Profit = price - bom - labor - packing."""
    style_obj = {
        "_id": "style001",
        "code": "SSK_001",
        "bom": [{"rate": 150.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 30.0}, {"name": "Cutting", "rate": 20.0}],
        "packing_cost": 10.0,
        "overhead_pct": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    po_line = {
        "style_code": "SSK_001",
        "unit_price": 250.0,
    }

    async def _run():
        return await compute_po_profitability(po_line, style_obj, _DB())

    result = asyncio.run(_run())

    assert result["labor_source"] == "estimated"
    assert result["is_estimated"] is True
    assert result["bom_cost"] == 150.0
    assert result["labor_cost"] == 50.0   # 30 + 20
    assert result["packing_cost"] == 10.0
    # profit = 250 - 150 - 50 - 10 = 40
    assert result["profit"] == 40.0
    assert result["profit_pct"] == 16.0   # 40/250 * 100


def test_po_profitability_negotiated_price_actual():
    """PO line with actual job assignment data uses real labor rates, not
    the planned rates. labor_source must be 'actual'."""
    style_obj = {
        "_id": "style002",
        "code": "SSK_002",
        "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 30.0}],  # planned — should be ignored
        "packing_cost": 5.0,
        "overhead_pct": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    po_line = {"style_code": "SSK_002", "unit_price": 200.0}

    jobs = [
        {
            "assignments": {
                "cutting":   {"rate_per_pair": 18.0},
                "stitching": {"rate_per_pair": 22.0},
            }
        }
    ]

    async def _run():
        return await compute_po_profitability(po_line, style_obj, _DB(jobs))

    result = asyncio.run(_run())

    assert result["labor_source"] == "actual"
    assert result["is_estimated"] is False
    # actual labor = avg of one job → (18+22) = 40
    assert result["labor_cost"] == 40.0
    # profit = 200 - 100 - 40 - 5 = 55
    assert result["profit"] == 55.0
    assert result["profit_pct"] == 27.5   # 55/200 * 100


def test_po_profitability_bom_only_no_labor():
    """Style with BOM only (labor=[]) — PO profitability must not crash.
    is_estimated=True, labor_cost=0 (no planned rates to fall back to)."""
    style_obj = {
        "_id": "style003",
        "code": "SSK_003",
        "bom": [{"rate": 120.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [],           # ← BOM-only style
        "packing_cost": 8.0,
        "overhead_pct": 0,
        "margin_pct": 0,
        "gst_pct": 0,
    }
    po_line = {"style_code": "SSK_003", "unit_price": 180.0}

    async def _run():
        return await compute_po_profitability(po_line, style_obj, _DB())

    result = asyncio.run(_run())

    assert result["labor_source"] == "estimated"
    assert result["is_estimated"] is True
    assert result["bom_cost"] == 120.0
    assert result["labor_cost"] == 0.0
    assert result["packing_cost"] == 8.0
    assert result["profit"] == 52.0
    assert result["profit_pct"] == pytest.approx(28.9, abs=0.1)
