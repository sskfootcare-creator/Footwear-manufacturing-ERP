"""Recurring Expenses & Auto-generation Tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_recurring_expenses.py -v
"""
import os
import sys
import uuid
import pytest
from datetime import datetime, timezone

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


def test_recurring_expense_lifecycle_and_pnl(client):
    unique_suffix = uuid.uuid4().hex[:6].upper()

    # 1. Create monthly recurring Rent template (due_day = 1, past due date)
    rent_payload = {
        "category": "Rent",
        "payee": f"Landlord {unique_suffix}",
        "amount": 50000.0,
        "frequency": "monthly",
        "start_date": "2026-07-01",
        "due_day": 1,
        "active": True,
        "notes": "Factory rent"
    }
    r_rent = client.post("/expenses/recurring", json=rent_payload)
    assert r_rent.status_code == 201, r_rent.text
    rent_tmpl = r_rent.json()
    rent_tmpl_id = rent_tmpl["id"]

    # 2. Check Due Queue (Overdue flag should fire for Rent because due_day=1 is past)
    r_queue = client.get("/expenses/due-queue")
    assert r_queue.status_code == 200, r_queue.text
    due_queue = r_queue.json()

    rent_entry = next((e for e in due_queue if e.get("recurring_expense_id") == rent_tmpl_id), None)
    assert rent_entry is not None, "Auto-generated rent expense not found in due queue"
    assert rent_entry["status"] == "overdue"
    assert rent_entry["amount"] == 50000.0
    assert rent_entry["is_recurring"] is True

    # 3. Create monthly recurring Electricity template (base amount = 10,000, due_day = 28)
    elec_payload = {
        "category": "Electricity",
        "payee": f"State Power {unique_suffix}",
        "amount": 10000.0,
        "frequency": "monthly",
        "start_date": "2026-07-01",
        "due_day": 28,
        "active": True,
        "notes": "Variable power bill"
    }
    r_elec = client.post("/expenses/recurring", json=elec_payload)
    assert r_elec.status_code == 201, r_elec.text
    elec_tmpl = r_elec.json()
    elec_tmpl_id = elec_tmpl["id"]

    r_queue2 = client.get("/expenses/due-queue")
    assert r_queue2.status_code == 200, r_queue2.text
    elec_entry = next((e for e in r_queue2.json() if e.get("recurring_expense_id") == elec_tmpl_id), None)
    assert elec_entry is not None, "Auto-generated electricity expense not found in due queue"
    assert elec_entry["status"] in ["due", "overdue"]
    assert elec_entry["amount"] == 10000.0  # pre-filled base amount

    # 4. Confirm edit-before-confirm works (adjust electricity amount from 10,000 to 12,500 before confirming)
    elec_id = elec_entry["id"]
    r_confirm_elec = client.post(f"/expenses/{elec_id}/confirm", json={
        "amount": 12500.0,
        "notes": "Adjusted July actual meter reading"
    })
    assert r_confirm_elec.status_code == 200, r_confirm_elec.text
    confirmed_elec = r_confirm_elec.json()
    assert confirmed_elec["status"] == "confirmed"
    assert confirmed_elec["amount"] == 12500.0

    # 5. Confirm Rent expense without edits
    rent_id = rent_entry["id"]
    r_confirm_rent = client.post(f"/expenses/{rent_id}/confirm", json={})
    assert r_confirm_rent.status_code == 200, r_confirm_rent.text
    confirmed_rent = r_confirm_rent.json()
    assert confirmed_rent["status"] == "confirmed"
    assert confirmed_rent["amount"] == 50000.0

    # 6. Verify P&L report breakdown & single-counting
    r_pnl = client.get("/expenses/pnl")
    assert r_pnl.status_code == 200, r_pnl.text
    pnl = r_pnl.json()

    assert "recurring_expenses" in pnl
    assert "variable_expenses" in pnl
    assert pnl["recurring_expenses"] >= 62500.0  # 50,000 rent + 12,500 electricity

    # Ensure queue no longer contains confirmed expenses
    r_queue3 = client.get("/expenses/due-queue")
    queue3_ids = [e["id"] for e in r_queue3.json()]
    assert rent_id not in queue3_ids
    assert elec_id not in queue3_ids
