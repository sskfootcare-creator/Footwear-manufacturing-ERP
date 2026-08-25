"""Test dashboard stats caching, performance speedup, and freshness."""
import pytest
import os
import time
from motor.motor_asyncio import AsyncIOMotorClient
import server
from server import (
    oid,
    dashboard_stats,
    invalidate_dashboard_stats_cache,
)


class DummyRequest:
    """Mock Request for unit testing endpoints with auth state."""
    state = type("State", (), {"user": {"email": "admin@sskfootcare.com", "role": "admin"}})()
    headers = {}
    cookies = {}


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    monkeypatch.setattr(server, "client", c)
    monkeypatch.setattr(server, "db", d)
    invalidate_dashboard_stats_cache()
    yield d
    invalidate_dashboard_stats_cache()
    c.close()


@pytest.mark.anyio
async def test_dashboard_stats_caching_and_freshness(fresh_db, monkeypatch):
    """Verify: measure dashboard load time before/after with a realistic dataset size;
    confirm stats are served rapidly from cache, stored in db.stats_cache, and
    freshness is preserved upon refresh.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    dummy_req = DummyRequest()

    # Clear any previous cached entry
    await server.db.stats_cache.delete_one({"_id": "dashboard_stats"})
    invalidate_dashboard_stats_cache()

    # 1. Seed 250 production jobs and 25 POs
    test_jobs = []
    for i in range(250):
        test_jobs.append({
            "po_number": f"PO-STATS-TEST-{i % 25:03d}",
            "style_code": f"SSK-STYLE-{i % 10:02d}",
            "color": "Black" if i % 2 == 0 else "Brown",
            "size": str(6 + (i % 5)),
            "quantity": 20,
            "stage": "cutting" if i < 150 else "dispatched",
            "source_type": "b2b",
            "created_at": "2026-08-25T10:00:00Z",
        })
    inserted_jobs = await server.db.production_jobs.insert_many(test_jobs)

    try:
        # 2. Cold request (live computation)
        t0 = time.perf_counter()
        cold_stats = await dashboard_stats(dummy_req)
        t_cold = time.perf_counter() - t0

        assert cold_stats["pairs_in_wip"] >= 3000  # 150 * 20 = 3000
        assert cold_stats["dispatched"] >= 2000    # 100 * 20 = 2000

        # Verify db.stats_cache collection was populated
        cache_doc = await server.db.stats_cache.find_one({"_id": "dashboard_stats"})
        assert cache_doc is not None
        assert cache_doc["data"]["pairs_in_wip"] == cold_stats["pairs_in_wip"]

        # 3. Warm request (served from memory/cache)
        t0 = time.perf_counter()
        warm_stats = await dashboard_stats(dummy_req)
        t_warm = time.perf_counter() - t0

        assert warm_stats == cold_stats
        # Warm should be noticeably faster
        assert t_warm < t_cold or t_warm < 0.05

        # 4. Invalidate and check fallback
        invalidate_dashboard_stats_cache()
        # In-memory is cleared, but db.stats_cache is still fresh (<5min)
        db_cache_stats = await dashboard_stats(dummy_req)
        assert db_cache_stats == cold_stats

        # 5. Add a new job and force refresh
        new_job_res = await server.db.production_jobs.insert_one({
            "po_number": "PO-STATS-NEW-01",
            "style_code": "SSK-NEW",
            "color": "Tan",
            "size": "8",
            "quantity": 100,
            "stage": "stitching",
            "source_type": "b2b",
            "created_at": "2026-08-25T11:55:00Z",
        })

        # Request with force_refresh=True
        refreshed_stats = await dashboard_stats(dummy_req, force_refresh=True)
        assert refreshed_stats["pairs_in_wip"] == cold_stats["pairs_in_wip"] + 100

        await server.db.production_jobs.delete_one({"_id": new_job_res.inserted_id})

    finally:
        await server.db.production_jobs.delete_many({"po_number": {"$regex": "^PO-STATS-"}})
        await server.db.stats_cache.delete_one({"_id": "dashboard_stats"})
        invalidate_dashboard_stats_cache()
