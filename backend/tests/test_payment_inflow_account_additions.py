import pytest
import asyncio
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient

from routes.banking import (
    compute_bank_account_balance,
    sync_bank_account_balance,
    sync_cash_account_balance,
    get_cash_account_transactions,
    create_deposit_entry,
)
from routes.pos import (
    create_payment,
    delete_payment,
)
from models.vendors import PaymentIn
from models.banking import DepositCreateIn


class FakeApp:
    def __init__(self, db):
        self.mongodb = db


def fake_request(db, user=None):
    req = MagicMock(spec=Request)
    req.app = FakeApp(db)
    req.state = MagicMock()
    req.state.user = user or {"email": "admin@example.com", "role": "admin", "roles": ["admin"]}
    return req


@pytest.mark.anyio
async def test_payment_inflow_bank_and_cash_additions_and_reversals(monkeypatch):
    """
    Verify end-to-end that:
    1. Client invoice payment recorded against a bank account adds to that bank account's live current_balance.
    2. Direct bank deposit recorded adds to that bank account's live current_balance.
    3. Deleting a payment reduces the account balance back (complete reversal).
    4. Client cash payment adds to the cash account's live balance and appears in cash ledger transactions.
    5. Vendor payment deducts from bank account balance and updates PO financials.
    """
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client["test_erp_payment_inflows"]
    await client.drop_database("test_erp_payment_inflows")

    req = fake_request(db)

    # Monkeypatch get_db and _get_user in routes
    monkeypatch.setattr("routes.pos.get_db", lambda: db)
    monkeypatch.setattr("routes.pos._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin", "roles": ["admin"]}))
    monkeypatch.setattr("routes.banking._get_db", lambda r: db)
    monkeypatch.setattr("routes.banking._get_user", AsyncMock(return_value={"email": "admin@example.com", "role": "admin", "roles": ["admin"]}))

    # 1. Setup Bank Account with opening balance 100,000
    bank_oid = ObjectId()
    bank_id = str(bank_oid)
    await db.bank_accounts.insert_one({
        "_id": bank_oid,
        "name": "State Bank of India",
        "bank_name": "SBI",
        "account_number_last4": "4321",
        "opening_balance": 100000.0,
        "current_balance": 100000.0,
        "balance": 100000.0,
        "active": True,
    })

    bal0 = await sync_bank_account_balance(db, bank_id)
    assert bal0 == 100000.0

    # 2. Setup Client Invoice of 25,000
    inv_oid = ObjectId()
    inv_id = str(inv_oid)
    await db.invoices.insert_one({
        "_id": inv_oid,
        "invoice_no": "INV-2026-001",
        "client_name": "Apex Retail Stores",
        "grand_total": 25000.0,
        "net_amount": 25000.0,
        "invoice_date": "2026-10-20",
        "due_date": "2026-11-20",
    })

    # 3. Record Client Payment of 25,000 into the Bank Account
    pay_payload = PaymentIn(
        invoice_ids=[inv_id],
        amount=25000.0,
        payment_date="2026-10-23",
        mode="Bank Transfer",
        bank="State Bank of India",
        account_type="bank",
        bank_account_id=bank_id,
        reference="NEFT-CLIENT-99182",
        notes="Invoice INV-2026-001 payment",
    )

    created_pay = await create_payment(pay_payload, req)
    pay_id = str(created_pay.get("id") or created_pay.get("_id"))

    # Verify bank account balance is now 125,000 (+25,000 added)
    acc_doc1 = await db.bank_accounts.find_one({"_id": bank_oid})
    assert acc_doc1["current_balance"] == 125000.0

    stats1 = await compute_bank_account_balance(db, bank_id)
    assert stats1["current_balance"] == 125000.0
    assert stats1["client_payments_in"] == 25000.0
    assert stats1["total_received"] == 25000.0

    # 4. Record a Direct Bank Deposit of 10,000 into the Bank Account (e.g. refund / interest)
    dep_payload = DepositCreateIn(
        bank_account_id=bank_id,
        amount=10000.0,
        date="2026-10-23",
        category="interest_income",
        description="Bank Interest Credited",
        remarks="CR-INT-001",
    )
    dep_res = await create_deposit_entry(dep_payload, req)
    assert dep_res["ok"] is True

    # Verify bank account balance is now 135,000 (+10,000 added)
    acc_doc2 = await db.bank_accounts.find_one({"_id": bank_oid})
    assert acc_doc2["current_balance"] == 135000.0

    stats2 = await compute_bank_account_balance(db, bank_id)
    assert stats2["current_balance"] == 135000.0
    assert stats2["total_received"] == 35000.0

    # 5. Delete the Client Payment of 25,000 -> Should revert bank balance to 110,000
    del_res = await delete_payment(pay_id, req)
    assert del_res["ok"] is True

    acc_doc3 = await db.bank_accounts.find_one({"_id": bank_oid})
    assert acc_doc3["current_balance"] == 110000.0

    stats3 = await compute_bank_account_balance(db, bank_id)
    assert stats3["current_balance"] == 110000.0
    assert stats3["total_received"] == 10000.0

    # -------------------------------------------------------------------------
    # 6. Cash Account Test: Client Cash Payment Inflow
    # -------------------------------------------------------------------------
    ca_oid = ObjectId()
    ca_id = str(ca_oid)
    await db.cash_accounts.insert_one({
        "_id": ca_oid,
        "name": "Main Cash Box",
        "source_bank_account_id": bank_id,
        "current_balance": 0.0,
        "balance": 0.0,
        "is_default": True,
    })

    # Add 20,000 withdrawal into cash_ledger
    cl_oid = ObjectId()
    await db.cash_ledger.insert_one({
        "_id": cl_oid,
        "bank_account_id": bank_id,
        "amount": 20000.0,
        "remaining_balance": 20000.0,
        "date": "2026-10-23",
        "notes": "Cash withdrawal from SBI",
    })

    bal_cash0 = await sync_cash_account_balance(db, ca_id)
    assert bal_cash0 == 20000.0

    # Record client payment of 15,000 in Cash
    inv_oid2 = ObjectId()
    inv_id2 = str(inv_oid2)
    await db.invoices.insert_one({
        "_id": inv_oid2,
        "invoice_no": "INV-2026-002",
        "client_name": "City Footwear Hub",
        "grand_total": 15000.0,
        "net_amount": 15000.0,
        "invoice_date": "2026-10-23",
    })

    cash_pay_payload = PaymentIn(
        invoice_ids=[inv_id2],
        amount=15000.0,
        payment_date="2026-10-23",
        mode="Cash",
        account_type="cash",
        cash_account_id=ca_id,
        reference="RECEIPT-CASH-101",
        notes="Counter cash receipt",
    )

    created_cash_pay = await create_payment(cash_pay_payload, req)
    cash_pay_id = str(created_cash_pay.get("id") or created_cash_pay.get("_id"))

    # Cash account balance must now be 35,000 (20,000 + 15,000)
    ca_doc1 = await db.cash_accounts.find_one({"_id": ca_oid})
    assert ca_doc1["current_balance"] == 35000.0

    # Verify cash transactions ledger lists the client payment
    cash_txns = await get_cash_account_transactions(ca_id, req)
    in_txns = [t for t in cash_txns["items"] if t["direction"] == "in"]
    client_in = [t for t in in_txns if t["type"] == "client_payment"]
    assert len(client_in) == 1
    assert client_in[0]["amount"] == 15000.0
    assert client_in[0]["payee"] == "City Footwear Hub"

    # Delete cash payment -> Cash balance must revert back to 20,000
    del_cash_res = await delete_payment(cash_pay_id, req)
    assert del_cash_res["ok"] is True

    ca_doc2 = await db.cash_accounts.find_one({"_id": ca_oid})
    assert ca_doc2["current_balance"] == 20000.0

    # -------------------------------------------------------------------------
    # 7. Vendor Payment Deduction Test via create_payment
    # -------------------------------------------------------------------------
    # Current bank balance is 110,000.
    vendor_oid = ObjectId()
    await db.vendors.insert_one({
        "_id": vendor_oid,
        "name": "Sole Material Supplies",
        "payment_terms_days": 30,
    })

    vpo_oid = ObjectId()
    await db.vendor_purchase_orders.insert_one({
        "_id": vpo_oid,
        "vendor_id": str(vendor_oid),
        "po_number": "VPO-2026-001",
        "total_amount": 50000.0,
        "paid_amount": 0.0,
        "balance_amount": 50000.0,
        "payment_status": "unpaid",
    })

    vp_payload = PaymentIn(
        vendor_id=str(vendor_oid),
        vendor_po_id=str(vpo_oid),
        amount=30000.0,
        payment_date="2026-10-23",
        mode="Bank Transfer",
        bank="State Bank of India",
        account_type="bank",
        bank_account_id=bank_id,
        reference="VEND-PAY-7788",
        notes="Advance to Sole Material Supplies",
    )

    created_vp = await create_payment(vp_payload, req)
    vp_id = str(created_vp.get("id") or created_vp.get("_id"))

    # Bank balance: 100k op + 10k dep - 20k cash withdrawal - 30k vendor payment = 60,000
    acc_doc4 = await db.bank_accounts.find_one({"_id": bank_oid})
    assert acc_doc4["current_balance"] == 60000.0

    # Vendor PO paid_amount must be 30,000, balance 20,000, status partial
    vpo_doc1 = await db.vendor_purchase_orders.find_one({"_id": vpo_oid})
    assert vpo_doc1["paid_amount"] == 30000.0
    assert vpo_doc1["balance_amount"] == 20000.0
    assert vpo_doc1["payment_status"] == "partially_paid"

    # Delete the vendor payment -> Bank balance reverts to 90,000 (100k + 10k - 20k) and PO balance reverts to 50,000
    del_vp_res = await delete_payment(vp_id, req)
    assert del_vp_res["ok"] is True

    acc_doc5 = await db.bank_accounts.find_one({"_id": bank_oid})
    assert acc_doc5["current_balance"] == 90000.0

    vpo_doc2 = await db.vendor_purchase_orders.find_one({"_id": vpo_oid})
    assert vpo_doc2["paid_amount"] == 0.0
    assert vpo_doc2["balance_amount"] == 50000.0
    assert vpo_doc2["payment_status"] == "unpaid"

    await client.drop_database("test_erp_payment_inflows")
