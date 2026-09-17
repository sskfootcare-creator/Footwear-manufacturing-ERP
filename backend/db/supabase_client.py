"""Supabase Client Singleton & Accessor."""

import os
import logging
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment from root or backend directory
load_dotenv()
_backend_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(_backend_env):
    load_dotenv(_backend_env)

log = logging.getLogger(__name__)

_admin_client: Optional[Client] = None
_anon_client: Optional[Client] = None


def get_supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip()


def get_supabase_service_role_key() -> str:
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or ""
    ).strip()


def get_supabase_anon_key() -> str:
    return (
        os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or ""
    ).strip()


def get_supabase_admin_client() -> Optional[Client]:
    """Return Supabase client with service_role privileges for server-side administration."""
    global _admin_client
    if _admin_client is not None:
        return _admin_client

    url = get_supabase_url()
    key = get_supabase_service_role_key()

    if not url or not key:
        log.warning("Supabase URL or Service Role Key not configured; Supabase client unavailable.")
        return None

    try:
        _admin_client = create_client(url, key)
        log.info("Supabase Admin Client initialized for URL: %s", url)
        return _admin_client
    except Exception as e:
        log.error("Failed to initialize Supabase Admin Client: %s", e)
        return None


def get_supabase_anon_client() -> Optional[Client]:
    """Return Supabase client with anonymous/authenticated privileges."""
    global _anon_client
    if _anon_client is not None:
        return _anon_client

    url = get_supabase_url()
    key = get_supabase_anon_key()

    if not url or not key:
        return None

    try:
        _anon_client = create_client(url, key)
        return _anon_client
    except Exception as e:
        log.error("Failed to initialize Supabase Anon Client: %s", e)
        return None
