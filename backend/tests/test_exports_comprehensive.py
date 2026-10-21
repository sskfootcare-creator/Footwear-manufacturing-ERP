"""Comprehensive Unit & Integration Tests for Excel (.xlsx) and CSV (.csv) Exports across all modules."""

import io
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from bson import ObjectId
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from services.export_service import (
    generate_csv_bytes,
    generate_excel_workbook,
    build_export_response,
)
from routes.invoice_packing import invoice_packing_router
from routes.pos import pos_router
from routes.vendors import vendors_router
from routes.materials import materials_router


# ---------------------------------------------------------------------------
# 1. Export Service Unit Tests
# ---------------------------------------------------------------------------

def test_generate_csv_bytes():
    headers = ["Invoice #", "Client", "Amount (₹)", "Status"]
    rows = [
        ["INV-001", "Acme Retail, LLC", 15000.5, "paid"],
        ["INV-002", "Globex \"Corp\"", 2400.0, "overdue"],
        ["INV-003", None, 0.0, "pending"],
    ]
    csv_bytes = generate_csv_bytes(headers, rows)
    assert csv_bytes.startswith(b"\xef\xbb\xbf"), "Must begin with UTF-8 BOM"
    text = csv_bytes.decode("utf-8")
    assert "Invoice #" in text
    assert '"Acme Retail, LLC"' in text
    assert '"Globex ""Corp"""' in text
    assert "INV-001" in text
    assert "15000.5" in text


def test_generate_excel_workbook():
    headers = ["PO #", "Customer", "Pairs", "Gross (₹)", "Status"]
    rows = [
        ["PO-101", "Bata India", 1200, 450000.0, "active"],
        ["PO-102", "Relaxo Footwear", 800, 320000.0, "overdue"],
    ]
    summary_kpis = {
        "Total POs": 2,
        "Total Pairs": 2000,
        "Total Value": 770000.0,
    }
    xlsx_bytes = generate_excel_workbook(
        title="Test Purchase Orders",
        headers=headers,
        rows=rows,
        summary_kpis=summary_kpis,
        currency_col_indices=[4],
        total_col_indices=[3, 4],
        sheet_name="TestSheet",
    )
    assert xlsx_bytes.startswith(b"PK\x03\x04"), "Excel workbook must have zip/xlsx header PK"
    assert len(xlsx_bytes) > 1000


def test_build_export_response_xlsx():
    resp = build_export_response(
        filename_base="test_export",
        title="Test Title",
        headers=["A", "B"],
        rows=[[1, 2]],
        format="xlsx",
    )
    assert resp.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "test_export_" in resp.headers["Content-Disposition"]
    assert resp.headers["Content-Disposition"].endswith('.xlsx"')


def test_build_export_response_csv():
    resp = build_export_response(
        filename_base="test_csv_export",
        title="Test Title",
        headers=["A", "B"],
        rows=[[1, 2]],
        format="csv",
    )
    assert resp.media_type == "text/csv; charset=utf-8"
    assert "test_csv_export_" in resp.headers["Content-Disposition"]
    assert resp.headers["Content-Disposition"].endswith('.csv"')


# ---------------------------------------------------------------------------
# 2. Route Integration Tests with FastAPI TestClient
# ---------------------------------------------------------------------------

class MockCursor:
    def __init__(self, items):
        self._items = items

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, limit=1000):
        return self._items[:limit]


class MockCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, *args, **kwargs):
        return MockCursor(self.docs)

    async def find_one(self, query, *args, **kwargs):
        for d in self.docs:
            if "_id" in query and d.get("_id") == query["_id"]:
                return d
            if "name" in query and d.get("name") == query["name"]:
                return d
        return self.docs[0] if self.docs else None


@pytest.fixture
def export_test_app():
    app = FastAPI()
    app.include_router(invoice_packing_router)
    app.include_router(pos_router)
    app.include_router(vendors_router)
    app.include_router(materials_router)

    # Mock user in request state
    mock_user = {
        "id": "test_user_id",
        "email": "admin@sskfootcare.com",
        "name": "Admin Tester",
        "role": "admin",
        "roles": ["admin", "manager", "sales", "production"],
    }

    @app.middleware("http")
    async def attach_mock_user(request: Request, call_next):
        request.state.user = mock_user
        return await call_next(request)

    app.state.get_current_user = AsyncMock(return_value=mock_user)

    # Mock Database
    mock_db = MagicMock()
    app.mongodb = mock_db
    import server
    server.db = mock_db

    # Invoices doc
    inv_id = ObjectId()
    mock_db.invoices = MockCollection([
        {
            "_id": inv_id,
            "invoice_no": "INV-2026-001",
            "invoice_date": "2026-03-01",
            "due_date": "2026-03-15",
            "client_name": "Liberty Shoes Ltd",
            "client_gstin": "07AAAAA0000A1Z5",
            "total_quantity": 500,
            "grand_total": 250000.0,
            "net_amount": 250000.0,
            "received_amount": 50000.0,
            "status": "overdue",
            "payment_terms_days": 15,
        }
    ])
    mock_db.payments = MockCollection([])
    mock_db.grns = MockCollection([])
    mock_db.clients = MockCollection([
        {
            "_id": ObjectId(),
            "company_name": "Liberty Shoes Ltd",
            "contact_person": "Rajesh Kumar",
            "phone": "9876543210",
            "gstin": "07AAAAA0000A1Z5",
            "state": "Delhi",
        }
    ])
    mock_db.pos = MockCollection([
        {
            "_id": ObjectId(),
            "po_number": "PO-SSK-9901",
            "po_date": "2026-02-10",
            "delivery_date": "2026-03-30",
            "client_name": "Liberty Shoes Ltd",
            "total_quantity": 1000,
            "total_amount": 500000.0,
            "status": "active",
            "is_completed": False,
            "line_items": [],
            "notes": "Urgent summer collection",
        }
    ])
    mock_db.vendors = MockCollection([
        {
            "_id": ObjectId(),
            "name": "Super Tannery Kanpur",
            "contact_person": "Imran Khan",
            "phone": "9811223344",
            "email": "imran@supertannery.com",
            "gstin": "09BBBBB1111B1Z2",
            "payment_terms_days": 30,
            "active": True,
        }
    ])
    mock_db.vendor_purchase_orders = MockCollection([
        {
            "_id": ObjectId(),
            "po_number": "VPO-2026-042",
            "vendor_id": "vendor123",
            "created_at": "2026-02-15T10:00:00Z",
            "expected_delivery_date": "2026-03-01",
            "status": "sent",
            "total_amount": 120000.0,
            "line_items": [
                {"material_name": "Full Grain Leather Black", "quantity": 500, "rate": 240}
            ],
            "notes": "Grade A leather only",
        }
    ])
    mock_db.vendor_po_receives = MockCollection([])
    mock_db.materials = MockCollection([
        {
            "_id": ObjectId(),
            "code": "MAT-LTH-01",
            "name": "Full Grain Leather Black",
            "category": "leather",
            "color": "Black",
            "unit": "sqft",
            "rate": 240.0,
            "current_stock": 1500.0,
            "balance": 1500.0,
            "reorder_level": 500.0,
        }
    ])
    mock_db.inventory_movements = MockCollection([])
    mock_db.defects = MockCollection([
        {
            "_id": ObjectId(),
            "created_at": "2026-03-05T12:00:00Z",
            "po_number": "PO-SSK-9901",
            "style_code": "SSK-RUN-01",
            "stage": "stitching",
            "defect_type": "Workmanship",
            "quantity": 12,
            "action": "rework",
            "status": "open",
            "notes": "Loose upper stitching on heel",
        }
    ])
    mock_db.workers = MockCollection([])

    return TestClient(app)


def test_export_invoices_endpoints(export_test_app):
    # 1. Export All Invoices (XLSX)
    res_xlsx = export_test_app.get("/api/invoices/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_Invoices_Export" in res_xlsx.headers["content-disposition"]

    # 2. Export Overdue Invoices (CSV)
    res_csv = export_test_app.get("/api/invoices/export?status=overdue&format=csv")
    assert res_csv.status_code == 200
    assert res_csv.content.startswith(b"\xef\xbb\xbf")
    assert "SSK_Overdue_Invoices" in res_csv.headers["content-disposition"]
    csv_text = res_csv.content.decode("utf-8")
    assert "Invoice #" in csv_text
    assert "INV-2026-001" in csv_text
    assert "Liberty Shoes Ltd" in csv_text


def test_export_pos_endpoints(export_test_app):
    res_xlsx = export_test_app.get("/api/pos/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_Customer_POs" in res_xlsx.headers["content-disposition"]

    res_csv = export_test_app.get("/api/pos/export?format=csv")
    assert res_csv.status_code == 200
    assert res_csv.content.startswith(b"\xef\xbb\xbf")
    assert "PO-SSK-9901" in res_csv.content.decode("utf-8")


def test_export_clients_endpoints(export_test_app):
    res_xlsx = export_test_app.get("/api/clients/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_Clients_Receivables" in res_xlsx.headers["content-disposition"]

    res_csv = export_test_app.get("/api/clients/export?format=csv")
    assert res_csv.status_code == 200
    assert "Liberty Shoes Ltd" in res_csv.content.decode("utf-8")


def test_export_client_ledger_endpoint(export_test_app):
    res = export_test_app.get("/api/clients/Liberty%20Shoes%20Ltd/ledger/export?format=xlsx")
    assert res.status_code == 200
    assert res.content.startswith(b"PK\x03\x04")
    assert "SSK_Ledger_Liberty_Shoes_Ltd" in res.headers["content-disposition"]


def test_export_vendors_endpoints(export_test_app):
    res_xlsx = export_test_app.get("/api/vendors/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_Vendors_Payables" in res_xlsx.headers["content-disposition"]

    res_csv = export_test_app.get("/api/vendors/export?format=csv")
    assert res_csv.status_code == 200
    assert "Super Tannery Kanpur" in res_csv.content.decode("utf-8")


def test_export_vendor_pos_endpoints(export_test_app):
    res_xlsx = export_test_app.get("/api/vendor-pos/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_Vendor_Purchase_Orders" in res_xlsx.headers["content-disposition"]

    res_csv = export_test_app.get("/api/vendor-pos/export?format=csv")
    assert res_csv.status_code == 200
    assert "VPO-2026-042" in res_csv.content.decode("utf-8")


def test_export_inventory_endpoints(export_test_app):
    res_xlsx = export_test_app.get("/api/inventory/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_Inventory_Valuation" in res_xlsx.headers["content-disposition"]

    res_csv = export_test_app.get("/api/inventory/export?format=csv")
    assert res_csv.status_code == 200
    assert "MAT-LTH-01" in res_csv.content.decode("utf-8")


def test_export_defects_endpoints(export_test_app):
    res_xlsx = export_test_app.get("/api/defects/export?format=xlsx")
    assert res_xlsx.status_code == 200
    assert res_xlsx.content.startswith(b"PK\x03\x04")
    assert "SSK_QC_Defects_Log" in res_xlsx.headers["content-disposition"]

    res_csv = export_test_app.get("/api/defects/export?format=csv")
    assert res_csv.status_code == 200
    assert "PO-SSK-9901" in res_csv.content.decode("utf-8")
    assert "Workmanship" in res_csv.content.decode("utf-8")
