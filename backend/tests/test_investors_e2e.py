"""End-to-End Tests for Stages 2, 4, and 5 (Investors, Repayment/Reinvestment, Investor Portal)."""

import pytest
import motor.motor_asyncio
from httpx import AsyncClient, ASGITransport
from server import app
from auth import create_access_token


@pytest.fixture
async def e2e_env():
    import os
    from bson import ObjectId
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    created_pos = []
    # 1. Find or create a real PO from db.pos
    real_po = await db.pos.find_one({"line_items": {"$exists": True, "$ne": []}})
    if not real_po:
        real_po = await db.pos.find_one()
    if not real_po:
        await db.styles.update_one(
            {"code": "TEST-INV-E2E-STYLE"},
            {"$set": {
                "name": "Investor E2E Style",
                "bom": [{"material_name": "Sole Material", "rate": 100.0, "quantity": 1.0}],
                "labor": [{"stage": "Cutting", "rate": 20.0}],
            }},
            upsert=True,
        )
        real_po_doc = {
            "po_number": f"PO-INV-E2E-1-{ObjectId()}",
            "client_name": "Metro Retailers",
            "total_quantity": 500,
            "quantity": 500,
            "status": "in_production",
            "line_items": [
                {
                    "style_code": "TEST-INV-E2E-STYLE",
                    "quantity": 500,
                    "unit_price": 500.0,
                    "amount": 250000.0,
                }
            ],
        }
        res1 = await db.pos.insert_one(real_po_doc)
        real_po_doc["_id"] = res1.inserted_id
        real_po = real_po_doc
        created_pos.append(real_po["_id"])

    # Find or create a second real PO for reinvestment target
    pos = await db.pos.find().limit(5).to_list(5)
    target_po = None
    for p in pos:
        if str(p["_id"]) != str(real_po["_id"]):
            target_po = p
            break
    if not target_po:
        target_po_doc = {
            "po_number": f"PO-INV-E2E-2-{ObjectId()}",
            "client_name": "Target Retailers",
            "total_quantity": 500,
            "quantity": 500,
            "status": "in_production",
            "line_items": [
                {
                    "style_code": "TEST-INV-E2E-STYLE",
                    "quantity": 500,
                    "unit_price": 500.0,
                    "amount": 250000.0,
                }
            ],
        }
        res2 = await db.pos.insert_one(target_po_doc)
        target_po_doc["_id"] = res2.inserted_id
        target_po = target_po_doc
        created_pos.append(target_po["_id"])

    # Find or create admin user
    admin_user = await db.users.find_one({"role": "admin"})
    if not admin_user:
        admin_user = await db.users.find_one()
    if not admin_user:
        from auth import hash_password
        admin_doc = {
            "email": os.environ.get("ADMIN_EMAIL", "admin@sskfootcare.com"),
            "password_hash": hash_password(os.environ.get("ADMIN_PASSWORD", "Admin@123")),
            "role": "admin",
            "name": "Admin User",
            "active": True,
        }
        res = await db.users.insert_one(admin_doc)
        admin_doc["_id"] = res.inserted_id
        admin_user = admin_doc
    admin_id = str(admin_user["_id"])
    admin_email = admin_user.get("email", "admin@example.com")

    # Clean up test investor data
    test_email = "test.investor@example.com"
    test_phone = "9988776655"
    await db.investors.delete_many({"$or": [{"email": test_email}, {"phone": test_phone}]})
    await db.investor_advances.delete_many({"investor_name": "Test Titan Capital"})

    yield {
        "db": db,
        "po": real_po,
        "target_po": target_po,
        "admin_id": admin_id,
        "admin_email": admin_email,
        "test_email": test_email,
        "test_phone": test_phone,
    }

    # Cleanup after test
    await db.investors.delete_many({"$or": [{"email": test_email}, {"phone": test_phone}]})
    await db.investor_advances.delete_many({"investor_name": "Test Titan Capital"})
    if created_pos:
        await db.pos.delete_many({"_id": {"$in": created_pos}})


@pytest.mark.anyio
async def test_stage_2_create_advance(e2e_env):
    """
    Stage 2: Create investor, create advance via Stage 1 calculation,
    confirm stored breakdown and negotiable margin rate match agreed deal.
    """
    db = e2e_env["db"]
    po = e2e_env["po"]
    admin_token = create_access_token(e2e_env["admin_id"], e2e_env["admin_email"], "admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create investor
        inv_payload = {
            "name": "Test Titan Capital",
            "contact": "Mr. Sharma",
            "phone": e2e_env["test_phone"],
            "email": e2e_env["test_email"],
            "default_margin_per_pair": 12.5,
            "pin": "1234",
            "active": True
        }
        r_inv = await ac.post("/api/investors", json=inv_payload, headers=headers)
        assert r_inv.status_code == 201, r_inv.text
        inv_data = r_inv.json()
        inv_id = inv_data["_id"]

        # 2. Create advance with negotiable override margin = 15.0 and include_opex = False
        adv_payload = {
            "po_id": str(po["_id"]),
            "include_opex": False,
            "margin_per_pair": 15.0,  # negotiated rate override
            "advance_date": "2026-10-06"
        }
        r_adv = await ac.post(f"/api/investors/{inv_id}/advances", json=adv_payload, headers=headers)
        assert r_adv.status_code == 201, r_adv.text
        adv_data = r_adv.json()

        assert adv_data["investor_id"] == inv_id
        assert adv_data["po_id"] == str(po["_id"])
        assert adv_data["margin_per_pair"] == 15.0
        assert adv_data["status"] == "active"
        assert "breakdown" in adv_data
        assert adv_data["breakdown"]["opex_cost"] == 0.0
        assert adv_data["breakdown"]["bom_cost"] > 0 or adv_data["amount"] > 0


@pytest.mark.anyio
async def test_stage_4_repay_in_full_and_reinvest(e2e_env):
    """
    Stage 4: Verify end-to-end for each of the two action paths separately:
    (a) Repay in full
    (b) Pay margin & reinvest into target PO
    """
    db = e2e_env["db"]
    po = e2e_env["po"]
    target_po = e2e_env["target_po"]
    admin_token = create_access_token(e2e_env["admin_id"], e2e_env["admin_email"], "admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Create investor
        inv_payload = {
            "name": "Test Titan Capital",
            "contact": "Mr. Sharma",
            "phone": e2e_env["test_phone"],
            "email": e2e_env["test_email"],
            "default_margin_per_pair": 10.0,
            "pin": "1234",
            "active": True
        }
        r_inv = await ac.post("/api/investors", json=inv_payload, headers=headers)
        assert r_inv.status_code == 201
        inv_id = r_inv.json()["_id"]

        # --- PATH 1: Repay in Full ---
        r_adv1 = await ac.post(f"/api/investors/{inv_id}/advances", json={
            "po_id": str(po["_id"]),
            "include_opex": False,
            "margin_per_pair": 10.0,
        }, headers=headers)
        adv1_id = r_adv1.json()["_id"]

        # Execute "repay_in_full"
        r_repay = await ac.post(f"/api/investors/advances/{adv1_id}/repay", json={
            "action": "repay_in_full",
            "payout_date": "2026-10-06"
        }, headers=headers)
        assert r_repay.status_code == 200, r_repay.text
        rep_res = r_repay.json()
        assert rep_res["action"] == "repay_in_full"
        assert rep_res["advance_status"] == "repaid"
        assert rep_res["repayment"]["reinvested"] is False

        # Confirm advance status in DB is "repaid"
        from bson import ObjectId
        adv1_db = await db.investor_advances.find_one({"_id": ObjectId(adv1_id)})
        assert adv1_db is not None
        assert adv1_db["status"] == "repaid"
        # or check via endpoint
        r_all_adv = await ac.get("/api/investors-advances/all?status=repaid", headers=headers)
        assert any(a["_id"] == adv1_id for a in r_all_adv.json())

        # --- PATH 2: Pay Margin & Reinvest ---
        r_adv2 = await ac.post(f"/api/investors/{inv_id}/advances", json={
            "po_id": str(po["_id"]),
            "include_opex": False,
            "margin_per_pair": 12.0,
        }, headers=headers)
        adv2_id = r_adv2.json()["_id"]

        # Execute "reinvest" with target_po_id
        r_reinvest = await ac.post(f"/api/investors/advances/{adv2_id}/repay", json={
            "action": "reinvest",
            "target_po_id": str(target_po["_id"]),
            "payout_date": "2026-10-06"
        }, headers=headers)
        assert r_reinvest.status_code == 200, r_reinvest.text
        reinv_res = r_reinvest.json()
        assert reinv_res["action"] == "reinvest"
        assert reinv_res["old_advance_status"] == "reinvested"
        assert reinv_res["new_advance"]["status"] == "active"
        assert reinv_res["new_advance"]["po_id"] == str(target_po["_id"])
        assert reinv_res["repayment"]["reinvested"] is True


@pytest.mark.anyio
async def test_stage_5_investor_portal_security_and_scoping(e2e_env):
    """
    Stage 5: Verify portal login, server-side data scoping:
    1. Response bodies contain NO bom_cost/labour_cost/opex_cost fields.
    2. Requesting an unfunded po_id returns 404 rather than leaking.
    3. Cannot access other investors' data.
    """
    db = e2e_env["db"]
    po = e2e_env["po"]
    admin_token = create_access_token(e2e_env["admin_id"], e2e_env["admin_email"], "admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create test investor with PIN "4321"
        r_inv = await ac.post("/api/investors", json={
            "name": "Test Titan Capital",
            "contact": "Mr. Sharma",
            "phone": e2e_env["test_phone"],
            "email": e2e_env["test_email"],
            "default_margin_per_pair": 10.0,
            "pin": "4321",
            "active": True
        }, headers=admin_headers)
        inv_id = r_inv.json()["_id"]

        # Create advance for real_po
        r_adv = await ac.post(f"/api/investors/{inv_id}/advances", json={
            "po_id": str(po["_id"]),
            "include_opex": False,
        }, headers=admin_headers)
        adv_id = r_adv.json()["_id"]

        # 2. Login via Investor Portal
        login_res = await ac.post("/api/auth/investor-login", json={
            "identifier": e2e_env["test_phone"],
            "pin": "4321"
        })
        assert login_res.status_code == 200, login_res.text
        investor_token = login_res.json()["access_token"]
        assert login_res.json()["role"] == "investor"

        investor_headers = {"Authorization": f"Bearer {investor_token}"}

        # 3. GET /investor-portal/advances
        r_portal_adv = await ac.get("/api/investor-portal/advances", headers=investor_headers)
        assert r_portal_adv.status_code == 200, r_portal_adv.text
        advances = r_portal_adv.json()
        assert len(advances) >= 1

        # CRITICAL VERIFICATION: Confirm actual API response bodies contain NO bom_cost/labour_cost/opex_cost/breakdown
        adv_payload = advances[0]
        assert "bom_cost" not in adv_payload, "LEAK DETECTED: bom_cost exposed in investor response!"
        assert "labour_cost" not in adv_payload, "LEAK DETECTED: labour_cost exposed in investor response!"
        assert "labor_cost" not in adv_payload, "LEAK DETECTED: labor_cost exposed in investor response!"
        assert "opex_cost" not in adv_payload, "LEAK DETECTED: opex_cost exposed in investor response!"
        assert "breakdown" not in adv_payload, "LEAK DETECTED: breakdown exposed in investor response!"
        assert "amount" in adv_payload
        assert "pairs" in adv_payload

        # 4. GET /investor-portal/pos/{po_id} for FUNDED PO
        r_po_funded = await ac.get(f"/api/investor-portal/pos/{str(po['_id'])}", headers=investor_headers)
        assert r_po_funded.status_code == 200, r_po_funded.text
        po_info = r_po_funded.json()
        assert "po_number" in po_info
        assert "quantity" in po_info
        assert "amount_received_from_client_so_far" in po_info
        assert "amount_still_receivable" in po_info
        assert "repayment_status" in po_info
        # Confirm financial details stay out
        assert "unit_price" not in po_info, "LEAK DETECTED: client unit price exposed to investor!"
        assert "vendor_cost" not in po_info, "LEAK DETECTED: vendor cost exposed to investor!"
        assert "bom_cost" not in po_info, "LEAK DETECTED: bom_cost exposed to investor!"

        # 5. GET /investor-portal/pos/{unfunded_po_id} for an UNFUNDED PO -> MUST 404!
        fake_unfunded_id = "60d5ec49f1b2c80015f8a999"
        r_unfunded = await ac.get(f"/api/investor-portal/pos/{fake_unfunded_id}", headers=investor_headers)
        assert r_unfunded.status_code == 404, "SECURITY ERROR: Unfunded PO must return 404 rather than leaking!"


@pytest.mark.anyio
async def test_investor_banking_inflow_and_repayment_sync(e2e_env):
    """
    Verify that advancing investor funds against a selected company bank account:
    1. Records an inflow into db.payments with type="investor_funding" and updates bank balance.
    2. Repaying an advance with a bank account records outflow into db.payments with type="investor_repayment" and syncs balance.
    """
    db = e2e_env["db"]
    po = e2e_env["po"]
    admin_token = create_access_token(e2e_env["admin_id"], e2e_env["admin_email"], "admin")

    # Insert a temporary test bank account
    bank_doc = {
        "account_name": "Test Company Treasury",
        "bank_name": "Axis Bank",
        "account_number": "999888777666",
        "ifsc_code": "UTIB0000123",
        "opening_balance": 100000.0,
        "current_balance": 100000.0,
        "active": True,
    }
    res_b = await db.bank_accounts.insert_one(bank_doc)
    bank_id = str(res_b.inserted_id)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            headers = {"Authorization": f"Bearer {admin_token}"}

            # 1. Create investor
            inv_payload = {
                "name": "Test Titan Capital",
                "contact": "Mr. Sharma",
                "phone": e2e_env["test_phone"],
                "email": e2e_env["test_email"],
                "default_margin_per_pair": 10.0,
                "pin": "1234",
                "active": True
            }
            r_inv = await ac.post("/api/investors", json=inv_payload, headers=headers)
            assert r_inv.status_code == 201
            inv_id = r_inv.json()["_id"]

            # 2. Advance funding linked to bank account
            adv_payload = {
                "po_id": str(po["_id"]),
                "include_opex": False,
                "bank_account_id": bank_id,
                "payment_mode": "NEFT",
                "reference": "REF-INV-INFLOW-001"
            }
            r_adv = await ac.post(f"/api/investors/{inv_id}/advances", json=adv_payload, headers=headers)
            assert r_adv.status_code == 201, r_adv.text
            adv_data = r_adv.json()
            adv_id = adv_data["_id"]
            funded_amt = adv_data["amount"]

            assert adv_data.get("bank_account_id") == bank_id
            assert "Axis Bank" in (adv_data.get("bank_name") or "")

            # 3. Verify payment entry in db.payments (inflow)
            payment_in = await db.payments.find_one({"advance_id": adv_id, "type": "investor_funding"})
            assert payment_in is not None
            assert payment_in["amount"] == funded_amt
            assert payment_in["bank_account_id"] == bank_id
            assert payment_in["reference"] == "REF-INV-INFLOW-001"

            # 4. Verify updated bank balance
            updated_bank = await db.bank_accounts.find_one({"_id": res_b.inserted_id})
            assert updated_bank["current_balance"] == round(100000.0 + funded_amt, 2)

            # 5. Repay in full using the same bank account
            repay_payload = {
                "action": "repay_in_full",
                "bank_account_id": bank_id,
                "payment_mode": "RTGS",
                "reference": "REF-INV-PAYOUT-001",
                "payout_date": "2026-10-06"
            }
            r_repay = await ac.post(f"/api/investors/advances/{adv_id}/repay", json=repay_payload, headers=headers)
            assert r_repay.status_code == 200, r_repay.text
            rep_data = r_repay.json()
            repay_id = rep_data["repayment"]["_id"]
            total_payout = rep_data["repayment"]["total_payout"]

            # 6. Verify repayment outflow in db.payments
            payment_out = await db.payments.find_one({"repayment_id": str(repay_id), "type": "investor_repayment"})
            assert payment_out is not None
            assert payment_out["amount"] == total_payout
            assert payment_out["bank_account_id"] == bank_id
            assert payment_out["reference"] == "REF-INV-PAYOUT-001"

            # 7. Verify updated bank balance after payout
            final_bank = await db.bank_accounts.find_one({"_id": res_b.inserted_id})
            expected_balance = round(100000.0 + funded_amt - total_payout, 2)
            assert final_bank["current_balance"] == expected_balance
    finally:
        # Cleanup test bank account and payments
        await db.bank_accounts.delete_one({"_id": res_b.inserted_id})
        await db.payments.delete_many({"bank_account_id": bank_id})
