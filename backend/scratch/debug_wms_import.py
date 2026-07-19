"""Throwaway debug script to reproduce the WMS online order import picklist auto-generation bug."""

import sys
sys.path.insert(0, '.')
import asyncio
from bson import ObjectId
from unittest.mock import MagicMock


class AsyncCursor:
    def __init__(self, docs):
        self.docs = list(docs)
        self.index = 0

    def sort(self, sort_spec):
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

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        return MagicMock(inserted_id=d["_id"])

    async def insert_many(self, docs):
        for doc in docs:
            await self.insert_one(doc)
        return MagicMock(inserted_ids=[d["_id"] for d in docs])


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
        self.settings = MockCollection("settings")
        self.unresolved_sku_queue = MockCollection("unresolved_sku_queue")

    def __getitem__(self, name):
        return getattr(self, name)


async def debug_repro():
    import server
    mock_db = MockDB()
    server.db = mock_db

    # 1. Create a style
    style_id = ObjectId()
    await mock_db.styles.insert_one({
        "_id": style_id,
        "code": "WMS-STYLE-01",
        "name": "WMS Test Style",
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

    # 3. Perform production_in movement of 10 pairs via _allocate_to_locations
    await server._allocate_to_locations(
        style_id=str(style_id),
        style_code="WMS-STYLE-01",
        color="Black",
        size="8",
        qty=10,
        user_email="admin@example.com",
        zone="main"
    )

    print("--- RAW fg_location_inventory DOCS ---")
    for doc in mock_db.fg_location_inventory.docs:
        print("Doc:", doc)
        print("  style_id type:", type(doc.get("style_id")), "val:", doc.get("style_id"))
        print("  color type:", type(doc.get("color")), "val:", repr(doc.get("color")))
        print("  size type:", type(doc.get("size")), "val:", repr(doc.get("size")))
        print("  qty type:", type(doc.get("qty")), "val:", doc.get("qty"))
        print("  reserved_qty type:", type(doc.get("reserved_qty")), "val:", repr(doc.get("reserved_qty")))

    # 4. Test exact query in POST /api/online-orders/import
    result = {
        "style_id": str(style_id),
        "style_code": "WMS-STYLE-01",
        "color": "Black",
        "size": "8"
    }

    print("\n--- RUNNING IMPORT Stock Coverage Check ---")
    try:
        style_oid = ObjectId(result["style_id"])
        covered_available = 0
        async for loc in mock_db.fg_location_inventory.find({
            "style_id": style_oid,
            "color": result["color"],
            "size":  result["size"],
            "qty":   {"$gt": 0},
        }):
            res_val = int(loc.get("reserved_qty", 0) or 0)
            print("loc doc found in find():", loc, "calculated free:", int(loc.get("qty", 0)) - res_val)
            covered_available += max(0, int(loc.get("qty", 0)) - res_val)
        print("covered_available calculated:", covered_available)
    except Exception as e:
        import traceback
        print("EXCEPT IN STOCK CHECK:", type(e), e)
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_repro())
