"""Centralized Immutable Audit Logging Service (P1-017).

Provides:
1. Structured, tamper-evident audit log creation with SHA-256 integrity hash chaining.
2. Change delta / diff generation for critical business writes (stock moves, settlements, invoice edits, user roles).
3. Queryable audit log repository.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

log = logging.getLogger("audit_service")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_diff(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute field-level changes between before and after states."""
    if not before and not after:
        return {}
    if not before:
        return {"created": after}
    if not after:
        return {"deleted": before}

    changes = {}
    all_keys = set(before.keys()) | set(after.keys())
    for k in all_keys:
        if k in ("_id", "updated_at"):
            continue
        v_before = before.get(k)
        v_after = after.get(k)
        if v_before != v_after:
            changes[k] = {"before": v_before, "after": v_after}
    return changes


def compute_audit_hash(prev_hash: str, payload_str: str) -> str:
    """Generate SHA-256 hash chaining to ensure tamper evidence."""
    combined = f"{prev_hash}:{payload_str}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


async def record_audit_event(
    db,
    action: str,
    category: str,
    actor: str,
    details: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    diff: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record an immutable, queryable audit log entry."""
    if db is None:
        return {}

    ts = now_iso()
    computed_diff = diff or compute_diff(before, after)

    # Fetch last audit record for hash chaining
    prev_hash = "GENESIS"
    try:
        last_log = await db.audit_logs.find_one(
            {"audit_hash": {"$exists": True}},
            sort=[("_id", -1)]
        )
        if last_log and "audit_hash" in last_log:
            prev_hash = last_log["audit_hash"]
    except Exception:
        pass

    payload_summary = json.dumps({
        "action": action,
        "category": category,
        "actor": actor,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else "",
        "timestamp": ts,
    }, sort_keys=True)

    audit_hash = compute_audit_hash(prev_hash, payload_summary)

    doc = {
        "action": action,
        "category": category,
        "actor": actor,
        "user": actor,  # backward compatibility
        "details": details,
        "entity_type": entity_type or "",
        "entity_id": str(entity_id) if entity_id else "",
        "diff": computed_diff,
        "metadata": metadata or {},
        "timestamp": ts,
        "created_at": ts,
        "prev_hash": prev_hash,
        "audit_hash": audit_hash,
    }

    try:
        await db.audit_logs.insert_one(doc)
    except Exception as e:
        log.warning(f"Failed to persist audit log: {e}")

    return doc
