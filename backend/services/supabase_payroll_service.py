"""Supabase Payroll & Karigar Wage Disbursement Service.

Synchronizes wage disbursements recorded in MongoDB to Supabase Relational Financial Core:
- public.financial_entities (Workers / Karigars)
- public.cash_registers / public.bank_accounts
- public.journal_entries & public.journal_lines (Double-Entry General Ledger)
- public.payment_vouchers
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from db.supabase_client import get_supabase_admin_client

log = logging.getLogger(__name__)

DEFAULT_CASH_REGISTER_UUID = str(uuid.uuid5(uuid.NAMESPACE_OID, "FACTORY_PETTY_CASH_REGISTER"))


def to_uuid(val: Any) -> str:
    """Convert an ObjectId or string to a deterministic, valid UUID."""
    if not val:
        return str(uuid.uuid4())
    s = str(val).strip()
    try:
        return str(uuid.UUID(s))
    except (ValueError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_OID, s))


def _get_coa_map(client) -> Dict[str, str]:
    """Retrieve mapping of chart_of_accounts code -> UUID."""
    try:
        res = client.table("chart_of_accounts").select("id, code").execute()
        return {row["code"]: row["id"] for row in (res.data or [])}
    except Exception as e:
        log.error("Failed to query chart_of_accounts from Supabase: %s", e)
        return {}


def ensure_cash_register(client, coa_map: Dict[str, str]) -> Optional[str]:
    """Ensure at least one factory petty cash register exists in public.cash_registers."""
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


def ensure_worker_entity(
    client,
    worker_id_str: str,
    worker_doc: Dict[str, Any],
    coa_map: Dict[str, str]
) -> Optional[str]:
    """Ensure Karigar / Worker exists in public.financial_entities."""
    worker_uuid = to_uuid(worker_id_str)
    gl_wages = coa_map.get("2020") or coa_map.get("5020")
    if not gl_wages:
        log.warning("GL Account 2020/5020 not found in chart_of_accounts.")
        return None

    name = (worker_doc.get("name") or "Karigar").strip()
    code = (worker_doc.get("worker_code") or f"WRK-{str(worker_id_str)[-6:]}").strip()

    row = {
        "id": worker_uuid,
        "entity_type": "WORKER",
        "external_ref_id": str(worker_id_str),
        "code": code,
        "name": name,
        "phone": worker_doc.get("phone") or "",
        "gl_account_id": gl_wages,
        "is_active": bool(worker_doc.get("active", True)),
    }
    try:
        client.table("financial_entities").upsert(row, on_conflict="id").execute()
        return worker_uuid
    except Exception as e:
        log.error("Failed to upsert worker entity %s in Supabase: %s", worker_uuid, e)
        return None


def sync_wage_payment_to_supabase(
    payment_doc: Dict[str, Any],
    worker_doc: Optional[Dict[str, Any]] = None,
    bank_acc_doc: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Persist a worker wage payout to Supabase:
    1. Ensures Worker exists in public.financial_entities.
    2. Ensures Bank or Cash register exists.
    3. Creates balanced public.journal_entries record.
    4. Creates debit (Direct Labor 5020) & credit (Cash 1020 or Bank 1010) public.journal_lines.
    5. Creates public.payment_vouchers record.
    """
    client = get_supabase_admin_client()
    if not client:
        log.warning("Supabase admin client unavailable; skipping wage payment sync.")
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            log.warning("No accounts found in Supabase chart_of_accounts.")
            return None

        gl_labor_exp = coa_map.get("5020")   # Direct Karigar Labor & Wages
        gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020") # Cash
        gl_bank = coa_map.get("1010")        # Bank Accounts

        if not gl_labor_exp:
            log.error("Required GL Account 5020 (Direct Karigar Labor & Wages) missing from Supabase.")
            return None

        # 1. Ensure Worker entity
        worker_raw_id = payment_doc.get("worker_id") or ""
        worker_info = worker_doc or {}
        worker_uuid = ensure_worker_entity(client, str(worker_raw_id), worker_info, coa_map)
        if not worker_uuid:
            log.error("Could not create/find worker entity for worker_id %s", worker_raw_id)
            return None

        # 2. Identify destination (Cash register vs Bank account)
        paid_via = (payment_doc.get("paid_via") or "cash").lower()
        amount = round(float(payment_doc.get("amount") or 0.0), 2)
        if amount <= 0:
            log.warning("Payment amount %s <= 0; skipping Supabase journal entry.", amount)
            return None

        raw_payment_id = str(payment_doc.get("_id") or payment_doc.get("id") or uuid.uuid4())
        payment_uuid = to_uuid(raw_payment_id)
        raw_date = str(payment_doc.get("date") or datetime.now(timezone.utc).date().isoformat())[:10]
        worker_name = payment_doc.get("worker_name") or worker_info.get("name") or "Karigar"

        cash_register_uuid = None
        bank_account_uuid = None
        credit_gl = gl_cash

        if paid_via in ("bank_transfer", "upi"):
            credit_gl = gl_bank or gl_cash
            raw_bank_id = payment_doc.get("bank_account_id")
            if raw_bank_id:
                bank_account_uuid = to_uuid(raw_bank_id)
                # If bank_acc_doc is provided, upsert into bank_accounts
                if bank_acc_doc:
                    try:
                        from services.supabase_banking_service import upsert_supabase_bank_account
                        upsert_supabase_bank_account(bank_acc_doc)
                    except Exception as be:
                        log.debug("Could not upsert bank account: %s", be)
        else:
            cash_register_uuid = ensure_cash_register(client, coa_map)

        # 3. Create Balanced Journal Entry (chk_balanced_entry: total_debit = total_credit)
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_WAGE_{payment_uuid}"))
        period_str = ""
        if payment_doc.get("period_from") and payment_doc.get("period_to"):
            period_str = f" ({payment_doc.get('period_from')} to {payment_doc.get('period_to')})"
        narration = f"Wage disbursement to {worker_name}{period_str}"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-WAGE-{payment_uuid[:8].upper()}",
            "entry_date": raw_date,
            "entry_type": "PAYROLL",
            "status": "POSTED",
            "narration": narration,
            "source_document_ref": f"WAGE-{payment_uuid[:8].upper()}",
            "total_debit": amount,
            "total_credit": amount,
            "posted_by": payment_doc.get("created_by") or payment_doc.get("paid_by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # 4. Insert Balanced Journal Lines
        lines = [
            # Line 1: Debit Direct Karigar Labor Expense
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_1")),
                "journal_entry_id": je_id,
                "account_id": gl_labor_exp,
                "entity_id": worker_uuid,
                "line_number": 1,
                "description": f"Labor expense for {worker_name}",
                "debit": amount,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            },
            # Line 2: Credit Cash or Bank Account
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_2")),
                "journal_entry_id": je_id,
                "account_id": credit_gl,
                "entity_id": worker_uuid,
                "line_number": 2,
                "description": f"Paid via {paid_via.upper()}",
                "debit": 0.0,
                "credit": amount,
                "reconciliation_status": "UNRECONCILED" if paid_via in ("bank_transfer", "upi") else "RECONCILED",
            },
        ]
        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        # 5. Insert Payment Voucher
        voucher_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"VCH_WAGE_{payment_uuid}"))
        voucher_mode = "BANK_TRANSFER" if paid_via == "bank_transfer" else ("UPI" if paid_via == "upi" else "CASH")
        voucher_row = {
            "id": voucher_id,
            "voucher_no": f"VCH-WAGE-{payment_uuid[:8].upper()}",
            "voucher_type": "PAYMENT",
            "voucher_date": raw_date,
            "entity_id": worker_uuid,
            "payment_mode": voucher_mode,
            "bank_account_id": bank_account_uuid,
            "cash_register_id": cash_register_uuid,
            "amount": amount,
            "reference_number": payment_doc.get("upi_reference") or payment_doc.get("notes") or "",
            "journal_entry_id": je_id,
            "notes": narration,
        }
        res_vch = client.table("payment_vouchers").upsert(voucher_row, on_conflict="id").execute()
        log.info("Successfully persisted Karigar wage payment %s to Supabase financial ledger.", payment_uuid)
        return res_vch.data[0] if (res_vch and getattr(res_vch, "data", None)) else voucher_row

    except Exception as e:
        log.error("Failed to sync wage payment %s to Supabase: %s", payment_doc.get("_id"), e)
        return None
