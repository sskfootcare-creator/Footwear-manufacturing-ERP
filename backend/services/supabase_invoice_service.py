"""Supabase Invoicing & Accounts Receivable (AR) Synchronization Service.

Handles persistence of Sales Invoices, Client Entities, Payment Receipts,
and double-entry General Ledger postings in Supabase:
- public.financial_entities (Clients / B2B Buyers)
- public.journal_entries & public.journal_lines (Double-Entry Core)
- public.sales_invoices
- public.payment_vouchers & public.voucher_allocations
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from db.supabase_client import get_supabase_admin_client

log = logging.getLogger(__name__)


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
    """Retrieve chart_of_accounts code -> UUID map."""
    try:
        res = client.table("chart_of_accounts").select("id, code").execute()
        return {row["code"]: row["id"] for row in (res.data or [])}
    except Exception as e:
        log.error("Failed to query chart_of_accounts from Supabase: %s", e)
        return {}


def ensure_client_entity(client, client_data: Dict[str, Any], coa_map: Dict[str, str]) -> Optional[str]:
    """Ensure client exists in public.financial_entities with GL Account 1030 (Accounts Receivable)."""
    gl_ar = coa_map.get("1030")
    if not gl_ar:
        log.warning("GL Account 1030 (Accounts Receivable) not found in chart_of_accounts.")
        return None

    client_id_val = client_data.get("id") or client_data.get("_id") or client_data.get("client_id")
    if not client_id_val:
        # Generate stable UUID based on company name
        company_clean = (client_data.get("client_name") or client_data.get("company_name") or "CLIENT").strip()
        client_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"CLIENT_{company_clean}"))
    else:
        client_uuid = to_uuid(client_id_val)

    name = (client_data.get("client_name") or client_data.get("company_name") or "Client").strip()
    code = (client_data.get("code") or f"CLI-{name[:4].upper()}-{client_uuid[:4].upper()}").strip()

    row = {
        "id": client_uuid,
        "entity_type": "CLIENT",
        "external_ref_id": str(client_id_val or client_uuid),
        "code": code,
        "name": name,
        "gstin": client_data.get("client_gstin") or client_data.get("gstin") or "",
        "pan": client_data.get("pan") or "",
        "phone": client_data.get("phone") or "",
        "email": client_data.get("email") or "",
        "billing_address": str(client_data.get("billing_address") or ""),
        "payment_terms_days": int(client_data.get("payment_terms_days") or 30),
        "gl_account_id": gl_ar,
        "is_active": True,
    }

    try:
        client.table("financial_entities").upsert(row, on_conflict="id").execute()
        return client_uuid
    except Exception as e:
        log.error("Failed to upsert client entity %s in Supabase: %s", client_uuid, e)
        return None


def sync_direct_invoice_to_supabase(invoice_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Persist Direct Invoice into Supabase:
    1. Ensures Client in public.financial_entities.
    2. Creates balanced public.journal_entries (Debit AR 1030 = Credit Revenue 4010 + GST).
    3. Creates public.journal_lines.
    4. Creates public.sales_invoices record.
    """
    client = get_supabase_admin_client()
    if not client:
        log.warning("Supabase admin client unavailable; skipping invoice sync.")
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            log.warning("No chart of accounts found in Supabase.")
            return None

        gl_ar = coa_map.get("1030")              # Accounts Receivable
        gl_revenue = coa_map.get("4010")         # B2B Footwear Sales Revenue
        gl_cgst = coa_map.get("2030-CGST-OUT")   # CGST Output
        gl_sgst = coa_map.get("2030-SGST-OUT")   # SGST Output
        gl_igst = coa_map.get("2030-IGST-OUT")   # IGST Output

        if not gl_ar or not gl_revenue:
            log.error("Core GL accounts (1030 or 4010) missing in Supabase.")
            return None

        # 1. Ensure Client
        client_uuid = ensure_client_entity(client, invoice_doc, coa_map)
        if not client_uuid:
            log.error("Could not link/create client entity in Supabase.")
            return None

        raw_inv_id = str(invoice_doc.get("_id") or invoice_doc.get("id") or uuid.uuid4())
        inv_uuid = to_uuid(raw_inv_id)
        invoice_no = invoice_doc.get("invoice_no") or f"INV-{inv_uuid[:8].upper()}"

        # Parse amounts
        subtotal = round(float(invoice_doc.get("subtotal") or 0.0), 2)
        cgst_amt = round(float(invoice_doc.get("cgst_amount") or 0.0), 2)
        sgst_amt = round(float(invoice_doc.get("sgst_amount") or 0.0), 2)
        igst_amt = round(float(invoice_doc.get("igst_amount") or 0.0), 2)
        grand_total = round(float(invoice_doc.get("grand_total") or (subtotal + cgst_amt + sgst_amt + igst_amt)), 2)

        # Dates
        raw_inv_date = invoice_doc.get("invoice_iso_date") or invoice_doc.get("invoice_date") or datetime.now(timezone.utc).date().isoformat()
        if "/" in str(raw_inv_date):
            # Parse DD/MM/YYYY
            p = str(raw_inv_date).split("/")
            if len(p) == 3:
                raw_inv_date = f"{p[2]}-{p[1]}-{p[0]}"
        inv_date_str = str(raw_inv_date)[:10]

        due_date_str = str(invoice_doc.get("due_date") or inv_date_str)[:10]
        client_name = invoice_doc.get("client_name") or "Client"

        # 2. Journal Entry
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_INV_{inv_uuid}"))
        narration = f"Sales Tax Invoice {invoice_no} to {client_name}"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-INV-{invoice_no.replace('/', '-')}",
            "entry_date": inv_date_str,
            "entry_type": "SALES_INVOICE",
            "status": "POSTED",
            "narration": narration,
            "source_document_ref": invoice_no,
            "total_debit": grand_total,
            "total_credit": grand_total,
            "posted_by": invoice_doc.get("by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # 3. Journal Lines (Double-Entry: Debit AR = Credit Sales Revenue + Taxes)
        lines: List[Dict[str, Any]] = [
            # Line 1: Debit Accounts Receivable (Grand Total)
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_ar")),
                "journal_entry_id": je_id,
                "account_id": gl_ar,
                "entity_id": client_uuid,
                "line_number": 1,
                "description": f"Receivable: {invoice_no}",
                "debit": grand_total,
                "credit": 0.0,
                "reconciliation_status": "UNRECONCILED",
            },
            # Line 2: Credit Sales Revenue (Subtotal)
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_rev")),
                "journal_entry_id": je_id,
                "account_id": gl_revenue,
                "entity_id": client_uuid,
                "line_number": 2,
                "description": f"Sales Revenue: {invoice_no}",
                "debit": 0.0,
                "credit": subtotal,
                "reconciliation_status": "RECONCILED",
            },
        ]

        next_line_no = 3
        if cgst_amt > 0 and gl_cgst:
            lines.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cgst")),
                "journal_entry_id": je_id,
                "account_id": gl_cgst,
                "entity_id": client_uuid,
                "line_number": next_line_no,
                "description": f"CGST Output: {invoice_no}",
                "debit": 0.0,
                "credit": cgst_amt,
                "reconciliation_status": "RECONCILED",
            })
            next_line_no += 1

        if sgst_amt > 0 and gl_sgst:
            lines.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_sgst")),
                "journal_entry_id": je_id,
                "account_id": gl_sgst,
                "entity_id": client_uuid,
                "line_number": next_line_no,
                "description": f"SGST Output: {invoice_no}",
                "debit": 0.0,
                "credit": sgst_amt,
                "reconciliation_status": "RECONCILED",
            })
            next_line_no += 1

        if igst_amt > 0 and gl_igst:
            lines.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_igst")),
                "journal_entry_id": je_id,
                "account_id": gl_igst,
                "entity_id": client_uuid,
                "line_number": next_line_no,
                "description": f"IGST Output: {invoice_no}",
                "debit": 0.0,
                "credit": igst_amt,
                "reconciliation_status": "RECONCILED",
            })

        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        # 4. Sales Invoices
        paid_amt = round(float(invoice_doc.get("received_amount") or 0.0), 2)
        net_rec = max(0.0, round(grand_total - paid_amt, 2))
        inv_status = "PAID" if net_rec <= 0.01 else ("PARTIALLY_PAID" if paid_amt > 0 else "POSTED")

        inv_row = {
            "id": inv_uuid,
            "invoice_no": invoice_no,
            "invoice_date": inv_date_str,
            "due_date": due_date_str,
            "client_id": client_uuid,
            "po_number": invoice_doc.get("po_number") or "DIRECT",
            "customer_gstin": invoice_doc.get("client_gstin") or "",
            "place_of_supply": invoice_doc.get("place_of_supply") or "09-Uttar Pradesh",
            "subtotal": subtotal,
            "cgst_rate": float(invoice_doc.get("cgst_rate") or 0.0),
            "cgst_amount": cgst_amt,
            "sgst_rate": float(invoice_doc.get("sgst_rate") or 0.0),
            "sgst_amount": sgst_amt,
            "igst_rate": float(invoice_doc.get("igst_rate") or 0.0),
            "igst_amount": igst_amt,
            "grand_total": grand_total,
            "paid_amount": paid_amt,
            "net_receivable": net_rec,
            "status": inv_status,
            "journal_entry_id": je_id,
            "notes": invoice_doc.get("notes") or "",
        }
        res_inv = client.table("sales_invoices").upsert(inv_row, on_conflict="id").execute()
        log.info("Successfully synced Direct Invoice %s (%s) to Supabase.", invoice_no, inv_uuid)
        return res_inv.data[0] if (res_inv and getattr(res_inv, "data", None)) else inv_row

    except Exception as e:
        log.error("Failed to sync invoice to Supabase: %s", e)
        return None


def sync_invoice_payment_to_supabase(payment_doc: Dict[str, Any], invoice_docs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Persist Payment Receipt against Invoices into Supabase:
    1. Debit Bank/Cash, Credit Accounts Receivable.
    2. Creates public.payment_vouchers record (voucher_type='RECEIPT').
    3. Creates public.voucher_allocations for each invoice paid.
    4. Updates public.sales_invoices paid_amount.
    """
    client = get_supabase_admin_client()
    if not client:
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            return None

        gl_ar = coa_map.get("1030")
        gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020")
        gl_bank = coa_map.get("1010")

        if not gl_ar:
            return None

        amount = round(float(payment_doc.get("amount") or 0.0), 2)
        if amount <= 0:
            return None

        mode = (payment_doc.get("mode") or "Bank Transfer").upper()
        is_cash = ("CASH" in mode) and not payment_doc.get("bank_account_id")
        debit_gl = gl_cash if is_cash else gl_bank

        pay_id = to_uuid(payment_doc.get("_id") or payment_doc.get("id"))
        pay_date = str(payment_doc.get("payment_date") or datetime.now(timezone.utc).date().isoformat())[:10]
        payment_no = payment_doc.get("payment_no") or f"REC-{pay_id[:8].upper()}"

        client_uuid = None
        if invoice_docs:
            client_uuid = ensure_client_entity(client, invoice_docs[0], coa_map)
        elif payment_doc.get("client_name"):
            client_uuid = ensure_client_entity(client, {
                "client_name": payment_doc.get("client_name"),
                "client_id": payment_doc.get("client_id") or payment_doc.get("client_name"),
            }, coa_map)

        # 1. Receipt Journal Entry
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_REC_{pay_id}"))
        narration = f"Receipt {payment_no} from {payment_doc.get('client_name') or 'Client'}"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-REC-{payment_no.replace('/', '-')}",
            "entry_date": pay_date,
            "entry_type": "RECEIPT",
            "status": "POSTED",
            "narration": narration,
            "source_document_ref": payment_no,
            "total_debit": amount,
            "total_credit": amount,
            "posted_by": payment_doc.get("by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # 2. Receipt Journal Lines
        lines = [
            # Debit Cash / Bank
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr")),
                "journal_entry_id": je_id,
                "account_id": debit_gl,
                "entity_id": client_uuid,
                "line_number": 1,
                "description": f"Receipt via {mode}",
                "debit": amount,
                "credit": 0.0,
                "reconciliation_status": "UNRECONCILED" if not is_cash else "RECONCILED",
            },
            # Credit Accounts Receivable
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr")),
                "journal_entry_id": je_id,
                "account_id": gl_ar,
                "entity_id": client_uuid,
                "line_number": 2,
                "description": f"Payment against invoices from {payment_doc.get('client_name')}",
                "debit": 0.0,
                "credit": amount,
                "reconciliation_status": "RECONCILED",
            }
        ]
        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        # 3. Payment Voucher
        voucher_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"VCH_REC_{pay_id}"))
        bank_acc_uuid = to_uuid(payment_doc.get("bank_account_id")) if payment_doc.get("bank_account_id") else None

        voucher_row = {
            "id": voucher_id,
            "voucher_no": f"VCH-REC-{payment_no}",
            "voucher_type": "RECEIPT",
            "voucher_date": pay_date,
            "entity_id": client_uuid,
            "payment_mode": "CASH" if is_cash else "BANK_TRANSFER",
            "bank_account_id": bank_acc_uuid,
            "amount": amount,
            "reference_number": payment_doc.get("reference") or "",
            "journal_entry_id": je_id,
            "notes": narration,
        }
        res_vch = client.table("payment_vouchers").upsert(voucher_row, on_conflict="id").execute()

        # 4. Voucher Allocations
        allocations = payment_doc.get("allocations") or {}
        alloc_rows = []
        for inv_id_str, alloc_amt in allocations.items():
            alloc_amt_flt = round(float(alloc_amt or 0.0), 2)
            if alloc_amt_flt <= 0:
                continue
            inv_uuid = to_uuid(inv_id_str)
            alloc_rows.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{voucher_id}_{inv_uuid}")),
                "voucher_id": voucher_id,
                "sales_invoice_id": inv_uuid,
                "allocated_amount": alloc_amt_flt,
            })
            # Also update invoice in Supabase
            try:
                cur_inv = client.table("sales_invoices").select("grand_total, paid_amount").eq("id", inv_uuid).execute()
                if cur_inv.data:
                    gt = float(cur_inv.data[0].get("grand_total") or 0.0)
                    old_paid = float(cur_inv.data[0].get("paid_amount") or 0.0)
                    new_paid = round(old_paid + alloc_amt_flt, 2)
                    new_net = max(0.0, round(gt - new_paid, 2))
                    st = "PAID" if new_net <= 0.01 else "PARTIALLY_PAID"
                    client.table("sales_invoices").update({
                        "paid_amount": new_paid,
                        "net_receivable": new_net,
                        "status": st
                    }).eq("id", inv_uuid).execute()
            except Exception as ie:
                log.debug("Could not update sales_invoice %s in Supabase: %s", inv_uuid, ie)

        if alloc_rows:
            client.table("voucher_allocations").upsert(alloc_rows, on_conflict="id").execute()

        log.info("Successfully recorded receipt voucher %s into Supabase.", voucher_id)
        return res_vch.data[0] if (res_vch and getattr(res_vch, "data", None)) else voucher_row

    except Exception as e:
        log.error("Failed to sync invoice payment to Supabase: %s", e)
        return None
