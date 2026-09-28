import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "Admin@123")


def _get_admin_session():
    """Return an authenticated admin session or skip the test if the server is unreachable."""
    admin_session = requests.Session()
    try:
        res = admin_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        pytest.skip("Live backend server not available")
    if res.status_code != 200:
        pytest.skip(f"Admin login failed ({res.status_code}): {res.text}")
    admin_session.headers.update({"Authorization": f"Bearer {res.json()['access_token']}"})
    return admin_session


def test_karigar_task_assignment_lifecycle():
    admin_session = _get_admin_session()

    # 1. Create worker or use existing
    worker_phone = f"99{int(time.time()*1000) % 100000000:08d}"
    w_res = admin_session.post(f"{BASE_URL}/api/workers", json={
        "name": "Test Karigar Task Flow",
        "phone": worker_phone,
        "skill": "upper",
        "rate_per_pair": 15.0,
        "pin": "1234"
    })
    if w_res.status_code == 200:
        worker_doc = w_res.json()
    else:
        workers = admin_session.get(f"{BASE_URL}/api/workers").json()
        worker_doc = next(w for w in workers if w.get("phone") == worker_phone)

    wid = worker_doc.get("id") or str(worker_doc.get("_id"))
    pin_res = admin_session.patch(f"{BASE_URL}/api/workers/{wid}/set-pin", json={"pin": "1234"})
    assert pin_res.status_code == 200, f"set-pin failed: {pin_res.text}"

    # Login as worker
    w_session = requests.Session()
    w_login = w_session.post(f"{BASE_URL}/api/auth/worker-login", json={"phone": worker_phone, "pin": "1234"})
    assert w_login.status_code == 200, f"Worker login failed: {w_login.text}"
    worker_id = w_login.json()["worker_id"]
    w_token = w_login.json()["access_token"]
    w_session.headers.update({"Authorization": f"Bearer {w_token}"})

    # 2. Create material & dedicated style with BOM, then create PO + job and assign to worker for role 'cutting'
    m_res = admin_session.post(f"{BASE_URL}/api/materials", json={
        "code": f"MAT-K-{int(time.time()*1000)}",
        "name": "Karigar Leather",
        "category": "upper",
        "unit": "sqft",
        "rate": 50.0,
    })
    if m_res.status_code == 200:
        mat_doc = m_res.json()
    else:
        mats = admin_session.get(f"{BASE_URL}/api/materials").json()
        mat_doc = mats[0]

    mat_id = mat_doc.get("id") or str(mat_doc.get("_id"))
    admin_session.post(f"{BASE_URL}/api/inventory/movements", json={
        "material_id": mat_id,
        "type": "in",
        "quantity": 100.0,
        "rate": 50.0,
        "party": "Opening Stock",
        "notes": "Initial test stock",
    })

    style_payload = {
        "name": "Karigar Test Style",
        "category": "Footwear",
        "base_size": "7",
        "bom": [{
            "material_id": mat_id,
            "material_name": mat_doc["name"],
            "material_code": mat_doc["code"],
            "unit": mat_doc.get("unit", "sqft"),
            "rate": mat_doc.get("rate", 50.0),
            "quantity": 1.0,
        }],
        "labor": [],
    }
    r_style = admin_session.post(f"{BASE_URL}/api/styles", json=style_payload)
    assert r_style.status_code == 200
    style_code = r_style.json()["code"]

    po_num = f"PO-KARIGAR-{int(time.time()*1000)}"
    po_res = admin_session.post(f"{BASE_URL}/api/pos", json={
        "po_number": po_num,
        "client_name": "Karigar Test Client",
        "po_date": "2026-08-08",
        "line_items": [
            {
                "style_code": style_code,
                "external_sku": style_code,
                "color": "Black",
                "size": "7",
                "quantity": 10,
                "unit_price": 500.0,
                "amount": 5000.0
            }
        ]
    })
    assert po_res.status_code in [200, 201]

    jobs = admin_session.get(f"{BASE_URL}/api/production/jobs").json()
    test_job = next(j for j in jobs if j.get("po_number") == po_num)
    jid = test_job["id"]

    # Assign worker to role 'cutting'
    assign_res = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/assignment", json={
        "role": "cutting",
        "worker_id": worker_id,
        "rate_per_pair": 15.0
    })
    assert assign_res.status_code == 200

    # Advance job to 'cutting' stage
    r_adv = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={
        "stage": "cutting", "confirm_skip": True,
    })
    assert r_adv.status_code == 200, r_adv.text

    # 3. Check worker's 'active' (Ongoing Tasks) -> MUST BE PRESENT!
    active_tasks = w_session.get(f"{BASE_URL}/api/my/tasks?scope=active").json()
    task_in_active = any(t["id"] == jid or jid in t.get("job_ids", []) for t in active_tasks)
    assert task_in_active is True, "Newly assigned task must appear under Ongoing Tasks (scope=active)"

    # Check worker's 'completed' -> MUST NOT BE PRESENT YET!
    completed_tasks = w_session.get(f"{BASE_URL}/api/my/tasks?scope=completed").json()
    task_in_completed = any(t["id"] == jid or jid in t.get("job_ids", []) for t in completed_tasks)
    assert task_in_completed is False, "Newly assigned task must NOT appear under Completed Tasks before ready_for_pickup"

    # 4. Worker marks task ready for pickup (completes work)
    rfp_res = w_session.patch(f"{BASE_URL}/api/my/tasks/{jid}/ready-for-pickup", json={
        "completed_qty": test_job.get("quantity", 10),
        "notes": "Finished cutting work"
    })
    assert rfp_res.status_code == 200, f"Ready for pickup failed: {rfp_res.text}"

    # 5. Re-check 'active' -> MUST NO LONGER BE PRESENT!
    active_after = w_session.get(f"{BASE_URL}/api/my/tasks?scope=active").json()
    assert any(t["id"] == jid or jid in t.get("job_ids", []) for t in active_after) is False, "Completed task must disappear from Ongoing Tasks"

    # Re-check 'completed' -> MUST NOW BE PRESENT!
    completed_after = w_session.get(f"{BASE_URL}/api/my/tasks?scope=completed").json()
    assert any(t["id"] == jid or jid in t.get("job_ids", []) for t in completed_after) is True, "Completed task must appear under Completed Tasks"
