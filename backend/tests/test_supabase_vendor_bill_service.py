"""Tests for Supabase Vendor Bills & Payments Service (services/supabase_vendor_bill_service.py)."""

import pytest
from unittest.mock import MagicMock, patch
from services.supabase_vendor_bill_service import (
    to_uuid,
    ensure_vendor_entity,
    sync_vendor_po_to_supabase,
    sync_vendor_payment_to_supabase,
    ensure_cash_register,
)


@pytest.fixture
def mock_supabase():
    client = MagicMock()

    # Mock chart_of_accounts
    coa_data = [
        {"code": "1010", "id": "uuid-coa-1010-bank"},
        {"code": "1020", "id": "uuid-coa-1020-cash"},
        {"code": "1020-FACTORY-CASH", "id": "uuid-coa-1020-fcash"},
        {"code": "1040", "id": "uuid-coa-1040-inventory"},
        {"code": "1060-CGST-IN", "id": "uuid-coa-1060-cgst"},
        {"code": "1060-SGST-IN", "id": "uuid-coa-1060-sgst"},
        {"code": "1060-IGST-IN", "id": "uuid-coa-1060-igst"},
        {"code": "2010", "id": "uuid-coa-2010-ap"},
        {"code": "5010", "id": "uuid-coa-5010-cogs"},
    ]
    coa_mock = MagicMock()
    coa_mock.select.return_value.execute.return_value = MagicMock(data=coa_data)

    def table_router(name):
        tbl = MagicMock()
        if name == "chart_of_accounts":
            return coa_mock

        def mock_upsert(row, *args, **kwargs):
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[row] if isinstance(row, dict) else row)
            return m

        tbl.upsert.side_effect = mock_upsert
        tbl.insert.side_effect = mock_upsert
        tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
        tbl.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=[])
        return tbl

    client.table.side_effect = table_router
    return client


def test_to_uuid_deterministic():
    u1 = to_uuid("507f1f77bcf86cd799439011")
    u2 = to_uuid("507f1f77bcf86cd799439011")
    assert u1 == u2
    assert len(u1) == 36


def test_ensure_vendor_entity(mock_supabase):
    coa_map = {
        "2010": "uuid-coa-2010-ap",
    }
    vendor_data = {
        "id": "507f1f77bcf86cd799439011",
        "name": "Apex Leather Supplies",
        "gstin": "09AAAAA0000A1Z5",
        "payment_terms_days": 45,
    }
    v_uuid = ensure_vendor_entity(mock_supabase, vendor_data, coa_map)
    assert v_uuid is not None

    table_call = mock_supabase.table.call_args_list
    assert any(call[0][0] == "financial_entities" for call in table_call)


def test_sync_vendor_po_to_supabase(mock_supabase):
    po_doc = {
        "id": "507f1f77bcf86cd799439022",
        "po_number": "PO-VEN-2026-001",
        "receipt_id": "GRN-2026-0001",
        "receipt_date": "2026-09-23",
        "vendor_id": "507f1f77bcf86cd799439011",
        "vendor_name": "Apex Leather Supplies",
        "total_amount": 10500.0,
        "cgst_amount": 250.0,
        "sgst_amount": 250.0,
        "igst_amount": 0.0,
        "subtotal": 10000.0,
        "by": "test@ssk.com",
    }
    vendor_doc = {
        "id": "507f1f77bcf86cd799439011",
        "name": "Apex Leather Supplies",
        "payment_terms_days": 30,
    }

    with patch("services.supabase_vendor_bill_service.get_supabase_admin_client", return_value=mock_supabase):
        res = sync_vendor_po_to_supabase(po_doc, vendor_doc)
        assert res is not None
        assert res["total_amount"] == 10500.0
        assert res["status"] == "POSTED"
        assert res["vendor_po_ref"] == "PO-VEN-2026-001"


def test_sync_vendor_payment_to_supabase(mock_supabase):
    payment_doc = {
        "id": "507f1f77bcf86cd799439099",
        "payment_no": "PAY-2026-0005",
        "payment_date": "2026-09-23",
        "amount": 5000.0,
        "mode": "NEFT",
        "bank_account_id": "507f1f77bcf86cd799439088",
        "vendor_id": "507f1f77bcf86cd799439011",
        "vendor_name": "Apex Leather Supplies",
        "vendor_po_number": "PO-VEN-2026-001",
        "by": "test@ssk.com",
    }
    vendor_doc = {
        "id": "507f1f77bcf86cd799439011",
        "name": "Apex Leather Supplies",
    }

    bills_mock = MagicMock()
    bills_mock.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "bill-uuid-1",
                "bill_no": "GRN-2026-0001",
                "total_amount": 10500.0,
                "paid_amount": 0.0,
                "status": "POSTED",
                "vendor_po_ref": "PO-VEN-2026-001",
                "bill_date": "2026-09-20",
            }
        ]
    )

    def table_router(name):
        tbl = MagicMock()
        if name == "vendor_bills":
            return bills_mock
        if name == "chart_of_accounts":
            coa_mock = MagicMock()
            coa_mock.select.return_value.execute.return_value = MagicMock(
                data=[
                    {"code": "1010", "id": "uuid-coa-1010-bank"},
                    {"code": "1020", "id": "uuid-coa-1020-cash"},
                    {"code": "2010", "id": "uuid-coa-2010-ap"},
                ]
            )
            return coa_mock

        def mock_upsert(row, *args, **kwargs):
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[row] if isinstance(row, dict) else row)
            return m

        tbl.upsert.side_effect = mock_upsert
        return tbl

    mock_supabase.table.side_effect = table_router

    with patch("services.supabase_vendor_bill_service.get_supabase_admin_client", return_value=mock_supabase):
        res = sync_vendor_payment_to_supabase(payment_doc, vendor_doc)
        assert res is not None

        # Verify allocation and bill update occurred
        assert bills_mock.update.called
        update_args = bills_mock.update.call_args[0][0]
        assert update_args["paid_amount"] == 5000.0
        assert update_args["status"] == "PARTIALLY_PAID"


def test_sync_vendor_payment_cash(mock_supabase):
    payment_doc = {
        "id": "507f1f77bcf86cd799439098",
        "payment_no": "PAY-CASH-001",
        "payment_date": "2026-09-23",
        "amount": 1000.0,
        "mode": "Cash",
        "account_type": "cash",
        "vendor_id": "507f1f77bcf86cd799439011",
        "vendor_name": "Apex Leather Supplies",
        "by": "test@ssk.com",
    }
    vendor_doc = {
        "id": "507f1f77bcf86cd799439011",
        "name": "Apex Leather Supplies",
    }

    with patch("services.supabase_vendor_bill_service.get_supabase_admin_client", return_value=mock_supabase):
        res = sync_vendor_payment_to_supabase(payment_doc, vendor_doc)
        assert res is not None
        assert res["payment_mode"] == "CASH"
