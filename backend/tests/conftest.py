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


class AuthenticatedSession(requests.Session):
    def __init__(self, login_url, email, password):
        super().__init__()
        self.login_url = login_url
        self.email = email
        self.password = password

    def request(self, method, url, *args, **kwargs):
        res = super().request(method, url, *args, **kwargs)
        if res.status_code == 401 and "/auth/login" not in str(url):
            login_res = super().request(
                "POST",
                self.login_url,
                json={"email": self.email, "password": self.password},
                timeout=30,
            )
            if login_res.status_code == 200:
                try:
                    tok = login_res.json().get("access_token")
                    if tok:
                        self.headers["Authorization"] = f"Bearer {tok}"
                except Exception:
                    pass
                res = super().request(method, url, *args, **kwargs)
        return res


@pytest.fixture(scope="session")
def admin_requests_session(test_admin_email, test_admin_password, api_url):
    """Authenticated ``requests.Session`` (session-scoped) for integration tests with auto-relogin."""
    login_url = f"{api_url}/auth/login"
    s = AuthenticatedSession(login_url, test_admin_email, test_admin_password)
    try:
        r = s.post(
            login_url,
            json={"email": test_admin_email, "password": test_admin_password},
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        pytest.skip(f"Live backend server not running at {api_url}")
    if r.status_code != 200:
        pytest.skip(f"conftest: admin login failed ({r.status_code}): {r.text}")
    try:
        tok = r.json().get("access_token")
        if tok:
            s.headers["Authorization"] = f"Bearer {tok}"
    except Exception:
        pass
    return s


@pytest.fixture(scope="session")
def admin_httpx_cookies(test_admin_email, test_admin_password, api_url) -> dict:
    """Authenticated cookie dict via httpx (session-scoped) for tests using httpx."""
    try:
        r = httpx.post(
            f"{api_url}/auth/login",
            json={"email": test_admin_email, "password": test_admin_password},
            timeout=10,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        pytest.skip(f"Live backend server not running at {api_url}")
    if r.status_code != 200:
        pytest.skip(f"conftest: admin login failed ({r.status_code}): {r.text}")
    return dict(r.cookies)


@pytest.fixture(autouse=True)
def clean_db_state():
    """Ensure mock DB assignments on app.mongodb or server.db do not leak across tests."""
    import server

    db_name = os.environ.get("DB_NAME", "ssk_ci_db")
    real_db = server.client[db_name] if hasattr(server, "client") and server.client is not None else None

    # Reset before test
    if hasattr(server.app, "mongodb"):
        try:
            delattr(server.app, "mongodb")
        except AttributeError:
            pass
    if real_db is not None:
        server.db = real_db

    yield

    # Reset after test
    if hasattr(server.app, "mongodb"):
        try:
            delattr(server.app, "mongodb")
        except AttributeError:
            pass
    if real_db is not None:
        server.db = real_db

