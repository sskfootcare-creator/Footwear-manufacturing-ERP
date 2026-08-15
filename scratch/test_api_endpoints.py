import asyncio
import os
import sys
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
async def test_admin_resync():
    server.get_current_user = await get_current_user_factory(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Login
        login_resp = await ac.post("/api/auth/login", json={
            "email": "sskfootcare@gmail.com",
            "password": "Chandu@220494"
        })
        print(f"Login status: {login_resp.status_code}")
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

        # Call resync endpoint
        resync_resp = await ac.post("/api/admin/resync-invoice-sequence")
        print(f"Resync status: {resync_resp.status_code}")
        print(f"Resync response: {resync_resp.json()}")
        assert resync_resp.status_code == 200
        assert resync_resp.json()["ok"] is True
        assert resync_resp.json()["max_existing_seq"] == 19
        assert resync_resp.json()["synced_counter_seq"] == 19
        assert resync_resp.json()["next_invoice_will_be"] == "SSK26-27-020"

        # List invoices
        inv_resp = await ac.get("/api/invoices")
        print(f"List invoices status: {inv_resp.status_code}, count: {len(inv_resp.json())}")
        for inv in inv_resp.json():
            print(f"  {inv.get('invoice_no')} | {inv.get('client_name')} | {inv.get('invoice_date')} | Total: {inv.get('grand_total')}")

    print("\nAPI ENDPOINTS VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_admin_resync())
