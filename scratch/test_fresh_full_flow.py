import asyncio
import base64
import hashlib
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

async def run_fresh_flow_test():
    server.get_current_user = await get_current_user_factory(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print("=== STEP 1: Authenticate Admin User ===")
        login_resp = await ac.post("/api/auth/login", json={
            "email": "sskfootcare@gmail.com",
            "password": "Chandu@220494"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        print("Admin login successful.")

        print("\n=== STEP 2: Create Fresh PO and 2 Job Groups ===")
        # Baseline invoice count in db
        inv_count_start = await db.invoices.count_documents({})
        print(f"Starting db.invoices count: {inv_count_start}")

        # PO with 2 styles/colors
        po_doc = {
            "po_number": "PO-FRESH-FLOW-2026",
            "client_name": "SIYARAM SILK MILLS LTD.",
            "status": "pending",
            "created_at": "2026-08-15T15:30:00Z",
            "line_items": [
                {"style_code": "SSK_00001", "description": "Derby Classic Black", "color": "Black", "size": "8", "quantity": 30, "unit_price": 1100.0, "amount": 33000.0},
                {"style_code": "SSK_00001", "description": "Derby Classic Tan", "color": "Tan", "size": "9", "quantity": 20, "unit_price": 1100.0, "amount": 22000.0},
            ],
            "cgst_rate": 6.0,
            "sgst_rate": 6.0,
            "igst_rate": 0.0,
        }
        po_res = await db.pos.insert_one(po_doc)
        po_id = str(po_res.inserted_id)

        # Job Group A (Black / Size 8) - 3 cartons (10 pairs each = 30 pairs)
        j1_res = await db.production_jobs.insert_one({
            "po_id": po_id, "po_number": "PO-FRESH-FLOW-2026", "style_code": "SSK_00001", "color": "Black", "size": "8",
            "quantity": 30, "completed_qty": 30, "stage": "qc_pack", "unit_price": 1100.0, "client_name": "SIYARAM SILK MILLS LTD.",
        })
        j1_id = str(j1_res.inserted_id)
        c1_ids = []
        for i in range(3):
            cr = await db.packing_cartons.insert_one({
                "po_id": po_id, "job_id": j1_id, "style_code": "SSK_00001", "color": "Black", "size": "8",
                "qty": 10, "status": "packed", "box_number": i + 1,
            })
            c1_ids.append(cr.inserted_id)

        # Job Group B (Tan / Size 9) - 2 cartons (10 pairs each = 20 pairs)
        j2_res = await db.production_jobs.insert_one({
            "po_id": po_id, "po_number": "PO-FRESH-FLOW-2026", "style_code": "SSK_00001", "color": "Tan", "size": "9",
            "quantity": 20, "completed_qty": 20, "stage": "qc_pack", "unit_price": 1100.0, "client_name": "SIYARAM SILK MILLS LTD.",
        })
        j2_id = str(j2_res.inserted_id)
        c2_ids = []
        for i in range(2):
            cr = await db.packing_cartons.insert_one({
                "po_id": po_id, "job_id": j2_id, "style_code": "SSK_00001", "color": "Tan", "size": "9",
                "qty": 10, "status": "packed", "box_number": i + 1,
            })
            c2_ids.append(cr.inserted_id)

        print(f"Created PO {po_id}, Job Group A ({j1_id}, 3 cartons), Job Group B ({j2_id}, 2 cartons)")

        print("\n=== STEP 3: Dispatch Job Group A and Job Group B Individually ===")
        # Dispatch Group A
        disp_a = await ac.post("/api/dispatch", json={"po_id": po_id, "job_ids": [j1_id], "transport_mode": "Road", "vehicle_no": "MH-04-1234"})
        assert disp_a.status_code == 200
        dr_a_id = disp_a.headers.get("x-dispatch-record-id")
        print(f"Group A dispatched individually -> DR ID: {dr_a_id}")

        # Dispatch Group B
        disp_b = await ac.post("/api/dispatch", json={"po_id": po_id, "job_ids": [j2_id], "transport_mode": "Road", "vehicle_no": "MH-04-1234"})
        assert disp_b.status_code == 200
        dr_b_id = disp_b.headers.get("x-dispatch-record-id")
        print(f"Group B dispatched individually -> DR ID: {dr_b_id}")

        # Check Group A original labels (1/3, 2/3, 3/3)
        dr_a_doc = await db.dispatch_records.find_one({"_id": ObjectId(dr_a_id)})
        reader_a = PdfReader(io.BytesIO(base64.b64decode(dr_a_doc["carton_labels_file_b64"])))
        text_a = "".join(p.extract_text() or "" for p in reader_a.pages)
        assert "1/3" in text_a and "2/3" in text_a and "3/3" in text_a
        print("CONFIRMED: Group A original labels have boxes 1/3, 2/3, 3/3.")

        # Check Group B original labels (1/2, 2/2)
        dr_b_doc = await db.dispatch_records.find_one({"_id": ObjectId(dr_b_id)})
        reader_b = PdfReader(io.BytesIO(base64.b64decode(dr_b_doc["carton_labels_file_b64"])))
        text_b = "".join(p.extract_text() or "" for p in reader_b.pages)
        assert "1/2" in text_b and "2/2" in text_b
        print("CONFIRMED: Group B original labels have boxes 1/2, 2/2.")

        print("\n=== STEP 4: Merge Invoices via POST /api/invoices/merged ===")
        merge_resp = await ac.post("/api/invoices/merged", json={
            "entries": [
                {"po_id": po_id, "job_ids": [j1_id]},
                {"po_id": po_id, "job_ids": [j2_id]},
            ],
            "transport_mode": "Road",
            "vehicle_no": "MH-04-1234",
            "supply_date": "2026-08-15",
        })
        assert merge_resp.status_code == 200
        merged_inv_id = merge_resp.headers.get("x-invoice-id")
        print(f"Merged invoice created successfully -> Invoice ID: {merged_inv_id}")

        # Fetch merged invoice document
        merged_inv = await db.invoices.find_one({"_id": ObjectId(merged_inv_id)})
        merged_inv_no = merged_inv["invoice_no"]
        print(f"Merged Invoice Number: {merged_inv_no}")

        print("\n=== STEP 5: Verify Continuous Carton Numbering in Combined Labels ===")
        lbl_resp = await ac.get(f"/api/invoices/{merged_inv_id}/carton-labels")
        assert lbl_resp.status_code == 200
        merged_labels_bytes = lbl_resp.content
        assert len(merged_labels_bytes) > 1000

        merged_lbl_reader = PdfReader(io.BytesIO(merged_labels_bytes))
        merged_lbl_text = "".join(p.extract_text() or "" for p in merged_lbl_reader.pages)
        
        # Verify 1/5 through 5/5
        for box in ["1/5", "2/5", "3/5", "4/5", "5/5"]:
            assert box in merged_lbl_text, f"Missing carton box number {box} in merged labels text!"
        print("CONFIRMED: Combined labels contain continuous carton numbering: 1/5, 2/5, 3/5, 4/5, 5/5.")

        # Verify invoice number on labels matches merged invoice number
        assert merged_inv_no in merged_lbl_text, f"Invoice number {merged_inv_no} not found on labels!"
        print(f"CONFIRMED: Combined labels display matching invoice number: {merged_inv_no}.")

        print("\n=== STEP 6: Verify Zero Duplicate Invoices on Multiple Downloads ===")
        # Count before clicking
        inv_count_before = await db.invoices.count_documents({})
        print(f"db.invoices count before clicks: {inv_count_before}")

        # Click 1
        click1_resp = await ac.get(f"/api/invoices/{merged_inv_id}/file")
        assert click1_resp.status_code == 200
        click1_bytes = click1_resp.content
        click1_hash = hashlib.sha256(click1_bytes).hexdigest()

        # Click 2
        click2_resp = await ac.get(f"/api/invoices/{merged_inv_id}/file")
        assert click2_resp.status_code == 200
        click2_bytes = click2_resp.content
        click2_hash = hashlib.sha256(click2_bytes).hexdigest()

        # Verify byte identity
        assert click1_bytes == click2_bytes, "Click 1 and Click 2 invoice bytes differ!"
        assert click1_hash == click2_hash, "Click 1 and Click 2 hashes differ!"
        print(f"CONFIRMED: Click 1 and Click 2 invoice files are 100% BYTE-IDENTICAL (SHA256: {click1_hash})")

        # Count after clicking
        inv_count_after = await db.invoices.count_documents({})
        assert inv_count_before == inv_count_after, f"db.invoices count increased from {inv_count_before} to {inv_count_after}!"
        print(f"CONFIRMED: db.invoices count strictly unchanged ({inv_count_after}). Zero duplicate records created.")

        print("\n=== STEP 7: Verify Pre-Merge Individual Documents Remain Intact ===")
        dr_a_after = await db.dispatch_records.find_one({"_id": ObjectId(dr_a_id)})
        dr_b_after = await db.dispatch_records.find_one({"_id": ObjectId(dr_b_id)})
        assert dr_a_after["carton_labels_file_b64"] == dr_a_doc["carton_labels_file_b64"]
        assert dr_b_after["carton_labels_file_b64"] == dr_b_doc["carton_labels_file_b64"]
        print("CONFIRMED: Pre-merge individual dispatch records and documents remain untouched.")

        print("\n=== STEP 8: Cleanup Test Data ===")
        await db.pos.delete_one({"_id": ObjectId(po_id)})
        await db.production_jobs.delete_many({"_id": {"$in": [ObjectId(j1_id), ObjectId(j2_id)]}})
        await db.packing_cartons.delete_many({"_id": {"$in": c1_ids + c2_ids}})
        await db.dispatch_records.delete_many({"_id": {"$in": [ObjectId(dr_a_id), ObjectId(dr_b_id)]}})
        await db.invoices.delete_one({"_id": ObjectId(merged_inv_id)})
        await db.counters.update_one({"_id": "invoice_26-27"}, {"$set": {"seq": 19}})
        print("Cleaned up test records and restored invoice counter to 19.")

    print("\n>>> ALL FRESH MERGED FLOW CHECKS PASSED WITH 100% SUCCESS! <<<")

if __name__ == "__main__":
    asyncio.run(run_fresh_flow_test())
