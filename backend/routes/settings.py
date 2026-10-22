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


async def log_activity_db(db, action: str, category: str, details: str, email: str, request_id: str = None):
    """DATA-024: Robust audit logging with error observability and actor attribution."""
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "by": email or "system",
            "request_id": request_id,
            "created_at": now_iso()
        })
    except Exception as e:
        log.error(f"DATA-024 AUDIT_LOG_PERSISTENCE_FAILED: action={action} category={category} actor={email}: {e}")


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


# ---------- GMAIL / EMAIL CONFIGURATION ----------

@settings_router.get("/email")
async def get_email_settings(request: Request):
    """Retrieve current email configuration with masked credentials."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import get_email_config
    cfg = await get_email_config(db)
    
    pwd = cfg.get("gmail_app_password", "")
    masked_pwd = ""
    if pwd:
        masked_pwd = "•••• •••• •••• " + (pwd[-4:] if len(pwd) >= 4 else "****")

    return {
        "gmail_user": cfg.get("gmail_user", ""),
        "has_app_password": bool(pwd),
        "masked_app_password": masked_pwd,
        "from_name": cfg.get("from_name", "SSK Footcare Manufacturing"),
        "reply_to": cfg.get("reply_to", ""),
        "default_cc": cfg.get("default_cc", ""),
        "smtp_host": cfg.get("smtp_host", "smtp.gmail.com"),
        "smtp_port": cfg.get("smtp_port", 465),
        "is_configured": cfg.get("is_configured", False),
        "source": cfg.get("source", "none"),
        "updated_at": cfg.get("updated_at"),
    }


@settings_router.put("/email")
async def put_email_settings(payload: dict, request: Request):
    """Save or update company Gmail SMTP credentials with optional verification."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import (
        get_email_config,
        clean_app_password,
        verify_smtp_credentials,
    )

    current_cfg = await get_email_config(db)

    gmail_user = (payload.get("gmail_user") or "").strip()
    new_pwd = clean_app_password(payload.get("gmail_app_password"))
    # If no new password was submitted, retain current password if already present
    if not new_pwd and current_cfg.get("gmail_app_password"):
        new_pwd = current_cfg.get("gmail_app_password")

    from_name = (payload.get("from_name") or "SSK Footcare Manufacturing").strip()
    reply_to = (payload.get("reply_to") or "").strip()
    default_cc = (payload.get("default_cc") or "").strip()
    smtp_host = (payload.get("smtp_host") or "smtp.gmail.com").strip()
    try:
        smtp_port = int(payload.get("smtp_port") or 465)
    except (ValueError, TypeError):
        smtp_port = 465

    verify_now = payload.get("verify_now", False)
    verification_result = None

    if verify_now and gmail_user and new_pwd:
        ok, msg = verify_smtp_credentials(smtp_host, smtp_port, gmail_user, new_pwd)
        verification_result = {"ok": ok, "message": msg}
        if not ok:
            raise HTTPException(400, f"Gmail SMTP verification failed: {msg}")

    update_doc = {
        "gmail_user": gmail_user,
        "gmail_app_password": new_pwd,
        "from_name": from_name,
        "reply_to": reply_to,
        "default_cc": default_cc,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "updated_at": now_iso(),
        "updated_by": u.get("email"),
    }

    await db.settings.update_one(
        {"_id": "email_config"},
        {"$set": update_doc},
        upsert=True,
    )

    await log_activity_db(
        db,
        "update_email_settings",
        "settings",
        f"Updated Gmail SMTP configuration for {gmail_user}",
        u.get("email"),
    )

    return {
        "ok": True,
        "message": "Gmail settings saved successfully",
        "verification": verification_result,
    }


@settings_router.post("/email/verify")
async def verify_email_settings(payload: dict, request: Request):
    """Test Gmail SMTP authentication credentials without persisting."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import get_email_config, clean_app_password, verify_smtp_credentials

    current_cfg = await get_email_config(db)
    user = (payload.get("gmail_user") or current_cfg.get("gmail_user") or "").strip()
    pwd = clean_app_password(payload.get("gmail_app_password")) or current_cfg.get("gmail_app_password") or ""
    host = (payload.get("smtp_host") or current_cfg.get("smtp_host") or "smtp.gmail.com").strip()
    port = int(payload.get("smtp_port") or current_cfg.get("smtp_port") or 465)

    if not user or not pwd:
        raise HTTPException(400, "Both Gmail address and Google App Password are required to test connection.")

    ok, msg = verify_smtp_credentials(host, port, user, pwd)
    return {"ok": ok, "message": msg}


@settings_router.post("/email/test")
async def send_test_email_route(payload: dict, request: Request):
    """Send an actual test email via Gmail SMTP to verify end-to-end delivery."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import get_email_config, send_email

    cfg = await get_email_config(db)
    if not cfg["is_configured"]:
        raise HTTPException(400, "Gmail is not configured. Please save valid credentials first.")

    recipient = (payload.get("test_recipient") or u.get("email") or "").strip()
    if not recipient:
        raise HTTPException(400, "Recipient email is required.")

    subject = "SSK Footcare ERP — Gmail Connection Test"
    text_body = (
        f"Hello,\n\n"
        f"This is a test email confirming that your company Gmail ({cfg['gmail_user']}) "
        f"has been successfully connected to SSK Footcare Manufacturing ERP.\n\n"
        f"You can now send automated invoice payment reminders directly from the Invoices tab.\n\n"
        f"— SSK Footcare ERP System"
    )
    html_body = f"""<!doctype html>
<html>
<body style="font-family: system-ui, sans-serif; background: #F8FAFC; padding: 24px; color: #1E293B;">
  <div style="max-width: 520px; margin: 0 auto; background: #FFFFFF; border: 2px solid #0F172A; padding: 28px; box-shadow: 4px 4px 0px #0F172A;">
    <div style="font-size: 11px; letter-spacing: 2px; color: #64748B; text-transform: uppercase; font-weight: 700;">
      SSK Footcare ERP
    </div>
    <h2 style="font-size: 22px; margin: 8px 0 16px; color: #0F172A;">
      Gmail Connection Verified
    </h2>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">
      This test email confirms that your company Gmail (<strong>{cfg['gmail_user']}</strong>) is properly connected and functioning.
    </p>
    <div style="background: #F0FDF4; border-left: 4px solid #16A34A; padding: 12px 16px; font-size: 13px; color: #15803D; margin: 16px 0; font-weight: 600;">
      Status: Ready to send invoice payment reminders
    </div>
    <p style="font-size: 12px; color: #64748B;">
      Dispatched by: {u.get('email')} at {now_iso()}
    </p>
  </div>
</body>
</html>"""

    ok, msg = send_email(
        to_emails=recipient,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        config=cfg,
    )

    if not ok:
        raise HTTPException(400, f"Failed to send test email: {msg}")

    return {"ok": True, "message": f"Test email sent successfully to {recipient}"}

