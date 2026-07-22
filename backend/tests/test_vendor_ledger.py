"""Vendor Ledger & Ageing View Tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_vendor_ledger.py -v
"""
import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "Admin@123")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from server import app
    with TestClient(app, base_url="http://testserver/api") as tc:
        r = tc.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert r.status_code == 200, f"Login failed: {r.text}"
        yield tc


def test_vendor_po_receive_partial_payment_ledger_and_ageing(client):
    unique_suffix = uuid.uuid4().hex[:6].upper()

    # 1. Create Vendor
    v_resp = client.post("/vendors", json={
        "name": f"Ledger Test Vendor {unique_suffix}",
        "gstin": "27AAACV9999M1ZX",
        "contact_person": "Ledger Manager",
        "phone": "9876543210",
        "address": "123 Industrial Area",
        "payment_terms_days": 30
    })
    assert v_resp.status_code == 201, v_resp.text
    vendor = v_resp.json()
    vendor_id = vendor["id"]

    # 2. Create Material for Vendor
    m_resp = client.post("/materials", json={
        "code": f"MAT-LED-{unique_suffix}",
        "name": f"Sole Leather Grade A {unique_suffix}",
        "category": "sole",
        "unit": "pair",
        "rate": 200.0,
        "reorder_level": 50.0,
        "preferred_vendor_id": vendor_id
    })
    assert m_resp.status_code == 200, m_resp.text
    material = m_resp.json()
    material_id = material["id"]

    # 3. Create Vendor PO
    po_resp = client.post("/vendor-pos", json={
        "vendor_id": vendor_id,
        "line_items": [
            {
                "material_id": material_id,
                "quantity": 100.0,
                "rate": 200.0,
                "amount": 20000.0
            }
        ],
        "expected_delivery_date": "2026-08-15",
        "notes": "Ledger test purchase order"
    })
    assert po_resp.status_code == 201, po_resp.text
    po = po_resp.json()
    po_id = po["id"]

    # 4. Receive materials against Vendor PO (Receive 100 @ 200 = 20,000)
    rec_resp = client.post(f"/vendor-pos/{po_id}/receive", json={
        "receipt_id": f"REC-{unique_suffix}",
        "items": [
            {
                "material_id": material_id,
                "quantity": 100.0
            }
        ]
    })
    assert rec_resp.status_code == 200, rec_resp.text

    # 5. Check Ledger immediately after Receive (Total Received = 20,000, Total Paid = 0, Current Balance = 20,000)
    leg1_resp = client.get(f"/vendors/{vendor_id}/ledger")
    assert leg1_resp.status_code == 200, leg1_resp.text
    ledger1 = leg1_resp.json()

    assert ledger1["total_received"] == 20000.0
    assert ledger1["total_paid"] == 0.0
    assert ledger1["current_balance"] == 20000.0
    assert len(ledger1["transactions"]) == 1
    assert ledger1["transactions"][0]["type"] == "receive"
    assert ledger1["transactions"][0]["credit"] == 20000.0
    assert ledger1["transactions"][0]["running_balance"] == 20000.0

    # 6. Post Partial Payment of 8,000
    pay_resp = client.post(f"/vendors/{vendor_id}/payments", json={
        "amount": 8000.0,
        "payment_date": "2026-07-22",
        "mode": "Bank Transfer",
        "reference": f"UTR-{unique_suffix}",
        "bank": "HDFC Bank",
        "notes": f"Partial payment for REC-{unique_suffix}"
    })
    assert pay_resp.status_code == 201, pay_resp.text

    # 7. Check Ledger after Partial Payment (Total Received = 20,000, Total Paid = 8,000, Current Balance = 12,000)
    leg2_resp = client.get(f"/vendors/{vendor_id}/ledger")
    assert leg2_resp.status_code == 200, leg2_resp.text
    ledger2 = leg2_resp.json()

    assert ledger2["total_received"] == 20000.0
    assert ledger2["total_paid"] == 8000.0
    assert ledger2["current_balance"] == 12000.0
    assert len(ledger2["transactions"]) == 2

    tx_rec = ledger2["transactions"][0]
    tx_pay = ledger2["transactions"][1]

    assert tx_rec["type"] == "receive"
    assert tx_rec["credit"] == 20000.0
    assert tx_rec["running_balance"] == 20000.0

    assert tx_pay["type"] == "payment"
    assert tx_pay["debit"] == 8000.0
    assert tx_pay["running_balance"] == 12000.0

    # 8. Check Ageing View for All Vendors
    age_resp = client.get("/vendors/ageing")
    assert age_resp.status_code == 200, age_resp.text
    age_data = age_resp.json()

    assert "summary" in age_data
    assert "vendors" in age_data

    v_age = next((v for v in age_data["vendors"] if v["vendor_id"] == vendor_id), None)
    assert v_age is not None
    assert v_age["outstanding_balance"] == 12000.0
    # Sum of buckets should equal outstanding_balance
    bucket_sum = v_age["current"] + v_age["days_1_30"] + v_age["days_31_60"] + v_age["days_60_plus"]
    assert bucket_sum == 12000.0
