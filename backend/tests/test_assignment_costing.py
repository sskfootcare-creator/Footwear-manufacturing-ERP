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

from server import compute_style_costing_async, compute_style_costing_from_jobs


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

    c_async = asyncio.run(_run())
    c_from_jobs = compute_style_costing_from_jobs(style, [])

    for c in [c_async, c_from_jobs]:
        assert c["labor_source"] == "estimated"
        assert c["is_assigned"] is False
        assert c["materials_cost"] == 100.0
        assert c["labor_cost"] == 35.0  # 20 + 15
        # base = 100 + 35 = 135
        # overhead = 135 * 10% = 13.5
        # total = 135 + 13.5 + 5 = 153.5
        assert c["total_cost"] == 153.5

    assert c_from_jobs == c_async


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

    c_async = asyncio.run(_run())
    c_from_jobs = compute_style_costing_from_jobs(style, jobs)

    for c in [c_async, c_from_jobs]:
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

    assert c_from_jobs == c_async


def test_compute_style_costing_from_jobs_multi_job_average():
    """Directly test compute_style_costing_from_jobs with multiple production jobs averaging labor rates."""
    style = {
        "_id": "style_103",
        "code": "SSK_103",
        "bom": [{"rate": 50.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
        "labor": [{"name": "Stitching", "rate": 20.0}],
        "overhead_pct": 10.0,
        "packing_cost": 5.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
    }

    # Job 1 total rate = 30.0; Job 2 total rate = 40.0 -> average = 35.0
    jobs = [
        {
            "_id": "j1",
            "style_id": "style_103",
            "assignments": {
                "cutting": {"worker_id": "w1", "rate_per_pair": 10.0},
                "stitching": {"worker_id": "w2", "rate_per_pair": 20.0},
            },
        },
        {
            "_id": "j2",
            "style_id": "style_103",
            "assignments": {
                "cutting": {"worker_id": "w3", "rate_per_pair": 15.0},
                "stitching": {"worker_id": "w4", "rate_per_pair": 25.0},
            },
        },
    ]

    c = compute_style_costing_from_jobs(style, jobs)
    assert c["labor_source"] == "actual"
    assert c["is_assigned"] is True
    assert c["actual_labor_cost"] == 35.0
    assert c["labor_cost"] == 35.0
    # base = 50 + 35 = 85
    # overhead = 85 * 10% = 8.5
    # total = 85 + 8.5 + 5 = 98.5
    assert c["total_cost"] == 98.5
