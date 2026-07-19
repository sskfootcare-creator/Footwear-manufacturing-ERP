"""Iteration 17 — Vendor PO Material Receiving & Idempotency Tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_receiving.py -v
"""
import os
import pytest
import httpx
import uuid

BASE = "http://localhost:8000/api"
TIMEOUT = 15

# Use seeded admin credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "Admin@123")


def admin_cookies() -> dict:
    r = httpx.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=TIMEOUT)
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
                       "name": "Receiving Test Vendor",
                       "gstin": "27AADCB1111M1ZX",
                       "contact_person": "Vendor Contact",
                       "phone": "9876543210",
                       "address": "Vendor Address",
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
                       "code": "RCV-MAT-01",
                       "name": "Receiving Test Material",
                       "category": "upper",
                       "unit": "sqft",
                       "rate": 100.0,
                       "reorder_level": 5.0,
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


class TestVendorPOReceiving:

    def test_partial_and_full_receiving_with_idempotency(self, admin_session, test_vendor, test_material):
        # 1. Create a Vendor PO
        po_payload = {
            "vendor_id": test_vendor["id"],
            "line_items": [
                {
                    "material_id": test_material["id"],
                    "quantity": 100.0,
                    "rate": 100.0,
                    "amount": 10000.0
                }
            ],
            "status": "sent",
            "expected_delivery_date": "2026-09-01",
            "notes": "Receiving Test PO"
        }
        r = httpx.post(f"{BASE}/vendor-pos", json=po_payload, cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        po = r.json()
        po_id = po["id"]
        assert po["status"] == "sent"
        assert po["line_items"][0]["received_quantity"] == 0.0

        # Check initial inventory balance for this material
        r_inv = httpx.get(f"{BASE}/inventory", cookies=admin_session, timeout=TIMEOUT)
        assert r_inv.status_code == 200
        initial_bal = 0.0
        for item in r_inv.json():
            if item["material_id"] == test_material["id"]:
                initial_bal = item["balance"]
                break

        # 2. Receive 40 units (partial receipt)
        receipt1_id = f"rcpt_{uuid.uuid4().hex[:10]}"
        receive_payload = {
            "receipt_id": receipt1_id,
            "items": [
                {
                    "material_id": test_material["id"],
                    "quantity": 40.0
                }
            ]
        }
        r_rec1 = httpx.post(f"{BASE}/vendor-pos/{po_id}/receive", json=receive_payload, cookies=admin_session, timeout=TIMEOUT)
        assert r_rec1.status_code == 200, r_rec1.text
        po_updated = r_rec1.json()
        assert po_updated["status"] == "partially_received"
        assert po_updated["line_items"][0]["received_quantity"] == 40.0

        # Verify inventory movement was created and balance updated
        r_inv = httpx.get(f"{BASE}/inventory", cookies=admin_session, timeout=TIMEOUT)
        assert r_inv.status_code == 200
        new_bal = 0.0
        for item in r_inv.json():
            if item["material_id"] == test_material["id"]:
                new_bal = item["balance"]
                break
        assert new_bal == initial_bal + 40.0

        # 3. Test Idempotency: retry the same receipt1_id
        r_rec_dup = httpx.post(f"{BASE}/vendor-pos/{po_id}/receive", json=receive_payload, cookies=admin_session, timeout=TIMEOUT)
        assert r_rec_dup.status_code == 200, r_rec_dup.text
        po_dup = r_rec_dup.json()
        assert po_dup["line_items"][0]["received_quantity"] == 40.0  # remains 40 (no double count)

        # Verify inventory balance has NOT increased further
        r_inv = httpx.get(f"{BASE}/inventory", cookies=admin_session, timeout=TIMEOUT)
        assert r_inv.status_code == 200
        dup_bal = 0.0
        for item in r_inv.json():
            if item["material_id"] == test_material["id"]:
                dup_bal = item["balance"]
                break
        assert dup_bal == initial_bal + 40.0

        # 4. Receive the remaining 60 units (full receipt)
        receipt2_id = f"rcpt_{uuid.uuid4().hex[:10]}"
        receive_payload_full = {
            "receipt_id": receipt2_id,
            "items": [
                {
                    "material_id": test_material["id"],
                    "quantity": 60.0
                }
            ]
        }
        r_rec2 = httpx.post(f"{BASE}/vendor-pos/{po_id}/receive", json=receive_payload_full, cookies=admin_session, timeout=TIMEOUT)
        assert r_rec2.status_code == 200, r_rec2.text
        po_full = r_rec2.json()
        assert po_full["status"] == "received"
        assert po_full["line_items"][0]["received_quantity"] == 100.0

        # Verify inventory balance updated to reflect full receipt
        r_inv = httpx.get(f"{BASE}/inventory", cookies=admin_session, timeout=TIMEOUT)
        assert r_inv.status_code == 200
        final_bal = 0.0
        for item in r_inv.json():
            if item["material_id"] == test_material["id"]:
                final_bal = item["balance"]
                break
        assert final_bal == initial_bal + 100.0

        # Clean up Vendor PO
        httpx.delete(f"{BASE}/vendor-pos/{po_id}", cookies=admin_session, timeout=TIMEOUT)
