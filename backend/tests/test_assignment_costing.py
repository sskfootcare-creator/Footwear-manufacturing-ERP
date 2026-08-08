"""
Tests for compute_style_costing_async:
- Estimated labor when no production job assignments exist
- Actual labor and recalculated total cost when production job assignments exist
- Assigned roles breakdown
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import compute_style_costing_async


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


def test_style_costing_no_assignments_uses_planned():
    style = {
        "_id": "style_101",
        "code": "SSK_101",
        "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 20.0}, {"name": "Cutting", "rate": 15.0}],
        "overhead_pct": 10.0,
        "packing_cost": 5.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
    }

    async def _run():
        return await compute_style_costing_async(style, _DB([]))

    c = asyncio.run(_run())

    assert c["labor_source"] == "estimated"
    assert c["is_assigned"] is False
    assert c["materials_cost"] == 100.0
    assert c["labor_cost"] == 35.0  # 20 + 15
    # base = 100 + 35 = 135
    # overhead = 135 * 10% = 13.5
    # total = 135 + 13.5 + 5 = 153.5
    assert c["total_cost"] == 153.5


def test_style_costing_with_job_assignments_recalculates_actual_total():
    style = {
        "_id": "style_102",
        "code": "SSK_102",
        "bom": [{"rate": 100.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 20.0}],  # planned = 20.0
        "overhead_pct": 10.0,
        "packing_cost": 5.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
    }

    jobs = [
        {
            "style_id": "style_102",
            "assignments": {
                "cutting": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 18.0},
                "stitching": {"worker_id": "w2", "worker_name": "Suresh", "rate_per_pair": 22.0},
            },
        }
    ]

    async def _run():
        return await compute_style_costing_async(style, _DB(jobs))

    c = asyncio.run(_run())

    assert c["labor_source"] == "actual"
    assert c["is_assigned"] is True
    assert c["planned_labor_cost"] == 20.0
    assert c["actual_labor_cost"] == 40.0  # 18 + 22
    assert c["labor_cost"] == 40.0
    # base = 100 + 40 = 140
    # overhead = 140 * 10% = 14
    # packing = 5
    # total = 140 + 14 + 5 = 159
    assert c["total_cost"] == 159.0
    assert len(c["assigned_roles"]) == 2
    roles = {r["role"]: r for r in c["assigned_roles"]}
    assert roles["cutting"]["worker_name"] == "Ramesh"
    assert roles["cutting"]["rate_per_pair"] == 18.0
    assert roles["stitching"]["worker_name"] == "Suresh"
    assert roles["stitching"]["rate_per_pair"] == 22.0
