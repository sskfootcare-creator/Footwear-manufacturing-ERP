"""Backfill Expense records for historical bank_transfer / upi wage payments.

Usage:
    # Dry run (scan and report candidates only):
    python backfill_wage_payment_expenses.py

    # Apply backfill (create retroactive expense records and link them):
    python backfill_wage_payment_expenses.py --apply
"""

import sys
import os
import argparse
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ssk_footwear_erp")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_backfill_candidates(db):
    query = {
        "paid_via": {"$in": ["bank_transfer", "upi"]},
        "$or": [
            {"linked_expense_id": {"$exists": False}},
            {"linked_expense_id": None},
            {"linked_expense_id": ""},
        ]
    }
    cursor = db.wage_payments.find(query).sort("date", 1)
    return await cursor.to_list(5000)


async def run_backfill(apply: bool = False):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    candidates = await get_backfill_candidates(db)
    count = len(candidates)
    total_value = sum(float(c.get("amount") or 0.0) for c in candidates)

    print("=" * 70)
    print(f"DATABASE: {DB_NAME} on {MONGO_URL}")
    print(f"UNLINKED BANK / UPI WAGE PAYMENTS: {count}")
    print(f"TOTAL AMOUNT TO BACKFILL: INR {total_value:,.2f}")
    print("=" * 70)

    if count == 0:
        print("No historical wage payments require expense backfill.")
        return

    print("\nCandidates Found:")
    for idx, c in enumerate(candidates, start=1):
        wid = str(c.get("_id"))
        wname = c.get("worker_name", "Unknown")
        amt = float(c.get("amount") or 0.0)
        dt = c.get("date", "Unknown")
        via = c.get("paid_via")
        b_acc = c.get("bank_account_id") or "None"
        p_from = c.get("period_from", "")
        p_to = c.get("period_to", "")
        upi = c.get("upi_reference")
        print(f"  [{idx}] ID: {wid} | Worker: {wname:<18} | INR {amt:>9.2f} | Date: {dt} | Via: {via:<13} | Bank Acc: {b_acc} | Period: {p_from} to {p_to} {f'(UPI: {upi})' if upi else ''}")

    if not apply:
        print("\n[DRY RUN MODE] No changes were made.")
        print("To execute backfill and create linked expenses, run with --apply flag.")
        return

    print("\nApplying backfill...")
    created_count = 0
    for c in candidates:
        wp_id = c["_id"]
        wp_id_str = str(wp_id)
        worker_name = c.get("worker_name") or "Worker"
        period_from = c.get("period_from", "")
        period_to = c.get("period_to", "")
        notes = f"Wage payment to {worker_name} for {period_from}-{period_to}"
        if c.get("paid_via") == "upi" and c.get("upi_reference"):
            notes += f" (UPI Ref: {str(c['upi_reference']).strip()})"
        if c.get("notes"):
            notes += f" - {str(c['notes']).strip()}"

        expense_doc = {
            "category": "wages",
            "amount": round(float(c.get("amount") or 0.0), 2),
            "date": c.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "payee": worker_name,
            "notes": notes,
            "receipt": None,
            "paid_via": "bank",
            "cash_ledger_id": None,
            "bank_account_id": str(c.get("bank_account_id")) if c.get("bank_account_id") else None,
            "is_recurring": False,
            "recurring_expense_id": "",
            "status": "confirmed",
            "linked_wage_payment_id": wp_id_str,
            "created_at": now_iso(),
            "created_by": "system_backfill",
        }

        res = await db.expenses.insert_one(expense_doc)
        exp_id_str = str(res.inserted_id)

        await db.wage_payments.update_one(
            {"_id": wp_id},
            {"$set": {"linked_expense_id": exp_id_str}}
        )
        created_count += 1

    print(f"Successfully backfilled {created_count} expense records.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing expense records for historical wage payments.")
    parser.add_argument("--apply", action="store_true", help="Execute backfill against the database")
    args = parser.parse_args()

    asyncio.run(run_backfill(apply=args.apply))
