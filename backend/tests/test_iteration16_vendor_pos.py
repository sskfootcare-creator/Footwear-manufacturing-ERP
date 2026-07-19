"""Iteration 16 — Vendor Purchase Orders CRUD + Shortage PO tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_iteration16_vendor_pos.py -v
"""
import os
import pytest
import httpx

BASE = "http://localhost:8000/api"
TIMEOUT = 15

# Use seeded admin credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "Admin@123")


def admin_cookies() -> dict:
    r = httpx.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return dict(r.cookies)


def login_as(email: str, password: str) -> dict:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return dict(r.cookies)


@pytest.fixture(scope="module")
def admin_session():
    return admin_cookies()


@pytest.fixture(scope="module")
def test_vendor(admin_session):
    # Create vendor
    r = httpx.post(f"{BASE}/vendors",
                   json={
                       "name": "Fixture Vendor 16",
                       "gstin": "27AADCB1111M1ZX",
                       "contact_person": "Vendor 16 Contact",
                       "phone": "9999999999",
                       "address": "Vendor 16 Address",
                       "payment_terms_days": 30,
                   },
                   cookies=admin_session, timeout=TIMEOUT)
    assert r.status_code == 201, r.text
    v = r.json()
    vid = v["id"]
    yield v
    # Teardown
    httpx.delete(f"{BASE}/vendors/{vid}", cookies=admin_session, timeout=TIMEOUT)


@pytest.fixture(scope="module")
def test_material(admin_session, test_vendor):
    # Create material with preferred vendor
    r = httpx.post(f"{BASE}/materials",
                   json={
                       "code": "TEST-MAT-16",
                       "name": "Test Material Iteration 16",
                       "category": "upper",
                       "unit": "sqft",
                       "rate": 150.0,
                       "reorder_level": 10.0,
                       "preferred_vendor_id": test_vendor["id"],
                       "notes": "Fixture material"
                   },
                   cookies=admin_session, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    m = r.json()
    mid = m["id"]
    yield m
    # Teardown
    httpx.delete(f"{BASE}/materials/{mid}", cookies=admin_session, timeout=TIMEOUT)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestVendorPO:

    def test_create_vendor_po(self, admin_session, test_vendor, test_material):
        payload = {
            "vendor_id": test_vendor["id"],
            "line_items": [
                {
                    "material_id": test_material["id"],
                    "quantity": 50.0,
                    "rate": 150.0,
                    "amount": 7500.0
                }
            ],
            "status": "draft",
            "expected_delivery_date": "2026-08-01",
            "notes": "Pytest raised PO"
        }
        r = httpx.post(f"{BASE}/vendor-pos", json=payload, cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        po = r.json()
        assert po["id"]
        assert po["po_number"].startswith("PO-VEN-")
        assert po["status"] == "draft"

        # List POs
        r_list = httpx.get(f"{BASE}/vendor-pos", cookies=admin_session, timeout=TIMEOUT)
        assert r_list.status_code == 200
        po_ids = [p["id"] for p in r_list.json()]
        assert po["id"] in po_ids

        # Get single PO
        r_single = httpx.get(f"{BASE}/vendor-pos/{po['id']}", cookies=admin_session, timeout=TIMEOUT)
        assert r_single.status_code == 200
        assert r_single.json()["vendor_name"] == "Fixture Vendor 16"

        # Patch PO status
        r_patch = httpx.patch(f"{BASE}/vendor-pos/{po['id']}", json={"status": "sent"},
                              cookies=admin_session, timeout=TIMEOUT)
        assert r_patch.status_code == 200
        assert r_patch.json()["status"] == "sent"

        # Delete PO
        r_del = httpx.delete(f"{BASE}/vendor-pos/{po['id']}", cookies=admin_session, timeout=TIMEOUT)
        assert r_del.status_code == 200

    def test_shortage_decorations(self, admin_session, test_vendor, test_material):
        # We need a job to check shortage. Let's find one.
        r_jobs = httpx.get(f"{BASE}/production/jobs", cookies=admin_session, timeout=TIMEOUT)
        assert r_jobs.status_code == 200
        jobs = r_jobs.json()
        if not jobs:
            pytest.skip("No production jobs available to run shortage check")

        jid = jobs[0]["id"]
        # Call shortage endpoint
        r_sh = httpx.post(f"{BASE}/inventory/shortage", json={"job_ids": [jid]},
                          cookies=admin_session, timeout=TIMEOUT)
        assert r_sh.status_code == 200
        res = r_sh.json()
        assert "shortage" in res
        
        # Verify schema decorations exist (even if values are default/blank for existing materials)
        for s in res["shortage"]:
            assert "material_id" in s
            assert "reorder_level" in s
            assert "preferred_vendor_id" in s
            assert "preferred_vendor_name" in s
            assert "rate" in s
