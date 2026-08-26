"""Unit tests for online orders & marketplace format import routes."""

import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from bson import ObjectId
from datetime import datetime, timezone

import server
from routes.online_orders import (
    online_orders_router,
    _seed_order_import_format_configs,
    ORDER_CANONICAL_FIELDS,
    DISPATCH_CANONICAL_FIELDS,
    MONTHLY_REPORT_CANONICAL_FIELDS,
    SETTLEMENT_CANONICAL_FIELDS,
    OrderImportFormatConfigIn,
    OrderImportFormatConfigUpdate,
    list_order_import_format_configs,
    get_order_import_format_config,
    create_order_import_format_config,
    update_order_import_format_config,
    delete_order_import_format_config,
    import_configured_online_orders,
    import_dispatch_orders,
    import_monthly_report,
    import_settlement,
    list_settlements,
    settlement_summary,
    reconciliation_summary,
    import_online_orders,
    list_online_orders,
)


class MockCursor:
    def __init__(self, docs):
        self.docs = [dict(d) for d in docs]

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, count):
        self.docs = self.docs[:count]
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


class GenericMockCollection:
    def __init__(self):
        self.store = {}

    def _matches(self, doc, q):
        if not q:
            return True
        for k, v in q.items():
            if k == "_id" and not isinstance(v, dict):
                if str(doc.get("_id")) != str(v):
                    return False
            elif k == "$or":
                if not any(self._matches(doc, subq) for subq in v):
                    return False
            elif isinstance(v, dict):
                if "$in" in v:
                    doc_val = doc.get(k)
                    str_in = [str(x) for x in v["$in"]]
                    if isinstance(doc_val, list):
                        if not any(str(x) in str_in or x in v["$in"] for x in doc_val):
                            return False
                    else:
                        if str(doc_val) not in str_in and doc_val not in v["$in"]:
                            return False
                if "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        return False
                if "$regex" in v:
                    pattern = v["$regex"].lstrip("^").rstrip("$")
                    if pattern.lower() not in str(doc.get(k, "")).lower():
                        return False
                if "$gt" in v:
                    if not (doc.get(k, 0) > v["$gt"]):
                        return False
                if "$gte" in v:
                    if not (doc.get(k, "") >= v["$gte"]):
                        return False
                if "$lte" in v:
                    if not (doc.get(k, "") <= v["$lte"]):
                        return False
                if "$exists" in v:
                    exists = k in doc
                    if exists != v["$exists"]:
                        return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    async def find_one(self, q, *args, **kwargs):
        for doc in self.store.values():
            if self._matches(doc, q):
                return dict(doc)
        return None

    def find(self, q=None, *args, **kwargs):
        q = q or {}
        matches = [d for d in self.store.values() if self._matches(d, q)]
        return MockCursor(matches)

    async def insert_one(self, doc):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        _id = str(doc_copy["_id"])
        self.store[_id] = doc_copy
        res = MagicMock()
        res.inserted_id = doc_copy["_id"]
        return res

    async def insert_many(self, docs):
        res_ids = []
        for d in docs:
            r = await self.insert_one(d)
            res_ids.append(r.inserted_id)
        res = MagicMock()
        res.inserted_ids = res_ids
        return res

    async def update_one(self, q, update, upsert=False):
        for doc in self.store.values():
            if self._matches(doc, q):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                if "$push" in update:
                    for k, v in update["$push"].items():
                        if k not in doc:
                            doc[k] = []
                        doc[k].append(v)
                res = MagicMock()
                res.matched_count = 1
                res.modified_count = 1
                return res
        if upsert:
            new_doc = dict(q)
            if "$set" in update:
                new_doc.update(update["$set"])
            new_doc["_id"] = ObjectId()
            self.store[str(new_doc["_id"])] = new_doc
            res = MagicMock()
            res.upserted_id = new_doc["_id"]
            return res
        res = MagicMock()
        res.matched_count = 0
        res.modified_count = 0
        return res

    async def update_many(self, q, update, *args, **kwargs):
        count = 0
        for doc in self.store.values():
            if self._matches(doc, q):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                if "$push" in update:
                    for k, v in update["$push"].items():
                        if k not in doc:
                            doc[k] = []
                        doc[k].append(v)
                count += 1
        res = MagicMock()
        res.modified_count = count
        return res

    async def delete_one(self, q):
        for k, doc in list(self.store.items()):
            if self._matches(doc, q):
                del self.store[k]
                res = MagicMock()
                res.deleted_count = 1
                return res
        res = MagicMock()
        res.deleted_count = 0
        return res

    async def count_documents(self, q):
        return sum(1 for doc in self.store.values() if self._matches(doc, q))

    async def create_index(self, *args, **kwargs):
        pass

    async def drop_index(self, *args, **kwargs):
        pass

    async def index_information(self):
        return {}


class MockDB:
    def __init__(self):
        self.order_import_format_configs = GenericMockCollection()
        self.styles = GenericMockCollection()
        self.sku_map = GenericMockCollection()
        self.production_jobs = GenericMockCollection()
        self.fg_location_inventory = GenericMockCollection()
        self.style_color_inventory = GenericMockCollection()
        self.picklists = GenericMockCollection()
        self.picklist_counters = GenericMockCollection()
        self.fg_stock_movements = GenericMockCollection()
        self.online_orders_monthly = GenericMockCollection()
        self.online_settlements = GenericMockCollection()
        self.audit_logs = GenericMockCollection()
        self.stage_durations = GenericMockCollection()
        self.settings = GenericMockCollection()
        self.users = GenericMockCollection()
        self.marketplace_parser_templates = GenericMockCollection()
        self.marketplace_style_color_mapping = GenericMockCollection()
        self.unresolved_sku_queue = GenericMockCollection()


@pytest.fixture
def mock_db_fixture(monkeypatch):
    mock_db = MockDB()
    monkeypatch.setattr(server, "db", mock_db)
    monkeypatch.setattr("routes.online_orders.get_db", lambda: mock_db)

    async def mock_get_user(request):
        return {
            "_id": ObjectId(),
            "email": "manager@sskfootcare.com",
            "role": "admin",
            "name": "Admin User",
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_user)
    return mock_db


@pytest.fixture
def client(mock_db_fixture):
    app = FastAPI()
    app.include_router(online_orders_router)
    return TestClient(app)


def test_order_import_format_config_crud(client, mock_db_fixture):
    import asyncio
    asyncio.run(_seed_order_import_format_configs(mock_db_fixture))

    # 1. List configs
    res = client.get("/api/order-import-format-configs")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2
    platforms = [d["platform"] for d in data]
    assert "flipkart" in platforms
    assert "myntra" in platforms

    # 2. Get single config
    res = client.get("/api/order-import-format-configs/flipkart")
    assert res.status_code == 200
    assert res.json()["platform"] == "flipkart"

    # 3. Create new config
    new_cfg = {
        "platform": "ajio",
        "role": "order",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id": "order-id",
            "leaf_sku": "sku",
            "qty": "quantity",
            "selling_price": "item-price"
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {},
        "is_picklist": False,
        "active": True,
        "notes": "Ajio test config"
    }
    res = client.post("/api/order-import-format-configs", json=new_cfg)
    assert res.status_code == 200
    assert res.json()["platform"] == "ajio"

    # 4. Patch config
    res = client.patch(
        "/api/order-import-format-configs/ajio",
        json={"notes": "Updated Ajio notes"}
    )
    assert res.status_code == 200
    assert res.json()["notes"] == "Updated Ajio notes"

    # 5. Delete config
    res = client.delete("/api/order-import-format-configs/ajio")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_standard_online_order_import(client, mock_db_fixture):
    import asyncio
    s_res = asyncio.run(mock_db_fixture.styles.insert_one({
        "code": "RUN-100",
        "name": "Runner 100",
        "colors": [{"color": "Black", "sizes": ["8", "9"]}],
        "created_at": "2026-08-20T00:00:00Z"
    }))
    asyncio.run(mock_db_fixture.sku_map.insert_one({
        "source_type": "online_channel",
        "source_name": "myntra",
        "source_name_key": "myntra",
        "external_sku": "RUN-100-BLK-8",
        "external_sku_key": "run-100-blk-8",
        "style_id": str(s_res.inserted_id),
        "color_map": {},
        "size_map": {},
    }))
    asyncio.run(mock_db_fixture.sku_map.insert_one({
        "source_type": "online_channel",
        "source_name": "myntra",
        "source_name_key": "myntra",
        "external_sku": "RUN-100-BLK-9",
        "external_sku_key": "run-100-blk-9",
        "style_id": str(s_res.inserted_id),
        "color_map": {},
        "size_map": {},
    }))

    csv_content = (
        "order_id,style_sku,quantity,color,size,unit_price\n"
        "ORD-001,RUN-100-BLK-8,2,Black,8,1200\n"
        "ORD-002,RUN-100-BLK-9,1,Black,9,1200\n"
    )
    files = {"file": ("orders.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/online-orders/import?channel=myntra", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["channel"] == "myntra"
    assert data["imported"] == 2
    assert data["unresolved"] == 0

    # Test listing online orders
    list_res = client.get("/api/online-orders?channel=myntra")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 2


def test_configured_online_order_import(client, mock_db_fixture):
    import asyncio
    asyncio.run(_seed_order_import_format_configs(mock_db_fixture))
    s_res = asyncio.run(mock_db_fixture.styles.insert_one({
        "code": "FL-501",
        "name": "Flipkart Style 501",
        "colors": [{"color": "Tan", "sizes": ["7", "8"]}],
        "created_at": "2026-08-20T00:00:00Z"
    }))
    asyncio.run(mock_db_fixture.sku_map.insert_one({
        "source_type": "online_channel",
        "source_name": "flipkart",
        "source_name_key": "flipkart",
        "external_sku": "FL-501-TAN-7",
        "external_sku_key": "fl-501-tan-7",
        "style_id": str(s_res.inserted_id),
        "color_map": {},
        "size_map": {},
    }))

    csv_content = (
        "Order Id,ORDER ITEM ID,Shipment ID,Ordered On,SKU,Product,Quantity,Selling Price Per Item,Invoice Amount,Order State,Tracking ID,Dispatch by date,Buyer name,City,State,PIN Code\n"
        "OD12345,ITEM-01,SHIP-01,2026-08-25,TH-FL-501-TAN-7,Flipkart Loafer,1,1499,1499,APPROVED,TRK999,2026-08-28,John Doe,Mumbai,MH,400001\n"
    )

    # Dry run
    res_dry = client.post(
        "/api/online-orders/import-configured?platform=flipkart&dry_run=true",
        files={"file": ("flipkart_orders.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    )
    assert res_dry.status_code == 200
    assert res_dry.json()["dry_run"] is True
    assert res_dry.json()["matched_count"] == 1

    # Actual import
    res = client.post(
        "/api/online-orders/import-configured?platform=flipkart&dry_run=false",
        files={"file": ("flipkart_orders.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    )
    assert res.status_code == 200
    assert res.json()["matched_count"] == 1


def test_settlement_import_and_summaries(client, mock_db_fixture):
    import asyncio
    asyncio.run(_seed_order_import_format_configs(mock_db_fixture))
    s_res = asyncio.run(mock_db_fixture.styles.insert_one({
        "code": "FL-501",
        "name": "Flipkart Style 501",
        "colors": [{"color": "Tan", "sizes": ["7", "8"]}],
        "created_at": "2026-08-20T00:00:00Z"
    }))
    asyncio.run(mock_db_fixture.sku_map.insert_one({
        "source_type": "online_channel",
        "source_name": "flipkart",
        "source_name_key": "flipkart",
        "external_sku": "FL-501-TAN-7",
        "external_sku_key": "fl-501-tan-7",
        "style_id": str(s_res.inserted_id),
        "color_map": {},
        "size_map": {},
    }))

    csv_content = (
        "order_id,sku,sale_amount,commission,shipping_fee,reverse_shipping_fee,bank_settlement_value,settlement_date,neft_id\n"
        "OD12345,TH-FL-501-TAN-7,1500,150,50,0,1300,2026-08-26,NEFT999\n"
    )
    files = {"file": ("settlement.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post(
        "/api/online-orders/settlement-import?platform=flipkart&dry_run=false",
        files=files
    )
    assert res.status_code == 200
    assert res.json()["matched_count"] == 1

    # Check list settlements
    s_list = client.get("/api/online-orders/settlements?platform=flipkart")
    assert s_list.status_code == 200
    assert len(s_list.json()) == 1

    # Check settlement summary
    s_sum = client.get("/api/online-orders/settlement-summary?platform=flipkart")
    assert s_sum.status_code == 200
    assert s_sum.json()["total_gross"] == 1500.0
    assert s_sum.json()["total_net_payout"] == 1300.0

    # Check reconciliation summary
    rec_sum = client.get("/api/online-orders/reconciliation-summary?platform=flipkart")
    assert rec_sum.status_code == 200
    assert rec_sum.json()["settled_orders"] == 1
