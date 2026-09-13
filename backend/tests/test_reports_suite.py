import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.reports import reports_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, count):
        return self

    async def to_list(self, limit=None):
        return self.docs


class MockReportsDB:
    def __init__(self):
        self.invoices_store = []
        self.online_settlements_detailed_store = []
        self.online_settlements_store = []
        self.vendor_purchase_orders_store = []
        self.vendor_pos_store = []
        self.expenses_store = []
        self.bank_accounts_store = []
        self.cash_accounts_store = []
        self.production_jobs_store = []
        self.materials_store = []
        self.inventory_movements_store = []
        self.defects_store = []
        self.clients_store = []

        self.invoices = MagicMock()
        self.invoices.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.invoices_store, q)))

        self.online_settlements_detailed = MagicMock()
        self.online_settlements_detailed.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.online_settlements_detailed_store, q)))

        self.online_settlements = MagicMock()
        self.online_settlements.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.online_settlements_store, q)))

        self.vendor_purchase_orders = MagicMock()
        self.vendor_purchase_orders.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.vendor_purchase_orders_store, q)))

        self.vendor_pos = MagicMock()
        self.vendor_pos.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.vendor_pos_store, q)))

        self.expenses = MagicMock()
        self.expenses.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.expenses_store, q)))

        self.bank_accounts = MagicMock()
        self.bank_accounts.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.bank_accounts_store, q)))

        self.cash_accounts = MagicMock()
        self.cash_accounts.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.cash_accounts_store, q)))

        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.production_jobs_store, q)))

        self.materials = MagicMock()
        self.materials.find = MagicMock(side_effect=lambda q=None: MockCursor(self.materials_store))

        self.inventory_movements = MagicMock()
        self.inventory_movements.find = MagicMock(side_effect=lambda q=None: MockCursor(self._filter_docs(self.inventory_movements_store, q)))

        self.defects = MagicMock()
        self.defects.find = MagicMock(side_effect=lambda q=None: MockCursor(self.defects_store))

        self.clients = MagicMock()
        self.clients.find = MagicMock(side_effect=lambda q=None: MockCursor(self.clients_store))

    def _filter_docs(self, docs, query):
        if not query:
            return docs
        filtered = []
        for d in docs:
            match = True
            if "status" in query:
                st_q = query["status"]
                if isinstance(st_q, dict) and "$ne" in st_q:
                    if d.get("status") == st_q["$ne"]:
                        match = False
                elif isinstance(st_q, dict) and "$nin" in st_q:
                    if d.get("status") in st_q["$nin"]:
                        match = False
                elif isinstance(st_q, str) and d.get("status") != st_q:
                    match = False
            if "active" in query:
                if d.get("active") != query["active"]:
                    match = False
            if "archived" in query:
                arch_q = query["archived"]
                if isinstance(arch_q, dict) and "$ne" in arch_q:
                    if d.get("archived") == arch_q["$ne"]:
                        match = False
            if match:
                filtered.append(d)
        return filtered


@pytest.fixture
def mock_reports_env(monkeypatch):
    mock_db = MockReportsDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_user(request):
        return {"id": "test_admin", "role": "admin", "username": "admin@test.com"}

    monkeypatch.setattr(server, "get_current_user", mock_user)

    test_app = FastAPI()
    test_app.mongodb = mock_db
    test_app.include_router(reports_router)

    client = TestClient(test_app)
    return client, mock_db


def test_business_summary_and_executive_kpis(mock_reports_env):
    client, db = mock_reports_env

    # Seed B2B Invoice
    db.invoices_store.append({
        "_id": ObjectId(),
        "invoice_number": "INV-2026-001",
        "invoice_date": "2026-09-01",
        "grand_total": 50000.0,
        "paid_amount": 35000.0,
        "balance_due": 15000.0,
        "client_name": "Metro Retailers",
        "created_at": "2026-09-01T10:00:00Z",
    })

    # Seed Online Settlement
    db.online_settlements_detailed_store.append({
        "_id": ObjectId(),
        "settlement_date": "2026-09-05",
        "net_payout": 25000.0,
        "created_at": "2026-09-05T12:00:00Z",
    })

    # Seed Vendor PO
    db.vendor_purchase_orders_store.append({
        "_id": ObjectId(),
        "po_number": "PO-VEN-001",
        "vendor_name": "Super Leather Ltd",
        "total_amount": 30000.0,
        "paid_amount": 20000.0,
        "balance_due": 10000.0,
        "status": "sent",
        "created_at": "2026-09-02T10:00:00Z",
    })

    # Seed Operating Expense
    db.expenses_store.append({
        "_id": ObjectId(),
        "title": "Factory Electricity",
        "category": "Utilities",
        "amount": 8000.0,
        "status": "paid",
        "date": "2026-09-03",
    })

    # Seed Bank and Cash Accounts
    db.bank_accounts_store.append({
        "_id": ObjectId(),
        "account_name": "HDFC Current",
        "current_balance": 120000.0,
        "active": True,
    })
    db.cash_accounts_store.append({
        "_id": ObjectId(),
        "account_name": "Main Factory Petty Cash",
        "current_balance": 15000.0,
        "active": True,
    })

    # Seed Production Jobs
    db.production_jobs_store.append({
        "_id": ObjectId(),
        "job_number": "JOB-001",
        "stage": "lasting",
        "quantity": 200,
        "archived": False,
    })
    db.production_jobs_store.append({
        "_id": ObjectId(),
        "job_number": "JOB-002",
        "stage": "dispatched",
        "quantity": 100,
        "archived": False,
    })

    # Seed Materials
    db.materials_store.append({
        "_id": ObjectId(),
        "code": "LEA-01",
        "name": "Full Grain Leather",
        "balance": 500.0,
        "weighted_avg_rate": 80.0,
        "rate": 80.0,
    })

    res = client.get("/api/reports/business-summary")
    assert res.status_code == 200
    data = res.json()

    assert data["gross_revenue"] == 75000.0  # 50k B2B + 25k online
    assert data["total_b2b_invoiced"] == 50000.0
    assert data["total_online_revenue"] == 25000.0
    assert data["total_procurement"] == 30000.0
    assert data["operating_expenses"] == 8000.0
    assert data["total_liquid_funds"] == 135000.0  # 120k + 15k
    assert data["total_ar_receivables"] == 15000.0
    assert data["total_ap_payables"] == 10000.0
    assert data["pipeline_pairs_count"] == 200
    assert data["dispatched_pairs_count"] == 100
    assert data["inventory_valuation"] == 40000.0  # 500 * 80
    assert len(data["monthly_trend"]) >= 1


def test_inventory_materials_report(mock_reports_env):
    client, db = mock_reports_env

    db.materials_store.extend([
        {
            "_id": ObjectId(),
            "code": "SOLE-TPR-01",
            "name": "TPR Sneaker Sole",
            "category": "Soles",
            "unit": "pairs",
            "balance": 150.0,
            "weighted_avg_rate": 120.0,
            "last_purchase_rate": 125.0,
            "reorder_level": 50.0,
        },
        {
            "_id": ObjectId(),
            "code": "EYE-BRASS",
            "name": "Brass Eyelets",
            "category": "Hardware",
            "unit": "pcs",
            "balance": 20.0,
            "weighted_avg_rate": 2.0,
            "last_purchase_rate": 2.0,
            "reorder_level": 100.0,
        },
        {
            "_id": ObjectId(),
            "code": "TH-NYLON",
            "name": "Bonded Nylon Thread",
            "category": "Threads",
            "unit": "spools",
            "balance": 0.0,
            "weighted_avg_rate": 45.0,
            "last_purchase_rate": 45.0,
            "reorder_level": 10.0,
        },
    ])

    res = client.get("/api/reports/inventory-materials")
    assert res.status_code == 200
    data = res.json()

    assert data["total_items"] == 3
    assert data["total_valuation"] == (150 * 120) + (20 * 2) + 0  # 18000 + 40 = 18040
    assert data["low_stock_count"] == 1  # EYE-BRASS balance 20 <= reorder 100
    assert data["out_of_stock_count"] == 1  # TH-NYLON balance 0
    assert len(data["categories"]) == 3
    assert len(data["materials"]) == 3


def test_production_overview_report(mock_reports_env):
    client, db = mock_reports_env

    db.production_jobs_store.extend([
        {"_id": ObjectId(), "stage": "cutting", "quantity": 100, "archived": False},
        {"_id": ObjectId(), "stage": "stitching", "quantity": 150, "archived": False},
        {"_id": ObjectId(), "stage": "lasting", "quantity": 250, "archived": False},
        {"_id": ObjectId(), "stage": "dispatched", "quantity": 300, "archived": False},
    ])

    db.defects_store.extend([
        {"_id": ObjectId(), "quantity": 5, "defect_type": "Stitching unravel"},
        {"_id": ObjectId(), "quantity": 3, "defect_type": "Sole delamination"},
    ])

    res = client.get("/api/reports/production-overview")
    assert res.status_code == 200
    data = res.json()

    assert data["total_jobs"] == 4
    assert data["active_jobs"] == 3
    assert data["total_pairs_started"] == 800
    assert data["total_pairs_dispatched"] == 300
    assert data["total_defects"] == 2
    assert data["total_rejected_pairs"] == 8
    assert len(data["stage_breakdown"]) == 10


def test_invoices_sales_report(mock_reports_env):
    client, db = mock_reports_env

    db.invoices_store.extend([
        {
            "_id": ObjectId(),
            "invoice_number": "INV-101",
            "invoice_date": "2026-09-01",
            "client_name": "Bata India",
            "grand_total": 100000.0,
            "paid_amount": 100000.0,
            "balance_due": 0.0,
            "total_pairs": 400,
        },
        {
            "_id": ObjectId(),
            "invoice_number": "INV-102",
            "invoice_date": "2026-09-05",
            "client_name": "Relaxo Footwear",
            "grand_total": 80000.0,
            "paid_amount": 30000.0,
            "balance_due": 50000.0,
            "total_pairs": 320,
        },
    ])

    res = client.get("/api/reports/invoices-sales")
    assert res.status_code == 200
    data = res.json()

    assert data["total_invoices"] == 2
    assert data["total_invoiced"] == 180000.0
    assert data["total_paid"] == 130000.0
    assert data["total_balance"] == 50000.0
    assert data["collection_rate_pct"] == round(130000 / 180000 * 100, 2)
    assert len(data["top_clients"]) == 2
    assert data["top_clients"][0]["client_name"] == "Bata India"


def test_vendor_procurement_report(mock_reports_env):
    client, db = mock_reports_env

    db.vendor_purchase_orders_store.extend([
        {
            "_id": ObjectId(),
            "po_number": "VPO-01",
            "vendor_name": "Apex Soles",
            "created_at": "2026-09-01T10:00:00Z",
            "total_amount": 45000.0,
            "paid_amount": 20000.0,
            "balance_due": 25000.0,
            "status": "partially_received",
            "line_items": [
                {"material_id": "mat1", "quantity": 500, "received_quantity": 300}
            ]
        },
        {
            "_id": ObjectId(),
            "po_number": "VPO-02",
            "vendor_name": "Royal Chemicals",
            "created_at": "2026-09-03T10:00:00Z",
            "total_amount": 15000.0,
            "paid_amount": 15000.0,
            "balance_due": 0.0,
            "status": "received",
            "line_items": [
                {"material_id": "mat2", "quantity": 100, "received_quantity": 100}
            ]
        }
    ])

    res = client.get("/api/reports/vendor-procurement")
    assert res.status_code == 200
    data = res.json()

    assert data["total_pos"] == 2
    assert data["total_po_value"] == 60000.0
    assert data["total_paid"] == 35000.0
    assert data["total_balance_due"] == 25000.0
    assert data["total_ordered_qty"] == 600
    assert data["total_received_qty"] == 400
    assert data["fulfillment_rate_pct"] == round(400 / 600 * 100, 2)
    assert "0_30" in data["ap_aging"]


def test_client_receivables_report(mock_reports_env):
    client, db = mock_reports_env

    cid1 = str(ObjectId())
    db.clients_store.append({
        "_id": ObjectId(cid1),
        "name": "Woodland Footwear",
        "contact_person": "Mr. Sharma",
        "phone": "9876543210",
        "payment_terms_days": 30,
    })

    db.invoices_store.append({
        "_id": ObjectId(),
        "client_id": cid1,
        "client_name": "Woodland Footwear",
        "invoice_number": "INV-W-01",
        "invoice_date": "2026-09-01",
        "grand_total": 90000.0,
        "paid_amount": 40000.0,
        "balance_due": 50000.0,
    })

    res = client.get("/api/reports/client-receivables")
    assert res.status_code == 200
    data = res.json()

    assert data["total_clients"] >= 1
    assert data["total_invoiced"] == 90000.0
    assert data["total_paid"] == 40000.0
    assert data["total_outstanding"] == 50000.0
    assert "0_30" in data["ar_aging"]
    assert data["clients"][0]["name"] == "Woodland Footwear"


def test_pnl_detailed_report(mock_reports_env):
    client, db = mock_reports_env

    # Invoices for revenue
    db.invoices_store.append({
        "_id": ObjectId(),
        "grand_total": 120000.0,
        "invoice_date": "2026-09-01",
    })
    # POs for COGS
    db.vendor_purchase_orders_store.append({
        "_id": ObjectId(),
        "total_amount": 50000.0,
        "status": "received",
        "created_at": "2026-09-02T10:00:00Z",
    })
    # Expenses for OPEX
    db.expenses_store.append({
        "_id": ObjectId(),
        "category": "Rent & Factory Lease",
        "amount": 25000.0,
        "status": "paid",
        "date": "2026-09-05",
    })

    res = client.get("/api/reports/pnl-detailed")
    assert res.status_code == 200
    data = res.json()

    assert data["gross_revenue"] == 120000.0
    assert data["material_cogs"] == 50000.0
    assert data["gross_profit"] == 70000.0
    assert data["total_opex"] == 25000.0
    assert data["net_profit"] == 45000.0
    assert len(data["expense_categories"]) == 1
    assert data["expense_categories"][0]["category"] == "Rent & Factory Lease"
