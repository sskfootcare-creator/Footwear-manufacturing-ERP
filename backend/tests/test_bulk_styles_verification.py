import io
from collections import defaultdict
import pytest
import pandas as pd
from bson import ObjectId
from httpx import AsyncClient, ASGITransport

import server
from server import app, DEFAULT_PLM_FOLDERS


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
        else:
            if val != v:
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
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        class R:
            inserted_id = d["_id"]
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
        self._cols = defaultdict(MockCollection)

    def __getattr__(self, name):
        return self._cols[name]

    def __getitem__(self, name):
        return self._cols[name]


@pytest.mark.anyio
async def test_bulk_styles_verification_suite(monkeypatch):
    mock_db = MockDB()
    monkeypatch.setattr(server, "db", mock_db)

    # Bypass auth and rate limiters
    async def mock_current_user(*args, **kwargs):
        return {"email": "admin@sskfootcare.com", "role": "admin", "roles": ["admin"]}
    monkeypatch.setattr(server, "get_current_user", mock_current_user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        
        # -------------------------------------------------------------
        # 1. Upload Excel with 5 styles & Preview
        # -------------------------------------------------------------
        excel_rows = [
            {"Name": "Style Alpha", "Category": "Footwear", "Insole Mould Name": "IN-01", "Sole Mould Name": "SO-01", "Default Pairs Per Carton": 12, "Base Size": "7", "Overhead %": 10, "Packing Cost": 15, "Margin %": 20, "GST %": 5},
            {"Name": "Style Beta", "Category": "Footwear", "Insole Mould Name": "IN-02", "Sole Mould Name": "SO-02", "Default Pairs Per Carton": 24, "Base Size": "8", "Overhead %": 12, "Packing Cost": 18, "Margin %": 22, "GST %": 5},
            {"Name": "Style Gamma", "Category": "Footwear", "Insole Mould Name": "IN-03", "Sole Mould Name": "SO-03", "Default Pairs Per Carton": 12, "Base Size": "9", "Overhead %": 10, "Packing Cost": 15, "Margin %": 25, "GST %": 5},
            {"Name": "Style Delta", "Category": "Footwear", "Insole Mould Name": "IN-04", "Sole Mould Name": "SO-04", "Default Pairs Per Carton": 36, "Base Size": "7", "Overhead %": 8, "Packing Cost": 10, "Margin %": 30, "GST %": 5},
            {"Name": "Style Epsilon", "Category": "Footwear", "Insole Mould Name": "IN-05", "Sole Mould Name": "SO-05", "Default Pairs Per Carton": 12, "Base Size": "6", "Overhead %": 15, "Packing Cost": 20, "Margin %": 25, "GST %": 5},
        ]
        df = pd.DataFrame(excel_rows)
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        out.seek(0)

        preview_resp = await client.post(
            "/api/styles/bulk/preview",
            files={"file": ("test_5_styles.xlsx", out.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        )
        assert preview_resp.status_code == 200, f"Preview failed: {preview_resp.text}"
        pdata = preview_resp.json()
        assert pdata["total_rows"] == 5
        assert pdata["valid_rows"] == 5
        assert len(pdata["errors"]) == 0
        assert len(pdata["preview"]) == 5

        # Check insole/sole mould and default_pairs_per_carton parsed
        first_p = pdata["preview"][0]
        assert first_p["insole_mould_name"] == "IN-01"
        assert first_p["sole_mould_name"] == "SO-01"
        assert first_p["default_pairs_per_carton"] == {"default": 12}
        assert first_p["row_number"] == 2

        # -------------------------------------------------------------
        # 2. Upload to /styles/bulk → all 5 get SSK_XXXXX codes
        # -------------------------------------------------------------
        bulk_resp = await client.post(
            "/api/styles/bulk",
            json={"styles": pdata["preview"]}
        )
        assert bulk_resp.status_code == 200, f"Bulk upload failed: {bulk_resp.text}"
        bdata = bulk_resp.json()
        assert bdata["ok"] is True
        assert bdata["success_count"] == 5
        assert len(bdata["errors"]) == 0
        assert len(bdata["created"]) == 5

        # Check all get SSK_XXXXX codes
        for item in bdata["created"]:
            assert item["code"].startswith("SSK_")
            assert len(item["code"]) == 9  # e.g. SSK_00001
            assert item["costing"] is not None

        # Check MongoDB styles
        styles_in_db = await mock_db.styles.find().to_list()
        assert len(styles_in_db) == 5

        # -------------------------------------------------------------
        # 3. Check MongoDB: each style has style_folders document with 23 folders
        # -------------------------------------------------------------
        folders_in_db = await mock_db.style_folders.find().to_list()
        assert len(folders_in_db) == 5
        for folder_doc in folders_in_db:
            assert len(folder_doc["folders"]) == 23
            assert folder_doc["folders"] == DEFAULT_PLM_FOLDERS

        # -------------------------------------------------------------
        # 4. Check MongoDB: each style has costing field computed
        # -------------------------------------------------------------
        for style_doc in styles_in_db:
            assert style_doc["status"] == "inactive"
            assert style_doc["insole_mould_name"] in ["IN-01", "IN-02", "IN-03", "IN-04", "IN-05"]
            assert style_doc["sole_mould_name"] in ["SO-01", "SO-02", "SO-03", "SO-04", "SO-05"]

        # -------------------------------------------------------------
        # 5. Check activity log: style.create entries + BULK_CREATE summary
        # -------------------------------------------------------------
        activity_logs = await mock_db.audit_logs.find().to_list()
        style_create_logs = [a for a in activity_logs if a.get("action") == "style.create"]
        bulk_create_logs = [a for a in activity_logs if a.get("action") == "BULK_CREATE"]
        assert len(style_create_logs) == 5
        assert len(bulk_create_logs) == 1
        assert "Bulk import: 5 created, 0 errors" in bulk_create_logs[0]["details"]

        # -------------------------------------------------------------
        # 6. Upload with missing Name → error shows correct row number, other rows still process
        # -------------------------------------------------------------
        mixed_rows = [
            {"Name": "Valid Style 1", "Category": "Footwear", "Insole Mould Name": "IN-M1", "Sole Mould Name": "SO-M1", "Default Pairs Per Carton": 12},
            {"Name": "", "Category": "Footwear"},  # Row 3 (Excel indexing: 1-header, 2-first row, 3-second row)
            {"Name": "Valid Style 2", "Category": "Footwear"},
        ]
        df_mixed = pd.DataFrame(mixed_rows)
        out_mixed = io.BytesIO()
        with pd.ExcelWriter(out_mixed, engine='openpyxl') as writer:
            df_mixed.to_excel(writer, index=False)
        out_mixed.seek(0)

        preview_mixed = await client.post(
            "/api/styles/bulk/preview",
            files={"file": ("mixed.xlsx", out_mixed.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        )
        assert preview_mixed.status_code == 200
        p_mixed = preview_mixed.json()
        assert p_mixed["total_rows"] == 3
        assert p_mixed["valid_rows"] == 2
        assert any("Row 3: Missing Name" in err for err in p_mixed["errors"])

        # Also test submitting directly to /styles/bulk with missing Name
        bulk_mixed_resp = await client.post(
            "/api/styles/bulk",
            json={"styles": [
                {"row_number": 2, "name": "Row 2 Style"},
                {"row_number": 3, "name": ""},
                {"row_number": 4, "name": "Row 4 Style"},
            ]}
        )
        assert bulk_mixed_resp.status_code == 200
        bm_data = bulk_mixed_resp.json()
        assert bm_data["success_count"] == 2
        assert len(bm_data["errors"]) == 1
        assert "Row 3: Missing Name" in bm_data["errors"][0]
        assert len(bm_data["created"]) == 2

        # -------------------------------------------------------------
        # 7. Normal single create still works unchanged
        # -------------------------------------------------------------
        single_create_resp = await client.post(
            "/api/styles",
            json={
                "name": "Single Oxford Shoe",
                "category": "Footwear",
                "description": "Handcrafted oxford",
                "base_size": "8",
                "insole_mould_name": "IN-SINGLE",
                "sole_mould_name": "SO-SINGLE",
                "overhead_pct": 10,
                "packing_cost": 15,
                "margin_pct": 25,
                "gst_pct": 5,
                "default_pairs_per_carton": {"default": 12},
                "bom": [],
                "labor": [{"name": "Cutting", "rate": 20}]
            }
        )
        assert single_create_resp.status_code == 200, f"Single create failed: {single_create_resp.text}"
        single_data = single_create_resp.json()
        assert single_data["name"] == "Single Oxford Shoe"
        assert single_data["code"].startswith("SSK_")
        assert single_data["insole_mould_name"] == "IN-SINGLE"
        assert single_data["sole_mould_name"] == "SO-SINGLE"
        assert single_data["default_pairs_per_carton"] == {"default": 12}
        assert single_data["costing"] is not None
