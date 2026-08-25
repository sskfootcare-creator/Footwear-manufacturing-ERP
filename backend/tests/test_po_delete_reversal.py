"""Test PO deletion compensating inventory reversal and audit trail."""
import pytest
import server
from server import (
    db,
    oid,
    create_movement,
    delete_po,
    _get_material_balance,
    _compute_material_inventory_summary,
)
from models.materials import InventoryMovement


import os
from motor.motor_asyncio import AsyncIOMotorClient

class DummyRequest:
    """Mock Request for unit testing endpoints with auth state."""
    state = type("State", (), {"user": {"email": "admin@sskfootcare.com", "role": "admin"}})()
    headers = {}
    cookies = {}


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = c[os.environ["DB_NAME"]]
    monkeypatch.setattr(server, "client", c)
    monkeypatch.setattr(server, "db", d)
    yield d
    c.close()


@pytest.mark.anyio
async def test_delete_po_reverses_inventory_movements(fresh_db, monkeypatch):

    """Verify: create a PO, produce jobs that consume material stock, delete the PO,
    confirm stock levels are correctly restored to what they were before production
    started (not just deleted without reversal).
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    dummy_req = DummyRequest()

    # 1. Setup a test material with 100 units of initial stock @ rate 50
    mat_res = await server.db.materials.insert_one({
        "code": "TEST_PO_REV_MAT",
        "name": "PO Reversal Test Material",
        "category": "upper",
        "unit": "sqft",
        "rate": 50.0,
        "balance": 0.0,
    })
    mat_id = str(mat_res.inserted_id)

    # 2. Setup a test PO
    po_num = "TEST_PO_REV_001"
    po_res = await server.db.pos.insert_one({
        "po_number": po_num,
        "client_name": "Test Client",
        "items": [{"style_code": "ST_01", "quantity": 100}],
        "status": "in_production",
    })
    po_id = str(po_res.inserted_id)

    # 3. Setup a production job under this PO
    job_res = await server.db.production_jobs.insert_one({
        "po_id": po_id,
        "po_number": po_num,
        "style_code": "ST_01",
        "color": "Black",
        "size": "8",
        "quantity": 100,
        "stage": "Cutting",
    })
    job_id = str(job_res.inserted_id)

    try:
        # Stock In: 100.0 units
        await create_movement(
            InventoryMovement(
                material_id=mat_id,
                type="in",
                quantity=100.0,
                rate=50.0,
                notes="Initial Stock",
            ),
            dummy_req,
        )

        initial_bal = await _get_material_balance(mat_id)
        assert initial_bal == 100.0

        # Simulate production consumption of 35.0 units for this job
        await create_movement(
            InventoryMovement(
                material_id=mat_id,
                type="out",
                quantity=35.0,
                job_id=job_id,
                notes=f"Consumed for job {job_id}",
            ),
            dummy_req,
        )

        consumed_bal = await _get_material_balance(mat_id)
        assert consumed_bal == 65.0

        # 4. Delete the PO
        del_res = await delete_po(po_id, dummy_req)
        assert del_res["ok"] is True
        assert del_res["reversed_movements_count"] >= 1

        # 5. Verify stock level is restored back to 100.0
        restored_bal = await _get_material_balance(mat_id)
        assert restored_bal == 100.0, f"Expected 100.0 restored balance, got {restored_bal}"

        mat_doc = await server.db.materials.find_one({"_id": oid(mat_id)})
        assert mat_doc["balance"] == 100.0

        # 6. Verify reversal movement was created
        reversal_movs = await server.db.inventory_movements.find({
            "material_id": mat_id,
            "is_reversal": True,
        }).to_list(10)
        assert len(reversal_movs) == 1
        assert reversal_movs[0]["type"] == "in"
        assert reversal_movs[0]["quantity"] == 35.0
        assert po_num in reversal_movs[0]["notes"]

        # 7. Verify PO and production jobs were deleted
        assert await server.db.pos.find_one({"_id": oid(po_id)}) is None
        assert await server.db.production_jobs.find_one({"_id": oid(job_id)}) is None

        # 8. Verify activity log
        log_entry = await server.db.audit_logs.find_one({
            "category": "po",
            "action": "DELETE",
            "details": {"$regex": po_num},
        })
        assert log_entry is not None
        assert "compensating inventory reversal" in log_entry["details"]

    finally:
        # Cleanup
        await server.db.materials.delete_one({"_id": oid(mat_id)})
        await server.db.pos.delete_one({"_id": oid(po_id)})
        await server.db.production_jobs.delete_many({"po_id": po_id})
        await server.db.inventory_movements.delete_many({"material_id": mat_id})

