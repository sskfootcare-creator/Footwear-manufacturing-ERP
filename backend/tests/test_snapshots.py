import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def test_pending_list_snapshots_lifecycle(admin_session):
    # 1. Fetch live pending product list
    live_resp = admin_session.get(f"{BASE_URL}/api/production/pending-list", timeout=15)
    assert live_resp.status_code == 200
    live_jobs = live_resp.json()

    # 2. Create a snapshot
    snapshot_payload = {"filter_used": "all"}
    post_resp = admin_session.post(
        f"{BASE_URL}/api/production/pending-list/snapshot",
        json=snapshot_payload,
        timeout=15
    )
    assert post_resp.status_code == 200
    snapshot = post_resp.json()
    assert "id" in snapshot
    assert snapshot["saved_by"] == ADMIN_EMAIL.lower()
    assert "saved_at" in snapshot
    assert snapshot["filter_used"] == "all"
    
    # Verify totals
    totals = snapshot["totals"]
    assert "pending" in totals
    assert "ready" in totals
    assert "shortage" in totals
    assert "total_pairs" in totals
    assert totals["pending"] == len(live_jobs)
    assert len(snapshot["jobs"]) == len(live_jobs)

    snapshot_id = snapshot["id"]

    # 3. List snapshots (check metadata only - exclude jobs)
    list_resp = admin_session.get(f"{BASE_URL}/api/production/pending-list/snapshots", timeout=15)
    assert list_resp.status_code == 200
    snapshots_list = list_resp.json()
    assert len(snapshots_list) > 0
    
    # Find our snapshot in the list
    matching = [s for s in snapshots_list if s["id"] == snapshot_id]
    assert len(matching) == 1
    matched_meta = matching[0]
    assert "saved_at" in matched_meta
    assert "saved_by" in matched_meta
    assert "totals" in matched_meta
    assert "jobs" not in matched_meta or matched_meta["jobs"] is None

    # 4. Get full snapshot details (including jobs)
    get_resp = admin_session.get(
        f"{BASE_URL}/api/production/pending-list/snapshots/{snapshot_id}",
        timeout=15
    )
    assert get_resp.status_code == 200
    full_snapshot = get_resp.json()
    assert full_snapshot["id"] == snapshot_id
    assert "jobs" in full_snapshot
    assert len(full_snapshot["jobs"]) == len(live_jobs)

    # 5. Verify snapshot remains unchanged if live data updates (by dispatching/modifying a live job)
    # If there are any pending jobs, we try to record a production for one to see that the live list changes
    # but the snapshot jobs array remains unchanged.
    if len(live_jobs) > 0:
        target_job = live_jobs[0]
        # Record production for this style/color/size
        produce_payload = {
            "style_id": target_job["style_id"],
            "color": target_job["color"],
            "size": target_job["size"],
            "produced_qty": int(target_job["quantity"]) - int(target_job.get("completed_qty", 0) or 0),
            "reason": "Verify snapshot independence",
            "use_components": False, # skip BOM component requirement
            "channel_filter": "online_channel",
            "force_negative_stock": True
        }
        
        prod_resp = admin_session.post(
            f"{BASE_URL}/api/production/produce-cell",
            json=produce_payload,
            timeout=15
        )
        assert prod_resp.status_code == 200
        
        # Verify live list has updated and the job stage is dispatched (so it drops off live pending list)
        live_resp_updated = admin_session.get(f"{BASE_URL}/api/production/pending-list", timeout=15)
        assert live_resp_updated.status_code == 200
        live_jobs_updated = live_resp_updated.json()
        
        # Check that the total pending count in live list has decreased (or jobs are different)
        # Note: since the matrix groupings filter out completed items, the list length or quantities will change.
        assert len(live_jobs_updated) < len(live_jobs) or sum(j["quantity"] - j.get("completed_qty", 0) for j in live_jobs_updated) < sum(j["quantity"] - j.get("completed_qty", 0) for j in live_jobs)
        
        # Verify the saved snapshot still contains the exact original jobs count and totals
        get_resp_after = admin_session.get(
            f"{BASE_URL}/api/production/pending-list/snapshots/{snapshot_id}",
            timeout=15
        )
        assert get_resp_after.status_code == 200
        full_snapshot_after = get_resp_after.json()
        assert len(full_snapshot_after["jobs"]) == len(live_jobs)
        assert full_snapshot_after["totals"]["pending"] == len(live_jobs)
