"""Test /inventory/movements pagination and date-range filtering."""
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient
import server
from server import (
    oid,
    list_movements,
)


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
async def test_inventory_movements_pagination_and_date_filtering(fresh_db, monkeypatch):
    """Verify: for a material with 200+ movements, confirm the endpoint can load beyond the
    first page (pagination); confirm date-range filtering correctly narrows results.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    dummy_req = DummyRequest()

    # 1. Create a test material
    mat_res = await server.db.materials.insert_one({
        "code": "MAT-PAGINATION-001",
        "name": "Pagination Test Leather",
        "category": "upper",
        "unit": "sqft",
        "rate": 150.0,
    })
    mat_id = str(mat_res.inserted_id)

    # 2. Seed 250 movements with distinct dates:
    # 100 movements: 2026-08-01 -> 2026-08-10
    # 100 movements: 2026-08-11 -> 2026-08-20
    #  50 movements: 2026-08-21 -> 2026-08-25
    test_movements = []
    for i in range(250):
        if i < 100:
            d_str = f"2026-08-{(i % 10) + 1:02d}"
        elif i < 200:
            d_str = f"2026-08-{(i % 10) + 11:02d}"
        else:
            d_str = f"2026-08-{(i % 5) + 21:02d}"

        test_movements.append({
            "material_id": mat_id,
            "type": "in" if i % 2 == 0 else "out",
            "quantity": 10 + (i % 5),
            "rate": 150.0,
            "date": d_str,
            "created_at": f"{d_str}T10:{i % 60:02d}:00Z",
            "party": f"Supplier/Job {i}",
            "by": "admin@sskfootcare.com",
        })

    await server.db.inventory_movements.insert_many(test_movements)

    try:
        # 3. Test Pagination
        # Page 1 (limit 100)
        p1 = await list_movements(dummy_req, material_id=mat_id, page=1, limit=100)
        assert len(p1) == 100

        # Page 2 (limit 100)
        p2 = await list_movements(dummy_req, material_id=mat_id, page=2, limit=100)
        assert len(p2) == 100

        # Page 3 (limit 100) -> remaining 50
        p3 = await list_movements(dummy_req, material_id=mat_id, page=3, limit=100)
        assert len(p3) == 50

        # Ensure no overlap between pages
        p1_ids = {m["id"] for m in p1}
        p2_ids = {m["id"] for m in p2}
        p3_ids = {m["id"] for m in p3}
        assert len(p1_ids.intersection(p2_ids)) == 0
        assert len(p2_ids.intersection(p3_ids)) == 0
        assert len(p1_ids.union(p2_ids).union(p3_ids)) == 250

        # 4. Test Date-Range Filtering
        # Mid-range: 2026-08-11 to 2026-08-20 (should be exactly 100 movements)
        mid_range = await list_movements(
            dummy_req,
            material_id=mat_id,
            start_date="2026-08-11",
            end_date="2026-08-20",
            limit=200,
        )
        assert len(mid_range) == 100
        assert all("2026-08-11" <= (m.get("date") or m.get("created_at"))[:10] <= "2026-08-20" for m in mid_range)

        # Late-range: start_date="2026-08-21" onwards (should be exactly 50 movements)
        late_range = await list_movements(
            dummy_req,
            material_id=mat_id,
            start_date="2026-08-21",
            limit=200,
        )
        assert len(late_range) == 50
        assert all((m.get("date") or m.get("created_at"))[:10] >= "2026-08-21" for m in late_range)

        # Early-range: end_date="2026-08-10" (should be exactly 100 movements)
        early_range = await list_movements(
            dummy_req,
            material_id=mat_id,
            end_date="2026-08-10",
            limit=200,
        )
        assert len(early_range) == 100

    finally:
        await server.db.materials.delete_one({"_id": oid(mat_id)})
        await server.db.inventory_movements.delete_many({"material_id": mat_id})
