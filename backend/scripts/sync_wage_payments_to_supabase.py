"""Backfill and sync all MongoDB wage payments to Supabase financial ledger.

Usage:
    python backend/scripts/sync_wage_payments_to_supabase.py --dry-run
    python backend/scripts/sync_wage_payments_to_supabase.py --execute
"""

import os
import sys
import argparse
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.supabase_client import get_supabase_admin_client
from services.supabase_payroll_service import sync_wage_payment_to_supabase

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "ssk_footwear_erp")


async def sync_all_wage_payments(dry_run: bool = False):
    supabase = get_supabase_admin_client()
    if not supabase:
        print("[ERROR] Supabase client could not be initialized. Please check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return

    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client[DB_NAME]

    print(f"[*] Connected to MongoDB: {DB_NAME}")
    total_count = await db.wage_payments.count_documents({})
    print(f"[*] Found {total_count} wage payments in MongoDB.")

    if total_count == 0:
        print("[INFO] No wage payments found to sync.")
        return

    synced = 0
    failed = 0

    cursor = db.wage_payments.find({}).sort("date", 1)
    async for wp in cursor:
        wid = wp.get("worker_id")
        worker = None
        if wid:
            try:
                worker = await db.workers.find_one({"_id": ObjectId(wid)})
            except Exception:
                try:
                    worker = await db.workers.find_one({"_id": str(wid)})
                except Exception:
                    pass

        bank_doc = None
        bid = wp.get("bank_account_id")
        if bid:
            try:
                bank_doc = await db.bank_accounts.find_one({"_id": ObjectId(bid)})
            except Exception:
                try:
                    bank_doc = await db.bank_accounts.find_one({"_id": str(bid)})
                except Exception:
                    pass

        worker_name = wp.get("worker_name") or (worker.get("name") if worker else "Unknown Worker")
        amount = wp.get("amount", 0.0)
        date = wp.get("date")
        wp_id = str(wp.get("_id"))

        if dry_run:
            print(f"  [DRY RUN] Would sync: Payment {wp_id[:8]} | ₹{amount} to {worker_name} ({date}) via {wp.get('paid_via')}")
            synced += 1
            continue

        try:
            res = sync_wage_payment_to_supabase(wp, worker_doc=worker, bank_acc_doc=bank_doc)
            if res:
                synced += 1
                print(f"  [OK] Synced: Payment {wp_id[:8]} | ₹{amount} to {worker_name} ({date}) -> Supabase JE & Voucher")
            else:
                failed += 1
                print(f"  [WARN] Failed to sync payment {wp_id}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] Error syncing payment {wp_id}: {e}")

    print(f"\n[SUMMARY] Finished! Total: {total_count}, Synced: {synced}, Failed: {failed}")


def main():
    parser = argparse.ArgumentParser(description="Sync MongoDB Wage Payments to Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Preview wage payments without writing to Supabase")
    parser.add_argument("--execute", action="store_true", help="Execute sync to Supabase")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        return

    asyncio.run(sync_all_wage_payments(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
