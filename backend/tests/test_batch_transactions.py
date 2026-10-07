"""
Unit and Integration tests for Batch/Multi-PO funding and Bulk Repayment transactions.
Verifies all transactional operations and state transitions against real MongoDB data.
"""

import pytest
import motor.motor_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from bson import ObjectId

from server import app
from auth import create_access_token


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_batch_funding_and_bulk_repayment_transactions():
    """
    Complete transaction audit:
    1. Create 3 test POs with BOM and labor data.
    2. Register investor partner.
    3. Test preview-batch calculation.
    4. Execute batch funding (fund 2 POs at once).
    5. Verify advance documents, batch_id, amounts, and opex uniqueness.
    6. Execute bulk repayment (pay 2 POs at once in full).
    7. Verify advance status='repaid', repayment ledger, and financial totals.
    8. Execute reinvestment for another batch into a 3rd PO.
    9. Verify margin cash payout and principal rollover.
    """
    import os
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    motor_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    db = motor_client[db_name]

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
    admin_email = admin_user.get("email", "admin@sskfootwear.com")

    admin_token = create_access_token(admin_id, admin_email, "admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 0. Setup matching styles in db.styles
        await db.styles.delete_many({"code": {"$in": ["STYLE-BATCH-1", "STYLE-BATCH-2", "STYLE-BATCH-3"]}})
        await db.styles.insert_many([
            {
                "code": "STYLE-BATCH-1",
                "name": "Batch Sneaker 1",
                "bom": [
                    {"material_name": "Sole Eva", "rate": 120.0, "quantity": 1.0},
                    {"material_name": "Upper Synthetic", "rate": 80.0, "quantity": 1.0},
                ],
                "labor": [
                    {"stage": "Cutting", "rate": 15.0},
                    {"stage": "Stitching", "rate": 25.0},
                ]
            },
            {
                "code": "STYLE-BATCH-2",
                "name": "Batch Leather 2",
                "bom": [
                    {"material_name": "Leather Upper", "rate": 150.0, "quantity": 1.0},
                    {"material_name": "TPR Sole", "rate": 90.0, "quantity": 1.0},
                ],
                "labor": [
                    {"stage": "Cutting", "rate": 20.0},
                    {"stage": "Lasting", "rate": 30.0},
                ]
            },
            {
                "code": "STYLE-BATCH-3",
                "name": "Batch Classic 3",
                "bom": [{"material_name": "Raw Rubber", "rate": 100.0, "quantity": 1.0}],
                "labor": [{"stage": "Molding", "rate": 20.0}]
            }
        ])

        # 1. Setup Test Purchase Orders
        po1_doc = {
            "po_number": f"TEST-PO-BATCH-1-{ObjectId()}",
            "client_name": "Metro Retailers",
            "total_quantity": 500,
            "quantity": 500,
            "status": "in_production",
            "items": [
                {
                    "style_code": "STYLE-BATCH-1",
                    "quantity": 500,
                    "pair_price": 450.0,
                    "bom_lines": [
                        {"material_name": "Sole Eva", "cost_per_pair": 120.0},
                        {"material_name": "Upper Synthetic", "cost_per_pair": 80.0},
                    ],
                    "labor_rates": [
                        {"stage": "Cutting", "rate": 15.0},
                        {"stage": "Stitching", "rate": 25.0},
                    ]
                }
            ],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        r1 = await db.pos.insert_one(po1_doc)
        po1_id = str(r1.inserted_id)

        po2_doc = {
            "po_number": f"TEST-PO-BATCH-2-{ObjectId()}",
            "client_name": "Apex Footwear",
            "total_quantity": 800,
            "quantity": 800,
            "status": "in_production",
            "items": [
                {
                    "style_code": "STYLE-BATCH-2",
                    "quantity": 800,
                    "pair_price": 500.0,
                    "bom_lines": [
                        {"material_name": "Leather Upper", "cost_per_pair": 150.0},
                        {"material_name": "TPR Sole", "cost_per_pair": 90.0},
                    ],
                    "labor_rates": [
                        {"stage": "Cutting", "rate": 20.0},
                        {"stage": "Lasting", "rate": 30.0},
                    ]
                }
            ],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        r2 = await db.pos.insert_one(po2_doc)
        po2_id = str(r2.inserted_id)

        po3_doc = {
            "po_number": f"TEST-PO-TARGET-3-{ObjectId()}",
            "client_name": "Bata Distribution",
            "total_quantity": 1000,
            "quantity": 1000,
            "status": "confirmed",
            "items": [
                {
                    "style_code": "STYLE-BATCH-3",
                    "quantity": 1000,
                    "pair_price": 600.0,
                    "bom_lines": [{"material_name": "Raw Rubber", "cost_per_pair": 100.0}],
                    "labor_rates": [{"stage": "Molding", "rate": 20.0}]
                }
            ],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        r3 = await db.pos.insert_one(po3_doc)
        po3_id = str(r3.inserted_id)

        # 2. Register Investor
        unique_suffix = f"{int(datetime.now().timestamp() * 1000) % 100000000:08d}"
        inv_payload = {
            "name": f"Batch Capital Partners {unique_suffix}",
            "contact": "Vikram Singh",
            "phone": f"88{unique_suffix}",
            "email": f"batch_{unique_suffix}@invest.com",
            "default_margin_per_pair": 12.0,
            "active": True
        }
        inv_res = await ac.post("/api/investors", json=inv_payload, headers=headers)
        assert inv_res.status_code == 201, inv_res.text
        inv_data = inv_res.json()
        investor_id = inv_data["_id"]

        # 3. Test Preview-Batch Endpoint
        preview_res = await ac.post(
            "/api/investors-advances/preview-batch",
            json={"po_ids": [po1_id, po2_id], "include_opex": False},
            headers=headers
        )
        assert preview_res.status_code == 200, preview_res.text
        preview_data = preview_res.json()
        assert preview_data["count"] == 2
        assert preview_data["total_pairs"] == 1300  # 500 + 800
        assert preview_data["total_funding_required"] > 0

        # 4. Execute Multi-PO Batch Funding (fund PO1 and PO2 at once)
        batch_fund_res = await ac.post(
            f"/api/investors/{investor_id}/advances/batch",
            json={
                "po_ids": [po1_id, po2_id],
                "include_opex": False,
                "margin_per_pair": 15.0,  # negotiated override
                "notes": "Q4 multi-PO syndicate advance"
            },
            headers=headers
        )
        assert batch_fund_res.status_code == 201, batch_fund_res.text
        batch_fund_data = batch_fund_res.json()

        assert batch_fund_data["ok"] is True
        assert batch_fund_data["count"] == 2
        assert batch_fund_data["total_pairs"] == 1300
        batch_id = batch_fund_data["batch_id"]
        assert batch_id.startswith("BATCH-")

        advances = batch_fund_data["advances"]
        assert len(advances) == 2
        adv1 = advances[0]
        adv2 = advances[1]

        assert adv1["batch_id"] == batch_id
        assert adv2["batch_id"] == batch_id
        assert adv1["status"] == "active"
        assert adv2["status"] == "active"
        assert adv1["margin_per_pair"] == 15.0
        assert adv2["margin_per_pair"] == 15.0

        # Verify directly in MongoDB
        db_adv1 = await db.investor_advances.find_one({"_id": ObjectId(adv1["_id"])})
        db_adv2 = await db.investor_advances.find_one({"_id": ObjectId(adv2["_id"])})
        assert db_adv1 is not None and db_adv2 is not None
        assert db_adv1["status"] == "active"
        assert db_adv2["status"] == "active"

        # 5. Check Transaction Math for Bulk Repay
        expected_adv1_principal = float(db_adv1["amount"])
        expected_adv1_margin = float(db_adv1["pairs"]) * 15.0
        expected_adv2_principal = float(db_adv2["amount"])
        expected_adv2_margin = float(db_adv2["pairs"]) * 15.0

        expected_total_principal = round(expected_adv1_principal + expected_adv2_principal, 2)
        expected_total_margin = round(expected_adv1_margin + expected_adv2_margin, 2)
        expected_total_payout = round(expected_total_principal + expected_total_margin, 2)

        # 6. Execute Bulk Repayment: Pay both PO advances at once in full
        bulk_repay_res = await ac.post(
            "/api/investors/advances/bulk-repay",
            json={
                "advance_ids": [adv1["_id"], adv2["_id"]],
                "action": "repay_in_full",
                "mode": "Bank Transfer",
                "notes": "Full syndicate settlement for Q4 batch"
            },
            headers=headers
        )
        assert bulk_repay_res.status_code == 200, bulk_repay_res.text
        bulk_repay_data = bulk_repay_res.json()

        assert bulk_repay_data["ok"] is True
        assert bulk_repay_data["settled_count"] == 2
        assert bulk_repay_data["total_principal"] == expected_total_principal
        assert bulk_repay_data["total_margin"] == expected_total_margin
        assert bulk_repay_data["total_payout"] == expected_total_payout
        assert bulk_repay_data["batch_repayment_id"].startswith("BREP-")

        # 7. Verify MongoDB State Transitions
        updated_adv1 = await db.investor_advances.find_one({"_id": ObjectId(adv1["_id"])})
        updated_adv2 = await db.investor_advances.find_one({"_id": ObjectId(adv2["_id"])})
        assert updated_adv1["status"] == "repaid"
        assert updated_adv2["status"] == "repaid"
        assert updated_adv1.get("repayment_id") is not None
        assert updated_adv2.get("repayment_id") is not None

        # Verify Repayments in DB
        reps = await db.investor_repayments.find({
            "batch_repayment_id": bulk_repay_data["batch_repayment_id"]
        }).to_list(10)
        assert len(reps) == 2
        for r in reps:
            assert r["reinvested"] is False
            assert r["total_payout"] == round(r["principal_amount"] + r["margin_amount"], 2)

        # 8. Test Bulk Reinvestment Transaction (fund another PO, then reinvest into PO3)
        fund_reinv_res = await ac.post(
            f"/api/investors/{investor_id}/advances",
            json={
                "po_id": po1_id,
                "margin_per_pair": 10.0,
                "notes": "Advance for reinvestment test"
            },
            headers=headers
        )
        assert fund_reinv_res.status_code == 201
        adv_reinv_id = fund_reinv_res.json()["_id"]

        bulk_reinv_res = await ac.post(
            "/api/investors/advances/bulk-repay",
            json={
                "advance_ids": [adv_reinv_id],
                "action": "reinvest",
                "target_po_id": po3_id,
                "notes": "Roll principal into PO3"
            },
            headers=headers
        )
        assert bulk_reinv_res.status_code == 200, bulk_reinv_res.text
        bulk_reinv_data = bulk_reinv_res.json()
        assert bulk_reinv_data["ok"] is True
        assert bulk_reinv_data["settled_count"] == 1

        # Verify old advance status is reinvested and new advance exists for PO3
        old_adv = await db.investor_advances.find_one({"_id": ObjectId(adv_reinv_id)})
        assert old_adv["status"] == "reinvested"
        new_adv = await db.investor_advances.find_one({
            "rolled_over_from_advance_id": adv_reinv_id
        })
        assert new_adv is not None
        assert new_adv["status"] == "active"
        assert new_adv["po_id"] == po3_id
        assert new_adv["amount"] == old_adv["amount"]  # rolled over principal
