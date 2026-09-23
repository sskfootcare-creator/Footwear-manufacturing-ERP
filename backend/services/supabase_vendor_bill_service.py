"""Supabase Vendor Bills & Accounts Payable (AP) Synchronization Service.

Handles persistence of Vendor Entities, Vendor Bills (Purchases / Goods Receipts),
Vendor Payment Vouchers, and double-entry General Ledger postings in Supabase:
- public.financial_entities (Vendors / Raw Material Suppliers)
- public.journal_entries & public.journal_lines (Double-Entry Core)
- public.vendor_bills
- public.payment_vouchers & public.voucher_allocations

Mirrors services/supabase_invoice_service.py for the accounts payable side.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from db.supabase_client import get_supabase_admin_client
from services.supabase_invoice_service import to_uuid, _get_coa_map

log = logging.getLogger(__name__)

DEFAULT_CASH_REGISTER_UUID = str(uuid.uuid5(uuid.NAMESPACE_OID, "FACTORY_PETTY_CASH_REGISTER"))


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


def ensure_vendor_entity(client, vendor_data: Dict[str, Any], coa_map: Dict[str, str]) -> Optional[str]:
    """Ensure vendor exists in public.financial_entities with GL Account 2010 (Accounts Payable)."""
    gl_ap = coa_map.get("2010")
    if not gl_ap:
        log.warning("GL Account 2010 (Accounts Payable) not found in chart_of_accounts.")
        return None

    vendor_id_val = vendor_data.get("id") or vendor_data.get("_id") or vendor_data.get("vendor_id")
    name = (vendor_data.get("name") or vendor_data.get("vendor_name") or "Vendor").strip()
    if not vendor_id_val:
        vendor_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"VENDOR_{name}"))
    else:
        vendor_uuid = to_uuid(vendor_id_val)

    code = (vendor_data.get("code") or f"VEN-{name[:4].upper()}-{vendor_uuid[:4].upper()}").strip()

    row = {
        "id": vendor_uuid,
        "entity_type": "VENDOR",
        "external_ref_id": str(vendor_id_val or vendor_uuid),
        "code": code,
        "name": name,
        "gstin": vendor_data.get("gstin") or "",
        "pan": vendor_data.get("pan") or "",
        "phone": vendor_data.get("phone") or "",
        "email": vendor_data.get("email") or "",
        "billing_address": str(vendor_data.get("billing_address") or vendor_data.get("address") or ""),
        "payment_terms_days": int(vendor_data.get("payment_terms_days") or 30),
        "gl_account_id": gl_ap,
        "is_active": True,
    }

    try:
        client.table("financial_entities").upsert(row, on_conflict="id").execute()
        return vendor_uuid
    except Exception as e:
        log.error("Failed to upsert vendor entity %s in Supabase: %s", vendor_uuid, e)
        return None


def sync_vendor_po_to_supabase(
    po_doc: Dict[str, Any],
    vendor_doc: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Persist Vendor PO / Goods Receipt Note into Supabase:
    1. Ensures Vendor in public.financial_entities.
    2. Creates balanced public.journal_entries (Debit Inventory/COGS 1040/5010 = Credit Accounts Payable 2010).
    3. Creates public.journal_lines.
    4. Creates public.vendor_bills record.

    Mirrors sync_direct_invoice_to_supabase for the Accounts Payable side.
    """
    client = get_supabase_admin_client()
    if not client:
        log.warning("Supabase admin client unavailable; skipping vendor bill sync.")
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            log.warning("No chart of accounts found in Supabase.")
            return None

        gl_ap = coa_map.get("2010")                                  # Accounts Payable (Raw Material Suppliers)
        gl_inv = coa_map.get("1040") or coa_map.get("5010")          # Raw Material Inventory Asset or COGS
        gl_cgst_in = coa_map.get("1060-CGST-IN")                     # CGST Input Tax Credit
        gl_sgst_in = coa_map.get("1060-SGST-IN")                     # SGST Input Tax Credit
        gl_igst_in = coa_map.get("1060-IGST-IN")                     # IGST Input Tax Credit

        if not gl_ap or not gl_inv:
            log.error("Core GL accounts (2010 or 1040/5010) missing in Supabase.")
            return None

        # 1. Ensure Vendor entity
        v_doc = vendor_doc or {}
        if not v_doc and po_doc.get("vendor_id"):
            v_doc = {
                "id": po_doc.get("vendor_id"),
                "name": po_doc.get("vendor_name") or "Vendor"
            }
        vendor_uuid = ensure_vendor_entity(client, v_doc, coa_map)
        if not vendor_uuid:
            log.error("Could not link/create vendor entity in Supabase.")
            return None

        # Identifiers
        raw_id = str(po_doc.get("_id") or po_doc.get("id") or po_doc.get("receipt_id") or uuid.uuid4())
        bill_uuid = to_uuid(raw_id)
        po_number = po_doc.get("po_number") or f"VPO-{bill_uuid[:8].upper()}"
        bill_no = po_doc.get("bill_no") or po_doc.get("receipt_id") or f"BILL-{po_number.replace('/', '-')}"

        # Parse amounts
        total_amount = round(float(po_doc.get("total_amount") or po_doc.get("grand_total") or 0.0), 2)
        if total_amount <= 0 and po_doc.get("line_items"):
            total_amount = round(sum(float(li.get("amount") or (float(li.get("quantity", 0)) * float(li.get("rate", 0)))) for li in po_doc.get("line_items", [])), 2)
        if total_amount <= 0:
            log.warning("Vendor bill total_amount %s <= 0; skipping Supabase sync.", total_amount)
            return None

        cgst_amt = round(float(po_doc.get("cgst_amount") or 0.0), 2)
        sgst_amt = round(float(po_doc.get("sgst_amount") or 0.0), 2)
        igst_amt = round(float(po_doc.get("igst_amount") or 0.0), 2)
        subtotal = round(float(po_doc.get("subtotal") or (total_amount - (cgst_amt + sgst_amt + igst_amt))), 2)

        # Dates
        raw_date = po_doc.get("receipt_date") or po_doc.get("bill_date") or po_doc.get("created_at") or datetime.now(timezone.utc).date().isoformat()
        if "/" in str(raw_date):
            p = str(raw_date).split("/")
            if len(p) == 3:
                raw_date = f"{p[2]}-{p[1]}-{p[0]}"
        bill_date_str = str(raw_date)[:10]

        terms_days = int(v_doc.get("payment_terms_days") or po_doc.get("payment_terms_days") or 30)
        try:
            parsed_date = datetime.strptime(bill_date_str, "%Y-%m-%d").date()
            due_date_str = (parsed_date + timedelta(days=terms_days)).isoformat()
        except Exception:
            due_date_str = bill_date_str

        vendor_name = v_doc.get("name") or po_doc.get("vendor_name") or "Vendor"

        # 2. Journal Entry
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_BILL_{bill_uuid}"))
        narration = f"Vendor Bill {bill_no} (PO: {po_number}) from {vendor_name}"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-BILL-{bill_no.replace('/', '-')}",
            "entry_date": bill_date_str,
            "entry_type": "VENDOR_BILL",
            "status": "POSTED",
            "narration": narration,
            "source_document_ref": bill_no,
            "total_debit": total_amount,
            "total_credit": total_amount,
            "posted_by": po_doc.get("by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # 3. Journal Lines (Debit Inventory/COGS + Taxes = Credit Accounts Payable)
        lines: List[Dict[str, Any]] = [
            # Line 1: Debit Raw Material Inventory Asset / COGS (Subtotal)
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_rm")),
                "journal_entry_id": je_id,
                "account_id": gl_inv,
                "entity_id": vendor_uuid,
                "line_number": 1,
                "description": f"RM Inventory: {bill_no}",
                "debit": subtotal,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            },
        ]

        next_line_no = 2
        if cgst_amt > 0 and gl_cgst_in:
            lines.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cgst")),
                "journal_entry_id": je_id,
                "account_id": gl_cgst_in,
                "entity_id": vendor_uuid,
                "line_number": next_line_no,
                "description": f"CGST Input: {bill_no}",
                "debit": cgst_amt,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            })
            next_line_no += 1

        if sgst_amt > 0 and gl_sgst_in:
            lines.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_sgst")),
                "journal_entry_id": je_id,
                "account_id": gl_sgst_in,
                "entity_id": vendor_uuid,
                "line_number": next_line_no,
                "description": f"SGST Input: {bill_no}",
                "debit": sgst_amt,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            })
            next_line_no += 1

        if igst_amt > 0 and gl_igst_in:
            lines.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_igst")),
                "journal_entry_id": je_id,
                "account_id": gl_igst_in,
                "entity_id": vendor_uuid,
                "line_number": next_line_no,
                "description": f"IGST Input: {bill_no}",
                "debit": igst_amt,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            })
            next_line_no += 1

        # Final line: Credit Accounts Payable (Total Amount)
        lines.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_ap")),
            "journal_entry_id": je_id,
            "account_id": gl_ap,
            "entity_id": vendor_uuid,
            "line_number": next_line_no,
            "description": f"Payable: {bill_no}",
            "debit": 0.0,
            "credit": total_amount,
            "reconciliation_status": "UNRECONCILED",
        })

        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        # 4. Vendor Bills
        paid_amt = round(float(po_doc.get("paid_amount") or 0.0), 2)
        net_payable = max(0.0, round(total_amount - paid_amt, 2))
        bill_status = "PAID" if net_payable <= 0.01 else ("PARTIALLY_PAID" if paid_amt > 0 else "POSTED")

        bill_row = {
            "id": bill_uuid,
            "bill_no": bill_no,
            "vendor_id": vendor_uuid,
            "vendor_po_ref": po_number,
            "bill_date": bill_date_str,
            "due_date": due_date_str,
            "subtotal": subtotal,
            "cgst_amount": cgst_amt,
            "sgst_amount": sgst_amt,
            "igst_amount": igst_amt,
            "total_amount": total_amount,
            "paid_amount": paid_amt,
            "status": bill_status,
            "journal_entry_id": je_id,
        }
        res_bill = client.table("vendor_bills").upsert(bill_row, on_conflict="id").execute()
        log.info("Successfully synced Vendor Bill %s (%s) to Supabase.", bill_no, bill_uuid)
        return res_bill.data[0] if (res_bill and getattr(res_bill, "data", None)) else bill_row

    except Exception as e:
        log.error("Failed to sync vendor bill to Supabase: %s", e)
        return None


def sync_vendor_payment_to_supabase(
    payment_doc: Dict[str, Any],
    vendor_doc: Optional[Dict[str, Any]] = None,
    po_docs: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Persist Vendor Payment Voucher into Supabase:
    1. Debit Accounts Payable (2010), Credit Bank/Cash (1010/1020).
    2. Creates public.payment_vouchers record (voucher_type='PAYMENT').
    3. Creates public.voucher_allocations for each vendor bill paid.
    4. Updates public.vendor_bills paid_amount & status.

    Mirrors sync_invoice_payment_to_supabase for the Accounts Payable side.
    """
    client = get_supabase_admin_client()
    if not client:
        return None

    try:
        coa_map = _get_coa_map(client)
        if not coa_map:
            return None

        gl_ap = coa_map.get("2010")                                        # Accounts Payable
        gl_cash = coa_map.get("1020-FACTORY-CASH") or coa_map.get("1020")  # Cash
        gl_bank = coa_map.get("1010")                                       # Bank Accounts

        if not gl_ap:
            return None

        amount = round(float(payment_doc.get("amount") or 0.0), 2)
        if amount <= 0:
            return None

        mode = (payment_doc.get("mode") or "Bank Transfer").upper()
        account_type = payment_doc.get("account_type") or ("cash" if "CASH" in mode else "bank")
        is_cash = account_type == "cash" or ("CASH" in mode and not payment_doc.get("bank_account_id"))
        credit_gl = gl_cash if is_cash else gl_bank

        pay_id = to_uuid(payment_doc.get("_id") or payment_doc.get("id"))
        pay_date = str(payment_doc.get("payment_date") or datetime.now(timezone.utc).date().isoformat())[:10]
        payment_no = payment_doc.get("payment_no") or f"PAY-{pay_id[:8].upper()}"

        # 1. Ensure Vendor Entity
        v_doc = vendor_doc or {}
        if not v_doc and payment_doc.get("vendor_id"):
            v_doc = {
                "id": payment_doc.get("vendor_id"),
                "name": payment_doc.get("vendor_name") or "Vendor"
            }
        vendor_uuid = ensure_vendor_entity(client, v_doc, coa_map)
        if not vendor_uuid:
            return None

        vendor_name = v_doc.get("name") or payment_doc.get("vendor_name") or "Vendor"

        # 2. Payment Journal Entry
        je_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"JE_PAY_{pay_id}"))
        narration = f"Payment {payment_no} to {vendor_name}"

        je_row = {
            "id": je_id,
            "entry_number": f"JE-PAY-{payment_no.replace('/', '-')}",
            "entry_date": pay_date,
            "entry_type": "PAYMENT",
            "status": "POSTED",
            "narration": narration,
            "source_document_ref": payment_no,
            "total_debit": amount,
            "total_credit": amount,
            "posted_by": payment_doc.get("by") or "system",
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("journal_entries").upsert(je_row, on_conflict="id").execute()

        # 3. Journal Lines (Debit Accounts Payable 2010 = Credit Cash/Bank 1020/1010)
        lines = [
            # Line 1: Debit Accounts Payable
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_dr")),
                "journal_entry_id": je_id,
                "account_id": gl_ap,
                "entity_id": vendor_uuid,
                "line_number": 1,
                "description": f"Payment to {vendor_name} ({payment_no})",
                "debit": amount,
                "credit": 0.0,
                "reconciliation_status": "RECONCILED",
            },
            # Line 2: Credit Cash / Bank
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{je_id}_line_cr")),
                "journal_entry_id": je_id,
                "account_id": credit_gl,
                "entity_id": vendor_uuid,
                "line_number": 2,
                "description": f"Paid via {mode}",
                "debit": 0.0,
                "credit": amount,
                "reconciliation_status": "UNRECONCILED" if not is_cash else "RECONCILED",
            }
        ]
        client.table("journal_lines").upsert(lines, on_conflict="id").execute()

        # 4. Payment Voucher
        voucher_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"VCH_PAY_{pay_id}"))
        bank_acc_uuid = to_uuid(payment_doc.get("bank_account_id")) if (payment_doc.get("bank_account_id") and not is_cash) else None
        cash_reg_uuid = ensure_cash_register(client, coa_map) if is_cash else None

        voucher_row = {
            "id": voucher_id,
            "voucher_no": f"VCH-PAY-{payment_no}",
            "voucher_type": "PAYMENT",
            "voucher_date": pay_date,
            "entity_id": vendor_uuid,
            "payment_mode": "CASH" if is_cash else "BANK_TRANSFER",
            "bank_account_id": bank_acc_uuid,
            "cash_register_id": cash_reg_uuid,
            "amount": amount,
            "reference_number": payment_doc.get("reference") or "",
            "journal_entry_id": je_id,
            "notes": payment_doc.get("notes") or narration,
        }
        res_vch = client.table("payment_vouchers").upsert(voucher_row, on_conflict="id").execute()

        # 5. Voucher Allocations against Vendor Bills
        target_po_num = payment_doc.get("vendor_po_number") or ""
        if not target_po_num and po_docs:
            target_po_num = po_docs[0].get("po_number") or ""

        try:
            bill_query = client.table("vendor_bills").select("id, bill_no, total_amount, paid_amount, status, vendor_po_ref")
            bill_query = bill_query.eq("vendor_id", vendor_uuid).neq("status", "PAID")
            res_bills = bill_query.execute()
            bills = res_bills.data or []

            # Prioritize bills matching the target PO if specified
            if target_po_num and bills:
                bills.sort(key=lambda b: (0 if b.get("vendor_po_ref") == target_po_num else 1, b.get("bill_date") or ""))

            remaining = amount
            alloc_rows = []
            for b in bills:
                b_id = b["id"]
                tot = float(b.get("total_amount") or 0.0)
                paid = float(b.get("paid_amount") or 0.0)
                outstanding = max(0.0, round(tot - paid, 2))
                if outstanding <= 0:
                    continue

                take = min(outstanding, remaining)
                take = round(take, 2)
                if take > 0:
                    alloc_rows.append({
                        "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{voucher_id}_{b_id}")),
                        "voucher_id": voucher_id,
                        "vendor_bill_id": b_id,
                        "allocated_amount": take,
                    })
                    new_paid = round(paid + take, 2)
                    new_status = "PAID" if new_paid >= (tot - 0.01) else "PARTIALLY_PAID"
                    try:
                        client.table("vendor_bills").update({
                            "paid_amount": new_paid,
                            "status": new_status,
                        }).eq("id", b_id).execute()
                    except Exception as b_upd_err:
                        log.debug("Could not update vendor_bill %s in Supabase: %s", b_id, b_upd_err)

                    remaining = round(remaining - take, 2)
                if remaining <= 0:
                    break

            if alloc_rows:
                client.table("voucher_allocations").upsert(alloc_rows, on_conflict="id").execute()

        except Exception as alloc_err:
            log.debug("Vendor bill allocation skipped or failed: %s", alloc_err)

        log.info("Successfully recorded vendor payment voucher %s into Supabase.", voucher_id)
        return res_vch.data[0] if (res_vch and getattr(res_vch, "data", None)) else voucher_row

    except Exception as e:
        log.error("Failed to sync vendor payment to Supabase: %s", e)
        return None
