"""Tests for Supabase Expense Service and Void/Reversal Handlers."""

import pytest
from unittest.mock import MagicMock, patch

from services.supabase_expense_service import (
    sync_expense_to_supabase,
    void_expense_in_supabase,
    CATEGORY_GL_MAP,
)
from services.supabase_invoice_service import (
    void_invoice_in_supabase,
    reverse_payment_in_supabase,
)
from services.supabase_vendor_bill_service import void_vendor_bill_in_supabase


@pytest.fixture
def mock_supabase():
    client = MagicMock()

    # Default chart of accounts
    coa_data = [
        {"id": "coa-1010", "code": "1010"},
        {"id": "coa-1020", "code": "1020"},
        {"id": "coa-1020-cash", "code": "1020-FACTORY-CASH"},
        {"id": "coa-1030", "code": "1030"},
        {"id": "coa-2010", "code": "2010"},
        {"id": "coa-4010", "code": "4010"},
        {"id": "coa-5010", "code": "5010"},
        {"id": "coa-5020", "code": "5020"},
        {"id": "coa-5030", "code": "5030"},
        {"id": "coa-5040", "code": "5040"},
        {"id": "coa-5050", "code": "5050"},
        {"id": "coa-5060", "code": "5060"},
        {"id": "coa-5070", "code": "5070"},
    ]

    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_execute = MagicMock()
    mock_execute.data = coa_data
    mock_select.execute.return_value = mock_execute
    mock_table.select.return_value = mock_select
    mock_table.upsert.return_value.execute.return_value.data = [{"id": "mock-id"}]
    mock_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "mock-id"}]
    mock_table.delete.return_value.eq.return_value.execute.return_value.data = []

    client.table.return_value = mock_table
    return client


def test_sync_expense_bank(mock_supabase):
    with patch("services.supabase_expense_service.get_supabase_admin_client", return_value=mock_supabase):
        doc = {
            "_id": "603d2bbf1234567890123456",
            "category": "Rent & Utilities",
            "amount": 25000.0,
            "date": "2026-10-14",
            "payee": "Industrial Park Landlord",
            "paid_via": "bank",
            "bank_account_id": "bank-acc-1",
            "notes": "Monthly factory rent"
        }
        res = sync_expense_to_supabase(doc)
        assert res is not None
        mock_supabase.table.assert_any_call("journal_entries")
        mock_supabase.table.assert_any_call("journal_lines")


def test_sync_expense_cash(mock_supabase):
    with patch("services.supabase_expense_service.get_supabase_admin_client", return_value=mock_supabase):
        doc = {
            "_id": "603d2bbf1234567890123457",
            "category": "Office & Administrative",
            "amount": 1500.0,
            "date": "2026-10-14",
            "payee": "Stationery Mart",
            "paid_via": "cash",
            "notes": "Printing paper and supplies"
        }
        res = sync_expense_to_supabase(doc)
        assert res is not None
        mock_supabase.table.assert_any_call("cash_registers")


def test_void_expense(mock_supabase):
    with patch("services.supabase_expense_service.get_supabase_admin_client", return_value=mock_supabase):
        ok = void_expense_in_supabase("603d2bbf1234567890123456", voided_by="admin@example.com")
        assert ok is True
        mock_supabase.table.assert_any_call("journal_entries")


def test_void_invoice(mock_supabase):
    with patch("services.supabase_invoice_service.get_supabase_admin_client", return_value=mock_supabase):
        ok = void_invoice_in_supabase("603d2bbf1234567890123499", voided_by="admin@example.com", reason="Order cancelled")
        assert ok is True
        mock_supabase.table.assert_any_call("sales_invoices")
        mock_supabase.table.assert_any_call("journal_entries")


def test_reverse_payment(mock_supabase):
    with patch("services.supabase_invoice_service.get_supabase_admin_client", return_value=mock_supabase):
        ok = reverse_payment_in_supabase("603d2bbf1234567890123488", reversed_by="admin@example.com", reason="Customer bounce")
        assert ok is True
        mock_supabase.table.assert_any_call("voucher_allocations")
        mock_supabase.table.assert_any_call("payment_vouchers")
        mock_supabase.table.assert_any_call("journal_entries")


def test_void_vendor_bill(mock_supabase):
    with patch("services.supabase_vendor_bill_service.get_supabase_admin_client", return_value=mock_supabase):
        ok = void_vendor_bill_in_supabase("603d2bbf1234567890123477", voided_by="admin@example.com")
        assert ok is True
        mock_supabase.table.assert_any_call("vendor_bills")
        mock_supabase.table.assert_any_call("journal_entries")
