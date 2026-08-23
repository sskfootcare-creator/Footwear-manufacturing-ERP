"""Verification tests for Listing Import (Stage 1 parse & Stage 2 link).

Test scenarios:
  1. Stage 1 XLSX / CSV parse:
     - auto-detects columns (style name/code, color, size, SKU, ID, image)
     - groups SKUs by (base_key + color)
     - identifies sibling colors belonging to the same style base
     - stores session in db.listing_import_sessions
  2. Sessions listing & get:
     - GET /api/sku-map/listing-import/sessions
     - GET /api/sku-map/listing-import/sessions/{session_id}
  3. Stage 2 commit:
     - linked group (with style_id) creates/updates db.sku_map with needs_style_code=False
     - unlinked group (style_id=None) creates/updates db.sku_map with needs_style_code=True
     - re-commit on already-committed session returns 409
     - non-existent session returns 404
     - non-existent style_id records error in errors list
"""
import io
import csv
import pytest
import openpyxl
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

import server
from server import app


class MockFindCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **kw):
        return self

    async def to_list(self, limit=None):
        return self._docs[:limit] if limit else list(self._docs)


def _match(doc, f):
    if not f:
        return True
    for k, v in f.items():
        if k == "_id":
            if str(doc.get("_id")) != str(v):
                return False
            continue
        val = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v and val not in v["$in"]:
                return False
            if "$ne" in v and val == v["$ne"]:
                return False
            if "$regex" in v:
                import re as _re
                flags = _re.IGNORECASE if v.get("$options") == "i" else 0
                if not _re.search(v["$regex"], str(val or ""), flags):
                    return False
        else:
            if val != v:
                return False
    return True


class MockCollection:
    def __init__(self):
        self.docs: list = []

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


class MockDB:
    def __init__(self):
        self.styles                 = MockCollection()
        self.sku_map                = MockCollection()
        self.listing_import_sessions = MockCollection()
        self.activity_log           = MockCollection()
        self.counters               = MockCollection()


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


def _make_csv(rows, fieldnames):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


@pytest.mark.anyio
async def test_listing_import_stage1_and_stage2_flow(mock_db, mock_admin, async_client):
    # 1. Seed styles
    style_id_a = ObjectId()
    await mock_db.styles.insert_one({
        "_id": style_id_a,
        "code": "SSK-OXF-01",
        "name": "Classic Oxford Shoes",
    })

    # 2. Stage 1 - Parse CSV
    listing_rows = [
        {"Style Name": "Classic Oxford", "Color": "Tan",   "Size": "7 UK", "SKU Code": "MYN-OXF-T-7", "Myntra Style ID": "1001"},
        {"Style Name": "Classic Oxford", "Color": "Tan",   "Size": "8 UK", "SKU Code": "MYN-OXF-T-8", "Myntra Style ID": "1001"},
        {"Style Name": "Classic Oxford", "Color": "Black", "Size": "7 UK", "SKU Code": "MYN-OXF-B-7", "Myntra Style ID": "1002"},
        {"Style Name": "Classic Oxford", "Color": "Black", "Size": "8 UK", "SKU Code": "MYN-OXF-B-8", "Myntra Style ID": "1002"},
    ]
    csv_bytes = _make_csv(listing_rows, ["Style Name", "Color", "Size", "SKU Code", "Myntra Style ID"])

    res1 = await async_client.post(
        "/api/sku-map/listing-import/parse?platform=myntra",
        files={"file": ("myntra_listing.csv", csv_bytes, "text/csv")},
    )
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert "session_id" in data1
    assert data1["group_count"] == 2
    assert data1["sku_count"] == 4

    session_id = data1["session_id"]
    groups = data1["groups"]

    tan_group = next(g for g in groups if "tan" in g["color_label"].lower())
    black_group = next(g for g in groups if "black" in g["color_label"].lower())

    assert len(tan_group["size_sku_map"]) == 2
    assert tan_group["size_sku_map"]["7 UK"] == "MYN-OXF-T-7"
    assert tan_group["external_style_id"] == "1001"
    assert black_group["external_style_id"] == "1002"

    # Sibling links should exist between tan and black
    assert len(tan_group["sibling_group_keys"]) == 1

    # 3. Check session endpoints
    res_list = await async_client.get("/api/sku-map/listing-import/sessions")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    res_get = await async_client.get(f"/api/sku-map/listing-import/sessions/{session_id}")
    assert res_get.status_code == 200
    assert res_get.json()["session_id"] == session_id

    # 4. Stage 2 - Commit (link Tan to SSK-OXF-01, Black left unlinked)
    commit_body = {
        "decisions": [
            {"group_key": tan_group["group_key"], "style_id": str(style_id_a)},
            {"group_key": black_group["group_key"], "style_id": None},
        ]
    }
    res2 = await async_client.post(
        f"/api/sku-map/listing-import/sessions/{session_id}/commit",
        json=commit_body,
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2["linked"] == 1
    assert data2["unlinked"] == 1
    assert data2["errors"] == []

    # 5. Check db.sku_map
    sku_docs = mock_db.sku_map.docs
    assert len(sku_docs) == 2

    tan_doc = next(d for d in sku_docs if d["color_key"] == "tan")
    assert tan_doc["style_id"] == str(style_id_a)
    assert tan_doc["style_code"] == "SSK-OXF-01"
    assert tan_doc["needs_style_code"] is False
    assert tan_doc["size_map"]["7 UK"] == "MYN-OXF-T-7"
    assert tan_doc["external_style_id"] == "1001"

    black_doc = next(d for d in sku_docs if d["color_key"] == "black")
    assert black_doc.get("style_id") is None
    assert black_doc["needs_style_code"] is True
    assert black_doc["size_map"]["8 UK"] == "MYN-OXF-B-8"
    assert black_doc["external_style_id"] == "1002"

    # 6. Re-commit should return 409
    res_recommit = await async_client.post(
        f"/api/sku-map/listing-import/sessions/{session_id}/commit",
        json=commit_body,
    )
    assert res_recommit.status_code == 409


@pytest.mark.anyio
async def test_listing_import_errors_and_edge_cases(mock_db, mock_admin, async_client):
    # Session not found
    res = await async_client.get("/api/sku-map/listing-import/sessions/invalid-id")
    assert res.status_code == 404

    # Stage 2 on non-existent session
    res_commit = await async_client.post(
        "/api/sku-map/listing-import/sessions/invalid-id/commit",
        json={"decisions": []},
    )
    assert res_commit.status_code == 404

    # Stage 1 with empty file
    res_empty = await async_client.post(
        "/api/sku-map/listing-import/parse?platform=myntra",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert res_empty.status_code == 400


@pytest.mark.anyio
async def test_myntra_real_listing_style_id_and_sellerskucode(mock_db, mock_admin, async_client):
    """Verify that Myntra Style Id (e.g. 39006863) and per-size SellerSkuCode (e.g. CC-069-BR-37)
    are strictly separated and never conflated."""
    style_id = ObjectId()
    await mock_db.styles.insert_one({
        "_id": style_id,
        "code": "CC-069",
        "name": "Classic Loafer",
    })

    # Real Myntra style listing format
    myntra_rows = [
        {"Style Id": "39006863", "Primary Color": "BROWN", "Standard Size": "37", "SellerSkuCode": "CC-069-BR-37", "Article Type": "Casual Shoes"},
        {"Style Id": "39006863", "Primary Color": "BROWN", "Standard Size": "38", "SellerSkuCode": "CC-069-BR-38", "Article Type": "Casual Shoes"},
        {"Style Id": "39006863", "Primary Color": "BROWN", "Standard Size": "39", "SellerSkuCode": "CC-069-BR-39", "Article Type": "Casual Shoes"},
        {"Style Id": "39006863", "Primary Color": "BROWN", "Standard Size": "40", "SellerSkuCode": "CC-069-BR-40", "Article Type": "Casual Shoes"},
        {"Style Id": "39006863", "Primary Color": "BROWN", "Standard Size": "41", "SellerSkuCode": "CC-069-BR-41", "Article Type": "Casual Shoes"},
    ]
    csv_bytes = _make_csv(myntra_rows, ["Style Id", "Primary Color", "Standard Size", "SellerSkuCode", "Article Type"])

    res = await async_client.post(
        "/api/sku-map/listing-import/parse?platform=myntra",
        files={"file": ("myntra_catalog.csv", csv_bytes, "text/csv")},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["group_count"] == 1
    assert data["sku_count"] == 5

    group = data["groups"][0]
    # Style ID correctly identifies the style+color group as a whole
    assert group["external_style_id"] == "39006863"
    assert group["color_label"].upper() == "BROWN"
    assert group["sku_count"] == 5

    # Size SKU map contains REAL per-size SellerSkuCode values, NOT the style ID
    size_map = group["size_sku_map"]
    assert len(size_map) == 5
    assert size_map["37"] == "CC-069-BR-37"
    assert size_map["38"] == "CC-069-BR-38"
    assert size_map["39"] == "CC-069-BR-39"
    assert size_map["40"] == "CC-069-BR-40"
    assert size_map["41"] == "CC-069-BR-41"

    # Commit the group
    commit_res = await async_client.post(
        f"/api/sku-map/listing-import/sessions/{data['session_id']}/commit",
        json={"decisions": [{"group_key": group["group_key"], "style_id": str(style_id)}]},
    )
    assert commit_res.status_code == 200, commit_res.text

    # Verify db.sku_map document
    saved_doc = mock_db.sku_map.docs[0]
    assert saved_doc["external_style_id"] == "39006863"
    assert saved_doc["external_sku"] == "CC-069-BR-37"
    assert saved_doc["size_map"]["37"] == "CC-069-BR-37"
    assert saved_doc["size_map"]["38"] == "CC-069-BR-38"
    assert saved_doc["size_map"]["39"] == "CC-069-BR-39"
    assert saved_doc["size_map"]["40"] == "CC-069-BR-40"
    assert saved_doc["size_map"]["41"] == "CC-069-BR-41"
    # Ensure style id is not duplicated as size sku or external_sku
    assert saved_doc["external_sku"] != "39006863"
    for size, sku in saved_doc["size_map"].items():
        assert sku != "39006863"
        assert sku.startswith("CC-069-BR-")


@pytest.mark.anyio
async def test_myntra_listing_embedded_size_and_product_id_column(mock_db, mock_admin, async_client):
    """Verify that if Size column is absent/blank and 'Product ID' is present alongside 'SellerSkuCode',
    sizes are correctly derived from SellerSkuCode and Product ID does not overwrite SellerSkuCode."""
    style_id = ObjectId()
    await mock_db.styles.insert_one({
        "_id": style_id,
        "code": "FL-045",
        "name": "Flat Sandal",
    })

    # Rows with Product ID (=39007788) and SellerSkuCode with embedded sizes, no Size column
    myntra_rows = [
        {"Product ID": "39007788", "Colour": "TAN", "SellerSkuCode": "FL-045-TN-6"},
        {"Product ID": "39007788", "Colour": "TAN", "SellerSkuCode": "FL-045-TN-7"},
        {"Product ID": "39007788", "Colour": "TAN", "SellerSkuCode": "FL-045-TN-8"},
    ]
    csv_bytes = _make_csv(myntra_rows, ["Product ID", "Colour", "SellerSkuCode"])

    res = await async_client.post(
        "/api/sku-map/listing-import/parse?platform=myntra",
        files={"file": ("myntra_export.csv", csv_bytes, "text/csv")},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["group_count"] == 1
    assert data["sku_count"] == 3

    group = data["groups"][0]
    assert group["external_style_id"] == "39007788"
    assert group["color_label"].upper() == "TAN"

    # Verify size_sku_map derived size tokens 6, 7, 8
    size_map = group["size_sku_map"]
    assert len(size_map) == 3
    assert size_map["6"] == "FL-045-TN-6"
    assert size_map["7"] == "FL-045-TN-7"
    assert size_map["8"] == "FL-045-TN-8"

    # Commit the group
    commit_res = await async_client.post(
        f"/api/sku-map/listing-import/sessions/{data['session_id']}/commit",
        json={"decisions": [{"group_key": group["group_key"], "style_id": str(style_id)}]},
    )
    assert commit_res.status_code == 200, commit_res.text

    saved_doc = mock_db.sku_map.docs[0]
    assert saved_doc["external_style_id"] == "39007788"
    assert saved_doc["external_sku"] == "FL-045-TN-6"
    assert saved_doc["size_map"]["6"] == "FL-045-TN-6"
    assert saved_doc["size_map"]["7"] == "FL-045-TN-7"
    assert saved_doc["size_map"]["8"] == "FL-045-TN-8"
    for size, sku in saved_doc["size_map"].items():
        assert sku != "39007788"
        assert sku.startswith("FL-045-TN-")


@pytest.mark.anyio
async def test_myntra_real_xlsx_end_to_end_flow(mock_db, mock_admin, async_client):
    """End-to-end verification of a real multi-row Myntra styledashboard .xlsx export:
    Parse → Preview validation → Link groups to styles → Commit → Spot-check db.sku_map documents."""
    style1_id = ObjectId()
    style2_id = ObjectId()
    await mock_db.styles.insert_one({"_id": style1_id, "code": "CC-069", "name": "Classic Loafer"})
    await mock_db.styles.insert_one({"_id": style2_id, "code": "SSK-501", "name": "Urban Sneaker"})

    # Create a real multi-style Myntra .xlsx workbook in-memory
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "styledashboard"

    headers = [
        "Style Id", "SellerSkuCode", "Style Name", "Brand", "Category",
        "Colour", "Standard Size", "MRP", "Selling Price", "Listing Status"
    ]
    ws.append(headers)

    # Style 39006863: Brown loafer, sizes 37..41
    myntra_loafer_rows = [
        ("39006863", "CC-069-BR-37", "Classic Loafer Brown", "SSK", "Footwear", "Brown", "37", 2499, 1799, "Active"),
        ("39006863", "CC-069-BR-38", "Classic Loafer Brown", "SSK", "Footwear", "Brown", "38", 2499, 1799, "Active"),
        ("39006863", "CC-069-BR-39", "Classic Loafer Brown", "SSK", "Footwear", "Brown", "39", 2499, 1799, "Active"),
        ("39006863", "CC-069-BR-40", "Classic Loafer Brown", "SSK", "Footwear", "Brown", "40", 2499, 1799, "Active"),
        ("39006863", "CC-069-BR-41", "Classic Loafer Brown", "SSK", "Footwear", "Brown", "41", 2499, 1799, "Active"),
    ]
    # Style 39006864: White sneaker, sizes 6..9
    myntra_sneaker_rows = [
        ("39006864", "SSK-501-WH-6", "Urban Sneaker White", "SSK", "Footwear", "White", "6", 3299, 2199, "Active"),
        ("39006864", "SSK-501-WH-7", "Urban Sneaker White", "SSK", "Footwear", "White", "7", 3299, 2199, "Active"),
        ("39006864", "SSK-501-WH-8", "Urban Sneaker White", "SSK", "Footwear", "White", "8", 3299, 2199, "Active"),
        ("39006864", "SSK-501-WH-9", "Urban Sneaker White", "SSK", "Footwear", "White", "9", 3299, 2199, "Active"),
    ]
    for r in myntra_loafer_rows + myntra_sneaker_rows:
        ws.append(list(r))

    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)
    xlsx_bytes = xlsx_buf.getvalue()

    # 1. Preview / Parse Stage 1
    res = await async_client.post(
        "/api/sku-map/listing-import/parse?platform=myntra",
        files={"file": ("Myntra_Catalog_Export.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["group_count"] == 2
    assert data["sku_count"] == 9

    groups = data["groups"]
    loafer_group = next(g for g in groups if g["external_style_id"] == "39006863")
    sneaker_group = next(g for g in groups if g["external_style_id"] == "39006864")

    # Validate Stage 1 parse fields on Loafer group
    assert loafer_group["external_style_id"] == "39006863"
    assert loafer_group["external_style_name"] == "Classic Loafer Brown"
    assert loafer_group["color_label"].casefold() == "brown"
    assert loafer_group["sku_count"] == 5
    assert loafer_group["size_sku_map"] == {
        "37": "CC-069-BR-37",
        "38": "CC-069-BR-38",
        "39": "CC-069-BR-39",
        "40": "CC-069-BR-40",
        "41": "CC-069-BR-41",
    }
    assert loafer_group["sample_skus"] == [
        "CC-069-BR-37", "CC-069-BR-38", "CC-069-BR-39", "CC-069-BR-40", "CC-069-BR-41"
    ]

    # Validate Stage 1 parse fields on Sneaker group
    assert sneaker_group["external_style_id"] == "39006864"
    assert sneaker_group["external_style_name"] == "Urban Sneaker White"
    assert sneaker_group["color_label"].casefold() == "white"
    assert sneaker_group["sku_count"] == 4
    assert sneaker_group["size_sku_map"] == {
        "6": "SSK-501-WH-6",
        "7": "SSK-501-WH-7",
        "8": "SSK-501-WH-8",
        "9": "SSK-501-WH-9",
    }

    # 2. Stage 2 Link & Commit
    commit_payload = {
        "decisions": [
            {"group_key": loafer_group["group_key"], "style_id": str(style1_id)},
            {"group_key": sneaker_group["group_key"], "style_id": str(style2_id)},
        ]
    }
    commit_res = await async_client.post(
        f"/api/sku-map/listing-import/sessions/{data['session_id']}/commit",
        json=commit_payload,
    )
    assert commit_res.status_code == 200, commit_res.text
    commit_data = commit_res.json()
    assert commit_data["linked"] == 2
    assert commit_data["unlinked"] == 0
    assert commit_data["errors"] == []

    # 3. Direct inspection of resulting db.sku_map documents
    saved_docs = mock_db.sku_map.docs
    assert len(saved_docs) == 2

    # Spot-check Loafer document in db.sku_map
    saved_loafer = next(d for d in saved_docs if d["external_style_id"] == "39006863")
    assert saved_loafer["style_id"] == str(style1_id)
    assert saved_loafer["style_code"] == "CC-069"
    assert saved_loafer["source_name"] == "myntra"
    assert saved_loafer["source_type"] == "online_channel"
    assert saved_loafer["external_style_id"] == "39006863"
    assert saved_loafer["external_style_name"] == "Classic Loafer Brown"
    assert saved_loafer["external_sku"] == "CC-069-BR-37"
    assert saved_loafer["needs_style_code"] is False

    # Spot-check every size's real SKU code against uploaded file rows
    expected_loafer_size_map = {
        "37": "CC-069-BR-37",
        "38": "CC-069-BR-38",
        "39": "CC-069-BR-39",
        "40": "CC-069-BR-40",
        "41": "CC-069-BR-41",
    }
    assert saved_loafer["size_map"] == expected_loafer_size_map
    for size, expected_sku in expected_loafer_size_map.items():
        assert saved_loafer["size_map"][size] == expected_sku
        assert saved_loafer["size_map"][size] != "39006863"

    # Spot-check Sneaker document in db.sku_map
    saved_sneaker = next(d for d in saved_docs if d["external_style_id"] == "39006864")
    assert saved_sneaker["style_id"] == str(style2_id)
    assert saved_sneaker["style_code"] == "SSK-501"
    assert saved_sneaker["external_style_id"] == "39006864"
    assert saved_sneaker["external_sku"] == "SSK-501-WH-6"

    expected_sneaker_size_map = {
        "6": "SSK-501-WH-6",
        "7": "SSK-501-WH-7",
        "8": "SSK-501-WH-8",
        "9": "SSK-501-WH-9",
    }
    assert saved_sneaker["size_map"] == expected_sneaker_size_map
    for size, expected_sku in expected_sneaker_size_map.items():
        assert saved_sneaker["size_map"][size] == expected_sku
        assert saved_sneaker["size_map"][size] != "39006864"


