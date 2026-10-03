import os
import pytest
from httpx import AsyncClient, ASGITransport
import server


@pytest.mark.anyio
async def test_subtask_bulk_assignment_and_outside_labour_flow():
    app = server.app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login as admin
        _email = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
        _pass  = os.environ.get("ADMIN_PASSWORD", "Admin@123")
        login_res = await client.post("/api/auth/login", json={"email": _email, "password": _pass})
        assert login_res.status_code == 200, f"Login failed ({login_res.status_code}): {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create 2 workers
        w1_res = await client.post("/api/workers", json={
            "name": "Suresh Master",
            "skill": "cutting",
            "rate_per_pair": 20.0,
        }, headers=headers)
        assert w1_res.status_code in (200, 201)
        w1_id = w1_res.json()["id"]

        w2_res = await client.post("/api/workers", json={
            "name": "Pooja Stitching Specialist",
            "skill": "stitching",
            "rate_per_pair": 16.0,
        }, headers=headers)
        assert w2_res.status_code in (200, 201)
        w2_id = w2_res.json()["id"]

        # 3. Create a vendor for outside labour
        vendor_res = await client.post("/api/vendors", json={
            "name": "Apex Embossing & Foiling",
            "category": "Job Work",
            "phone": "9998887776",
        }, headers=headers)
        assert vendor_res.status_code in (200, 201)
        vendor_id = vendor_res.json()["id"]

        # 4. Create a style
        style_res = await client.post("/api/styles", json={
            "name": "Urban Loafer Pro",
            "category": "Footwear",
            "footwear_type": "flat",
            "bom": [],
            "labor": [],
        }, headers=headers)
        assert style_res.status_code == 200
        style_id = style_res.json()["id"]
        style_code = style_res.json()["code"]

        # 5. Insert test production job with component_specs
        specs = {
            "footwear_type": "flat",
            "components": {
                "upper": {"stages": ["cutting", "stitching", "folding"], "ready_if_empty": False},
                "bottom": {"stages": ["cutting"], "ready_if_empty": True},
                "sole": {"stages": [], "ready_if_empty": True},
            }
        }
        job_doc = {
            "source_type": "b2b_client",
            "client_name": "Metro Retailers",
            "po_number": "PO-TEST-SUBTASK-001",
            "style_code": style_code,
            "style_id": style_id,
            "quantity": 250,
            "completed_qty": 0,
            "stage": "planning",
            "component_specs": specs,
            "components": {"upper_done": False, "bottom_done": False, "sole_done": False},
            "assignments": {},
            "outside_labour": [],
            "history": [],
            "created_at": server.now_iso(),
            "updated_at": server.now_iso(),
        }
        ins = await server.db.production_jobs.insert_one(job_doc)
        job_id = str(ins.inserted_id)

        # 6. Bulk-assign Upper to Suresh Master (w1_id)
        bulk_res = await client.post(
            f"/api/production/jobs/{job_id}/components/upper/bulk-assign",
            json={"worker_id": w1_id, "overwrite": False},
            headers=headers
        )
        assert bulk_res.status_code == 200
        j_bulk = bulk_res.json()
        assert j_bulk["assignments"]["upper"]["worker_id"] == w1_id
        assert j_bulk["assignments"]["upper.cutting"]["worker_id"] == w1_id
        assert j_bulk["assignments"]["upper.stitching"]["worker_id"] == w1_id
        assert j_bulk["assignments"]["upper.folding"]["worker_id"] == w1_id

        # 7. Override one sub-task (upper.stitching) to Pooja (w2_id) with rate override
        subtask_res = await client.patch(
            f"/api/production/jobs/{job_id}/sub-task-assignment",
            json={
                "component": "upper",
                "substage": "stitching",
                "worker_id": w2_id,
                "rate_per_pair": 18.5,
            },
            headers=headers
        )
        assert subtask_res.status_code == 200
        j_subtask = subtask_res.json()
        # Cutting & folding still belong to Suresh
        assert j_subtask["assignments"]["upper.cutting"]["worker_id"] == w1_id
        assert j_subtask["assignments"]["upper.folding"]["worker_id"] == w1_id
        # Stitching now specifically belongs to Pooja with ₹18.5
        assert j_subtask["assignments"]["upper.stitching"]["worker_id"] == w2_id
        assert j_subtask["assignments"]["upper.stitching"]["rate_per_pair"] == 18.5

        # 8. Log an Outside Labour Work entry for upper
        outside_item = {
            "id": "ol-101",
            "name": "Gold Foil Logo Stamp",
            "component": "upper",
            "substage": "embossing",
            "vendor_id": vendor_id,
            "vendor": "Apex Embossing & Foiling",
            "rate": 7.0,
            "qty": 250,
            "is_outside": True,
        }
        ol_res = await client.patch(
            f"/api/production/jobs/{job_id}/outside-labour",
            json={"outside_labour": [outside_item]},
            headers=headers
        )
        assert ol_res.status_code == 200
        assert len(ol_res.json()["outside_labour"]) == 1

        # 9. Verify payroll: outside labour MUST NOT appear in payroll!
        payroll_res_initial = await client.get("/api/reports/payroll", headers=headers)
        assert payroll_res_initial.status_code == 200
        payroll_data = payroll_res_initial.json()
        # Ensure outside labour vendor does not appear as a worker in payroll
        assert not any(r.get("worker_id") == vendor_id for r in payroll_data.get("rows", []))
        assert not any("Gold Foil" in str(r) for r in payroll_data.get("rows", []))

        # 10. Complete outside labour -> produces a vendor bill (AP), not payroll!
        comp_ol_res = await client.post(
            f"/api/production/jobs/{job_id}/outside-labour/ol-101/complete",
            json={"completed_qty": 250},
            headers=headers
        )
        assert comp_ol_res.status_code == 200
        assert comp_ol_res.json()["completed_item"]["completed"] is True
        bill_id = comp_ol_res.json()["vendor_bill_id"]
        assert bill_id is not None

        # Verify vendor_pos has the bill for Apex Embossing
        vbill = await server.db.vendor_pos.find_one({"_id": server.oid(bill_id)})
        assert vbill is not None
        assert vbill["vendor_id"] == vendor_id
        assert vbill["total_amount"] == 1750.0  # 250 * 7.0
        assert vbill["type"] == "outside_labour"

        # 11. Complete upper.stitching by Pooja (w2_id) via component-stage completion
        stage_comp_res = await client.patch(
            f"/api/production/jobs/{job_id}/component-stage",
            json={
                "component": "upper",
                "stage": "stitching",
                "completed_qty": 250,
                "worker_id": w2_id,
            },
            headers=headers
        )
        assert stage_comp_res.status_code == 200

        # 12. Verify Payroll: Pooja earned 250 * 18.5 = 4625.0, vendor still not in payroll!
        payroll_res_after = await client.get("/api/reports/payroll", headers=headers)
        assert payroll_res_after.status_code == 200
        pooja_row = next((r for r in payroll_res_after.json().get("rows", []) if r["worker_id"] == w2_id), None)
        assert pooja_row is not None
        assert pooja_row["total_pairs"] >= 250
        assert pooja_row["total_earning"] >= 4625.0

        # Vendor remains absent from payroll
        assert not any(r.get("worker_id") == vendor_id for r in payroll_res_after.json().get("rows", []))
