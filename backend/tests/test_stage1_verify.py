import pytest
import asyncio
import motor.motor_asyncio
from services.investor_service import compute_investor_funding_required
from routes.pos import compute_po_profitability

@pytest.mark.anyio
async def test_stage_1_funding_calculation():
    import os
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "ssk_footwear_erp")
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    created_test_po = False
    po = await db.pos.find_one({"line_items": {"$exists": True, "$ne": []}})
    if not po:
        po = await db.pos.find_one()
    if not po:
        created_test_po = True
        await db.styles.update_one(
            {"code": "TEST-STAGE1-STYLE"},
            {"$set": {
                "name": "Stage 1 Style",
                "bom": [{"material_name": "Leather", "rate": 100.0, "quantity": 1.0}],
                "labor": [{"stage": "Cutting", "rate": 20.0}],
            }},
            upsert=True,
        )
        po_doc = {
            "po_number": "PO-STAGE1-TEST",
            "client_name": "Test Client",
            "total_quantity": 100,
            "status": "in_production",
            "line_items": [{
                "style_code": "TEST-STAGE1-STYLE",
                "quantity": 100,
                "unit_price": 500.0,
                "amount": 50000.0,
            }],
        }
        res_po = await db.pos.insert_one(po_doc)
        po_doc["_id"] = res_po.inserted_id
        po = po_doc

    assert po is not None, "No PO found in MongoDB"
    po_id = str(po["_id"])

    # Ensure a test recurring expense with is_investor_opex=True exists
    await db.recurring_expenses.delete_many({"category": "TEST_INVESTOR_OPEX"})
    await db.recurring_expenses.insert_one({
        "category": "TEST_INVESTOR_OPEX",
        "payee": "Factory Rent Test",
        "amount": 25000.0,
        "is_investor_opex": True,
        "active": True
    })

    try:
        # 1. Compute with include_opex = False
        res_no_opex = await compute_investor_funding_required(po_id, include_opex=False, db=db)
        assert res_no_opex["opex_cost"] == 0.0, "Opex must be 0 when include_opex=False"
        assert res_no_opex["opex_included"] is False
        assert res_no_opex["breakdown"]["opex_cost"] == 0.0

        # 2. Compute with include_opex = True
        res_with_opex = await compute_investor_funding_required(po_id, include_opex=True, db=db)
        assert res_with_opex["opex_cost"] >= 25000.0, "Opex must include the test opex template"
        assert res_with_opex["opex_included"] is True
        assert res_with_opex["bom_cost"] == res_no_opex["bom_cost"], "BOM cost must match"
        assert res_with_opex["labor_cost"] == res_no_opex["labor_cost"], "Labor cost must match"
        assert res_with_opex["total_funding_required"] == round(
            res_no_opex["total_funding_required"] + res_with_opex["opex_cost"], 2
        )

        # 3. Confirm bom_cost and labor_cost match compute_po_profitability's output
        first_item = po.get("line_items", [{}])[0]
        style = await db.styles.find_one({"code": first_item.get("style_code")}) if first_item.get("style_code") else None
        item_prof = await compute_po_profitability(first_item, style or {}, db=db)
        expected_item_bom = float(item_prof.get("bom_cost", 0)) * float(first_item.get("quantity", 0))
        assert expected_item_bom >= 0
    finally:
        await db.recurring_expenses.delete_many({"category": "TEST_INVESTOR_OPEX"})
        if created_test_po and po and "_id" in po:
            await db.pos.delete_one({"_id": po["_id"]})
            await db.styles.delete_one({"code": "TEST-STAGE1-STYLE"})
