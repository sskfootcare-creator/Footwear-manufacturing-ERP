"""Unit and integration tests for PostgreSQL / Supabase Financial Core and Ledgers."""

import os
import sys
import asyncio
from datetime import date, datetime
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from db.postgres import Base
from models.sql_financials import (
    Account,
    FinancialEntity,
    BankAccount,
    CashRegister,
    JournalEntry,
    JournalLine,
    SalesInvoice,
    VendorBill,
    PaymentVoucher,
    VoucherAllocation,
    BankStatementLine,
    AccountingPeriodLock,
)
from scripts.seed_chart_of_accounts import seed_chart_of_accounts
from services.financial_ledger_service import (
    post_journal_entry,
    get_general_ledger,
    get_trial_balance,
    post_sales_invoice_voucher,
    post_vendor_bill_voucher,
    post_payment_voucher,
    reconcile_bank_statement_line,
    get_bank_reconciliation_summary,
    to_dec,
)


def run_async(coro):
    """Run an async coroutine synchronously inside standard pytest test."""
    return asyncio.run(coro)


async def _setup_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


def test_chart_of_accounts_seeded():
    """Verify standard Indian footwear chart of accounts is fully seeded."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)
            tb = await get_trial_balance(session)
            assert tb["is_balanced"] is True
            accounts = (await session.execute(Account.__table__.select())).fetchall()
            assert len(accounts) >= 30
        await engine.dispose()

    run_async(_test())


def test_double_entry_balance_enforcement():
    """Assert unbalanced journal entry (Debit != Credit) is strictly rejected."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            # Unbalanced: ₹10,000 debit vs ₹8,000 credit
            unbalanced_lines = [
                {"account_code": "1010-HDFC-MAIN", "debit": 10000, "credit": 0},
                {"account_code": "4010", "debit": 0, "credit": 8000},
            ]
            with pytest.raises(ValueError, match="Double-entry equation violated"):
                await post_journal_entry(
                    session,
                    {"entry_date": date(2026, 4, 10), "narration": "Unbalanced test"},
                    unbalanced_lines,
                )

            # Balanced: ₹10,000 debit == ₹10,000 credit
            balanced_lines = [
                {"account_code": "1010-HDFC-MAIN", "debit": 10000, "credit": 0},
                {"account_code": "4010", "debit": 0, "credit": 10000},
            ]
            entry = await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 10), "narration": "Balanced test entry"},
                balanced_lines,
            )
            assert entry.id is not None
            assert entry.total_debit == Decimal("10000.00")
            assert entry.total_credit == Decimal("10000.00")
        await engine.dispose()

    run_async(_test())


def test_general_ledger_running_balance():
    """Verify chronological movements, opening balance, and running balance calculation."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            # Entry 1: 2026-04-01 Deposit ₹50,000
            await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 1), "narration": "Capital injection"},
                [
                    {"account_code": "1010-HDFC-MAIN", "debit": 50000, "credit": 0},
                    {"account_code": "3010", "debit": 0, "credit": 50000},
                ],
            )
            # Entry 2: 2026-04-05 Spend ₹15,000 on Rent
            await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 5), "narration": "Rent payment"},
                [
                    {"account_code": "5030", "debit": 15000, "credit": 0},
                    {"account_code": "1010-HDFC-MAIN", "debit": 0, "credit": 15000},
                ],
            )
            # Entry 3: 2026-04-10 Receive ₹20,000 B2B Sales
            await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 10), "narration": "Direct sale"},
                [
                    {"account_code": "1010-HDFC-MAIN", "debit": 20000, "credit": 0},
                    {"account_code": "4010", "debit": 0, "credit": 20000},
                ],
            )

            ledger = await get_general_ledger(session, "1010-HDFC-MAIN")
            assert ledger["total_debit"] == 70000.00
            assert ledger["total_credit"] == 15000.00
            assert ledger["closing_balance"] == 55000.00  # 50,000 - 15,000 + 20,000
            assert len(ledger["entries"]) == 3
            assert ledger["entries"][0]["running_balance"] == 50000.00
            assert ledger["entries"][1]["running_balance"] == 35000.00
            assert ledger["entries"][2]["running_balance"] == 55000.00
        await engine.dispose()

    run_async(_test())


def test_trial_balance_mathematical_equality():
    """Confirm that the trial balance maintains net zero imbalance across multiple accounts."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            # 1. Capital: Bank +1,00,000, Equity +1,00,000
            await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 1), "narration": "Capital"},
                [
                    {"account_code": "1010-HDFC-MAIN", "debit": 100000, "credit": 0},
                    {"account_code": "3010", "debit": 0, "credit": 100000},
                ],
            )
            # 2. Buy RM: RM Expense +40,000, CGST +3,600, SGST +3,600, AP +47,200
            await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 2), "narration": "RM Purchase"},
                [
                    {"account_code": "5010", "debit": 40000, "credit": 0},
                    {"account_code": "1060-CGST-IN", "debit": 3600, "credit": 0},
                    {"account_code": "1060-SGST-IN", "debit": 3600, "credit": 0},
                    {"account_code": "2010", "debit": 0, "credit": 47200},
                ],
            )

            tb = await get_trial_balance(session)
            assert tb["is_balanced"] is True
            assert tb["difference"] == 0.00
            assert tb["total_debit"] == tb["total_credit"] == 147200.00
        await engine.dispose()

    run_async(_test())


def test_sales_invoice_voucher_and_allocation():
    """Test full cycle: Client creation, Invoice posting, and partial payment voucher allocation."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            ar_id = (await session.execute(Account.__table__.select().where(Account.code == "1030"))).scalar()
            bank_gl_id = (await session.execute(Account.__table__.select().where(Account.code == "1010-HDFC-MAIN"))).scalar()

            client = FinancialEntity(
                code="CLI-METRO-001",
                name="Metro Brands Ltd",
                entity_type="CLIENT",
                gl_account_id=ar_id,
            )
            session.add(client)
            await session.flush()
            bank = BankAccount(
                entity_id=client.id,
                gl_account_id=bank_gl_id,
                account_name="SSK HDFC Current",
                bank_name="HDFC Bank",
                account_number="50200012345678",
                account_number_last4="5678",
                ifsc="HDFC0001234",
                opening_balance=Decimal("0.00"),
            )
            session.add(bank)
            await session.flush()

            # Post Invoice: ₹1,00,000 subtotal + ₹18,000 GST = ₹1,18,000
            inv, je = await post_sales_invoice_voucher(
                session,
                {
                    "invoice_no": "SSK/26-27/0001",
                    "invoice_date": date(2026, 4, 15),
                    "client_id": client.id,
                    "subtotal": 100000,
                    "cgst_amount": 9000,
                    "sgst_amount": 9000,
                },
            )
            assert inv.grand_total == Decimal("118000.00")
            assert inv.paid_amount == Decimal("0.00")
            assert inv.status == "POSTED"

            # Partial Receipt Voucher ₹50,000
            v1, je1 = await post_payment_voucher(
                session,
                {
                    "voucher_type": "RECEIPT",
                    "voucher_date": date(2026, 4, 20),
                    "entity_id": client.id,
                    "bank_account_id": bank.id,
                    "amount": 50000,
                    "reference_number": "UTR50000NEFT",
                },
                allocations=[{"sales_invoice_id": inv.id, "allocated_amount": 50000}],
            )
            assert inv.paid_amount == Decimal("50000.00")
            assert inv.status == "PARTIALLY_PAID"

            # Final Receipt Voucher ₹68,000
            v2, je2 = await post_payment_voucher(
                session,
                {
                    "voucher_type": "RECEIPT",
                    "voucher_date": date(2026, 4, 25),
                    "entity_id": client.id,
                    "bank_account_id": bank.id,
                    "amount": 68000,
                    "reference_number": "UTR68000NEFT",
                },
                allocations=[{"sales_invoice_id": inv.id, "allocated_amount": 68000}],
            )
            assert inv.paid_amount == Decimal("118000.00")
            assert inv.status == "PAID"
        await engine.dispose()

    run_async(_test())


def test_period_lock_blocks_entry():
    """Verify that entries in locked accounting periods are rejected."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            lock = AccountingPeriodLock(
                period_from=date(2026, 4, 1),
                period_to=date(2026, 4, 30),
                locked_by="auditor@example.com",
                lock_reason="FY Close Audited",
            )
            session.add(lock)
            await session.flush()

            with pytest.raises(ValueError, match="is locked"):
                await post_journal_entry(
                    session,
                    {"entry_date": date(2026, 4, 15), "narration": "Post in locked period"},
                    [
                        {"account_code": "1010-HDFC-MAIN", "debit": 5000, "credit": 0},
                        {"account_code": "4010", "debit": 0, "credit": 5000},
                    ],
                )

            lock.unlocked_at = datetime.now()
            lock.unlocked_by = "admin@example.com"
            await session.flush()

            entry = await post_journal_entry(
                session,
                {"entry_date": date(2026, 4, 15), "narration": "Post in unlocked period"},
                [
                    {"account_code": "1010-HDFC-MAIN", "debit": 5000, "credit": 0},
                    {"account_code": "4010", "debit": 0, "credit": 5000},
                ],
            )
            assert entry.id is not None
        await engine.dispose()

    run_async(_test())


def test_bank_reconciliation_cleared_balance():
    """Verify bank statement line matching updates cleared balance atomically."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            bank_gl_id = (await session.execute(Account.__table__.select().where(Account.code == "1010-HDFC-MAIN"))).scalar()

            entity = FinancialEntity(
                code="BANK-HDFC-ENT",
                name="HDFC Bank Entity",
                entity_type="BANK",
                gl_account_id=bank_gl_id,
            )
            session.add(entity)
            await session.flush()
            bank_acc = BankAccount(
                entity_id=entity.id,
                gl_account_id=entity.gl_account_id,
                account_name="HDFC Main",
                bank_name="HDFC Bank",
                account_number="1234567890",
                account_number_last4="7890",
                ifsc="HDFC0001234",
                opening_balance=Decimal("100000.00"),
                current_cleared_balance=Decimal("100000.00"),
            )
            session.add(bank_acc)
            await session.flush()

            stmt_line = BankStatementLine(
                bank_account_id=bank_acc.id,
                transaction_date=date(2026, 4, 12),
                narration="NEFT from Metro Brands",
                credit_amount=Decimal("25000.00"),
                debit_amount=Decimal("0.00"),
                match_status="UNMATCHED",
            )
            session.add(stmt_line)
            await session.flush()

            reconciled = await reconcile_bank_statement_line(
                session,
                stmt_line_id=stmt_line.id,
                matched_by="accountant@example.com",
                remarks="Verified against UTR",
            )
            assert reconciled.match_status == "MATCHED"
            assert bank_acc.current_cleared_balance == Decimal("125000.00")
        await engine.dispose()

    run_async(_test())


def test_vendor_bill_voucher_and_allocation():
    """Test full AP cycle: Vendor creation, Bill posting, and partial payment voucher allocation."""
    async def _test():
        engine, session_factory = await _setup_test_db()
        async with session_factory() as session:
            await seed_chart_of_accounts(session)

            ap_id = (await session.execute(Account.__table__.select().where(Account.code == "2010"))).scalar()
            bank_gl_id = (await session.execute(Account.__table__.select().where(Account.code == "1010-HDFC-MAIN"))).scalar()

            vendor = FinancialEntity(
                code="VEN-SYNTH-001",
                name="Prime Synthetic Leathers",
                entity_type="VENDOR",
                gl_account_id=ap_id,
            )
            session.add(vendor)
            await session.flush()
            bank = BankAccount(
                entity_id=vendor.id,
                gl_account_id=bank_gl_id,
                account_name="SSK HDFC Current",
                bank_name="HDFC Bank",
                account_number="50200012345678",
                account_number_last4="5678",
                ifsc="HDFC0001234",
                opening_balance=Decimal("0.00"),
            )
            session.add(bank)
            await session.flush()

            # Post Vendor Bill: ₹60,000 subtotal + ₹10,800 GST = ₹70,800
            bill, je = await post_vendor_bill_voucher(
                session,
                {
                    "bill_no": "BILL/SYN/2026/042",
                    "bill_date": date(2026, 4, 18),
                    "vendor_id": vendor.id,
                    "subtotal": 60000,
                    "cgst_amount": 5400,
                    "sgst_amount": 5400,
                },
            )
            assert bill.total_amount == Decimal("70800.00")
            assert bill.paid_amount == Decimal("0.00")
            assert bill.status == "POSTED"

            # Payment voucher ₹70,800
            pv, je_pv = await post_payment_voucher(
                session,
                {
                    "voucher_type": "PAYMENT",
                    "voucher_date": date(2026, 4, 25),
                    "entity_id": vendor.id,
                    "bank_account_id": bank.id,
                    "amount": 70800,
                    "reference_number": "UTR-PAY-70800",
                },
                allocations=[{"vendor_bill_id": bill.id, "allocated_amount": 70800}],
            )
            assert bill.paid_amount == Decimal("70800.00")
            assert bill.status == "PAID"
        await engine.dispose()

    run_async(_test())


def test_fastapi_financial_endpoints():
    """Verify FastAPI router endpoints via httpx AsyncClient."""
    from httpx import ASGITransport, AsyncClient
    from server import app
    from db.postgres import get_pg_db

    async def _test():
        engine, session_factory = await _setup_test_db()

        async def override_get_pg_db():
            async with session_factory() as s:
                yield s

        app.dependency_overrides[get_pg_db] = override_get_pg_db

        async with session_factory() as session:
            await seed_chart_of_accounts(session)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            res = await ac.get("/api/finance/status")
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "healthy"
            assert data["chart_of_accounts_count"] >= 30

            res_coa = await ac.get("/api/finance/chart-of-accounts")
            assert res_coa.status_code == 200
            coa_list = res_coa.json()
            assert len(coa_list) >= 30

            res_tb = await ac.get("/api/finance/trial-balance")
            assert res_tb.status_code == 200
            tb_data = res_tb.json()
            assert tb_data["is_balanced"] is True

        app.dependency_overrides.clear()
        await engine.dispose()

    run_async(_test())


def test_cloud_isolation_and_github_activation(monkeypatch):
    """Verify Supabase Cloud is isolated in local dev and activated only on GitHub / Production."""
    from db.postgres import get_database_url, is_cloud_allowed
    from db.supabase_client import is_supabase_configured

    # Case 1: Local development environment
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("ALLOW_CLOUD_IN_DEV", raising=False)
    monkeypatch.setenv("POSTGRES_URL", "postgresql://postgres:secret@db.xyz.supabase.co:5432/postgres")
    monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "secret-key")

    assert is_cloud_allowed() is False
    # Must fallback to local sqlite in dev to prevent accidental cloud mutations
    assert get_database_url().startswith("sqlite+aiosqlite:///")
    assert is_supabase_configured() is False

    # Case 2: Running in GitHub Actions CI/CD
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert is_cloud_allowed() is True
    assert "xyz.supabase.co" in get_database_url()
    assert is_supabase_configured() is True

    # Case 3: Running in Production
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert is_cloud_allowed() is True
    assert "xyz.supabase.co" in get_database_url()
    assert is_supabase_configured() is True


