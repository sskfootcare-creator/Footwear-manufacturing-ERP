"""Tests for SkuMap image_url field.

Verifies:
  - image_url is stored and normalized via normalize_image_url() on create
  - image_url is normalized on update
  - existing entries without image_url are unaffected (default "")
  - omitting image_url in PUT does NOT overwrite existing stored URL
"""
import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

import server
from server import app, normalize_image_url


# ── mock infrastructure ───────────────────────────────────────────────────────

class MockFindCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: d.get(key, "") or "", reverse=(direction == -1))
        return self

    async def to_list(self, limit=None):
        return self._docs[:limit] if limit else self._docs


def _match(doc, f):
    if not f:
        return True
    if "_id" in f and str(doc.get("_id")) != str(f["_id"]):
        return False
    for k, v in f.items():
        if k == "_id":
            continue
        val = doc.get(k)
        if isinstance(v, dict) and "$in" in v:
            if val not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$ne" in v:
            if val == v["$ne"]:
                return False
        elif val != v:
            return False
    return True


class MockCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, f=None, *a, **kw):
        matched = [d for d in self.docs if _match(d, f or {})]
        return matched[0] if matched else None

    def find(self, f=None, *a, **kw):
        return MockFindCursor([d for d in self.docs if _match(d, f or {})])

    async def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.docs.append(doc)
        class R:
            inserted_id = doc["_id"]
        return R()

    async def update_one(self, f, upd, upsert=False):
        for doc in self.docs:
            if _match(doc, f):
                if "$set" in upd:
                    doc.update(upd["$set"])
                return
        if upsert:
            new = {}
            if "$set" in upd:
                new.update(upd["$set"])
            new.update({k: v for k, v in f.items() if not k.startswith("$")})
            if "_id" not in new:
                new["_id"] = ObjectId()
            self.docs.append(new)

    async def delete_one(self, f):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, f)]
        class R:
            deleted_count = before - len(self.docs)
        return R()

    async def find_one_and_update(self, f, upd, upsert=False, return_document=True):
        for doc in self.docs:
            if _match(doc, f):
                if "$inc" in upd:
                    for k, v in upd["$inc"].items():
                        doc[k] = doc.get(k, 0) + v
                return doc
        if upsert:
            new = {"_id": f.get("_id", "seq")}
            if "$inc" in upd:
                for k, v in upd["$inc"].items():
                    new[k] = v
            self.docs.append(new)
            return new
        return None


class MockDB:
    def __init__(self):
        self.styles               = MockCollection()
        self.sku_map              = MockCollection()
        self.activity_log         = MockCollection()
        self.counters             = MockCollection()
        self.production_jobs      = MockCollection()
        self.unmatched_production_jobs = MockCollection()


@pytest.fixture
def mock_db(monkeypatch):
    mdb = MockDB()
    monkeypatch.setattr(server, "db", mdb)
    return mdb


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def mock_admin(monkeypatch):
    async def _user(request=None):
        return {"id": "u1", "email": "admin@test.com", "role": "admin", "roles": ["admin"]}
    monkeypatch.setattr(server, "get_current_user", _user)


# ── unit: normalize_image_url() ───────────────────────────────────────────────

def test_normalize_dropbox_share_link():
    raw = "https://www.dropbox.com/s/abc123/photo.jpg?dl=0"
    out = normalize_image_url(raw)
    assert "dl.dropboxusercontent.com" in out
    assert "dl=0" not in out


def test_normalize_google_drive_link():
    raw = "https://drive.google.com/file/d/FILE_ID_123/view?usp=sharing"
    out = normalize_image_url(raw)
    assert "uc?export=view" in out
    assert "FILE_ID_123" in out


def test_normalize_plain_url_passes_through():
    raw = "https://example.com/images/shoe.jpg"
    assert normalize_image_url(raw) == raw


def test_normalize_empty_string():
    assert normalize_image_url("") == ""


# ── integration: POST /api/sku-map ────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_sku_map_image_url_is_normalized(mock_db, mock_admin, async_client):
    """Dropbox share link in image_url must be rewritten to dl.dropboxusercontent.com."""
    style_id = ObjectId()
    await mock_db.styles.insert_one({"_id": style_id, "code": "STYLE-01", "name": "Test"})

    r = await async_client.post("/api/sku-map", json={
        "style_id": str(style_id),
        "source_type": "b2b_client",
        "source_name": "ClientA",
        "external_sku": "CA-001",
        "image_url": "https://www.dropbox.com/s/xyz789/shoe.jpg?dl=0",
    })
    assert r.status_code == 200, r.text
    data = r.json()

    assert "dl.dropboxusercontent.com" in data["image_url"], data["image_url"]
    assert "dl=0" not in data["image_url"]

    # Verify DB persistence
    stored = await mock_db.sku_map.find_one({})
    assert stored is not None
    assert "dl.dropboxusercontent.com" in stored["image_url"]


@pytest.mark.anyio
async def test_create_sku_map_without_image_url_defaults_empty(mock_db, mock_admin, async_client):
    """Omitting image_url on create stores \"\" — existing entries without image_url unaffected."""
    style_id = ObjectId()
    await mock_db.styles.insert_one({"_id": style_id, "code": "STYLE-02", "name": "NoImg"})

    r = await async_client.post("/api/sku-map", json={
        "style_id": str(style_id),
        "source_type": "b2b_client",
        "source_name": "ClientB",
        "external_sku": "CB-001",
        # image_url intentionally omitted
    })
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["image_url"] == ""
    stored = await mock_db.sku_map.find_one({})
    assert stored["image_url"] == ""


# ── integration: PUT /api/sku-map/{mid} ──────────────────────────────────────

@pytest.mark.anyio
async def test_update_sku_map_image_url_normalized(mock_db, mock_admin, async_client):
    """PUT with a Google Drive link normalizes it before storing."""
    style_id = ObjectId()
    await mock_db.styles.insert_one({"_id": style_id, "code": "STYLE-03"})

    entry_id = ObjectId()
    await mock_db.sku_map.insert_one({
        "_id": entry_id,
        "style_id": str(style_id),
        "style_code": "STYLE-03",
        "source_type": "b2b_client",
        "source_name": "ClientC",
        "source_name_key": "clientc",
        "external_sku": "CC-001",
        "external_sku_key": "cc-001",
        "image_url": "",
    })

    drive = "https://drive.google.com/file/d/DRIVEID999/view?usp=sharing"
    r = await async_client.put(f"/api/sku-map/{entry_id}", json={"image_url": drive})
    assert r.status_code == 200, r.text
    data = r.json()

    assert "uc?export=view" in data["image_url"]
    assert "DRIVEID999" in data["image_url"]


@pytest.mark.anyio
async def test_update_sku_map_omitting_image_url_leaves_existing_unchanged(mock_db, mock_admin, async_client):
    """PUT without image_url key must not overwrite the currently stored image_url."""
    style_id = ObjectId()
    await mock_db.styles.insert_one({"_id": style_id, "code": "STYLE-04"})

    entry_id = ObjectId()
    original_url = "https://dl.dropboxusercontent.com/s/existing/img.jpg"
    await mock_db.sku_map.insert_one({
        "_id": entry_id,
        "style_id": str(style_id),
        "style_code": "STYLE-04",
        "source_type": "b2b_client",
        "source_name": "ClientD",
        "source_name_key": "clientd",
        "external_sku": "CD-001",
        "external_sku_key": "cd-001",
        "image_url": original_url,
    })

    # Only update external_style_name — image_url NOT sent
    r = await async_client.put(f"/api/sku-map/{entry_id}", json={"external_style_name": "Updated Name"})
    assert r.status_code == 200, r.text

    after = await mock_db.sku_map.find_one({"_id": entry_id})
    assert after["image_url"] == original_url, (
        f"image_url was unexpectedly overwritten: {after['image_url']}"
    )
