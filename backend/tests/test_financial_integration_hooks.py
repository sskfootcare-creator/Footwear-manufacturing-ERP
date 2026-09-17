"""Unit and integration tests for Financial Core auto-posting hooks."""

import asyncio
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from db.postgres import Base
from models.sql_financials import (
    Account,
    FinancialEntity,
    JournalEntry,
    JournalLine,
    SalesInvoice,
    VendorBill,
    PaymentVoucher,
)
from scripts.seed_chart_of_accounts import seed_chart_of_accounts
from services.financial_ledger_service import (
    get_or_create_financial_entity,
    post_sales_invoice_voucher,
    post_vendor_bill_voucher,
    post_payment_voucher,
    get_trial_balance,
)


def run_async(coro):
    return asyncio.run(coro)


async def _setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as sess:
        await seed_chart_of_accounts(sess)
    return engine, session_factory


def test_entity_auto_creation():
    """Verify get_or_create_financial_entity finds or auto-creates subledger entities."""
    async def _test():
        engine, session_factory = await _setup_db()
        async with session_factory() as sess:
            # 1. Create client entity
            e1 = await get_or_create_financial_entity(
                sess,
                name="Metro Footwear Traders",
                entity_type="CLIENT",
                gstin="07AABCM1234F1Z1",
            )
            assert e1.id is not None
            assert e1.entity_type == "CLIENT"
            assert e1.name == "Metro Footwear Traders"

            # 2. Idempotent retrieval by name
            e2 = await get_or_create_financial_entity(
                sess,
                name="metro footwear traders",
                entity_type="CLIENT",
            )
            assert e2.id == e1.id

            # 3. Create vendor entity
            v1 = await get_or_create_financial_entity(
                sess,
                name="Apex Rubber & Soles Ltd",
                entity_type="VENDOR",
            )
            assert v1.id is not None
            assert v1.entity_type == "VENDOR"

    run_async(_test())


def test_sales_invoice_auto_post():
    """Verify posting a sales invoice creates balanced journal entry and updates TB."""
    async def _test():
        engine, session_factory = await _setup_db()
        async with session_factory() as sess:
            sales_inv, je = await post_sales_invoice_voucher(
                sess,
                {
                    "invoice_no": "INV-2026-001",
                    "client_name": "Liberty Footwear Store",
                    "invoice_date": "2026-09-17",
                    "po_number": "PO-1001",
                    "subtotal": 100000.0,
                    "cgst_amount": 6000.0,
                    "sgst_amount": 6000.0,
                    "igst_amount": 0.0,
                    "tcs_amount": 0.0,
                    "grn_adjustment": 0.0,
                }
            )
            await sess.commit()

            assert sales_inv.invoice_no == "INV-2026-001"
            assert sales_inv.grand_total == Decimal("112000.00")
            assert je.total_debit == je.total_credit
            assert je.status == "POSTED"

            # Verify Trial balance stays balanced
            tb = await get_trial_balance(sess, as_of_date=date(2026, 9, 17))
            assert tb["is_balanced"] is True
            assert tb["total_debit"] == tb["total_credit"] == 112000.0

    run_async(_test())


def test_vendor_bill_and_payment_flow():
    """Verify vendor bill receipt and subsequent payment voucher keeps books balanced."""
    async def _test():
        engine, session_factory = await _setup_db()
        async with session_factory() as sess:
            # 1. Receive Material (Vendor Bill)
            bill, je_bill = await post_vendor_bill_voucher(
                sess,
                {
                    "bill_no": "GRN-VPO-001-1",
                    "vendor_name": "Classic Leather Corp",
                    "bill_date": "2026-09-17",
                    "subtotal": 50000.0,
                    "cgst_amount": 2500.0,
                    "sgst_amount": 2500.0,
                }
            )
            await sess.commit()
            assert je_bill.total_debit == je_bill.total_credit
            assert bill.total_amount == Decimal("55000.00")

            # 2. Pay Vendor via Bank
            pv, je_pay = await post_payment_voucher(
                sess,
                {
                    "voucher_type": "PAYMENT",
                    "voucher_date": "2026-09-18",
                    "amount": 55000.0,
                    "entity_name": "Classic Leather Corp",
                    "payment_mode": "BANK",
                    "reference_number": "NEFT-998822",
                }
            )
            await sess.commit()
            assert je_pay.total_debit == je_pay.total_credit

            # 3. Verify Trial balance is balanced
            tb = await get_trial_balance(sess, as_of_date=date(2026, 9, 18))
            assert tb["is_balanced"] is True

    run_async(_test())
