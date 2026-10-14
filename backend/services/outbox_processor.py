import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from services.supabase_invoice_service import (
    sync_direct_invoice_to_supabase,
    sync_invoice_payment_to_supabase,
    void_invoice_in_supabase,
    reverse_payment_in_supabase,
)
from services.supabase_vendor_bill_service import (
    sync_vendor_po_to_supabase,
    sync_vendor_payment_to_supabase,
    void_vendor_bill_in_supabase,
)
from services.supabase_expense_service import (
    sync_expense_to_supabase,
    void_expense_in_supabase,
)
from services.supabase_payroll_service import sync_wage_payment_to_supabase
from services.supabase_investor_service import (
    sync_investor_advance_to_supabase,
    sync_investor_repayment_to_supabase,
)

log = logging.getLogger("erp.outbox")

async def process_outbox_events(db: Any):
    """
    Background worker that continuously polls the outbox_events collection
    and pushes pending events to Supabase.
    """
    log.info("Starting Supabase outbox processor background worker...")
    while True:
        try:
            # Find one pending event, prioritizing older ones
            event = await db.outbox_events.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}},
                sort=[("created_at", 1)]
            )
            
            if not event:
                # No pending events, wait before polling again
                await asyncio.sleep(5)
                continue

            event_id = event["_id"]
            event_type = event.get("type")
            payload = event.get("payload") or {}
            
            log.info(f"Processing outbox event {event_id} of type {event_type}")

            success = False
            error_msg = None

            try:
                # 1. SALES INVOICES
                if event_type in ("direct_invoice_created", "invoice_created", "sales_invoice_created"):
                    res = sync_direct_invoice_to_supabase(payload)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for invoice sync.")
                elif event_type in ("invoice_voided", "sales_invoice_voided"):
                    inv_id = payload.get("invoice_id") or payload.get("id") or payload.get("_id")
                    by = payload.get("by") or "system"
                    reason = payload.get("reason") or "Invoice voided"
                    res = void_invoice_in_supabase(inv_id, voided_by=by, reason=reason)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for invoice voiding.")

                # 2. CUSTOMER PAYMENTS / RECEIPTS
                elif event_type in ("payment_received", "payment_created", "customer_payment_created"):
                    payment_doc = payload.get("payment_doc") or payload
                    invoice_docs = payload.get("invoice_docs", [])
                    res = sync_invoice_payment_to_supabase(payment_doc, invoice_docs)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for payment sync.")
                elif event_type in ("payment_reversed", "payment_deleted"):
                    pay_id = payload.get("payment_id") or payload.get("id") or payload.get("_id")
                    by = payload.get("by") or "system"
                    reason = payload.get("reason") or "Payment reversed"
                    res = reverse_payment_in_supabase(pay_id, reversed_by=by, reason=reason)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for payment reversal.")

                # 3. VENDOR BILLS (AP)
                elif event_type in ("vendor_bill_created", "vendor_po_received"):
                    po_doc = payload.get("po_doc") or payload
                    vendor_doc = payload.get("vendor_doc")
                    res = sync_vendor_po_to_supabase(po_doc, vendor_doc=vendor_doc)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for vendor bill sync.")
                elif event_type in ("vendor_bill_voided", "vendor_po_deleted"):
                    po_id = payload.get("po_id") or payload.get("id") or payload.get("_id")
                    by = payload.get("by") or "system"
                    reason = payload.get("reason") or "Vendor bill voided"
                    res = void_vendor_bill_in_supabase(po_id, voided_by=by, reason=reason)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for vendor bill voiding.")

                # 4. VENDOR PAYMENTS
                elif event_type == "vendor_payment_created":
                    payment_doc = payload.get("payment_doc") or payload
                    vendor_doc = payload.get("vendor_doc")
                    po_docs = payload.get("po_docs")
                    res = sync_vendor_payment_to_supabase(payment_doc, vendor_doc=vendor_doc, po_docs=po_docs)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for vendor payment sync.")

                # 5. EXPENSES & OPERATING OUTFLOWS
                elif event_type in ("expense_created", "expense_confirmed"):
                    exp_doc = payload.get("expense_doc") or payload
                    res = sync_expense_to_supabase(exp_doc)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for expense sync.")
                elif event_type in ("expense_voided", "expense_deleted"):
                    exp_id = payload.get("expense_id") or payload.get("id") or payload.get("_id")
                    by = payload.get("by") or "system"
                    reason = payload.get("reason") or "Expense deleted"
                    res = void_expense_in_supabase(exp_id, voided_by=by, reason=reason)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for expense voiding.")

                # 6. WORKER WAGE DISBURSEMENTS (PAYROLL)
                elif event_type in ("wage_payment_created", "payroll_disbursed"):
                    pay_doc = payload.get("payment_doc") or payload
                    worker_doc = payload.get("worker_doc")
                    bank_doc = payload.get("bank_acc_doc")
                    res = sync_wage_payment_to_supabase(pay_doc, worker_doc=worker_doc, bank_acc_doc=bank_doc)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for wage payment sync.")

                # 7. INVESTOR ADVANCES & REPAYMENTS
                elif event_type == "investor_advance_created":
                    adv_doc = payload.get("advance_doc") or payload
                    inv_doc = payload.get("investor_doc")
                    mode = payload.get("payment_mode", "BANK_TRANSFER")
                    res = sync_investor_advance_to_supabase(adv_doc, investor_doc=inv_doc, payment_mode=mode)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for investor advance sync.")
                elif event_type == "investor_repayment_created":
                    rep_doc = payload.get("repayment_doc") or payload
                    inv_doc = payload.get("investor_doc")
                    is_reinv = bool(payload.get("is_reinvestment", False))
                    mode = payload.get("payment_mode", "BANK_TRANSFER")
                    res = sync_investor_repayment_to_supabase(rep_doc, investor_doc=inv_doc, is_reinvestment=is_reinv, payment_mode=mode)
                    if not res:
                        raise RuntimeError("Supabase returned no confirmation for investor repayment sync.")

                else:
                    log.warning(f"Unknown outbox event type: {event_type}")
                    
                success = True
            except Exception as e:
                error_msg = str(e)
                log.error(f"Error processing outbox event {event_id}: {error_msg}")
                log.debug(traceback.format_exc())

            if success:
                await db.outbox_events.update_one(
                    {"_id": event_id},
                    {"$set": {
                        "status": "processed",
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            else:
                retries = event.get("retries", 0) + 1
                is_connection_error = any(term in str(error_msg).lower() for term in ["connect", "refused", "10061", "timeout", "unavailable", "no confirmation"])
                max_retries = 50 if is_connection_error else 5
                new_status = "failed" if retries >= max_retries else "pending"
                await db.outbox_events.update_one(
                    {"_id": event_id},
                    {"$set": {
                        "status": new_status,
                        "error": error_msg,
                        "retries": retries,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                if is_connection_error and new_status == "pending":
                    await asyncio.sleep(5)
                if new_status == "failed":
                    # Optionally record in supabase_sync_failures for manual review
                    try:
                        from services.supabase_sync_failure_service import record_supabase_sync_failure
                        await record_supabase_sync_failure(db, event.get("collection", "unknown"), str(event.get("doc_id")), error_msg)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            log.info("Outbox processor worker cancelled.")
            break
        except Exception as e:
            log.error(f"Outbox processor encountered a fatal error: {e}")
            await asyncio.sleep(10)

def start_outbox_processor(db: Any):
    asyncio.create_task(process_outbox_events(db))
