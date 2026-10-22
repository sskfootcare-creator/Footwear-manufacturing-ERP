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

    resend_key = cfg.get("resend_api_key", "")
    masked_resend = ""
    if resend_key:
        masked_resend = "re_••••••••" + (resend_key[-4:] if len(resend_key) >= 4 else "****")

    client_secret = cfg.get("gmail_client_secret", "")
    masked_secret = ""
    if client_secret:
        masked_secret = "••••••••" + (client_secret[-4:] if len(client_secret) >= 4 else "****")

    refresh_token = cfg.get("gmail_refresh_token", "")
    masked_token = ""
    if refresh_token:
        masked_token = "1//••••••••" + (refresh_token[-4:] if len(refresh_token) >= 4 else "****")

    return {
        "provider": cfg.get("provider", "gmail_api"),
        "gmail_user": cfg.get("gmail_user", ""),
        "gmail_client_id": cfg.get("gmail_client_id", ""),
        "has_client_secret": bool(client_secret),
        "masked_client_secret": masked_secret,
        "has_refresh_token": bool(refresh_token),
        "masked_refresh_token": masked_token,
        "has_app_password": bool(pwd),
        "masked_app_password": masked_pwd,
        "has_resend_key": bool(resend_key),
        "masked_resend_key": masked_resend,
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
    """Save or update company email credentials (Gmail REST API, SMTP, or Resend) with non-blocking verification."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    import json
    from services.email_service import (
        get_email_config,
        clean_app_password,
        async_verify_email_credentials,
    )

    current_cfg = await get_email_config(db)

    provider = (payload.get("provider") or "").strip()
    if not provider:
        if payload.get("gmail_client_id") or payload.get("gmail_refresh_token"):
            provider = "gmail_api"
        elif payload.get("resend_api_key"):
            provider = "resend"
        elif payload.get("gmail_app_password"):
            provider = "smtp"
        else:
            provider = current_cfg.get("provider") or "gmail_api"
    gmail_user = (payload.get("gmail_user") or current_cfg.get("gmail_user") or "").strip()

    # Parse raw client_secret.json if provided
    raw_json_str = payload.get("client_secret_json", "").strip()
    extracted_client_id = ""
    extracted_client_secret = ""
    if raw_json_str:
        try:
            parsed = json.loads(raw_json_str)
            sub = parsed.get("installed") or parsed.get("web") or parsed
            extracted_client_id = sub.get("client_id", "").strip()
            extracted_client_secret = sub.get("client_secret", "").strip()
        except Exception as e:
            raise HTTPException(400, f"Invalid client_secret.json format: {e}")

    client_id = extracted_client_id or (payload.get("gmail_client_id") or "").strip()
    if not client_id and current_cfg.get("gmail_client_id"):
        client_id = current_cfg.get("gmail_client_id")

    client_secret = extracted_client_secret or (payload.get("gmail_client_secret") or "").strip()
    if not client_secret and current_cfg.get("gmail_client_secret"):
        client_secret = current_cfg.get("gmail_client_secret")

    refresh_token = (payload.get("gmail_refresh_token") or "").strip()
    if not refresh_token and current_cfg.get("gmail_refresh_token"):
        refresh_token = current_cfg.get("gmail_refresh_token")

    new_pwd = clean_app_password(payload.get("gmail_app_password"))
    if not new_pwd and current_cfg.get("gmail_app_password"):
        new_pwd = current_cfg.get("gmail_app_password")

    resend_api_key = (payload.get("resend_api_key") or "").strip()
    if not resend_api_key and current_cfg.get("resend_api_key"):
        resend_api_key = current_cfg.get("resend_api_key")

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

    if verify_now:
        test_cfg = {
            "provider": provider,
            "gmail_user": gmail_user,
            "gmail_client_id": client_id,
            "gmail_client_secret": client_secret,
            "gmail_refresh_token": refresh_token,
            "gmail_app_password": new_pwd,
            "resend_api_key": resend_api_key,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
        }
        ok, msg = await async_verify_email_credentials(test_cfg)
        verification_result = {"ok": ok, "message": msg}
        if not ok:
            raise HTTPException(400, f"Email verification failed: {msg}")

    update_doc = {
        "provider": provider,
        "gmail_user": gmail_user,
        "gmail_client_id": client_id,
        "gmail_client_secret": client_secret,
        "gmail_refresh_token": refresh_token,
        "gmail_app_password": new_pwd,
        "resend_api_key": resend_api_key,
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
        f"Updated email configuration (provider: {provider})",
        u.get("email"),
    )

    return {
        "ok": True,
        "message": "Email settings saved successfully",
        "verification": verification_result,
    }


@settings_router.post("/email/verify")
async def verify_email_settings(payload: dict, request: Request):
    """Test email authentication credentials without persisting (non-blocking)."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import get_email_config, clean_app_password, async_verify_email_credentials

    current_cfg = await get_email_config(db)
    provider = (payload.get("provider") or current_cfg.get("provider") or "gmail_api").strip()
    user = (payload.get("gmail_user") or current_cfg.get("gmail_user") or "").strip()
    client_id = (payload.get("gmail_client_id") or current_cfg.get("gmail_client_id") or "").strip()
    client_secret = (payload.get("gmail_client_secret") or current_cfg.get("gmail_client_secret") or "").strip()
    refresh_token = (payload.get("gmail_refresh_token") or current_cfg.get("gmail_refresh_token") or "").strip()
    pwd = clean_app_password(payload.get("gmail_app_password")) or current_cfg.get("gmail_app_password") or ""
    resend_key = (payload.get("resend_api_key") or current_cfg.get("resend_api_key") or "").strip()
    host = (payload.get("smtp_host") or current_cfg.get("smtp_host") or "smtp.gmail.com").strip()
    port = int(payload.get("smtp_port") or current_cfg.get("smtp_port") or 465)

    test_cfg = {
        "provider": provider,
        "gmail_user": user,
        "gmail_client_id": client_id,
        "gmail_client_secret": client_secret,
        "gmail_refresh_token": refresh_token,
        "gmail_app_password": pwd,
        "resend_api_key": resend_key,
        "smtp_host": host,
        "smtp_port": port,
    }

    if provider == "gmail_api":
        if not client_id or not client_secret:
            raise HTTPException(400, "Google OAuth Client ID and Client Secret are required.")
        if not refresh_token:
            raise HTTPException(400, "Google OAuth Refresh Token is required. Please authorize your Google account first.")
    elif provider == "resend":
        if not resend_key:
            raise HTTPException(400, "Resend API key is required to test HTTP connection.")
    else:
        if not user or not pwd:
            raise HTTPException(400, "Both Gmail address and Google App Password are required to test connection.")

    ok, msg = await async_verify_email_credentials(test_cfg)
    return {"ok": ok, "message": msg}


@settings_router.post("/email/oauth/auth-url")
async def get_google_auth_url_endpoint(payload: dict, request: Request):
    """Generate the Google OAuth 2.0 consent URL for Gmail REST API authorization."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import get_email_config, generate_google_auth_url
    cfg = await get_email_config(db)
    client_id = (payload.get("client_id") or cfg.get("gmail_client_id") or "").strip()
    redirect_uri = (payload.get("redirect_uri") or "urn:ietf:wg:oauth:2.0:oob").strip()

    if not client_id:
        raise HTTPException(400, "Google OAuth Client ID is required to generate authorization URL.")

    url = generate_google_auth_url(client_id=client_id, redirect_uri=redirect_uri)
    return {"ok": True, "auth_url": url}


@settings_router.post("/email/oauth/exchange")
async def exchange_google_oauth_code_endpoint(payload: dict, request: Request):
    """Exchange an authorization code for permanent Google OAuth refresh token and persist credentials."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import (
        get_email_config,
        exchange_google_auth_code,
        async_verify_email_credentials,
    )

    cfg = await get_email_config(db)
    client_id = (payload.get("client_id") or cfg.get("gmail_client_id") or "").strip()
    client_secret = (payload.get("client_secret") or cfg.get("gmail_client_secret") or "").strip()
    code = (payload.get("code") or "").strip()
    redirect_uri = (payload.get("redirect_uri") or "urn:ietf:wg:oauth:2.0:oob").strip()

    if not client_id or not client_secret:
        raise HTTPException(400, "Both Client ID and Client Secret are required for Google OAuth token exchange.")
    if not code:
        raise HTTPException(400, "Authorization code is required.")

    try:
        token_data = exchange_google_auth_code(client_id, client_secret, code, redirect_uri)
        refresh_token = token_data.get("refresh_token", "").strip()
        if not refresh_token:
            # If Google didn't return a new refresh token (already authorized), fallback to existing if available
            refresh_token = cfg.get("gmail_refresh_token", "").strip()
            if not refresh_token:
                raise HTTPException(400, "Google did not return a refresh_token. Please revoke access at myaccount.google.com/permissions and retry.")

        save_doc = {
            "provider": "gmail_api",
            "gmail_client_id": client_id,
            "gmail_client_secret": client_secret,
            "gmail_refresh_token": refresh_token,
            "updated_at": now_iso(),
            "updated_by": u.get("email"),
        }
        if payload.get("gmail_user"):
            save_doc["gmail_user"] = str(payload.get("gmail_user")).strip()

        test_cfg = {**cfg, **save_doc}
        ok, vmsg = await async_verify_email_credentials(test_cfg)
        if not ok:
            raise HTTPException(400, f"Connected to Google OAuth, but verification failed: {vmsg}")

        await db.settings.update_one({"_id": "email_config"}, {"$set": save_doc}, upsert=True)
        return {
            "ok": True,
            "message": "Successfully authorized with Google and saved Gmail REST API configuration!",
            "verification": vmsg,
            "refresh_token_masked": "1//••••••••" + (refresh_token[-4:] if len(refresh_token) >= 4 else "****"),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("OAuth exchange failed")
        raise HTTPException(400, f"Google OAuth exchange failed: {e}")


@settings_router.post("/email/test")
async def send_test_email_route(payload: dict, request: Request):
    """Send an actual test email non-blockingly to verify end-to-end delivery."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db

    from services.email_service import get_email_config, async_send_email

    cfg = await get_email_config(db)
    if not cfg["is_configured"]:
        raise HTTPException(400, "Email delivery is not configured. Please save valid credentials first.")

    recipient = (payload.get("test_recipient") or u.get("email") or "").strip()
    if not recipient:
        raise HTTPException(400, "Recipient email is required.")

    if cfg.get("provider") == "gmail_api":
        sender_info = f"Gmail REST API HTTPS Port 443 ({cfg.get('gmail_user') or 'Authorized Account'})"
    elif cfg.get("provider") == "resend":
        sender_info = "Resend HTTP API (Port 443 HTTPS)"
    else:
        sender_info = f"Gmail SMTP ({cfg.get('gmail_user')})"

    subject = "SSK Footcare ERP — Email Connection Test"
    text_body = (
        f"Hello,\n\n"
        f"This is a test email confirming that your email service ({sender_info}) "
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
      Email Connection Verified
    </h2>
    <p style="font-size: 14px; line-height: 1.6; color: #334155;">
      This test email confirms that your company email service (<strong>{sender_info}</strong>) is properly connected and functioning.
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

    ok, msg = await async_send_email(
        to_emails=recipient,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        config=cfg,
    )

    if not ok:
        raise HTTPException(400, f"Failed to send test email: {msg}")

    return {"ok": True, "message": f"Test email sent successfully to {recipient}"}

