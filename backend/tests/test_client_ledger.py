"""Client Ledger & Ageing View Tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_client_ledger.py -v
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


def test_client_invoice_partial_payment_ledger_and_ageing(client):
    unique_suffix = uuid.uuid4().hex[:6].upper()
    client_name = f"Client Ledger Test {unique_suffix}"

    # 1. Create test invoice via test helper
    inv_resp = client.post("/test-helpers/create-test-invoice", json={
        "invoice_no": f"INV-{unique_suffix}",
        "invoice_date": "22/07/2026",
        "invoice_iso_date": "2026-07-22",
        "due_date": "2026-08-21",
        "payment_terms_days": 30,
        "client_name": client_name,
        "grand_total": 15000.0,
        "net_amount": 15000.0,
    })
    assert inv_resp.status_code == 200, inv_resp.text
    inv_doc = inv_resp.json()
    inv_id = inv_doc["id"]

    # 2. Check Client Ledger immediately after Invoice (Invoiced = 15,000, Received = 0, Balance = 15,000)
    leg1_resp = client.get(f"/clients/{client_name}/ledger")
    assert leg1_resp.status_code == 200, leg1_resp.text
    ledger1 = leg1_resp.json()

    assert ledger1["client_name"] == client_name
    assert ledger1["total_invoiced"] == 15000.0
    assert ledger1["total_received"] == 0.0
    assert ledger1["current_balance"] == 15000.0
    assert len(ledger1["transactions"]) == 1
    assert ledger1["transactions"][0]["debit"] == 15000.0
    assert ledger1["transactions"][0]["running_balance"] == 15000.0

    # 3. Post Partial Payment of 5,000 against the invoice
    pay_resp = client.post("/payments", json={
        "invoice_ids": [inv_id],
        "amount": 5000.0,
        "payment_date": "2026-07-22",
        "mode": "Bank Transfer",
        "reference": f"UTR-CLIENT-{unique_suffix}",
        "bank": "ICICI Bank",
        "notes": f"Partial payment for INV-{unique_suffix}"
    })
    assert pay_resp.status_code == 200, pay_resp.text

    # 4. Check Client Ledger after Partial Payment (Invoiced = 15,000, Received = 5,000, Balance = 10,000)
    leg2_resp = client.get(f"/clients/{client_name}/ledger")
    assert leg2_resp.status_code == 200, leg2_resp.text
    ledger2 = leg2_resp.json()

    assert ledger2["total_invoiced"] == 15000.0
    assert ledger2["total_received"] == 5000.0
    assert ledger2["current_balance"] == 10000.0
    assert len(ledger2["transactions"]) == 2

    tx_inv = ledger2["transactions"][0]
    tx_pay = ledger2["transactions"][1]

    assert tx_inv["debit"] == 15000.0
    assert tx_inv["running_balance"] == 15000.0

    assert tx_pay["credit"] == 5000.0
    assert tx_pay["running_balance"] == 10000.0

    # 5. Check Client Ageing View for All Clients
    age_resp = client.get("/clients/ageing")
    assert age_resp.status_code == 200, age_resp.text
    age_data = age_resp.json()

    assert "summary" in age_data
    assert "clients" in age_data

    c_age = next((c for c in age_data["clients"] if c["client_name"] == client_name), None)
    assert c_age is not None
    assert c_age["outstanding_balance"] == 10000.0
    # Sum of buckets should equal outstanding_balance
    bucket_sum = c_age["current"] + c_age["days_1_30"] + c_age["days_31_60"] + c_age["days_60_plus"]
    assert bucket_sum == 10000.0
