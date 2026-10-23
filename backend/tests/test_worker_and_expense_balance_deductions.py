import pytest
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from unittest.mock import MagicMock
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient

from routes.banking import (
    compute_bank_account_balance,
    sync_bank_account_balance,
    sync_cash_account_balance,
    get_cash_account_transactions,
)
from routes.expenses import (
    create_expense,
    delete_expense,
    confirm_expense,
)
from routes.workers import (
    create_advance,
    delete_advance,
    create_wage_payment,
    worker_ledger,
)
from routes.pos import compute_payroll
from models.expenses import ExpenseIn
from models.workers import AdvanceIn, WagePaymentIn


class FakeApp:
    def __init__(self, db):
        self.mongodb = db


def fake_request(db, user=None):
    req = MagicMock(spec=Request)
    req.app = FakeApp(db)
    req.state = MagicMock()
    req.state.user = user or {"email": "admin@example.com", "role": "admin", "roles": ["admin"]}
    return req


def test_bank_and_cash_expense_deductions():
    async def _run():
        client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
        db = client["test_erp_expense_deductions"]
        await client.drop_database("test_erp_expense_deductions")

        req = fake_request(db)

        # 1. Setup Bank Account with opening balance 50,000
        bank_oid = ObjectId()
        bank_id = str(bank_oid)
        await db.bank_accounts.insert_one({
            "_id": bank_oid,
            "name": "HDFC Test Bank",
            "bank_name": "HDFC",
            "opening_balance": 50000.0,
            "current_balance": 50000.0,
            "balance": 50000.0,
        })

        # Verify initial bank balance
        bal = await sync_bank_account_balance(db, bank_id)
        assert bal == 50000.0

        # 2. Record a confirmed bank expense of 4,500
        exp_in = ExpenseIn(
            category="utilities",
            amount=4500.0,
            date="2026-10-23",
            payee="Electricity Board",
            notes="Factory electric bill",
            bank_account_id=bank_id,
            paid_via="bank",
            status="confirmed",
        )
        exp_res = await create_expense(exp_in, req)
        exp_id = exp_res.get("id") or str(exp_res.get("_id"))

        # Bank balance must be reduced to 45,500
        b_doc = await db.bank_accounts.find_one({"_id": bank_oid})
        assert b_doc["current_balance"] == 45500.0

        # Delete expense -> Bank balance restored to 50,000
        await delete_expense(exp_id, req)
        b_doc_after = await db.bank_accounts.find_one({"_id": bank_oid})
        assert b_doc_after["current_balance"] == 50000.0

        # 3. Setup Cash Account & Cash Ledger with 10,000
        ca_oid = ObjectId()
        ca_id = str(ca_oid)
        cl_oid = ObjectId()
        cl_id = str(cl_oid)

        await db.cash_accounts.insert_one({
            "_id": ca_oid,
            "name": "Main Cash Box",
            "source_bank_account_id": bank_id,
            "current_balance": 10000.0,
            "balance": 10000.0,
        })
        await db.cash_ledger.insert_one({
            "_id": cl_oid,
            "bank_account_id": bank_id,
            "amount": 10000.0,
            "remaining_balance": 10000.0,
            "date": "2026-10-23",
            "notes": "Withdrawal for cash pool",
        })

        c_bal = await sync_cash_account_balance(db, ca_id)
        assert c_bal == 10000.0

        # 4. Record a cash expense of 1,200
        exp_cash_in = ExpenseIn(
            category="tea_snacks",
            amount=1200.0,
            date="2026-10-23",
            payee="Tea Stall",
            notes="Karigar evening tea",
            cash_ledger_id=cl_id,
            paid_via="cash",
            status="confirmed",
        )
        exp_cash_res = await create_expense(exp_cash_in, req)
        exp_cash_id = exp_cash_res.get("id") or str(exp_cash_res.get("_id"))

        # Verify cash ledger remaining_balance and cash_accounts current_balance reduced
        cl_after = await db.cash_ledger.find_one({"_id": cl_oid})
        assert cl_after["remaining_balance"] == 8800.0
        ca_after = await db.cash_accounts.find_one({"_id": ca_oid})
        assert ca_after["current_balance"] == 8800.0

        # Delete cash expense -> cash restored
        await delete_expense(exp_cash_id, req)
        cl_restored = await db.cash_ledger.find_one({"_id": cl_oid})
        assert cl_restored["remaining_balance"] == 10000.0
        ca_restored = await db.cash_accounts.find_one({"_id": ca_oid})
        assert ca_restored["current_balance"] == 10000.0

        await client.drop_database("test_erp_expense_deductions")

    asyncio.run(_run())


def test_worker_karigar_advance_and_wage_deductions():
    async def _run():
        client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
        db = client["test_erp_worker_deductions"]
        await client.drop_database("test_erp_worker_deductions")

        req = fake_request(db)

        # 1. Setup Bank & Cash Accounts
        bank_oid = ObjectId()
        bank_id = str(bank_oid)
        await db.bank_accounts.insert_one({
            "_id": bank_oid,
            "name": "State Bank Karigar Payout",
            "bank_name": "SBI",
            "opening_balance": 100000.0,
            "current_balance": 100000.0,
            "balance": 100000.0,
        })

        ca_oid = ObjectId()
        ca_id = str(ca_oid)
        cl_oid = ObjectId()
        cl_id = str(cl_oid)
        await db.cash_accounts.insert_one({
            "_id": ca_oid,
            "name": "Factory Petty Cash",
            "source_bank_account_id": bank_id,
            "current_balance": 20000.0,
            "balance": 20000.0,
        })
        await db.cash_ledger.insert_one({
            "_id": cl_oid,
            "bank_account_id": bank_id,
            "amount": 20000.0,
            "remaining_balance": 20000.0,
            "date": "2026-10-23",
            "notes": "Petty cash withdrawal",
        })

        # 2. Setup Worker
        worker_oid = ObjectId()
        wid = str(worker_oid)
        await db.workers.insert_one({
            "_id": worker_oid,
            "name": "Ramesh Kumar (Upper Maker)",
            "skill": "upper",
            "rate_per_pair": 50.0,
            "opening_balance": 5000.0,  # Worker is owed 5000
        })

        # Verify initial payroll net payable
        payroll_init = await compute_payroll(db=db)
        r_init = next(r for r in payroll_init["rows"] if str(r["worker_id"]) == wid)
        assert r_init["net_payable"] == 5000.0

        # 3. Record Karigar Cash Advance of 2,000
        adv_cash_in = AdvanceIn(
            worker_id=wid,
            amount=2000.0,
            date="2026-10-23",
            txn_type="advance",
            paid_via="cash",
            cash_ledger_id=cl_id,
            notes="Festival advance",
        )
        adv_res = await create_advance(adv_cash_in, req)
        adv_id = adv_res["id"]

        # Verify Cash Ledger and Cash Account were deducted by 2,000
        cl_doc = await db.cash_ledger.find_one({"_id": cl_oid})
        assert cl_doc["remaining_balance"] == 18000.0
        ca_doc = await db.cash_accounts.find_one({"_id": ca_oid})
        assert ca_doc["current_balance"] == 18000.0

        # Verify Karigar balance in Payroll was reduced from 5000 to 3000
        payroll_after_adv = await compute_payroll(db=db)
        r_after = next(r for r in payroll_after_adv["rows"] if str(r["worker_id"]) == wid)
        assert r_after["advances_taken"] == 2000.0
        assert r_after["net_payable"] == 3000.0

        # Verify Worker Ledger shows advance as debit reducing closing balance
        ledger_data = await worker_ledger(wid, req)
        assert ledger_data["total_paid"] == 2000.0
        assert ledger_data["closing_balance"] == 3000.0

        # 4. Verify Cash Account unified transactions include this Karigar advance
        txns = await get_cash_account_transactions(ca_id, req)
        adv_txns = [t for t in txns["transactions"] if t.get("source_id") == adv_id]
        assert len(adv_txns) == 1
        assert adv_txns[0]["direction"] == "out"
        assert adv_txns[0]["amount"] == 2000.0

        # 5. Delete advance -> Cash restored, Karigar balance restored
        await delete_advance(adv_id, req)
        cl_restored = await db.cash_ledger.find_one({"_id": cl_oid})
        assert cl_restored["remaining_balance"] == 20000.0
        ca_restored = await db.cash_accounts.find_one({"_id": ca_oid})
        assert ca_restored["current_balance"] == 20000.0

        payroll_restored = await compute_payroll(db=db)
        r_res = next(r for r in payroll_restored["rows"] if str(r["worker_id"]) == wid)
        assert r_res["net_payable"] == 5000.0

        # 6. Record Karigar Bank Advance of 3,000
        adv_bank_in = AdvanceIn(
            worker_id=wid,
            amount=3000.0,
            date="2026-10-23",
            txn_type="advance",
            paid_via="bank_transfer",
            bank_account_id=bank_id,
            notes="Bank advance for medical",
        )
        b_adv_res = await create_advance(adv_bank_in, req)
        b_adv_id = b_adv_res["id"]

        # Verify Bank Account was reduced from 80,000 (100k op - 20k cash withdrawal) to 77,000
        b_doc = await db.bank_accounts.find_one({"_id": bank_oid})
        assert b_doc["current_balance"] == 77000.0

        # Verify Karigar net payable reduced to 2000
        payroll_b_adv = await compute_payroll(db=db)
        r_b_adv = next(r for r in payroll_b_adv["rows"] if str(r["worker_id"]) == wid)
        assert r_b_adv["net_payable"] == 2000.0

        # Delete bank advance -> Bank balance restored to 80,000
        await delete_advance(b_adv_id, req)
        b_doc_res = await db.bank_accounts.find_one({"_id": bank_oid})
        assert b_doc_res["current_balance"] == 80000.0

        # 7. Record Wage Payment via Bank of 2,500
        wp_in = WagePaymentIn(
            worker_id=wid,
            worker_name="Ramesh Kumar (Upper Maker)",
            amount=2500.0,
            period_from="2026-10-01",
            period_to="2026-10-31",
            paid_via="bank_transfer",
            bank_account_id=bank_id,
            date="2026-10-23",
            notes="October partial wage",
        )
        wp_res = await create_wage_payment(wid, wp_in, req)
        assert wp_res["amount"] == 2500.0

        # Verify Bank Account current_balance reduced from 80,000 to 77,500
        b_after_wp = await db.bank_accounts.find_one({"_id": bank_oid})
        assert b_after_wp["current_balance"] == 77500.0

        # Verify Payroll remaining owed is now 2,500 (5,000 owed - 2,500 paid)
        payroll_wp = await compute_payroll(db=db, from_date="2026-10-01", to_date="2026-10-31")
        r_wp = next(r for r in payroll_wp["rows"] if str(r["worker_id"]) == wid)
        assert r_wp["disbursed_amount"] == 2500.0
        assert r_wp["remaining_owed"] == 2500.0

        await client.drop_database("test_erp_worker_deductions")

    asyncio.run(_run())
