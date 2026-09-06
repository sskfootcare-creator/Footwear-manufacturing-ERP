"""Tests for Per-Source Cash Accounts and Unified Transactions Ledger."""

import pytest
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException, Request

from models.banking import (
    CashWithdrawalConfirmIn,
    CashLedgerCreateIn,
)
import routes.banking as banking_routes
from routes.banking import (
    _ensure_cash_account_for_bank,
    confirm_cash_withdrawal,
    create_cash_ledger_entry,
    list_cash_accounts,
    get_cash_account_transactions,
    get_reconciliation_summary,
    get_unmatched_erp_candidates,
)


class MockCursor:
    def __init__(self, docs):
        self.docs = list(docs) if docs else []

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return list(self.docs)


def _make_req(role="admin", email="admin@sskfootcare.com"):
    req = MagicMock(spec=Request)
    req.app = MagicMock()
    req.app.get_current_user = AsyncMock(return_value={
        "id": "u1", "email": email, "name": "Admin User", "role": role
    })
    return req


@pytest.mark.anyio
async def test_lazy_cash_account_creation_on_withdrawal_and_manual():
    """Verify lazy creation of distinct cash accounts for different banks without duplication."""
    mock_db = MagicMock()
    hdfc_id = str(ObjectId())
    uco_id = str(ObjectId())

    bank_accounts_store = {
        hdfc_id: {"_id": ObjectId(hdfc_id), "name": "HDFC", "bank_name": "HDFC"},
        uco_id: {"_id": ObjectId(uco_id), "name": "UCO Bank", "bank_name": "UCO Bank"},
    }
    cash_accounts_store = {}

    async def _mock_find_one_bank(q):
        bid = str(q.get("_id") or "")
        return bank_accounts_store.get(bid)

    async def _mock_find_one_cash_account(q):
        src = q.get("source_bank_account_id")
        if src:
            for ca in cash_accounts_store.values():
                if ca.get("source_bank_account_id") == str(src):
                    return ca
        cid = str(q.get("_id") or "")
        return cash_accounts_store.get(cid)

    async def _mock_insert_cash_account(doc):
        new_id = ObjectId()
        d = dict(doc)
        d["_id"] = new_id
        cash_accounts_store[str(new_id)] = d
        res = MagicMock()
        res.inserted_id = new_id
        return res

    mock_db.bank_accounts.find_one = AsyncMock(side_effect=_mock_find_one_bank)
    mock_db.cash_accounts.find_one = AsyncMock(side_effect=_mock_find_one_cash_account)
    mock_db.cash_accounts.insert_one = AsyncMock(side_effect=_mock_insert_cash_account)

    # 1. First ensure call for HDFC creates Cash (HDFC)
    ca_hdfc_1 = await _ensure_cash_account_for_bank(mock_db, hdfc_id)
    assert ca_hdfc_1 is not None
    assert ca_hdfc_1["name"] == "Cash (HDFC)"
    assert ca_hdfc_1["source_bank_account_id"] == hdfc_id
    assert len(cash_accounts_store) == 1

    # 2. Second call for HDFC retrieves existing, does not duplicate
    ca_hdfc_2 = await _ensure_cash_account_for_bank(mock_db, hdfc_id)
    assert str(ca_hdfc_2["_id"]) == str(ca_hdfc_1["_id"])
    assert len(cash_accounts_store) == 1

    # 3. Call for UCO Bank creates separate Cash (UCO Bank)
    ca_uco = await _ensure_cash_account_for_bank(mock_db, uco_id)
    assert ca_uco is not None
    assert ca_uco["name"] == "Cash (UCO Bank)"
    assert ca_uco["source_bank_account_id"] == uco_id
    assert len(cash_accounts_store) == 2


@pytest.mark.anyio
async def test_multi_pool_isolation_and_no_cross_contamination():
    """Verify HDFC and UCO cash pools maintain isolated rollups and disbursements without cross-contamination."""
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    hdfc_id = str(ObjectId())
    uco_id = str(ObjectId())

    hdfc_ca_id = str(ObjectId())
    uco_ca_id = str(ObjectId())

    cl_hdfc_id = str(ObjectId())
    cl_uco_id = str(ObjectId())

    cash_accounts = [
        {"_id": ObjectId(hdfc_ca_id), "name": "Cash (HDFC)", "source_bank_account_id": hdfc_id, "created_at": "2026-04-01T10:00:00Z"},
        {"_id": ObjectId(uco_ca_id), "name": "Cash (UCO Bank)", "source_bank_account_id": uco_id, "created_at": "2026-04-02T10:00:00Z"},
    ]

    bank_accounts = [
        {"_id": ObjectId(hdfc_id), "name": "HDFC", "bank_name": "HDFC"},
        {"_id": ObjectId(uco_id), "name": "UCO Bank", "bank_name": "UCO Bank"},
    ]

    # HDFC withdrew 50,000, 35,000 remaining
    # UCO withdrew 30,000, 25,000 remaining
    cash_ledgers = [
        {"_id": ObjectId(cl_hdfc_id), "bank_account_id": hdfc_id, "amount": 50000.0, "remaining_balance": 35000.0, "date": "2026-04-01"},
        {"_id": ObjectId(cl_uco_id), "bank_account_id": uco_id, "amount": 30000.0, "remaining_balance": 25000.0, "date": "2026-04-02"},
    ]

    mock_db.cash_accounts.find = MagicMock(return_value=MockCursor(cash_accounts))
    mock_db.cash_accounts.find_one = AsyncMock(side_effect=lambda q: next((c for c in cash_accounts if str(c.get("_id")) == str(q.get("_id")) or str(c.get("source_bank_account_id")) == str(q.get("source_bank_account_id"))), None))
    mock_db.bank_accounts.find = MagicMock(return_value=MockCursor(bank_accounts))
    mock_db.cash_ledger.find = MagicMock(return_value=MockCursor(cash_ledgers))
    mock_db.cash_ledger.distinct = AsyncMock(return_value=[hdfc_id, uco_id])

    res = await list_cash_accounts(req)
    assert res["ok"] is True
    assert len(res["cash_accounts"]) == 2

    hdfc_pool = next(a for a in res["cash_accounts"] if a["source_bank_account_id"] == hdfc_id)
    uco_pool = next(a for a in res["cash_accounts"] if a["source_bank_account_id"] == uco_id)

    assert hdfc_pool["name"] == "Cash (HDFC)"
    assert hdfc_pool["total_withdrawn"] == 50000.0
    assert hdfc_pool["current_balance"] == 35000.0
    assert hdfc_pool["total_spent"] == 15000.0

    assert uco_pool["name"] == "Cash (UCO Bank)"
    assert uco_pool["total_withdrawn"] == 30000.0
    assert uco_pool["current_balance"] == 25000.0
    assert uco_pool["total_spent"] == 5000.0

    assert res["total_cash_in_hand"] == 60000.0
    assert res["total_cash_withdrawn"] == 80000.0


@pytest.mark.anyio
async def test_cash_account_transactions_ledger_running_balance():
    """Verify unified transactions endpoint calculates chronological running balance across Money IN and OUT."""
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    hdfc_id = str(ObjectId())
    ca_id = str(ObjectId())
    cl1_id = str(ObjectId())
    cl2_id = str(ObjectId())

    ca_doc = {"_id": ObjectId(ca_id), "name": "Cash (HDFC)", "source_bank_account_id": hdfc_id, "created_at": "2026-04-01T09:00:00Z"}
    bank_doc = {"_id": ObjectId(hdfc_id), "name": "HDFC", "bank_name": "HDFC"}

    cash_ledgers = [
        {
            "_id": ObjectId(cl1_id),
            "bank_account_id": hdfc_id,
            "amount": 10000.0,
            "date": "2026-04-01",
            "source_statement_line_id": "line_stmt_001",
            "notes": "ATM Withdrawal",
            "created_at": "2026-04-01T10:00:00Z",
        },
        {
            "_id": ObjectId(cl2_id),
            "bank_account_id": hdfc_id,
            "amount": 5000.0,
            "date": "2026-04-05",
            "source_statement_line_id": None,
            "notes": "Manual Topup",
            "created_at": "2026-04-05T09:00:00Z",
        },
    ]

    wage_payments = [
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl1_id,
            "amount": 3000.0,
            "date": "2026-04-02",
            "worker_name": "Ramesh Kumar",
            "period_from": "2026-03-25",
            "period_to": "2026-04-01",
            "created_at": "2026-04-02T11:00:00Z",
        }
    ]

    expenses = [
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl1_id,
            "amount": 1500.0,
            "date": "2026-04-03",
            "payee": "City Hardware",
            "category": "Maintenance",
            "notes": "Machine belt replacement",
            "created_at": "2026-04-03T14:00:00Z",
        }
    ]

    advances = [
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl1_id,
            "amount": 500.0,
            "date": "2026-04-04",
            "worker_name": "Suresh Karigar",
            "txn_type": "advance",
            "notes": "Festival advance",
            "created_at": "2026-04-04T16:00:00Z",
        }
    ]

    mock_db.cash_accounts.find_one = AsyncMock(return_value=ca_doc)
    mock_db.bank_accounts.find_one = AsyncMock(return_value=bank_doc)

    def _mock_find_cl(q):
        return MockCursor(cash_ledgers)

    def _mock_find_wp(q):
        return MockCursor(wage_payments)

    def _mock_find_exp(q):
        return MockCursor(expenses)

    def _mock_find_adv(q):
        return MockCursor(advances)

    mock_db.cash_ledger.find = MagicMock(side_effect=_mock_find_cl)
    mock_db.wage_payments.find = MagicMock(side_effect=_mock_find_wp)
    mock_db.expenses.find = MagicMock(side_effect=_mock_find_exp)
    mock_db.advances.find = MagicMock(side_effect=_mock_find_adv)

    # 1. Full transaction ledger (order="asc" for chronological sequence check)
    res_asc = await get_cash_account_transactions(ca_id, req, order="asc")
    assert res_asc["ok"] is True
    txns = res_asc["transactions"]
    assert len(txns) == 5

    # Sequence of events:
    # 2026-04-01: +10,000 -> running_bal = 10,000
    # 2026-04-02: -3,000  -> running_bal = 7,000
    # 2026-04-03: -1,500  -> running_bal = 5,500
    # 2026-04-04: -500    -> running_bal = 5,000
    # 2026-04-05: +5,000  -> running_bal = 10,000
    assert txns[0]["direction"] == "in"
    assert txns[0]["amount"] == 10000.0
    assert txns[0]["running_balance"] == 10000.0

    assert txns[1]["direction"] == "out"
    assert txns[1]["type"] == "wage_payment"
    assert txns[1]["amount"] == 3000.0
    assert txns[1]["running_balance"] == 7000.0

    assert txns[2]["direction"] == "out"
    assert txns[2]["type"] == "expense"
    assert txns[2]["amount"] == 1500.0
    assert txns[2]["running_balance"] == 5500.0

    assert txns[3]["direction"] == "out"
    assert txns[3]["type"] == "advance"
    assert txns[3]["amount"] == 500.0
    assert txns[3]["running_balance"] == 5000.0

    assert txns[4]["direction"] == "in"
    assert txns[4]["amount"] == 5000.0
    assert txns[4]["running_balance"] == 10000.0

    assert res_asc["total_withdrawn"] == 15000.0
    assert res_asc["total_spent"] == 5000.0
    assert res_asc["current_balance"] == 10000.0

    # 2. Test default desc order (newest first, but running_balance preserved)
    res_desc = await get_cash_account_transactions(ca_id, req, order="desc")
    assert res_desc["transactions"][0]["date"] == "2026-04-05"
    assert res_desc["transactions"][0]["running_balance"] == 10000.0
    assert res_desc["transactions"][-1]["date"] == "2026-04-01"
    assert res_desc["transactions"][-1]["running_balance"] == 10000.0

    # 3. Test filtering by txn_type="inflow"
    res_inflow = await get_cash_account_transactions(ca_id, req, txn_type="inflow")
    assert all(t["direction"] == "in" for t in res_inflow["transactions"])
    assert len(res_inflow["transactions"]) == 2

    # 4. Test filtering by txn_type="outflow"
    res_outflow = await get_cash_account_transactions(ca_id, req, txn_type="outflow")
    assert all(t["direction"] == "out" for t in res_outflow["transactions"])
    assert len(res_outflow["transactions"]) == 3

    # 5. Test date range filtering
    res_date = await get_cash_account_transactions(ca_id, req, from_date="2026-04-02", to_date="2026-04-03")
    assert len(res_date["transactions"]) == 2
    dates = [t["date"] for t in res_date["transactions"]]
    assert "2026-04-02" in dates and "2026-04-03" in dates


@pytest.mark.anyio
async def test_reconciliation_total_cash_in_hand_matches_cash_accounts_sum():
    """Verify that Total Cash in Hand in reconciliation summary strictly equals the sum of individual cash accounts."""
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    hdfc_id = str(ObjectId())
    uco_id = str(ObjectId())

    cash_ledgers = [
        {"_id": ObjectId(), "bank_account_id": hdfc_id, "amount": 25000.0, "remaining_balance": 18000.0, "date": "2026-04-01"},
        {"_id": ObjectId(), "bank_account_id": uco_id, "amount": 15000.0, "remaining_balance": 12000.0, "date": "2026-04-02"},
    ]

    mock_db.cash_ledger.find = MagicMock(return_value=MockCursor(cash_ledgers))
    mock_db.cash_accounts.find = MagicMock(return_value=MockCursor([
        {"_id": ObjectId(), "name": "Cash (HDFC)", "source_bank_account_id": hdfc_id},
        {"_id": ObjectId(), "name": "Cash (UCO Bank)", "source_bank_account_id": uco_id},
    ]))
    mock_db.cash_accounts.find_one = AsyncMock(return_value={"_id": ObjectId()})
    mock_db.cash_accounts.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.bank_accounts.find = MagicMock(return_value=MockCursor([
        {"_id": ObjectId(hdfc_id), "name": "HDFC", "bank_name": "HDFC"},
        {"_id": ObjectId(uco_id), "name": "UCO Bank", "bank_name": "UCO Bank"},
    ]))
    mock_db.bank_statement_lines.find = MagicMock(return_value=MockCursor([]))
    mock_db.bank_statement_lines.distinct = AsyncMock(return_value=[])

    recon_summary = await get_reconciliation_summary(req)
    cash_accounts_res = await list_cash_accounts(req)

    sum_of_accounts = sum(ca["current_balance"] for ca in cash_accounts_res["cash_accounts"])
    assert recon_summary["summary"]["total_cash_in_hand"] == 30000.0
    assert sum_of_accounts == 30000.0
    assert recon_summary["summary"]["total_cash_in_hand"] == sum_of_accounts


@pytest.mark.anyio
async def test_client_cash_payment_rollup_in_list_cash_accounts():
    """Verify that client payments into cash accounts correctly rollup into current_balance and total_received."""
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    hdfc_id = str(ObjectId())
    ca_id = str(ObjectId())

    cash_ledgers = [
        {"_id": ObjectId(), "bank_account_id": hdfc_id, "amount": 20000.0, "remaining_balance": 15000.0, "date": "2026-04-01"},
    ]
    # Client paid ₹10,000 cash into this cash account
    client_payments = [
        {
            "_id": ObjectId(),
            "payment_no": "PAY-001",
            "amount": 10000.0,
            "account_type": "cash",
            "cash_account_id": ca_id,
            "bank_account_id": hdfc_id,
            "client_name": "Metro Shoes",
            "payment_date": "2026-04-03",
        }
    ]

    mock_db.cash_ledger.find = MagicMock(return_value=MockCursor(cash_ledgers))
    mock_db.cash_ledger.distinct = AsyncMock(return_value=[hdfc_id])
    mock_db.payments.find = MagicMock(return_value=MockCursor(client_payments))
    mock_db.cash_accounts.find = MagicMock(return_value=MockCursor([
        {"_id": ObjectId(ca_id), "name": "Cash (HDFC)", "source_bank_account_id": hdfc_id},
    ]))
    mock_db.bank_accounts.find = MagicMock(return_value=MockCursor([
        {"_id": ObjectId(hdfc_id), "name": "HDFC", "bank_name": "HDFC Bank"},
    ]))

    res = await list_cash_accounts(req)
    assert res["ok"] is True
    acc = res["cash_accounts"][0]
    # remaining_balance (15000) + client cash received (10000) = 25000
    assert acc["current_balance"] == 25000.0
    assert acc["total_withdrawn"] == 20000.0
    assert acc["total_received"] == 10000.0
    assert acc["total_spent"] == 5000.0
    assert res["total_cash_in_hand"] == 25000.0
    assert res["total_cash_received"] == 10000.0


@pytest.mark.anyio
async def test_client_cash_payment_in_unified_transactions_ledger():
    """Verify that client payment entries appear as Money IN and participate in chronological running balance."""
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    hdfc_id = str(ObjectId())
    ca_id = str(ObjectId())
    cl_id = str(ObjectId())
    exp_id = str(ObjectId())
    pay_id = str(ObjectId())

    ca_doc = {"_id": ObjectId(ca_id), "name": "Cash (HDFC)", "source_bank_account_id": hdfc_id}
    mock_db.cash_accounts.find_one = AsyncMock(return_value=ca_doc)
    mock_db.bank_accounts.find_one = AsyncMock(return_value={"_id": ObjectId(hdfc_id), "name": "HDFC Bank"})

    # 1. Day 1: Cash withdrawal 10,000 -> Running Bal = 10,000
    # 2. Day 2: Expense 2,000 -> Running Bal = 8,000
    # 3. Day 3: Client Cash Payment 5,000 -> Running Bal = 13,000
    cash_docs = [
        {"_id": ObjectId(cl_id), "bank_account_id": hdfc_id, "amount": 10000.0, "date": "2026-04-01", "created_at": "2026-04-01T10:00:00Z"}
    ]
    expenses = [
        {"_id": ObjectId(exp_id), "cash_ledger_id": str(cl_id), "amount": 2000.0, "category": "Tea", "date": "2026-04-02", "created_at": "2026-04-02T11:00:00Z"}
    ]
    payments = [
        {
            "_id": ObjectId(pay_id),
            "payment_no": "PAY-99",
            "amount": 5000.0,
            "account_type": "cash",
            "cash_account_id": ca_id,
            "client_name": "Apex Retail",
            "payment_date": "2026-04-03",
            "created_at": "2026-04-03T12:00:00Z",
            "reference": "CASH-REC-1",
        }
    ]

    mock_db.cash_ledger.find = MagicMock(return_value=MockCursor(cash_docs))
    mock_db.wage_payments.find = MagicMock(return_value=MockCursor([]))
    mock_db.expenses.find = MagicMock(return_value=MockCursor(expenses))
    mock_db.advances.find = MagicMock(return_value=MockCursor([]))
    mock_db.payments.find = MagicMock(return_value=MockCursor(payments))

    res = await get_cash_account_transactions(ca_id, req, order="asc")
    assert res["ok"] is True
    txns = res["transactions"]
    assert len(txns) == 3

    t1, t2, t3 = txns[0], txns[1], txns[2]
    assert t1["type"] == "cash_withdrawal"
    assert t1["amount"] == 10000.0
    assert t1["running_balance"] == 10000.0

    assert t2["type"] == "expense"
    assert t2["amount"] == 2000.0
    assert t2["running_balance"] == 8000.0

    assert t3["type"] == "client_payment"
    assert t3["amount"] == 5000.0
    assert t3["direction"] == "in"
    assert t3["running_balance"] == 13000.0
    assert t3["client_name"] == "Apex Retail"

    assert res["cash_account"]["total_withdrawn"] == 10000.0
    assert res["cash_account"]["total_received"] == 5000.0
    assert res["cash_account"]["total_in"] == 15000.0
    assert res["cash_account"]["total_spent"] == 2000.0
    assert res["cash_account"]["current_balance"] == 13000.0

    # Test filtering by txn_type="client_payment"
    res_client = await get_cash_account_transactions(ca_id, req, txn_type="client_payment")
    assert len(res_client["transactions"]) == 1
    assert res_client["transactions"][0]["type"] == "client_payment"


@pytest.mark.anyio
async def test_cash_payments_excluded_from_unmatched_erp_candidates():
    """Verify that client payments with account_type='cash' are not presented for bank statement reconciliation."""
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    bank_id = str(ObjectId())
    mock_db.bank_accounts.find_one = AsyncMock(return_value={
        "_id": ObjectId(bank_id), "name": "HDFC Bank", "account_type": "b2b_client"
    })
    mock_db.online_settlements.find = MagicMock(return_value=MockCursor([]))
    mock_db.expenses.find = MagicMock(return_value=MockCursor([]))

    # One bank payment and one cash payment
    payments = [
        {
            "_id": ObjectId(),
            "type": "payment",
            "amount": 25000.0,
            "account_type": "bank",
            "bank_account_id": bank_id,
            "client_name": "Bank Paying Client",
            "payment_date": "2026-04-05",
        },
        {
            "_id": ObjectId(),
            "type": "payment",
            "amount": 10000.0,
            "account_type": "cash",
            "bank_account_id": bank_id,
            "client_name": "Cash Paying Client",
            "payment_date": "2026-04-05",
        }
    ]

    mock_db.payments.find = MagicMock(return_value=MockCursor(payments))

    res = await get_unmatched_erp_candidates(req, bank_account_id=bank_id, side="credit")
    assert res["ok"] is True
    # The cash payment must be excluded!
    parties = [c["party"] for c in res["candidates"]]
    assert "Bank Paying Client" in parties
    assert "Cash Paying Client" not in parties
    assert len(res["candidates"]) == 1


@pytest.mark.anyio
async def test_stage4_full_realistic_workflow():
    """
    Stage 4 Full realistic workflow:
    - Withdraw cash from both HDFC and UCO on different dates
    - Pay wages and expenses from each pool separately
    - View both cash accounts: confirm each shows an accurate, independent balance and history
      with zero cross-contamination between the two sources
    - Confirm the existing 'Total Cash in Hand' summary figure in reconciliation summary
      strictly equals the sum of all cash accounts' balances.
    """
    mock_db = MagicMock()
    req = _make_req()
    req.app.mongodb = mock_db

    hdfc_id = str(ObjectId())
    uco_id = str(ObjectId())
    ca_hdfc_id = str(ObjectId())
    ca_uco_id = str(ObjectId())
    cl_hdfc_id = str(ObjectId())
    cl_uco_id = str(ObjectId())

    bank_accounts = [
        {"_id": ObjectId(hdfc_id), "name": "HDFC Primary", "bank_name": "HDFC"},
        {"_id": ObjectId(uco_id), "name": "UCO Bank Offline", "bank_name": "UCO Bank"},
    ]

    cash_accounts = [
        {"_id": ObjectId(ca_hdfc_id), "name": "Cash (HDFC Primary)", "source_bank_account_id": hdfc_id, "created_at": "2026-04-01T09:00:00Z"},
        {"_id": ObjectId(ca_uco_id), "name": "Cash (UCO Bank Offline)", "source_bank_account_id": uco_id, "created_at": "2026-04-03T09:00:00Z"},
    ]

    cash_ledgers = [
        {
            "_id": ObjectId(cl_hdfc_id),
            "bank_account_id": hdfc_id,
            "amount": 60000.0,
            "remaining_balance": 40000.0,
            "date": "2026-04-01",
            "source_statement_line_id": "stmt_hdfc_01",
            "notes": "HDFC Weekly Karigar Withdrawal",
            "created_at": "2026-04-01T09:30:00Z",
        },
        {
            "_id": ObjectId(cl_uco_id),
            "bank_account_id": uco_id,
            "amount": 40000.0,
            "remaining_balance": 28000.0,
            "date": "2026-04-03",
            "source_statement_line_id": "stmt_uco_01",
            "notes": "UCO Factory Floor Withdrawal",
            "created_at": "2026-04-03T10:00:00Z",
        },
    ]

    wage_payments = [
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl_hdfc_id,
            "amount": 15000.0,
            "date": "2026-04-02",
            "worker_name": "Ramesh Karigar",
            "period_from": "2026-03-25",
            "period_to": "2026-04-01",
            "created_at": "2026-04-02T11:00:00Z",
        },
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl_uco_id,
            "amount": 10000.0,
            "date": "2026-04-05",
            "worker_name": "Suresh Karigar",
            "period_from": "2026-03-28",
            "period_to": "2026-04-04",
            "created_at": "2026-04-05T12:00:00Z",
        },
    ]

    expenses = [
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl_hdfc_id,
            "amount": 5000.0,
            "date": "2026-04-04",
            "payee": "City Spares",
            "category": "Maintenance",
            "notes": "Sole stitching needle replacement",
            "created_at": "2026-04-04T14:00:00Z",
        }
    ]

    advances = [
        {
            "_id": ObjectId(),
            "cash_ledger_id": cl_uco_id,
            "amount": 2000.0,
            "date": "2026-04-06",
            "worker_name": "Mahesh Karigar",
            "txn_type": "advance",
            "notes": "Medical advance",
            "created_at": "2026-04-06T15:00:00Z",
        }
    ]

    # Setup database mocks
    mock_db.cash_accounts.find = MagicMock(return_value=MockCursor(cash_accounts))
    mock_db.cash_accounts.find_one = AsyncMock(side_effect=lambda q: next(
        (c for c in cash_accounts if str(c.get("_id")) == str(q.get("_id")) or str(c.get("source_bank_account_id")) == str(q.get("source_bank_account_id"))),
        None
    ))
    mock_db.bank_accounts.find = MagicMock(return_value=MockCursor(bank_accounts))
    mock_db.bank_accounts.find_one = AsyncMock(side_effect=lambda q: next(
        (b for b in bank_accounts if str(b.get("_id")) == str(q.get("_id"))),
        None
    ))
    mock_db.cash_ledger.find = MagicMock(side_effect=lambda q: MockCursor([
        c for c in cash_ledgers
        if not q or not q.get("bank_account_id") or
           (isinstance(q.get("bank_account_id"), dict) and str(c.get("bank_account_id")) in [str(x) for x in q["bank_account_id"].get("$in", [])])
    ]))
    mock_db.cash_ledger.distinct = AsyncMock(return_value=[hdfc_id, uco_id])
    mock_db.wage_payments.find = MagicMock(side_effect=lambda q: MockCursor([
        w for w in wage_payments
        if not q or not q.get("cash_ledger_id") or
           (isinstance(q.get("cash_ledger_id"), dict) and str(w.get("cash_ledger_id")) in [str(x) for x in q["cash_ledger_id"].get("$in", [])])
    ]))
    mock_db.expenses.find = MagicMock(side_effect=lambda q: MockCursor([
        e for e in expenses
        if not q or not q.get("cash_ledger_id") or
           (isinstance(q.get("cash_ledger_id"), dict) and str(e.get("cash_ledger_id")) in [str(x) for x in q["cash_ledger_id"].get("$in", [])])
    ]))
    mock_db.advances.find = MagicMock(side_effect=lambda q: MockCursor([
        a for a in advances
        if not q or not q.get("cash_ledger_id") or
           (isinstance(q.get("cash_ledger_id"), dict) and str(a.get("cash_ledger_id")) in [str(x) for x in q["cash_ledger_id"].get("$in", [])])
    ]))
    mock_db.payments.find = MagicMock(return_value=MockCursor([]))
    mock_db.bank_statement_lines.find = MagicMock(return_value=MockCursor([]))
    mock_db.bank_statement_lines.distinct = AsyncMock(return_value=[])

    # 1. Verify list_cash_accounts returns isolated pools with accurate rollups
    ca_res = await list_cash_accounts(req)
    assert ca_res["ok"] is True
    assert len(ca_res["cash_accounts"]) == 2

    hdfc_pool = next(a for a in ca_res["cash_accounts"] if a["source_bank_account_id"] == hdfc_id)
    uco_pool = next(a for a in ca_res["cash_accounts"] if a["source_bank_account_id"] == uco_id)

    assert hdfc_pool["name"] == "Cash (HDFC Primary)"
    assert hdfc_pool["total_withdrawn"] == 60000.0
    assert hdfc_pool["total_spent"] == 20000.0
    assert hdfc_pool["current_balance"] == 40000.0

    assert uco_pool["name"] == "Cash (UCO Bank Offline)"
    assert uco_pool["total_withdrawn"] == 40000.0
    assert uco_pool["total_spent"] == 12000.0
    assert uco_pool["current_balance"] == 28000.0

    assert ca_res["total_cash_withdrawn"] == 100000.0
    assert ca_res["total_cash_in_hand"] == 68000.0

    # 2. Verify HDFC cash account transactions ledger (order='asc' for sequential checking)
    hdfc_txns_res = await get_cash_account_transactions(ca_hdfc_id, req, order="asc")
    assert hdfc_txns_res["ok"] is True
    h_txns = hdfc_txns_res["transactions"]
    assert len(h_txns) == 3

    # HDFC events: +60,000 -> -15,000 -> -5,000
    assert h_txns[0]["direction"] == "in"
    assert h_txns[0]["amount"] == 60000.0
    assert h_txns[0]["running_balance"] == 60000.0
    assert h_txns[1]["direction"] == "out"
    assert h_txns[1]["amount"] == 15000.0
    assert h_txns[1]["title"] == "Ramesh Karigar"
    assert h_txns[1]["running_balance"] == 45000.0
    assert h_txns[2]["direction"] == "out"
    assert h_txns[2]["amount"] == 5000.0
    assert h_txns[2]["payee"] == "City Spares"
    assert h_txns[2]["running_balance"] == 40000.0

    # Confirm zero UCO records contaminated HDFC pool
    assert not any("Suresh" in str(t) or "Mahesh" in str(t) for t in h_txns)

    # 3. Verify UCO cash account transactions ledger (order='asc')
    uco_txns_res = await get_cash_account_transactions(ca_uco_id, req, order="asc")
    assert uco_txns_res["ok"] is True
    u_txns = uco_txns_res["transactions"]
    assert len(u_txns) == 3

    # UCO events: +40,000 -> -10,000 -> -2,000
    assert u_txns[0]["direction"] == "in"
    assert u_txns[0]["amount"] == 40000.0
    assert u_txns[0]["running_balance"] == 40000.0
    assert u_txns[1]["direction"] == "out"
    assert u_txns[1]["amount"] == 10000.0
    assert u_txns[1]["title"] == "Suresh Karigar"
    assert u_txns[1]["running_balance"] == 30000.0
    assert u_txns[2]["direction"] == "out"
    assert u_txns[2]["amount"] == 2000.0
    assert u_txns[2]["title"] == "Mahesh Karigar"
    assert u_txns[2]["running_balance"] == 28000.0

    # Confirm zero HDFC records contaminated UCO pool
    assert not any("Ramesh" in str(t) or "City Spares" in str(t) for t in u_txns)

    # 4. Verify Reconciliation Summary 'Total Cash in Hand' strictly equals the sum of cash accounts
    recon_res = await get_reconciliation_summary(req)
    total_cash_in_hand_summary = recon_res["summary"]["total_cash_in_hand"]
    total_from_individual_accounts = sum(ca["current_balance"] for ca in ca_res["cash_accounts"])

    assert total_cash_in_hand_summary == 68000.0
    assert total_from_individual_accounts == 68000.0
    assert total_cash_in_hand_summary == total_from_individual_accounts


