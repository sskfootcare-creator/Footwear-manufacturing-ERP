"""Supabase Sync Failure Tracking Service.

Persists sync failures to the MongoDB `supabase_sync_failures` collection:
- id: str (UUID)
- collection: str (MongoDB collection name e.g. 'invoices', 'payments', 'wage_payments', 'vendor_purchase_orders', 'vendor_po_receives')
- doc_id: str (ID of the document that failed to sync)
- error: str (Error message)
- timestamp: str (ISO format UTC)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Dict, List

log = logging.getLogger(__name__)


def build_sync_failure_doc(
    collection: str,
    doc_id: Any,
    error: Any,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """Create deterministic dictionary conforming to supabase_sync_failures schema."""
    return {
        "id": str(uuid.uuid4()),
        "collection": str(collection),
        "doc_id": str(doc_id),
        "error": str(error),
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }


async def record_supabase_sync_failure(
    db: Any,
    collection: str,
    doc_id: Any,
    error: Any,
    timestamp: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Record a failure into supabase_sync_failures in MongoDB.
    Schema: (id, collection, doc_id, error, timestamp)
    """
    if db is None:
        try:
            import server
            db = getattr(server, "db", None)
        except Exception:
            pass

    record = build_sync_failure_doc(collection, doc_id, error, timestamp)

    if db is None:
        log.warning("Database unavailable; cannot persist failure record to supabase_sync_failures: %s", record)
        return record

    try:
        if hasattr(db, "supabase_sync_failures") and db.supabase_sync_failures is not None:
            await db.supabase_sync_failures.insert_one(dict(record))
        return record
    except Exception as e:
        log.warning("Could not persist failure into supabase_sync_failures: %s", e)
        return record


async def get_supabase_sync_failures(
    db: Any,
    collection: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Query recent sync failures from supabase_sync_failures collection."""
    if db is None:
        try:
            import server
            db = getattr(server, "db", None)
        except Exception:
            pass

    if db is None or not hasattr(db, "supabase_sync_failures") or db.supabase_sync_failures is None:
        return []

    try:
        q = {}
        if collection:
            q["collection"] = collection
        cursor = db.supabase_sync_failures.find(q).sort("timestamp", -1)
        docs = await cursor.to_list(limit) if hasattr(cursor, "to_list") else list(cursor)
        for d in docs:
            if "_id" in d and "id" not in d:
                d["id"] = str(d.pop("_id"))
            elif "_id" in d:
                d.pop("_id")
        return docs
    except Exception as e:
        log.warning("Could not fetch sync failures from MongoDB: %s", e)
        return []
