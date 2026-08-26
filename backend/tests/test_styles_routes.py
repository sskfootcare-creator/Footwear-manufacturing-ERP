import pytest
from unittest.mock import AsyncMock, MagicMock
from bson import ObjectId
from collections import defaultdict
from fastapi import HTTPException
from starlette.requests import Request

import server
from routes.styles import (
    styles_router,
    suggest_gst_pct,
    get_gst_config,
    compute_style_costing,
    compute_style_costing_from_jobs,
    compute_style_costing_async,
    compute_po_profitability,
    _default_lifecycle,
    _validate_online_status_transition,
    _next_style_code,
    build_catalogue_sku,
    resolve_color_code,
    list_styles_summary,
    list_styles,
    get_style,
    create_style,
    update_style,
    delete_style,
    get_style_lifecycle,
    add_style_to_online_pipeline,
    remove_style_from_online_pipeline,
    list_styles_not_in_pipeline,
    list_online_styles,
    get_style_catalogue_codes,
    list_color_master,
    create_color,
    update_color,
)
from models.styles import StyleIn, StyleLifecycleUpsert, OnlineStatusPatchIn, ColorMasterIn, ColorMasterUpdate


class MockCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, limit=1000):
        return self.items[:limit]

    def __aiter__(self):
        self._iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class DummyRequest:
    def __init__(self, user=None):
        self.state = type("State", (), {"user": user or {"email": "admin@sskfootcare.com", "role": "admin"}})()
        self.headers = {}
        self.cookies = {}


@pytest.fixture
def mock_db():
    db = MagicMock()
    # In-memory storage
    db._styles = []
    db._lifecycle = []
    db._color_master = []
    db._production_jobs = []
    db._sku_map = []
    db._fg_inventory = []
    db._counters = {"style_code": {"_id": "style_code", "seq": 100}}

    # styles collection
    def find_styles(q=None, *args, **kwargs):
        res = list(db._styles)
        if q and "$or" in q:
            pass  # return all for mock
        return MockCursor(res)

    async def find_one_style(q, *args, **kwargs):
        for s in db._styles:
            if "_id" in q and str(s.get("_id")) == str(q["_id"]):
                return dict(s)
            if "code" in q and s.get("code") == q["code"]:
                return dict(s)
        return None

    async def insert_one_style(doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        db._styles.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def update_one_style(q, u):
        for s in db._styles:
            if "_id" in q and str(s.get("_id")) == str(q["_id"]):
                if "$set" in u:
                    s.update(u["$set"])
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    db.styles.find = MagicMock(side_effect=find_styles)
    db.styles.find_one = AsyncMock(side_effect=find_one_style)
    db.styles.insert_one = AsyncMock(side_effect=insert_one_style)
    db.styles.update_one = AsyncMock(side_effect=update_one_style)

    # style_lifecycle collection
    def find_lifecycle(q=None, *args, **kwargs):
        res = list(db._lifecycle)
        return MockCursor(res)

    async def find_one_lifecycle(q, *args, **kwargs):
        for l in db._lifecycle:
            if "style_id" in q and str(l.get("style_id")) == str(q["style_id"]):
                return dict(l)
        return None

    async def insert_one_lifecycle(doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        db._lifecycle.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    async def delete_one_lifecycle(q):
        for i, l in enumerate(list(db._lifecycle)):
            if "style_id" in q and str(l.get("style_id")) == str(q["style_id"]):
                db._lifecycle.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    db.style_lifecycle.find = MagicMock(side_effect=find_lifecycle)
    db.style_lifecycle.find_one = AsyncMock(side_effect=find_one_lifecycle)
    db.style_lifecycle.insert_one = AsyncMock(side_effect=insert_one_lifecycle)
    db.style_lifecycle.delete_one = AsyncMock(side_effect=delete_one_lifecycle)
    db.style_lifecycle.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    db.style_lifecycle.count_documents = AsyncMock(return_value=0)

    # color_master collection
    def find_color(q=None, *args, **kwargs):
        return MockCursor(list(db._color_master))

    async def find_one_color(q, *args, **kwargs):
        for c in db._color_master:
            if "color_code" in q and c.get("color_code") == q["color_code"]:
                return dict(c)
            if "color_name_lc" in q and c.get("color_name_lc") == q["color_name_lc"]:
                return dict(c)
            if "_id" in q and str(c.get("_id")) == str(q["_id"]):
                return dict(c)
        return None

    async def insert_one_color(doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        db._color_master.append(d)
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

    db.color_master.find = MagicMock(side_effect=find_color)
    db.color_master.find_one = AsyncMock(side_effect=find_one_color)
    db.color_master.insert_one = AsyncMock(side_effect=insert_one_color)
    db.color_master.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    # production_jobs collection
    def find_jobs(q=None, *args, **kwargs):
        return MockCursor(list(db._production_jobs))

    db.production_jobs.find = MagicMock(side_effect=find_jobs)
    db.production_jobs.find_one = AsyncMock(return_value=None)

    # counters collection
    async def find_one_and_update_counters(q, u, **kwargs):
        doc = db._counters.setdefault(q["_id"], {"_id": q["_id"], "seq": 0})
        if "$inc" in u and "seq" in u["$inc"]:
            doc["seq"] += u["$inc"]["seq"]
        return dict(doc)

    db.counters.find_one_and_update = AsyncMock(side_effect=find_one_and_update_counters)

    # sku_map, fg_inventory, audit_logs, style_folders
    db.sku_map.find = MagicMock(return_value=MockCursor([]))
    db.sku_map.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
    db.fg_inventory.find = MagicMock(return_value=MockCursor([]))
    db.fg_inventory.find_one = AsyncMock(return_value=None)
    db.fg_inventory.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
    db.fg_inventory.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    db.purchase_orders.find_one = AsyncMock(return_value=None)
    db.style_component_mapping.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    db.style_folders.insert_one = AsyncMock(return_value=MagicMock())
    db.audit_logs.insert_one = AsyncMock(return_value=MagicMock())

    return db


@pytest.mark.anyio
async def test_gst_suggestion_and_config():
    cfg = await get_gst_config()
    assert cfg["threshold"] == 2500.0
    assert cfg["rate_below_or_equal"] == 5.0
    assert cfg["rate_above"] == 18.0

    assert suggest_gst_pct(1500) == 5.0
    assert suggest_gst_pct(2500) == 5.0
    assert suggest_gst_pct(2501) == 18.0
    assert suggest_gst_pct(0) == 5.0
    assert suggest_gst_pct(None) == 5.0


@pytest.mark.anyio
async def test_catalogue_sku_builder():
    assert build_catalogue_sku("SSK_00001", "TN") == "SSK_00001-TN"
    assert build_catalogue_sku("SSK_00001", "TN", "8") == "SSK_00001-TN-8"
    assert build_catalogue_sku("", "TN") == ""
    assert build_catalogue_sku("SSK_00001", "") == ""


@pytest.mark.anyio
async def test_style_costing_math():
    style = {
        "bom": [
            {"rate": 100.0, "quantity": 1.0, "yield_per_unit": 1.0, "waste_pct": 10.0}  # 110.0
        ],
        "labor": [
            {"name": "Stitching", "rate": 30.0},
            {"name": "Pasting", "rate": 20.0},  # total labor 50.0
        ],
        "overhead_pct": 10.0,  # 10% of (110 + 50) = 16.0
        "packing_cost": 14.0,  # total cost = 160 + 16 + 14 = 190.0
        "margin_pct": 20.0,    # margin = 38.0 -> target price 228.0
        "gst_pct": 5.0,        # gst = 11.4 -> price with gst 239.4
    }
    costing = compute_style_costing(style)
    assert costing["materials_cost"] == 110.0
    assert costing["labor_cost"] == 50.0
    assert costing["overhead_cost"] == 16.0
    assert costing["packing_cost"] == 14.0
    assert costing["total_cost"] == 190.0
    assert costing["suggested_target_price"] == 228.0
    assert costing["gst_amount"] == 11.4
    assert costing["suggested_target_price_with_gst"] == 239.4


@pytest.mark.anyio
async def test_style_lifecycle_state_machine():
    # Testing invalid skip transition raises 400
    with pytest.raises(HTTPException):
        _validate_online_status_transition("draft", "live")

    # Testing valid forward step-by-step transitions
    _validate_online_status_transition("draft", "sample_approved")
    _validate_online_status_transition("sample_approved", "photoshoot_completed")

    # Testing transition to side branches (archived, liquidation_candidate)
    _validate_online_status_transition("draft", "archived")
    _validate_online_status_transition("catalog_completed", "liquidation_candidate")


@pytest.mark.anyio
async def test_style_master_crud_and_summary(monkeypatch, mock_db):
    monkeypatch.setattr(server, "db", mock_db)
    async def mock_user(request=None):
        return {"email": "admin@sskfootcare.com", "role": "admin"}
    monkeypatch.setattr(server, "get_current_user", mock_user)

    req = DummyRequest()

    # 1. Create Style
    payload = StyleIn(
        name="Sports Runner Pro",
        category="Footwear",
        base_size="8",
        bom=[{
            "material_id": "mat_1",
            "material_name": "Leather Upper",
            "material_code": "MAT-001",
            "unit": "sqft",
            "quantity": 1,
            "rate": 100,
        }],
        labor=[{"name": "Stitching", "rate": 50}],
        overhead_pct=10.0,
        packing_cost=10.0,
        margin_pct=25.0,
        gst_pct=5.0,
    )
    res = await create_style(payload, req)
    assert res["name"] == "Sports Runner Pro"
    assert res["code"].startswith("SSK_")
    sid = res["id"]

    # 2. Get Style
    fetched = await get_style(sid, req)
    assert fetched["id"] == sid
    assert fetched["name"] == "Sports Runner Pro"
    assert "costing" in fetched

    # 3. List Styles Summary (batch query zero N+1)
    summaries = await list_styles_summary(req)
    assert len(summaries) == 1
    assert summaries[0]["id"] == sid
    assert summaries[0]["name"] == "Sports Runner Pro"
    assert "cost_summary" in summaries[0]

    # 4. Color Master
    color_in = ColorMasterIn(color_name="Burgundy", color_code="BG")
    c_res = await create_color(color_in, req)
    assert c_res["color_code"] == "BG"

    resolved = await resolve_color_code("Burgundy")
    assert resolved == "BG"

    # 5. Pipeline Add/Remove
    pipe_add = await add_style_to_online_pipeline(sid, req)
    assert pipe_add["ok"] is True

    pipe_styles = await list_online_styles(req)
    assert len(pipe_styles) == 1
    assert pipe_styles[0]["style_id"] == sid

    pipe_rem = await remove_style_from_online_pipeline(sid, req)
    assert pipe_rem["ok"] is True
