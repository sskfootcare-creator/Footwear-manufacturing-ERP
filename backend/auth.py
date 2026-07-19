"""Auth helpers: password hashing, JWT, current user dependency, admin seed.

Environment-gated admin seeding
================================
The ``ENVIRONMENT`` env var (values: ``development`` | ``test`` | ``production``,
default ``development``) controls which admin accounts are seeded at startup:

+---------------------------+-------------+------+---------------+
| Account                   | development | test | production    |
+===========================+=============+======+===============+
| env-driven admin          | ✓           | ✓    | ✓ (required!) |
| admin@sskfootcare.com     | ✓           | ✓    | ✗  (skipped)  |
| admin@example.com         | ✓           | ✗    | ✗  (skipped)  |
+---------------------------+-------------+------+===============+

Production startup will raise ``RuntimeError`` if ``ADMIN_PASSWORD`` is unset,
preventing the server from booting with the insecure default credential.
"""
import os
import sys
import logging
import re
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request
from bson import ObjectId

log = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_HOURS = 12
REFRESH_TOKEN_DAYS = 7

# ── Valid values for ENVIRONMENT ──────────────────────────────────────────────
_VALID_ENVIRONMENTS = {"development", "test", "production"}

# ── Hardcoded test/dev seed accounts (never used in production) ───────────────
_SSK_SEED_EMAIL    = "admin@sskfootcare.com"
_SSK_SEED_PASSWORD = "Admin@123"
_EXAMPLE_SEED_EMAIL    = "admin@example.com"
_EXAMPLE_SEED_PASSWORD = "admin123"


def get_environment() -> str:
    """Return the normalised ENVIRONMENT value, defaulting to 'development'."""
    env = os.environ.get("ENVIRONMENT", "development").strip().lower()
    if env not in _VALID_ENVIRONMENTS:
        log.warning(
            f"ENVIRONMENT='{env}' is not a recognised value "
            f"({', '.join(sorted(_VALID_ENVIRONMENTS))}). Defaulting to 'development'."
        )
        return "development"
    return env


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def validate_password(password: str) -> None:
    """Enforce minimum password policy: at least 8 characters.
    Raises HTTPException 422 on violation.
    """
    if not password or len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters long.")


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_HOURS),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response, access_token: str, refresh_token: str = None):
    secure = True
    if os.environ.get("JWT_SECRET") == "supersecretjwtkey12345!" or os.environ.get("COOKIE_SECURE", "true").lower() == "false":
        secure = False
    samesite = "none" if secure else "lax"
    response.set_cookie(
        "access_token", access_token, httponly=True, secure=secure,
        samesite=samesite, max_age=ACCESS_TOKEN_HOURS * 3600, path="/"
    )
    if refresh_token:
        response.set_cookie(
            "refresh_token", refresh_token, httponly=True, secure=secure,
            samesite=samesite, max_age=REFRESH_TOKEN_DAYS * 24 * 3600, path="/"
        )


def clear_auth_cookies(response):
    secure = True
    if os.environ.get("JWT_SECRET") == "supersecretjwtkey12345!" or os.environ.get("COOKIE_SECURE", "true").lower() == "false":
        secure = False
    samesite = "none" if secure else "lax"
    response.delete_cookie("access_token", path="/", secure=secure, samesite=samesite)
    response.delete_cookie("refresh_token", path="/", secure=secure, samesite=samesite)


def _extract_token(request: Request) -> str | None:
    tok = request.cookies.get("access_token")
    if tok:
        return tok
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def get_current_user_factory(db):
    async def _get_current_user(request: Request) -> dict:
        token = _extract_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                raise HTTPException(status_code=401, detail="Invalid token type")
            user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            user["id"] = str(user["_id"])
            user.pop("_id", None)
            user.pop("password_hash", None)
            return user
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    return _get_current_user


def require_roles(*allowed_roles: str):
    def checker(user: dict):
        if user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


async def _upsert_admin(db, email: str, password: str, name: str, label: str) -> str:
    """Insert or re-sync one admin account. Returns 'seeded', 'updated', or 'exists'."""
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one({
            "email": email,
            "password_hash": hash_password(password),
            "name": name,
            "role": "admin",
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info(f"[seed_admin] Seeded {label} ({email})")
        return "seeded"
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one(
            {"email": email},
            {"$set": {"password_hash": hash_password(password)}},
        )
        log.info(f"[seed_admin] Updated password for {label} ({email})")
        return "updated"
    else:
        log.debug(f"[seed_admin] {label} ({email}) already exists — skipped")
        return "exists"


async def seed_admin(db) -> None:
    """Environment-gated admin seeding.

    Reads ENVIRONMENT (development | test | production, default development).

    production
    ----------
    - ADMIN_PASSWORD *must* be set; if missing the process aborts with
      RuntimeError (boot-fail-fast rather than silently use a weak default).
    - Only the env-configured admin is seeded.
    - The two hardcoded dev/test accounts are never touched.

    test
    ----
    - Env-configured admin + admin@sskfootcare.com are seeded.
    - admin@example.com is skipped.

    development  (default)
    ----------------------
    - All three accounts are seeded (preserves previous behaviour).
    """
    environment = get_environment()
    log.info(f"[seed_admin] ENVIRONMENT={environment}")

    # ── Validate env-admin config ─────────────────────────────────────────────
    admin_email    = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if environment == "production":
        if not admin_password:
            # Hard abort — do NOT start with a weak or missing password in prod.
            raise RuntimeError(
                "FATAL: ADMIN_PASSWORD environment variable is not set. "
                "The server refuses to start in production without an explicit "
                "admin password. Set ADMIN_PASSWORD in your deployment secrets."
            )
        if admin_password == _EXAMPLE_SEED_PASSWORD:
            log.warning(
                "[seed_admin] ADMIN_PASSWORD is set to the insecure default 'admin123'. "
                "Change it immediately."
            )

    # Fall back to insecure default only in non-production environments
    if not admin_password:
        admin_password = _EXAMPLE_SEED_PASSWORD   # "admin123" — dev/test only

    # ── 1. Env-driven admin (all environments) ────────────────────────────────
    await _upsert_admin(db, admin_email, admin_password, "Admin", "env-admin")

    # ── 2. SSK pytest admin (development + test only) ─────────────────────────
    if environment in ("development", "test"):
        await _upsert_admin(
            db, _SSK_SEED_EMAIL, _SSK_SEED_PASSWORD,
            "Test Admin", "ssk-test-admin"
        )
    else:
        log.info(f"[seed_admin] SKIPPED ssk-test-admin ({_SSK_SEED_EMAIL}) — environment={environment}")

    # ── 3. Example/fallback admin (development only) ──────────────────────────
    if environment == "development" and admin_email != _EXAMPLE_SEED_EMAIL:
        await _upsert_admin(
            db, _EXAMPLE_SEED_EMAIL, _EXAMPLE_SEED_PASSWORD,
            "Example Admin", "example-admin"
        )
    elif environment != "development":
        log.info(f"[seed_admin] SKIPPED example-admin ({_EXAMPLE_SEED_EMAIL}) — environment={environment}")

    log.info(f"[seed_admin] Done for environment={environment}")
