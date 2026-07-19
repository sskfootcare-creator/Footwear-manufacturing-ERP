"""Full reproduction script for WMS online order import picklist bug using mock database."""

import sys
sys.path.insert(0, '.')
import asyncio
import io
from bson import ObjectId
from unittest.mock import MagicMock
from fastapi import UploadFile
import auth
import server


class AsyncCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.index = 0

    def limit(self, limit_count):
        self.docs = self.docs[:limit_count]
        return self

    def sort(self, *args, **kwargs):
        sort_spec = args[0] if args else kwargs.get("key")
        if isinstance(sort_spec, list):
            for key, direction in reversed(sort_spec):
                self.docs.sort(key=lambda d: d.get(key, ""), reverse=(direction < 0))
        return self

    def to_list(self, limit):
        fut = asyncio.Future()
        fut.set_result(self.docs[:limit])
        return fut

    def __aiter__(self):
        self.index = 0
        return self

    async def __anext__(self):
        if self.index < len(self.docs):
            item = self.docs[self.index]
            self.index += 1
            return item
        raise StopAsyncIteration


class MockCollection:
    def __init__(self, name):
        self.name = name
        self.docs = []

    def _match_doc(self, doc, filter_dict):
        for k, v in filter_dict.items():
            if k == "$or":
                sub_match = any(
                    all(doc.get(sub_k) == sub_v for sub_k, sub_v in sub_d.items())
                    for sub_d in v
                )
                if not sub_match:
                    return False
                continue

            val = doc.get(k)
            if isinstance(v, dict):
                if "$gt" in v and not (val is not None and val > v["$gt"]):
                    return False
                if "$ne" in v and val == v["$ne"]:
                    return False
                if "$nin" in v and val in v["$nin"]:
                    return False
                if "$regex" in v:
                    import re
                    opts = v.get("$options", "")
                    flags = re.IGNORECASE if "i" in opts else 0
                    if not (val is not None and re.search(v["$regex"], str(val), flags)):
                        return False
            elif val != v:
                return False
        return True

    async def find_one(self, filter_dict, sort=None):
        results = [d for d in self.docs if self._match_doc(d, filter_dict)]
        if not results:
            return None
        if sort:
            for key, direction in reversed(sort):
                results.sort(key=lambda d: d.get(key, ""), reverse=(direction < 0))
        return results[0]

    def find(self, filter_dict, projection=None, sort=None):
        matched = [d for d in self.docs if self._match_doc(d, filter_dict)]
        cursor = AsyncCursor(matched)
        if sort:
            cursor.sort(sort)
        return cursor

    async def update_one(self, filter_dict, update_dict, upsert=False):
        existing = await self.find_one(filter_dict)
        if existing:
            if "$inc" in update_dict:
                for k, v in update_dict["$inc"].items():
                    existing[k] = existing.get(k, 0) + v
            if "$set" in update_dict:
                for k, v in update_dict["$set"].items():
                    existing[k] = v
            return MagicMock(modified_count=1, upserted_id=None)
        elif upsert:
            new_doc = {"_id": ObjectId()}
            for k, v in filter_dict.items():
                if not k.startswith("$"):
                    new_doc[k] = v
            if "$setOnInsert" in update_dict:
                for k, v in update_dict["$setOnInsert"].items():
                    new_doc[k] = v
            if "$inc" in update_dict:
                for k, v in update_dict["$inc"].items():
                    new_doc[k] = new_doc.get(k, 0) + v
            if "$set" in update_dict:
                for k, v in update_dict["$set"].items():
                    new_doc[k] = v
            self.docs.append(new_doc)
            return MagicMock(modified_count=1, upserted_id=new_doc["_id"])
        return MagicMock(modified_count=0, upserted_id=None)

    async def update_many(self, filter_dict, update_dict):
        matched = [d for d in self.docs if self._match_doc(d, filter_dict)]
        cnt = 0
        for doc in matched:
            if "$set" in update_dict:
                for k, v in update_dict["$set"].items():
                    doc[k] = v
            cnt += 1
        return MagicMock(modified_count=cnt)

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        return MagicMock(inserted_id=d["_id"])

    async def insert_many(self, docs):
        ids = []
        for doc in docs:
            res = await self.insert_one(doc)
            ids.append(res.inserted_id)
        return MagicMock(inserted_ids=ids)


class MockDB:
    def __init__(self):
        self.styles = MockCollection("styles")
        self.fg_inventory = MockCollection("fg_inventory")
        self.fg_location_inventory = MockCollection("fg_location_inventory")
        self.warehouse_locations = MockCollection("warehouse_locations")
        self.production_jobs = MockCollection("production_jobs")
        self.picklists = MockCollection("picklists")
        self.sku_map = MockCollection("sku_map")
        self.activity_logs = MockCollection("activity_logs")
        self.audit_logs = MockCollection("audit_logs")
        self.settings = MockCollection("settings")
        self.unresolved_sku_queue = MockCollection("unresolved_sku_queue")
        self.marketplace_style_color_mapping = MockCollection("marketplace_style_color_mapping")
        self.sku_parser_templates = MockCollection("sku_parser_templates")
        self.parser_templates = MockCollection("parser_templates")
        self.inventory_reservations = MockCollection("inventory_reservations")
        self.fg_stock_movements = MockCollection("fg_stock_movements")

    def __getitem__(self, name):
        return getattr(self, name)


async def test_repro():
    mock_db = MockDB()
    server.db = mock_db

    # 1. Create a style
    style_id = ObjectId()
    await mock_db.styles.insert_one({
        "_id": style_id,
        "code": "WMS-REG-01",
        "name": "WMS Regression Style",
        "active": True
    })

    # 2. Add warehouse location
    await mock_db.warehouse_locations.insert_one({
        "_id": ObjectId(),
        "location_code": "A-01-01",
        "zone": "main",
        "status": "empty",
        "capacity_pairs": 50,
        "occupied_pairs": 0,
        "available_pairs": 50,
        "rack": "A", "row": "01", "cell": "01"
    })

    # 3. Create SKU Map
    map_res = await mock_db.sku_map.insert_one({
        "style_id": str(style_id),
        "style_code": "WMS-REG-01",
        "source_type": "online_channel",
        "source_name": "flipkart",
        "external_sku": "EXT-WMS-REG",
        "color_map": {"Black": "Black"},
        "size_map": {"8": "8"}
    })

    # 4. Post production_in movement of 10 pairs
    mv_payload = server.FgStockMovementIn(
        style_id=str(style_id),
        color="Black",
        size="8",
        movement_type="production_in",
        quantity=10,
        reference_type="manual",
        notes="Test stock"
    )
    await server._apply_movement(mv_payload, "admin@example.com")

    print("--- FG INVENTORY ---")
    for d in mock_db.fg_inventory.docs:
        print(d)

    print("\n--- FG LOCATION INVENTORY ---")
    for d in mock_db.fg_location_inventory.docs:
        print(d)

    # Test enhanced translate logic
    color_map = {"Black": "Black"}
    size_map = {"8": "8"}
    def translate(m: dict, val: str) -> str:
        val = (val or "").strip()
        if val and val in m:
            return m[val]
        if val:
            val_lower = val.lower()
            for k, v in m.items():
                if k.lower() == val_lower:
                    return v
        if len(m) == 1:
            return next(iter(m.values()))
        return val

    print("Translate empty color with len(color_map)==1:", repr(translate(color_map, "")))
    print("Translate empty size with len(size_map)==1:", repr(translate(size_map, "")))

    # 5. Case A: CSV with lowercase color "black"
    csv_bytes_a = b"order_id,style_sku,color,size,quantity\nORD-WMS-REG-A,EXT-WMS-REG,black,8,5\n"
    file_obj_a = UploadFile(filename="test_a.csv", file=io.BytesIO(csv_bytes_a))

    async def mock_get_user(req):
        return {"email": "admin@example.com", "role": "admin"}
    server.get_current_user = mock_get_user

    res_a = await server.import_online_orders(
        file=file_obj_a,
        channel="flipkart",
        request=MagicMock()
    )

    print("\n--- CASE A: Lowercase color 'black' ---")
    print("imported:", res_a.get("imported"))
    print("fulfilled_from_stock:", res_a.get("fulfilled_from_stock"))
    print("picklists_created:", res_a.get("picklists_created"))

    # 6. Case B: CSV with no color/size specified (empty string)
    csv_bytes_b = b"order_id,style_sku,quantity\nORD-WMS-REG-B,EXT-WMS-REG,5\n"
    file_obj_b = UploadFile(filename="test_b.csv", file=io.BytesIO(csv_bytes_b))

    res_b = await server.import_online_orders(
        file=file_obj_b,
        channel="flipkart",
        request=MagicMock()
    )

    print("\n--- CASE B: Missing color/size in CSV ---")
    print("imported:", res_b.get("imported"))
    print("fulfilled_from_stock:", res_b.get("fulfilled_from_stock"))
    print("picklists_created:", res_b.get("picklists_created"))

if __name__ == "__main__":
    asyncio.run(test_repro())
