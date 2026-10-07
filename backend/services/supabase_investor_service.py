"""Supabase Investor Ledger Mirror & Financial Core Synchronization Service.

Handles persistence of Investor Financial Entities, Investor Advances,
and double-entry General Ledger postings in Supabase:
- public.financial_entities (Investors, entity_type='INVESTOR')
- public.chart_of_accounts ('Investor Advances Payable', 'Investor Margin / Finance Cost')
- public.journal_entries & public.journal_lines (Double-Entry Core)
- public.payment_vouchers

Mirrors services/supabase_vendor_bill_service.py with fire-and-forget safety pattern.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from db.supabase_client import get_supabase_admin_client
from services.supabase_invoice_service import to_uuid, _get_coa_map

log = logging.getLogger(__name__)

DEFAULT_CASH_REGISTER_UUID = str(uuid.uuid5(uuid.NAMESPACE_OID, "FACTORY_PETTY_CASH_REGISTER"))


def ensure_investor_gl_accounts(client, coa_map: Dict[str, str]) -> Dict[str, str]:
    """
    Ensure GL accounts exist in public.chart_of_accounts:
    - "Investor Advances Payable" (liability, 2020)
    - "Investor Margin / Finance Cost" (expense, 5030)
    Checks chart_of_accounts first — avoids duplicate code or name collisions.
    """
    resolved = {
        "gl_advances_payable": None,
        "gl_margin_cost": None,
    }

    try:
        res = client.table("chart_of_accounts").select("id, code, name").execute()
        existing = res.data or []
    except Exception as e:
        log.error("Failed to query chart_of_accounts in Supabase: %s", e)
        return resolved

    by_code = {row["code"]: row for row in existing}
    by_name = {row["name"].strip().lower(): row for row in existing}

    # 1. Investor Advances Payable (Liability)
    adv_name = "Investor Advances Payable"
    adv_account = by_name.get(adv_name.lower())
    if not adv_account:
        code_to_use = "2020"
        if "2020" in by_code:
            # Code 2020 is occupied by another account name (e.g. Karigar Wages Payable)
            code_to_use = "2020-INV" if "2020-INV" not in by_code else "2025"

        row = {
            "code": code_to_use,
            "name": adv_name,
            "account_type": "LIABILITY",
            "sub_type": "INVESTOR_ADVANCE",
            "is_reconcilable": True,
        }
        try:
            ins = client.table("chart_of_accounts").insert(row).execute()
            if ins and ins.data:
                adv_account = ins.data[0]
                coa_map[code_to_use] = adv_account["id"]
        except Exception as e:
            log.warning("Could not insert GL Account '%s': %s", adv_name, e)
            adv_account = by_name.get(adv_name.lower()) or by_code.get(code_to_use)

    if adv_account:
        resolved["gl_advances_payable"] = adv_account["id"]

    # 2. Investor Margin / Finance Cost (Expense)
    margin_name = "Investor Margin / Finance Cost"
    margin_account = by_name.get(margin_name.lower())
    if not margin_account:
        code_to_use = "5030"
        if "5030" in by_code:
            # Code 5030 is occupied by another account name (e.g. Factory Rent & Electricity)
            code_to_use = "5030-INV" if "5030-INV" not in by_code else "5035"

        row = {
            "code": code_to_use,
            "name": margin_name,
            "account_type": "EXPENSE",
            "sub_type": "INVESTOR_FINANCE_COST",
            "is_reconcilable": False,
        }
        try:
            ins = client.table("chart_of_accounts").insert(row).execute()
            if ins and ins.data:
                margin_account = ins.data[0]
                coa_map[code_to_use] = margin_account["id"]
        except Exception as e:
            log.warning("Could not insert GL Account '%s': %s", margin_name, e)
            margin_account = by_name.get(margin_name.lower()) or by_code.get(code_to_use)

    if margin_account:
        resolved["gl_margin_cost"] = margin_account["id"]

    return resolved


def ensure_investor_entity(
    client,
    investor_data: Dict[str, Any],
    coa_map: Dict[str, str],
    gl_adv_payable: Optional[str] = None
) -> Optional[str]:
    """Ensure investor exists in public.financial_entities with entity_type='INVESTOR'."""
    investor_id_val = investor_data.get("id") or investor_data.get("_id") or investor_data.get("investor_id")
    name = (investor_data.get("name") or investor_data.get("investor_name") or "Investor").strip()
    if not investor_id_val:
        investor_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"INVESTOR_{name}"))
    else:
        investor_uuid = to_uuid(investor_id_val)

    code = (investor_data.get("code") or f"INV-{name[:4].upper()}-{investor_uuid[:4].upper()}").strip()

    row = {
        "id": investor_uuid,
        "entity_type": "INVESTOR",
        "external_ref_id": str(investor_id_val or investor_uuid),
        "code": code,
        "name": name,
        "phone": investor_data.get("phone") or investor_data.get("contact") or "",
        "email": investor_data.get("email") or "",
        "billing_address": str(investor_data.get("billing_address") or investor_data.get("address") or ""),
        "gl_account_id": gl_adv_payable,
        "is_active": True,
    }

    try:
        client.table("financial_entities").upsert(row, on_conflict="id").execute()
        return investor_uuid
    except Exception as e:
        log.error("Failed to upsert investor entity %s in Supabase: %s", investor_uuid, e)
        return None


def sync_investor_advance_to_supabase(
    advance_doc: Dict[str, Any],
    investor_doc: Optional[Dict[str, Any]] = None,
    payment_mode: str = "BANK_TRANSFER",
    bank_account_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Sync Investor Advance receipt to Supabase:
    Debit Bank/Cash, Credit Investor Advances Payable.
    """
    client = get_supabase_admin_client()
    if not client:
        log.warning("Supabase admin client unavailable; skipping investor advance sync.")
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            log.warning("No chart of accounts found in Supabase.")
            return None

        gl_accs = ensure_investor_gl_accounts(client, coa_map)
        gl_adv_payable = gl_accs.get("gl_advances_payable") or coa_map.get("2020-INV") or coa_map.get("2020")
        gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020")
        gl_bank = coa_map.get("1010")

        if not gl_adv_payable:
            log.error("Investor Advances Payable GL account not found in Supabase.")
            return None

        amount = round(float(advance_doc.get("amount") or 0.0), 2)
        if amount <= 0:
            return None

        is_cash = payment_mode.upper() == "CASH"
        debit_gl = gl_cash if is_cash else gl_bank
        if not debit_gl:
            debit_gl = gl_cash or gl_bank

        # 1. Ensure Investor entity
        inv_data = investor_doc or {}
        if not inv_data and advance_doc.get("investor_id"):
            inv_data = {
                "id": advance_doc.get("investor_id"),
                "name": advance_doc.get("investor_name") or "Investor"
            }
        investor_uuid = ensure_investor_entity(client, inv_data, coa_map, gl_adv_payable=gl_adv_payable)

        adv_raw_id = str(advance_doc.get("_id") or advance_doc.get("id") or uuid.uuid4())
        adv_uuid = to_uuid(adv_raw_id)
        adv_date = str(advance_doc.get("advance_date") or datetime.now(timezone.utc).date().isoformat())[:10]
        po_number = advance_doc.get("po_number") or advance_doc.get("po_id") or "PO"

        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_INV_ADV_{adv_uuid}"))
        narration = f"Investor Advance from {inv_data.get('name', 'Investor')} for PO {po_number}"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-INV-ADV-{adv_uuid[:8].upper()}",
            "entry_date": adv_date,
            "entry_type": "RECEIPT",
            "status": "POSTED",
            "narration": narration,
            "source_document_ref": f"INV-ADV-{adv_uuid[:8]}",
            "total_debit": amount,
            "total_credit": amount,
            "posted_by": advance_doc.get("created_by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # Journal Lines: Debit Cash/Bank = Credit Investor Advances Payable
        lines = [
            # Line 1: Debit Cash/Bank
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr_bank")),
                "journal_entry_id": je_id,
                "account_id": debit_gl,
                "entity_id": investor_uuid,
                "line_number": 1,
                "description": f"Inflow via {payment_mode} from {inv_data.get('name', 'Investor')}",
                "debit": amount,
                "credit": 0.0,
                "reconciliation_status": "UNRECONCILED" if not is_cash else "RECONCILED",
            },
            # Line 2: Credit Investor Advances Payable
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr_payable")),
                "journal_entry_id": je_id,
                "account_id": gl_adv_payable,
                "entity_id": investor_uuid,
                "line_number": 2,
                "description": f"Investor Advance Payable for PO {po_number}",
                "debit": 0.0,
                "credit": amount,
                "reconciliation_status": "RECONCILED",
            }
        ]
        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        log.info("Successfully mirrored investor advance %s to Supabase journal entry %s", adv_raw_id, je_id)
        return je_row

    except Exception as e:
        log.error("Failed to sync investor advance to Supabase: %s", e)
        return None


def sync_investor_repayment_to_supabase(
    repayment_doc: Dict[str, Any],
    investor_doc: Optional[Dict[str, Any]] = None,
    is_reinvestment: bool = False,
    new_advance_doc: Optional[Dict[str, Any]] = None,
    payment_mode: str = "BANK_TRANSFER",
    bank_account_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Sync Investor Repayment / Reinvestment to Supabase.
    Handles TWO distinct cases explicitly:
      (a) Straight repayment (not reinvesting):
          Debit Investor Advances Payable (principal)
          Debit Investor Margin / Finance Cost (margin)
          Credit Bank/Cash for the full amount — real cash out.
      (b) Reinvestment:
          Margin is ALWAYS paid in cash first:
            Debit Investor Margin / Finance Cost (margin)
            Credit Bank/Cash for margin only.
          Principal is rolled forward as a non-cash entry:
            Debit Investor Advances Payable (old advance, closing it)
            Credit Investor Advances Payable (new advance, same amount, tagged to new PO)
            Zero net cash movement for principal leg.
    The caller must say explicitly via `is_reinvestment`.
    """
    client = get_supabase_admin_client()
    if not client:
        log.warning("Supabase admin client unavailable; skipping investor repayment sync.")
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            return None

        gl_accs = ensure_investor_gl_accounts(client, coa_map)
        gl_adv_payable = gl_accs.get("gl_advances_payable") or coa_map.get("2020-INV") or coa_map.get("2020")
        gl_margin_cost = gl_accs.get("gl_margin_cost") or coa_map.get("5030-INV") or coa_map.get("5030")
        gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020")
        gl_bank = coa_map.get("1010")

        if not gl_adv_payable or not gl_margin_cost:
            log.error("Core GL accounts for investor repayment missing in Supabase.")
            return None

        principal = round(float(repayment_doc.get("principal_amount") or 0.0), 2)
        margin = round(float(repayment_doc.get("margin_amount") or 0.0), 2)
        if principal <= 0 and margin <= 0:
            return None

        is_cash = payment_mode.upper() == "CASH"
        credit_gl = gl_cash if is_cash else gl_bank
        if not credit_gl:
            credit_gl = gl_cash or gl_bank

        # Ensure investor entity
        inv_data = investor_doc or {}
        if not inv_data and repayment_doc.get("investor_id"):
            inv_data = {
                "id": repayment_doc.get("investor_id"),
                "name": repayment_doc.get("investor_name") or "Investor"
            }
        investor_uuid = ensure_investor_entity(client, inv_data, coa_map, gl_adv_payable=gl_adv_payable)

        rep_raw_id = str(repayment_doc.get("_id") or repayment_doc.get("id") or uuid.uuid4())
        rep_uuid = to_uuid(rep_raw_id)
        payout_date = str(repayment_doc.get("payout_date") or datetime.now(timezone.utc).date().isoformat())[:10]

        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_INV_REP_{rep_uuid}"))
        inv_name = inv_data.get("name", "Investor")

        if not is_reinvestment:
            # ── CASE (a): STRAIGHT REPAYMENT ─────────────────────────────────────
            total_cash_out = round(principal + margin, 2)
            narration = f"Full Repayment to {inv_name} (Principal ₹{principal} + Margin ₹{margin})"

            je_row = {
                "id": je_id,
                "entry_number": f"JE-INV-REP-{rep_uuid[:8].upper()}",
                "entry_date": payout_date,
                "entry_type": "PAYMENT",
                "status": "POSTED",
                "narration": narration,
                "source_document_ref": f"INV-REP-{rep_uuid[:8]}",
                "total_debit": total_cash_out,
                "total_credit": total_cash_out,
                "posted_by": repayment_doc.get("created_by") or "system",
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
            client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

            lines = [
                # Line 1: Debit Investor Advances Payable (principal)
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr_principal")),
                    "journal_entry_id": je_id,
                    "account_id": gl_adv_payable,
                    "entity_id": investor_uuid,
                    "line_number": 1,
                    "description": f"Principal Repayment to {inv_name}",
                    "debit": principal,
                    "credit": 0.0,
                    "reconciliation_status": "RECONCILED",
                },
                # Line 2: Debit Investor Margin / Finance Cost (margin)
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr_margin")),
                    "journal_entry_id": je_id,
                    "account_id": gl_margin_cost,
                    "entity_id": investor_uuid,
                    "line_number": 2,
                    "description": f"Negotiated Margin / Finance Cost paid to {inv_name}",
                    "debit": margin,
                    "credit": 0.0,
                    "reconciliation_status": "RECONCILED",
                },
                # Line 3: Credit Bank/Cash (full cash payout)
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr_bank")),
                    "journal_entry_id": je_id,
                    "account_id": credit_gl,
                    "entity_id": investor_uuid,
                    "line_number": 3,
                    "description": f"Paid full settlement via {payment_mode}",
                    "debit": 0.0,
                    "credit": total_cash_out,
                    "reconciliation_status": "UNRECONCILED" if not is_cash else "RECONCILED",
                }
            ]
            client.table("journal_lines").upsert(lines, on_conflict="id").execute()
            log.info("Mirrored straight repayment %s to Supabase successfully.", rep_raw_id)
            return je_row

        else:
            # ── CASE (b): REINVESTMENT ──────────────────────────────────────────
            target_po = ""
            if new_advance_doc:
                target_po = new_advance_doc.get("po_number") or new_advance_doc.get("po_id") or ""
            target_desc = f" into PO {target_po}" if target_po else ""

            narration = f"Margin Payout (₹{margin}) & Reinvestment of Principal (₹{principal}) for {inv_name}{target_desc}"
            total_trans = round(principal + margin, 2)

            je_row = {
                "id": je_id,
                "entry_number": f"JE-INV-REINV-{rep_uuid[:8].upper()}",
                "entry_date": payout_date,
                "entry_type": "JOURNAL",
                "status": "POSTED",
                "narration": narration,
                "source_document_ref": f"INV-REINV-{rep_uuid[:8]}",
                "total_debit": total_trans,
                "total_credit": total_trans,
                "posted_by": repayment_doc.get("created_by") or "system",
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
            client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

            lines = [
                # 1. Margin Cash Leg: Debit Finance Cost
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr_margin")),
                    "journal_entry_id": je_id,
                    "account_id": gl_margin_cost,
                    "entity_id": investor_uuid,
                    "line_number": 1,
                    "description": f"Margin paid to {inv_name} prior to reinvestment",
                    "debit": margin,
                    "credit": 0.0,
                    "reconciliation_status": "RECONCILED",
                },
                # 2. Margin Cash Leg: Credit Bank/Cash (margin only)
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr_margin_cash")),
                    "journal_entry_id": je_id,
                    "account_id": credit_gl,
                    "entity_id": investor_uuid,
                    "line_number": 2,
                    "description": f"Margin cash disbursement via {payment_mode}",
                    "debit": 0.0,
                    "credit": margin,
                    "reconciliation_status": "UNRECONCILED" if not is_cash else "RECONCILED",
                },
                # 3. Principal Non-Cash Roll Leg: Debit old advance (closing it)
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr_close_old")),
                    "journal_entry_id": je_id,
                    "account_id": gl_adv_payable,
                    "entity_id": investor_uuid,
                    "line_number": 3,
                    "description": f"Closing advance for rollover into PO {target_po}",
                    "debit": principal,
                    "credit": 0.0,
                    "reconciliation_status": "RECONCILED",
                },
                # 4. Principal Non-Cash Roll Leg: Credit new advance (new advance tagged to new PO)
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr_open_new")),
                    "journal_entry_id": je_id,
                    "account_id": gl_adv_payable,
                    "entity_id": investor_uuid,
                    "line_number": 4,
                    "description": f"Roll forward advance tagged to PO {target_po}",
                    "debit": 0.0,
                    "credit": principal,
                    "reconciliation_status": "RECONCILED",
                }
            ]
            client.table("journal_lines").upsert(lines, on_conflict="id").execute()
            log.info("Mirrored reinvestment %s to Supabase successfully.", rep_raw_id)
            return je_row

    except Exception as e:
        log.error("Failed to sync investor repayment to Supabase: %s", e)
        return None
