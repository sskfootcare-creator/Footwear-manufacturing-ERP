"""Enterprise Database Backup, Restore, and Migration Rollback Policy Engine (P1-016).

Provides automated DB snapshotting, restore drills, backup integrity verification,
and schema migration rollback support.

Usage:
    python backend/db/backup_restore.py --backup [--dir /path/to/backups]
    python backend/db/backup_restore.py --verify <backup_directory>
    python backend/db/backup_restore.py --restore <backup_directory> [--drop]
    python backend/db/backup_restore.py --rollback-migration <version_id>
"""

import os
import sys
import json
import gzip
import hashlib
import asyncio
import argparse
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import json_util

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_restore")

CORE_COLLECTIONS = [
    "users",
    "styles",
    "materials",
    "pos",
    "production_jobs",
    "invoices",
    "dispatch_records",
    "warehouse_locations",
    "fg_location_inventory",
    "fg_stock_movements",
    "picklists",
    "online_orders",
    "online_settlements",
    "sku_map",
    "audit_logs",
    "schema_migrations",
    "settings",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


async def create_backup(
    db,
    output_dir: Optional[str] = None,
    collections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Creates a compressed, checksum-verified point-in-time snapshot of the database."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_dir = output_dir or os.path.join(os.getcwd(), "backups", f"snapshot_{ts}")
    os.makedirs(base_dir, exist_ok=True)

    colls = collections or CORE_COLLECTIONS
    manifest = {
        "version": "1.0",
        "created_at": now_iso(),
        "database": getattr(db, "name", "unknown"),
        "collections": {},
    }

    logger.info(f"Starting backup to directory: {base_dir}")

    for col_name in colls:
        try:
            coll = db[col_name]
            file_path = os.path.join(base_dir, f"{col_name}.json.gz")
            doc_count = 0

            with gzip.open(file_path, "wt", encoding="utf-8") as gz:
                async for doc in coll.find({}):
                    gz.write(json_util.dumps(doc) + "\n")
                    doc_count += 1

            file_hash = sha256_file(file_path)
            file_size = os.path.getsize(file_path)

            manifest["collections"][col_name] = {
                "file": f"{col_name}.json.gz",
                "count": doc_count,
                "sha256": file_hash,
                "size_bytes": file_size,
            }
            logger.info(f"Backed up {col_name}: {doc_count} docs, {file_size} bytes, SHA256={file_hash[:8]}...")
        except Exception as e:
            logger.error(f"Failed to backup {col_name}: {e}")
            manifest["collections"][col_name] = {"error": str(e), "count": 0}

    manifest_path = os.path.join(base_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)

    logger.info(f"Backup completed successfully. Manifest written to: {manifest_path}")
    return {"status": "success", "backup_dir": base_dir, "manifest": manifest}


def verify_backup(backup_dir: str) -> Dict[str, Any]:
    """Validates the cryptographic integrity and manifest structure of an existing snapshot."""
    manifest_path = os.path.join(backup_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Missing manifest.json in backup directory '{backup_dir}'")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    verified_collections = {}
    all_ok = True

    for col_name, meta in manifest.get("collections", {}).items():
        if "error" in meta:
            verified_collections[col_name] = {"status": "FAILED", "reason": meta["error"]}
            all_ok = False
            continue

        file_path = os.path.join(backup_dir, meta["file"])
        if not os.path.exists(file_path):
            verified_collections[col_name] = {"status": "FAILED", "reason": "File missing"}
            all_ok = False
            continue

        actual_hash = sha256_file(file_path)
        actual_size = os.path.getsize(file_path)

        if actual_hash != meta["sha256"]:
            verified_collections[col_name] = {
                "status": "CHECKSUM_MISMATCH",
                "expected": meta["sha256"],
                "actual": actual_hash,
            }
            all_ok = False
            continue

        # Count lines in gzip to verify document count
        actual_count = 0
        try:
            with gzip.open(file_path, "rt", encoding="utf-8") as gz:
                for _ in gz:
                    actual_count += 1
        except Exception as read_err:
            verified_collections[col_name] = {"status": "CORRUPT_ARCHIVE", "reason": str(read_err)}
            all_ok = False
            continue

        if actual_count != meta["count"]:
            verified_collections[col_name] = {
                "status": "COUNT_MISMATCH",
                "expected": meta["count"],
                "actual": actual_count,
            }
            all_ok = False
            continue

        verified_collections[col_name] = {
            "status": "VERIFIED",
            "count": actual_count,
            "size_bytes": actual_size,
        }

    return {
        "status": "PASSED" if all_ok else "FAILED",
        "verified_at": now_iso(),
        "backup_dir": backup_dir,
        "collections": verified_collections,
    }


async def restore_backup(
    db,
    backup_dir: str,
    collections: Optional[List[str]] = None,
    drop_first: bool = False,
) -> Dict[str, Any]:
    """Restores database collections from a verified snapshot."""
    logger.info(f"Verifying snapshot integrity before restore: {backup_dir}")
    verification = verify_backup(backup_dir)
    if verification["status"] != "PASSED":
        raise ValueError(f"Snapshot integrity verification failed: {verification}")

    manifest_path = os.path.join(backup_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    target_colls = collections or list(manifest.get("collections", {}).keys())
    restored_stats = {}

    for col_name in target_colls:
        if col_name not in manifest.get("collections", {}):
            continue

        meta = manifest["collections"][col_name]
        file_path = os.path.join(backup_dir, meta["file"])
        coll = db[col_name]

        if drop_first:
            await coll.delete_many({})
            logger.info(f"Cleared existing documents in collection '{col_name}'.")

        inserted = 0
        batch = []
        with gzip.open(file_path, "rt", encoding="utf-8") as gz:
            for line in gz:
                if not line.strip():
                    continue
                doc = json_util.loads(line)
                batch.append(doc)
                if len(batch) >= 500:
                    try:
                        res = await coll.insert_many(batch, ordered=False)
                        inserted += len(res.inserted_ids)
                    except Exception:
                        for item in batch:
                            try:
                                await coll.update_one({"_id": item["_id"]}, {"$setOnInsert": item}, upsert=True)
                                inserted += 1
                            except Exception:
                                pass
                    batch = []

        if batch:
            try:
                res = await coll.insert_many(batch, ordered=False)
                inserted += len(res.inserted_ids)
            except Exception:
                for item in batch:
                    try:
                        await coll.update_one({"_id": item["_id"]}, {"$setOnInsert": item}, upsert=True)
                        inserted += 1
                    except Exception:
                        pass

        restored_stats[col_name] = {"restored_count": inserted, "expected": meta["count"]}
        logger.info(f"Restored {col_name}: {inserted}/{meta['count']} documents.")

    # Record restore event into audit log
    try:
        from services.audit_service import record_audit_event
        await record_audit_event(
            db=db,
            entity_type="system",
            entity_id="restore",
            action="restore_backup_drill",
            actor="admin_ops",
            after_state={"backup_dir": backup_dir, "restored": restored_stats},
        )
    except Exception as a_err:
        logger.warning(f"Audit log recording notice: {a_err}")

    return {"status": "success", "restored": restored_stats}


async def rollback_migration(db, target_version: str) -> Dict[str, Any]:
    """Rolls back applied migration records and releases migration locks."""
    logger.info(f"Executing migration rollback to version prior to: {target_version}")

    # Remove target version and newer from schema_migrations
    res = await db.schema_migrations.delete_many({"version": {"$gte": target_version}})
    removed_count = res.deleted_count

    # Release any lingering lock
    await db.migration_locks.update_one(
        {"_id": "global_migration_lock"},
        {"$set": {"locked": False, "released_at": now_iso(), "rollback_note": f"Rollback target {target_version}"}},
        upsert=True,
    )

    logger.info(f"Rollback complete: removed {removed_count} applied migration records. Lock released.")
    return {"status": "success", "removed_migrations_count": removed_count, "target_version": target_version}


async def main():
    parser = argparse.ArgumentParser(description="Database Backup, Restore & Rollback Engine")
    parser.add_argument("--backup", action="store_true", help="Create point-in-time snapshot")
    parser.add_argument("--verify", type=str, help="Verify existing backup snapshot directory")
    parser.add_argument("--restore", type=str, help="Restore database from snapshot directory")
    parser.add_argument("--drop", action="store_true", help="Drop/clear existing collection data before restore")
    parser.add_argument("--rollback-migration", type=str, help="Rollback migration records from specified version upwards")
    parser.add_argument("--dir", type=str, default=None, help="Custom backup directory")
    parser.add_argument("--mongo-url", default=os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "ssk_footwear_erp"))
    args = parser.parse_args()

    client = AsyncIOMotorClient(args.mongo_url)
    db = client[args.db_name]

    if args.backup:
        res = await create_backup(db, output_dir=args.dir)
        print(json.dumps(res, indent=2))
    elif args.verify:
        res = verify_backup(args.verify)
        print(json.dumps(res, indent=2))
    elif args.restore:
        res = await restore_backup(db, args.restore, drop_first=args.drop)
        print(json.dumps(res, indent=2))
    elif args.rollback_migration:
        res = await rollback_migration(db, args.rollback_migration)
        print(json.dumps(res, indent=2))
    else:
        parser.print_help()

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
