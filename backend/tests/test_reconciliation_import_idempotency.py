import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from server import app


@pytest.fixture
def client_app():
    return TestClient(app)


def test_monthly_report_import_repeated_noop(client_app):
    """DB-008 Acceptance Criteria:
    Repeated imports are no-ops; partial files can resume safely;
    every skipped duplicate is visible to the operator.
    """
    mock_db = MagicMock()
    stored_reports = {}

    async def mock_find_one(query):
        row_hash = query.get("row_hash")
        return stored_reports.get(row_hash)

    async def mock_insert_many(docs):
        for d in docs:
            stored_reports[d["row_hash"]] = d
        return MagicMock(inserted_ids=[d["row_hash"] for d in docs])

    mock_db.online_monthly_order_reports.find_one = AsyncMock(side_effect=mock_find_one)
    mock_db.online_monthly_order_reports.insert_many = AsyncMock(side_effect=mock_insert_many)
    mock_db.audit_logs.insert_one = AsyncMock()

    csv_data = (
        "seller order id,order release id,sku id,style id,seller sku code,size,order status,packed on,final amount,seller price\n"
        "ORD1001,REL001,SKU001,STY001,SSK-BOOTS-01,8,DELIVERED,2026-09-01,1500.0,1200.0\n"
        "ORD1002,REL002,SKU002,STY001,SSK-BOOTS-02,9,SHIPPED,2026-09-02,1600.0,1300.0\n"
    )

    headers = {"Authorization": "Bearer test-token"}

    with patch("routes.online_reconciliation._get_user", AsyncMock(return_value={"email": "recon_mgr@ssk.com", "role": "admin"})), \
         patch("routes.online_reconciliation.log_activity_db", AsyncMock()):

        # 1st import: 2 inserted, 0 skipped
        files = {"file": ("monthly_recon_sept.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        app.mongodb = mock_db
        res1 = client_app.post("/api/online-reconciliation/import-monthly-report", files=files, headers=headers)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["ok"] is True
        assert data1["count"] == 2
        assert data1["skipped_duplicates"] == 0
        assert "file_hash" in data1

        # 2nd import of exact same file: 0 inserted, 2 skipped (no-op)
        files = {"file": ("monthly_recon_sept.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res2 = client_app.post("/api/online-reconciliation/import-monthly-report", files=files, headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["ok"] is True
        assert data2["count"] == 0
        assert data2["skipped_duplicates"] == 2
        assert data2["file_hash"] == data1["file_hash"]

        # Exactly 2 unique records stored in database
        assert len(stored_reports) == 2
