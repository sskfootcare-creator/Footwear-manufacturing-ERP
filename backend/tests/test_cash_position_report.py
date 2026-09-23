"""Unit tests for /api/reports/cash-position endpoint."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.reports import reports_router


@pytest.fixture
def client_app():
    app = FastAPI()
    app.include_router(reports_router)

    # Mock user
    async def mock_user(request):
        return {"email": "admin@ssk.com", "role": "admin", "name": "Admin"}

    app.state.mock_user = mock_user
    return app


def test_report_cash_position_supabase_unconfigured(client_app):
    with patch("routes.reports._get_user", return_value={"role": "admin"}), \
         patch("routes.reports.get_supabase_admin_client", return_value=None):
        client = TestClient(client_app)
        res = client.get("/api/reports/cash-position")
        assert res.status_code == 503
        assert "Supabase not configured" in res.text


def test_report_cash_position_success(client_app):
    mock_sb = MagicMock()

    # Mock bank_accounts
    mock_accounts_table = MagicMock()
    mock_accounts_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "acc-1",
                "account_name": "HDFC Primary",
                "bank_name": "HDFC",
                "account_number_last4": "1234",
                "category": "OPERATING",
                "current_cleared_balance": 150000.50,
            },
            {
                "id": "acc-2",
                "account_name": "ICICI Secondary",
                "bank_name": "ICICI",
                "account_number_last4": "5678",
                "category": "SAVINGS",
                "current_cleared_balance": 75000.00,
            }
        ]
    )

    # Mock bank_statement_lines
    mock_lines_table = MagicMock()
    mock_lines_table.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
        count=3
    )

    # Mock bank_reconciliation_statements
    mock_recon_table = MagicMock()
    mock_recon_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"as_of_date": "2026-09-20", "is_balanced": True}]
    )

    def table_router(tbl):
        if tbl == "bank_accounts":
            return mock_accounts_table
        elif tbl == "bank_statement_lines":
            return mock_lines_table
        elif tbl == "bank_reconciliation_statements":
            return mock_recon_table
        return MagicMock()

    mock_sb.table.side_effect = table_router

    with patch("routes.reports._get_user", return_value={"role": "admin"}), \
         patch("routes.reports.get_supabase_admin_client", return_value=mock_sb):
        client = TestClient(client_app)
        res = client.get("/api/reports/cash-position")
        assert res.status_code == 200
        data = res.json()
        assert data["total_cash_position"] == 225000.50
        assert len(data["accounts"]) == 2
        assert data["total_unreconciled_lines"] == 6
        assert data["accounts"][0]["account_name"] == "HDFC Primary"
        assert data["accounts"][0]["last_reconciliation_balanced"] is True
