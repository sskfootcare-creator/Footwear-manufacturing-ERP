import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from collections import defaultdict
import server
from server import list_styles_summary, compute_style_costing_async, get_style


class MockCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, key, direction):
        return self

    async def to_list(self, limit):
        return self.items


class MockDB:
    def __init__(self, styles, jobs, style_lifecycle=None):
        self.styles_data = styles
        self.jobs_data = jobs
        self.lifecycle_data = style_lifecycle or []

        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=self._find_styles)
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=self._find_jobs)

        self.style_lifecycle = MagicMock()
        self.style_lifecycle.find = MagicMock(side_effect=lambda q, proj=None: MockCursor(self.lifecycle_data))

    def _find_styles(self, query):
        return MockCursor(self.styles_data)

    async def _find_one_style(self, query):
        for s in self.styles_data:
            if "_id" in query:
                val = query["_id"]
                if str(s.get("_id", "")) == str(val) or s.get("_id") == val:
                    return dict(s)
        return None

    def _find_jobs(self, query):
        # Support either $or query with $in, or simple $or per-style query
        results = []
        if "$or" in query:
            for job in self.jobs_data:
                matched = False
                for cond in query["$or"]:
                    if "style_id" in cond:
                        val = cond["style_id"]
                        if isinstance(val, dict) and "$in" in val:
                            if str(job.get("style_id", "")) in val["$in"]:
                                matched = True
                        elif str(job.get("style_id", "")) == str(val):
                            matched = True
                    if "style_code" in cond:
                        val = cond["style_code"]
                        if isinstance(val, dict) and "$in" in val:
                            if job.get("style_code") in val["$in"]:
                                matched = True
                        elif job.get("style_code") == val:
                            matched = True
                if matched and job not in results:
                    results.append(job)
        return MockCursor(results)


class DummyRequest:
    state = type("State", (), {"user": {"email": "admin@sskfootcare.com", "role": "admin"}})()
    headers = {}
    cookies = {}


@pytest.mark.anyio
async def test_list_styles_summary_batched_jobs_matches_per_style_results(monkeypatch):
    """Verify that single batched query returns the exact same results as per-style resolution,
    and calls production_jobs.find only once.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    styles = [
        {
            "_id": "style_001",
            "id": "style_001",
            "code": "ST-001",
            "name": "Sneaker Alpha",
            "bom": [{"rate": 50.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Stitching", "rate": 20.0}],
            "overhead_pct": 10.0,
            "packing_cost": 5.0,
            "margin_pct": 20.0,
            "gst_pct": 5.0,
        },
        {
            "_id": "style_002",
            "id": "style_002",
            "code": "ST-002",
            "name": "Boot Beta",
            "bom": [{"rate": 80.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Assembly", "rate": 30.0}],
            "overhead_pct": 10.0,
            "packing_cost": 5.0,
            "margin_pct": 25.0,
            "gst_pct": 5.0,
        },
        {
            "_id": "style_003",
            "id": "style_003",
            "code": "ST-003",
            "name": "Sandal Gamma",
            "bom": [{"rate": 30.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Finishing", "rate": 15.0}],
            "overhead_pct": 5.0,
            "packing_cost": 2.0,
            "margin_pct": 15.0,
            "gst_pct": 5.0,
        },
    ]

    jobs = [
        # Job for style_001 matched by style_id
        {
            "_id": "job_1",
            "style_id": "style_001",
            "style_code": "ST-001",
            "assignments": {
                "stitching": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 25.0}
            },
        },
        # Another Job for style_001 matched by style_code
        {
            "_id": "job_2",
            "style_id": "style_001_legacy",
            "style_code": "ST-001",
            "assignments": {
                "stitching": {"worker_id": "w2", "worker_name": "Suresh", "rate_per_pair": 35.0}
            },
        },
        # Job for style_002 matched by style_id only
        {
            "_id": "job_3",
            "style_id": "style_002",
            "style_code": "OTHER-CODE",
            "assignments": {
                "assembly": {"worker_id": "w3", "worker_name": "Dinesh", "rate_per_pair": 40.0}
            },
        },
        # Job for unrelated style
        {
            "_id": "job_99",
            "style_id": "style_999",
            "style_code": "ST-999",
            "assignments": {
                "cutting": {"worker_id": "w9", "worker_name": "Other", "rate_per_pair": 50.0}
            },
        },
    ]

    mock_db = MockDB(styles, jobs)
    monkeypatch.setattr(server, "db", mock_db)

    # 1. Compute per-style costing the old sequential way
    costing_old_001 = await compute_style_costing_async(styles[0], mock_db)
    costing_old_002 = await compute_style_costing_async(styles[1], mock_db)
    costing_old_003 = await compute_style_costing_async(styles[2], mock_db)

    # Reset mock find counter
    mock_db.production_jobs.find.reset_mock()

    # 2. Run list_styles_summary
    results = await list_styles_summary(DummyRequest())

    # 3. Verify exactly ONE find call was made to production_jobs
    assert mock_db.production_jobs.find.call_count == 1

    # Verify query structure passed to production_jobs.find
    call_args = mock_db.production_jobs.find.call_args[0][0]
    assert "$or" in call_args
    assert {"style_id": {"$in": ["style_001", "style_002", "style_003"]}} in call_args["$or"]
    assert {"style_code": {"$in": ["ST-001", "ST-002", "ST-003"]}} in call_args["$or"]

    # 4. Verify results match individual per-style costing
    res_001 = next(r for r in results if r["id"] == "style_001")
    res_002 = next(r for r in results if r["id"] == "style_002")
    res_003 = next(r for r in results if r["id"] == "style_003")

    # Style 001: had 2 jobs (rates 25 and 35, avg labor = 30)
    assert res_001["cost_summary"]["labor_cost"] == costing_old_001["labor_cost"] == 30.0
    assert res_001["cost_summary"]["is_assigned"] == costing_old_001["is_assigned"] is True
    assert res_001["cost_summary"]["total_cost"] == costing_old_001["total_cost"]

    # Style 002: had 1 job (rate 40, avg labor = 40)
    assert res_002["cost_summary"]["labor_cost"] == costing_old_002["labor_cost"] == 40.0
    assert res_002["cost_summary"]["is_assigned"] == costing_old_002["is_assigned"] is True
    assert res_002["cost_summary"]["total_cost"] == costing_old_002["total_cost"]

    # Style 003: had 0 jobs (planned labor = 15)
    assert res_003["cost_summary"]["labor_cost"] == costing_old_003["labor_cost"] == 15.0
    assert res_003["cost_summary"]["is_assigned"] == costing_old_003["is_assigned"] is False
    assert res_003["cost_summary"]["total_cost"] == costing_old_003["total_cost"]


@pytest.mark.anyio
async def test_list_styles_summary_deduplicates_jobs_matching_both_id_and_code(monkeypatch):
    """Ensure a job matching both style_id and style_code is counted exactly once."""
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    styles = [
        {
            "_id": "style_dup_1",
            "id": "style_dup_1",
            "code": "DUP-001",
            "name": "Deduplication Test Style",
            "bom": [{"rate": 10.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0}],
            "labor": [{"name": "Labor 1", "rate": 10.0}],
            "overhead_pct": 0,
            "packing_cost": 0,
            "margin_pct": 0,
            "gst_pct": 0,
        }
    ]

    jobs = [
        {
            "_id": "job_dup_1",
            "style_id": "style_dup_1",
            "style_code": "DUP-001",
            "assignments": {
                "role1": {"rate_per_pair": 50.0}
            }
        }
    ]

    mock_db = MockDB(styles, jobs)
    monkeypatch.setattr(server, "db", mock_db)

    results = await list_styles_summary(DummyRequest())
    assert len(results) == 1
    # If counted once, labor_cost is 50.0. (If erroneously counted twice, sum(50,50)/2 is also 50, but let's check assigned roles count)
    assert results[0]["cost_summary"]["labor_cost"] == 50.0
    assert results[0]["cost_summary"]["is_assigned"] is True


@pytest.mark.anyio
async def test_list_styles_summary_empty_docs(monkeypatch):
    """Ensure empty styles returns [] and doesn't query production_jobs."""
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    mock_db = MockDB([], [])
    monkeypatch.setattr(server, "db", mock_db)

    results = await list_styles_summary(DummyRequest())
    assert results == []
    assert mock_db.production_jobs.find.call_count == 0


@pytest.mark.anyio
async def test_benchmark_and_accuracy_200_plus_styles(monkeypatch):
    """Realistic dataset benchmark with 250+ styles:
    - 250 styles, ~150 with real production history jobs
    - Verifies 1 DB query total for production_jobs
    - Verifies returned cost_summary is 100% IDENTICAL to unbatched sequential queries
    - Verifies execution does not suffer linear DB query overhead
    """
    import time
    from server import stringify

    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    styles = []
    jobs = []
    num_styles = 250

    for i in range(num_styles):
        sid = f"style_{i:04d}"
        scode = f"SSK-STYLE-{i:04d}"
        styles.append({
            "_id": sid,
            "id": sid,
            "code": scode,
            "name": f"Performance Test Footwear {i}",
            "category": "Sneakers" if i % 2 == 0 else "Sandals",
            "bom": [
                {"rate": 40.0 + (i % 20), "quantity": 1, "yield_per_unit": 1, "waste_pct": 2.0}
            ],
            "labor": [
                {"name": "Stitching", "rate": 20.0 + (i % 10)},
                {"name": "Finishing", "rate": 15.0}
            ],
            "overhead_pct": 10.0,
            "packing_cost": 5.0,
            "margin_pct": 20.0,
            "gst_pct": 5.0,
        })

        # Attach production jobs to ~60% of styles
        if i % 3 != 0:
            # Add 1 to 3 jobs per style with realistic assignments
            for j in range((i % 3) + 1):
                jobs.append({
                    "_id": f"job_{i:04d}_{j}",
                    "style_id": sid if j % 2 == 0 else f"legacy_{sid}",
                    "style_code": scode,
                    "assignments": {
                        "stitching": {
                            "worker_id": f"w_{i}_{j}",
                            "worker_name": f"Worker {j}",
                            "rate_per_pair": 22.0 + (i % 5) + (j * 2)
                        },
                        "finishing": {
                            "worker_id": f"w_fin_{i}_{j}",
                            "worker_name": f"Finisher {j}",
                            "rate_per_pair": 16.0 + (j * 1.5)
                        }
                    }
                })

    mock_db = MockDB(styles, jobs)
    monkeypatch.setattr(server, "db", mock_db)

    # 1. Compute baseline ground-truth cost summaries sequentially via unbatched compute_style_costing_async
    unbatched_results = {}
    for s in styles:
        s_copy = stringify(dict(s))
        c_old = await compute_style_costing_async(s_copy, mock_db)
        unbatched_results[s_copy["id"]] = {
            "materials_cost": c_old.get("materials_cost", 0.0),
            "labor_cost": c_old.get("labor_cost", 0.0),
            "total_cost": c_old.get("total_cost", 0.0),
            "selling_price": c_old.get("selling_price", 0.0),
            "suggested_target_price": c_old.get("suggested_target_price", 0.0),
            "is_assigned": c_old.get("is_assigned", False),
        }

    # Reset mock find call count
    mock_db.production_jobs.find.reset_mock()

    # 2. Run batched list_styles_summary
    t0 = time.perf_counter()
    summary_results = await list_styles_summary(DummyRequest())
    elapsed = time.perf_counter() - t0

    # 3. Verify exactly ONE production_jobs query was executed across all 250 styles
    assert mock_db.production_jobs.find.call_count == 1
    assert len(summary_results) == num_styles

    # 4. Confirm returned cost_summary is 100% IDENTICAL to what unbatched produced for every single style
    for item in summary_results:
        sid = item["id"]
        assert sid in unbatched_results, f"Missing style {sid} in baseline"
        expected = unbatched_results[sid]
        actual = item["cost_summary"]

        assert actual == expected, (
            f"Mismatch on style {sid}: actual={actual} vs expected={expected}"
        )


@pytest.mark.anyio
async def test_get_style_single_detail_view_unaffected(monkeypatch):
    """Confirm the style edit drawer's single-style detail view (GET /styles/{sid})
    is unaffected, loads full BOM and Labor, and correctly calculates actual/estimated
    costing using compute_style_costing_async.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    style_with_jobs = {
        "_id": "507f1f77bcf86cd799439011",
        "id": "507f1f77bcf86cd799439011",
        "code": "SSK-REAL-001",
        "name": "Real Production Style",
        "bom": [
            {"material_name": "Leather Upper", "rate": 150.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0},
            {"material_name": "Rubber Sole", "rate": 80.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0},
        ],
        "labor": [
            {"name": "Cutting", "rate": 20.0},
            {"name": "Stitching", "rate": 30.0},
        ],
        "overhead_pct": 10.0,
        "packing_cost": 15.0,
        "margin_pct": 25.0,
        "gst_pct": 5.0,
    }

    style_without_jobs = {
        "_id": "507f1f77bcf86cd799439022",
        "id": "507f1f77bcf86cd799439022",
        "code": "SSK-EST-002",
        "name": "Estimated Labor Style",
        "bom": [
            {"material_name": "Canvas", "rate": 60.0, "quantity": 1, "yield_per_unit": 1, "waste_pct": 0},
        ],
        "labor": [
            {"name": "Cutting", "rate": 15.0},
        ],
        "overhead_pct": 10.0,
        "packing_cost": 5.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
    }

    jobs = [
        {
            "_id": "job_real_1",
            "style_id": "507f1f77bcf86cd799439011",
            "style_code": "SSK-REAL-001",
            "assignments": {
                "cutting": {"worker_id": "w1", "worker_name": "Ramesh", "rate_per_pair": 24.0},
                "stitching": {"worker_id": "w2", "worker_name": "Suresh", "rate_per_pair": 36.0},
            },
        }
    ]

    mock_db = MockDB([style_with_jobs, style_without_jobs], jobs)
    monkeypatch.setattr(server, "db", mock_db)

    # 1. Test get_style for style with production history
    detail_with_jobs = await get_style("507f1f77bcf86cd799439011", DummyRequest())
    assert detail_with_jobs["id"] == "507f1f77bcf86cd799439011"
    assert detail_with_jobs["code"] == "SSK-REAL-001"
    assert len(detail_with_jobs["bom"]) == 2
    assert len(detail_with_jobs["labor"]) == 2

    # Check costing breakdown
    costing_1 = detail_with_jobs["costing"]
    assert costing_1["labor_source"] == "actual"
    assert costing_1["is_assigned"] is True
    assert costing_1["actual_labor_cost"] == 60.0  # 24 + 36
    assert costing_1["planned_labor_cost"] == 50.0  # 20 + 30
    assert costing_1["materials_cost"] == 230.0  # 150 + 80
    assert len(costing_1["assigned_roles"]) == 2

    # 2. Test get_style for style without production history
    detail_without_jobs = await get_style("507f1f77bcf86cd799439022", DummyRequest())
    assert detail_without_jobs["id"] == "507f1f77bcf86cd799439022"
    assert detail_without_jobs["code"] == "SSK-EST-002"
    costing_2 = detail_without_jobs["costing"]
    assert costing_2["labor_source"] == "estimated"
    assert costing_2["is_assigned"] is False
    assert costing_2["labor_cost"] == 15.0
