"""Concurrency test for inventory movements atomic deduction guard."""
import asyncio
import pytest
from fastapi import HTTPException
import server
from server import (
    db,
    oid,
    create_movement,
    _get_material_balance,
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
async def test_concurrent_inventory_deductions_prevent_negative_stock(fresh_db, monkeypatch):

    """Verify: simulate two concurrent deduction requests for the same material with
    combined quantity exceeding stock — confirm only one succeeds, the other is
    correctly rejected, and stock never goes negative.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    # 1. Setup a test material with 10.0 initial stock
    mat_code = f"TEST_CONC_{asyncio.current_task().get_name()}"
    mat_res = await server.db.materials.insert_one({
        "code": mat_code,
        "name": "Concurrency Test Material",
        "category": "upper",
        "unit": "meters",
        "rate": 100.0,
        "balance": 0.0,
    })
    mat_id = str(mat_res.inserted_id)

    dummy_req = DummyRequest()

    try:
        # Stock In: 10.0 units
        stock_in_payload = InventoryMovement(
            material_id=mat_id,
            type="in",
            quantity=10.0,
            rate=100.0,
        )
        await create_movement(stock_in_payload, dummy_req)

        # Confirm initial balance is 10.0
        bal = await _get_material_balance(mat_id)
        assert bal == 10.0


        # 2. Simulate 2 concurrent deductions of 8.0 units each (combined 16.0 > 10.0)
        out_payload_1 = InventoryMovement(
            material_id=mat_id,
            type="out",
            quantity=8.0,
            notes="Concurrent deduction 1",
        )
        out_payload_2 = InventoryMovement(
            material_id=mat_id,
            type="out",
            quantity=8.0,
            notes="Concurrent deduction 2",
        )

        results = await asyncio.gather(
            create_movement(out_payload_1, dummy_req),
            create_movement(out_payload_2, dummy_req),
            return_exceptions=True,
        )

        # 3. Analyze results
        successes = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        # Exactly ONE must succeed and ONE must fail with HTTPException 400
        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
        assert len(errors) == 1, f"Expected exactly 1 failure, got {len(errors)}"
        assert isinstance(errors[0], HTTPException)
        assert errors[0].status_code == 400
        assert "exceeds current stock balance" in errors[0].detail

        # 4. Confirm stock balance never went negative and is exactly 2.0
        final_bal_from_movements = await _get_material_balance(mat_id)
        assert final_bal_from_movements == 2.0

        mat_doc = await server.db.materials.find_one({"_id": oid(mat_id)})
        assert mat_doc["balance"] == 2.0

    finally:
        # Cleanup test data
        await server.db.materials.delete_one({"_id": oid(mat_id)})
        await server.db.inventory_movements.delete_many({"material_id": mat_id})

