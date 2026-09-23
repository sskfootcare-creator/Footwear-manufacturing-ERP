"""One-off ledger backfill script to sync existing MongoDB financial documents to Supabase.

Handles 4 streams:
1. Invoices -> sync_direct_invoice_to_supabase (sales_invoices, AR journal entries)
2. Customer Payments -> sync_invoice_payment_to_supabase (payment_vouchers [RECEIPT], voucher_allocations)
3. Vendor Purchase Orders -> sync_vendor_po_to_supabase (vendor_bills, AP journal entries)
4. Vendor Payments -> sync_vendor_payment_to_supabase (payment_vouchers [PAYMENT], voucher_allocations)

Usage:
    # Dry run (Default: scans and counts all documents, prints preview, makes NO writes)
    python backend/scripts/backfill_supabase_ledgers.py
    python backend/scripts/backfill_supabase_ledgers.py --dry-run

    # Live execution (Only after counts are confirmed)
    python backend/scripts/backfill_supabase_ledgers.py --execute
"""

import os
import sys
import argparse
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
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
        # Fallback to legacy vendor_pos
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


async def run_backfill(execute: bool = False, category: str = "all", limit: Optional[int] = None):
    mode_label = "LIVE EXECUTION" if execute else "DRY RUN (READ-ONLY)"
    print("=" * 80)
    print(f" SSK FOOTWEAR ERP — SUPABASE LEDGER BACKFILL [{mode_label}]")
    print(f" Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    # Initialize Supabase client if executing
    supabase_client = None
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
    from services.supabase_sync_failure_service import record_supabase_sync_failure

    stats = {
        "invoices": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "customer_payments": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "vendor_pos": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
        "vendor_payments": {"total": 0, "processed": 0, "skipped": 0, "success": 0, "failed": 0},
    }

    # ---------------------------------------------------------
    # 1. SALES INVOICES
    # ---------------------------------------------------------
    if category in ("all", "invoices"):
        print("\n" + "-" * 80)
        print(" [STREAM 1/4] SALES INVOICES (Direct Invoices -> sales_invoices + AR Ledger)")
        print("-" * 80)
        inv_cursor = db.invoices.find({}).sort("created_at", 1)
        invoices = await inv_cursor.to_list(limit)
        stats["invoices"]["total"] = len(invoices)
        print(f"Found {len(invoices)} total invoice documents in MongoDB.")

        for idx, inv in enumerate(invoices, 1):
            inv_id = str(inv.get("_id"))
            inv_no = inv.get("invoice_no") or f"INV-INDEX-{idx}"
            client_name = inv.get("client_name") or "Unknown Client"
            grand_total = round(float(inv.get("grand_total") or inv.get("total_amount") or 0.0), 2)
            inv_date = inv.get("invoice_date") or inv.get("created_at") or "Unknown Date"

            if grand_total <= 0:
                print(f"  [{idx:02d}] SKIP: {inv_no} ({client_name}) - Grand Total is INR {grand_total} (<= 0)")
                stats["invoices"]["skipped"] += 1
                continue

            stats["invoices"]["processed"] += 1
            if not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync invoice {inv_no} | INR {grand_total:,.2f} | Client: {client_name} ({inv_date})")
                stats["invoices"]["success"] += 1
            else:
                try:
                    res = sync_direct_invoice_to_supabase(inv)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced invoice {inv_no} | INR {grand_total:,.2f} -> Supabase ID: {res.get('id')}")
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
        print(" [STREAM 2/4] CUSTOMER PAYMENTS (Receipts -> payment_vouchers + Allocations)")
        print("-" * 80)
        pay_cursor = db.payments.find({}).sort("created_at", 1)
        all_payments = await pay_cursor.to_list(None)
        
        # Filter customer payments: those WITHOUT vendor_id and NOT vendor_payment type
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

            # Look up related invoice docs
            matched_invoices = []
            if inv_ids:
                oids = [parse_oid(i) for i in inv_ids if parse_oid(i)]
                str_ids = [str(i) for i in inv_ids]
                cur = db.invoices.find({"$or": [{"_id": {"$in": oids}}, {"_id": {"$in": str_ids}}]})
                matched_invoices = await cur.to_list(100)

            # If no direct invoice match, attempt to resolve client master details
            if not matched_invoices and client_name:
                client_doc = await db.clients.find_one({"name": client_name})
                if client_doc:
                    pay["client_id"] = str(client_doc.get("_id"))
                    pay["client_gstin"] = client_doc.get("gstin") or ""
                    pay["billing_address"] = client_doc.get("billing_address") or client_doc.get("address") or ""

            stats["customer_payments"]["processed"] += 1
            if not execute:
                inv_refs = ", ".join(i.get("invoice_no") or str(i.get("_id"))[:8] for i in matched_invoices) or "(No linked invoices)"
                print(f"  [{idx:02d}] DRY RUN: Would sync receipt {pay_no} | INR {amount:,.2f} via {mode} | Client: {client_name} -> Linked: {inv_refs}")
                stats["customer_payments"]["success"] += 1
            else:
                try:
                    res = sync_invoice_payment_to_supabase(pay, matched_invoices)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced payment receipt {pay_no} | INR {amount:,.2f} -> Voucher ID: {res.get('id')}")
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
        print(" [STREAM 3/4] VENDOR PURCHASE ORDERS (PO/GRN -> vendor_bills + AP Ledger)")
        print("-" * 80)
        vpo_cursor = db.vendor_purchase_orders.find({}).sort("created_at", 1)
        vpos = await vpo_cursor.to_list(limit)
        
        # Check if legacy vendor_pos has extra docs
        if "vendor_pos" in await db.list_collection_names():
            legacy_cursor = db.vendor_pos.find({}).sort("created_at", 1)
            legacy_vpos = await legacy_cursor.to_list(limit)
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

            # Compute total if not direct
            total_amt = round(float(po.get("total_amount") or po.get("grand_total") or 0.0), 2)
            line_items = po.get("line_items") or []
            if total_amt <= 0 and line_items:
                total_amt = round(sum(float(li.get("amount") or (float(li.get("quantity", 0)) * float(li.get("rate", 0)))) for li in line_items), 2)

            if total_amt <= 0:
                print(f"  [{idx:02d}] SKIP: {po_number} ({vendor_name}) - Total amount is INR {total_amt} (<= 0)")
                stats["vendor_pos"]["skipped"] += 1
                continue

            stats["vendor_pos"]["processed"] += 1
            if not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync vendor bill {po_number} | INR {total_amt:,.2f} | Vendor: {vendor_name} ({len(line_items)} items)")
                stats["vendor_pos"]["success"] += 1
            else:
                try:
                    res = sync_vendor_po_to_supabase(po, vendor_doc=vendor_doc)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced vendor bill {po_number} | INR {total_amt:,.2f} -> Bill UUID: {res.get('id')}")
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
        print(" [STREAM 4/4] VENDOR PAYMENTS (Vouchers -> payment_vouchers + Bill Allocations)")
        print("-" * 80)
        pay_cursor = db.payments.find({}).sort("created_at", 1)
        all_payments = await pay_cursor.to_list(None)

        # Filter vendor payments: those WITH vendor_id OR vendor_payment type
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
            
            # Matched PO if specified
            po_doc = await fetch_po(db, pay.get("vendor_po_id"), pay.get("vendor_po_number"))
            po_ref = po_doc.get("po_number") if po_doc else (pay.get("vendor_po_number") or "(General on Account)")

            stats["vendor_payments"]["processed"] += 1
            if not execute:
                print(f"  [{idx:02d}] DRY RUN: Would sync vendor payment {pay_no} | INR {amount:,.2f} via {mode} | Vendor: {vendor_name} -> PO: {po_ref}")
                stats["vendor_payments"]["success"] += 1
            else:
                try:
                    res = sync_vendor_payment_to_supabase(pay, vendor_doc=vendor_doc, po_docs=[po_doc] if po_doc else None)
                    if res:
                        print(f"  [{idx:02d}] OK: Synced vendor payment {pay_no} | INR {amount:,.2f} -> Voucher ID: {res.get('id')}")
                        stats["vendor_payments"]["success"] += 1
                    else:
                        raise RuntimeError(f"Sync returned None for vendor payment {pay_no}")
                except Exception as e:
                    print(f"  [{idx:02d}] FAIL: Error syncing vendor payment {pay_no}: {e}")
                    stats["vendor_payments"]["failed"] += 1
                    await record_supabase_sync_failure(db, "payments", pay_id, str(e))

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
    if not execute:
        print("\n[*] Dry run completed. No writes were committed to Supabase or MongoDB.")
        print("[*] To execute the backfill against live Supabase, run with the --execute flag:")
        print("    python backend/scripts/backfill_supabase_ledgers.py --execute\n")
    else:
        print("\n[*] Live backfill completed.")


def main():
    parser = argparse.ArgumentParser(description="SSK ERP: Backfill Mongo Invoices, POs, and Payments to Supabase")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Scan and count documents without writing (default)")
    parser.add_argument("--execute", action="store_true", help="Execute sync against Supabase")
    parser.add_argument("--category", choices=["all", "invoices", "customer_payments", "vendor_pos", "vendor_payments"], default="all")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents per stream")
    args = parser.parse_args()

    execute = args.execute
    asyncio.run(run_backfill(execute=execute, category=args.category, limit=args.limit))


if __name__ == "__main__":
    main()
