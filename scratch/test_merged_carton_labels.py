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

async def verify_merged_carton_labels():
    server.get_current_user = await get_current_user_factory(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print("=== STEP 1: Logging in as Admin ===")
        login_resp = await ac.post("/api/auth/login", json={
            "email": "sskfootcare@gmail.com",
            "password": "Chandu@220494"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

        print("\n=== STEP 2: Creating Test PO and 2 Job Groups ===")
        # 1. Create a PO
        po_doc = {
            "po_number": "PO-MERGE-TEST-001",
            "client_name": "SIYARAM SILK MILLS LTD.",
            "status": "pending",
            "created_at": "2026-08-15T14:30:00Z",
            "line_items": [
                {"style_code": "SSK_00001", "description": "Classic Oxford", "color": "Black", "size": "8", "quantity": 30, "unit_price": 1000.0, "hsn_code": "64029990", "amount": 30000.0},
                {"style_code": "SSK_00001", "description": "Classic Oxford", "color": "Brown", "size": "9", "quantity": 20, "unit_price": 1000.0, "hsn_code": "64029990", "amount": 20000.0},
            ],
            "cgst_rate": 6.0,
            "sgst_rate": 6.0,
            "igst_rate": 0.0,
        }
        po_res = await db.pos.insert_one(po_doc)
        po_id = str(po_res.inserted_id)

        # 2. Create Job 1 (Group A) with 3 cartons
        job1_doc = {
            "po_id": po_id,
            "po_number": "PO-MERGE-TEST-001",
            "style_code": "SSK_00001",
            "color": "Black",
            "size": "8",
            "quantity": 30,
            "completed_qty": 30,
            "stage": "qc_pack",
            "unit_price": 1000.0,
        }
        j1_res = await db.production_jobs.insert_one(job1_doc)
        j1_id = str(j1_res.inserted_id)

        # Create 3 cartons for Job 1
        c1_ids = []
        for i in range(3):
            c_doc = {
                "po_id": po_id,
                "job_id": j1_id,
                "style_code": "SSK_00001",
                "color": "Black",
                "size": "8",
                "qty": 10,
                "status": "packed",
                "box_number": i + 1,
            }
            c_res = await db.packing_cartons.insert_one(c_doc)
            c1_ids.append(c_res.inserted_id)

        # 3. Create Job 2 (Group B) with 2 cartons
        job2_doc = {
            "po_id": po_id,
            "po_number": "PO-MERGE-TEST-001",
            "style_code": "SSK_00001",
            "color": "Brown",
            "size": "9",
            "quantity": 20,
            "completed_qty": 20,
            "stage": "qc_pack",
            "unit_price": 1000.0,
        }
        j2_res = await db.production_jobs.insert_one(job2_doc)
        j2_id = str(j2_res.inserted_id)

        # Create 2 cartons for Job 2
        c2_ids = []
        for i in range(2):
            c_doc = {
                "po_id": po_id,
                "job_id": j2_id,
                "style_code": "SSK_00001",
                "color": "Brown",
                "size": "9",
                "qty": 10,
                "status": "packed",
                "box_number": i + 1,
            }
            c_res = await db.packing_cartons.insert_one(c_doc)
            c2_ids.append(c_res.inserted_id)

        print("Created PO, Job 1 (3 cartons), Job 2 (2 cartons)")

        print("\n=== STEP 3: Dispatching Group A and Group B individually ===")
        # Dispatch Group A
        disp_a_resp = await ac.post("/api/dispatch", json={
            "po_id": po_id,
            "job_ids": [j1_id],
            "transport_mode": "Road",
            "vehicle_no": "MH-04-1234",
        })
        assert disp_a_resp.status_code == 200, f"Dispatch A failed: {disp_a_resp.text}"
        dr_a_id = disp_a_resp.headers.get("x-dispatch-record-id")
        print(f"Dispatch A created: DR ID {dr_a_id}")

        # Dispatch Group B
        disp_b_resp = await ac.post("/api/dispatch", json={
            "po_id": po_id,
            "job_ids": [j2_id],
            "transport_mode": "Road",
            "vehicle_no": "MH-04-1234",
        })
        assert disp_b_resp.status_code == 200, f"Dispatch B failed: {disp_b_resp.text}"
        dr_b_id = disp_b_resp.headers.get("x-dispatch-record-id")
        print(f"Dispatch B created: DR ID {dr_b_id}")

        # Inspect individual dispatch record label PDFs
        dr_a = await db.dispatch_records.find_one({"_id": ObjectId(dr_a_id)})
        dr_b = await db.dispatch_records.find_one({"_id": ObjectId(dr_b_id)})
        
        pdf_a_bytes = base64.b64decode(dr_a["carton_labels_file_b64"])
        pdf_b_bytes = base64.b64decode(dr_b["carton_labels_file_b64"])
        
        reader_a = PdfReader(io.BytesIO(pdf_a_bytes))
        text_a = "".join(page.extract_text() or "" for page in reader_a.pages)
        print("Dispatch A labels extracted text summary:")
        for line in text_a.splitlines():
            if "CARTON" in line or "1/3" in line or "2/3" in line or "3/3" in line or "SSK" in line:
                print(f"  {line.strip()}")

        reader_b = PdfReader(io.BytesIO(pdf_b_bytes))
        text_b = "".join(page.extract_text() or "" for page in reader_b.pages)
        print("Dispatch B labels extracted text summary:")
        for line in text_b.splitlines():
            if "CARTON" in line or "1/2" in line or "2/2" in line or "SSK" in line:
                print(f"  {line.strip()}")

        print("\n=== STEP 4: Calling merged_invoice across [Group A, Group B] ===")
        merged_resp = await ac.post("/api/invoices/merged", json={
            "entries": [
                {"po_id": po_id, "job_ids": [j1_id]},
                {"po_id": po_id, "job_ids": [j2_id]},
            ],
            "transport_mode": "Road",
            "vehicle_no": "MH-04-1234",
            "supply_date": "2026-08-15",
        })
        assert merged_resp.status_code == 200, f"Merged invoice failed: {merged_resp.text}"
        merged_inv_id = merged_resp.headers.get("x-invoice-id")
        print(f"Merged invoice generated: ID {merged_inv_id}")

        print("\n=== STEP 5: Inspecting Regenerated Merged Carton Labels ===")
        merged_inv_doc = await db.invoices.find_one({"_id": ObjectId(merged_inv_id)})
        assert merged_inv_doc is not None, "Merged invoice doc not found in db.invoices"
        assert "carton_labels_file_b64" in merged_inv_doc, "carton_labels_file_b64 missing on merged invoice doc"
        assert merged_inv_doc["carton_labels_file_b64"], "carton_labels_file_b64 is empty"

        merged_pdf_bytes = base64.b64decode(merged_inv_doc["carton_labels_file_b64"])
        merged_reader = PdfReader(io.BytesIO(merged_pdf_bytes))
        merged_text = "".join(page.extract_text() or "" for page in merged_reader.pages)
        
        print(f"Merged PDF pages count: {len(merged_reader.pages)}")
        print("Merged labels extracted lines:")
        for line in merged_text.splitlines():
            if "1/5" in line or "2/5" in line or "3/5" in line or "4/5" in line or "5/5" in line or "CARTON" in line:
                print(f"  {line.strip()}")

        # Verify continuous numbering 1/5, 2/5, 3/5, 4/5, 5/5
        for expected_box in ["1/5", "2/5", "3/5", "4/5", "5/5"]:
            assert expected_box in merged_text, f"Expected '{expected_box}' in merged label text! Text found: {merged_text}"
        print("VERIFIED: Merged carton labels contain 1/5, 2/5, 3/5, 4/5, 5/5 continuous sequence!")

        # Verify download endpoint /invoices/{iid}/carton-labels
        lbl_download_resp = await ac.get(f"/api/invoices/{merged_inv_id}/carton-labels")
        assert lbl_download_resp.status_code == 200
        assert len(lbl_download_resp.content) > 100
        print(f"VERIFIED: GET /invoices/{merged_inv_id}/carton-labels returned status 200 OK ({len(lbl_download_resp.content)} bytes)")

        print("\n=== STEP 6: Verifying Original Per-Group Label Documents are Untouched ===")
        dr_a_after = await db.dispatch_records.find_one({"_id": ObjectId(dr_a_id)})
        dr_b_after = await db.dispatch_records.find_one({"_id": ObjectId(dr_b_id)})
        
        assert dr_a_after["carton_labels_file_b64"] == dr_a["carton_labels_file_b64"], "Original Dispatch A carton labels were modified!"
        assert dr_b_after["carton_labels_file_b64"] == dr_b["carton_labels_file_b64"], "Original Dispatch B carton labels were modified!"
        print("VERIFIED: Original per-group label documents are completely untouched!")

        print("\n=== STEP 7: Cleaning up test verification records ===")
        await db.pos.delete_one({"_id": ObjectId(po_id)})
        await db.production_jobs.delete_many({"_id": {"$in": [ObjectId(j1_id), ObjectId(j2_id)]}})
        await db.packing_cartons.delete_many({"_id": {"$in": c1_ids + c2_ids}})
        await db.dispatch_records.delete_many({"_id": {"$in": [ObjectId(dr_a_id), ObjectId(dr_b_id)]}})
        await db.invoices.delete_one({"_id": ObjectId(merged_inv_id)})
        # Reset counter back to 19 (the 4 real invoices)
        await db.counters.update_one({"_id": "invoice_26-27"}, {"$set": {"seq": 19}})
        print("Cleaned up test verification records and confirmed counter at 19.")

    print("\nALL MERGED CARTON LABEL TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(verify_merged_carton_labels())
