"""Supabase Official Client Integration Helper."""

import os
import logging
from typing import Optional, Any

try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None

log = logging.getLogger(__name__)

_supabase_client: Optional[Any] = None


def get_supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip()


def get_supabase_key() -> str:
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    ).strip()


def is_cloud_allowed() -> bool:
    """Return True only when running on GitHub Actions, Production, or explicitly permitted."""
    is_github = os.environ.get("GITHUB_ACTIONS", "").lower() == "true" or os.environ.get("CI", "").lower() == "true"
    env = os.environ.get("ENVIRONMENT", "development").lower()
    allow_dev = os.environ.get("ALLOW_CLOUD_IN_DEV", "").lower() == "true"
    return is_github or env == "production" or allow_dev


def is_supabase_configured() -> bool:
    """Check if Supabase URL and Key are configured."""
    url = get_supabase_url()
    # Guard: dev servers strictly use local database; cloud Supabase is reserved for GitHub / Production
    if "supabase.co" in url and not is_cloud_allowed():
        return False
    return bool(url and get_supabase_key() and create_client is not None)


def get_supabase_client():
    """Retrieve or initialize the Supabase client instance."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if not is_supabase_configured():
        return None

    try:
        url = get_supabase_url()
        key = get_supabase_key()
        _supabase_client = create_client(url, key)
        log.info("Initialized official Supabase client for %s", url)
        return _supabase_client
    except Exception as e:
        log.warning("Could not initialize Supabase client: %s", e)
        return None


async def test_supabase_connection() -> dict:
    """Test connection to Supabase instance."""
    url = get_supabase_url()
    if "supabase.co" in url and not is_cloud_allowed():
        return {
            "configured": False,
            "connected": False,
            "mode": "local_dev_isolated",
            "message": "Dev servers are isolated to local storage. Supabase Cloud will only be used when pushed to GitHub / Production.",
        }

    client = get_supabase_client()
    if not client:
        return {
            "configured": False,
            "connected": False,
            "mode": "local_dev_isolated",
            "message": "Supabase credentials are not active in local development. Using local database.",
        }

    try:
        # Lightweight ping query against chart_of_accounts or auth
        response = client.table("chart_of_accounts").select("code").limit(1).execute()
        return {
            "configured": True,
            "connected": True,
            "url": get_supabase_url(),
            "data": response.data,
        }
    except Exception as e:
        return {
            "configured": True,
            "connected": False,
            "url": get_supabase_url(),
            "error": str(e),
        }
