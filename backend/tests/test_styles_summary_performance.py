"""Test GET /styles/summary vs GET /styles performance, payload size reduction, and edit drawer full BOM loading."""
import pytest
import os
import json
import time
from motor.motor_asyncio import AsyncIOMotorClient
import server
from server import (
    oid,
    list_styles,
    list_styles_summary,
    get_style,
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
async def test_styles_summary_payload_reduction_and_full_edit(fresh_db, monkeypatch):
    """Verify: measure response size/time for /styles/summary vs the old full /styles call
    against a dataset with 100+ styles — confirm meaningful reduction. Confirm the
    edit drawer still loads full BOM correctly when opened via get_style.
    """
    async def mock_get_current_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin", "name": "Admin"}

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)

    dummy_req = DummyRequest()

    # 1. Seed 105 test styles, each with realistic BOM (15 line items) and Labor
    test_styles = []
    prefix = "TEST_PERF_STYLE_"
    for i in range(105):
        bom = [
            {
                "material_id": f"mat_id_{j}",
                "material_code": f"MAT_CODE_{j}",
                "material_name": f"Material Name Description Long {j}",
                "unit": "meters" if j % 2 == 0 else "sqft",
                "quantity": 1.5 + (j * 0.1),
                "yield_per_unit": 2.0,
                "waste_pct": 5.0,
                "rate": 120.0 + (j * 10),
                "section": "Upper Top" if j < 5 else ("Lining" if j < 10 else "Sole"),
                "color": "Black",
                "notes": f"Special requirement notes for component {j} with yield specifications",
            }
            for j in range(15)
        ]
        labor = [
            {"name": "Cutting", "rate": 25.0},
            {"name": "Fitting", "rate": 35.0},
            {"name": "Pasting", "rate": 30.0},
            {"name": "Finishing", "rate": 20.0},
            {"name": "Packing", "rate": 10.0},
        ]
        test_styles.append({
            "code": f"{prefix}{i:03d}",
            "name": f"Performance Test Footwear Style #{i}",
            "category": "Sneakers" if i % 2 == 0 else "Formal",
            "status": "active",
            "image_url": f"https://example.com/images/style_{i}.jpg",
            "image_thumbnail_url": f"https://example.com/thumbnails/style_{i}_thumb.jpg",
            "description": f"Detailed description for performance benchmark style {i} with materials and construction.",
            "base_size": "8",
            "overhead_pct": 10.0,
            "packing_cost": 15.0,
            "margin_pct": 20.0,
            "gst_pct": 5.0,
            "bom": bom,
            "labor": labor,
            "default_pairs_per_carton": {"6": 2, "7": 4, "8": 4, "9": 2},
            "created_at": "2026-08-25T11:00:00Z",
            "active": True,
        })

    insert_res = await server.db.styles.insert_many(test_styles)
    seeded_ids = insert_res.inserted_ids

    try:
        # 2. Fetch full /styles (old endpoint)
        t0 = time.perf_counter()
        full_results = await list_styles(dummy_req, search=prefix)
        t_full = time.perf_counter() - t0

        full_json = json.dumps(full_results)
        full_size_bytes = len(full_json.encode("utf-8"))

        assert len(full_results) == 105
        # Verify full BOM is present on full results
        assert "bom" in full_results[0]
        assert len(full_results[0]["bom"]) == 15
        assert "labor" in full_results[0]
        assert len(full_results[0]["labor"]) == 5

        # 3. Fetch lightweight /styles/summary
        t0 = time.perf_counter()
        summary_results = await list_styles_summary(dummy_req, search=prefix)
        t_summary = time.perf_counter() - t0

        summary_json = json.dumps(summary_results)
        summary_size_bytes = len(summary_json.encode("utf-8"))

        assert len(summary_results) == 105
        first_summary = summary_results[0]

        # Verify summary contains essential card fields ONLY (NO full BOM / labor array)
        assert "code" in first_summary
        assert "name" in first_summary
        assert "category" in first_summary
        assert "status" in first_summary
        assert "image_thumbnail_url" in first_summary
        assert "cost_summary" in first_summary
        assert "total_cost" in first_summary["cost_summary"]
        assert "selling_price" in first_summary["cost_summary"]

        assert "bom" not in first_summary, "BOM should be excluded from /styles/summary"
        assert "labor" not in first_summary, "Labor should be excluded from /styles/summary"

        # 4. Assert meaningful payload reduction (>60% reduction)
        reduction_pct = (1.0 - (summary_size_bytes / full_size_bytes)) * 100.0
        assert reduction_pct > 60.0, f"Expected >60% payload size reduction, got {reduction_pct:.2f}% (Full: {full_size_bytes}B, Summary: {summary_size_bytes}B)"

        # 5. Verify edit drawer loads full BOM correctly via get_style(id)
        test_style_id = str(seeded_ids[0])
        full_style_detail = await get_style(test_style_id, dummy_req)

        assert full_style_detail["id"] == test_style_id
        assert full_style_detail["code"] == f"{prefix}000"
        assert "bom" in full_style_detail
        assert len(full_style_detail["bom"]) == 15
        assert "labor" in full_style_detail
        assert len(full_style_detail["labor"]) == 5
        assert full_style_detail["costing"]["total_cost"] > 0

    finally:
        await server.db.styles.delete_many({"code": {"$regex": f"^{prefix}"}})
