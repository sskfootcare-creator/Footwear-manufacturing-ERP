import pytest
import requests
import time

BASE_URL = "http://localhost:8000"

def test_material_requirement_stage_gate():
    session = requests.Session()
    # Login as admin
    res = session.post(f"{BASE_URL}/api/auth/login", json={"email": "sskfootcare@gmail.com", "password": "Chandu@220494"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})

    # Fetch an existing active style
    styles = session.get(f"{BASE_URL}/api/styles").json()
    assert len(styles) > 0
    style = styles[0]
    style_code = style["code"]

    # Temporarily clear BOM on style to test the gate
    orig_bom = style.get("bom", [])
    session.patch(f"{BASE_URL}/api/styles/{style['id']}", json={"bom": []})

    po_num = f"PO-GATE-TEST-{int(time.time())}"
    try:
        # Create a PO with this style to produce a job in procurement stage
        po_res = session.post(f"{BASE_URL}/api/pos", json={
            "po_number": po_num,
            "client_name": "Test Gate Client",
            "po_date": "2026-08-08",
            "line_items": [
                {
                    "style_code": style_code,
                    "external_sku": style_code,
                    "description": "Test sandal",
                    "color": style.get("color", "Black"),
                    "size": "7",
                    "quantity": 10,
                    "unit_price": 500.0,
                    "amount": 5000.0
                }
            ]
        })
        assert po_res.status_code in [200, 201], po_res.text

        # Find the newly created job
        jobs = session.get(f"{BASE_URL}/api/production/jobs").json()
        gate_job = next(j for j in jobs if j.get("po_number") == po_num)
        assert gate_job["stage"] == "procurement"

        # Attempt to move job out of procurement to cutting -> MUST FAIL WITH 400!
        move_res = session.patch(f"{BASE_URL}/api/production/jobs/{gate_job['id']}", json={"stage": "cutting"})
        assert move_res.status_code == 400, move_res.text
        detail = move_res.json()["detail"]
        print("\n[SUCCESS] Gate blocked stage transition out of Procurement with detail:", detail)
        assert "Cannot move out of Procurement" in detail

        # Verify job stage remained in procurement
        jobs_after = session.get(f"{BASE_URL}/api/production/jobs").json()
        j_after = next(j for j in jobs_after if j["id"] == gate_job["id"])
        assert j_after["stage"] == "procurement"

    finally:
        # Restore original BOM
        session.patch(f"{BASE_URL}/api/styles/{style['id']}", json={"bom": orig_bom})
