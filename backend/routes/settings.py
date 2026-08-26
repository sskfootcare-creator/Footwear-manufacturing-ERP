"""Settings, Stage Durations, Company Profile, Audit Logs & Backup Routes."""

from typing import Dict, Optional, List
from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone
from auth import require_roles

from models.settings import (
    DEFAULT_STAGE_HOURS,
    StageDurationsIn,
)

settings_router = APIRouter(prefix="/api/settings", tags=["Settings & Configuration"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


async def _get_user(request: Request):
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    db = getattr(request.app, "mongodb", None) or server.db
    fn = await get_current_user_factory(db)
    return await fn(request)


async def _get_stage_durations_db(db) -> Dict[str, float]:
    doc = await db.settings.find_one({"_id": "stage_durations"})
    out = dict(DEFAULT_STAGE_HOURS)
    if doc and isinstance(doc.get("hours"), dict):
        out.update({k: float(v) for k, v in doc["hours"].items() if isinstance(v, (int, float))})
    return out


async def log_activity_db(db, action: str, category: str, details: str, email: str):
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "by": email,
            "created_at": now_iso()
        })
    except Exception:
        pass


# ---------- STAGE DURATIONS ----------

@settings_router.get("/stage-durations")
async def get_stage_durations(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db
    return {"hours": await _get_stage_durations_db(db), "defaults": DEFAULT_STAGE_HOURS}


@settings_router.put("/stage-durations")
async def put_stage_durations(payload: StageDurationsIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    cleaned = {k: float(v) for k, v in payload.hours.items() if isinstance(v, (int, float)) and float(v) >= 0}
    await db.settings.update_one(
        {"_id": "stage_durations"},
        {"$set": {"hours": cleaned, "updated_at": now_iso(), "updated_by": u["email"]}},
        upsert=True,
    )
    await log_activity_db(db, "update_stage_durations", "settings", "Updated stage ETAs/deadlines", u["email"])
    return {"ok": True, "hours": await _get_stage_durations_db(db)}


# ---------- COMPANY PROFILE ----------

@settings_router.get("/company")
async def get_company_profile(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    profile = await db.settings.find_one({"_id": "company_profile"})
    if not profile:
        from pdf_docs import COMPANY
        return COMPANY
    profile.pop("_id", None)
    return profile


@settings_router.put("/company")
async def put_company_profile(payload: dict, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    await db.settings.update_one(
        {"_id": "company_profile"},
        {"$set": payload},
        upsert=True
    )
    from pdf_docs import update_company_profile
    update_company_profile(payload)
    await log_activity_db(db, "update_company_profile", "settings", "Updated company profile details", u["email"])
    return {"ok": True}


# ---------- AUDIT LOGS ----------

@settings_router.get("/audit-logs")
async def get_audit_logs(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    logs = await db.audit_logs.find({}).sort("created_at", -1).to_list(100)
    return [stringify(l) for l in logs]


# ---------- EXPORT / BACKUP ----------

@settings_router.get("/export-backup")
async def get_export_backup(request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    backup_data = {}
    collections = [
        "users", "materials", "styles", "pos", "production_jobs", 
        "workers", "defects", "packing_templates", "invoices", 
        "grns", "payments", "settings", "inventory_movements", "audit_logs"
    ]
    for col_name in collections:
        docs = await db[col_name].find({}).to_list(10000)
        backup_data[col_name] = [stringify(d) for d in docs]
    await log_activity_db(db, "database_backup", "settings", f"Full database backup downloaded by {u['email']}", u["email"])
    return backup_data
