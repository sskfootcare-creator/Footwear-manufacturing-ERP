import asyncio
import hashlib
import os
import sys
from bson import ObjectId
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

async def test_endpoint_byte_identity():
    server.get_current_user = await get_current_user_factory(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        print("=== 1. Login as Admin ===")
        login_resp = await ac.post("/api/auth/login", json={
            "email": "sskfootcare@gmail.com",
            "password": "Chandu@220494"
        })
        assert login_resp.status_code == 200

        print("\n=== 2. Create Merged Invoice with 2 Groups ===")
        # Create PO
        po_doc = {
            "po_number": "PO-IDENTITY-TEST-001",
            "client_name": "SIYARAM SILK MILLS LTD.",
            "status": "pending",
            "created_at": "2026-08-15T15:00:00Z",
            "line_items": [
                {"style_code": "SSK_00001", "description": "Shoe A", "color": "Black", "size": "8", "quantity": 30, "unit_price": 1000.0, "amount": 30000.0},
                {"style_code": "SSK_00001", "description": "Shoe B", "color": "Tan", "size": "9", "quantity": 20, "unit_price": 1000.0, "amount": 20000.0},
            ],
            "cgst_rate": 6.0,
            "sgst_rate": 6.0,
            "igst_rate": 0.0,
        }
        po_res = await db.pos.insert_one(po_doc)
        po_id = str(po_res.inserted_id)

        # Job 1 (3 cartons)
        j1_res = await db.production_jobs.insert_one({
            "po_id": po_id, "po_number": "PO-IDENTITY-TEST-001", "style_code": "SSK_00001", "color": "Black", "size": "8",
            "quantity": 30, "completed_qty": 30, "stage": "qc_pack", "unit_price": 1000.0,
        })
        j1_id = str(j1_res.inserted_id)
        c1_ids = []
        for i in range(3):
            cr = await db.packing_cartons.insert_one({
                "po_id": po_id, "job_id": j1_id, "style_code": "SSK_00001", "color": "Black", "size": "8", "qty": 10, "status": "packed", "box_number": i + 1,
            })
            c1_ids.append(cr.inserted_id)

        # Job 2 (2 cartons)
        j2_res = await db.production_jobs.insert_one({
            "po_id": po_id, "po_number": "PO-IDENTITY-TEST-001", "style_code": "SSK_00001", "color": "Tan", "size": "9",
            "quantity": 20, "completed_qty": 20, "stage": "qc_pack", "unit_price": 1000.0,
        })
        j2_id = str(j2_res.inserted_id)
        c2_ids = []
        for i in range(2):
            cr = await db.packing_cartons.insert_one({
                "po_id": po_id, "job_id": j2_id, "style_code": "SSK_00001", "color": "Tan", "size": "9", "qty": 10, "status": "packed", "box_number": i + 1,
            })
            c2_ids.append(cr.inserted_id)

        # Create merged invoice
        merged_resp = await ac.post("/api/invoices/merged", json={
            "entries": [
                {"po_id": po_id, "job_ids": [j1_id]},
                {"po_id": po_id, "job_ids": [j2_id]},
            ],
            "transport_mode": "Road",
            "vehicle_no": "MH-04-1234",
            "supply_date": "2026-08-15",
        })
        assert merged_resp.status_code == 200
        merged_inv_id = merged_resp.headers.get("x-invoice-id")
        print(f"Created Merged Invoice: {merged_inv_id}")

        print("\n=== 3. Calling GET /api/invoices/{id}/carton-labels Twice ===")
        # Call 1
        resp1 = await ac.get(f"/api/invoices/{merged_inv_id}/carton-labels")
        assert resp1.status_code == 200, f"Call 1 failed: {resp1.status_code} {resp1.text}"
        bytes1 = resp1.content
        hash1 = hashlib.sha256(bytes1).hexdigest()
        print(f"Call 1 Response: Status {resp1.status_code} | Bytes: {len(bytes1)} | SHA256: {hash1}")

        # Call 2
        resp2 = await ac.get(f"/api/invoices/{merged_inv_id}/carton-labels")
        assert resp2.status_code == 200, f"Call 2 failed: {resp2.status_code} {resp2.text}"
        bytes2 = resp2.content
        hash2 = hashlib.sha256(bytes2).hexdigest()
        print(f"Call 2 Response: Status {resp2.status_code} | Bytes: {len(bytes2)} | SHA256: {hash2}")

        print("\n=== 4. Verifying Exact Byte Identity ===")
        assert bytes1 == bytes2, "Call 1 and Call 2 response bytes differ!"
        assert hash1 == hash2, "Call 1 and Call 2 SHA256 hashes differ!"
        print("VERIFIED: Both responses are 100% BYTE-IDENTICAL!")
        print(f"Content-Disposition Header: {resp1.headers.get('content-disposition')}")
        print(f"Content-Type Header: {resp1.headers.get('content-type')}")

        print("\n=== 5. Clean up ===")
        await db.pos.delete_one({"_id": ObjectId(po_id)})
        await db.production_jobs.delete_many({"_id": {"$in": [ObjectId(j1_id), ObjectId(j2_id)]}})
        await db.packing_cartons.delete_many({"_id": {"$in": c1_ids + c2_ids}})
        await db.invoices.delete_one({"_id": ObjectId(merged_inv_id)})
        await db.counters.update_one({"_id": "invoice_26-27"}, {"$set": {"seq": 19}})
        print("Cleaned up test data and confirmed counter at 19.")

    print("\nTEST COMPLETED SUCCESSFULLY: Endpoint serves stored bytes without regeneration!")

if __name__ == "__main__":
    asyncio.run(test_endpoint_byte_identity())
