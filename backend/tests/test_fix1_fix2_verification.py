import pytest
import requests

BASE_URL = "http://localhost:8000"

@pytest.fixture
def admin_session():
    s = requests.Session()
    # Login as admin
    res = s.post(f"{BASE_URL}/api/auth/login", json={"email": "sskfootcare@gmail.com", "password": "Chandu@220494"})
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s

def test_fix1_parallel_completion_gate(admin_session):
    """Verify parallel-completion gate before moving stage to 'lasting'."""
    # Fetch existing jobs or grab first available job
    res = admin_session.get(f"{BASE_URL}/api/production/jobs")
    assert res.status_code == 200
    jobs = res.json()
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
