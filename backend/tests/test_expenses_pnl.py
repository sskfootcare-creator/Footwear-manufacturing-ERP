"""Expense Management & Simple P&L tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_expenses_pnl.py -v
"""
import os
import sys
import pytest
import httpx

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "Admin@123")


@pytest.fixture(scope="module")
def client():
    # Try connecting to live server first
    try:
        c = httpx.Client(base_url="http://localhost:8000/api", timeout=10)
        r = c.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        if r.status_code == 200:
            yield c
            return
    except Exception:
        pass

    # Fallback: FastAPI TestClient as context manager (triggers on_event("startup"))
    from fastapi.testclient import TestClient
    from server import app
    with TestClient(app, base_url="http://testserver/api") as tc:
        r = tc.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert r.status_code == 200, f"Login failed: {r.text}"
        yield tc


class TestExpensesAndPNL:

    def test_expense_crud_and_pnl(self, client):
        # 1. Create Expense 1 (Rent & Utilities)
        payload1 = {
            "category": "Rent & Utilities",
            "amount": 15000.0,
            "date": "2026-07-15",
            "payee": "Industrial Estate Maintenance Ltd",
            "notes": "Factory unit rent for July 2026",
            "receipt": {
                "url": "/api/uploads/receipt_rent_july.png",
                "display_url": "/api/uploads/receipt_rent_july.png",
                "thumbnail_url": "/api/uploads/receipt_rent_july.png"
            }
        }
        r1 = client.post("/expenses", json=payload1)
        assert r1.status_code == 200, r1.text
        exp1 = r1.json()
        assert exp1["id"]
        assert exp1["amount"] == 15000.0
        assert exp1["category"] == "Rent & Utilities"
        assert exp1["receipt"]["url"] == "/api/uploads/receipt_rent_july.png"

        # 2. Create Expense 2 (Packaging & Printing)
        payload2 = {
            "category": "Packaging & Printing",
            "amount": 4500.0,
            "date": "2026-07-18",
            "payee": "Standard Packaging Works",
            "notes": "Printed carton boxes",
            "receipt": "/api/uploads/receipt_boxes.jpg"
        }
        r2 = client.post("/expenses", json=payload2)
        assert r2.status_code == 200, r2.text
        exp2 = r2.json()
        assert exp2["id"]

        # 3. List Expenses without filter
        r_list = client.get("/expenses")
        assert r_list.status_code == 200
        all_expenses = r_list.json()
        e_ids = [e["id"] for e in all_expenses]
        assert exp1["id"] in e_ids
        assert exp2["id"] in e_ids

        # 4. Filter by category
        r_cat = client.get("/expenses?category=Rent%20%26%20Utilities")
        assert r_cat.status_code == 200
        cat_expenses = r_cat.json()
        assert all(e["category"] == "Rent & Utilities" for e in cat_expenses)

        # 5. Filter by search query
        r_search = client.get("/expenses?search=Packaging")
        assert r_search.status_code == 200
        search_expenses = r_search.json()
        assert any(e["id"] == exp2["id"] for e in search_expenses)

        # 6. Get single expense
        r_single = client.get(f"/expenses/{exp1['id']}")
        assert r_single.status_code == 200
        assert r_single.json()["payee"] == "Industrial Estate Maintenance Ltd"

        # 7. Update expense
        r_up = client.put(f"/expenses/{exp1['id']}", json={"amount": 16000.0, "notes": "Updated rent amount"})
        assert r_up.status_code == 200
        assert r_up.json()["amount"] == 16000.0

        # 8. Check Simple P&L Endpoint
        r_pnl = client.get("/reports/pnl")
        assert r_pnl.status_code == 200
        pnl_data = r_pnl.json()
        assert "revenue" in pnl_data
        assert "invoices_revenue" in pnl_data
        assert "settlements_revenue" in pnl_data
        assert "material_cost" in pnl_data
        assert "labor_cost" in pnl_data
        assert "expenses" in pnl_data
        assert "gross_profit" in pnl_data
        assert "net_profit" in pnl_data
        assert "category_totals" in pnl_data
        assert "monthly_breakdown" in pnl_data

        # Verify net profit formula: revenue - material_cost - labor_cost - expenses
        rev = pnl_data["revenue"]
        mat = pnl_data["material_cost"]
        lab = pnl_data["labor_cost"]
        exp = pnl_data["expenses"]
        expected_gross = round(rev - mat - lab, 2)
        expected_net = round(rev - mat - lab - exp, 2)
        assert pnl_data["gross_profit"] == expected_gross
        assert pnl_data["net_profit"] == expected_net
        assert pnl_data["expenses"] >= 16000.0 + 4500.0

        # 9. Clean up / Delete expenses
        r_del1 = client.delete(f"/expenses/{exp1['id']}")
        assert r_del1.status_code == 200
        r_del2 = client.delete(f"/expenses/{exp2['id']}")
        assert r_del2.status_code == 200

        # Verify deletion
        r_check = client.get(f"/expenses/{exp1['id']}")
        assert r_check.status_code == 404
