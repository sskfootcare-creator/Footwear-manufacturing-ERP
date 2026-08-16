import asyncio
import base64
import io
import os
import sys
from bson import ObjectId
from pypdf import PdfReader
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ssk_footwear_erp")
os.environ.setdefault("JWT_SECRET", "supersecretjwtkey12345!")
os.environ.setdefault("ADMIN_EMAIL", "sskfootcare@gmail.com")
os.environ.setdefault("ADMIN_PASSWORD", "Chandu@220494")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from auth import get_current_user_factory
import server
from server import app, db

async def verify_archive_rendering_e2e():
    server.get_current_user = await get_current_user_factory(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print("=== 1. Login as Admin ===")
        login_resp = await ac.post("/api/auth/login", json={
            "email": "sskfootcare@gmail.com",
            "password": "Chandu@220494"
        })
        assert login_resp.status_code == 200, "Login failed"

        print("\n=== 2. Creating Test POs and Jobs ===")
        # PO 1: For Group A and Group B (will be merged)
        po1_res = await db.pos.insert_one({
            "po_number": "PO-ARCH-TEST-001",
            "client_name": "SIYARAM SILK MILLS LTD.",
            "status": "pending",
            "created_at": "2026-08-15T15:00:00Z",
            "line_items": [
                {"style_code": "SSK_00001", "description": "Shoe Black", "color": "Black", "size": "8", "quantity": 30, "unit_price": 1000.0, "amount": 30000.0},
                {"style_code": "SSK_00001", "description": "Shoe Brown", "color": "Brown", "size": "9", "quantity": 20, "unit_price": 1000.0, "amount": 20000.0},
            ],
            "cgst_rate": 6.0, "sgst_rate": 6.0, "igst_rate": 0.0,
        })
        po1_id = str(po1_res.inserted_id)

        # Job 1 (Group A) - 30 pairs, 3 cartons
        j1_res = await db.production_jobs.insert_one({
            "po_id": po1_id, "po_number": "PO-ARCH-TEST-001", "style_code": "SSK_00001", "color": "Black", "size": "8",
            "quantity": 30, "completed_qty": 30, "stage": "qc_pack", "unit_price": 1000.0, "client_name": "SIYARAM SILK MILLS LTD.",
        })
        j1_id = str(j1_res.inserted_id)
        c1_ids = []
        for i in range(3):
            cr = await db.packing_cartons.insert_one({
                "po_id": po1_id, "job_id": j1_id, "style_code": "SSK_00001", "color": "Black", "size": "8", "qty": 10, "status": "packed", "box_number": i + 1,
            })
            c1_ids.append(cr.inserted_id)

        # Job 2 (Group B) - 20 pairs, 2 cartons
        j2_res = await db.production_jobs.insert_one({
            "po_id": po1_id, "po_number": "PO-ARCH-TEST-001", "style_code": "SSK_00001", "color": "Brown", "size": "9",
            "quantity": 20, "completed_qty": 20, "stage": "qc_pack", "unit_price": 1000.0, "client_name": "SIYARAM SILK MILLS LTD.",
        })
        j2_id = str(j2_res.inserted_id)
        c2_ids = []
        for i in range(2):
            cr = await db.packing_cartons.insert_one({
                "po_id": po1_id, "job_id": j2_id, "style_code": "SSK_00001", "color": "Brown", "size": "9", "qty": 10, "status": "packed", "box_number": i + 1,
            })
            c2_ids.append(cr.inserted_id)

        # PO 2: For Group C (non-merged individual)
        po2_res = await db.pos.insert_one({
            "po_number": "PO-ARCH-TEST-002",
            "client_name": "SIYARAM SILK MILLS LTD.",
            "status": "pending",
            "created_at": "2026-08-15T15:00:00Z",
            "line_items": [
                {"style_code": "SSK_00002", "description": "Shoe Navy", "color": "Navy", "size": "10", "quantity": 10, "unit_price": 1200.0, "amount": 12000.0},
            ],
            "cgst_rate": 6.0, "sgst_rate": 6.0, "igst_rate": 0.0,
        })
        po2_id = str(po2_res.inserted_id)

        # Job 3 (Group C) - 10 pairs, 1 carton
        j3_res = await db.production_jobs.insert_one({
            "po_id": po2_id, "po_number": "PO-ARCH-TEST-002", "style_code": "SSK_00002", "color": "Navy", "size": "10",
            "quantity": 10, "completed_qty": 10, "stage": "qc_pack", "unit_price": 1200.0, "client_name": "SIYARAM SILK MILLS LTD.",
        })
        j3_id = str(j3_res.inserted_id)
        c3_res = await db.packing_cartons.insert_one({
            "po_id": po2_id, "job_id": j3_id, "style_code": "SSK_00002", "color": "Navy", "size": "10", "qty": 10, "status": "packed", "box_number": 1,
        })
        c3_id = c3_res.inserted_id

        print("Created PO1 (Job 1 Black, Job 2 Brown) and PO2 (Job 3 Navy)")

        print("\n=== 3. Executing Dispatches and Merged Invoice ===")
        # Dispatch Group A
        disp_a = await ac.post("/api/dispatch", json={"po_id": po1_id, "job_ids": [j1_id], "transport_mode": "Road", "vehicle_no": "MH-04-1234"})
        dr_a_id = disp_a.headers.get("x-dispatch-record-id")

        # Dispatch Group B
        disp_b = await ac.post("/api/dispatch", json={"po_id": po1_id, "job_ids": [j2_id], "transport_mode": "Road", "vehicle_no": "MH-04-1234"})
        dr_b_id = disp_b.headers.get("x-dispatch-record-id")

        # Merge Group A and Group B
        merged_resp = await ac.post("/api/invoices/merged", json={
            "entries": [
                {"po_id": po1_id, "job_ids": [j1_id]},
                {"po_id": po1_id, "job_ids": [j2_id]},
            ],
            "transport_mode": "Road",
            "vehicle_no": "MH-04-1234",
            "supply_date": "2026-08-15",
        })
        merged_inv_id = merged_resp.headers.get("x-invoice-id")
        print(f"Merged invoice generated: {merged_inv_id}")

        # Dispatch Group C (Individual non-merged)
        disp_c = await ac.post("/api/dispatch", json={"po_id": po2_id, "job_ids": [j3_id], "transport_mode": "Road", "vehicle_no": "MH-04-5678"})
        dr_c_id = disp_c.headers.get("x-dispatch-record-id")
        print(f"Individual dispatch C generated: {dr_c_id}")

        # Also create a saved packing list for each so they qualify as archived
        await db.packing_lists.insert_one({"po_id": po1_id, "job_ids": [j1_id], "created_at": "2026-08-15T15:10:00Z"})
        await db.packing_lists.insert_one({"po_id": po1_id, "job_ids": [j2_id], "created_at": "2026-08-15T15:10:00Z"})
        await db.packing_lists.insert_one({"po_id": po2_id, "job_ids": [j3_id], "created_at": "2026-08-15T15:10:00Z"})

        print("\n=== 4. Fetching Archive Data from API (Simulating Frontend Load) ===")
        arch_jobs_resp = await ac.get("/api/production/archive")
        assert arch_jobs_resp.status_code == 200
        arch_jobs = arch_jobs_resp.json()

        dispatch_records_resp = await ac.get("/api/dispatch-records?limit=1000")
        assert dispatch_records_resp.status_code == 200
        dispatch_records = dispatch_records_resp.json()

        invoices_resp = await ac.get("/api/invoices")
        assert invoices_resp.status_code == 200
        invoices = invoices_resp.json()

        print(f"Loaded {len(arch_jobs)} archived jobs, {len(dispatch_records)} dispatch records, {len(invoices)} invoices")

        # Test merged invoice file download
        inv_file_resp = await ac.get(f"/api/invoices/{merged_inv_id}/file")
        assert inv_file_resp.status_code == 200
        assert len(inv_file_resp.content) > 1000
        print(f"VERIFIED: Merged invoice download /invoices/{merged_inv_id}/file returned 200 OK ({len(inv_file_resp.content)} bytes)")

        # Test merged labels download
        labels_file_resp = await ac.get(f"/api/invoices/{merged_inv_id}/carton-labels")
        assert labels_file_resp.status_code == 200
        assert len(labels_file_resp.content) > 1000
        print(f"VERIFIED: Merged carton labels download /invoices/{merged_inv_id}/carton-labels returned 200 OK ({len(labels_file_resp.content)} bytes)")

        # Test individual group pre-merge document links
        dr_a_inv = await ac.get(f"/api/dispatch-records/{dr_a_id}/invoice")
        assert dr_a_inv.status_code == 200
        dr_a_lbl = await ac.get(f"/api/dispatch-records/{dr_a_id}/carton-labels")
        assert dr_a_lbl.status_code == 200
        print(f"VERIFIED: Individual pre-merge documents for Group A reachable via /dispatch-records/{dr_a_id}/...")

        dr_b_inv = await ac.get(f"/api/dispatch-records/{dr_b_id}/invoice")
        assert dr_b_inv.status_code == 200
        dr_b_lbl = await ac.get(f"/api/dispatch-records/{dr_b_id}/carton-labels")
        assert dr_b_lbl.status_code == 200
        print(f"VERIFIED: Individual pre-merge documents for Group B reachable via /dispatch-records/{dr_b_id}/...")

        # Test individual dispatch C document links
        dr_c_inv = await ac.get(f"/api/dispatch-records/{dr_c_id}/invoice")
        assert dr_c_inv.status_code == 200
        print(f"VERIFIED: Non-merged Group C invoice reachable via /dispatch-records/{dr_c_id}/invoice")

        print("\n=== 5. Clean up test records ===")
        await db.pos.delete_many({"_id": {"$in": [ObjectId(po1_id), ObjectId(po2_id)]}})
        await db.production_jobs.delete_many({"_id": {"$in": [ObjectId(j1_id), ObjectId(j2_id), ObjectId(j3_id)]}})
        await db.packing_cartons.delete_many({"_id": {"$in": c1_ids + c2_ids + [c3_id]}})
        await db.dispatch_records.delete_many({"_id": {"$in": [ObjectId(dr_a_id), ObjectId(dr_b_id), ObjectId(dr_c_id)]}})
        # Delete test invoices created during this test
        await db.invoices.delete_many({"_id": {"$in": [ObjectId(merged_inv_id)]}})
        # Clean test packing lists
        await db.packing_lists.delete_many({"po_id": {"$in": [po1_id, po2_id]}})
        # Ensure sequence counter restored to 19
        await db.counters.update_one({"_id": "invoice_26-27"}, {"$set": {"seq": 19}})
        print("Test data cleaned up and counter restored to 19.")

    print("\nALL ARCHIVE RENDERING E2E TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(verify_archive_rendering_e2e())
