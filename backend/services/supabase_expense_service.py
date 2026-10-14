"""Supabase Expense Ledger & Operating Cost Synchronization Service.

Handles persistence of Factory Petty Cash / Bank Expenses into Supabase:
- public.chart_of_accounts (Operating, Factory Overhead & Admin Expenses)
- public.journal_entries & public.journal_lines (Double-Entry Core)
- public.payment_vouchers (Cash/Bank Outflow)
- public.cash_registers / public.bank_accounts
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from db.supabase_client import get_supabase_admin_client
from services.supabase_invoice_service import to_uuid, _get_coa_map

log = logging.getLogger(__name__)

DEFAULT_CASH_REGISTER_UUID = str(uuid.uuid5(uuid.NAMESPACE_OID, "FACTORY_PETTY_CASH_REGISTER"))

# Map MongoDB Expense Category to Standard Indian Footwear Chart of Accounts GL Code
CATEGORY_GL_MAP = {
    "wages": "5020",                         # Direct Karigar Labor & Wages
    "Rent & Utilities": "5030",              # Factory Rent & Electricity
    "Raw Materials": "5010",                 # Raw Material Consumption (COGS)
    "Machinery & Maintenance": "5030",       # Factory Overhead
    "Transport & Logistics": "5040",         # Outward Freight & Shipping
    "Packaging & Printing": "5030",          # Factory Overhead / Packaging
    "Office & Administrative": "5060",       # Administrative & Office Expenses
    "Marketing & Sales": "5050",             # Marketplace Commission / Selling & Distribution
    "Tax & Professional Fees": "5060",       # Administrative / Professional Fees
    "Other Expenses": "5060",                # Administrative & Office Expenses
}


def ensure_cash_register(client, coa_map: Dict[str, str]) -> Optional[str]:
    """Ensure default factory petty cash register exists in public.cash_registers."""
    gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020")
    if not gl_cash:
        log.warning("GL Account for Cash (1020) not found in chart_of_accounts.")
        return None

    row = {
        "id": DEFAULT_CASH_REGISTER_UUID,
        "name": "Factory Petty Cash",
        "gl_account_id": gl_cash,
        "opening_balance": 0.0,
        "current_balance": 0.0,
        "is_active": True,
    }
    try:
        client.table("cash_registers").upsert(row, on_conflict="id").execute()
        return DEFAULT_CASH_REGISTER_UUID
    except Exception as e:
        log.error("Failed to ensure default cash register in Supabase: %s", e)
        return None


def sync_expense_to_supabase(expense_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Persist an Expense voucher into Supabase:
    1. Debit Expense GL (5010..5070), Credit Bank (1010) or Cash (1020).
    2. Creates public.journal_entries record (total_debit == total_credit).
    3. Creates public.journal_lines.
    4. Creates public.payment_vouchers record (voucher_type='PAYMENT').
    """
    client = get_supabase_admin_client()
    if not client:
        log.warning("Supabase admin client unavailable; skipping expense sync.")
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            log.warning("No chart of accounts found in Supabase.")
            return None

        amount = round(float(expense_doc.get("amount") or 0.0), 2)
        if amount <= 0:
            log.warning("Expense amount %s <= 0; skipping Supabase sync.", amount)
            return None

        # Resolve Debit (Expense) GL
        cat = (expense_doc.get("category") or "Other Expenses").strip()
        gl_code = CATEGORY_GL_MAP.get(cat, "5060")
        gl_expense = coa_map.get(gl_code) or coa_map.get("5060") or coa_map.get("5030")

        # Resolve Credit (Cash / Bank) GL
        paid_via = (expense_doc.get("paid_via") or "bank").lower()
        is_cash = paid_via == "cash"
        gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020")
        gl_bank = coa_map.get("1010")
        credit_gl = gl_cash if is_cash else gl_bank
        if not credit_gl:
            credit_gl = gl_cash or gl_bank

        if not gl_expense or not credit_gl:
            log.error("Required GL accounts missing for expense %s (category: %s)", expense_doc.get("_id"), cat)
            return None

        exp_raw_id = str(expense_doc.get("_id") or expense_doc.get("id") or uuid.uuid4())
        exp_uuid = to_uuid(exp_raw_id)
        exp_date = str(expense_doc.get("date") or datetime.now(timezone.utc).date().isoformat())[:10]
        payee = expense_doc.get("payee") or "Payee"

        # 1. Journal Entry
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_EXP_{exp_uuid}"))
        narration = f"Expense: {cat} - {payee}"
        if expense_doc.get("notes"):
            narration += f" ({expense_doc.get('notes')})"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-EXP-{exp_uuid[:8].upper()}",
            "entry_date": exp_date,
            "entry_type": "EXPENSE",
            "status": "POSTED",
            "narration": narration[:255],
            "source_document_ref": f"EXP-{exp_uuid[:8].upper()}",
            "total_debit": amount,
            "total_credit": amount,
            "posted_by": expense_doc.get("created_by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # 2. Journal Lines
        lines = [
            # Line 1: Debit Operating / Overhead Expense
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr")),
                "journal_entry_id": je_id,
                "account_id": gl_expense,
                "line_number": 1,
                "description": f"{cat} - {payee}",
                "debit": amount,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            },
            # Line 2: Credit Bank / Cash
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr")),
                "journal_entry_id": je_id,
                "account_id": credit_gl,
                "line_number": 2,
                "description": f"Paid via {paid_via.upper()}",
                "debit": 0.0,
                "credit": amount,
                "reconciliation_status": "UNRECONCILED" if not is_cash else "RECONCILED",
            }
        ]
        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        # 3. Payment Voucher
        voucher_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"VCH_EXP_{exp_uuid}"))
        bank_acc_uuid = to_uuid(expense_doc.get("bank_account_id")) if (expense_doc.get("bank_account_id") and not is_cash) else None
        cash_reg_uuid = ensure_cash_register(client, coa_map) if is_cash else None

        voucher_row = {
            "id": voucher_id,
            "voucher_no": f"VCH-EXP-{exp_uuid[:8].upper()}",
            "voucher_type": "PAYMENT",
            "voucher_date": exp_date,
            "payment_mode": "CASH" if is_cash else "BANK_TRANSFER",
            "bank_account_id": bank_acc_uuid,
            "cash_register_id": cash_reg_uuid,
            "amount": amount,
            "reference_number": str(expense_doc.get("receipt") or "")[:100],
            "journal_entry_id": je_id,
            "notes": narration[:255],
        }

        # Resolve entity_id if payee matches a known financial entity, else use default entity
        try:
            fe_res = client.table("financial_entities").select("id").limit(1).execute()
            if fe_res and fe_res.data:
                voucher_row["entity_id"] = fe_res.data[0]["id"]
        except Exception:
            pass

        if "entity_id" in voucher_row:
            res_vch = client.table("payment_vouchers").upsert(voucher_row, on_conflict="id").execute()
            data = getattr(res_vch, "data", None)
            if data and len(data) > 0:
                log.info("Persisted expense payment voucher %s to Supabase", voucher_id)
                return data[0]

        log.info("Persisted expense journal entry %s to Supabase", je_id)
        return je_row

    except Exception as e:
        log.error("Failed to sync expense to Supabase: %s", e)
        return None


def void_expense_in_supabase(expense_id_or_doc: Any, voided_by: str = "system", reason: str = "Expense deleted/voided") -> bool:
    """
    Void an expense in Supabase:
    Marks linked journal entry status = 'VOIDED' and records void audit fields.
    """
    client = get_supabase_admin_client()
    if not client:
        return False

    try:
        raw_id = expense_id_or_doc.get("_id") if isinstance(expense_id_or_doc, dict) else expense_id_or_doc
        exp_uuid = to_uuid(raw_id)
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_EXP_{exp_uuid}"))
        now_ts = datetime.now(timezone.utc).isoformat()

        # Update journal entry to VOIDED
        client.table("journal_entries").update({
            "status": "VOIDED",
            "voided_at": now_ts,
            "voided_by": str(voided_by)[:100],
            "void_reason": str(reason)[:255]
        }).eq("id", je_id).execute()

        log.info("Voided expense journal entry %s in Supabase.", je_id)
        return True
    except Exception as e:
        log.error("Failed to void expense in Supabase: %s", e)
        return False
