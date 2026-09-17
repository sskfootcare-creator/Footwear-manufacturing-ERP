"""Transactional Double-Entry General Ledger & Financial Services."""

import os
import sys
from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

try:
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
        BankReconciliationStatement,
        MarketplaceSettlement,
        AccountingPeriodLock,
        FiscalYear,
        gen_uuid,
        now_utc,
    )
except ImportError:
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
        BankReconciliationStatement,
        MarketplaceSettlement,
        AccountingPeriodLock,
        FiscalYear,
        gen_uuid,
        now_utc,
    )


def to_dec(val: Any) -> Decimal:
    """Convert any numeric value to Decimal with 2 decimal places."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ============================================================================
# PERIOD LOCK CHECKS
# ============================================================================
async def check_period_lock(
    session: AsyncSession,
    entry_date: date,
    bank_account_id: Optional[str] = None,
) -> None:
    """Raise ValueError if the given date falls into an active locked accounting period."""
    conditions = [
        AccountingPeriodLock.period_from <= entry_date,
        AccountingPeriodLock.period_to >= entry_date,
        AccountingPeriodLock.unlocked_at.is_(None),
    ]
    if bank_account_id:
        conditions.append(
            or_(
                AccountingPeriodLock.bank_account_id.is_(None),
                AccountingPeriodLock.bank_account_id == bank_account_id,
            )
        )
    else:
        conditions.append(AccountingPeriodLock.bank_account_id.is_(None))

    stmt = select(AccountingPeriodLock).where(and_(*conditions))
    res = await session.execute(stmt)
    lock = res.scalars().first()
    if lock:
        raise ValueError(
            f"Accounting period for date {entry_date} is locked: '{lock.lock_reason}' (Locked by {lock.locked_by}). Unlock period before posting."
        )


# ============================================================================
# DOUBLE-ENTRY CORE: POST JOURNAL ENTRY
# ============================================================================
async def post_journal_entry(
    session: AsyncSession,
    entry_data: Dict[str, Any],
    lines_data: List[Dict[str, Any]],
) -> JournalEntry:
    """
    Atomically post a balanced Double-Entry Journal Entry.
    Enforces that sum(debit) == sum(credit) > 0 and period is not locked.
    """
    if len(lines_data) < 2:
        raise ValueError("A journal entry requires at least 2 legs (debit and credit).")

    entry_date = entry_data.get("entry_date")
    if isinstance(entry_date, str):
        entry_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    elif not isinstance(entry_date, date):
        entry_date = date.today()

    await check_period_lock(session, entry_date)

    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    processed_lines = []

    for idx, ld in enumerate(lines_data, start=1):
        debit = to_dec(ld.get("debit", 0))
        credit = to_dec(ld.get("credit", 0))

        if debit < 0 or credit < 0:
            raise ValueError(f"Line {idx}: Debits and credits must be non-negative.")
        if debit > 0 and credit > 0:
            raise ValueError(f"Line {idx}: A journal line cannot have both debit and credit amounts.")

        total_debit += debit
        total_credit += credit

        # Resolve account_id if account_code was supplied
        account_id = ld.get("account_id")
        if not account_id and ld.get("account_code"):
            acct_stmt = select(Account.id).where(Account.code == ld["account_code"])
            acct_res = await session.execute(acct_stmt)
            account_id = acct_res.scalar_one_or_none()
            if not account_id:
                raise ValueError(f"Account code not found: {ld['account_code']}")

        if not account_id:
            raise ValueError(f"Line {idx}: Missing account_id or account_code.")

        processed_lines.append(
            JournalLine(
                line_number=idx,
                account_id=account_id,
                entity_id=ld.get("entity_id"),
                description=ld.get("description", ""),
                debit=debit,
                credit=credit,
            )
        )

    if total_debit != total_credit:
        raise ValueError(
            f"Double-entry equation violated: Total Debits (₹{total_debit}) != Total Credits (₹{total_credit})."
        )
    if total_debit <= Decimal("0.00"):
        raise ValueError("Total entry amount must be greater than zero.")

    # Generate entry number if not supplied
    entry_number = entry_data.get("entry_number")
    if not entry_number:
        count_stmt = select(func.count(JournalEntry.id))
        c_res = await session.execute(count_stmt)
        count = (c_res.scalar() or 0) + 1
        entry_number = f"JE-{entry_date.year}-{count:06d}"

    entry = JournalEntry(
        entry_number=entry_number,
        entry_date=entry_date,
        entry_type=entry_data.get("entry_type", "GENERAL_JOURNAL"),
        status=entry_data.get("status", "POSTED"),
        narration=entry_data.get("narration", ""),
        source_document_ref=entry_data.get("source_document_ref"),
        fiscal_year_id=entry_data.get("fiscal_year_id"),
        total_debit=total_debit,
        total_credit=total_credit,
        posted_by=entry_data.get("posted_by", "system"),
        posted_at=now_utc(),
        lines=processed_lines,
    )

    session.add(entry)
    await session.flush()
    return entry


# ============================================================================
# GENERAL LEDGER & RUNNING BALANCE
# ============================================================================
async def get_general_ledger(
    session: AsyncSession,
    account_code_or_id: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Calculate opening balance, chronological movements, running balance, and closing balance."""
    # Find account
    stmt = select(Account).where(
        or_(Account.id == account_code_or_id, Account.code == account_code_or_id)
    )
    res = await session.execute(stmt)
    account = res.scalar_one_or_none()
    if not account:
        raise ValueError(f"Account not found: {account_code_or_id}")

    # Determine normal balance sign: ASSET & EXPENSE are normally Debit (+). LIABILITY, EQUITY, REVENUE are Credit (+).
    is_debit_normal = account.account_type in ("ASSET", "EXPENSE")

    # Opening balance query: sum before from_date
    opening_balance = Decimal("0.00")
    if from_date:
        op_stmt = (
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0.00")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0.00")),
            )
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                and_(
                    JournalLine.account_id == account.id,
                    JournalEntry.status == "POSTED",
                    JournalEntry.entry_date < from_date,
                )
            )
        )
        op_res = await session.execute(op_stmt)
        past_debit, past_credit = op_res.first() or (Decimal("0.00"), Decimal("0.00"))
        if is_debit_normal:
            opening_balance = to_dec(past_debit) - to_dec(past_credit)
        else:
            opening_balance = to_dec(past_credit) - to_dec(past_debit)

    # Period movements query
    filters = [
        JournalLine.account_id == account.id,
        JournalEntry.status == "POSTED",
    ]
    if from_date:
        filters.append(JournalEntry.entry_date >= from_date)
    if to_date:
        filters.append(JournalEntry.entry_date <= to_date)

    mov_stmt = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(and_(*filters))
        .order_by(JournalEntry.entry_date.asc(), JournalEntry.posted_at.asc(), JournalLine.line_number.asc())
    )
    mov_res = await session.execute(mov_stmt)
    rows = mov_res.all()

    running_bal = opening_balance
    total_period_debit = Decimal("0.00")
    total_period_credit = Decimal("0.00")
    ledger_entries = []

    for line, entry in rows:
        d = to_dec(line.debit)
        c = to_dec(line.credit)
        total_period_debit += d
        total_period_credit += c

        if is_debit_normal:
            running_bal += d - c
        else:
            running_bal += c - d

        ledger_entries.append(
            {
                "line_id": line.id,
                "entry_id": entry.id,
                "entry_number": entry.entry_number,
                "entry_date": entry.entry_date.isoformat(),
                "entry_type": entry.entry_type,
                "narration": entry.narration,
                "line_description": line.description,
                "source_ref": entry.source_document_ref,
                "debit": float(d),
                "credit": float(c),
                "running_balance": float(running_bal),
            }
        )

    return {
        "account": {
            "id": account.id,
            "code": account.code,
            "name": account.name,
            "account_type": account.account_type,
            "sub_type": account.sub_type,
            "normal_balance": "DEBIT" if is_debit_normal else "CREDIT",
        },
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "opening_balance": float(opening_balance),
        "total_debit": float(total_period_debit),
        "total_credit": float(total_period_credit),
        "closing_balance": float(running_bal),
        "entries": ledger_entries,
    }


# ============================================================================
# TRIAL BALANCE
# ============================================================================
async def get_trial_balance(
    session: AsyncSession, as_of_date: Optional[date] = None
) -> Dict[str, Any]:
    """Compute mathematical trial balance proving total debit == total credit."""
    if not as_of_date:
        as_of_date = date.today()

    stmt = select(Account).where(Account.is_active == True).order_by(Account.code.asc())
    acct_res = await session.execute(stmt)
    accounts = acct_res.scalars().all()

    account_rows = []
    grand_total_debit = Decimal("0.00")
    grand_total_credit = Decimal("0.00")

    for acct in accounts:
        sum_stmt = (
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0.00")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0.00")),
            )
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                and_(
                    JournalLine.account_id == acct.id,
                    JournalEntry.status == "POSTED",
                    JournalEntry.entry_date <= as_of_date,
                )
            )
        )
        s_res = await session.execute(sum_stmt)
        tot_deb, tot_cred = s_res.first() or (Decimal("0.00"), Decimal("0.00"))
        tot_deb = to_dec(tot_deb)
        tot_cred = to_dec(tot_cred)

        if tot_deb == 0 and tot_cred == 0:
            continue

        net_diff = tot_deb - tot_cred
        if net_diff > 0:
            bal_debit = net_diff
            bal_credit = Decimal("0.00")
        else:
            bal_debit = Decimal("0.00")
            bal_credit = abs(net_diff)

        grand_total_debit += bal_debit
        grand_total_credit += bal_credit

        account_rows.append(
            {
                "account_id": acct.id,
                "code": acct.code,
                "name": acct.name,
                "account_type": acct.account_type,
                "sub_type": acct.sub_type,
                "total_debit": float(tot_deb),
                "total_credit": float(tot_cred),
                "balance_debit": float(bal_debit),
                "balance_credit": float(bal_credit),
            }
        )

    difference = grand_total_debit - grand_total_credit
    return {
        "as_of_date": as_of_date.isoformat(),
        "total_debit": float(grand_total_debit),
        "total_credit": float(grand_total_credit),
        "difference": float(difference),
        "is_balanced": grand_total_debit == grand_total_credit,
        "accounts": account_rows,
    }


# ============================================================================
# FINANCIAL ENTITY RESOLUTION HELPER
# ============================================================================
async def get_or_create_financial_entity(
    session: AsyncSession,
    name: str,
    entity_type: str = "CLIENT",
    external_ref_id: Optional[str] = None,
    gstin: Optional[str] = None,
    pan: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> FinancialEntity:
    """Find or auto-create a subledger financial entity (Client, Vendor, Worker, Bank, etc.)."""
    cleaned_name = (name or "").strip() or "General Partner"
    etype = entity_type.upper()

    if external_ref_id:
        stmt = select(FinancialEntity).where(FinancialEntity.external_ref_id == str(external_ref_id))
        entity = (await session.execute(stmt)).scalar_one_or_none()
        if entity:
            return entity

    stmt = select(FinancialEntity).where(
        and_(
            func.lower(FinancialEntity.name) == cleaned_name.lower(),
            FinancialEntity.entity_type == etype,
        )
    )
    entity = (await session.execute(stmt)).scalar_one_or_none()
    if entity:
        return entity

    gl_code_map = {
        "CLIENT": "1030",       # Accounts Receivable
        "VENDOR": "2010",       # Accounts Payable
        "WORKER": "2020",       # Karigar Wages Payable
        "BANK": "1010",         # Bank Accounts
        "CASH_REGISTER": "1020",# Cash in Hand
        "MARKETPLACE": "1030",  # Accounts Receivable
    }
    gl_code = gl_code_map.get(etype, "1030")
    gl_stmt = select(Account.id).where(Account.code == gl_code)
    gl_id = (await session.execute(gl_stmt)).scalar_one_or_none()
    if not gl_id:
        gl_id = (await session.execute(select(Account.id).where(Account.is_active == True))).scalars().first()

    clean_prefix = "".join(c for c in cleaned_name if c.isalnum())[:6].upper() or etype[:4]
    uid_suffix = gen_uuid()[:6].upper()
    code = f"{etype[:3]}-{clean_prefix}-{uid_suffix}"

    entity = FinancialEntity(
        entity_type=etype,
        external_ref_id=str(external_ref_id) if external_ref_id else None,
        code=code,
        name=cleaned_name,
        gstin=gstin,
        pan=pan,
        phone=phone,
        email=email,
        gl_account_id=gl_id,
        is_active=True,
    )
    session.add(entity)
    await session.flush()
    return entity


# ============================================================================
# B2B SALES INVOICE WITH BALANCED POSTING
# ============================================================================
async def post_sales_invoice_voucher(
    session: AsyncSession, invoice_data: Dict[str, Any]
) -> Tuple[SalesInvoice, JournalEntry]:
    """Create a B2B sales invoice and generate balanced journal entry."""
    invoice_no = invoice_data["invoice_no"]
    client_id = invoice_data.get("client_id")
    if not client_id:
        c_name = invoice_data.get("client_name") or invoice_data.get("customer_name") or "B2B Client"
        client_entity = await get_or_create_financial_entity(
            session,
            name=c_name,
            entity_type="CLIENT",
            external_ref_id=invoice_data.get("client_ref_id") or invoice_data.get("po_id"),
            gstin=invoice_data.get("customer_gstin"),
        )
        client_id = client_entity.id
    inv_date = invoice_data.get("invoice_date")
    if isinstance(inv_date, str):
        inv_date = datetime.strptime(inv_date, "%Y-%m-%d").date()
    elif not isinstance(inv_date, date):
        inv_date = date.today()

    due_date = invoice_data.get("due_date")
    if isinstance(due_date, str):
        due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
    elif not isinstance(due_date, date):
        due_date = inv_date

    subtotal = to_dec(invoice_data.get("subtotal", 0))
    cgst_rate = to_dec(invoice_data.get("cgst_rate", 0))
    cgst_amount = to_dec(invoice_data.get("cgst_amount", 0))
    sgst_rate = to_dec(invoice_data.get("sgst_rate", 0))
    sgst_amount = to_dec(invoice_data.get("sgst_amount", 0))
    igst_rate = to_dec(invoice_data.get("igst_rate", 0))
    igst_amount = to_dec(invoice_data.get("igst_amount", 0))
    tcs_amount = to_dec(invoice_data.get("tcs_amount", 0))
    grn_adjustment = to_dec(invoice_data.get("grn_adjustment", 0))

    grand_total = subtotal + cgst_amount + sgst_amount + igst_amount + tcs_amount
    net_receivable = grand_total - grn_adjustment

    # Look up Accounts Receivable GL account
    ar_acct_stmt = select(Account.id).where(Account.code == "1030")
    ar_acct_id = (await session.execute(ar_acct_stmt)).scalar_one_or_none()
    if not ar_acct_id:
        raise ValueError("Accounts Receivable account (code 1030) not found in chart of accounts.")

    # Look up Sales Revenue GL account
    rev_acct_stmt = select(Account.id).where(Account.code == "4010")
    rev_acct_id = (await session.execute(rev_acct_stmt)).scalar_one_or_none()
    if not rev_acct_id:
        raise ValueError("Sales Revenue account (code 4010) not found in chart of accounts.")

    lines = []
    # Debit: Accounts Receivable (Client Net Receivable)
    lines.append(
        {
            "account_id": ar_acct_id,
            "entity_id": client_id,
            "description": f"Invoice {invoice_no} net receivable",
            "debit": net_receivable,
            "credit": Decimal("0.00"),
        }
    )

    if grn_adjustment > 0:
        disc_stmt = select(Account.id).where(Account.code == "4030")
        disc_acct_id = (await session.execute(disc_stmt)).scalar_one_or_none() or rev_acct_id
        lines.append(
            {
                "account_id": disc_acct_id,
                "entity_id": client_id,
                "description": f"GRN adjustment deduction on {invoice_no}",
                "debit": grn_adjustment,
                "credit": Decimal("0.00"),
            }
        )

    # Credit: Revenue
    lines.append(
        {
            "account_id": rev_acct_id,
            "description": f"B2B Sales revenue for {invoice_no}",
            "debit": Decimal("0.00"),
            "credit": subtotal,
        }
    )

    # Credit Taxes
    if cgst_amount > 0:
        tax_id = (await session.execute(select(Account.id).where(Account.code == "2030-CGST-OUT"))).scalar_one_or_none()
        lines.append({"account_id": tax_id or rev_acct_id, "description": "CGST Output", "debit": Decimal("0.00"), "credit": cgst_amount})
    if sgst_amount > 0:
        tax_id = (await session.execute(select(Account.id).where(Account.code == "2030-SGST-OUT"))).scalar_one_or_none()
        lines.append({"account_id": tax_id or rev_acct_id, "description": "SGST Output", "debit": Decimal("0.00"), "credit": sgst_amount})
    if igst_amount > 0:
        tax_id = (await session.execute(select(Account.id).where(Account.code == "2030-IGST-OUT"))).scalar_one_or_none()
        lines.append({"account_id": tax_id or rev_acct_id, "description": "IGST Output", "debit": Decimal("0.00"), "credit": igst_amount})
    if tcs_amount > 0:
        tax_id = (await session.execute(select(Account.id).where(Account.code == "2050-TCS"))).scalar_one_or_none()
        lines.append({"account_id": tax_id or rev_acct_id, "description": "TCS Payable", "debit": Decimal("0.00"), "credit": tcs_amount})

    # Post balanced journal entry
    je = await post_journal_entry(
        session,
        {
            "entry_date": inv_date,
            "entry_type": "SALES_INVOICE",
            "narration": f"Sales Invoice {invoice_no} to client",
            "source_document_ref": invoice_no,
            "posted_by": invoice_data.get("posted_by", "system"),
        },
        lines,
    )

    sales_inv = SalesInvoice(
        invoice_no=invoice_no,
        invoice_date=inv_date,
        due_date=due_date,
        client_id=client_id,
        po_number=invoice_data.get("po_number"),
        customer_gstin=invoice_data.get("customer_gstin"),
        place_of_supply=invoice_data.get("place_of_supply"),
        subtotal=subtotal,
        cgst_rate=cgst_rate,
        cgst_amount=cgst_amount,
        sgst_rate=sgst_rate,
        sgst_amount=sgst_amount,
        igst_rate=igst_rate,
        igst_amount=igst_amount,
        tcs_amount=tcs_amount,
        grand_total=grand_total,
        grn_adjustment=grn_adjustment,
        net_receivable=net_receivable,
        paid_amount=Decimal("0.00"),
        status="POSTED",
        journal_entry_id=je.id,
        notes=invoice_data.get("notes"),
    )
    session.add(sales_inv)
    await session.flush()
    return sales_inv, je


# ============================================================================
# VENDOR BILL WITH BALANCED POSTING (ACCOUNTS PAYABLE)
# ============================================================================
async def post_vendor_bill_voucher(
    session: AsyncSession, bill_data: Dict[str, Any]
) -> Tuple[VendorBill, JournalEntry]:
    """Create a Vendor Bill and post balanced double-entry voucher to Accounts Payable."""
    bill_no = bill_data["bill_no"]
    vendor_id = bill_data.get("vendor_id")
    if not vendor_id:
        v_name = bill_data.get("vendor_name") or "Vendor Partner"
        vendor_entity = await get_or_create_financial_entity(
            session,
            name=v_name,
            entity_type="VENDOR",
            external_ref_id=bill_data.get("vendor_ref_id"),
        )
        vendor_id = vendor_entity.id
    bill_date = bill_data.get("bill_date")
    if isinstance(bill_date, str):
        bill_date = datetime.strptime(bill_date, "%Y-%m-%d").date()
    elif not isinstance(bill_date, date):
        bill_date = date.today()

    due_date = bill_data.get("due_date")
    if isinstance(due_date, str):
        due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
    elif not isinstance(due_date, date):
        due_date = bill_date

    subtotal = to_dec(bill_data.get("subtotal", 0))
    cgst_amount = to_dec(bill_data.get("cgst_amount", 0))
    sgst_amount = to_dec(bill_data.get("sgst_amount", 0))
    igst_amount = to_dec(bill_data.get("igst_amount", 0))
    total_amount = subtotal + cgst_amount + sgst_amount + igst_amount

    # Debit Raw Material Consumption (5010) or Inventory Asset (1040)
    rm_acct_id = (await session.execute(select(Account.id).where(Account.code == "5010"))).scalar_one_or_none()
    if not rm_acct_id:
        rm_acct_id = (await session.execute(select(Account.id).where(Account.code == "1040"))).scalar_one_or_none()
    if not rm_acct_id:
        raise ValueError("Raw Material Expense / Asset account not found.")

    # Credit Accounts Payable (2010)
    ap_acct_id = (await session.execute(select(Account.id).where(Account.code == "2010"))).scalar_one_or_none()
    if not ap_acct_id:
        raise ValueError("Accounts Payable account (code 2010) not found.")

    lines = []
    # Debit: RM Expense
    lines.append({
        "account_id": rm_acct_id,
        "entity_id": vendor_id,
        "description": f"Raw material purchase - Bill {bill_no}",
        "debit": subtotal,
        "credit": Decimal("0.00"),
    })

    # Debit: GST Input Tax Credit
    if cgst_amount > 0:
        itc_cgst = (await session.execute(select(Account.id).where(Account.code == "1060-CGST-IN"))).scalar_one_or_none()
        lines.append({"account_id": itc_cgst or rm_acct_id, "description": "CGST ITC", "debit": cgst_amount, "credit": Decimal("0.00")})
    if sgst_amount > 0:
        itc_sgst = (await session.execute(select(Account.id).where(Account.code == "1060-SGST-IN"))).scalar_one_or_none()
        lines.append({"account_id": itc_sgst or rm_acct_id, "description": "SGST ITC", "debit": sgst_amount, "credit": Decimal("0.00")})
    if igst_amount > 0:
        itc_igst = (await session.execute(select(Account.id).where(Account.code == "1060-IGST-IN"))).scalar_one_or_none()
        lines.append({"account_id": itc_igst or rm_acct_id, "description": "IGST ITC", "debit": igst_amount, "credit": Decimal("0.00")})

    # Credit: Accounts Payable (Vendor Total)
    lines.append({
        "account_id": ap_acct_id,
        "entity_id": vendor_id,
        "description": f"AP for Vendor Bill {bill_no}",
        "debit": Decimal("0.00"),
        "credit": total_amount,
    })

    je = await post_journal_entry(
        session,
        {
            "entry_date": bill_date,
            "entry_type": "PURCHASE_BILL",
            "narration": f"Vendor Bill {bill_no}",
            "source_document_ref": bill_no,
            "posted_by": bill_data.get("posted_by", "system"),
        },
        lines,
    )

    bill = VendorBill(
        bill_no=bill_no,
        vendor_id=vendor_id,
        vendor_po_ref=bill_data.get("vendor_po_ref"),
        bill_date=bill_date,
        due_date=due_date,
        subtotal=subtotal,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        total_amount=total_amount,
        paid_amount=Decimal("0.00"),
        status="POSTED",
        journal_entry_id=je.id,
    )
    session.add(bill)
    await session.flush()
    return bill, je


# ============================================================================
# PAYMENT & RECEIPT VOUCHERS WITH ATOMIC ALLOCATIONS
# ============================================================================
async def post_payment_voucher(
    session: AsyncSession,
    voucher_data: Dict[str, Any],
    allocations: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[PaymentVoucher, JournalEntry]:
    """
    Post a receipt or payment voucher, create balanced journal entry, and apply allocations.
    """
    voucher_type = voucher_data.get("voucher_type", "RECEIPT").upper()  # RECEIPT or PAYMENT
    v_date = voucher_data.get("voucher_date")
    if isinstance(v_date, str):
        v_date = datetime.strptime(v_date, "%Y-%m-%d").date()
    elif not isinstance(v_date, date):
        v_date = date.today()

    amount = to_dec(voucher_data.get("amount", 0))
    if amount <= 0:
        raise ValueError("Voucher amount must be strictly greater than 0.")

    entity_id = voucher_data.get("entity_id")
    if not entity_id:
        p_name = voucher_data.get("entity_name") or voucher_data.get("party_name") or "Counterparty"
        etype = "CLIENT" if voucher_type == "RECEIPT" else "VENDOR"
        p_entity = await get_or_create_financial_entity(
            session,
            name=p_name,
            entity_type=etype,
            external_ref_id=voucher_data.get("external_ref_id"),
        )
        entity_id = p_entity.id

    bank_account_id = voucher_data.get("bank_account_id")
    cash_register_id = voucher_data.get("cash_register_id")

    # Determine Bank/Cash GL Account
    if bank_account_id:
        b_stmt = select(BankAccount).where(BankAccount.id == bank_account_id)
        b_res = await session.execute(b_stmt)
        b_acc = b_res.scalar_one_or_none()
        if b_acc:
            bank_gl_id = b_acc.gl_account_id
        else:
            bank_gl_id = (await session.execute(select(Account.id).where(Account.code == "1010"))).scalar_one_or_none()
    elif cash_register_id:
        c_stmt = select(CashRegister).where(CashRegister.id == cash_register_id)
        c_res = await session.execute(c_stmt)
        c_acc = c_res.scalar_one_or_none()
        if c_acc:
            bank_gl_id = c_acc.gl_account_id
        else:
            bank_gl_id = (await session.execute(select(Account.id).where(Account.code == "1020"))).scalar_one_or_none()
    else:
        pmode = str(voucher_data.get("payment_mode", "")).lower()
        target_code = "1020" if "cash" in pmode else "1010"
        bank_gl_id = (await session.execute(select(Account.id).where(Account.code == target_code))).scalar_one_or_none()
        if not bank_gl_id:
            bank_gl_id = (await session.execute(select(Account.id).where(Account.code == "1010"))).scalar_one_or_none()
            if not bank_gl_id:
                bank_gl_id = (await session.execute(select(Account.id).where(Account.is_active == True))).scalars().first()

    # Determine Sub-ledger partner GL account (e.g. 1030 for AR, 2010 for AP)
    if voucher_type == "RECEIPT":
        # Inflow: Debit Bank, Credit Accounts Receivable (1030)
        partner_acct_id = (await session.execute(select(Account.id).where(Account.code == "1030"))).scalar_one_or_none()
        lines = [
            {"account_id": bank_gl_id, "description": f"Receipt via {voucher_data.get('payment_mode', 'BANK')}", "debit": amount, "credit": Decimal("0.00")},
            {"account_id": partner_acct_id, "entity_id": entity_id, "description": f"Customer payment received", "debit": Decimal("0.00"), "credit": amount},
        ]
    else:
        # Outflow: Debit Accounts Payable (2010) or Wages (2020), Credit Bank
        partner_acct_id = (await session.execute(select(Account.id).where(Account.code == "2010"))).scalar_one_or_none()
        lines = [
            {"account_id": partner_acct_id, "entity_id": entity_id, "description": f"Vendor/Partner payment disbursed", "debit": amount, "credit": Decimal("0.00")},
            {"account_id": bank_gl_id, "description": f"Payment via {voucher_data.get('payment_mode', 'BANK')}", "debit": Decimal("0.00"), "credit": amount},
        ]

    # Generate voucher number
    voucher_no = voucher_data.get("voucher_no")
    if not voucher_no:
        prefix = "RCT" if voucher_type == "RECEIPT" else "PMT"
        c_stmt = select(func.count(PaymentVoucher.id)).where(PaymentVoucher.voucher_type == voucher_type)
        c_count = (await session.execute(c_stmt)).scalar() or 0
        voucher_no = f"{prefix}-{v_date.year}-{(c_count + 1):05d}"

    je = await post_journal_entry(
        session,
        {
            "entry_date": v_date,
            "entry_type": "CLIENT_RECEIPT" if voucher_type == "RECEIPT" else "VENDOR_PAYMENT",
            "narration": voucher_data.get("notes") or f"{voucher_type} Voucher {voucher_no}",
            "source_document_ref": voucher_data.get("reference_number") or voucher_no,
            "posted_by": voucher_data.get("posted_by", "system"),
        },
        lines,
    )

    voucher = PaymentVoucher(
        voucher_no=voucher_no,
        voucher_type=voucher_type,
        voucher_date=v_date,
        entity_id=entity_id,
        payment_mode=voucher_data.get("payment_mode", "BANK_TRANSFER"),
        bank_account_id=bank_account_id,
        cash_register_id=cash_register_id,
        amount=amount,
        reference_number=voucher_data.get("reference_number"),
        journal_entry_id=je.id,
        notes=voucher_data.get("notes"),
    )
    session.add(voucher)
    await session.flush()

    # Apply allocations if present
    if allocations:
        total_allocated = Decimal("0.00")
        for alloc in allocations:
            alloc_amt = to_dec(alloc.get("allocated_amount", 0))
            if alloc_amt <= 0:
                continue
            total_allocated += alloc_amt

            va = VoucherAllocation(
                voucher_id=voucher.id,
                sales_invoice_id=alloc.get("sales_invoice_id"),
                vendor_bill_id=alloc.get("vendor_bill_id"),
                allocated_amount=alloc_amt,
            )
            session.add(va)

            # Update Invoice or Bill paid amount
            if alloc.get("sales_invoice_id"):
                sinv = await session.get(SalesInvoice, alloc["sales_invoice_id"])
                if sinv:
                    sinv.paid_amount = to_dec(sinv.paid_amount) + alloc_amt
                    if sinv.paid_amount >= sinv.net_receivable:
                        sinv.status = "PAID"
                    else:
                        sinv.status = "PARTIALLY_PAID"

            elif alloc.get("vendor_bill_id"):
                vbill = await session.get(VendorBill, alloc["vendor_bill_id"])
                if vbill:
                    vbill.paid_amount = to_dec(vbill.paid_amount) + alloc_amt
                    if vbill.paid_amount >= vbill.total_amount:
                        vbill.status = "PAID"
                    else:
                        vbill.status = "PARTIALLY_PAID"

        if total_allocated > amount:
            raise ValueError(
                f"Total allocated amount (₹{total_allocated}) exceeds voucher amount (₹{amount})."
            )

    await session.flush()
    return voucher, je


# ============================================================================
# BANK STATEMENT ATOMIC RECONCILIATION
# ============================================================================
async def reconcile_bank_statement_line(
    session: AsyncSession,
    stmt_line_id: str,
    voucher_id: Optional[str] = None,
    journal_line_id: Optional[str] = None,
    matched_by: str = "system",
    remarks: Optional[str] = None,
) -> BankStatementLine:
    """Atomic match of bank statement line updating cleared balance and row state."""
    stmt = (
        select(BankStatementLine)
        .options(selectinload(BankStatementLine.bank_account))
        .where(BankStatementLine.id == stmt_line_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    line = res.scalar_one_or_none()
    if not line:
        raise ValueError(f"Bank statement line {stmt_line_id} not found.")

    if line.match_status == "MATCHED":
        raise ValueError("Bank statement line is already matched and reconciled.")

    bank_acc = line.bank_account
    if not bank_acc:
        raise ValueError("Associated bank account not found.")

    line.match_status = "MATCHED"
    line.matched_voucher_id = voucher_id
    line.matched_journal_line_id = journal_line_id
    line.reconciled_by = matched_by
    line.reconciled_at = now_utc()
    if remarks:
        line.remarks = remarks

    # Update cleared balance
    net_line_effect = to_dec(line.credit_amount) - to_dec(line.debit_amount)
    bank_acc.current_cleared_balance = to_dec(bank_acc.current_cleared_balance) + net_line_effect

    if journal_line_id:
        jl = await session.get(JournalLine, journal_line_id)
        if jl:
            jl.reconciliation_status = "RECONCILED"
            jl.reconciled_at = now_utc()

    await session.flush()
    return line


# ============================================================================
# BANK RECONCILIATION STATEMENT (BRS) SUMMARY
# ============================================================================
async def get_bank_reconciliation_summary(
    session: AsyncSession, bank_account_id: str, as_of_date: date
) -> Dict[str, Any]:
    """Calculate Bank Reconciliation Statement (BRS) comparing bank vs ledger book balance."""
    b_stmt = select(BankAccount).where(BankAccount.id == bank_account_id)
    b_res = await session.execute(b_stmt)
    bank_acc = b_res.scalar_one_or_none()
    if not bank_acc:
        raise ValueError("Bank account not found.")

    # Ledger Book balance as of date
    ledger_data = await get_general_ledger(session, bank_acc.gl_account_id, to_date=as_of_date)
    book_balance = to_dec(ledger_data["closing_balance"])

    # Cleared statement balance up to as_of_date
    cleared_stmt = (
        select(
            func.coalesce(func.sum(BankStatementLine.credit_amount), Decimal("0.00")),
            func.coalesce(func.sum(BankStatementLine.debit_amount), Decimal("0.00")),
        )
        .where(
            and_(
                BankStatementLine.bank_account_id == bank_account_id,
                BankStatementLine.transaction_date <= as_of_date,
                BankStatementLine.match_status == "MATCHED",
            )
        )
    )
    c_res = await session.execute(cleared_stmt)
    cl_credits, cl_debits = c_res.first() or (Decimal("0.00"), Decimal("0.00"))
    statement_cleared_balance = to_dec(bank_acc.opening_balance) + to_dec(cl_credits) - to_dec(cl_debits)

    # Unpresented payments: vouchers issued but not matched in bank statement
    # Uncredited receipts: receipts entered but not cleared
    diff = statement_cleared_balance - book_balance

    return {
        "bank_account_id": bank_acc.id,
        "bank_name": bank_acc.bank_name,
        "account_number": bank_acc.account_number,
        "as_of_date": as_of_date.isoformat(),
        "statement_balance": float(statement_cleared_balance),
        "book_balance": float(book_balance),
        "difference": float(diff),
        "is_balanced": diff == Decimal("0.00"),
    }
