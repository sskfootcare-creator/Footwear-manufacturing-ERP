import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import compute_style_costing, compute_po_profitability

def test_compute_style_costing_suggested_target_price():
    style = {
        "bom": [{"item_code": "MAT1", "rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 25.0}],
        "overhead_pct": 10.0,
        "packing_cost": 5.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
    }
    costing = compute_style_costing(style)
    assert costing["materials_cost"] == 100.0
    assert costing["labor_cost"] == 25.0
    # base_cost = 125.0
    assert costing["overhead_cost"] == 12.50
    assert costing["packing_cost"] == 5.0
    assert costing["total_cost"] == 142.50
    assert costing["suggested_margin_amount"] == 28.50
    assert costing["suggested_target_price"] == 171.00

def test_compute_po_profitability_estimated_fallback():
    class MockCursor:
        async def to_list(self, limit):
            return []

    class MockJobs:
        def find(self, query):
            return MockCursor()

    class MockDB:
        production_jobs = MockJobs()

    style_obj = {
        "_id": "60d5ec49f1b2c80015f8a001",
        "code": "SSK_TEST_01",
        "bom": [{"rate": 100.0, "quantity": 1}],
        "labor": [{"name": "Cutting", "rate": 20.0}],
        "packing_cost": 10.0,
    }
    po_line = {
        "style_code": "SSK_TEST_01",
        "unit_price": 200.0,
    }

    async def run():
        return await compute_po_profitability(po_line, style_obj, MockDB())

    result = asyncio.run(run())
    assert result["is_estimated"] is True
    assert result["labor_source"] == "estimated"
    assert result["bom_cost"] == 100.0
    assert result["labor_cost"] == 20.0
    assert result["packing_cost"] == 10.0
    # profit = 200 - 100 - 20 - 10 = 70.0
    assert result["profit"] == 70.0
    # profit_pct = (70 / 200) * 100 = 35.0%
    assert result["profit_pct"] == 35.0

def test_compute_po_profitability_actual_job_assignments():
    class MockCursor:
        async def to_list(self, limit):
            return [
                {
                    "assignments": {
                        "cutting": {"rate_per_pair": 15.0},
                        "stitching": {"rate_per_pair": 25.0},
                    }
                }
            ]

    class MockJobs:
        def find(self, query):
            return MockCursor()

    class MockDB:
        production_jobs = MockJobs()

    style_obj = {
        "_id": "60d5ec49f1b2c80015f8a001",
        "code": "SSK_TEST_01",
        "bom": [{"rate": 100.0, "quantity": 1}],
        "labor": [{"name": "Cutting", "rate": 20.0}],
        "packing_cost": 10.0,
    }
    po_line = {
        "style_code": "SSK_TEST_01",
        "unit_price": 200.0,
    }

    async def run():
        return await compute_po_profitability(po_line, style_obj, MockDB())

    result = asyncio.run(run())
    assert result["is_estimated"] is False
    assert result["labor_source"] == "actual"
    # actual labor = 15 + 25 = 40.0
    assert result["labor_cost"] == 40.0
    # profit = 200 - 100 - 40 - 10 = 50.0
    assert result["profit"] == 50.0
    # profit_pct = (50 / 200) * 100 = 25.0%
    assert result["profit_pct"] == 25.0
