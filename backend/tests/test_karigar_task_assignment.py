import pytest
import requests

BASE_URL = "http://localhost:8000"

def test_karigar_task_assignment_lifecycle():
    admin_session = requests.Session()
    res = admin_session.post(f"{BASE_URL}/api/auth/login", json={"email": "sskfootcare@gmail.com", "password": "Chandu@220494"})
    assert res.status_code == 200
    admin_token = res.json()["access_token"]
    admin_session.headers.update({"Authorization": f"Bearer {admin_token}"})

    # 1. Create worker or use existing
    w_res = admin_session.post(f"{BASE_URL}/api/workers", json={
        "name": "Test Karigar Task Flow",
        "phone": "9998887771",
        "skill": "upper",
        "rate_per_pair": 15.0,
        "pin": "1234"
    })
    if w_res.status_code == 200:
        worker_doc = w_res.json()
    else:
        # Worker might exist, find by phone
        workers = admin_session.get(f"{BASE_URL}/api/workers").json()
        worker_doc = next(w for w in workers if w.get("phone") == "9998887771")

    worker_id = worker_doc["id"]
    admin_session.patch(f"{BASE_URL}/api/workers/{worker_id}/set-pin", json={"pin": "1234"})

    # Login as worker
    w_session = requests.Session()
    w_login = w_session.post(f"{BASE_URL}/api/auth/worker-login", json={"phone": "9998887771", "pin": "1234"})
    assert w_login.status_code == 200, f"Worker login failed: {w_login.text}"
    w_token = w_login.json()["access_token"]
    w_session.headers.update({"Authorization": f"Bearer {w_token}"})

    # 2. Get an existing job and assign to worker for role 'upper' or 'cutting'
    jobs = admin_session.get(f"{BASE_URL}/api/production/jobs").json()
    assert len(jobs) > 0
    test_job = jobs[0]
    jid = test_job["id"]

    # Assign worker to role 'upper'
    assign_res = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/assignment", json={
        "role": "upper",
        "worker_id": worker_id,
        "rate_per_pair": 15.0
    })
    assert assign_res.status_code == 200

    # 3. Check worker's 'active' (Ongoing Tasks) -> MUST BE PRESENT!
    active_tasks = w_session.get(f"{BASE_URL}/api/my/tasks?scope=active").json()
    task_in_active = any(t["id"] == jid for t in active_tasks)
    assert task_in_active is True, "Newly assigned task must appear under Ongoing Tasks (scope=active)"

    # Check worker's 'completed' -> MUST NOT BE PRESENT YET!
    completed_tasks = w_session.get(f"{BASE_URL}/api/my/tasks?scope=completed").json()
    task_in_completed = any(t["id"] == jid for t in completed_tasks)
    assert task_in_completed is False, "Newly assigned task must NOT appear under Completed Tasks before ready_for_pickup"

    # 4. Worker marks task ready for pickup (completes work)
    rfp_res = w_session.patch(f"{BASE_URL}/api/my/tasks/{jid}/ready-for-pickup", json={
        "completed_qty": test_job.get("quantity", 10),
        "notes": "Finished upper work"
    })
    assert rfp_res.status_code == 200, f"Ready for pickup failed: {rfp_res.text}"

    # 5. Re-check 'active' -> MUST NO LONGER BE PRESENT!
    active_after = w_session.get(f"{BASE_URL}/api/my/tasks?scope=active").json()
    assert any(t["id"] == jid for t in active_after) is False, "Completed task must disappear from Ongoing Tasks"

    # Re-check 'completed' -> MUST NOW BE PRESENT!
    completed_after = w_session.get(f"{BASE_URL}/api/my/tasks?scope=completed").json()
    assert any(t["id"] == jid for t in completed_after) is True, "Completed task must appear under Completed Tasks"
