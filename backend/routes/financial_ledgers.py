"""Relational Financial Core & Double-Entry Ledgers Router."""

import logging
from datetime import datetime, date, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from db.postgres import get_pg_db
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
        FiscalYear,
        now_utc,
    )
    from services.financial_ledger_service import (
        post_journal_entry,
        get_general_ledger,
        get_trial_balance,
        post_sales_invoice_voucher,
        post_vendor_bill_voucher,
        post_payment_voucher,
        reconcile_bank_statement_line,
        get_bank_reconciliation_summary,
        check_period_lock,
        to_dec,
    )
except ImportError:
    from backend.db.postgres import get_pg_db
    from backend.models.sql_financials import (
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
        FiscalYear,
        now_utc,
    )
    from backend.services.financial_ledger_service import (
        post_journal_entry,
        get_general_ledger,
        get_trial_balance,
        post_sales_invoice_voucher,
        post_vendor_bill_voucher,
        post_payment_voucher,
        reconcile_bank_statement_line,
        get_bank_reconciliation_summary,
        check_period_lock,
        to_dec,
    )

log = logging.getLogger(__name__)

financial_ledgers_router = APIRouter(prefix="/api/finance", tags=["Financial Core & Ledgers"])


async def _get_user(request: Request) -> dict:
    getter = getattr(request.app, "get_current_user", None)
    if not getter:
        try:
            from server import get_current_user as getter
        except ImportError:
            return {"email": "system@example.com", "role": "admin"}
    return await getter(request)


# ============================================================================
# 0. ENGINE & SUPABASE HEALTH CHECK
# ============================================================================
@financial_ledgers_router.get("/status")
async def get_finance_status(db: AsyncSession = Depends(get_pg_db)):
    """Health check returning SQL engine dialect, accounts count, and Supabase config status."""
    try:
        from db.supabase_client import is_supabase_configured, test_supabase_connection
        supabase_status = await test_supabase_connection()
    except Exception:
        supabase_status = {"configured": False, "connected": False}

    acct_count_res = await db.execute(select(func.count(Account.id)))
    acct_count = acct_count_res.scalar() or 0

    return {
        "status": "healthy",
        "engine_dialect": db.bind.dialect.name if db.bind else "unknown",
        "chart_of_accounts_count": acct_count,
        "supabase": supabase_status,
    }


# ============================================================================
# 1. CHART OF ACCOUNTS
# ============================================================================
@financial_ledgers_router.get("/chart-of-accounts")
async def list_chart_of_accounts(
    account_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_pg_db),
):
    """List chart of accounts with optional filtering."""
    query = select(Account).order_by(Account.code.asc())
    filters = []
    if account_type:
        filters.append(Account.account_type == account_type.upper())
    if is_active is not None:
        filters.append(Account.is_active == is_active)
    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query)
    accounts = result.scalars().all()
    return [
        {
            "id": a.id,
            "code": a.code,
            "name": a.name,
            "account_type": a.account_type,
            "sub_type": a.sub_type,
            "currency": a.currency,
            "is_active": a.is_active,
            "is_reconcilable": a.is_reconcilable,
            "description": a.description,
        }
        for a in accounts
    ]


@financial_ledgers_router.post("/chart-of-accounts")
async def create_account(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    """Create a new account in chart of accounts."""
    u = await _get_user(request)
    code = payload.get("code", "").strip()
    name = payload.get("name", "").strip()
    account_type = payload.get("account_type", "").strip().upper()
    sub_type = payload.get("sub_type", "").strip().upper()

    if not code or not name or not account_type or not sub_type:
        raise HTTPException(400, "code, name, account_type, and sub_type are required.")

    existing = await db.execute(select(Account).where(Account.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Account with code '{code}' already exists.")

    account = Account(
        code=code,
        name=name,
        account_type=account_type,
        sub_type=sub_type,
        is_reconcilable=payload.get("is_reconcilable", False),
        description=payload.get("description"),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {"ok": True, "account": {"id": account.id, "code": account.code, "name": account.name}}


# ============================================================================
# 2. FINANCIAL ENTITIES (Sub-ledger Partners)
# ============================================================================
@financial_ledgers_router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_pg_db),
):
    query = select(FinancialEntity).order_by(FinancialEntity.name.asc())
    if entity_type:
        query = query.where(FinancialEntity.entity_type == entity_type.upper())
    result = await db.execute(query)
    entities = result.scalars().all()
    return [
        {
            "id": e.id,
            "entity_type": e.entity_type,
            "code": e.code,
            "name": e.name,
            "gstin": e.gstin,
            "pan": e.pan,
            "external_ref_id": e.external_ref_id,
            "gl_account_id": e.gl_account_id,
        }
        for e in entities
    ]


@financial_ledgers_router.post("/entities")
async def create_entity(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    code = payload.get("code", "").strip()
    name = payload.get("name", "").strip()
    entity_type = payload.get("entity_type", "").strip().upper()
    gl_account_id = payload.get("gl_account_id")

    if not code or not name or not entity_type:
        raise HTTPException(400, "code, name, and entity_type are required.")

    if not gl_account_id:
        # Default GL account by entity type
        def_code = "1030" if entity_type == "CLIENT" else ("2010" if entity_type == "VENDOR" else "2020")
        acct_res = await db.execute(select(Account.id).where(Account.code == def_code))
        gl_account_id = acct_res.scalar_one_or_none()
        if not gl_account_id:
            raise HTTPException(400, f"Default GL account {def_code} not found. Please provide gl_account_id.")

    existing = await db.execute(select(FinancialEntity).where(FinancialEntity.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Entity code '{code}' already exists.")

    entity = FinancialEntity(
        code=code,
        name=name,
        entity_type=entity_type,
        gl_account_id=gl_account_id,
        external_ref_id=payload.get("external_ref_id"),
        gstin=payload.get("gstin"),
        pan=payload.get("pan"),
        phone=payload.get("phone"),
        email=payload.get("email"),
        billing_address=payload.get("billing_address"),
        payment_terms_days=payload.get("payment_terms_days", 30),
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return {"ok": True, "entity": {"id": entity.id, "code": entity.code, "name": entity.name}}


# ============================================================================
# 3. DOUBLE-ENTRY JOURNAL ENTRIES
# ============================================================================
@financial_ledgers_router.post("/journal-entries")
async def create_journal_entry(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    """Post a balanced double-entry journal transaction."""
    u = await _get_user(request)
    entry_data = payload.get("entry", {})
    lines_data = payload.get("lines", [])

    entry_data["posted_by"] = u.get("email", "system")

    try:
        async with db.begin():
            entry = await post_journal_entry(db, entry_data, lines_data)
            return {
                "ok": True,
                "journal_entry": {
                    "id": entry.id,
                    "entry_number": entry.entry_number,
                    "entry_date": entry.entry_date.isoformat(),
                    "total_debit": float(entry.total_debit),
                    "total_credit": float(entry.total_credit),
                    "status": entry.status,
                },
            }
    except ValueError as ve:
        raise HTTPException(422, str(ve))
    except Exception as e:
        log.exception("Journal entry creation failed: %s", e)
        raise HTTPException(500, f"Failed to post journal entry: {e}")


@financial_ledgers_router.get("/journal-entries")
async def list_journal_entries(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    entry_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_pg_db),
):
    query = select(JournalEntry).order_by(desc(JournalEntry.entry_date), desc(JournalEntry.posted_at))
    filters = []
    if from_date:
        filters.append(JournalEntry.entry_date >= datetime.strptime(from_date, "%Y-%m-%d").date())
    if to_date:
        filters.append(JournalEntry.entry_date <= datetime.strptime(to_date, "%Y-%m-%d").date())
    if entry_type:
        filters.append(JournalEntry.entry_type == entry_type.upper())
    if filters:
        query = query.where(and_(*filters))

    query = query.limit(limit)
    res = await db.execute(query)
    entries = res.scalars().all()
    return [
        {
            "id": e.id,
            "entry_number": e.entry_number,
            "entry_date": e.entry_date.isoformat(),
            "entry_type": e.entry_type,
            "narration": e.narration,
            "source_ref": e.source_document_ref,
            "total_debit": float(e.total_debit),
            "total_credit": float(e.total_credit),
            "status": e.status,
            "posted_by": e.posted_by,
        }
        for e in entries
    ]


# ============================================================================
# 4. GENERAL LEDGER & TRIAL BALANCE
# ============================================================================
@financial_ledgers_router.get("/ledger/{account_code_or_id}")
async def get_account_ledger(
    account_code_or_id: str,
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_pg_db),
):
    """Retrieve detailed chronological general ledger with running balance."""
    fd = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else None
    td = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else None

    try:
        ledger = await get_general_ledger(db, account_code_or_id, from_date=fd, to_date=td)
        return ledger
    except ValueError as ve:
        raise HTTPException(404, str(ve))


@financial_ledgers_router.get("/trial-balance")
async def get_company_trial_balance(
    as_of_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_pg_db),
):
    """Retrieve trial balance confirming sum(debit) == sum(credit)."""
    aod = datetime.strptime(as_of_date, "%Y-%m-%d").date() if as_of_date else date.today()
    try:
        tb = await get_trial_balance(db, as_of_date=aod)
        return tb
    except Exception as e:
        log.exception("Trial balance query failed: %s", e)
        raise HTTPException(500, f"Error generating trial balance: {e}")


# ============================================================================
# 5. SALES INVOICES & VENDOR BILLS
# ============================================================================
@financial_ledgers_router.post("/invoices")
async def create_sales_invoice(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    payload["posted_by"] = u.get("email", "system")
    try:
        async with db.begin():
            inv, je = await post_sales_invoice_voucher(db, payload)
            return {
                "ok": True,
                "invoice": {
                    "id": inv.id,
                    "invoice_no": inv.invoice_no,
                    "grand_total": float(inv.grand_total),
                    "net_receivable": float(inv.net_receivable),
                    "status": inv.status,
                    "journal_entry_id": je.id,
                },
            }
    except ValueError as ve:
        raise HTTPException(422, str(ve))
    except Exception as e:
        log.exception("Sales invoice posting failed: %s", e)
        raise HTTPException(500, f"Error posting sales invoice: {e}")


@financial_ledgers_router.post("/vendor-bills")
async def create_vendor_bill(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    payload["posted_by"] = u.get("email", "system")
    try:
        async with db.begin():
            bill, je = await post_vendor_bill_voucher(db, payload)
            return {
                "ok": True,
                "bill": {
                    "id": bill.id,
                    "bill_no": bill.bill_no,
                    "total_amount": float(bill.total_amount),
                    "status": bill.status,
                    "journal_entry_id": je.id,
                },
            }
    except ValueError as ve:
        raise HTTPException(422, str(ve))
    except Exception as e:
        log.exception("Vendor bill posting failed: %s", e)
        raise HTTPException(500, f"Error posting vendor bill: {e}")


# ============================================================================
# 6. PAYMENT VOUCHERS & ALLOCATIONS
# ============================================================================
@financial_ledgers_router.post("/vouchers")
async def create_voucher(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    voucher_data = payload.get("voucher", payload)
    allocations = payload.get("allocations", [])
    voucher_data["posted_by"] = u.get("email", "system")

    try:
        async with db.begin():
            voucher, je = await post_payment_voucher(db, voucher_data, allocations=allocations)
            return {
                "ok": True,
                "voucher": {
                    "id": voucher.id,
                    "voucher_no": voucher.voucher_no,
                    "voucher_type": voucher.voucher_type,
                    "amount": float(voucher.amount),
                    "journal_entry_id": je.id,
                },
            }
    except ValueError as ve:
        raise HTTPException(422, str(ve))
    except Exception as e:
        log.exception("Voucher creation failed: %s", e)
        raise HTTPException(500, f"Error creating voucher: {e}")


# ============================================================================
# 7. BANK RECONCILIATION & STATEMENTS
# ============================================================================
@financial_ledgers_router.post("/bank-reconcile")
async def reconcile_statement_row(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    stmt_line_id = payload.get("statement_line_id")
    voucher_id = payload.get("voucher_id")
    journal_line_id = payload.get("journal_line_id")
    remarks = payload.get("remarks")

    if not stmt_line_id:
        raise HTTPException(400, "statement_line_id is required.")

    try:
        async with db.begin():
            line = await reconcile_bank_statement_line(
                db,
                stmt_line_id=stmt_line_id,
                voucher_id=voucher_id,
                journal_line_id=journal_line_id,
                matched_by=u.get("email", "system"),
                remarks=remarks,
            )
            return {
                "ok": True,
                "reconciled_line": {
                    "id": line.id,
                    "match_status": line.match_status,
                    "reconciled_at": line.reconciled_at.isoformat() if line.reconciled_at else None,
                },
            }
    except ValueError as ve:
        raise HTTPException(422, str(ve))
    except Exception as e:
        log.exception("Bank reconciliation failed: %s", e)
        raise HTTPException(500, f"Bank reconciliation error: {e}")


@financial_ledgers_router.get("/bank-reconciliation-statement/{bank_account_id}")
async def get_brs(
    bank_account_id: str,
    as_of_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_pg_db),
):
    aod = datetime.strptime(as_of_date, "%Y-%m-%d").date() if as_of_date else date.today()
    try:
        brs = await get_bank_reconciliation_summary(db, bank_account_id, as_of_date=aod)
        return brs
    except ValueError as ve:
        raise HTTPException(404, str(ve))


# ============================================================================
# 8. ACCOUNTING PERIOD LOCKS
# ============================================================================
@financial_ledgers_router.post("/periods/lock")
async def lock_period(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    period_from = datetime.strptime(payload["period_from"], "%Y-%m-%d").date()
    period_to = datetime.strptime(payload["period_to"], "%Y-%m-%d").date()

    lock = AccountingPeriodLock(
        bank_account_id=payload.get("bank_account_id"),
        period_from=period_from,
        period_to=period_to,
        locked_by=u.get("email", "admin"),
        lock_reason=payload.get("lock_reason", "Period closed by accounting"),
    )
    db.add(lock)
    await db.commit()
    await db.refresh(lock)
    return {"ok": True, "lock": {"id": lock.id, "period_from": lock.period_from.isoformat(), "period_to": lock.period_to.isoformat()}}


@financial_ledgers_router.post("/periods/unlock")
async def unlock_period(
    payload: Dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_pg_db),
):
    u = await _get_user(request)
    lock_id = payload.get("lock_id")
    if not lock_id:
        raise HTTPException(400, "lock_id is required.")

    lock = await db.get(AccountingPeriodLock, lock_id)
    if not lock:
        raise HTTPException(404, "Lock not found.")

    lock.unlocked_at = now_utc()
    lock.unlocked_by = u.get("email", "admin")
    lock.unlock_reason = payload.get("unlock_reason", "Authorized unlock")
    await db.commit()
    return {"ok": True, "unlocked": True}


@financial_ledgers_router.get("/periods/locks")
async def list_period_locks(db: AsyncSession = Depends(get_pg_db)):
    """List all period locks with active/unlocked status."""
    stmt = select(AccountingPeriodLock).order_by(AccountingPeriodLock.period_from.desc())
    res = await db.execute(stmt)
    locks = res.scalars().all()
    return [
        {
            "id": l.id,
            "bank_account_id": l.bank_account_id,
            "period_from": l.period_from.isoformat(),
            "period_to": l.period_to.isoformat(),
            "locked_at": l.locked_at.isoformat() if l.locked_at else None,
            "locked_by": l.locked_by,
            "lock_reason": l.lock_reason,
            "unlocked_at": l.unlocked_at.isoformat() if l.unlocked_at else None,
            "unlocked_by": l.unlocked_by,
            "unlock_reason": l.unlock_reason,
            "is_active": l.unlocked_at is None,
        }
        for l in locks
    ]


@financial_ledgers_router.get("/bank-accounts")
async def list_finance_bank_accounts(db: AsyncSession = Depends(get_pg_db)):
    """List registered bank accounts with GL accounts in PostgreSQL."""
    stmt = select(BankAccount).order_by(BankAccount.bank_name.asc())
    res = await db.execute(stmt)
    accounts = res.scalars().all()
    return [
        {
            "id": b.id,
            "bank_name": b.bank_name,
            "account_number": b.account_number,
            "ifsc_code": b.ifsc_code,
            "branch_name": b.branch_name,
            "currency": b.currency,
            "gl_account_id": b.gl_account_id,
            "is_active": b.is_active,
        }
        for b in accounts
    ]
