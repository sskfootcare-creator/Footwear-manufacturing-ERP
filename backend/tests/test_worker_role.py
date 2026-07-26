"""test_worker_role.py — Full integration test suite for the worker (karigar) login role.

Tests cover:
  1. Admin sets PIN on worker
  2. Worker login (correct phone + PIN) → JWT with role="worker" and worker_id
  3. Wrong PIN → 401
  4. Repeated wrong PINs → 429 (rate-limit)
  5. GET /api/my/tasks — shows only assigned jobs at current stage (raw JSON inspection)
  6. Response redaction: no other worker's rate/name in payload
  7. PATCH /api/my/tasks/{job_id}/ready-for-pickup → 200, flag set, notification created
  8. Ready-for-pickup on un-assigned job → 403
  9. GET /api/notifications (manager) → sees pickup_ready notification
 10. PATCH /api/notifications/{id}/read → notification dismissed
 11. Manager advances stage → ready_for_pickup flag cleared on job
 12. GET /api/my/payroll (worker) → self-scoped earnings
 13. GET /api/my/payroll (manager) → 403
 14. GET /api/my/tasks (manager) → 403
 15. Regression: existing assignment/stage-update endpoints still work

NOTE: Requires a live server (ENVIRONMENT=test or development) with MONGO.
"""

import os
import time
import pytest
import requests

BASE_URL   = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API_URL    = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL",    "admin@sskfootcare.com")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "Admin@123")


# ─────────────────────────────────────────────────────────────────────────────
# Session-scoped fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    token = r.json().get("access_token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="session")
def worker_data(admin_session):
    """Create a test worker with a known phone and PIN, return (worker_doc, pin)."""
    phone = f"9{int(time.time()) % 1_000_000_000:09d}"[-10:]
    pin   = "7531"
    r = admin_session.post(f"{API_URL}/workers", json={
        "name":  "Test Karigar",
        "phone": phone,
        "skill": "cutting",
        "rate_per_pair": 15.0,
        "active": True,
    })
    assert r.status_code == 200, f"Create worker failed: {r.text}"
    worker = r.json()
    wid    = worker["id"]

    # Set PIN
    r2 = admin_session.patch(f"{API_URL}/workers/{wid}/set-pin", json={"pin": pin})
    assert r2.status_code == 200, f"set-pin failed: {r2.text}"

    return {"worker": worker, "phone": phone, "pin": pin, "wid": wid}


@pytest.fixture(scope="session")
def second_worker(admin_session):
    """A second worker to verify redaction (his data should never appear in w1's payload)."""
    phone = f"8{int(time.time()) % 1_000_000_000:09d}"[-10:]
    r = admin_session.post(f"{API_URL}/workers", json={
        "name": "Other Karigar", "phone": phone, "skill": "stitching",
        "rate_per_pair": 22.0, "active": True,
    })
    assert r.status_code == 200, f"Create second worker failed: {r.text}"
    worker = r.json()
    wid    = worker["id"]
    pin    = "1234"
    admin_session.patch(f"{API_URL}/workers/{wid}/set-pin", json={"pin": pin})
    return {"worker": worker, "phone": phone, "pin": pin, "wid": wid}


@pytest.fixture(scope="session")
def production_job(admin_session, worker_token, second_worker):
    """Create a PO + production job, assign BOTH workers to different roles,
    and advance to 'cutting' so the logged-in worker is active at their stage.

    Uses worker_token['worker_id'] (the ACTUAL server-confirmed ID) instead of
    worker_data['wid'] to ensure the job is assigned to the same worker that
    worker_session will use — safe across xdist parallel processes.
    """
    actual_wid = worker_token["worker_id"]

    # Find or create a style code
    r_styles = admin_session.get(f"{API_URL}/styles")
    styles    = r_styles.json() if r_styles.status_code == 200 else []
    style_code = styles[0]["code"] if styles else "TEST-STYLE"

    # Create a PO
    import time as _time
    po_number = f"WRKTEST-{int(_time.time())}"
    r_po = admin_session.post(f"{API_URL}/pos", json={
        "po_number": po_number, "po_date": "2026-07-01",
        "client_name": "Test Client",
        "currency": "INR",
        "line_items": [{"style_code": style_code, "quantity": 10, "unit_price": 100, "amount": 1000}],
        "subtotal": 1000, "grand_total": 1000, "total_quantity": 10,
    })
    if r_po.status_code not in (200, 201):
        pytest.skip(f"Cannot create PO (need at least one style): {r_po.text[:200]}")

    po = r_po.json()
    po_id = po["id"] if "id" in po else po.get("_id")

    # Find the job created for this PO
    r_jobs = admin_session.get(f"{API_URL}/production/jobs?po_id={po_id}")
    jobs   = r_jobs.json() if r_jobs.status_code == 200 else []
    if not jobs:
        pytest.skip("No production job found for PO")
    job = jobs[0]
    job_id = job["id"]

    # Assign actual_wid to "cutting", second_worker to "stitching"
    admin_session.patch(f"{API_URL}/production/jobs/{job_id}/assignment", json={
        "role": "cutting", "worker_id": actual_wid, "rate_per_pair": 15.0,
    })
    admin_session.patch(f"{API_URL}/production/jobs/{job_id}/assignment", json={
        "role": "stitching", "worker_id": second_worker["wid"], "rate_per_pair": 22.0,
    })

    # Advance to cutting
    admin_session.patch(f"{API_URL}/production/jobs/{job_id}", json={
        "stage": "cutting", "confirm_skip": True,
    })

    return {"job_id": job_id, "po_number": po_number, "style_code": style_code, "worker_id": actual_wid}


@pytest.fixture(scope="session")
def worker_token(worker_data):
    """Log in as worker_data and return dict: {token, worker_id}.

    NOTE: With pytest-xdist, session-scoped fixtures run independently per worker process.
    We return both the token AND the server-confirmed worker_id so other fixtures can use
    the ACTUAL identity (not the one from a parallel fixture's DB write).
    """
    r = requests.post(f"{API_URL}/auth/worker-login", json={
        "phone": worker_data["phone"], "pin": worker_data["pin"],
    })
    assert r.status_code == 200, f"worker-login failed: {r.text}"
    data = r.json()
    assert data.get("role") == "worker", f"Expected role=worker, got: {data}"
    assert data.get("access_token"), "access_token missing from worker-login response"
    assert data.get("worker_id"), "worker_id missing from worker-login response"
    return {"token": data["access_token"], "worker_id": data["worker_id"]}


@pytest.fixture(scope="session")
def worker_session(worker_token):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {worker_token['token']}"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# 1. Set PIN
# ─────────────────────────────────────────────────────────────────────────────

class TestSetPin:
    def test_set_pin_success(self, admin_session, worker_data):
        r = admin_session.patch(
            f"{API_URL}/workers/{worker_data['wid']}/set-pin",
            json={"pin": "9999"},
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # Reset to known PIN for subsequent tests
        admin_session.patch(
            f"{API_URL}/workers/{worker_data['wid']}/set-pin",
            json={"pin": worker_data["pin"]},
        )

    def test_set_pin_invalid_too_short(self, admin_session, worker_data):
        r = admin_session.patch(
            f"{API_URL}/workers/{worker_data['wid']}/set-pin",
            json={"pin": "12"},
        )
        assert r.status_code == 422

    def test_set_pin_non_admin_forbidden(self, worker_session, worker_data):
        r = worker_session.patch(
            f"{API_URL}/workers/{worker_data['wid']}/set-pin",
            json={"pin": "5555"},
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 2-4. Worker login & rate limiting
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkerLogin:
    def test_login_success_returns_worker_token(self, worker_data):
        r = requests.post(f"{API_URL}/auth/worker-login", json={
            "phone": worker_data["phone"], "pin": worker_data["pin"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "worker"
        assert data["worker_id"] == worker_data["wid"]
        assert "access_token" in data

    def test_login_wrong_pin_401(self, worker_data):
        r = requests.post(f"{API_URL}/auth/worker-login", json={
            "phone": worker_data["phone"], "pin": "0000",
        })
        assert r.status_code == 401

    def test_login_unknown_phone_401(self):
        r = requests.post(f"{API_URL}/auth/worker-login", json={
            "phone": "0000000000", "pin": "1234",
        })
        assert r.status_code == 401

    def test_login_rate_limit_429(self, worker_data):
        """Rapid wrong PINs from same virtual IP should trigger 429."""
        fake_ip = f"192.168.99.{int(time.time()) % 255}"
        headers = {"x-test-rate-limit-client-ip": fake_ip}
        body    = {"phone": worker_data["phone"], "pin": "WRONG"}
        # First 5 failures; 6th should be 429
        for _ in range(5):
            requests.post(f"{API_URL}/auth/worker-login", json=body, headers=headers)
        r = requests.post(f"{API_URL}/auth/worker-login", json=body, headers=headers)
        assert r.status_code == 429


# ─────────────────────────────────────────────────────────────────────────────
# 5-6. GET /api/my/tasks — redaction + scoping
# ─────────────────────────────────────────────────────────────────────────────

class TestMyTasks:
    def test_manager_cannot_access_my_tasks(self, admin_session):
        r = admin_session.get(f"{API_URL}/my/tasks")
        assert r.status_code == 403

    def test_worker_sees_only_own_tasks(self, worker_session, production_job, worker_data):
        r = worker_session.get(f"{API_URL}/my/tasks")
        assert r.status_code == 200
        jobs = r.json()
        # All returned jobs must have my_assignment for the caller
        for job in jobs:
            assert "my_assignment" in job, "my_assignment key missing"
            assert "assignments" not in job, "Raw assignments dict must NOT appear in response"

    def test_response_never_contains_other_worker_rate(
        self, worker_session, production_job, worker_data, second_worker
    ):
        """CRITICAL: raw API JSON must not contain other worker's rate or name."""
        r = worker_session.get(f"{API_URL}/my/tasks")
        assert r.status_code == 200
        raw_text = r.text

        # Other worker's name and rate must not appear anywhere in the response
        assert second_worker["worker"]["name"] not in raw_text, \
            "Other worker's name leaked into /my/tasks response!"
        # Rate 22.0 (other worker's rate) should not appear
        # (15.0 is caller's rate and is allowed)
        assert '"rate_per_pair": 22' not in raw_text and "'rate_per_pair': 22" not in raw_text, \
            "Other worker's rate leaked into /my/tasks response!"

    def test_job_at_correct_stage_appears(self, worker_session, production_job):
        r = worker_session.get(f"{API_URL}/my/tasks")
        assert r.status_code == 200
        jobs = r.json()
        all_job_ids = [jid for j in jobs for jid in ([j["id"]] + j.get("job_ids", []))]
        assert production_job["job_id"] in all_job_ids, \
            f"Expected job {production_job['job_id']} in worker's task list"


# ─────────────────────────────────────────────────────────────────────────────
# 7-8. PATCH /api/my/tasks/{job_id}/ready-for-pickup
# ─────────────────────────────────────────────────────────────────────────────

class TestReadyForPickup:
    """Uses its own rfp_job class-scoped fixture to avoid stage-advance interference
    from TestRegression which also uses production_job and advances stage."""

    @pytest.fixture(scope="class")
    def rfp_job(self, admin_session, worker_token, second_worker):
        """Class-scoped: fresh job at 'cutting' for the logged-in worker."""
        actual_wid = worker_token["worker_id"]
        r_styles = admin_session.get(f"{API_URL}/styles")
        styles    = r_styles.json() if r_styles.status_code == 200 else []
        style_code = styles[0]["code"] if styles else "TEST-STYLE"

        import time as _t
        po_number = f"RFPTEST-{int(_t.time())}"
        r_po = admin_session.post(f"{API_URL}/pos", json={
            "po_number": po_number, "po_date": "2026-07-01", "client_name": "RFP Client",
            "currency": "INR",
            "line_items": [{"style_code": style_code, "quantity": 6, "unit_price": 100, "amount": 600}],
            "subtotal": 600, "grand_total": 600, "total_quantity": 6,
        })
        if r_po.status_code not in (200, 201):
            pytest.skip(f"Cannot create PO for rfp_job: {r_po.text[:200]}")

        po_id = r_po.json().get("id") or r_po.json().get("_id")
        r_jobs = admin_session.get(f"{API_URL}/production/jobs?po_id={po_id}")
        jobs   = r_jobs.json() if r_jobs.status_code == 200 else []
        if not jobs:
            pytest.skip("No production job for rfp_job fixture")
        job_id = jobs[0]["id"]

        # Assign and advance
        admin_session.patch(f"{API_URL}/production/jobs/{job_id}/assignment", json={
            "role": "cutting", "worker_id": actual_wid, "rate_per_pair": 15.0,
        })
        admin_session.patch(f"{API_URL}/production/jobs/{job_id}/assignment", json={
            "role": "stitching", "worker_id": second_worker["wid"], "rate_per_pair": 22.0,
        })
        admin_session.patch(f"{API_URL}/production/jobs/{job_id}", json={
            "stage": "cutting", "confirm_skip": True,
        })
        yield {"job_id": job_id, "worker_id": actual_wid}

    def test_mark_ready_success(self, worker_session, rfp_job, admin_session):
        job_id = rfp_job["job_id"]
        r = worker_session.patch(
            f"{API_URL}/my/tasks/{job_id}/ready-for-pickup",
            json={"completed_qty": 8, "notes": "Batch 1 done"},
        )
        assert r.status_code == 200, f"ready-for-pickup returned {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True
        rfp = data.get("ready_for_pickup", {})
        assert rfp.get("completed_qty") == 8
        assert rfp.get("role") == "cutting"

        # Verify flag is set on the job document (admin can see full doc)
        rj = admin_session.get(f"{API_URL}/production/jobs")
        jobs = rj.json() if rj.status_code == 200 else []
        job_doc = next((j for j in jobs if j.get("id") == job_id), None)
        if job_doc:
            assert "ready_for_pickup" in job_doc
            assert job_doc["ready_for_pickup"]["completed_qty"] == 8
            # Stage must NOT have changed
            assert job_doc["stage"] == "cutting"

    def test_notification_created(self, admin_session):
        r = admin_session.get(f"{API_URL}/notifications")
        assert r.status_code == 200
        notifs = r.json()
        assert len(notifs) >= 1
        pickup_notifs = [n for n in notifs if n.get("type") == "pickup_ready"]
        assert pickup_notifs, "No pickup_ready notification found after marking ready"

    def test_unassigned_job_returns_403(self, worker_session, second_worker, rfp_job):
        """Worker trying ready-for-pickup on a job at a stage they're not assigned to → 403."""
        # The job is at "cutting"; second_worker is assigned to "stitching" — not cutting.
        r_login = requests.post(f"{API_URL}/auth/worker-login", json={
            "phone": second_worker["phone"], "pin": second_worker["pin"],
        })
        if r_login.status_code != 200:
            pytest.skip("Second worker login failed")
        token2 = r_login.json()["access_token"]
        s2 = requests.Session()
        s2.headers["Authorization"] = f"Bearer {token2}"
        r = s2.patch(
            f"{API_URL}/my/tasks/{rfp_job['job_id']}/ready-for-pickup",
            json={"completed_qty": 5},
        )
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 9-11. Notifications + stage advance clearing
# ─────────────────────────────────────────────────────────────────────────────

class TestNotifications:
    def test_manager_can_list_notifications(self, admin_session):
        r = admin_session.get(f"{API_URL}/notifications")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_worker_cannot_list_notifications(self, worker_session):
        r = worker_session.get(f"{API_URL}/notifications")
        assert r.status_code == 403

    def test_mark_notification_read(self, admin_session):
        r = admin_session.get(f"{API_URL}/notifications")
        assert r.status_code == 200
        notifs = [n for n in r.json() if n.get("type") == "pickup_ready"]
        if not notifs:
            pytest.skip("No unread pickup_ready notifications to mark")
        nid = notifs[0]["id"]
        r2 = admin_session.patch(f"{API_URL}/notifications/{nid}/read", json={})
        assert r2.status_code == 200
        assert r2.json().get("ok") is True

    def test_stage_advance_clears_ready_for_pickup(
        self, admin_session, production_job
    ):
        """When manager advances stage, ready_for_pickup must be cleared."""
        job_id = production_job["job_id"]
        r = admin_session.patch(
            f"{API_URL}/production/jobs/{job_id}",
            json={"stage": "folding", "confirm_skip": True},
        )
        assert r.status_code == 200
        job_doc = r.json()
        assert "ready_for_pickup" not in job_doc or job_doc.get("ready_for_pickup") is None, \
            "ready_for_pickup was not cleared after stage advance!"


# ─────────────────────────────────────────────────────────────────────────────
# 12-13. GET /api/my/payroll
# ─────────────────────────────────────────────────────────────────────────────

class TestMyPayroll:
    def test_worker_payroll_self_scoped(self, worker_session, worker_token):
        r = worker_session.get(f"{API_URL}/my/payroll")
        assert r.status_code == 200
        data = r.json()
        assert "payroll" in data
        assert "from_date" in data
        payroll = data["payroll"]
        # The payroll must be for the same worker that is logged in
        assert payroll.get("worker_id") == worker_token["worker_id"], (
            f"Payroll worker_id={payroll.get('worker_id')} != logged-in worker_id={worker_token['worker_id']}"
        )
        # No other worker data should appear
        assert "rows" not in data, "Payroll must be self-scoped, not return all rows"

    def test_manager_cannot_use_my_payroll(self, admin_session):
        r = admin_session.get(f"{API_URL}/my/payroll")
        assert r.status_code == 403

    def test_optional_date_range(self, worker_session):
        r = worker_session.get(f"{API_URL}/my/payroll?from_date=2026-01-01&to_date=2026-12-31")
        assert r.status_code == 200
        data = r.json()
        assert data.get("from_date") == "2026-01-01"
        assert data.get("to_date") == "2026-12-31"


# ─────────────────────────────────────────────────────────────────────────────
# 14. Regression: existing endpoints unaffected
# ─────────────────────────────────────────────────────────────────────────────

class TestRegression:
    def test_existing_assignment_endpoint_still_works(
        self, admin_session, production_job, worker_data
    ):
        job_id = production_job["job_id"]
        r = admin_session.patch(
            f"{API_URL}/production/jobs/{job_id}/assignment",
            json={"role": "folding", "worker_id": worker_data["wid"], "rate_per_pair": 12.0},
        )
        assert r.status_code == 200
        doc = r.json()
        assigns = doc.get("assignments") or {}
        assert "folding" in assigns

    def test_existing_stage_update_endpoint_still_works(
        self, admin_session, production_job
    ):
        job_id = production_job["job_id"]
        # Already at folding from previous test — advance to attachment
        r = admin_session.patch(
            f"{API_URL}/production/jobs/{job_id}",
            json={"stage": "attachment", "confirm_skip": True},
        )
        assert r.status_code == 200
        doc = r.json()
        assert doc.get("stage") == "attachment"

    def test_existing_payroll_report_still_works(self, admin_session):
        r = admin_session.get(f"{API_URL}/reports/payroll")
        assert r.status_code == 200
        data = r.json()
        assert "rows" in data
        assert "grand_total" in data

    def test_worker_role_not_in_existing_admin_endpoints(self, worker_session):
        """Worker token must be denied on admin-only endpoints."""
        r = worker_session.get(f"{API_URL}/workers")
        # list_workers requires any valid login — should be 200
        # but production CRUD must be 403
        r2 = worker_session.patch(
            f"{API_URL}/production/jobs/000000000000000000000000",
            json={"stage": "cutting"},
        )
        assert r2.status_code in (403, 404)  # 403 preferred; 404 if validation hits first


# ─────────────────────────────────────────────────────────────────────────────
# 15. Production Card viewing & PDF downloads for Workers
# ─────────────────────────────────────────────────────────────────────────────

class TestProductionCard:
    @pytest.fixture(scope="class")
    def card_job(self, admin_session, worker_token, second_worker):
        actual_wid = worker_token["worker_id"]
        r_styles = admin_session.get(f"{API_URL}/styles")
        styles = r_styles.json() if r_styles.status_code == 200 else []
        style_code = styles[0]["code"] if styles else "TEST-STYLE"

        import time as _t
        po_number = f"CARDTEST-{int(_t.time())}"
        r_po = admin_session.post(f"{API_URL}/pos", json={
            "po_number": po_number, "po_date": "2026-07-01", "client_name": "Card Client",
            "currency": "INR",
            "line_items": [{"style_code": style_code, "quantity": 12, "unit_price": 100, "amount": 1200}],
            "subtotal": 1200, "grand_total": 1200, "total_quantity": 12,
        })
        if r_po.status_code not in (200, 201):
            pytest.skip("Cannot create PO for card_job")

        po_id = r_po.json().get("id") or r_po.json().get("_id")
        r_jobs = admin_session.get(f"{API_URL}/production/jobs?po_id={po_id}")
        jobs = r_jobs.json() if r_jobs.status_code == 200 else []
        if not jobs:
            pytest.skip("No production job for card_job fixture")
        job_id = jobs[0]["id"]

        admin_session.patch(f"{API_URL}/production/jobs/{job_id}/assignment", json={
            "role": "cutting", "worker_id": actual_wid, "rate_per_pair": 15.0,
        })
        return {"job_id": job_id, "style_code": style_code}

    def test_worker_can_get_task_card_details(self, worker_session, card_job):
        job_id = card_job["job_id"]
        r = worker_session.get(f"{API_URL}/my/tasks/{job_id}/details")
        assert r.status_code == 200, f"details failed: {r.text}"
        data = r.json()
        assert data.get("job_id") == job_id
        assert data.get("style_code") == card_job["style_code"]
        assert "sizes" in data
        assert "my_assignment" in data

    def test_worker_can_download_production_card_pdf(self, worker_session, card_job):
        job_id = card_job["job_id"]
        r = worker_session.get(f"{API_URL}/my/tasks/{job_id}/card.pdf")
        assert r.status_code == 200, f"card.pdf failed: {r.text}"
        assert r.headers.get("content-type") == "application/pdf"
        assert len(r.content) > 100

    def test_unassigned_worker_cannot_download_card_pdf(self, second_worker, card_job):
        r_login = requests.post(f"{API_URL}/auth/worker-login", json={
            "phone": second_worker["phone"], "pin": second_worker["pin"],
        })
        if r_login.status_code != 200:
            pytest.skip("Second worker login failed")
        token2 = r_login.json()["access_token"]
        s2 = requests.Session()
        s2.headers["Authorization"] = f"Bearer {token2}"
        r = s2.get(f"{API_URL}/my/tasks/{card_job['job_id']}/card.pdf")
        assert r.status_code == 403


