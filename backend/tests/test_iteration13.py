"""Iteration 13 - Accounts Receivable backend test suite.

Covers:
- Invoice persistence (file_b64, totals, due_date) via /api/invoices/job
- /api/invoices listing + filters + overdue
- /api/invoices/{id} with payments + grns + /file re-download
- /api/grns CRUD + aggregates
- /api/payments FIFO allocation (partial/full/over-pay)
- /api/clients aggregates + /api/clients/{name}/ledger Tally entries + aging
- Regression on PO/dashboard/production smoke endpoints
"""
import os
import base64
import datetime as dt
import pytest
import requests
from pathlib import Path


def _load_frontend_url():
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000")


BASE_URL = _load_frontend_url().rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@sskfootcare.com"
ADMIN_PASS = "Admin@123"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def dispatched_job(session):
    """Find one dispatched job we can invoice from."""
    r = session.get(f"{API}/production/archive", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    # pick a dispatched job (stage == 'dispatched' or similar)
    cand = None
    for row in rows:
        stage = (row.get("stage") or "").lower()
        if stage in ("dispatched", "dispatch", "ready_to_dispatch"):
            cand = row
            break
    if not cand and rows:
        # Fallback: first row from archive (already dispatched)
        cand = rows[0]
    assert cand, "No dispatched jobs available to invoice"
    return cand


@pytest.fixture(scope="session")
def fresh_invoice(session):
    """Create a fresh invoice from a dispatched job for tests below."""
    # archive returns dispatched/archived production rows with id and po_id
    r = session.get(f"{API}/production/archive", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    # Prefer a SIYARAM dispatched row not yet invoiced? Use first dispatched row.
    job = None
    for row in rows:
        if (row.get("stage") or "").lower() == "dispatched":
            job = row
            break
    if not job and rows:
        job = rows[0]
    assert job, "no dispatched jobs"
    pid = job["po_id"]
    jid = job["id"]
    # Trigger invoice job (must pass job_ids list)
    r3 = session.post(f"{API}/invoices/job", json={
        "po_id": pid,
        "job_ids": [jid],
    }, timeout=60)
    assert r3.status_code == 200, f"invoice/job failed: {r3.status_code} {r3.text}"
    inv_id = r3.headers.get("X-Invoice-Id")
    assert inv_id, "X-Invoice-Id header missing"
    return {"id": inv_id, "po_id": pid, "client_name": job.get("client_name")}


# ---------------- Smoke ----------------
def test_health(session):
    r = session.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200


# ---------------- Invoices ----------------
def test_invoice_persistence_headers_and_doc(session, fresh_invoice):
    inv = session.get(f"{API}/invoices/{fresh_invoice['id']}", timeout=20).json()
    assert inv.get("invoice_no"), "invoice_no missing"
    assert inv.get("due_date"), "due_date missing (45-day default expected)"
    assert float(inv.get("grand_total") or 0) > 0, "grand_total not persisted"
    assert float(inv.get("subtotal") or 0) > 0
    # tax fields present
    assert "cgst_amount" in inv and "sgst_amount" in inv and "igst_amount" in inv
    # status/outstanding/days_to_due decorated
    assert inv.get("status") in ("paid", "partial", "overdue", "pending")
    assert "outstanding" in inv and "received_amount" in inv


def test_invoice_file_redownload(session, fresh_invoice):
    r = session.get(f"{API}/invoices/{fresh_invoice['id']}/file", timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 1000


def test_list_invoices_and_filters(session, fresh_invoice):
    r = session.get(f"{API}/invoices", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) > 0
    # decorated fields
    for r0 in rows[:5]:
        assert "status" in r0 and "outstanding" in r0 and "received_amount" in r0

    # filter by status=pending should not contain paid
    r = session.get(f"{API}/invoices?status=pending", timeout=30)
    assert r.status_code == 200
    for r0 in r.json():
        assert r0["status"] == "pending"

    # filter by client substring (use part of fresh_invoice client_name)
    cn = fresh_invoice["client_name"] or "SIYARAM"
    r = session.get(f"{API}/invoices", params={"client": cn.split()[0]}, timeout=30)
    assert r.status_code == 200
    assert all(cn.split()[0].upper() in (x.get("client_name") or "").upper() for x in r.json())


def test_overdue_excludes_fresh_45day_invoice(session, fresh_invoice):
    r = session.get(f"{API}/invoices/overdue", timeout=30)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert fresh_invoice["id"] not in ids, "freshly-created 45-day invoice must not be overdue"


# ---------------- GRN ----------------
@pytest.fixture(scope="session")
def created_grn(session, fresh_invoice):
    """Create a GRN with one short/rejected line."""
    inv = session.get(f"{API}/invoices/{fresh_invoice['id']}", timeout=20).json()
    lis = inv.get("line_items_snapshot") or []
    assert lis, "invoice has no line_items_snapshot"
    # Build line_items with first line short by 1 unit (rejected)
    out_lines = []
    for i, li in enumerate(lis):
        disp = int(li.get("quantity") or li.get("qty") or 0)
        rej = 1 if i == 0 else 0
        recv = disp
        acc = recv - rej
        out_lines.append({
            "style_code": li.get("style_code"),
            "description": li.get("description"),
            "color": li.get("color"),
            "size": str(li.get("size") or ""),
            "dispatched_qty": disp,
            "received_qty": recv,
            "rejected_qty": rej,
            "accepted_qty": acc,
            "rejection_reason": "TEST_SHORT" if rej else None,
        })
    today = dt.date.today().isoformat()
    r = session.post(f"{API}/grns", json={
        "invoice_id": fresh_invoice["id"],
        "grn_date": today, "received_date": today,
        "client_reference": "TEST_GRN_REF",
        "notes": "TEST_GRN", "line_items": out_lines,
    }, timeout=30)
    assert r.status_code == 200, f"GRN POST {r.status_code} {r.text}"
    d = r.json()
    assert d.get("grn_no", "").startswith("GRN-"), f"unexpected grn_no {d.get('grn_no')}"
    assert d["total_rejected"] >= 1
    return d


def test_grn_attached_to_invoice(session, fresh_invoice, created_grn):
    inv = session.get(f"{API}/invoices/{fresh_invoice['id']}", timeout=20).json()
    grn_nos = [g.get("grn_no") for g in inv.get("grns") or []]
    assert created_grn["grn_no"] in grn_nos


def test_grn_list_by_invoice(session, fresh_invoice, created_grn):
    r = session.get(f"{API}/grns", params={"invoice_id": fresh_invoice["id"]}, timeout=20)
    assert r.status_code == 200
    assert any(g["grn_no"] == created_grn["grn_no"] for g in r.json())


# ---------------- Payments ----------------
def test_payment_partial_then_full(session, fresh_invoice):
    inv = session.get(f"{API}/invoices/{fresh_invoice['id']}", timeout=20).json()
    outstanding_before = float(inv.get("outstanding") or 0)
    assert outstanding_before > 0, "invoice should have outstanding for payment test"

    part = round(outstanding_before / 2, 2)
    today = dt.date.today().isoformat()
    r = session.post(f"{API}/payments", json={
        "invoice_ids": [fresh_invoice["id"]],
        "amount": part, "mode": "NEFT",
        "reference": "TEST_PART_001",
        "payment_date": today, "bank": "HDFC",
    }, timeout=30)
    assert r.status_code == 200, f"part payment failed: {r.status_code} {r.text}"
    pd = r.json()
    assert pd.get("payment_no", "").startswith("RCT-")
    assert pd["amount"] == part

    inv = session.get(f"{API}/invoices/{fresh_invoice['id']}", timeout=20).json()
    assert inv["status"] == "partial", f"status {inv['status']}"
    assert abs(float(inv["received_amount"]) - part) < 0.5
    assert float(inv["outstanding"]) > 0

    # Now pay rest (try over-pay by +100; should advance_amount=100)
    rem = float(inv["outstanding"])
    over = round(rem + 100, 2)
    r2 = session.post(f"{API}/payments", json={
        "invoice_ids": [fresh_invoice["id"]],
        "amount": over, "mode": "RTGS",
        "reference": "TEST_FULL_001",
        "payment_date": today, "bank": "HDFC",
    }, timeout=30)
    assert r2.status_code == 200
    pd2 = r2.json()
    assert pd2.get("advance_amount", 0) >= 99.5  # ~100 surplus
    inv = session.get(f"{API}/invoices/{fresh_invoice['id']}", timeout=20).json()
    assert inv["status"] == "paid", f"expected paid after full pay, got {inv['status']}"
    assert float(inv["outstanding"]) < 0.5


def test_payments_listing(session, fresh_invoice):
    r = session.get(f"{API}/payments", params={"invoice_id": fresh_invoice["id"]}, timeout=20)
    assert r.status_code == 200
    rows = r.json()
    assert any(p["reference"] == "TEST_PART_001" for p in rows)
    assert any(p["reference"] == "TEST_FULL_001" for p in rows)


# ---------------- Clients / Ledger ----------------
def test_clients_aggregate(session, fresh_invoice):
    r = session.get(f"{API}/clients", timeout=30)
    assert r.status_code == 200
    rows = r.json()
    assert any(fresh_invoice["client_name"] and fresh_invoice["client_name"] in (x["client_name"] or "")
               for x in rows)


def test_client_ledger_structure(session, fresh_invoice):
    cn = fresh_invoice["client_name"]
    r = session.get(f"{API}/clients/{requests.utils.quote(cn)}/ledger", timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    led = r.json()
    # structure
    for k in ("entries", "closing_balance", "closing_balance_type", "aging",
              "totals", "invoices"):
        assert k in led, f"ledger missing {k}"
    # entries include an Invoice and a Payment voucher type
    types = {e["vch_type"] for e in led["entries"]}
    assert "Invoice" in types and "Payment" in types
    # Each entry must have Dr/Cr running balance
    for e in led["entries"]:
        assert e["balance_type"] in ("Dr", "Cr")
        assert "balance" in e
    # totals
    t = led["totals"]
    for k in ("invoiced", "received", "outstanding"):
        assert k in t
    # aging keys (list of {bucket, amount, count})
    aging_buckets = {a["bucket"] for a in led["aging"]}
    for k in ("0-30", "31-60", "61-90", "90+"):
        assert k in aging_buckets


# ---------------- Regression smoke ----------------
@pytest.mark.parametrize("path", [
    "/pos", "/workers", "/dashboard/overdue", "/production/archive",
    "/packing-templates", "/reports/payroll", "/reports/monthly-production",
    "/packing-lists",
])
def test_regression_smoke(session, path):
    r = session.get(f"{API}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
