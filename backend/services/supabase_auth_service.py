"""Supabase Auth Integration Service with Circuit Breaker."""

import time
import logging
from typing import Optional, Dict, Any, Tuple
from db.supabase_client import get_supabase_admin_client, get_supabase_anon_client

log = logging.getLogger(__name__)

_supabase_offline_until: float = 0.0
SUPABASE_COOLDOWN_SECONDS: float = 60.0


def is_supabase_available() -> bool:
    """Return False if Supabase recently failed connectivity, avoiding blocking socket timeouts."""
    return time.time() >= _supabase_offline_until


def mark_supabase_failed(err: Optional[Exception] = None) -> None:
    """Trip the circuit breaker for SUPABASE_COOLDOWN_SECONDS."""
    global _supabase_offline_until
    _supabase_offline_until = time.time() + SUPABASE_COOLDOWN_SECONDS
    if err:
        log.warning("Supabase connectivity failed (%s); silencing calls for %ds", err, int(SUPABASE_COOLDOWN_SECONDS))


def find_supabase_user_by_email(email: str) -> Optional[Any]:
    """Look up a user in Supabase Auth by email address."""
    if not is_supabase_available():
        return None
    client = get_supabase_admin_client()
    if not client:
        return None
    try:
        clean_email = email.strip().lower()
        users = client.auth.admin.list_users()
        for u in users:
            if getattr(u, "email", "").strip().lower() == clean_email:
                return u
        return None
    except Exception as e:
        mark_supabase_failed(e)
        return None


def create_or_sync_supabase_user(
    email: str,
    password: Optional[str] = None,
    name: str = "",
    role: str = "custom",
    allowed_modules: Optional[list] = None,
) -> Optional[Any]:
    """
    Ensure user exists in Supabase Auth (auth.users).
    If missing, creates it with confirmed email.
    If existing and password is provided, updates credentials.
    """
    if not is_supabase_available():
        return None
    client = get_supabase_admin_client()
    if not client:
        return None

    clean_email = email.strip().lower()
    meta = {
        "name": name,
        "role": role,
    }
    if allowed_modules is not None:
        meta["allowed_modules"] = allowed_modules

    try:
        existing = find_supabase_user_by_email(clean_email)
        if existing:
            update_kwargs: Dict[str, Any] = {"user_metadata": meta}
            if password:
                update_kwargs["password"] = password
            res = client.auth.admin.update_user_by_id(existing.id, update_kwargs)
            log.info("Updated Supabase Auth user %s (uid=%s)", clean_email, existing.id)
            return getattr(res, "user", res)
        else:
            if not password:
                import secrets
                password = secrets.token_urlsafe(16)
            res = client.auth.admin.create_user({
                "email": clean_email,
                "password": password,
                "email_confirm": True,
                "user_metadata": meta,
            })
            user_obj = getattr(res, "user", res)
            log.info("Created Supabase Auth user %s (uid=%s)", clean_email, getattr(user_obj, "id", "unknown"))
            return user_obj
    except Exception as e:
        mark_supabase_failed(e)
        return None


def authenticate_with_supabase(email: str, password: str) -> Optional[Any]:
    """
    Authenticate against Supabase Auth using email and password.
    Returns the Supabase AuthResponse object (containing session, user) on success, or None.
    """
    if not is_supabase_available():
        return None
    client = get_supabase_anon_client() or get_supabase_admin_client()
    if not client:
        return None

    try:
        res = client.auth.sign_in_with_password({
            "email": email.strip().lower(),
            "password": password,
        })
        if getattr(res, "session", None) is not None:
            return res
        return None
    except Exception as e:
        mark_supabase_failed(e)
        return None


def verify_supabase_token(token: str) -> Optional[Any]:
    """
    Verify a Supabase JWT token and return the authenticated User object, or None if invalid.
    """
    if not is_supabase_available():
        return None
    client = get_supabase_admin_client()
    if not client or not token:
        return None

    try:
        res = client.auth.get_user(token)
        return getattr(res, "user", res)
    except Exception as e:
        mark_supabase_failed(e)
        return None


def delete_supabase_user(user_id: str) -> bool:
    """Delete a user from Supabase Auth."""
    if not is_supabase_available():
        return False
    client = get_supabase_admin_client()
    if not client or not user_id:
        return False
    try:
        client.auth.admin.delete_user(user_id)
        log.info("Deleted Supabase Auth user %s", user_id)
        return True
    except Exception as e:
        mark_supabase_failed(e)
        return False

