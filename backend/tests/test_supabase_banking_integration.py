"""Integration tests for Supabase Banking & Reconciliation persistence."""

import os
import sys
import uuid
import pytest
from bson import ObjectId

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.supabase_banking_service import (
    to_uuid,
    upsert_supabase_bank_account,
    insert_supabase_statement_lines,
    save_supabase_reconciliation_statement,
    list_supabase_bank_accounts,
)


@pytest.fixture(scope="module")
def sample_mongo_bank_account():
    test_oid = ObjectId("66e9c0000000000000000001")
    return {
        "_id": test_oid,
        "name": "SSK Primary Test HDFC",
        "bank_name": "HDFC Bank Ltd",
        "account_number": "50200099887766",
        "account_number_last4": "7766",
        "ifsc": "HDFC0001234",
        "branch": "Okhla Phase III",
        "account_type": "current",
        "opening_balance": 50000.0,
        "opening_balance_date": "2026-04-01",
        "active": True,
    }


def test_bank_account_upsert_and_fetch(sample_mongo_bank_account):
    """Test upserting a MongoDB bank account doc into Supabase and listing accounts."""
    saved = upsert_supabase_bank_account(sample_mongo_bank_account)
    assert saved is not None
    expected_uuid = str(to_uuid(sample_mongo_bank_account["_id"]))
    assert saved["id"] == expected_uuid
    assert saved["bank_name"] == "HDFC Bank Ltd"
    assert saved["account_number_last4"] == "7766"

    # Verify listing includes the account
    accounts = list_supabase_bank_accounts()
    matching = [a for a in accounts if a["id"] == expected_uuid]
    assert len(matching) == 1
    assert matching[0]["account_name"] == "SSK Primary Test HDFC"


def test_statement_lines_insertion(sample_mongo_bank_account):
    """Test batch inserting bank statement lines linked to the bank account."""
    acc_id = sample_mongo_bank_account["_id"]
    test_lines = [
        {
            "_id": ObjectId("66e9c0000000000000000011"),
            "date": "2026-05-01",
            "narration": "NEFT Inward - Bata India Settlement",
            "credit_amount": 125000.0,
            "debit_amount": 0.0,
            "reference_number": "NEFT12345678",
            "match_status": "matched",
        },
        {
            "_id": ObjectId("66e9c0000000000000000012"),
            "date": "2026-05-02",
            "narration": "RTGS Outward - Leather Supplier Payment",
            "credit_amount": 0.0,
            "debit_amount": 45000.0,
            "reference_number": "RTGS98765432",
            "match_status": "unmatched",
        },
    ]

    inserted = insert_supabase_statement_lines(test_lines, acc_id)
    assert len(inserted) == 2
    assert inserted[0]["narration"] == "NEFT Inward - Bata India Settlement"
    assert float(inserted[0]["credit_amount"]) == 125000.0
    assert float(inserted[1]["debit_amount"]) == 45000.0


def test_reconciliation_statement_lifecycle(sample_mongo_bank_account):
    """Test recording a balanced and discrepancy reconciliation statement."""
    acc_id = sample_mongo_bank_account["_id"]
    
    # 1. Balanced statement
    stmt_balanced = {
        "bank_account_id": str(acc_id),
        "period_start_date": "2026-05-01",
        "period_end_date": "2026-05-31",
        "statement_closing_balance": 130000.0,
        "gl_closing_balance": 130000.0,
        "reconciled_balance": 130000.0,
        "notes": "May 2026 Monthly Close",
    }
    saved_balanced = save_supabase_reconciliation_statement(stmt_balanced)
    assert saved_balanced is not None
    assert saved_balanced["status"] == "balanced"
    assert float(saved_balanced["unreconciled_difference"]) == 0.0

    # 2. Statement with discrepancy
    stmt_discrepancy = {
        "bank_account_id": str(acc_id),
        "period_start_date": "2026-06-01",
        "period_end_date": "2026-06-30",
        "statement_closing_balance": 150000.0,
        "gl_closing_balance": 148500.0,
        "reconciled_balance": 148500.0,
        "notes": "June 2026 Pending Cheques",
    }
    saved_discrepancy = save_supabase_reconciliation_statement(stmt_discrepancy)
    assert saved_discrepancy is not None
    assert saved_discrepancy["status"] == "discrepancy"
    assert float(saved_discrepancy["unreconciled_difference"]) == 1500.0
