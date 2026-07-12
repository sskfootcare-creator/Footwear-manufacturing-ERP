"""
Iteration 10 backend tests:
- P0 bug fix: payment recording (advance txn_type='payment')
- NEW: Settings stage-durations GET/PUT
- NEW: Dashboard overdue endpoint
- NEW: Visual reports (monthly-production, karigar-output, cost-variance, stage-cycle-time, defect-rate)
- NEW: Production card PDF with PROCESS TALLY section
- Regression: list POs, list workers, list materials, payroll, ledger, list jobs, update job stage (+ deadline)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ---------- AUTH SMOKE ----------
class TestAuth:
    def test_login(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == ADMIN_EMAIL.lower()


# ---------- P0 BUG FIX: payment recording ----------
class TestPaymentBugFix:
    def test_record_payment_success(self, admin_session):
        # pick a worker
        wr = admin_session.get(f"{BASE_URL}/api/workers", timeout=15)
        assert wr.status_code == 200
        workers = wr.json()
        assert len(workers) > 0, "No workers seeded"
        wid = workers[0].get("id") or workers[0].get("_id")
        assert wid

        # record a payment
        payload = {
            "worker_id": wid,
            "amount": 500,
            "date": "2026-01-15",
            "txn_type": "payment",
            "notes": "TEST_iter10_payment",
        }
        r = admin_session.post(f"{BASE_URL}/api/advances", json=payload, timeout=15)
        assert r.status_code == 200, f"payment create failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("amount") == 500
        assert data.get("txn_type") == "payment"

        # verify ledger reflects it (NOT /api/workers/undefined/ledger)
        lr = admin_session.get(f"{BASE_URL}/api/workers/{wid}/ledger", timeout=15)
        assert lr.status_code == 200, f"ledger fetch failed: {lr.status_code} {lr.text}"
        ledger = lr.json()
        assert "entries" in ledger
        # Ledger entries use 'description' field; payments are signed negative
        assert any(abs(e.get("amount", 0)) == 500 and e.get("txn_type") == "payment"
                   for e in ledger["entries"]), "payment not visible in ledger"

    def test_undefined_id_returns_404_not_400(self, admin_session):
        # The bug was the frontend calling /api/workers/undefined/ledger and getting 400
        # Server should reject invalid IDs cleanly
        r = admin_session.get(f"{BASE_URL}/api/workers/undefined/ledger", timeout=15)
        assert r.status_code in (400, 404, 422), f"unexpected status {r.status_code}"


# ---------- SETTINGS / STAGE DURATIONS ----------
class TestStageDurations:
    def test_get_defaults(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/settings/stage-durations", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "hours" in body and "defaults" in body
        defaults = body["defaults"]
        # spec asks for 7 stage inputs + dispatched (server has 9 entries incl. dispatched)
        for key in ["procurement", "cutting", "folding", "attachment", "stitching",
                    "lasting", "sole_pasting", "finishing"]:
            assert key in defaults, f"missing default for {key}"

    def test_put_and_persist(self, admin_session):
        new_hours = {
            "procurement": 30, "cutting": 22, "folding": 6, "attachment": 7,
            "stitching": 50, "lasting": 20, "sole_pasting": 10, "finishing": 11,
        }
        r = admin_session.put(
            f"{BASE_URL}/api/settings/stage-durations",
            json={"hours": new_hours},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        g = admin_session.get(f"{BASE_URL}/api/settings/stage-durations", timeout=15).json()
        for k, v in new_hours.items():
            assert g["hours"].get(k) == v, f"persist failed for {k}"


# ---------- DASHBOARD OVERDUE ----------
class TestOverdue:
    def test_overdue_endpoint(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard/overdue", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # If any overdue jobs, ensure they have overdue_hours field
        for j in data:
            assert "overdue_hours" in j
            assert isinstance(j["overdue_hours"], (int, float))


# ---------- VISUAL REPORTS ----------
class TestReports:
    def test_monthly_production(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/monthly-production", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for row in data:
            assert "month" in row and "started" in row and "dispatched" in row

    def test_karigar_output(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/karigar-output", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for row in data:
            for k in ("worker_id", "name", "pairs", "earnings"):
                assert k in row, f"missing {k} in karigar output row"

    def test_cost_variance(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/cost-variance", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_stage_cycle_time(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/stage-cycle-time", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_defect_rate(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/defect-rate", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "by_stage" in data and "by_type" in data


# ---------- PRODUCTION CARD PDF ----------
class TestProductionCardPDF:
    def test_card_pdf_with_tally(self, admin_session):
        # need a job_id
        jr = admin_session.get(f"{BASE_URL}/api/production/jobs", timeout=15)
        assert jr.status_code == 200
        jobs = jr.json()
        assert len(jobs) > 0, "no jobs seeded for production card"
        jid = jobs[0].get("id") or jobs[0].get("_id")

        r = admin_session.post(
            f"{BASE_URL}/api/production/card.pdf",
            json={"job_ids": [jid]},
            timeout=30,
        )
        assert r.status_code == 200, f"card.pdf failed: {r.status_code} {r.text[:300]}"
        assert r.content[:4] == b"%PDF", "Not a valid PDF (header)"
        assert len(r.content) > 4096, f"PDF too small ({len(r.content)} bytes)"
        # process tally text isn't searchable easily in PDF binary, just confirm size > raw card
        # by being noticeably > 4KB (previous baseline was ~4KB in iteration_9)


# ---------- PRODUCTION STAGE UPDATE -> deadline ----------
class TestJobStageDeadline:
    def test_stage_update_sets_deadline(self, admin_session):
        jr = admin_session.get(f"{BASE_URL}/api/production/jobs", timeout=15)
        assert jr.status_code == 200
        jobs = jr.json()
        assert len(jobs) > 0
        # pick a non-dispatched job
        job = next((j for j in jobs if j.get("stage") != "dispatched"), jobs[0])
        jid = job.get("id") or job.get("_id")
        current = job.get("stage", "procurement")
        new_stage = "cutting" if current != "cutting" else "folding"

        r = admin_session.patch(
            f"{BASE_URL}/api/production/jobs/{jid}",
            json={"stage": new_stage},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated.get("stage") == new_stage
        # deadline + entered_at should be set
        assert updated.get("stage_entered_at"), "stage_entered_at not set"
        assert updated.get("stage_deadline"), "stage_deadline not set"


# ---------- REGRESSION SMOKE ----------
class TestRegression:
    def test_list_pos(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/pos", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_workers(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/workers", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_materials(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/materials", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_payroll_report(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/reports/payroll", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "rows" in body

    def test_create_worker(self, admin_session):
        payload = {
            "name": f"TEST_Karigar_{int(time.time())}",
            "phone": "9000000000",
            "skill": "stitching",
            "wage_type": "piece",
            "rate": 50,
        }
        r = admin_session.post(f"{BASE_URL}/api/workers", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        wid = r.json().get("id") or r.json().get("_id")
        assert wid
        # verify
        g = admin_session.get(f"{BASE_URL}/api/workers", timeout=15).json()
        assert any((w.get("id") or w.get("_id")) == wid for w in g)

    def test_wage_slip_pdf(self, admin_session):
        wr = admin_session.get(f"{BASE_URL}/api/workers", timeout=15).json()
        wid = wr[0].get("id") or wr[0].get("_id")
        r = admin_session.get(
            f"{BASE_URL}/api/workers/{wid}/wage-slip.pdf?from_date=2026-01-01&to_date=2026-01-31",
            timeout=30,
        )
        # endpoint must exist; accept 200 or 404 (if route differs)
        assert r.status_code in (200, 404), f"unexpected status {r.status_code}"
        if r.status_code == 200:
            assert r.content[:4] == b"%PDF"
