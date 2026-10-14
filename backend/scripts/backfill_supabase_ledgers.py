"""Ledger backfill and reconciliation script to sync existing MongoDB financial documents to Supabase.

Handles 8 streams:
1. Invoices -> sync_direct_invoice_to_supabase (sales_invoices, AR journal entries)
2. Customer Payments -> sync_invoice_payment_to_supabase (payment_vouchers [RECEIPT], voucher_allocations)
3. Vendor Purchase Orders -> sync_vendor_po_to_supabase (vendor_bills, AP journal entries)
4. Vendor Payments -> sync_vendor_payment_to_supabase (payment_vouchers [PAYMENT], voucher_allocations)
5. Operating & Overhead Expenses -> sync_expense_to_supabase (journal_entries, payment_vouchers [PAYMENT])
6. Worker Wage Disbursements -> sync_wage_payment_to_supabase (payment_vouchers [PAYMENT], payroll JEs)
7. Investor Advances -> sync_investor_advance_to_supabase (journal_entries [RECEIPT])
8. Investor Repayments -> sync_investor_repayment_to_supabase (journal_entries [PAYMENT])

Usage:
    # Dry run (Default: scans and counts all documents, prints preview, makes NO writes)
    python scripts/backfill_supabase_ledgers.py
    python scripts/backfill_supabase_ledgers.py --dry-run

    # Queue un-synced events into MongoDB outbox_events for background processing
    python scripts/backfill_supabase_ledgers.py --queue-outbox

    # Live execution (Push directly to live Supabase)
    python scripts/backfill_supabase_ledgers.py --execute
"""

import os
import sys
import json
import argparse
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId, json_util
from dotenv import load_dotenv

# Ensure backend root is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "ssk_footwear_erp")


def parse_oid(val: Any) -> Optional[ObjectId]:
    if not val:
        return None
    try:
        return ObjectId(str(val))
    except Exception:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def fetch_vendor(db, vendor_id: Any) -> Optional[Dict[str, Any]]:
    if not vendor_id:
        return None
    oid = parse_oid(vendor_id)
    if oid:
        v = await db.vendors.find_one({"_id": oid})
        if v:
            return v
    return await db.vendors.find_one({"_id": str(vendor_id)})


async def fetch_po(db, po_id: Any, po_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if po_id:
        oid = parse_oid(po_id)
        if oid:
            po = await db.vendor_purchase_orders.find_one({"_id": oid})
            if po:
                return po
        po = await db.vendor_purchase_orders.find_one({"_id": str(po_id)})
        if po:
            return po
        if "vendor_pos" in await db.list_collection_names():
            if oid:
                po = await db.vendor_pos.find_one({"_id": oid})
                if po:
                    return po
            po = await db.vendor_pos.find_one({"_id": str(po_id)})
            if po:
                return po

    if po_number:
        po = await db.vendor_purchase_orders.find_one({"po_number": po_number})
        if po:
            return po
        if "vendor_pos" in await db.list_collection_names():
            po = await db.vendor_pos.find_one({"po_number": po_number})
            if po:
                return po
    return None


async def run_backfill(execute: bool = False, queue_outbox: bool = False, category: str = "all", limit: Optional[int] = None):
    mode_label = "LIVE SUPABASE" if execute else ("QUEUE OUTBOX" if queue_outbox else "DRY RUN (READ-ONLY)")
    print("=" * 80)
    print(f" SSK FOOTWEAR ERP — RELATIONAL FINANCIAL LEDGER AUDIT & BACKFILL [{mode_label}]")
    print(f" Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    # Initialize Supabase client if executing directly
    if execute:
        from db.supabase_client import get_supabase_admin_client
        supabase_client = get_supabase_admin_client()
        if not supabase_client:
            print("[ERROR] Cannot proceed in execute mode: Supabase admin client is unavailable.")
            print("        Please ensure Supabase is running and SUPABASE_URL / keys are set.")
            return

    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client[DB_NAME]
    print(f"[*] Connected to MongoDB: {DB_NAME} at {MONGO_URL}")

    # Import sync services
    from services.supabase_invoice_service import (
        sync_direct_invoice_to_supabase,
        sync_invoice_payment_to_supabase,
    )
    from services.supabase_vendor_bill_service import (
        sync_vendor_po_to_supabase,
        sync_vendor_payment_to_supabase,
    )
    from services.supabase_expense_service import sync_expense_to_supabase
    from services.supabase_payroll_service import sync_wage_payment_to_supabase
    from services.supabase_investor_service import (
        sync_investor_advance_to_supabase,
        sync_investor_repayment_to_supabase,
    )
    from services.supabase_sync_failure_service import record_supabase_sync_failure

    stats = {
        "invoices": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "customer_payments": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "vendor_pos": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "vendor_payments": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "expenses": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "wage_payments": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "investor_advances": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "investor_repayments": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
    }

    # ---------------------------------------------------------
    # 1. SALES INVOICES
    # ---------------------------------------------------------
    if category in ("all", "invoices"):
        print("\n" + "-" * 80)
        print(" [STREAM 1/8] SALES INVOICES (Direct Invoices -> sales_invoices + AR Ledger)")
        print("-" * 80)
        invoices = await db.invoices.find({}).sort("created_at", 1).to_list(limit)
        stats["invoices"]["total"] = len(invoices)
        print(f"Found {len(invoices)} total invoice documents in MongoDB.")

        for idx, inv in enumerate(invoices, 1):
            inv_id = str(inv.get("_id"))
            inv_no = inv.get("invoice_no") or f"INV-INDEX-{idx}"
            client_name = inv.get("client_name") or "Unknown Client"
            grand_total = round(float(inv.get("grand_total") or inv.get("total_amount") or 0.0), 2)

            if grand_total <= 0:
                print(f"  [{idx:02d}] SKIP: {inv_no} ({client_name}) - Grand Total is INR {grand_total} (<= 0)")
                stats["invoices"]["skipped"] += 1
                continue

            stats["invoices"]["processed"] += 1
            if queue_outbox:
                clean_inv = json.loads(json_util.dumps(inv))
                await db.outbox_events.update_one(
                    {"collection": "invoices", "doc_id": inv_id},
                    {"$setOnInsert": {
                        "type": "invoice_created",
                        "collection": "invoices",
                        "doc_id": inv_id,
                        "payload": clean_inv,
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Invoice {inv_no} into outbox_events")
                stats["invoices"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync invoice {inv_no} | INR {grand_total:,.2f} | Client: {client_name}")
                stats["invoices"]["success"] += 1
            else:
                try:
                    res = sync_direct_invoice_to_supabase(inv)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced invoice {inv_no} | INR {grand_total:,.2f}")
                        stats["invoices"]["success"] += 1
                    else:
                        raise RuntimeError(f"Sync returned None for invoice {inv_no}")
                except Exception as e:
                    print(f"  [{idx:02d}] FAIL: Error syncing invoice {inv_no}: {e}")
                    stats["invoices"]["failed"] += 1
                    await record_supabase_sync_failure(db, "invoices", inv_id, str(e))

    # ---------------------------------------------------------
    # 2. CUSTOMER PAYMENT RECEIPTS
    # ---------------------------------------------------------
    if category in ("all", "customer_payments"):
        print("\n" + "-" * 80)
        print(" [STREAM 2/8] CUSTOMER PAYMENTS (Receipts -> payment_vouchers + Allocations)")
        print("-" * 80)
        all_payments = await db.payments.find({}).sort("created_at", 1).to_list(None)
        cust_payments = [
            p for p in all_payments 
            if not p.get("vendor_id") and p.get("type") != "vendor_payment"
        ]
        if limit:
            cust_payments = cust_payments[:limit]
        stats["customer_payments"]["total"] = len(cust_payments)
        print(f"Found {len(cust_payments)} customer payment receipts in MongoDB.")

        for idx, pay in enumerate(cust_payments, 1):
            pay_id = str(pay.get("_id"))
            pay_no = pay.get("payment_no") or f"PAY-INDEX-{idx}"
            amount = round(float(pay.get("amount") or 0.0), 2)
            client_name = pay.get("client_name") or "Unknown Client"
            mode = pay.get("mode") or "Bank Transfer"
            inv_ids = pay.get("invoice_ids") or []

            matched_invoices = []
            if inv_ids:
                oids = [parse_oid(i) for i in inv_ids if parse_oid(i)]
                str_ids = [str(i) for i in inv_ids]
                cur = db.invoices.find({"$or": [{"_id": {"$in": oids}}, {"_id": {"$in": str_ids}}]})
                matched_invoices = await cur.to_list(100)

            stats["customer_payments"]["processed"] += 1
            if queue_outbox:
                clean_pay = json.loads(json_util.dumps(pay))
                clean_invs = [json.loads(json_util.dumps(i)) for i in matched_invoices]
                await db.outbox_events.update_one(
                    {"collection": "payments", "doc_id": pay_id},
                    {"$setOnInsert": {
                        "type": "payment_received",
                        "collection": "payments",
                        "doc_id": pay_id,
                        "payload": {"payment_doc": clean_pay, "invoice_docs": clean_invs},
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Customer receipt {pay_no} into outbox_events")
                stats["customer_payments"]["success"] += 1
            elif not execute:
                inv_refs = ", ".join(i.get("invoice_no") or str(i.get("_id"))[:8] for i in matched_invoices) or "(No linked invoices)"
                print(f"  [{idx:02d}] DRY RUN: Would sync receipt {pay_no} | INR {amount:,.2f} via {mode} -> Linked: {inv_refs}")
                stats["customer_payments"]["success"] += 1
            else:
                try:
                    res = sync_invoice_payment_to_supabase(pay, matched_invoices)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced payment receipt {pay_no} | INR {amount:,.2f}")
                        stats["customer_payments"]["success"] += 1
                    else:
                        raise RuntimeError(f"Sync returned None for customer payment {pay_no}")
                except Exception as e:
                    print(f"  [{idx:02d}] FAIL: Error syncing customer payment {pay_no}: {e}")
                    stats["customer_payments"]["failed"] += 1
                    await record_supabase_sync_failure(db, "payments", pay_id, str(e))

    # ---------------------------------------------------------
    # 3. VENDOR PURCHASE ORDERS / BILLS
    # ---------------------------------------------------------
    if category in ("all", "vendor_pos"):
        print("\n" + "-" * 80)
        print(" [STREAM 3/8] VENDOR PURCHASE ORDERS (PO/GRN -> vendor_bills + AP Ledger)")
        print("-" * 80)
        vpos = await db.vendor_purchase_orders.find({}).sort("created_at", 1).to_list(limit)
        if "vendor_pos" in await db.list_collection_names():
            legacy_vpos = await db.vendor_pos.find({}).sort("created_at", 1).to_list(limit)
            existing_ids = {str(v["_id"]) for v in vpos}
            for lv in legacy_vpos:
                if str(lv["_id"]) not in existing_ids:
                    vpos.append(lv)

        stats["vendor_pos"]["total"] = len(vpos)
        print(f"Found {len(vpos)} vendor purchase orders in MongoDB.")

        for idx, po in enumerate(vpos, 1):
            po_id = str(po.get("_id"))
            po_number = po.get("po_number") or f"VPO-INDEX-{idx}"
            vendor_id = po.get("vendor_id")
            vendor_doc = await fetch_vendor(db, vendor_id)
            vendor_name = (vendor_doc.get("name") if vendor_doc else None) or po.get("vendor_name") or "Unknown Vendor"

            total_amt = round(float(po.get("total_amount") or po.get("grand_total") or 0.0), 2)
            line_items = po.get("line_items") or []
            if total_amt <= 0 and line_items:
                total_amt = round(sum(float(li.get("amount") or (float(li.get("quantity", 0)) * float(li.get("rate", 0)))) for li in line_items), 2)

            if total_amt <= 0:
                print(f"  [{idx:02d}] SKIP: {po_number} ({vendor_name}) - Total amount is INR {total_amt} (<= 0)")
                stats["vendor_pos"]["skipped"] += 1
                continue

            stats["vendor_pos"]["processed"] += 1
            if queue_outbox:
                clean_po = json.loads(json_util.dumps(po))
                clean_v = json.loads(json_util.dumps(vendor_doc)) if vendor_doc else None
                await db.outbox_events.update_one(
                    {"collection": "vendor_purchase_orders", "doc_id": po_id},
                    {"$setOnInsert": {
                        "type": "vendor_bill_created",
                        "collection": "vendor_purchase_orders",
                        "doc_id": po_id,
                        "payload": {"po_doc": clean_po, "vendor_doc": clean_v},
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Vendor bill {po_number} into outbox_events")
                stats["vendor_pos"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync vendor bill {po_number} | INR {total_amt:,.2f} | Vendor: {vendor_name}")
                stats["vendor_pos"]["success"] += 1
            else:
                try:
                    res = sync_vendor_po_to_supabase(po, vendor_doc=vendor_doc)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced vendor bill {po_number} | INR {total_amt:,.2f}")
                        stats["vendor_pos"]["success"] += 1
                    else:
                        raise RuntimeError(f"Sync returned None for vendor PO {po_number}")
                except Exception as e:
                    print(f"  [{idx:02d}] FAIL: Error syncing vendor PO {po_number}: {e}")
                    stats["vendor_pos"]["failed"] += 1
                    await record_supabase_sync_failure(db, "vendor_purchase_orders", po_id, str(e))

    # ---------------------------------------------------------
    # 4. VENDOR PAYMENTS
    # ---------------------------------------------------------
    if category in ("all", "vendor_payments"):
        print("\n" + "-" * 80)
        print(" [STREAM 4/8] VENDOR PAYMENTS (Vouchers -> payment_vouchers + Bill Allocations)")
        print("-" * 80)
        all_payments = await db.payments.find({}).sort("created_at", 1).to_list(None)
        vend_payments = [
            p for p in all_payments 
            if p.get("vendor_id") or p.get("type") == "vendor_payment"
        ]
        if limit:
            vend_payments = vend_payments[:limit]
        stats["vendor_payments"]["total"] = len(vend_payments)
        print(f"Found {len(vend_payments)} vendor payments in MongoDB.")

        for idx, pay in enumerate(vend_payments, 1):
            pay_id = str(pay.get("_id"))
            pay_no = pay.get("payment_no") or f"VPAY-INDEX-{idx}"
            amount = round(float(pay.get("amount") or 0.0), 2)
            vendor_id = pay.get("vendor_id")
            vendor_doc = await fetch_vendor(db, vendor_id)
            vendor_name = (vendor_doc.get("name") if vendor_doc else None) or pay.get("vendor_name") or "Unknown Vendor"
            mode = pay.get("mode") or "Bank Transfer"
            po_doc = await fetch_po(db, pay.get("vendor_po_id"), pay.get("vendor_po_number"))

            stats["vendor_payments"]["processed"] += 1
            if queue_outbox:
                clean_pay = json.loads(json_util.dumps(pay))
                clean_v = json.loads(json_util.dumps(vendor_doc)) if vendor_doc else None
                clean_po_list = [json.loads(json_util.dumps(po_doc))] if po_doc else None
                await db.outbox_events.update_one(
                    {"collection": "payments", "doc_id": pay_id},
                    {"$setOnInsert": {
                        "type": "vendor_payment_created",
                        "collection": "payments",
                        "doc_id": pay_id,
                        "payload": {"payment_doc": clean_pay, "vendor_doc": clean_v, "po_docs": clean_po_list},
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Vendor payment {pay_no} into outbox_events")
                stats["vendor_payments"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync vendor payment {pay_no} | INR {amount:,.2f} via {mode} | Vendor: {vendor_name}")
                stats["vendor_payments"]["success"] += 1
            else:
                try:
                    res = sync_vendor_payment_to_supabase(pay, vendor_doc=vendor_doc, po_docs=[po_doc] if po_doc else None)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced vendor payment {pay_no} | INR {amount:,.2f}")
                        stats["vendor_payments"]["success"] += 1
                    else:
                        raise RuntimeError(f"Sync returned None for vendor payment {pay_no}")
                except Exception as e:
                    print(f"  [{idx:02d}] FAIL: Error syncing vendor payment {pay_no}: {e}")
                    stats["vendor_payments"]["failed"] += 1
                    await record_supabase_sync_failure(db, "payments", pay_id, str(e))

    # ---------------------------------------------------------
    # 5. FACTORY & OFFICE EXPENSES
    # ---------------------------------------------------------
    if category in ("all", "expenses"):
        print("\n" + "-" * 80)
        print(" [STREAM 5/8] OPERATING & OVERHEAD EXPENSES (expenses -> JEs + payment_vouchers)")
        print("-" * 80)
        exp_docs = await db.expenses.find({"status": {"$nin": ["due", "overdue"]}}).sort("date", 1).to_list(limit)
        stats["expenses"]["total"] = len(exp_docs)
        print(f"Found {len(exp_docs)} confirmed expenses in MongoDB.")

        for idx, exp in enumerate(exp_docs, 1):
            exp_id = str(exp.get("_id"))
            amt = round(float(exp.get("amount") or 0.0), 2)
            cat = exp.get("category") or "Other"
            payee = exp.get("payee") or "Payee"

            if amt <= 0:
                stats["expenses"]["skipped"] += 1
                continue

            stats["expenses"]["processed"] += 1
            if queue_outbox:
                clean_exp = json.loads(json_util.dumps(exp))
                await db.outbox_events.update_one(
                    {"collection": "expenses", "doc_id": exp_id},
                    {"$setOnInsert": {
                        "type": "expense_created",
                        "collection": "expenses",
                        "doc_id": exp_id,
                        "payload": clean_exp,
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Expense {cat} (₹{amt}) into outbox_events")
                stats["expenses"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync expense {cat} | INR {amt:,.2f} | Payee: {payee}")
                stats["expenses"]["success"] += 1
            else:
                try:
                    res = sync_expense_to_supabase(exp)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced expense {cat} | INR {amt:,.2f}")
                        stats["expenses"]["success"] += 1
                    else:
                        raise RuntimeError(f"Sync returned None for expense {exp_id}")
                except Exception as e:
                    print(f"  [{idx:02d}] FAIL: Error syncing expense {exp_id}: {e}")
                    stats["expenses"]["failed"] += 1

    # ---------------------------------------------------------
    # 6. WORKER WAGE DISBURSEMENTS
    # ---------------------------------------------------------
    if category in ("all", "wage_payments"):
        print("\n" + "-" * 80)
        print(" [STREAM 6/8] WORKER WAGE DISBURSEMENTS (wage_payments -> payroll JEs + vouchers)")
        print("-" * 80)
        wage_docs = await db.wage_payments.find({}).sort("date", 1).to_list(limit)
        stats["wage_payments"]["total"] = len(wage_docs)
        print(f"Found {len(wage_docs)} wage disbursements in MongoDB.")

        for idx, wpay in enumerate(wage_docs, 1):
            w_id = str(wpay.get("_id"))
            amt = round(float(wpay.get("amount") or 0.0), 2)
            w_name = wpay.get("worker_name") or "Karigar"

            stats["wage_payments"]["processed"] += 1
            if queue_outbox:
                clean_w = json.loads(json_util.dumps(wpay))
                await db.outbox_events.update_one(
                    {"collection": "wage_payments", "doc_id": w_id},
                    {"$setOnInsert": {
                        "type": "wage_payment_created",
                        "collection": "wage_payments",
                        "doc_id": w_id,
                        "payload": {"payment_doc": clean_w},
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Wage disbursement to {w_name} (₹{amt}) into outbox_events")
                stats["wage_payments"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync wage disbursement to {w_name} | INR {amt:,.2f}")
                stats["wage_payments"]["success"] += 1
            else:
                try:
                    res = sync_wage_payment_to_supabase(wpay)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced wage disbursement to {w_name} | INR {amt:,.2f}")
                        stats["wage_payments"]["success"] += 1
                except Exception as e:
                    stats["wage_payments"]["failed"] += 1

    # ---------------------------------------------------------
    # 7. INVESTOR ADVANCES
    # ---------------------------------------------------------
    if category in ("all", "investor_advances"):
        print("\n" + "-" * 80)
        print(" [STREAM 7/8] INVESTOR ADVANCES (investor_advances -> JEs [RECEIPT])")
        print("-" * 80)
        adv_docs = await db.investor_advances.find({}).sort("advance_date", 1).to_list(limit)
        stats["investor_advances"]["total"] = len(adv_docs)
        print(f"Found {len(adv_docs)} investor advances in MongoDB.")

        for idx, adv in enumerate(adv_docs, 1):
            adv_id = str(adv.get("_id"))
            amt = round(float(adv.get("amount") or 0.0), 2)
            inv_name = adv.get("investor_name") or "Investor"
            po_num = adv.get("po_number") or ""

            stats["investor_advances"]["processed"] += 1
            if queue_outbox:
                clean_adv = json.loads(json_util.dumps(adv))
                await db.outbox_events.update_one(
                    {"collection": "investor_advances", "doc_id": adv_id},
                    {"$setOnInsert": {
                        "type": "investor_advance_created",
                        "collection": "investor_advances",
                        "doc_id": adv_id,
                        "payload": {"advance_doc": clean_adv},
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Investor advance from {inv_name} (₹{amt}) into outbox_events")
                stats["investor_advances"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync investor advance from {inv_name} | INR {amt:,.2f} for PO {po_num}")
                stats["investor_advances"]["success"] += 1
            else:
                try:
                    res = sync_investor_advance_to_supabase(adv)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced investor advance from {inv_name} | INR {amt:,.2f}")
                        stats["investor_advances"]["success"] += 1
                except Exception as e:
                    stats["investor_advances"]["failed"] += 1

    # ---------------------------------------------------------
    # 8. INVESTOR REPAYMENTS
    # ---------------------------------------------------------
    if category in ("all", "investor_repayments"):
        print("\n" + "-" * 80)
        print(" [STREAM 8/8] INVESTOR REPAYMENTS (investor_repayments -> JEs [PAYMENT])")
        print("-" * 80)
        rep_docs = await db.investor_repayments.find({}).sort("payout_date", 1).to_list(limit)
        stats["investor_repayments"]["total"] = len(rep_docs)
        print(f"Found {len(rep_docs)} investor repayments in MongoDB.")

        for idx, rep in enumerate(rep_docs, 1):
            rep_id = str(rep.get("_id"))
            p_amt = round(float(rep.get("principal_amount") or 0.0), 2)
            m_amt = round(float(rep.get("margin_amount") or 0.0), 2)
            inv_name = rep.get("investor_name") or "Investor"

            stats["investor_repayments"]["processed"] += 1
            if queue_outbox:
                clean_rep = json.loads(json_util.dumps(rep))
                await db.outbox_events.update_one(
                    {"collection": "investor_repayments", "doc_id": rep_id},
                    {"$setOnInsert": {
                        "type": "investor_repayment_created",
                        "collection": "investor_repayments",
                        "doc_id": rep_id,
                        "payload": {"repayment_doc": clean_rep},
                        "status": "pending",
                        "retries": 0,
                        "created_at": now_iso(),
                        "updated_at": now_iso()
                    }},
                    upsert=True
                )
                print(f"  [{idx:02d}] QUEUED: Investor repayment to {inv_name} (₹{p_amt + m_amt}) into outbox_events")
                stats["investor_repayments"]["success"] += 1
            elif not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync investor repayment to {inv_name} | Principal: {p_amt:,.2f}, Margin: {m_amt:,.2f}")
                stats["investor_repayments"]["success"] += 1
            else:
                try:
                    res = sync_investor_repayment_to_supabase(rep)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced investor repayment to {inv_name}")
                        stats["investor_repayments"]["success"] += 1
                except Exception as e:
                    stats["investor_repayments"]["failed"] += 1

    # ---------------------------------------------------------
    # SUMMARY REPORT
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print(f" BACKFILL SUMMARY [{mode_label}]")
    print("=" * 80)
    print(f"{'STREAM':<26} | {'TOTAL':<8} | {'PROCESSED':<10} | {'SKIPPED':<8} | {'OK/WOULD':<9} | {'FAILED':<6}")
    print("-" * 80)
    for cat_name, s in stats.items():
        print(f"{cat_name:<26} | {s['total']:<8} | {s['processed']:<10} | {s['skipped']:<8} | {s['success']:<9} | {s['failed']:<6}")
    print("=" * 80)
    if queue_outbox:
        print("\n[*] Outbox queuing completed. Events are ready in MongoDB 'outbox_events'.")
        print("[*] As soon as Supabase is running, the background outbox worker will push all events to Supabase ledgers.\n")
    elif not execute:
        print("\n[*] Dry run completed. No writes were committed to Supabase or MongoDB.")
        print("[*] To queue events in MongoDB outbox for background sync, run:")
        print("    python scripts/backfill_supabase_ledgers.py --queue-outbox")
        print("[*] To execute directly against live Supabase, run:")
        print("    python scripts/backfill_supabase_ledgers.py --execute\n")
    else:
        print("\n[*] Live backfill completed.")


def main():
    parser = argparse.ArgumentParser(description="SSK ERP: Relational Financial Ledger Backfill & Reconciliation")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Scan and count documents without writing")
    parser.add_argument("--queue-outbox", action="store_true", default=False, help="Queue un-synced events into MongoDB outbox_events")
    parser.add_argument("--execute", action="store_true", default=False, help="Execute direct sync against Supabase")
    parser.add_argument("--category", choices=[
        "all", "invoices", "customer_payments", "vendor_pos", "vendor_payments",
        "expenses", "wage_payments", "investor_advances", "investor_repayments"
    ], default="all")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents per stream")
    args = parser.parse_args()

    asyncio.run(run_backfill(execute=args.execute, queue_outbox=args.queue_outbox, category=args.category, limit=args.limit))


if __name__ == "__main__":
    main()
