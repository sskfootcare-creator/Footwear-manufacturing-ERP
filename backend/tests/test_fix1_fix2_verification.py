import pytest
import requests

import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "Admin@123")

@pytest.fixture
def admin_session():
    s = requests.Session()
    # Login as admin
    res = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s

def test_fix1_parallel_completion_gate(admin_session):
    """Verify parallel-completion gate before moving stage to 'lasting'."""
    # Fetch existing jobs or create one if none exist
    res = admin_session.get(f"{BASE_URL}/api/production/jobs")
    assert res.status_code == 200
    jobs = res.json()
    if len(jobs) == 0:
        # Create a style and PO to produce a job
        style_res = admin_session.post(f"{BASE_URL}/api/styles", json={
            "name": f"Test Style Fix1 {int(time.time())}",
            "category": "Footwear",
            "base_size": "8",
            "bom": [],
            "labor": [],
        })
        assert style_res.status_code == 200
        style_code = style_res.json()["code"]
        po_num = f"PO-FIX1-{int(time.time())}"
        po_res = admin_session.post(f"{BASE_URL}/api/pos", json={
            "po_number": po_num,
            "client_name": "Test Client Fix1",
            "po_date": "2026-08-08",
            "line_items": [{
                "style_code": style_code,
                "external_sku": style_code,
                "description": "Test fix1 item",
                "color": "Black",
                "size": "8",
                "quantity": 5,
                "unit_price": 100.0,
                "amount": 500.0,
            }]
        })
        assert po_res.status_code in [200, 201]
        jobs = admin_session.get(f"{BASE_URL}/api/production/jobs").json()
    assert len(jobs) > 0, "No production jobs found"
    test_job = jobs[0]
    jid = test_job["id"]
    orig_stage = test_job.get("stage", "stitching")
    orig_comp = test_job.get("components") or {}

    try:
        # Ensure components are initially incomplete
        admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/components", json={"upper_done": False, "bottom_done": False})

        # Attempt 1: Move to 'lasting' with upper & bottom incomplete -> expect 400
        r1 = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={"stage": "lasting"})
        assert r1.status_code == 400, f"Expected 400, got {r1.status_code}"
        assert "upper and bottom/insole not completed" in r1.json()["detail"]

        # Attempt 2: Upper done only -> expect 400 (bottom missing)
        admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/components", json={"upper_done": True, "bottom_done": False})
        r2 = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={"stage": "lasting"})
        assert r2.status_code == 400
        assert "bottom/insole not completed" in r2.json()["detail"]

        # Attempt 3: Bottom done only -> expect 400 (upper missing)
        admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/components", json={"upper_done": False, "bottom_done": True})
        r3 = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={"stage": "lasting"})
        assert r3.status_code == 400
        assert "upper not completed" in r3.json()["detail"]

        # Attempt 4: Both upper_done & bottom_done -> expect 200 OK
        admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/components", json={"upper_done": True, "bottom_done": True})
        r4 = admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={"stage": "lasting"})
        assert r4.status_code == 200, f"Move to lasting failed: {r4.text}"
        assert r4.json()["stage"] == "lasting"
    finally:
        # Restore original stage and components
        admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}/components", json=orig_comp)
        admin_session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={"stage": orig_stage, "confirm_skip": True})

def test_fix2_with_eva_material_variant(admin_session):
    """Verify with_eva variant attribute on Texon Board materials."""
    code_eva = "TEST-TEXON-EVA"
    code_no_eva = "TEST-TEXON-NO-EVA"
    code_std = "TEST-MAT-STD"

    # Clean up previous runs if present
    mats_res = admin_session.get(f"{BASE_URL}/api/materials")
    for m in mats_res.json():
        if m.get("code") in [code_eva, code_no_eva, code_std]:
            admin_session.delete(f"{BASE_URL}/api/materials/{m['id']}")

    # 1. Create Texon material with with_eva=True
    m1 = admin_session.post(f"{BASE_URL}/api/materials", json={
        "code": code_eva,
        "name": "Texon Board 2.0mm",
        "category": "other",
        "unit": "pcs",
        "rate": 150.0,
        "with_eva": True
    })
    assert m1.status_code == 200, m1.text
    doc1 = m1.json()
    assert doc1.get("with_eva") is True

    # 2. Create Texon material with with_eva=False
    m2 = admin_session.post(f"{BASE_URL}/api/materials", json={
        "code": code_no_eva,
        "name": "Texon Board Hard",
        "category": "other",
        "unit": "pcs",
        "rate": 120.0,
        "with_eva": False
    })
    assert m2.status_code == 200, m2.text
    doc2 = m2.json()
    assert doc2.get("with_eva") is False

    # 3. Create standard material without with_eva specified
    m3 = admin_session.post(f"{BASE_URL}/api/materials", json={
        "code": code_std,
        "name": "PU Foam Sheet",
        "category": "accessory",
        "unit": "mtr",
        "rate": 80.0
    })
    assert m3.status_code == 200, m3.text
    doc3 = m3.json()
    assert doc3.get("with_eva") is None

    # Clean up test materials
    admin_session.delete(f"{BASE_URL}/api/materials/{doc1['id']}")
    admin_session.delete(f"{BASE_URL}/api/materials/{doc2['id']}")
    admin_session.delete(f"{BASE_URL}/api/materials/{doc3['id']}")
