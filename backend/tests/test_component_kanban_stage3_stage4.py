import os
import pytest
from httpx import AsyncClient, ASGITransport
import server
from models.orders import ComponentStageUpdate
from services.component_spec_service import derive_component_specs, init_component_tracks


@pytest.mark.anyio
async def test_component_stage_update_and_payroll_flow():
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

        # 2. Create worker for payroll test
        worker_res = await client.post("/api/workers", json={
            "name": "Ramesh Kumar Karigar",
            "skill": "upper_cutting",
            "phone": "9876543210",
            "rate_per_pair": 15.0,
        }, headers=headers)
        assert worker_res.status_code in (200, 201)
        worker_id = worker_res.json()["id"]

        # 3. Create a style with footwear_type="heel"
        style_res = await client.post("/api/styles", json={
            "name": "Heel Party Sandal",
            "category": "Footwear",
            "footwear_type": "heel",
            "bom": [],
            "labor": [],
        }, headers=headers)
        assert style_res.status_code == 200
        style_id = style_res.json()["id"]
        style_code = style_res.json()["code"]

        # 4. Insert a test production job with component_specs and component_tracks
        specs = {
            "footwear_type": "heel",
            "components": {
                "upper": {"stages": ["cutting", "stitching"], "ready_if_empty": False},
                "bottom": {"stages": ["cutting"], "ready_if_empty": True},
                "sole": {"stages": ["finishing"], "ready_if_empty": True},
                "heel_gola": {"stages": ["cover_cutting", "folding"], "ready_if_empty": True},
            }
        }
        tracks = init_component_tracks(specs)
        job_doc = {
            "source_type": "b2b_client",
            "client_name": "Test Boutique",
            "style_code": style_code,
            "style_id": style_id,
            "quantity": 100,
            "completed_qty": 0,
            "stage": "planning",
            "component_specs": specs,
            "component_tracks": tracks,
            "components": {"upper_done": False, "bottom_done": False, "sole_done": False},
            "history": [],
            "created_at": server.now_iso(),
            "updated_at": server.now_iso(),
        }
        insert_res = await server.db.production_jobs.insert_one(job_doc)
        job_id = str(insert_res.inserted_id)

        # 5. Verify lasting gate blocks advance
        gate_res = await client.patch(f"/api/production/jobs/{job_id}", json={"stage": "lasting"}, headers=headers)
        assert gate_res.status_code == 400
        assert "Cannot move to lasting" in gate_res.json()["detail"]

        # 6. Complete upper.cutting with worker_id
        comp_res1 = await client.patch(f"/api/production/jobs/{job_id}/component-stage", json={
            "component": "upper",
            "stage": "cutting",
            "completed_qty": 100,
            "worker_id": worker_id,
            "notes": "Finished cutting all 100 pairs",
        }, headers=headers)
        assert comp_res1.status_code == 200
        job_after_cut = comp_res1.json()
        assert job_after_cut["component_tracks"]["upper"]["current_stage"] == "stitching"
        assert "cutting" in job_after_cut["component_tracks"]["upper"]["stages_completed"]
        assert "upper.cutting" in job_after_cut["assignments"]
        assert job_after_cut["assignments"]["upper.cutting"]["worker_id"] == worker_id

        # 7. Complete upper.stitching -> upper enters ready
        comp_res2 = await client.patch(f"/api/production/jobs/{job_id}/component-stage", json={
            "component": "upper",
            "stage": "stitching",
            "completed_qty": 100,
            "worker_id": worker_id,
        }, headers=headers)
        assert comp_res2.status_code == 200
        job_after_stitch = comp_res2.json()
        assert job_after_stitch["component_tracks"]["upper"]["status"] == "ready"
        assert job_after_stitch["components"]["upper_done"] is True

        # Lasting still blocked because bottom is not ready
        gate_res2 = await client.patch(f"/api/production/jobs/{job_id}", json={"stage": "lasting"}, headers=headers)
        assert gate_res2.status_code == 400
        assert "bottom" in gate_res2.json()["detail"]

        # Complete bottom.cutting -> bottom enters ready
        comp_res3 = await client.patch(f"/api/production/jobs/{job_id}/component-stage", json={
            "component": "bottom",
            "stage": "cutting",
            "completed_qty": 100,
        }, headers=headers)
        assert comp_res3.status_code == 200
        assert comp_res3.json()["component_tracks"]["bottom"]["status"] == "ready"
        assert comp_res3.json()["components"]["bottom_done"] is True

        # 8. Now moving to lasting MUST SUCCEED
        gate_res3 = await client.patch(f"/api/production/jobs/{job_id}", json={"stage": "lasting"}, headers=headers)
        assert gate_res3.status_code == 200
        assert gate_res3.json()["stage"] == "lasting"

        # 9. Verify Payroll correctly tracked upper.cutting with composite key!
        payroll_res = await client.get("/api/reports/payroll", headers=headers)
        assert payroll_res.status_code == 200
        payroll_data = payroll_res.json()
        worker_summary = next((w for w in payroll_data.get("rows", []) if w["worker_id"] == worker_id), None)
        assert worker_summary is not None
        assert worker_summary["total_pairs"] >= 100
        assert worker_summary["total_earning"] >= 1500.0
