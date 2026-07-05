"""Iteration 15 — Vendor Master CRUD + RBAC tests.

Run with:
    cd backend && .venv/Scripts/pytest tests/test_iteration15_vendors.py -v
"""
import pytest
import httpx

BASE = "http://localhost:8000/api"
TIMEOUT = 15


# ── helpers ──────────────────────────────────────────────────────────────────

def admin_cookies() -> dict:
    """Return session cookies for the seeded admin account."""
    r = httpx.post(f"{BASE}/auth/login", json={"email": "admin@sskfootcare.com", "password": "Admin@123"},
                   timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return dict(r.cookies)


def login_as(email: str, password: str) -> dict:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=TIMEOUT)
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return dict(r.cookies)


@pytest.fixture(scope="module")
def admin_session():
    return admin_cookies()


@pytest.fixture(scope="module")
def vendor_id(admin_session):
    """Create a test vendor and return its id; cleaned up at module teardown."""
    r = httpx.post(f"{BASE}/vendors",
                   json={
                       "name": "Test Vendor Iteration15",
                       "gstin": "27AADCB9999M1ZZ",
                       "contact_person": "Ravi Kumar",
                       "phone": "9876543210",
                       "address": "123 Dharavi, Mumbai, MH 400017",
                       "payment_terms_days": 45,
                       "notes": "Pytest fixture vendor",
                   },
                   cookies=admin_session, timeout=TIMEOUT)
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    yield vid
    # teardown — deactivate (soft delete)
    httpx.delete(f"{BASE}/vendors/{vid}", cookies=admin_session, timeout=TIMEOUT)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestVendorCRUD:

    def test_create_vendor_returns_201(self, admin_session, vendor_id):
        """Fixture already called POST; just assert id is a non-empty string."""
        assert vendor_id and len(vendor_id) == 24  # MongoDB ObjectId length

    def test_list_vendors_includes_created(self, admin_session, vendor_id):
        r = httpx.get(f"{BASE}/vendors", cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert vendor_id in ids, "Newly created vendor not in list"

    def test_get_single_vendor(self, admin_session, vendor_id):
        r = httpx.get(f"{BASE}/vendors/{vendor_id}", cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 200
        v = r.json()
        assert v["name"] == "Test Vendor Iteration15"
        assert v["gstin"] == "27AADCB9999M1ZZ"
        assert v["payment_terms_days"] == 45
        assert v["active"] is True

    def test_patch_vendor_updates_fields(self, admin_session, vendor_id):
        r = httpx.patch(f"{BASE}/vendors/{vendor_id}",
                        json={"phone": "1111111111", "payment_terms_days": 60},
                        cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 200
        v = r.json()
        assert v["phone"] == "1111111111"
        assert v["payment_terms_days"] == 60

    def test_list_default_excludes_inactive(self, admin_session, vendor_id):
        """After a soft-delete, the default list should omit it."""
        # First soft-delete via DELETE endpoint
        r_del = httpx.delete(f"{BASE}/vendors/{vendor_id}", cookies=admin_session, timeout=TIMEOUT)
        assert r_del.status_code == 200
        assert r_del.json().get("ok") is True

        # Default list should exclude it
        r_list = httpx.get(f"{BASE}/vendors", cookies=admin_session, timeout=TIMEOUT)
        ids = [v["id"] for v in r_list.json()]
        assert vendor_id not in ids, "Deactivated vendor should not appear in default list"

        # include_inactive=true should show it
        r_all = httpx.get(f"{BASE}/vendors", params={"include_inactive": "true"},
                          cookies=admin_session, timeout=TIMEOUT)
        ids_all = [v["id"] for v in r_all.json()]
        assert vendor_id in ids_all, "Deactivated vendor missing from include_inactive list"

        # Re-activate so the fixture teardown doesn't 404
        httpx.patch(f"{BASE}/vendors/{vendor_id}", json={"active": True},
                    cookies=admin_session, timeout=TIMEOUT)

    def test_get_nonexistent_vendor_returns_404(self, admin_session):
        r = httpx.get(f"{BASE}/vendors/000000000000000000000000", cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 404

    def test_patch_nonexistent_vendor_returns_404(self, admin_session):
        r = httpx.patch(f"{BASE}/vendors/000000000000000000000000",
                        json={"name": "Ghost"}, cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code == 404


class TestVendorRBAC:

    @pytest.fixture(scope="class")
    def manager_cookies(self, admin_session):
        """Create a temporary manager user and return its session cookies."""
        # Create manager via admin
        r = httpx.post(f"{BASE}/users",
                       json={"email": "mgr_v15@ssk.com", "password": "Manager@1234",
                             "name": "Mgr V15", "role": "manager"},
                       cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code in (200, 201, 409), r.text
        cookies = login_as("mgr_v15@ssk.com", "Manager@1234")
        yield cookies

    @pytest.fixture(scope="class")
    def prod_cookies(self, admin_session):
        """Create a temporary production user."""
        r = httpx.post(f"{BASE}/users",
                       json={"email": "prod_v15@ssk.com", "password": "Prod@1234",
                             "name": "Prod V15", "role": "production"},
                       cookies=admin_session, timeout=TIMEOUT)
        assert r.status_code in (200, 201, 409), r.text
        return login_as("prod_v15@ssk.com", "Prod@1234")

    def test_manager_can_create_vendor(self, manager_cookies):
        r = httpx.post(f"{BASE}/vendors",
                       json={"name": "Manager Created Vendor V15", "payment_terms_days": 30},
                       cookies=manager_cookies, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        # cleanup
        vid = r.json()["id"]
        admin = admin_cookies()
        httpx.delete(f"{BASE}/vendors/{vid}", cookies=admin, timeout=TIMEOUT)

    def test_manager_can_patch_vendor(self, vendor_id, manager_cookies):
        r = httpx.patch(f"{BASE}/vendors/{vendor_id}",
                        json={"notes": "Updated by manager"},
                        cookies=manager_cookies, timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_production_can_read_vendors(self, prod_cookies):
        r = httpx.get(f"{BASE}/vendors", cookies=prod_cookies, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_production_cannot_create_vendor(self, prod_cookies):
        r = httpx.post(f"{BASE}/vendors",
                       json={"name": "Unauthorized Vendor", "payment_terms_days": 30},
                       cookies=prod_cookies, timeout=TIMEOUT)
        assert r.status_code == 403, f"Expected 403 but got {r.status_code}"

    def test_production_cannot_patch_vendor(self, vendor_id, prod_cookies):
        r = httpx.patch(f"{BASE}/vendors/{vendor_id}",
                        json={"name": "Hacked Name"}, cookies=prod_cookies, timeout=TIMEOUT)
        assert r.status_code == 403, f"Expected 403 but got {r.status_code}"

    def test_manager_cannot_delete_vendor(self, vendor_id, manager_cookies):
        """Only admin can soft-delete."""
        r = httpx.delete(f"{BASE}/vendors/{vendor_id}", cookies=manager_cookies, timeout=TIMEOUT)
        assert r.status_code == 403, f"Expected 403 but got {r.status_code}"

    def test_admin_can_delete_vendor(self, vendor_id):
        admin = admin_cookies()
        r = httpx.delete(f"{BASE}/vendors/{vendor_id}", cookies=admin, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # Restore active status for later tests
        httpx.patch(f"{BASE}/vendors/{vendor_id}", json={"active": True}, cookies=admin, timeout=TIMEOUT)
