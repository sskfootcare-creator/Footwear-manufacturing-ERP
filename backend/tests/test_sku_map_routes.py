"""Unit and end-to-end tests for SKU Map, Listing Import & Marketplace Resolver Routes."""

import io
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

import server
from routes.sku_map import sku_map_router


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key_or_list, direction=1):
        return self

    def limit(self, count):
        return self

    async def to_list(self, limit=1000):
        return self.docs


class MockSkuMapDB:
    def __init__(self):
        self.sku_map_store = {}
        self.listing_sessions_store = {}
        self.parser_templates_store = {}
        self.mappings_store = {}
        self.unresolved_queue_store = {}
        self.styles_store = {}
        self.production_jobs_store = {}
        self.audit_logs_store = []

        self.sku_map = MagicMock()
        self.sku_map.find = MagicMock(side_effect=self._find_sku_map)
        self.sku_map.find_one = AsyncMock(side_effect=self._find_one_sku_map)
        self.sku_map.insert_one = AsyncMock(side_effect=self._insert_sku_map)
        self.sku_map.update_one = AsyncMock(side_effect=self._update_sku_map)
        self.sku_map.delete_one = AsyncMock(side_effect=self._delete_sku_map)

        self.listing_import_sessions = MagicMock()
        self.listing_import_sessions.find = MagicMock(side_effect=self._find_listing_sessions)
        self.listing_import_sessions.find_one = AsyncMock(side_effect=self._find_one_listing_session)
        self.listing_import_sessions.insert_one = AsyncMock(side_effect=self._insert_listing_session)
        self.listing_import_sessions.update_one = AsyncMock(side_effect=self._update_listing_session)

        self.sku_parser_templates = MagicMock()
        self.sku_parser_templates.find = MagicMock(side_effect=self._find_parser_templates)
        self.sku_parser_templates.find_one = AsyncMock(side_effect=self._find_one_parser_template)
        self.sku_parser_templates.insert_one = AsyncMock(side_effect=self._insert_parser_template)
        self.sku_parser_templates.update_one = AsyncMock(side_effect=self._update_parser_template)
        self.sku_parser_templates.delete_one = AsyncMock(side_effect=self._delete_parser_template)

        self.marketplace_style_color_mapping = MagicMock()
        self.marketplace_style_color_mapping.find = MagicMock(side_effect=self._find_mappings)
        self.marketplace_style_color_mapping.find_one = AsyncMock(side_effect=self._find_one_mapping)
        self.marketplace_style_color_mapping.update_one = AsyncMock(side_effect=self._update_mapping)
        self.marketplace_style_color_mapping.delete_one = AsyncMock(side_effect=self._delete_mapping)

        self.unresolved_sku_queue = MagicMock()
        self.unresolved_sku_queue.find = MagicMock(side_effect=self._find_unresolved_queue)
        self.unresolved_sku_queue.update_one = AsyncMock(side_effect=self._update_unresolved_queue)
        self.unresolved_sku_queue.update_many = AsyncMock(side_effect=self._update_many_unresolved_queue)

        self.styles = MagicMock()
        self.styles.find = MagicMock(side_effect=self._find_styles)
        self.styles.find_one = AsyncMock(side_effect=self._find_one_style)

        self.production_jobs = MagicMock()
        self.production_jobs.find = MagicMock(side_effect=self._find_jobs)
        self.production_jobs.update_one = AsyncMock(side_effect=self._update_job)

        self.audit_logs = MagicMock()
        self.audit_logs.insert_one = AsyncMock(return_value=MagicMock(inserted_id="audit_1"))

    def _find_sku_map(self, query=None):
        docs = list(self.sku_map_store.values())
        if query:
            if "needs_style_code" in query:
                val = query["needs_style_code"]
                if val is True:
                    docs = [d for d in docs if d.get("needs_style_code") is True]
                elif isinstance(val, dict) and val.get("$ne") is True:
                    docs = [d for d in docs if d.get("needs_style_code") is not True]
            if "style_id" in query:
                docs = [d for d in docs if d.get("style_id") == query["style_id"]]
        return MockCursor(docs)

    async def _find_one_sku_map(self, query):
        if "_id" in query:
            return self.sku_map_store.get(str(query["_id"]))
        for doc in self.sku_map_store.values():
            match = True
            for k, v in query.items():
                if k == "$regex" or (isinstance(v, dict) and "$regex" in v):
                    continue
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc
        return None

    async def _insert_sku_map(self, doc):
        oid = ObjectId()
        doc["_id"] = oid
        self.sku_map_store[str(oid)] = doc
        return MagicMock(inserted_id=oid)

    async def _update_sku_map(self, query, update):
        oid_str = str(query.get("_id"))
        if oid_str in self.sku_map_store:
            self.sku_map_store[oid_str].update(update.get("$set", {}))
            return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def _delete_sku_map(self, query):
        oid_str = str(query.get("_id"))
        self.sku_map_store.pop(oid_str, None)
        return MagicMock(deleted_count=1)

    def _find_listing_sessions(self, query=None, projection=None):
        return MockCursor(list(self.listing_sessions_store.values()))

    async def _find_one_listing_session(self, query):
        if "session_id" in query:
            return self.listing_sessions_store.get(query["session_id"])
        return None

    async def _insert_listing_session(self, doc):
        sid = doc.get("session_id")
        self.listing_sessions_store[sid] = doc
        return MagicMock(inserted_id=sid)

    async def _update_listing_session(self, query, update):
        sid = query.get("session_id")
        if sid in self.listing_sessions_store:
            self.listing_sessions_store[sid].update(update.get("$set", {}))
            return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    def _find_parser_templates(self, query=None):
        return MockCursor(list(self.parser_templates_store.values()))

    async def _find_one_parser_template(self, query):
        if "marketplace" in query:
            return self.parser_templates_store.get(query["marketplace"])
        if "_id" in query:
            for t in self.parser_templates_store.values():
                if str(t.get("_id")) == str(query["_id"]):
                    return t
        return None

    async def _insert_parser_template(self, doc):
        mp = doc.get("marketplace")
        doc["_id"] = ObjectId()
        self.parser_templates_store[mp] = doc
        return MagicMock(inserted_id=doc["_id"])

    async def _update_parser_template(self, query, update, upsert=False):
        mp = query.get("marketplace")
        if mp in self.parser_templates_store:
            self.parser_templates_store[mp].update(update.get("$set", {}))
        elif upsert:
            doc = {**query, **update.get("$set", {}), "_id": ObjectId()}
            self.parser_templates_store[mp] = doc
        return MagicMock(matched_count=1)

    async def _delete_parser_template(self, query):
        oid_str = str(query.get("_id"))
        for k, v in list(self.parser_templates_store.items()):
            if str(v.get("_id")) == oid_str:
                del self.parser_templates_store[k]
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=1)

    def _find_mappings(self, query=None):
        return MockCursor(list(self.mappings_store.values()))

    async def _find_one_mapping(self, query):
        if "marketplace_key" in query:
            key = (query.get("marketplace_key"), query.get("marketplace_style_code_key"), query.get("marketplace_color_code_key"))
            return self.mappings_store.get(key)
        if "_id" in query:
            for m in self.mappings_store.values():
                if str(m.get("_id")) == str(query["_id"]):
                    return m
        return None

    async def _update_mapping(self, query, update, upsert=False):
        key = (query.get("marketplace_key"), query.get("marketplace_style_code_key"), query.get("marketplace_color_code_key"))
        if key in self.mappings_store:
            self.mappings_store[key].update(update.get("$set", {}))
        elif upsert:
            doc = {**query, **update.get("$set", {}), "_id": ObjectId()}
            self.mappings_store[key] = doc
        return MagicMock(matched_count=1)

    async def _delete_mapping(self, query):
        oid_str = str(query.get("_id"))
        for k, v in list(self.mappings_store.items()):
            if str(v.get("_id")) == oid_str:
                del self.mappings_store[k]
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=1)

    def _find_unresolved_queue(self, query=None):
        docs = list(self.unresolved_queue_store.values())
        if query and "marketplace" in query:
            docs = [d for d in docs if d.get("marketplace") == query["marketplace"]]
        return MockCursor(docs)

    async def _update_unresolved_queue(self, query, update, upsert=False):
        raw_sku = query.get("raw_sku")
        if raw_sku in self.unresolved_queue_store:
            self.unresolved_queue_store[raw_sku].update(update.get("$set", {}))
        elif upsert:
            doc = {**query, **update.get("$set", {}), "_id": ObjectId()}
            self.unresolved_queue_store[raw_sku] = doc
        return MagicMock(matched_count=1)

    async def _update_many_unresolved_queue(self, query, update):
        cnt = 0
        for doc in self.unresolved_queue_store.values():
            if doc.get("status") == "open":
                doc.update(update.get("$set", {}))
                cnt += 1
        return MagicMock(modified_count=cnt)

    def _find_styles(self, query=None, projection=None):
        return MockCursor(list(self.styles_store.values()))

    async def _find_one_style(self, query):
        import re
        if "_id" in query:
            return self.styles_store.get(str(query["_id"]))
        if "code" in query:
            val = query["code"]
            if isinstance(val, dict) and "$regex" in val:
                pattern = val["$regex"]
                flags = re.IGNORECASE if "i" in val.get("$options", "") else 0
                for s in self.styles_store.values():
                    if re.search(pattern, s.get("code", ""), flags):
                        return s
            else:
                for s in self.styles_store.values():
                    if s.get("code", "").lower() == str(val).lower():
                        return s
        return None

    def _find_jobs(self, query=None):
        return MockCursor(list(self.production_jobs_store.values()))

    async def _update_job(self, query, update):
        return MagicMock(matched_count=1, modified_count=1)


@pytest.fixture
def mock_sku_map_env(monkeypatch):
    mock_db = MockSkuMapDB()
    monkeypatch.setattr(server, "db", mock_db)

    async def mock_get_current_user(request=None):
        return {
            "id": "admin_1",
            "email": "admin@sskfootcare.com",
            "role": "admin",
            "name": "Admin User"
        }

    monkeypatch.setattr(server, "get_current_user", mock_get_current_user)
    return mock_db


@pytest.fixture
def client(mock_sku_map_env):
    test_app = FastAPI()
    test_app.include_router(sku_map_router)
    test_app.mongodb = mock_sku_map_env
    return TestClient(test_app)


def test_sku_map_crud(client, mock_sku_map_env):
    # Seed a style in mock_db
    style_oid = ObjectId()
    style_id = str(style_oid)
    mock_sku_map_env.styles_store[style_id] = {
        "_id": style_oid,
        "code": "SSK-OXF-01",
        "name": "Oxford Classic",
        "active": True,
    }

    # 1. Create SKU Map
    create_payload = {
        "style_id": style_id,
        "source_type": "online_channel",
        "source_name": "myntra",
        "external_sku": "MYN-OXF-TAN-8",
        "external_style_name": "Classic Oxford Tan",
        "color_map": {"Tan": "Tan"},
        "size_map": {"8": "8"},
    }
    res = client.post("/api/sku-map", json=create_payload)
    assert res.status_code == 200, res.text
    created = res.json()
    mid = created["id"]
    assert created["style_code"] == "SSK-OXF-01"

    # 2. List SKU Maps
    res = client.get("/api/sku-map")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == mid

    # 3. Resolve SKU
    res = client.get(f"/api/sku-map/resolve?source_type=online_channel&source_name=myntra&external_sku=MYN-OXF-TAN-8&external_color=Tan&external_size=8")
    assert res.status_code == 200
    resolved = res.json()
    assert resolved["matched"] is True
    assert resolved["style_code"] == "SSK-OXF-01"
    assert resolved["match_via"] == "sku_map"

    # 4. Update SKU Map
    update_payload = {
        "external_style_name": "Updated Oxford Tan",
        "size_map": {"8": "8", "9": "9"}
    }
    res = client.put(f"/api/sku-map/{mid}", json=update_payload)
    assert res.status_code == 200
    updated = res.json()
    assert updated["external_style_name"] == "Updated Oxford Tan"
    assert "9" in updated["size_map"]

    # 5. Delete SKU Map
    res = client.delete(f"/api/sku-map/{mid}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    res = client.get("/api/sku-map")
    assert len(res.json()) == 0


def test_marketplace_resolver_and_templates(client, mock_sku_map_env):
    # Seed styles
    style_oid = ObjectId()
    mock_sku_map_env.styles_store[str(style_oid)] = {
        "_id": style_oid,
        "code": "CC-058",
        "name": "Casual Comfort",
        "active": True
    }

    # 1. Upsert Parser Template
    tmpl_payload = {
        "marketplace": "myntra",
        "template": "STYLE-COLOR-SIZE",
        "pattern": r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
        "active": True,
    }
    res = client.post("/api/marketplace/parser-templates", json=tmpl_payload)
    assert res.status_code == 200

    res = client.get("/api/marketplace/parser-templates")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 2. Upsert Style-Color Mapping
    map_payload = {
        "marketplace": "myntra",
        "marketplace_style_code": "CC-058",
        "marketplace_color_code": "BR",
        "erp_style_code": "CC-058",
        "erp_color_code": "Brown",
        "active": True,
    }
    res = client.post("/api/marketplace/style-color-mapping", json=map_payload)
    assert res.status_code == 200

    # 3. Parse SKU
    res = client.post("/api/marketplace/parse-sku", json={"marketplace": "myntra", "sku": "CC-058-BR-38"})
    assert res.status_code == 200
    parsed = res.json()
    assert parsed["resolved"] is True
    assert parsed["erp_style_code"] == "CC-058"
    assert parsed["erp_color_code"] == "Brown"
    assert parsed["erp_size"] == "38"

    # 4. Unresolved Queue & Map Replay
    mock_sku_map_env.unresolved_queue_store["CC-099-BK-40"] = {
        "_id": ObjectId(),
        "marketplace": "myntra",
        "raw_sku": "CC-099-BK-40",
        "marketplace_style_code": "CC-099",
        "marketplace_color_code": "BK",
        "status": "open",
        "occurrences": 1,
    }

    res = client.get("/api/marketplace/unresolved?marketplace=myntra")
    assert res.status_code == 200
    unresolved = res.json()
    assert len(unresolved) == 1

    # Create ERP style for CC-099
    style2_oid = ObjectId()
    mock_sku_map_env.styles_store[str(style2_oid)] = {
        "_id": style2_oid,
        "code": "CC-099",
        "name": "New Comfort"
    }

    # Map and replay unresolved
    replay_res = client.post("/api/marketplace/unresolved/map", json={
        "marketplace": "myntra",
        "marketplace_style_code": "CC-099",
        "marketplace_color_code": "BK",
        "erp_style_code": "CC-099",
        "erp_color_code": "Black"
    })
    assert replay_res.status_code == 200
    assert replay_res.json()["ok"] is True
    assert replay_res.json()["closed_queue_rows"] == 1


def test_myntra_listing_import_flow_end_to_end(client, mock_sku_map_env):
    """Specifically test the Myntra / marketplace listing import flow end-to-end."""
    # 1. Seed existing styles
    s1_oid = ObjectId()
    s1_id = str(s1_oid)
    mock_sku_map_env.styles_store[s1_id] = {
        "_id": s1_oid,
        "code": "SSK-MYN-01",
        "name": "Myntra Runner"
    }

    # 2. Stage 1: Upload and Parse Myntra listing CSV
    csv_content = (
        "myntra_style_id,style_name,color,size,sellerskucode,image_url\n"
        "MYN_ART_101,Runner Air,Tan,7,MYN-RN-TAN-7,https://sample.com/1.jpg\n"
        "MYN_ART_101,Runner Air,Tan,8,MYN-RN-TAN-8,https://sample.com/1.jpg\n"
        "MYN_ART_101,Runner Air,Tan,9,MYN-RN-TAN-9,https://sample.com/1.jpg\n"
        "MYN_ART_101,Runner Air,Black,8,MYN-RN-BLK-8,https://sample.com/2.jpg\n"
        "MYN_ART_202,Unknown Boot,Brown,8,MYN-BT-BRN-8,https://sample.com/3.jpg\n"
    )
    files = {"file": ("myntra_listings.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    parse_res = client.post(
        "/api/sku-map/listing-import/parse?platform=myntra&source_type=online_channel",
        files=files,
    )
    assert parse_res.status_code == 200, parse_res.text
    data = parse_res.json()
    session_id = data["session_id"]
    assert data["group_count"] == 3
    assert data["sku_count"] == 5

    # 3. Retrieve Session
    sess_res = client.get(f"/api/sku-map/listing-import/sessions/{session_id}")
    assert sess_res.status_code == 200
    assert sess_res.json()["session_id"] == session_id

    # 4. Stage 2: Commit linking decisions
    commit_payload = {
        "decisions": [
            {"group_key": "MYN_ART_101/tan", "style_id": s1_id},
            {"group_key": "MYN_ART_101/black", "style_id": s1_id},
            {"group_key": "MYN_ART_202/brown", "style_id": None},
        ]
    }
    commit_res = client.post(
        f"/api/sku-map/listing-import/sessions/{session_id}/commit",
        json=commit_payload
    )
    assert commit_res.status_code == 200, commit_res.text
    commit_data = commit_res.json()
    assert commit_data["linked"] == 2
    assert commit_data["unlinked"] == 1
    assert len(commit_data["errors"]) == 0

    # 5. Verify SKU Map records
    assert len(mock_sku_map_env.sku_map_store) == 3

    # Check query by needs_style_code
    unlinked_list_res = client.get("/api/sku-map?needs_style_code=true")
    assert unlinked_list_res.status_code == 200
    assert len(unlinked_list_res.json()) == 1
    assert unlinked_list_res.json()[0]["color"] == "Brown"
