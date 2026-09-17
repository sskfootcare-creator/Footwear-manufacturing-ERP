"""Supabase Banking & Reconciliation Service."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from db.supabase_client import get_supabase_admin_client

log = logging.getLogger(__name__)

DEFAULT_ENTITY_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_GL_ACCOUNT_ID = "f5f05fa5-f16c-487c-88c6-ad56108be0ea"


def to_uuid(val: Any) -> str:
    """Convert an ObjectId or arbitrary ID to a deterministic, valid UUID string."""
    if not val:
        return str(uuid.uuid4())
    s = str(val).strip()
    try:
        # Check if already a valid UUID
        return str(uuid.UUID(s))
    except (ValueError, AttributeError):
        # Generate stable UUIDv5 from MongoDB ObjectId or custom string
        return str(uuid.uuid5(uuid.NAMESPACE_OID, s))


def upsert_supabase_bank_account(account_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Synchronize / persist a bank account to public.bank_accounts in Supabase.
    """
    client = get_supabase_admin_client()
    if not client:
        return None

    raw_id = account_data.get("id") or account_data.get("_id")
    acc_id = to_uuid(raw_id)
    raw_acc_num = str(account_data.get("account_number", "")).strip() or "0000000000"
    last4 = account_data.get("account_number_last4") or (raw_acc_num[-4:] if len(raw_acc_num) >= 4 else raw_acc_num)

    row = {
        "id": acc_id,
        "entity_id": account_data.get("entity_id") or DEFAULT_ENTITY_ID,
        "gl_account_id": account_data.get("gl_account_id") or DEFAULT_GL_ACCOUNT_ID,
        "account_name": account_data.get("account_name") or account_data.get("name") or "Bank Account",
        "bank_name": account_data.get("bank_name") or "Primary Bank",
        "account_number": raw_acc_num,
        "account_number_last4": last4,
        "ifsc": account_data.get("ifsc") or "SBIN0001234",
        "branch": account_data.get("branch") or "",
        "category": account_data.get("category") or "operating",
        "opening_balance": float(account_data.get("opening_balance") or 0.0),
        "opening_balance_date": str(account_data.get("opening_balance_date") or datetime.now(timezone.utc).date().isoformat())[:10],
        "current_cleared_balance": float(account_data.get("current_cleared_balance") or account_data.get("current_balance") or 0.0),
        "is_active": bool(account_data.get("is_active", True)),
    }

    try:
        res = client.table("bank_accounts").upsert(row, on_conflict="id").execute()
        data = getattr(res, "data", None)
        if data and len(data) > 0:
            log.info("Persisted bank account %s to Supabase public.bank_accounts", acc_id)
            return data[0]
        return row
    except Exception as e:
        log.error("Failed to upsert bank account %s to Supabase: %s", acc_id, e)
        return None


def insert_supabase_statement_lines(lines: List[Dict[str, Any]], bank_account_id: str) -> List[Dict[str, Any]]:
    """
    Persist statement lines to public.bank_statement_lines in Supabase.
    """
    client = get_supabase_admin_client()
    if not client or not lines:
        return []

    acc_uuid = to_uuid(bank_account_id)
    rows = []

    for line in lines:
        line_id = to_uuid(line.get("id") or line.get("_id"))
        raw_date = str(line.get("line_date") or line.get("date") or datetime.now(timezone.utc).date().isoformat())[:10]

        rows.append({
            "id": line_id,
            "bank_account_id": acc_uuid,
            "transaction_date": raw_date,
            "value_date": str(line.get("value_date") or raw_date)[:10],
            "narration": line.get("description") or line.get("narration") or "Bank Transaction",
            "cheque_reference_no": line.get("reference_number") or line.get("cheque_number") or line.get("ref_no") or "",
            "debit_amount": float(line.get("debit_amount") or line.get("debit") or line.get("withdrawal") or 0.0),
            "credit_amount": float(line.get("credit_amount") or line.get("credit") or line.get("deposit") or 0.0),
            "running_balance": float(line.get("running_balance") or line.get("balance") or 0.0),
            "match_status": line.get("match_status") or line.get("reconciliation_status") or ("matched" if line.get("matched") else "unmatched"),
            "imported_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        res = client.table("bank_statement_lines").upsert(rows, on_conflict="id").execute()
        saved = getattr(res, "data", [])
        log.info("Persisted %d statement lines to Supabase public.bank_statement_lines", len(saved or rows))
        return saved or rows
    except Exception as e:
        log.error("Failed to insert statement lines to Supabase: %s", e)
        return []


def save_supabase_reconciliation_statement(recon_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Persist finalized reconciliation report/snapshot to public.bank_reconciliation_statements in Supabase.
    """
    client = get_supabase_admin_client()
    if not client:
        return None

    acc_id = to_uuid(recon_data.get("bank_account_id"))
    as_of = str(recon_data.get("as_of_date") or recon_data.get("period_end_date") or datetime.now(timezone.utc).date().isoformat())[:10]

    raw_id = recon_data.get("id") or recon_data.get("_id")
    recon_id = to_uuid(raw_id) if raw_id else str(uuid.uuid5(uuid.NAMESPACE_OID, f"{acc_id}_{as_of}"))

    stmt_bal = float(recon_data.get("bank_statement_balance") or recon_data.get("statement_closing_balance") or 0.0)
    book_bal = float(recon_data.get("book_balance") or recon_data.get("gl_closing_balance") or recon_data.get("reconciled_balance") or 0.0)
    diff = float(recon_data.get("reconciled_difference") or recon_data.get("unreconciled_difference") or abs(stmt_bal - book_bal))
    is_bal = recon_data.get("is_balanced") if "is_balanced" in recon_data else (abs(stmt_bal - book_bal) < 0.01)

    row = {
        "id": recon_id,
        "bank_account_id": acc_id,
        "as_of_date": as_of,
        "bank_statement_balance": stmt_bal,
        "book_balance": book_bal,
        "unpresented_cheques_total": float(recon_data.get("unpresented_cheques_total") or 0.0),
        "uncredited_deposits_total": float(recon_data.get("uncredited_deposits_total") or 0.0),
        "unreconciled_bank_debits": float(recon_data.get("unreconciled_bank_debits") or 0.0),
        "unreconciled_bank_credits": float(recon_data.get("unreconciled_bank_credits") or 0.0),
        "reconciled_difference": diff,
        "is_balanced": bool(is_bal),
        "finalized_at": recon_data.get("finalized_at") or datetime.now(timezone.utc).isoformat(),
        "finalized_by": recon_data.get("finalized_by") or "system",
    }

    try:
        res = client.table("bank_reconciliation_statements").upsert(row, on_conflict="bank_account_id,as_of_date").execute()
        data = getattr(res, "data", None)
        ret = data[0] if (data and len(data) > 0) else row
        ret["status"] = "balanced" if ret.get("is_balanced") else "discrepancy"
        ret["unreconciled_difference"] = ret.get("reconciled_difference", 0.0)
        log.info("Saved reconciliation statement %s to Supabase", recon_id)
        return ret
    except Exception as e:
        log.error("Failed to save reconciliation statement to Supabase: %s", e)
        return None


def list_supabase_bank_accounts() -> List[Dict[str, Any]]:
    """Query bank accounts from Supabase."""
    client = get_supabase_admin_client()
    if not client:
        return []
    try:
        res = client.table("bank_accounts").select("*").execute()
        return getattr(res, "data", []) or []
    except Exception as e:
        log.error("Failed to list Supabase bank accounts: %s", e)
        return []
