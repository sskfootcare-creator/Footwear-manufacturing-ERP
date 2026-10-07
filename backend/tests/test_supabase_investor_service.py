"""Tests for Supabase Investor Ledger Service (services/supabase_investor_service.py)."""

import pytest
from unittest.mock import MagicMock, patch
from services.supabase_investor_service import (
    ensure_investor_gl_accounts,
    ensure_investor_entity,
    sync_investor_advance_to_supabase,
    sync_investor_repayment_to_supabase,
)


@pytest.fixture
def mock_supabase():
    client = MagicMock()

    # Pre-existing chart_of_accounts in Supabase (Indian footwear manufacturing standard)
    coa_data = [
        {"id": "uuid-1010-bank", "code": "1010", "name": "Bank Accounts"},
        {"id": "uuid-1020-cash", "code": "1020", "name": "Cash in Hand"},
        {"id": "uuid-1020-fcash", "code": "1020-FACTORY-CASH", "name": "Factory Petty Cash"},
        {"id": "uuid-2020-wages", "code": "2020", "name": "Karigar Wages Payable"},
        {"id": "uuid-5030-rent", "code": "5030", "name": "Factory Rent & Electricity"},
    ]
    coa_mock = MagicMock()
    coa_mock.select.return_value.execute.return_value = MagicMock(data=coa_data)

    inserted_rows = []

    def table_router(name):
        tbl = MagicMock()
        if name == "chart_of_accounts":
            def mock_insert(row):
                m = MagicMock()
                new_row = dict(row)
                new_row["id"] = f"uuid-{row['code']}"
                coa_data.append(new_row)
                inserted_rows.append(new_row)
                m.execute.return_value = MagicMock(data=[new_row])
                return m
            tbl.insert.side_effect = mock_insert
            tbl.select.return_value.execute.return_value = MagicMock(data=coa_data)
            return tbl

        recorded_journal_entries = []
        recorded_journal_lines = []

        def mock_upsert(row, *args, **kwargs):
            m = MagicMock()
            if name == "journal_entries":
                recorded_journal_entries.append(row)
            elif name == "journal_lines":
                if isinstance(row, list):
                    recorded_journal_lines.extend(row)
                else:
                    recorded_journal_lines.append(row)
            m.execute.return_value = MagicMock(data=[row] if isinstance(row, dict) else row)
            return m

        tbl.upsert.side_effect = mock_upsert
        tbl.recorded_entries = recorded_journal_entries
        tbl.recorded_lines = recorded_journal_lines
        return tbl

    client.table.side_effect = table_router
    return client


def test_ensure_investor_gl_accounts_avoids_collisions(mock_supabase):
    """Confirm GL accounts are added without colliding with existing 2020/5030 codes."""
    coa_map = {"1010": "uuid-1010-bank", "1020": "uuid-1020-cash"}
    res = ensure_investor_gl_accounts(mock_supabase, coa_map)

    assert res["gl_advances_payable"] is not None
    assert res["gl_margin_cost"] is not None

    # Calling a second time must NOT create duplicate entries
    res2 = ensure_investor_gl_accounts(mock_supabase, coa_map)
    assert res2["gl_advances_payable"] == res["gl_advances_payable"]
    assert res2["gl_margin_cost"] == res["gl_margin_cost"]


def test_sync_investor_advance_journal_lines(mock_supabase):
    """Verify investor advance posts Debit Cash/Bank, Credit Investor Advances Payable."""
    with patch("services.supabase_investor_service.get_supabase_admin_client", return_value=mock_supabase):
        adv_doc = {
            "_id": "60d5ec49f1b2c80015f8a001",
            "investor_id": "60d5ec49f1b2c80015f8a002",
            "investor_name": "Test Angel Partner",
            "amount": 100000.0,
            "po_number": "PO-SSK-2026-001",
            "advance_date": "2026-10-06",
        }
        res = sync_investor_advance_to_supabase(adv_doc, payment_mode="BANK_TRANSFER")
        assert res is not None
        assert res["total_debit"] == 100000.0
        assert res["total_credit"] == 100000.0


def test_sync_investor_repayment_case_a_straight(mock_supabase):
    """Case (a): Straight repayment debit principal + margin, credit cash/bank."""
    with patch("services.supabase_investor_service.get_supabase_admin_client", return_value=mock_supabase):
        rep_doc = {
            "_id": "60d5ec49f1b2c80015f8a010",
            "investor_id": "60d5ec49f1b2c80015f8a002",
            "principal_amount": 100000.0,
            "margin_amount": 10000.0,
            "payout_date": "2026-10-06",
        }
        res = sync_investor_repayment_to_supabase(rep_doc, is_reinvestment=False, payment_mode="BANK_TRANSFER")
        assert res is not None
        assert res["total_debit"] == 110000.0
        assert res["total_credit"] == 110000.0
        assert res["entry_type"] == "PAYMENT"


def test_sync_investor_repayment_case_b_reinvestment(mock_supabase):
    """
    Case (b): Reinvestment:
    Margin paid in cash (Debit Margin / Credit Bank).
    Principal rolled forward non-cash (Debit old advance / Credit new advance).
    """
    with patch("services.supabase_investor_service.get_supabase_admin_client", return_value=mock_supabase):
        rep_doc = {
            "_id": "60d5ec49f1b2c80015f8a020",
            "investor_id": "60d5ec49f1b2c80015f8a002",
            "principal_amount": 100000.0,
            "margin_amount": 12500.0,
            "payout_date": "2026-10-06",
        }
        new_adv = {
            "po_number": "PO-NEXT-CYCLE-002",
            "amount": 100000.0,
        }
        res = sync_investor_repayment_to_supabase(
            rep_doc, is_reinvestment=True, new_advance_doc=new_adv, payment_mode="BANK_TRANSFER"
        )
        assert res is not None
        assert res["total_debit"] == 112500.0
        assert res["total_credit"] == 112500.0
        assert res["entry_type"] == "JOURNAL"

