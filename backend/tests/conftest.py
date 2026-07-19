"""Root conftest.py for the backend test suite.

Provides canonical credential fixtures so every test module reads from the
same environment variables (ADMIN_EMAIL, ADMIN_PASSWORD) rather than
scattering hardcoded strings across test files.

Running tests
-------------
The defaults match the seeded admin@sskfootcare.com / Admin@123 account that
``seed_admin()`` creates in ``development`` and ``test`` environments.  Override
via environment variables if your deployment uses different credentials:

    ADMIN_EMAIL=myuser@company.com ADMIN_PASSWORD=MySecretPw pytest tests/ -v

CI / test environment
---------------------
Set ``ENVIRONMENT=test`` in your CI configuration so the server seeds only the
accounts needed by the test suite and never creates the example.com fallback.
"""

import os
import pytest
import requests
import httpx

# ── Canonical test credentials ────────────────────────────────────────────────
# Read from env; fall back to the well-known dev/test account seeded by
# seed_admin() when ENVIRONMENT is 'development' or 'test'.
TEST_ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL",    "admin@sskfootcare.com")
TEST_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
BASE_URL            = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API_URL             = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def test_admin_email() -> str:
    """The admin email address used to authenticate against the running server."""
    return TEST_ADMIN_EMAIL


@pytest.fixture(scope="session")
def test_admin_password() -> str:
    """The admin password used to authenticate against the running server."""
    return TEST_ADMIN_PASSWORD


@pytest.fixture(scope="session")
def base_url() -> str:
    """Backend base URL (no trailing slash)."""
    return BASE_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    """Backend API URL (= base_url + /api, no trailing slash)."""
    return API_URL


@pytest.fixture(scope="session")
def admin_requests_session(test_admin_email, test_admin_password, api_url):
    """Authenticated ``requests.Session`` (session-scoped) for integration tests."""
    s = requests.Session()
    r = s.post(
        f"{api_url}/auth/login",
        json={"email": test_admin_email, "password": test_admin_password},
        timeout=30,
    )
    assert r.status_code == 200, (
        f"conftest: admin login failed ({r.status_code}): {r.text}\n"
        f"Email: {test_admin_email} — check ADMIN_EMAIL / ADMIN_PASSWORD env vars "
        f"and ensure the server is running with ENVIRONMENT=test or development."
    )
    return s


@pytest.fixture(scope="session")
def admin_httpx_cookies(test_admin_email, test_admin_password, api_url) -> dict:
    """Authenticated cookie dict via httpx (session-scoped) for tests using httpx."""
    r = httpx.post(
        f"{api_url}/auth/login",
        json={"email": test_admin_email, "password": test_admin_password},
        timeout=30,
    )
    assert r.status_code == 200, (
        f"conftest: admin login failed ({r.status_code}): {r.text}\n"
        f"Email: {test_admin_email} — check ADMIN_EMAIL / ADMIN_PASSWORD env vars."
    )
    return dict(r.cookies)
