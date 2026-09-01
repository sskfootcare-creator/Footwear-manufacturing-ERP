import io
import json
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

from routes.po_ean import po_ean_router, _seed_po_ean_format_configs
import auth


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
            if k == "_id":
                if isinstance(v, dict) and "$in" in v:
                    if str(doc.get("_id")) not in [str(x) for x in v["$in"]]:
                        return False
                elif str(doc.get("_id")) != str(v):
                    return False
            elif k == "name" and doc.get("name") != v:
                return False
            elif k == "po_id" and str(doc.get("po_id")) != str(v):
                return False
            elif k == "active" and doc.get("active") != v:
                return False
            elif k == "client_name" and isinstance(v, dict) and "$regex" in v:
                cname = str(doc.get("client_name") or "")
                regex_val = v["$regex"].strip("^$")
                if regex_val.lower() not in cname.lower() and cname.lower() not in regex_val.lower():
                    return False
            elif isinstance(v, dict):
                continue
            elif doc.get(k) != v:
                return False
        return True

    def find(self, q=None, projection=None):
        matched = [d for d in self.store.values() if self._matches(d, q)]
        return MockCursor(matched)

    async def find_one(self, q=None, projection=None):
        for d in self.store.values():
            if self._matches(d, q):
                return dict(d)
        return None

    async def insert_one(self, doc):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        oid_str = str(doc_copy["_id"])
        self.store[oid_str] = doc_copy
        res = MagicMock()
        res.inserted_id = doc_copy["_id"]
        return res

    async def update_one(self, match, update):
        for doc in self.store.values():
            if self._matches(doc, match):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = v
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def delete_one(self, match):
        for k, doc in list(self.store.items()):
            if self._matches(doc, match):
                del self.store[k]
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    async def delete_many(self, match):
        cnt = 0
        for k, doc in list(self.store.items()):
            if self._matches(doc, match):
                del self.store[k]
                cnt += 1
        return MagicMock(deleted_count=cnt)

    async def create_index(self, *args, **kwargs):
        return "index_ok"


class FakeDB:
    def __init__(self):
        self.pos = GenericMockCollection()
        self.po_ean_codes = GenericMockCollection()
        self.po_ean_format_configs = GenericMockCollection()
        self.styles = GenericMockCollection()
        self.sku_map = GenericMockCollection()


@pytest.fixture
def client_app():
    fake_db = FakeDB()
    app = FastAPI()
    app.mongodb = fake_db
    app.include_router(po_ean_router)

    async def override_user(request=None):
        return {"email": "admin@example.com", "role": "admin"}

    async def get_mock_factory(db=None):
        return override_user

    auth.get_current_user_factory = get_mock_factory
    import routes.po_ean
    routes.po_ean.get_current_user_factory = get_mock_factory

    # Seed default styles and a PO
    po_oid = ObjectId("654321654321654321654321")
    po_doc = {
        "_id": po_oid,
        "po_number": "PO-TEST-001",
        "client_name": "Bata India",
        "client": "Bata",
        "line_items": [
            {"style_code": "ART-ALPHA", "color": "Black", "size": "7", "quantity": 100},
            {"style_code": "ART-ALPHA", "color": "Black", "size": "8", "quantity": 150},
            {"style_code": "ART-BETA", "color": "Tan", "size": "9", "quantity": 50},
        ],
    }
    fake_db.pos.store[str(po_oid)] = po_doc

    test_client = TestClient(app)
    return test_client, fake_db, str(po_oid)


def test_seed_and_list_po_ean_formats(client_app):
    client, db, po_id = client_app
    # Seed default templates
    import asyncio
    asyncio.run(_seed_po_ean_format_configs(db))

    r = client.get("/api/po-ean-formats")
    assert r.status_code == 200
    formats = r.json()
    assert len(formats) >= 4
    names = [f["name"] for f in formats]
    assert "Generic EAN Template" in names
    assert "Bata Barcodes Format" in names


def test_po_ean_file_import_matches_and_unmatched_flags(client_app):
    client, db, po_id = client_app
    import asyncio
    asyncio.run(_seed_po_ean_format_configs(db))

    # CSV file with:
    # 2 matching rows for ART-ALPHA Black (7 and 8)
    # 1 non-matching row for UNKNOWN-STYLE Red 10
    csv_content = (
        "Style Code,Color,Size,EAN Code,PO Number\n"
        "ART-ALPHA,Black,7,8901000000001,PO-TEST-001\n"
        "ART-ALPHA,Black,8,8901000000002,PO-TEST-001\n"
        "UNKNOWN-STYLE,Red,10,8909999999999,PO-TEST-001\n"
    ).encode("utf-8")

    files = {
        "file": ("test_barcodes.csv", csv_content, "text/csv"),
    }
    data = {
        "overwrite_existing": "false",
    }

    r = client.post(f"/api/pos/{po_id}/ean-codes/import", files=files, data=data)
    assert r.status_code == 200
    result = r.json()

    assert result["ok"] is True
    assert result["imported"] == 2
    assert result["unmatched_count"] == 1
    assert len(result["unmatched_rows"]) == 1
    assert result["unmatched_rows"][0]["raw_style"] == "UNKNOWN-STYLE"
    assert "does not match any valid line item" in result["unmatched_rows"][0]["reason"]

    # Verify db entries are strictly scoped to po_id
    records = list(db.po_ean_codes.store.values())
    assert len(records) == 2
    assert all(r["po_id"] == po_id for r in records)
    eans = {r["size"]: r["ean_code"] for r in records}
    assert eans["7"] == "8901000000001"
    assert eans["8"] == "8901000000002"


def test_po_ean_duplicate_and_overwrite(client_app):
    client, db, po_id = client_app

    # Initial JSON import
    payload = {
        "po_id": po_id,
        "items": [
            {"style_code": "ART-ALPHA", "color": "Black", "size": "7", "ean_code": "OLD_EAN_7"},
        ],
        "overwrite_existing": False,
    }
    r = client.post(f"/api/pos/{po_id}/ean-codes/import", json=payload)
    assert r.status_code == 200
    assert r.json()["imported"] == 1

    # Second import without overwrite -> should skip
    payload_new = {
        "po_id": po_id,
        "items": [
            {"style_code": "ART-ALPHA", "color": "Black", "size": "7", "ean_code": "NEW_EAN_7"},
        ],
        "overwrite_existing": False,
    }
    r2 = client.post(f"/api/pos/{po_id}/ean-codes/import", json=payload_new)
    assert r2.json()["imported"] == 0
    assert r2.json()["skipped_duplicates"] == 1

    # Third import with overwrite -> should update
    payload_overwrite = {
        "po_id": po_id,
        "items": [
            {"style_code": "ART-ALPHA", "color": "Black", "size": "7", "ean_code": "NEW_EAN_7"},
        ],
        "overwrite_existing": True,
    }
    r3 = client.post(f"/api/pos/{po_id}/ean-codes/import", json=payload_overwrite)
    assert r3.json()["imported"] == 1

    # Check list endpoint
    r_list = client.get(f"/api/pos/{po_id}/ean-codes")
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert len(items) == 1
    assert items[0]["ean_code"] == "NEW_EAN_7"

    # Delete endpoint
    r_del = client.delete(f"/api/pos/{po_id}/ean-codes")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True
    assert len(db.po_ean_codes.store) == 0
