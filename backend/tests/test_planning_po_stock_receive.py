import pytest
from httpx import AsyncClient, ASGITransport
import uuid
import os
import server


@pytest.mark.anyio
async def test_planning_po_receipt_adds_to_inventory_stock():
    app = server.app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as admin — use canonical credentials from env (same as conftest defaults)
        _email = os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com")
        _pass  = os.environ.get("ADMIN_PASSWORD", "Admin@123")
        login_res = await client.post("/api/auth/login", json={"email": _email, "password": _pass})
        assert login_res.status_code == 200, login_res.text
        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        uid = uuid.uuid4().hex[:6].upper()

        # 1. Create a Vendor
        v_resp = await client.post("/api/vendors", json={
            "name": f"Test Leather Co {uid}",
            "gstin": "27AADCB9999M1ZX",
            "contact_person": "Mr Sharma",
            "phone": "9998887777",
            "address": "Agra Hub",
            "payment_terms_days": 15
        }, headers=headers)
        assert v_resp.status_code in (200, 201), v_resp.text
        vendor = v_resp.json()
        vendor_id = vendor["id"]

        # 2. Create a Material
        mat_code = f"MAT-TEST-{uid}"
        m_resp = await client.post("/api/materials", json={
            "code": mat_code,
            "name": f"Black Synthetic Leather {uid}",
            "category": "upper",
            "unit": "sqft",
            "rate": 150.0,
            "reorder_level": 10.0,
            "preferred_vendor_id": vendor_id
        }, headers=headers)
        assert m_resp.status_code == 200, m_resp.text
        material = m_resp.json()
        mat_id = material["id"]

        # Verify initial stock is 0
        inv_init_resp = await client.get("/api/inventory", headers=headers)
        assert inv_init_resp.status_code == 200
        inv_init = inv_init_resp.json()
        init_item = next((i for i in inv_init if i["material_id"] == mat_id or i["code"] == mat_code), None)
        assert init_item is not None
        assert init_item["balance"] == 0.0

        # 3. Retrieve or create a Production Job
        jobs_resp = await client.get("/api/production/jobs?source_type=all", headers=headers)
        assert jobs_resp.status_code == 200, jobs_resp.text
        jobs = jobs_resp.json()
        if not jobs:
            style_resp = await client.post("/api/styles", json={
                "code": f"SSK-TEST-{uid}",
                "name": f"Test Oxford {uid}",
                "category": "shoes"
            }, headers=headers)
            style_code = style_resp.json().get("code", f"SSK-TEST-{uid}")
            po_resp = await client.post("/api/pos", json={
                "po_number": f"PO-TEST-{uid}",
                "client_name": "Test Client",
                "po_date": "2026-10-01",
                "delivery_date": "2026-11-01",
                "line_items": [
                    {
                        "style_code": style_code,
                        "color": "Black",
                        "size": "8",
                        "quantity": 100,
                        "unit_price": 500.0,
                        "amount": 50000.0
                    }
                ]
            }, headers=headers)
            assert po_resp.status_code == 200, po_resp.text
            jobs_resp = await client.get("/api/production/jobs?source_type=all", headers=headers)
            jobs = jobs_resp.json()
        assert len(jobs) > 0, "No production jobs available"
        job = jobs[0]
        job_id = job["id"]

        # 4. Generate Vendor PO from Planning Stage
        plan_resp = await client.post("/api/production/planning/generate-vendor-pos", json={
            "job_ids": [job_id],
            "customer_po_number": f"PO-CUST-{uid}",
            "style_code": f"STYLE-{uid}",
            "color": "Black",
            "allocations": [
                {
                    "material_id": mat_id,
                    "material_code": mat_code,
                    "material_name": material["name"],
                    "unit": "sqft",
                    "quantity": 100.0,
                    "rate": 150.0,
                    "amount": 15000.0,
                    "vendor_id": vendor_id,
                    "vendor_name": vendor["name"]
                }
            ]
        }, headers=headers)
        assert plan_resp.status_code == 201, plan_resp.text
        plan_data = plan_resp.json()
        vpos = plan_data.get("vendor_pos", [])
        assert len(vpos) == 1
        vpo = vpos[0]
        vpo_id = vpo["id"]
        assert vpo["line_items"][0]["material_id"] == mat_id

        # 5. Receive Material against Vendor PO
        rcpt_id = f"rcpt_test_{uid}"
        receive_resp = await client.post(f"/api/vendor-pos/{vpo_id}/receive", json={
            "receipt_id": rcpt_id,
            "items": [
                {
                    "material_id": mat_id,
                    "quantity": 60.0
                }
            ]
        }, headers=headers)
        assert receive_resp.status_code == 200, receive_resp.text

        # 6. Verify movement shows in history (/inventory/movements)
        mov_resp = await client.get(f"/api/inventory/movements?material_id={mat_id}", headers=headers)
        assert mov_resp.status_code == 200, mov_resp.text
        movements = mov_resp.json()
        assert len(movements) >= 1
        assert any(m.get("receipt_id") == rcpt_id and m.get("quantity") == 60.0 for m in movements)

        # 7. CRITICAL VERIFICATION:
        # GET /inventory must return the updated balance / total count == 60.0!
        inv_after_resp = await client.get("/api/inventory", headers=headers)
        assert inv_after_resp.status_code == 200
        inv_after = inv_after_resp.json()
        after_item = next((i for i in inv_after if i["material_id"] == mat_id or i["code"] == mat_code), None)
        assert after_item is not None, f"Material {mat_code} not found in /inventory"
        assert after_item["balance"] == 60.0, f"Expected balance 60.0 but got {after_item['balance']}"
        assert after_item.get("current_stock") == 60.0

        mat_doc_after_resp = await client.get(f"/api/materials/{mat_id}", headers=headers)
        assert mat_doc_after_resp.status_code == 200
        mat_doc_after = mat_doc_after_resp.json()
        assert mat_doc_after.get("balance") == 60.0
        assert mat_doc_after.get("current_stock") == 60.0

        # 8. Receive the remaining 40.0
        rcpt_id_2 = f"rcpt_test2_{uid}"
        receive_resp_2 = await client.post(f"/api/vendor-pos/{vpo_id}/receive", json={
            "receipt_id": rcpt_id_2,
            "items": [
                {
                    "material_id": mat_id,
                    "quantity": 40.0
                }
            ]
        }, headers=headers)
        assert receive_resp_2.status_code == 200, receive_resp_2.text

        inv_final_resp = await client.get("/api/inventory", headers=headers)
        assert inv_final_resp.status_code == 200
        inv_final = inv_final_resp.json()
        final_item = next((i for i in inv_final if i["material_id"] == mat_id or i["code"] == mat_code), None)
        assert final_item is not None
        assert final_item["balance"] == 100.0, f"Expected balance 100.0 but got {final_item['balance']}"
        assert final_item.get("current_stock") == 100.0

        mat_doc_final_resp = await client.get(f"/api/materials/{mat_id}", headers=headers)
        assert mat_doc_final_resp.status_code == 200
        mat_doc_final = mat_doc_final_resp.json()
        assert mat_doc_final.get("balance") == 100.0
        assert mat_doc_final.get("current_stock") == 100.0

        # Cleanup test resources
        await client.delete(f"/api/vendor-pos/{vpo_id}", headers=headers)
        await client.delete(f"/api/materials/{mat_id}", headers=headers)
        await client.delete(f"/api/vendors/{vendor_id}", headers=headers)
