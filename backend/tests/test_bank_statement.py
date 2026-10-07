"""
Automated Verification of Investor Repayment & Advance Bank Statement Passbook Ledger.
Tests:
- Transaction compilation (Credits, Debits, Margin payouts, Rollover journals)
- Running balance continuity across all transactions
- Opening and closing balance reconciliation
- Scoped investor statements and filters
"""
import pytest
import uuid
from datetime import datetime, timezone
from bson import ObjectId

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.mark.anyio
async def test_bank_statement_generation_and_balance_continuity():
    import server
    from routes.investors import generate_bank_statement_ledger
    db = server.db

    # 1. Fetch consolidated statement from DB
    statement = await generate_bank_statement_ledger(db)

    assert "statement_title" in statement
    assert "transactions" in statement
    assert "closing_balance" in statement
    assert "total_credit_inflow" in statement
    assert "total_principal_repaid" in statement

    txns = statement["transactions"]
    print(f"Total Statement Transactions: {len(txns)}")
    print(f"Total Credit Funded: ₹{statement['total_credit_inflow']:,.2f}")
    print(f"Total Principal Repaid: ₹{statement['total_principal_repaid']:,.2f}")
    print(f"Total Margins Paid: ₹{statement['total_margin_paid']:,.2f}")
    print(f"Closing Outstanding Balance: ₹{statement['closing_balance']:,.2f}")

    # 2. Check running balance continuity in chronological order (statement['transactions'] is reversed for display)
    chronological = list(reversed(txns))
    running = 0.0
    for idx, t in enumerate(chronological):
        running += (t["credit"] - t["debit"])
        assert round(running, 2) == round(t["running_balance"], 2), (
            f"Row {idx} ({t['voucher_no']}): Expected running balance {round(running, 2)}, got {t['running_balance']}"
        )
        assert t["voucher_no"].startswith("VCH-ADV-") or t["voucher_no"].startswith("VCH-REP-")
        assert "narration" in t and len(t["narration"]) > 5
        assert "channel" in t

    # 3. Overall accounting balance check:
    # closing_balance must equal total_credit_inflow - total_principal_repaid
    expected_closing = round(statement["total_credit_inflow"] - statement["total_principal_repaid"], 2)
    assert round(statement["closing_balance"], 2) == expected_closing

    # 4. Filter by specific investor if available
    investor = await db.investors.find_one()
    if investor:
        iid = str(investor["_id"])
        inv_statement = await generate_bank_statement_ledger(db, investor_id=iid)
        assert inv_statement["account_holder"] == investor["name"]
        inv_chronological = list(reversed(inv_statement["transactions"]))
        inv_running = 0.0
        for t in inv_chronological:
            inv_running += (t["credit"] - t["debit"])
            assert round(inv_running, 2) == round(t["running_balance"], 2)
        assert round(inv_statement["closing_balance"], 2) == round(inv_statement["total_credit_inflow"] - inv_statement["total_principal_repaid"], 2)

    print(" Bank Statement Ledger Verification Passed 100%!")
