import pytest
from routes.online_returns_engine import (
    classify_return_reason,
    parse_sku_details,
    get_footwear_placeholder_image,
)

def test_classify_return_reason():
    assert classify_return_reason("Size is different", "RETURN") == "SIZING_FIT"
    assert classify_return_reason("Product was defective", "RETURN") == "QUALITY_DEFECT"
    assert classify_return_reason("Product image was better than the actual product", "RETURN") == "CATALOG_MISMATCH"
    assert classify_return_reason("Received a completely different product", "RETURN") == "DISPATCH_ERROR"
    assert classify_return_reason("I do not need it anymore", "RETURN") == "BUYER_REMORSE"
    assert classify_return_reason("", "RTO") == "COURIER_RTO"
    assert classify_return_reason("Courier return", "RETURN") == "COURIER_RTO"

def test_parse_sku_details():
    res1 = parse_sku_details("FLL_AK_005_GO-7")
    assert res1["style_code"] == "FLL_AK_005"
    assert res1["color"] == "GO"
    assert res1["size"] == "7"

    res2 = parse_sku_details("CC-058-BR-38")
    assert res2["style_code"] == "CC_058"
    assert res2["color"] == "BR"
    assert res2["size"] == "38"

    res3 = parse_sku_details("SLIDE-01-9")
    assert res3["style_code"] == "SLIDE-01"
    assert res3["size"] == "9"

def test_get_footwear_placeholder_image():
    assert get_footwear_placeholder_image("SLIDE_101") == "/company/braided_slide.jpg"
    assert get_footwear_placeholder_image("FLL_AK_005") == "/company/laser_cut_flat.jpg"
    assert get_footwear_placeholder_image("CC_0003") == "/company/laser_cut_flat.jpg"
    assert get_footwear_placeholder_image("ETHNIC_JUTTI_01") == "/company/ethnic_embroidered.jpg"
    assert get_footwear_placeholder_image("DERBY_BLACK") == "/company/black_derby.jpg"
    assert get_footwear_placeholder_image("OXFORD_TAN") == "/company/classic_oxford.jpg"


from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from bson import ObjectId
import io
import server
from routes.online_returns_engine import online_returns_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    async def to_list(self, limit=10000):
        return self.docs[:limit]

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockReturnsDB:
    def __init__(self):
        self.records_store = []
        self.batches_store = {}
        self.photos_store = {}
        self.styles_store = {}
        self.sku_map_store = {}
        self.actions_store = []
        self.system_settings_store = {}
        self.platform_settings_store = {}
        self.online_orders_store = []

        self.online_returns_records = MagicMock()
        self.online_returns_records.find = MagicMock(side_effect=self._find_records)
        self.online_returns_records.insert_many = AsyncMock(side_effect=self._insert_records)
        self.online_returns_records.delete_many = AsyncMock(side_effect=self._delete_records)
        self.online_returns_records.count_documents = AsyncMock(side_effect=self._count_records)
        self.online_returns_records.find_one = AsyncMock(return_value=None)

        self.online_returns_batches = MagicMock()
        self.online_returns_batches.find_one = AsyncMock(return_value={"month": "2026-08"})
        self.online_returns_batches.update_one = AsyncMock(return_value=MagicMock())
        self.online_returns_batches.distinct = AsyncMock(return_value=["2026-08"])

        self.online_style_photos = MagicMock()
        self.online_style_photos.find = MagicMock(side_effect=lambda q=None: MockCursor([]))
        self.online_style_photos.update_one = AsyncMock(return_value=MagicMock())

        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=lambda q=None, p=None: MockCursor([]))
        self.styles.update_one = AsyncMock(return_value=MagicMock())

        self.sku_map = MagicMock()
        self.sku_map.find = MagicMock(side_effect=lambda q=None, p=None: MockCursor([]))

        self.online_return_actions = MagicMock()
        self.online_return_actions.insert_one = AsyncMock(side_effect=self._insert_action)
        self.online_return_actions.find = MagicMock(side_effect=lambda q=None: MockCursor(self.actions_store))

        self.system_settings = MagicMock()
        self.system_settings.find_one = AsyncMock(side_effect=lambda q: self.system_settings_store.get(q.get("key")))

        self.platform_settings = MagicMock()
        self.platform_settings.find_one = AsyncMock(return_value=None)

        self.online_orders = MagicMock()
        self.online_orders.count_documents = AsyncMock(return_value=0)

    def _find_records(self, q=None):
        docs = list(self.records_store)
        if q:
            if "month" in q:
                docs = [d for d in docs if d.get("month") == q["month"]]
            if "style_code" in q:
                docs = [d for d in docs if d.get("style_code") == q["style_code"]]
        return MockCursor(docs)

    async def _insert_records(self, docs):
        self.records_store.extend(docs)
        return MagicMock(inserted_ids=[ObjectId() for _ in docs])

    async def _delete_records(self, q):
        before = len(self.records_store)
        if "batch_id" in q and "$ne" in q["batch_id"]:
            keep_batch = q["batch_id"]["$ne"]
            self.records_store = [d for d in self.records_store if d.get("batch_id") == keep_batch]
        elif "batch_id" in q:
            del_batch = q["batch_id"]
            self.records_store = [d for d in self.records_store if d.get("batch_id") != del_batch]
        return MagicMock(deleted_count=before - len(self.records_store))

    async def _count_records(self, q):
        return len(self.records_store)

    async def _insert_action(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.actions_store.append(doc)
        return MagicMock(inserted_id=oid)


def test_online_returns_endpoints_require_authentication(monkeypatch):
    mock_db = MockReturnsDB()
    monkeypatch.setattr(server, "db", mock_db)

    # 1. Unauthenticated request -> should raise 401
    async def mock_get_current_user_unauth(request=None):
        raise HTTPException(status_code=401, detail="Authentication required")

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user_unauth)

    app = FastAPI()
    app.include_router(online_returns_router)
    app.mongodb = mock_db
    client = TestClient(app)

    res1 = client.get("/api/online-returns/analytics")
    assert res1.status_code == 401

    res2 = client.get("/api/online-returns/prescriptions")
    assert res2.status_code == 401

    res3 = client.post("/api/online-returns/style-photo", json={"style_code": "SSK-1", "image_url": "http://img.jpg"})
    assert res3.status_code == 401

    res4 = client.post("/api/online-returns/actions", json={
        "style_code": "SSK-1", "action_type": "LAST_ADJUSTMENT", "category": "SIZING_FIT",
        "title": "Fix size", "description": "Adjust mold", "target_month": "2026-08", "applied_date": "2026-08-15"
    })
    assert res4.status_code == 401

    res5 = client.get("/api/online-returns/impact-check")
    assert res5.status_code == 401


def test_online_returns_role_authorization_and_features(monkeypatch):
    mock_db = MockReturnsDB()
    monkeypatch.setattr(server, "db", mock_db)

    # 1. Unauthorized role "viewer" cannot upload or modify style photo
    async def mock_viewer(request=None):
        return {"id": "u1", "email": "viewer@example.com", "role": "viewer"}

    monkeypatch.setattr(server, "get_current_user", mock_viewer)

    app = FastAPI()
    app.include_router(online_returns_router)
    app.mongodb = mock_db
    client = TestClient(app)

    csv_data = "seller_sku_code,status,return_reason,brand\nSSK-BOOT-42,RETURN,size too small,SSK\n"
    res_upload = client.post(
        "/api/online-returns/upload?month=2026-08&platform=myntra",
        files={"file": ("returns.csv", io.BytesIO(csv_data.encode()), "text/csv")}
    )
    assert res_upload.status_code == 403

    # 2. Switch to admin user
    async def mock_admin(request=None):
        return {"id": "admin_1", "email": "admin@sskfootcare.com", "role": "admin"}

    monkeypatch.setattr(server, "get_current_user", mock_admin)

    # Upload returns as admin
    res_upload_ok = client.post(
        "/api/online-returns/upload?month=2026-08&platform=myntra",
        files={"file": ("returns.csv", io.BytesIO(csv_data.encode()), "text/csv")}
    )
    assert res_upload_ok.status_code == 200
    assert res_upload_ok.json()["success"] is True
    assert len(mock_db.records_store) == 1

    # Analytics with configurable freight rate
    res_analytics = client.get("/api/online-returns/analytics?month=2026-08&freight_rate=95.0")
    assert res_analytics.status_code == 200
    data = res_analytics.json()
    assert data["reverse_freight_rate_applied"] == 95.0
    assert data["is_freight_estimated"] is True
    assert data["freight_rate_source"] == "query_parameter"

    # Style photo update
    res_photo = client.post("/api/online-returns/style-photo", json={
        "style_code": "SSK-BOOT", "image_url": "https://img.com/boot.jpg"
    })
    assert res_photo.status_code == 200
    assert res_photo.json()["success"] is True

    # Record applied fix
    res_action = client.post("/api/online-returns/actions", json={
        "style_code": "SSK-BOOT",
        "action_type": "LAST_ADJUSTMENT",
        "category": "SIZING_FIT",
        "title": "Adjust boot sizing",
        "description": "Widened 2mm",
        "target_month": "2026-08",
        "applied_date": "2026-08-10"
    })
    assert res_action.status_code == 200
    assert res_action.json()["user"] == "admin@sskfootcare.com"

    # Impact check
    res_impact = client.get("/api/online-returns/impact-check?style_code=SSK-BOOT")
    assert res_impact.status_code == 200
    assert len(res_impact.json()["results"]) == 1

