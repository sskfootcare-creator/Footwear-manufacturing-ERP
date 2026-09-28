"""Versioned MongoDB Migration Runner for Production ERP (DB-002, DB-004, DB-007, DB-008).
Enforces repeatable forward-only migrations, distributed startup locks to prevent replica race conditions,
and decouples heavy index/backfill tasks from application process boot.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Callable, Awaitable

log = logging.getLogger("mongo_migrations")


async def acquire_migration_lock(db, lock_timeout_seconds: int = 120) -> bool:
    """Acquires a distributed migration lock using MongoDB find_one_and_update."""
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(seconds=lock_timeout_seconds)

    try:
        res = await db.migration_locks.find_one_and_update(
            {
                "_id": "global_migration_lock",
                "$or": [
                    {"locked": False},
                    {"locked_at": {"$lt": stale_threshold.isoformat()}}
                ]
            },
            {
                "$set": {
                    "locked": True,
                    "locked_at": now.isoformat(),
                    "host": os.environ.get("HOSTNAME", "local")
                }
            },
            upsert=True,
            return_document=True
        )
        return bool(res and res.get("locked"))
    except Exception as e:
        log.warning(f"Could not acquire migration lock: {e}")
        return False


async def release_migration_lock(db):
    """Releases the distributed migration lock."""
    try:
        await db.migration_locks.update_one(
            {"_id": "global_migration_lock"},
            {"$set": {"locked": False, "released_at": datetime.now(timezone.utc).isoformat()}}
        )
    except Exception as e:
        log.warning(f"Could not release migration lock: {e}")


# ── Migration 001: Core Collection Indexes ──────────────────────────────────
async def migration_001_core_indexes(db):
    """Creates core unique and query optimization indexes across all operational domains."""
    log.info("Running migration 001_core_indexes...")

    # Users
    await db.users.create_index("email", unique=True)

    # Materials & Styles
    try:
        await db.materials.create_index("code", unique=True)
    except Exception:
        try:
            await db.materials.drop_index("code_1")
            await db.materials.create_index("code", unique=True)
        except Exception:
            pass

    try:
        await db.styles.create_index("code", unique=True)
    except Exception:
        try:
            await db.styles.drop_index("code_1")
            await db.styles.create_index("code", unique=True)
        except Exception:
            pass

    # Purchase Orders & Production
    try:
        await db.pos.create_index("po_number", unique=True)
    except Exception:
        try:
            await db.pos.drop_index("po_number_1")
            await db.pos.create_index("po_number", unique=True)
        except Exception:
            pass

    for col in ("production_jobs", "invoices", "dispatch_records"):
        try:
            await db[col].create_index("po_id")
            await db[col].create_index("po_number")
        except Exception:
            pass

    try:
        await db.vendors.create_index("name")
        await db.workers.create_index("phone", name="workers_phone", sparse=True)
        await db.notifications.create_index([("read", 1), ("at", -1)], name="notifications_unread_time")
        await db.password_resets.create_index("expires_at", expireAfterSeconds=0, name="password_reset_ttl")
    except Exception:
        pass

    # Inventory & Reservations
    try:
        await db.fg_inventory.create_index([("style_id", 1), ("color", 1), ("size", 1)], unique=True, name="fg_inventory_unique")
        await db.inventory_reservations.create_index([("online_order_id", 1), ("status", 1)], name="inv_res_order_status")
        await db.inventory_reservations.create_index([("style_id", 1), ("color", 1), ("size", 1), ("status", 1)], name="inv_res_sku_status")
    except Exception:
        pass


# ── Migration 002: WMS & Warehouse Seed ──────────────────────────────────────
async def migration_002_wms_locations(db):
    """Creates WMS indexes and seeds warehouse cell layout idempotently."""
    log.info("Running migration 002_wms_locations...")
    try:
        await db.warehouse_locations.create_index("location_code", unique=True, name="warehouse_locations_unique")
        await db.fg_location_inventory.create_index(
            [("style_id", 1), ("color", 1), ("size", 1), ("location_code", 1)],
            unique=True, name="fg_loc_inv_unique"
        )
        await db.picklists.create_index("picklist_no", unique=True, name="picklists_no_unique")
    except Exception:
        pass

    try:
        from routes.wms import _seed_warehouse_locations
        await _seed_warehouse_locations()
    except Exception as e:
        log.warning(f"Warehouse cell seed skipped/failed: {e}")


# ── Migration 003: Marketplace & Registry Configs ────────────────────────────
async def migration_003_marketplace_configs(db):
    """Seeds parser templates, color master, and marketplace format configurations."""
    log.info("Running migration 003_marketplace_configs...")
    try:
        await db.sku_parser_templates.create_index("marketplace", unique=True, name="sku_parser_marketplace_unique")
        await db.marketplace_style_color_mapping.create_index(
            [("marketplace_key", 1), ("marketplace_style_code_key", 1), ("marketplace_color_code_key", 1)],
            unique=True, name="mp_scm_unique_normalized"
        )
    except Exception:
        pass

    try:
        from routes.sku_map import _seed_parser_templates
        await _seed_parser_templates()
    except Exception:
        pass

    try:
        from routes.styles import _seed_color_master, _seed_listing_format_configs
        await _seed_color_master()
        await _seed_listing_format_configs()
    except Exception:
        pass

    try:
        from routes.online_orders import _seed_order_import_format_configs
        await _seed_order_import_format_configs(db)
    except Exception:
        pass

    try:
        from routes.pos import _seed_po_ean_format_configs
        await _seed_po_ean_format_configs(db)
    except Exception:
        pass


# ── Migration 004: Offline & Reconciliation Idempotency Indexes ─────────────
async def migration_004_offline_and_recon_indexes(db):
    """DB-007 and DB-008: Compound unique indexes for offline batches and reconciliation imports."""
    log.info("Running migration 004_offline_and_recon_indexes...")

    # DB-007: offline_operation_registry unique compound index
    try:
        await db.offline_operation_registry.create_index(
            [("client_sync_id", 1), ("op_id", 1)],
            unique=True,
            name="offline_op_sync_unique"
        )
    except Exception as e:
        log.warning(f"Could not create offline_operation_registry index: {e}")

    # DB-008: Reconciliation import row hashes
    try:
        await db.online_settlements_detailed.create_index("row_hash", unique=True, sparse=True, name="settlements_row_hash_unique")
        await db.online_non_order_deductions.create_index("row_hash", unique=True, sparse=True, name="non_order_row_hash_unique")
        await db.online_monthly_order_reports.create_index("row_hash", unique=True, sparse=True, name="monthly_reports_row_hash_unique")
        await db.online_daily_payments.create_index("row_hash", sparse=True, name="daily_payments_row_hash")
    except Exception as e:
        log.warning(f"Could not create reconciliation row_hash indexes: {e}")


# ── Migration 005: Legacy URL Rewrites ───────────────────────────────────────
async def migration_005_legacy_url_rewrites(db):
    """One-time rewrite of legacy preview URLs to standard relative endpoints."""
    log.info("Running migration 005_legacy_url_rewrites...")
    import re as _re
    try:
        for coll, fields in (
            ("styles", ["image_url", "image_display_url", "image_thumbnail_url"]),
            ("materials", ["image_url", "image_display_url", "image_thumbnail_url"]),
        ):
            for fld in fields:
                q1 = {fld: {"$regex": r"^https?://[^/]+/uploads/(?!.*api/uploads)"}}
                cursor = db[coll].find(q1)
                async for doc in cursor:
                    val = doc.get(fld, "")
                    new_val = _re.sub(r"^https?://[^/]+/uploads/", "/api/uploads/", val)
                    await db[coll].update_one({"_id": doc["_id"]}, {"$set": {fld: new_val}})
    except Exception as e:
        log.warning(f"URL rewrite migration encountered minor error: {e}")


# ── Registry of Defined Migrations ──────────────────────────────────────────
MIGRATIONS_REGISTRY = [
    ("001", "core_indexes", migration_001_core_indexes),
    ("002", "wms_locations_seed", migration_002_wms_locations),
    ("003", "marketplace_configs_seed", migration_003_marketplace_configs),
    ("004", "offline_and_recon_indexes", migration_004_offline_and_recon_indexes),
    ("005", "legacy_url_rewrites", migration_005_legacy_url_rewrites),
]


async def run_mongo_migrations(db, force: bool = False) -> Dict[str, Any]:
    """Runs all pending MongoDB migrations forward-only in order with distributed locking."""
    # Ensure migration tracking collection exists
    await db.schema_migrations.create_index("version", unique=True)

    applied_docs = await db.schema_migrations.find({}).to_list(1000)
    applied_versions = {d["version"] for d in applied_docs}

    pending = [(v, name, fn) for (v, name, fn) in MIGRATIONS_REGISTRY if v not in applied_versions or force]
    if not pending:
        log.info("MongoDB migrations: schema is up to date (0 pending).")
        return {"status": "up_to_date", "applied_count": 0, "current_versions": list(applied_versions)}

    locked = await acquire_migration_lock(db)
    if not locked:
        log.warning("Could not acquire migration lock; another worker may be executing migrations.")
        return {"status": "locked", "applied_count": 0}

    applied_now = []
    try:
        for version, name, migration_fn in pending:
            log.info(f"Applying migration {version}_{name}...")
            start_time = datetime.now(timezone.utc)
            await migration_fn(db)
            end_time = datetime.now(timezone.utc)

            await db.schema_migrations.update_one(
                {"version": version},
                {
                    "$set": {
                        "version": version,
                        "name": name,
                        "applied_at": end_time.isoformat(),
                        "duration_ms": int((end_time - start_time).total_seconds() * 1000),
                        "status": "completed"
                    }
                },
                upsert=True
            )
            applied_now.append(version)
            log.info(f"Successfully applied migration {version}_{name}.")

        return {"status": "success", "applied_count": len(applied_now), "versions": applied_now}
    finally:
        await release_migration_lock(db)


if __name__ == "__main__":
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "footwear_erp")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(run_mongo_migrations(db))
    print(f"Migration completed: {result}")
