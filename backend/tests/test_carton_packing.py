import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def test_ean_mapping_workflow(session):
    # 1. Create a dummy style with default carton specs
    style_payload = {
        "code": "",
        "name": "Test Packing Style",
        "category": "Footwear",
        "base_size": "7",
        "bom": [],
        "labor": [],
        "overhead_pct": 5.0,
        "packing_cost": 10.0,
        "margin_pct": 20.0,
        "gst_pct": 5.0,
        "default_pairs_per_carton": {"default": 50, "7": 35, "8": 52}
    }
    r = session.post(f"{BASE_URL}/api/styles", json=style_payload)
    assert r.status_code == 200, r.text
    style = r.json()
    style_id = style["id"]

    # Verify default carton specification is saved
    assert style["default_pairs_per_carton"]["default"] == 50
    assert style["default_pairs_per_carton"]["7"] == 35

    # 2. Add an EAN code override
    ean_payload = {
        "style_id": style_id,
        "color": "Black",
        "size": "7",
        "ean_code": "8901234567890"
    }
    r = session.post(f"{BASE_URL}/api/packing/ean-codes", json=ean_payload)
    assert r.status_code == 200, r.text
    
    # 3. Retrieve EAN codes and verify
    r = session.get(f"{BASE_URL}/api/packing/ean-codes?style_id={style_id}")
    assert r.status_code == 200, r.text
    codes = r.json()
    assert len(codes) >= 1
    assert codes[0]["size"] == "7"
    assert codes[0]["ean_code"] == "8901234567890"


def test_carton_packing_and_invoice_workflow(session):
    # 1. Create a dummy style first
    style_payload = {
        "name": "Carton Packing Style",
        "category": "Footwear",
        "base_size": "8",
        "bom": [],
        "labor": [],
        "default_pairs_per_carton": {"default": 30}
    }
    r = session.post(f"{BASE_URL}/api/styles", json=style_payload)
    assert r.status_code == 200, r.text
    style = r.json()
    style_id = style["id"]
    style_code = style["code"]

    import time
    po_num = f"PO-PACK-TEST-{int(time.time())}"
    # 2. Add a mock Purchase Order
    po_payload = {
        "po_number": po_num,
        "client_name": "Test Retail Client",
        "po_date": "2026-07-13",
        "delivery_date": "2026-08-13",
        "payment_terms": "30 Days Credit",
        "line_items": [
            {
                "style_code": style_code,
                "color": "Brown",
                "size": "8",
                "quantity": 100,
                "unit_price": 500.0,
                "amount": 50000.0
            }
        ]
    }
    r = session.post(f"{BASE_URL}/api/pos", json=po_payload)
    assert r.status_code == 200, r.text
    po = r.json()
    po_id = po["id"]

    # 3. Retrieve the auto-created job for this PO
    r = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r.status_code == 200, r.text
    jobs = [j for j in r.json() if j.get("po_id") == po_id]
    assert len(jobs) > 0
    job = jobs[0]
    job_id = job["id"]

    # 4. Pack a carton for this job
    pack_payload = {
        "job_id": job_id,
        "size": "8",
        "qty": 30
    }
    r = session.post(f"{BASE_URL}/api/packing/cartons", json=pack_payload)
    assert r.status_code == 200, r.text
    carton = r.json()
    assert r.status_code == 200

    # Verify carton exists and is in "packed" status
    r = session.get(f"{BASE_URL}/api/packing/cartons?job_id={job_id}")
    assert r.status_code == 200, r.text
    cartons = r.json()
    assert len(cartons) == 1
    assert cartons[0]["status"] == "packed"
    assert cartons[0]["box_number"] is None
    assert cartons[0]["invoice_id"] is None
    carton_id = cartons[0]["id"]

    # 5. Move job to qc_pack and then finishing stages for test sanity
    # (Just verifying we can update stages cleanly)
    r = session.patch(f"{BASE_URL}/api/production/jobs/{job_id}", json={"stage": "qc_pack"})
    assert r.status_code == 200, r.text

    # 6. Generate an invoice to dispatch the job
    invoice_payload = {
        "po_id": po_id,
        "job_ids": [job_id],
        "transport_mode": "Road",
        "vehicle_no": "KA-01-1234",
        "supply_date": "2026-07-13"
    }
    r = session.post(f"{BASE_URL}/api/invoices/job", json=invoice_payload)
    assert r.status_code == 200, r.text
    headers = r.headers
    invoice_id = headers.get("X-Invoice-Id")
    assert invoice_id

    # 7. Check if carton status is updated to "dispatched" and receives box number
    r = session.get(f"{BASE_URL}/api/packing/cartons?job_id={job_id}")
    assert r.status_code == 200, r.text
    cartons = r.json()
    assert len(cartons) == 1
    assert cartons[0]["status"] == "dispatched"
    assert cartons[0]["box_number"] == 1
    assert cartons[0]["invoice_id"] == invoice_id

    # 8. Delete the invoice and verify the carton status is reverted to "packed"
    r = session.delete(f"{BASE_URL}/api/invoices/{invoice_id}")
    assert r.status_code == 200, r.text

    r = session.get(f"{BASE_URL}/api/packing/cartons?job_id={job_id}")
    assert r.status_code == 200, r.text
    cartons = r.json()
    assert len(cartons) == 1
    assert cartons[0]["status"] == "packed"
    assert cartons[0]["box_number"] is None
    assert cartons[0]["invoice_id"] is None

    # Clean up test carton
    r = session.delete(f"{BASE_URL}/api/packing/cartons/{carton_id}")
    assert r.status_code == 200, r.text
    
    r = session.get(f"{BASE_URL}/api/packing/cartons?job_id={job_id}")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 0


def test_bulk_confirm_qc_pack_flow(session):
    # 1. Create style
    style_payload = {
        "name": "Bulk Confirm Style",
        "category": "Footwear",
        "base_size": "7",
        "bom": [],
        "labor": [],
        "default_pairs_per_carton": {"default": 30}
    }
    r = session.post(f"{BASE_URL}/api/styles", json=style_payload)
    assert r.status_code == 200, r.text
    style = r.json()
    style_id = style["id"]
    style_code = style["code"]

    import time
    po_num = f"PO-BULK-CONFIRM-{int(time.time())}"
    # 2. Add PO with 2 sizes
    po_payload = {
        "po_number": po_num,
        "client_name": "Test Bulk Client",
        "po_date": "2026-07-13",
        "delivery_date": "2026-08-13",
        "payment_terms": "30 Days Credit",
        "line_items": [
            {
                "style_code": style_code,
                "color": "Black",
                "size": "7",
                "quantity": 60,
                "unit_price": 400.0,
                "amount": 24000.0
            },
            {
                "style_code": style_code,
                "color": "Black",
                "size": "8",
                "quantity": 90,
                "unit_price": 400.0,
                "amount": 36000.0
            }
        ]
    }
    r = session.post(f"{BASE_URL}/api/pos", json=po_payload)
    assert r.status_code == 200, r.text
    po = r.json()
    po_id = po["id"]

    # 3. Retrieve jobs
    r = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r.status_code == 200, r.text
    jobs = [j for j in r.json() if j.get("po_id") == po_id]
    assert len(jobs) == 2
    
    job_sz7 = [j for j in jobs if j.get("size") == "7"][0]
    job_sz8 = [j for j in jobs if j.get("size") == "8"][0]
    
    # 4. Set completed quantities (e.g. size 7 has 60 completed, size 8 has 90 completed)
    r = session.patch(f"{BASE_URL}/api/production/jobs/{job_sz7['id']}", json={"stage": "finishing", "completed_qty": 60})
    assert r.status_code == 200, r.text
    r = session.patch(f"{BASE_URL}/api/production/jobs/{job_sz8['id']}", json={"stage": "finishing", "completed_qty": 90})
    assert r.status_code == 200, r.text

    # 5. Confirm QC & Pack with EANs and cartons rows
    confirm_payload = {
        "job_ids": [job_sz7["id"], job_sz8["id"]],
        "eans": [
            {"size": "7", "ean_code": "EAN-BULK-7"},
            {"size": "8", "ean_code": "EAN-BULK-8"}
        ],
        "cartons": [
            {"size": "7", "qty": 30},
            {"size": "7", "qty": 30},
            {"size": "8", "qty": 30},
            {"size": "8", "qty": 30},
            {"size": "8", "qty": 30}
        ]
    }
    r = session.post(f"{BASE_URL}/api/packing/confirm-qc-pack", json=confirm_payload)
    assert r.status_code == 200, r.text
    
    # 6. Verify job stage is advanced to "qc_pack"
    r = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r.status_code == 200, r.text
    updated_jobs = [j for j in r.json() if j.get("po_id") == po_id]
    for j in updated_jobs:
        assert j["stage"] == "qc_pack"

    # 7. Verify EAN codes saved
    r = session.get(f"{BASE_URL}/api/packing/ean-codes?style_id={style_id}")
    assert r.status_code == 200, r.text
    eans = r.json()
    assert len(eans) >= 2
    
    # 8. Verify cartons packed
    r = session.get(f"{BASE_URL}/api/packing/cartons?job_ids={job_sz7['id']},{job_sz8['id']}")
    assert r.status_code == 200, r.text
    cartons = r.json()
    assert len(cartons) == 5
    for c in cartons:
        assert c["status"] == "packed"

    # 9. Generate invoice to dispatch (B2B Phase 3 dispatch step)
    invoice_payload = {
        "po_id": po_id,
        "job_ids": [job_sz7["id"], job_sz8["id"]],
        "transport_mode": "Road",
        "vehicle_no": "KA-01-9999",
        "supply_date": "2026-07-13"
    }
    r = session.post(f"{BASE_URL}/api/invoices/job", json=invoice_payload)
    assert r.status_code == 200, r.text
    invoice_id = r.headers.get("X-Invoice-Id")
    assert invoice_id

    # 10. Verify jobs advanced to "dispatched" stage
    r = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r.status_code == 200, r.text
    dispatched_jobs = [j for j in r.json() if j.get("po_id") == po_id]
    for j in dispatched_jobs:
        assert j["stage"] == "dispatched"

    # 11. Delete invoice
    r = session.delete(f"{BASE_URL}/api/invoices/{invoice_id}")
    assert r.status_code == 200, r.text

    # 12. Verify jobs reverted to "qc_pack" stage
    r = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r.status_code == 200, r.text
    reverted_jobs = [j for j in r.json() if j.get("po_id") == po_id]
    for j in reverted_jobs:
        assert j["stage"] == "qc_pack"


def test_dispatch_documents_flow(session):
    """
    End-to-end test for POST /dispatch:
      1. Create a style, PO, and two production jobs
      2. Run confirm-qc-pack to set packed cartons
      3. POST /dispatch → verify ZIP returned (3 files inside)
      4. Verify dispatch_record saved with correct fields
      5. Verify cartons advanced to dispatched + box_numbers set
      6. Verify jobs advanced to dispatched
      7. Verify individual re-download endpoints work
    """
    import zipfile, io, time

    # ── 1. Create style ────────────────────────────────────────────────────────
    r = session.post(f"{BASE_URL}/api/styles", json={
        "code": "", "name": "DispatchTestStyle",
        "category": "Footwear", "base_size": "7",
        "bom": [], "labor": [], "overhead_pct": 5.0,
        "packing_cost": 10.0, "margin_pct": 20.0, "gst_pct": 5.0,
        "default_pairs_per_carton": {"default": 40},
    })
    assert r.status_code == 200, r.text
    style = r.json(); style_id = style["id"]; style_code = style["code"]

    # ── 2. Create client ───────────────────────────────────────────────────────
    r = session.post(f"{BASE_URL}/api/clients", json={
        "name": "DispatchTestClient", "gstin": "27ZZZZZ1234F1ZX",
        "address": "Test City", "state": "Maharashtra", "state_code": "27",
    })
    client_name = "DispatchTestClient"

    # ── 3. Create PO ──────────────────────────────────────────────────────────
    po_num = f"DISP-TEST-{int(time.time())}"
    r = session.post(f"{BASE_URL}/api/pos", json={
        "po_number": po_num,
        "client_name": client_name,
        "po_date": "2026-07-13",
        "line_items": [
            {"style_code": style_code, "color": "Navy", "size": "7",
             "quantity": 80, "unit_price": 250.0, "amount": 20000.0, "description": "Test shoe"},
            {"style_code": style_code, "color": "Navy", "size": "8",
             "quantity": 80, "unit_price": 260.0, "amount": 20800.0, "description": "Test shoe"},
        ],
        "payment_terms": "Net 30", "delivery_date": "2025-12-31",
    })
    assert r.status_code == 200, r.text
    po = r.json(); po_id = po["id"]


    # ── 4. Retrieve auto-created production jobs ────────────────────────────────
    r = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r.status_code == 200, r.text
    job_ids = [j["id"] for j in r.json() if j.get("po_id") == po_id]
    assert len(job_ids) == 2

    # ── 5. Set completed qty on each job (move through stages) ─────────────────
    stages_to_advance = ["cutting", "stitching", "lasting", "finishing"]
    for jid in job_ids:
        for stage in stages_to_advance:
            session.post(f"{BASE_URL}/api/production/jobs/{jid}/move", json={"stage": stage})
        # Set completed_qty to match
        session.patch(f"{BASE_URL}/api/production/jobs/{jid}", json={"completed_qty": 80})

    # ── 6. Confirm QC Pack (creates packing cartons) ──────────────────────────
    confirm_payload = {
        "job_ids": job_ids,
        "eans": [
            {"size": "7", "ean_code": "8901234500001"},
            {"size": "8", "ean_code": "8901234500002"}
        ],
        "cartons": [
            {"size": "7", "qty": 40},
            {"size": "7", "qty": 40},
            {"size": "8", "qty": 40},
            {"size": "8", "qty": 40}
        ]
    }
    r = session.post(f"{BASE_URL}/api/packing/confirm-qc-pack", json=confirm_payload)
    assert r.status_code == 200, r.text

    # ── 7. Call POST /dispatch ─────────────────────────────────────────────────
    r = session.post(f"{BASE_URL}/api/dispatch", json={
        "job_ids": job_ids, "po_id": po_id,
        "transport_mode": "By Road", "vehicle_no": "MH-01-ZZ-9999",
        "supply_date": "2025-08-01",
        "carton_dim": "60x50x30 CMS",
        "net_wt_per_carton": 10.8, "gross_wt_per_carton": 12.0,
    })
    assert r.status_code == 200, f"dispatch failed: {r.status_code} {r.text[:500]}"
    assert r.headers.get("content-type", "").startswith("application/zip")

    dispatch_record_id = r.headers.get("x-dispatch-record-id", "")
    invoice_no = r.headers.get("x-invoice-no", "")
    assert dispatch_record_id, "X-Dispatch-Record-Id header missing"
    assert invoice_no, "X-Invoice-No header missing"

    # ── 8. Verify ZIP contains 3 files ────────────────────────────────────────
    zf_data = io.BytesIO(r.content)
    with zipfile.ZipFile(zf_data) as zf:
        names = zf.namelist()
        assert any("Invoice" in n and n.endswith(".pdf") for n in names), f"Invoice PDF missing: {names}"
        assert any("PackingList" in n and n.endswith(".xlsx") for n in names), f"Packing XLSX missing: {names}"
        assert any("CartonLabels" in n and n.endswith(".pdf") for n in names), f"Labels PDF missing: {names}"

    # ── 9. Verify dispatch_record in database ─────────────────────────────────
    r2 = session.get(f"{BASE_URL}/api/dispatch-records")
    assert r2.status_code == 200, r2.text
    records = r2.json()
    our_rec = next((rec for rec in records if rec["id"] == dispatch_record_id), None)
    assert our_rec is not None, "dispatch_record not found in list"
    assert our_rec["invoice_no"] == invoice_no
    assert our_rec["total_cartons"] == 4       # 2 sizes × 2 cartons each
    assert our_rec["total_qty"] == 160          # 80+80

    # ── 10. Verify dispatch_record detail ─────────────────────────────────────
    r3 = session.get(f"{BASE_URL}/api/dispatch-records/{dispatch_record_id}")
    assert r3.status_code == 200, r3.text
    detail = r3.json()
    assert len(detail["packing_cartons_snapshot"]) == 4
    box_numbers = [c["box_number"] for c in detail["packing_cartons_snapshot"]]
    assert sorted(box_numbers) == [1, 2, 3, 4], f"box_numbers wrong: {box_numbers}"

    # ── 11. Verify cartons updated to dispatched ──────────────────────────────
    r4 = session.get(f"{BASE_URL}/api/packing/cartons?job_id={job_ids[0]}")
    assert r4.status_code == 200, r4.text
    cartons = r4.json()
    for c in cartons:
        assert c["status"] == "dispatched", f"carton {c['id']} not dispatched"
        assert c["box_number"] is not None

    # ── 12. Verify jobs → dispatched ─────────────────────────────────────────
    r5 = session.get(f"{BASE_URL}/api/production/jobs?source_type=all")
    assert r5.status_code == 200
    our_jobs = [j for j in r5.json() if j["id"] in job_ids]
    for j in our_jobs:
        assert j["stage"] == "dispatched", f"job {j['id']} stage={j['stage']}"

    # ── 13. Re-download individual files ─────────────────────────────────────
    ri = session.get(f"{BASE_URL}/api/dispatch-records/{dispatch_record_id}/invoice")
    assert ri.status_code == 200
    assert ri.headers.get("content-type", "").startswith("application/pdf")
    assert len(ri.content) > 1000, "invoice PDF too small"

    rp = session.get(f"{BASE_URL}/api/dispatch-records/{dispatch_record_id}/packing-list")
    assert rp.status_code == 200
    assert "spreadsheetml" in rp.headers.get("content-type", "")

    rl = session.get(f"{BASE_URL}/api/dispatch-records/{dispatch_record_id}/carton-labels")
    assert rl.status_code == 200
    assert rl.headers.get("content-type", "").startswith("application/pdf")
    assert len(rl.content) > 500, "labels PDF too small"

    # ── 14. Reprint ZIP endpoint ──────────────────────────────────────────────
    rr = session.post(f"{BASE_URL}/api/dispatch-records/{dispatch_record_id}/reprint")
    assert rr.status_code == 200
    assert rr.headers.get("content-type", "").startswith("application/zip")
