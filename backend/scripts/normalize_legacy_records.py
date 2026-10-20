"""Legacy Database Normalization & Deduplication Utility (P2-002).

Performs collection-level deduplication and normalization for legacy ERP records:
1. `sku_map`: Normalizes external SKU keys using canonical normalization rules and flags ambiguous collisions.
2. `online_orders`: Fills missing idempotency keys and quarantines legacy duplicates into `online_order_exceptions`.
3. `online_settlements`: Fills missing `settlement_row_key` and quarantines duplicates into `online_settlement_exceptions`.

Usage:
    python backend/scripts/normalize_legacy_records.py --dry-run
    python backend/scripts/normalize_legacy_records.py --apply
    python backend/scripts/normalize_legacy_records.py --apply --collection sku_map
"""

import sys
import os
import argparse
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motor.motor_asyncio import AsyncIOMotorClient
from routes.sku_map import canonical_sku_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("legacy_normalizer")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def normalize_sku_map(db, dry_run: bool = True) -> Dict[str, int]:
    logger.info("--- Normalizing 'sku_map' collection ---")
    cursor = db.sku_map.find({})
    scanned = 0
    updated = 0
    duplicates_found = 0
    seen_keys: Dict[str, Any] = {}

    async for doc in cursor:
        scanned += 1
        doc_id = doc["_id"]
        source_type = doc.get("source_type") or "online_channel"
        source_name = (doc.get("source_name") or "default").strip().lower()
        ext_sku = doc.get("external_sku") or doc.get("external_sku_key") or ""

        canon_key = canonical_sku_key(ext_sku)
        composite_key = f"{source_type}:{source_name}:{canon_key}"

        if composite_key in seen_keys:
            duplicates_found += 1
            logger.warning(f"[Duplicate SKU Map] ID={doc_id} matches existing ID={seen_keys[composite_key]['_id']} key={composite_key}")
            if not dry_run:
                await db.sku_map_review_queue.update_one(
                    {"source_type": source_type, "source_name": source_name, "external_sku_key": canon_key},
                    {"$setOnInsert": {
                        "source_type": source_type,
                        "source_name": source_name,
                        "external_sku": ext_sku,
                        "external_sku_key": canon_key,
                        "flagged_reason": "legacy_duplicate_sku_mapping",
                        "status": "pending_review",
                        "created_at": now_iso(),
                    }},
                    upsert=True,
                )
            continue

        seen_keys[composite_key] = doc

        # Check if doc needs field normalization
        curr_canon_field = doc.get("canonical_sku_key")
        if curr_canon_field != canon_key or doc.get("external_sku_key") != canon_key:
            updated += 1
            if not dry_run:
                await db.sku_map.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "canonical_sku_key": canon_key,
                        "external_sku_key": canon_key,
                        "normalized_at": now_iso(),
                    }}
                )

    logger.info(f"sku_map finished: scanned={scanned}, updated={updated}, duplicates_flagged={duplicates_found}")
    return {"scanned": scanned, "updated": updated, "duplicates": duplicates_found}


async def normalize_online_orders(db, dry_run: bool = True) -> Dict[str, int]:
    logger.info("--- Normalizing 'online_orders' collection ---")
    cursor = db.online_orders.find({})
    scanned = 0
    updated = 0
    duplicates_quarantined = 0
    seen_keys: Dict[str, Any] = {}

    async for doc in cursor:
        scanned += 1
        doc_id = doc["_id"]
        channel = str(doc.get("channel") or doc.get("source") or "unknown").strip().lower()
        order_id = str(doc.get("order_id") or doc.get("external_order_id") or "no_order").strip()
        order_date = str(doc.get("order_date") or doc.get("created_at") or "")[:10].strip()
        sku = str(doc.get("sku") or doc.get("leaf_sku") or "").strip()
        color = str(doc.get("color") or "").strip()
        size = str(doc.get("size") or "").strip()

        raw_key = f"{channel}:{order_id}:{order_date}:{sku}:{color}:{size}"
        canon_idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        if canon_idempotency_key in seen_keys:
            duplicates_quarantined += 1
            logger.warning(f"[Duplicate Online Order] ID={doc_id} key={canon_idempotency_key}")
            if not dry_run:
                await db.online_order_exceptions.insert_one({
                    "original_doc_id": str(doc_id),
                    "channel": channel,
                    "order_id": order_id,
                    "idempotency_key": canon_idempotency_key,
                    "reason": "legacy_duplicate_order_import",
                    "quarantined_at": now_iso(),
                })
            continue

        seen_keys[canon_idempotency_key] = doc

        if doc.get("idempotency_key") != canon_idempotency_key:
            updated += 1
            if not dry_run:
                await db.online_orders.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "idempotency_key": canon_idempotency_key,
                        "raw_import_hash": canon_idempotency_key,
                        "normalized_at": now_iso(),
                    }}
                )

    logger.info(f"online_orders finished: scanned={scanned}, updated={updated}, duplicates_quarantined={duplicates_quarantined}")
    return {"scanned": scanned, "updated": updated, "duplicates": duplicates_quarantined}


async def normalize_online_settlements(db, dry_run: bool = True) -> Dict[str, int]:
    logger.info("--- Normalizing 'online_settlements' collection ---")
    cursor = db.online_settlements.find({})
    scanned = 0
    updated = 0
    duplicates_quarantined = 0
    seen_keys: Dict[str, Any] = {}

    async for doc in cursor:
        scanned += 1
        doc_id = doc["_id"]
        platform = str(doc.get("platform") or "unknown").strip().lower()
        payment_id = str(doc.get("payment_id") or "").strip()
        order_ref = str(doc.get("order_ref") or "").strip()
        leaf_sku = str(doc.get("leaf_sku") or "").strip()
        s_date = str(doc.get("settlement_date") or "")[:10].strip()
        net = float(doc.get("net_payout", 0.0) or 0.0)

        raw_key = f"{platform}:{payment_id}:{order_ref}:{leaf_sku}:{s_date}:{net}"
        row_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        if row_key in seen_keys:
            duplicates_quarantined += 1
            logger.warning(f"[Duplicate Settlement] ID={doc_id} key={row_key}")
            if not dry_run:
                await db.online_settlement_exceptions.insert_one({
                    "original_doc_id": str(doc_id),
                    "platform": platform,
                    "order_ref": order_ref,
                    "settlement_row_key": row_key,
                    "reason": "legacy_duplicate_settlement_record",
                    "quarantined_at": now_iso(),
                })
            continue

        seen_keys[row_key] = doc

        if doc.get("settlement_row_key") != row_key:
            updated += 1
            if not dry_run:
                await db.online_settlements.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "settlement_row_key": row_key,
                        "raw_import_hash": row_key,
                        "processed_status": "processed",
                        "normalized_at": now_iso(),
                    }}
                )

    logger.info(f"online_settlements finished: scanned={scanned}, updated={updated}, duplicates_quarantined={duplicates_quarantined}")
    return {"scanned": scanned, "updated": updated, "duplicates": duplicates_quarantined}


async def main():
    parser = argparse.ArgumentParser(description="Legacy Database Normalization & Deduplication")
    parser.add_argument("--apply", action="store_true", help="Apply modifications to DB (defaults to dry-run preview)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run in dry-run mode (default)")
    parser.add_argument("--collection", choices=["sku_map", "online_orders", "online_settlements", "all"], default="all")
    parser.add_argument("--mongo-url", default=os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "ssk_footwear_erp"))
    args = parser.parse_args()

    dry_run = True if args.dry_run else (not args.apply)
    mode_str = "DRY-RUN (NO CHANGES WILL BE WRITTEN)" if dry_run else "LIVE EXECUTION (WRITING TO DB)"
    logger.info(f"Starting Legacy Normalization in mode: {mode_str}")

    client = AsyncIOMotorClient(args.mongo_url)
    db = client[args.db_name]

    try:
        await db.command("ping")
        logger.info(f"Connected successfully to MongoDB database '{args.db_name}'.")
    except Exception as e:
        logger.error(f"Cannot connect to MongoDB: {e}")
        sys.exit(1)

    results = {}
    if args.collection in ("sku_map", "all"):
        results["sku_map"] = await normalize_sku_map(db, dry_run=dry_run)
    if args.collection in ("online_orders", "all"):
        results["online_orders"] = await normalize_online_orders(db, dry_run=dry_run)
    if args.collection in ("online_settlements", "all"):
        results["online_settlements"] = await normalize_online_settlements(db, dry_run=dry_run)

    logger.info("=== SUMMARY RESULTS ===")
    for coll, stats in results.items():
        logger.info(f"Collection: {coll} => {stats}")

    client.close()
    logger.info("Normalization process completed.")


if __name__ == "__main__":
    asyncio.run(main())
