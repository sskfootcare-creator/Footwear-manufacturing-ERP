"""Auth HTTP routes: login, logout, refresh, me, forgot-password, reset-password, users.

All JWT/password/cookie helpers live in auth.py (the module).  This router
owns:
  - Rate-limited login  (in-memory + Redis)
  - Token refresh with cookie rotation
  - Password-reset flow (token issue + consume + Gmail SMTP)
  - Users CRUD (admin-only)

The rate-limit state (``_login_failures``, ``redis_client``) is defined here
and re-exported by server.py so existing tests that import them from ``server``
continue to work.
"""
from __future__ import annotations

import os
import secrets
import hashlib
import smtplib
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Response
import jwt

import sys

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    validate_password,
    set_auth_cookies,
    clear_auth_cookies,
    require_roles,
    JWT_ALGORITHM,
    get_jwt_secret,
    ERP_MODULES,
    ROLE_DEFAULT_MODULES,
    get_user_modules,
)
from models.auth import (
    LoginInput,
    UserCreate,
    UserUpdate,
    ForgotPasswordInput,
    ResetPasswordInput,
)

log = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api", tags=["Authentication & Users"])

# ---------------------------------------------------------------------------
# Rate-limit state (in-memory fallback; Redis if REDIS_URL is set)
# ---------------------------------------------------------------------------
_login_failures: dict = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900   # 15-minute sliding window

redis_client = None
_REDIS_URL = os.environ.get("REDIS_URL")
if _REDIS_URL:
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
        log.info(f"Auth router: connected to Redis for distributed rate limiting: {_REDIS_URL}")
    except Exception as _e:
        log.warning(f"Auth router: failed to initialise Redis client: {_e}")


async def check_rate_limit(
    key: str,
    max_attempts: int = LOGIN_MAX_ATTEMPTS,
    window_seconds: int = LOGIN_WINDOW_SECONDS,
) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    window_start = now_ts - window_seconds

    if redis_client is not None:
        try:
            rkey = f"login_failures:{key}"
            await redis_client.zremrangebyscore(rkey, "-inf", window_start)
            count = await redis_client.zcard(rkey)
            if count >= max_attempts:
                oldest = await redis_client.zrange(rkey, 0, 0, withscores=True)
                oldest_ts = oldest[0][1] if oldest else window_start
                retry_after = int(window_seconds - (now_ts - oldest_ts))
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many failed login attempts. Try again in {max(1, retry_after // 60)} minutes.",
                    headers={"Retry-After": str(max(retry_after, 1))},
                )
            return
        except HTTPException:
            raise
        except Exception as e:
            log.warning(f"Redis rate check error, falling back to memory: {e}")

    _login_failures[key] = [t for t in _login_failures[key] if t > window_start]
    if len(_login_failures[key]) >= max_attempts:
        retry_after = int(window_seconds - (now_ts - _login_failures[key][0]))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {max(1, retry_after // 60)} minutes.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


async def record_login_failure(key: str, window_seconds: int = LOGIN_WINDOW_SECONDS) -> int:
    now_ts = datetime.now(timezone.utc).timestamp()
    if redis_client is not None:
        try:
            rkey = f"login_failures:{key}"
            await redis_client.zadd(rkey, {str(now_ts): now_ts})
            await redis_client.expire(rkey, window_seconds + 60)
            return await redis_client.zcard(rkey)
        except Exception as e:
            log.warning(f"Redis record failure error, falling back to memory: {e}")

    _login_failures[key].append(now_ts)
    return len(_login_failures[key])


async def clear_login_failures(key: str) -> None:
    if redis_client is not None:
        try:
            rkey = f"login_failures:{key}"
            await redis_client.delete(rkey)
        except Exception as e:
            log.warning(f"Redis clear failure error: {e}")
    _login_failures.pop(key, None)


# ---------------------------------------------------------------------------
# Password-reset helpers
# ---------------------------------------------------------------------------
PASSWORD_RESET_TTL_HOURS = 1


def _hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reset_link_base() -> str:
    """Return the absolute frontend base URL for password-reset links."""
    return (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("FRONTEND_URL")
        or "http://localhost:3000"
    ).rstrip("/")


def _send_reset_email(to_email: str, reset_url: str, user_name: str) -> tuple[bool, str]:
    """Return (ok, hint).  ok=False when SMTP isn't configured or send fails."""
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not gmail_user or not gmail_pass:
        return (False, "email_not_configured")

    from_display = os.environ.get("GMAIL_FROM_NAME", "SSK Footcare ERP")
    subject = "Reset your SSK Footcare ERP password"

    text_body = (
        f"Hi {user_name or 'there'},\n\n"
        f"We received a request to reset your SSK Footcare ERP password.\n"
        f"Open the link below to choose a new one — it expires in "
        f"{PASSWORD_RESET_TTL_HOURS} hour(s) and can only be used once.\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— SSK Footcare Manufacturing"
    )
    html_body = f"""\
<!doctype html>
<html><body style="font-family: system-ui, sans-serif; background:#F7F7F5; padding:24px;">
  <div style="max-width:520px; margin:0 auto; background:#fff; border:2px solid #111827; padding:28px;">
    <div style="font-size:11px; letter-spacing:2px; color:#64748B; text-transform:uppercase;">SSK Footcare Manufacturing</div>
    <h1 style="font-size:24px; margin:8px 0 16px;">Reset your password</h1>
    <p>Hi {user_name or 'there'},</p>
    <p>Click the button below to choose a new password. This link expires in
       <strong>{PASSWORD_RESET_TTL_HOURS} hour(s)</strong> and can only be used once.</p>
    <p style="text-align:center; margin:24px 0;">
      <a href="{reset_url}"
         style="background:#0F172A; color:#fff; text-decoration:none; padding:12px 24px;
                font-weight:700; letter-spacing:2px; text-transform:uppercase; font-size:12px;">
        Reset Password
      </a>
    </p>
    <p style="font-size:12px; color:#64748B; word-break:break-all;">Or copy this URL:<br/>{reset_url}</p>
    <hr style="border:none; border-top:1px solid #E2E8F0; margin:20px 0;"/>
    <p style="font-size:11px; color:#94A3B8;">If you didn't request this, you can safely ignore this email.</p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_display} <{gmail_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(gmail_user, gmail_pass)
            smtp.sendmail(gmail_user, [to_email], msg.as_string())
        return (True, "sent")
    except smtplib.SMTPAuthenticationError:
        log.exception("Gmail SMTP authentication failed")
        return (False, "smtp_auth_failed")
    except Exception:
        log.exception("Gmail SMTP send failed")
        return (False, "smtp_send_failed")


# ---------------------------------------------------------------------------
# Tiny forwarding helpers (resolve db / get_current_user at call time so the
# module can be imported before server.py finishes its startup sequence).
# All use sys.modules to avoid a top-level circular import.
# ---------------------------------------------------------------------------
import inspect


def _server():
    """Return the server module, importing it lazily if needed."""
    return sys.modules.get("server") or __import__("server")


def _get_db():
    return _server().db


async def _maybe_await(val):
    if inspect.isawaitable(val):
        return await val
    return val


def _current_user_fn():
    """Return the bound get_current_user coroutine function."""
    return _server().get_current_user


def _oid(v):
    return _server().oid(v)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stringify(doc: dict) -> dict:
    return _server().stringify(doc)


# ---------------------------------------------------------------------------
# Auth routes & Modules metadata
# ---------------------------------------------------------------------------

@auth_router.get("/auth/modules")
async def get_modules_catalogue():
    """Return all ERP modules with metadata and default role associations."""
    return {
        "modules": ERP_MODULES,
        "role_defaults": ROLE_DEFAULT_MODULES,
    }


@auth_router.post("/auth/login")
async def login(payload: LoginInput, request: Request, response: Response):
    """Rate-limited login — returns JWT access + refresh tokens in cookies and body."""
    from rate_limiter import _is_test_mode
    test_ip = request.headers.get("x-test-rate-limit-client-ip") if _is_test_mode() else None
    client_ip = test_ip or (request.client.host if request.client else "unknown")
    await check_rate_limit(client_ip)

    db = _get_db()
    email = payload.email.lower().strip()

    # ── 1. Attempt Supabase Auth credential validation ───────────────────────
    supa_auth_res = None
    try:
        from services.supabase_auth_service import authenticate_with_supabase
        supa_auth_res = authenticate_with_supabase(email, payload.password)
    except Exception as _supa_err:
        log.warning("Supabase auth check fallback: %s", _supa_err)

    user = await db.users.find_one({"email": email})
    is_authenticated = False
    access = None
    refresh = None

    if supa_auth_res and getattr(supa_auth_res, "session", None) is not None:
        is_authenticated = True
        access = supa_auth_res.session.access_token
        refresh = supa_auth_res.session.refresh_token
        if not user:
            supa_u = getattr(supa_auth_res, "user", None)
            meta = getattr(supa_u, "user_metadata", {}) or {}
            # F-002: NEVER trust client-supplied user_metadata for privileged ERP roles.
            # Only server-controlled mapping or default safe 'viewer' role can be assigned.
            server_mapped_role = None
            mapping = await db.role_mappings.find_one({"email": email}) if hasattr(db, "role_mappings") else None
            if mapping and mapping.get("role"):
                server_mapped_role = mapping["role"]
            elif email in ("admin@sskfootcare.com", "admin@example.com"):
                server_mapped_role = "admin"
            else:
                server_mapped_role = "viewer"

            user_doc = {
                "email": email,
                "name": meta.get("name", email.split("@")[0]),
                "role": server_mapped_role,
                "role_title": meta.get("role_title", "Viewer"),
                "active": True,
                "created_at": _now_iso(),
            }
            res_ins = await db.users.insert_one(user_doc)
            user_doc["_id"] = res_ins.inserted_id
            user = user_doc
    elif user and user.get("active", True) and verify_password(payload.password, user.get("password_hash", "")):
        is_authenticated = True
        # Auto-sync user into Supabase Auth for seamless migration
        try:
            from services.supabase_auth_service import create_or_sync_supabase_user
            create_or_sync_supabase_user(
                email=email,
                password=payload.password,
                name=user.get("name", ""),
                role=user.get("role", "custom"),
                allowed_modules=user.get("allowed_modules"),
            )
        except Exception as _e:
            log.debug("Auto-sync to Supabase warning: %s", _e)
        uid = str(user["_id"])
        allowed_modules = user.get("allowed_modules")
        access = create_access_token(uid, email, user["role"], allowed_modules=allowed_modules)
        refresh = create_refresh_token(uid)

        # F-003: Persist refresh session
        try:
            from auth import JWT_ISSUER, JWT_AUDIENCE
            r_payload = jwt.decode(
                refresh,
                get_jwt_secret(),
                algorithms=[JWT_ALGORITHM],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            )
            r_jti = r_payload.get("jti")
            r_exp = r_payload.get("exp")
            if r_jti:
                exp_dt = datetime.fromtimestamp(r_exp, tz=timezone.utc) if r_exp else (datetime.now(timezone.utc) + timedelta(days=7))
                await _maybe_await(db.refresh_tokens.insert_one({
                    "user_id": uid,
                    "jti": r_jti,
                    "revoked": False,
                    "expires_at": exp_dt,
                    "created_at": _now_iso(),
                    "ip": client_ip,
                }))
        except Exception as _r_err:
            log.warning("Failed to persist initial refresh token: %s", _r_err)

    if not is_authenticated or (user and not user.get("active", True)):
        attempt_count = await record_login_failure(client_ip)
        log.warning(
            "Failed login attempt for email=%s from ip=%s (attempt %d/%d)",
            email, client_ip, attempt_count, LOGIN_MAX_ATTEMPTS,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await clear_login_failures(client_ip)
    uid = str(user["_id"])
    allowed_modules = user.get("allowed_modules")
    effective_modules = get_user_modules(user)
    set_auth_cookies(response, access, refresh)
    res_dict = {
        "id": uid,
        "email": email,
        "name": user.get("name", ""),
        "role": user["role"],
        "role_title": user.get("role_title", ""),
        "allowed_modules": allowed_modules,
        "modules": effective_modules,
    }
    # F-029: Honor pure cookie mode if requested or configured
    headers = getattr(request, "headers", {}) or {}
    q_params = getattr(request, "query_params", {}) or {}
    client_mode = (headers.get("x-auth-client-mode") if hasattr(headers, "get") else None) or (q_params.get("auth_mode") if hasattr(q_params, "get") else None)
    cookie_only = client_mode == "cookie" or os.environ.get("COOKIE_AUTH_ONLY", "false").lower() in ("true", "1")
    if not cookie_only:
        res_dict["access_token"] = access
        res_dict["refresh_token"] = refresh
    return res_dict



@auth_router.post("/auth/logout")
async def logout(response: Response, request: Request = None):
    clear_auth_cookies(response)
    refresh_token = None
    if request:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            auth_hdr = request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                refresh_token = auth_hdr[7:]
    if refresh_token:
        try:
            from auth import JWT_ISSUER, JWT_AUDIENCE
            payload = jwt.decode(
                refresh_token,
                get_jwt_secret(),
                algorithms=[JWT_ALGORITHM],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            )
            jti = payload.get("jti")
            if jti:
                db = _get_db()
                await _maybe_await(db.refresh_tokens.update_one(
                    {"jti": jti},
                    {"$set": {"revoked": True, "revoked_at": _now_iso(), "revocation_reason": "logout"}}
                ))
        except Exception:
            pass
    return {"ok": True}


@auth_router.post("/auth/refresh")
async def refresh_token_route(request: Request, response: Response):
    """Accept refresh_token from either the httpOnly cookie OR the JSON body.

    The body-based flow is used when cookies can't be transmitted (e.g. when the
    frontend is embedded inside a cross-origin iframe and the ingress forces
    Access-Control-Allow-Origin: '*', which blocks credentialed fetches).
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        try:
            body = await request.json()
            refresh_token = (body or {}).get("refresh_token")
        except Exception:
            refresh_token = None
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        from auth import JWT_ISSUER, JWT_AUDIENCE
        payload = jwt.decode(
            refresh_token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        db = _get_db()
        uid_str = str(payload["sub"])
        jti = payload.get("jti")

        # F-003: Check refresh token revocation and replay protection
        if jti and hasattr(db, "refresh_tokens"):
            try:
                res = db.refresh_tokens.find_one_and_update(
                    {"jti": jti, "user_id": uid_str, "revoked": False},
                    {"$set": {"revoked": True, "revoked_at": _now_iso()}}
                )
                session = await _maybe_await(res)
                # If session is explicitly None (meaning not active/unrevoked), check replay
                if session is None:
                    res_chk = db.refresh_tokens.find_one({"jti": jti, "user_id": uid_str})
                    already_revoked = await _maybe_await(res_chk)
                    if already_revoked and isinstance(already_revoked, dict):
                        log.warning("Replay attack detected for user %s with jti=%s! Revoking all sessions.", uid_str, jti)
                        await _maybe_await(db.refresh_tokens.update_many(
                            {"user_id": uid_str},
                            {"$set": {"revoked": True, "revoked_at": _now_iso(), "revocation_reason": "replay_detected"}}
                        ))
                        raise HTTPException(status_code=401, detail="Refresh token revoked or already used (replay detected)")
            except HTTPException:
                raise
            except Exception as _r_chk_err:
                log.warning("Refresh session check error: %s", _r_chk_err)

        user = await db.users.find_one({"_id": ObjectId(uid_str)})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="User not found or inactive")

        allowed_modules = user.get("allowed_modules")
        new_access = create_access_token(str(user["_id"]), user["email"], user["role"], allowed_modules=allowed_modules)
        new_refresh = create_refresh_token(str(user["_id"]))

        # Persist new rotated refresh token
        try:
            new_payload = jwt.decode(
                new_refresh,
                get_jwt_secret(),
                algorithms=[JWT_ALGORITHM],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
            )
            new_jti = new_payload.get("jti")
            new_exp = new_payload.get("exp")
            if new_jti:
                new_exp_dt = datetime.fromtimestamp(new_exp, tz=timezone.utc) if new_exp else (datetime.now(timezone.utc) + timedelta(days=7))
                await _maybe_await(db.refresh_tokens.insert_one({
                    "user_id": uid_str,
                    "jti": new_jti,
                    "revoked": False,
                    "expires_at": new_exp_dt,
                    "created_at": _now_iso(),
                    "replaced_jti": jti,
                }))
        except Exception as _new_r_err:
            log.warning("Failed to persist rotated refresh token: %s", _new_r_err)

        set_auth_cookies(response, new_access, new_refresh)
        return {"ok": True, "access_token": new_access, "refresh_token": new_refresh}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Expired refresh token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@auth_router.get("/auth/me")
async def me(request: Request):
    user = await _current_user_fn()(request)
    return user


# ---------------------------------------------------------------------------
# Password-reset routes
# ---------------------------------------------------------------------------

@auth_router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordInput, request: Request):
    """Issue a single-use 1-hour password-reset token and email it.

    Always returns 200 with a generic message — we never leak whether an email
    is registered (prevents user-enumeration).
    """
    email = payload.email.lower().strip()
    db = _get_db()
    user = await db.users.find_one({"email": email})

    generic_ok = {
        "ok": True,
        "message": "If that email matches an account, a reset link has been sent.",
    }

    if not user or not user.get("active", True):
        log.info("Forgot-password requested for unknown/inactive email: %s", email)
        return generic_ok

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=PASSWORD_RESET_TTL_HOURS)

    # Invalidate previous unused tokens for this user before issuing a new one
    await db.password_resets.update_many(
        {"user_id": str(user["_id"]), "used_at": None},
        {"$set": {"used_at": _now_iso(), "invalidated": True}},
    )
    await db.password_resets.insert_one({
        "user_id":    str(user["_id"]),
        "email":      email,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "used_at":    None,
        "created_at": datetime.now(timezone.utc),
        "created_ip": request.client.host if request.client else "unknown",
    })

    reset_url = f"{_reset_link_base()}/reset-password?token={raw_token}"
    ok, hint = _send_reset_email(email, reset_url, user.get("name", ""))

    if ok:
        return generic_ok

    # SMTP not configured / failed — surface a discoverable hint to the caller
    # (still 200 so we don't leak account existence). Admin who calls this on
    # their own account can look at the JSON body to see the link.
    resp: dict = dict(generic_ok)
    resp["email_status"] = hint  # "email_not_configured" | "smtp_auth_failed" | "smtp_send_failed"
    from auth import get_environment
    env = get_environment()
    allow_dev_expose = os.environ.get("EXPOSE_DEV_RESET_URL", "true" if env == "development" else "false").lower() in ("true", "1")
    if hint == "email_not_configured" and env == "development" and allow_dev_expose:
        # In dev only, expose the reset link when explicitly allowed so the admin can test locally.
        # NEVER exposes the token in production or when SMTP is configured.
        resp["dev_reset_url"] = reset_url
    return resp


@auth_router.post("/auth/reset-password")
async def reset_password(payload: ResetPasswordInput):
    """Consume a reset token and set a new password.  Invalidates all other
    outstanding tokens and refresh sessions for the same user on success."""
    token_hash = _hash_reset_token(payload.token.strip())
    db = _get_db()
    now = datetime.now(timezone.utc)
    
    # F-004: Atomic find_one_and_update directly in lookup query (eliminates concurrent consumption race)
    row = await db.password_resets.find_one_and_update(
        {
            "token_hash": token_hash,
            "used_at": None,
            "expires_at": {"$gt": now},
        },
        {"$set": {"used_at": _now_iso()}}
    )
    if not row:
        existing = await db.password_resets.find_one({"token_hash": token_hash})
        if existing and existing.get("used_at"):
            raise HTTPException(400, "This reset link has already been used.")
        if existing and existing.get("expires_at"):
            exp = existing["expires_at"]
            if isinstance(exp, datetime):
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now:
                    raise HTTPException(400, "This reset link has expired. Please request a new one.")
        raise HTTPException(400, "Invalid or already-used reset link.")
    validate_password(payload.new_password)

    user = await db.users.find_one({"_id": _oid(row["user_id"])})
    if not user or not user.get("active", True):
        raise HTTPException(400, "Account not found or inactive.")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "password_updated_at": _now_iso()}},
    )
    # Invalidate all other pending reset tokens for this user
    await db.password_resets.update_many(
        {"user_id": str(user["_id"]), "used_at": None, "_id": {"$ne": row["_id"]}},
        {"$set": {"used_at": _now_iso(), "invalidated": True}},
    )
    # F-003: Invalidate all active refresh sessions for this user on password reset
    try:
        await db.refresh_tokens.update_many(
            {"user_id": str(user["_id"])},
            {"$set": {"revoked": True, "revoked_at": _now_iso(), "revocation_reason": "password_reset"}}
        )
    except Exception:
        pass
    return {"ok": True, "message": "Password updated. You can now sign in."}


# ---------------------------------------------------------------------------
# Users (admin-only CRUD)
# ---------------------------------------------------------------------------

@auth_router.get("/users")
async def list_users(request: Request):
    user = await _current_user_fn()(request)
    require_roles("admin")(user)
    db = _get_db()
    docs = await db.users.find({}, {"password_hash": 0}).to_list(500)
    result = []
    for d in docs:
        item = _stringify(d)
        item["modules"] = get_user_modules(d)
        result.append(item)
    return result


@auth_router.post("/users")
async def create_user(payload: UserCreate, request: Request):
    user = await _current_user_fn()(request)
    require_roles("admin")(user)
    validate_password(payload.password)
    email = payload.email.lower()
    db = _get_db()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already exists")

    # Sync into Supabase Auth
    supa_uid = None
    try:
        from services.supabase_auth_service import create_or_sync_supabase_user
        supa_user = create_or_sync_supabase_user(
            email=email,
            password=payload.password,
            name=payload.name,
            role=payload.role,
            allowed_modules=payload.allowed_modules,
        )
        if supa_user:
            supa_uid = getattr(supa_user, "id", None)
    except Exception as _supa_err:
        log.warning("Failed to provision user in Supabase Auth: %s", _supa_err)

    doc = {
        "email": email,
        "name": payload.name,
        "full_name": payload.full_name or payload.name,
        "role": payload.role,
        "role_title": payload.role_title,
        "department": payload.department or "general",
        "allowed_modules": payload.allowed_modules,
        "password_hash": hash_password(payload.password),
        "supabase_uid": supa_uid,
        "active": True,
        "created_at": _now_iso(),
    }
    res = await db.users.insert_one(doc)
    return {
        "id": str(res.inserted_id),
        "email": email,
        "name": payload.name,
        "full_name": doc["full_name"],
        "role": payload.role,
        "role_title": payload.role_title,
        "department": doc["department"],
        "allowed_modules": payload.allowed_modules,
        "modules": get_user_modules(doc),
        "active": True,
        "created_at": doc["created_at"],
    }


@auth_router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, request: Request):
    user = await _current_user_fn()(request)
    require_roles("admin")(user)
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "password" in update:
        validate_password(update["password"])
        update["password_hash"] = hash_password(update.pop("password"))
    db = _get_db()
    user_before = await db.users.find_one({"_id": _oid(user_id)})
    if not user_before:
        raise HTTPException(404, "User not found")

    # F-027: Last-admin protection & self-privilege checks
    if user_before.get("role") == "admin":
        is_demoting = "role" in update and update["role"] != "admin"
        is_deactivating = update.get("active") is False
        if is_demoting or is_deactivating:
            active_admins = await db.users.count_documents({
                "role": "admin",
                "active": {"$ne": False},
                "_id": {"$ne": _oid(user_id)}
            })
            if active_admins == 0:
                raise HTTPException(400, "Cannot remove, demote, or deactivate the last active administrator.")

    # Prevent admin from self-demoting their own account
    if str(user.get("id")) == str(user_id) and "role" in update and update["role"] != "admin":
        raise HTTPException(400, "Administrators cannot demote their own account.")

    # Audit role change
    if "role" in update and update["role"] != user_before.get("role"):
        try:
            await db.audit_logs.insert_one({
                "action": "USER_ROLE_CHANGE",
                "target_user_id": str(user_id),
                "target_email": user_before.get("email"),
                "old_role": user_before.get("role"),
                "new_role": update["role"],
                "changed_by": user.get("email") or user.get("id"),
                "timestamp": _now_iso(),
            })
        except Exception:
            pass

    # Sync updates to Supabase Auth
    try:
        from services.supabase_auth_service import create_or_sync_supabase_user
        raw_pw = payload.password if payload.password else None
        create_or_sync_supabase_user(
            email=user_before["email"],
            password=raw_pw,
            name=update.get("name", user_before.get("name", "")),
            role=update.get("role", user_before.get("role", "custom")),
            allowed_modules=update.get("allowed_modules", user_before.get("allowed_modules")),
        )
    except Exception as _supa_err:
        log.warning("Failed to sync user update to Supabase Auth: %s", _supa_err)

    await db.users.update_one({"_id": _oid(user_id)}, {"$set": update})
    doc = await db.users.find_one({"_id": _oid(user_id)}, {"password_hash": 0})
    res = _stringify(doc)
    res["modules"] = get_user_modules(doc)
    return res


@auth_router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    user = await _current_user_fn()(request)
    require_roles("admin")(user)
    if str(user.get("id")) == str(user_id):
        raise HTTPException(400, "Cannot delete yourself")
    db = _get_db()
    target = await db.users.find_one({"_id": _oid(user_id)})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("role") == "admin":
        active_admins = await db.users.count_documents({
            "role": "admin",
            "active": {"$ne": False},
            "_id": {"$ne": _oid(user_id)}
        })
        if active_admins == 0:
            raise HTTPException(400, "Cannot delete or deactivate the last active administrator.")

    res = await db.users.update_one({"_id": _oid(user_id)}, {"$set": {"active": False}})
    # F-028: Check matched_count and return 404 when user does not exist
    if res.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}
