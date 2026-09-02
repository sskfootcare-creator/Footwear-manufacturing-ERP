import io
import json
import re
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from bson import ObjectId

from routes.po_ean import po_ean_router, _seed_po_ean_format_configs
from models.sku_map import SheetLocator, HeaderLocator
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
            if isinstance(v, dict) and "$in" in v:
                doc_val = doc.get(k)
                if str(doc_val) not in [str(x) for x in v["$in"]]:
                    return False
            elif k == "_id":
                if str(doc.get("_id")) != str(v):
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
            elif str(doc.get(k) or "").strip().lower() != str(v or "").strip().lower():
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

    async def insert_many(self, docs):
        res = MagicMock()
        res.inserted_ids = []
        for d in docs:
            r = await self.insert_one(d)
            res.inserted_ids.append(r.inserted_id)
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
        self.production_jobs = GenericMockCollection()
        self.packing_cartons = GenericMockCollection()
        self.sku_ean_codes = GenericMockCollection()
        self.settings = GenericMockCollection()
        self.stock = GenericMockCollection()


@pytest.fixture
def client_app():
    fake_db = FakeDB()
    app = FastAPI()
    app.mongodb = fake_db
    app.include_router(po_ean_router)
    from routes.invoice_packing import invoice_packing_router
    app.include_router(invoice_packing_router)

    async def override_user(request=None):
        return {"email": "admin@example.com", "role": "admin"}

    app.state.get_current_user = override_user

    async def get_mock_factory(db=None):
        return override_user

    auth.get_current_user_factory = get_mock_factory
    import routes.po_ean
    routes.po_ean.get_current_user_factory = get_mock_factory
    import routes.invoice_packing
    routes.invoice_packing.get_current_user_factory = get_mock_factory

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


def test_po_ean_import_no_column_map_error(client_app):
    client, db, _ = client_app

    # Create a PO with a client that does NOT match any saved format config
    unmapped_po_oid = ObjectId("654321654321654321654322")
    unmapped_po_doc = {
        "_id": unmapped_po_oid,
        "po_number": "PO-UNMAPPED-999",
        "client_name": "NonExistentClient Brand",
        "client": "NonExistentClient",
        "line_items": [
            {"style_code": "ART-ALPHA", "color": "Black", "size": "7", "quantity": 100},
        ],
    }
    db.pos.store[str(unmapped_po_oid)] = unmapped_po_doc

    csv_content = (
        "UnknownCol1,UnknownCol2,UnknownCol3\n"
        "ART-ALPHA,7,8901000000001\n"
    ).encode("utf-8")

    files = {
        "file": ("unmapped_barcodes.csv", csv_content, "text/csv"),
    }
    data = {
        "overwrite_existing": "false",
    }

    # Attempt import with no config_id, config_json, or matching client format config
    r = client.post(f"/api/pos/{str(unmapped_po_oid)}/ean-codes/import", files=files, data=data)
    assert r.status_code == 400
    assert "No column mapping found for this file/client. Please map the columns before importing." in r.json()["detail"]


def test_po_ean_preview_headers(client_app):
    client, db, po_id = client_app

    csv_content = (
        "Style,Colour,Size,Barcode,MRP,Notes\n"
        "ZC-100,Black,7,8905555000001,1499,Sample Note\n"
        "ZC-100,Black,8,8905555000002,1499,Sample Note\n"
    ).encode("utf-8")

    files = {
        "file": ("zecode_barcodes.csv", csv_content, "text/csv"),
    }

    # Call preview headers endpoint scoped to PO
    r = client.post(f"/api/pos/{po_id}/ean-codes/preview-headers", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["headers"] == ["Style", "Colour", "Size", "Barcode", "MRP", "Notes"]
    assert len(data["sample_rows"]) == 2
    assert data["sample_rows"][0]["Style"] == "ZC-100"

    # Check suggested column map heuristically matches Style, Colour, Size, Barcode
    sug = data["suggested_column_map"]
    assert sug["style_code"] == "Style"
    assert sug["color"] == "Colour"
    assert sug["size"] == "Size"
    assert sug["ean_code"] == "Barcode"


def test_po_ean_create_custom_format_and_reuse_flow(client_app):
    client, db, _ = client_app

    # 1. Setup PO 1 for client "Zecode"
    po1_oid = ObjectId("654321654321654321654330")
    po1_doc = {
        "_id": po1_oid,
        "po_number": "PO-ZC-001",
        "client_name": "Zecode Shoes",
        "client": "Zecode",
        "line_items": [
            {"style_code": "ZC-101", "color": "Tan", "size": "7", "quantity": 100},
            {"style_code": "ZC-101", "color": "Tan", "size": "8", "quantity": 120},
        ],
    }
    db.pos.store[str(po1_oid)] = po1_doc

    # 2. Setup PO 2 for client "Zecode"
    po2_oid = ObjectId("654321654321654321654331")
    po2_doc = {
        "_id": po2_oid,
        "po_number": "PO-ZC-002",
        "client_name": "Zecode Shoes",
        "client": "Zecode",
        "line_items": [
            {"style_code": "ZC-202", "color": "Navy", "size": "9", "quantity": 80},
        ],
    }
    db.pos.store[str(po2_oid)] = po2_doc

    # 3. Create a new custom format "Zecode Standard" with client_name="Zecode Shoes"
    config_payload = {
        "name": "Zecode Standard",
        "client_name": "Zecode Shoes",
        "column_map": {
            "style_code": "Style",
            "color": "Colour",
            "size": "Size",
            "ean_code": "Barcode",
        },
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "active": True,
    }
    r_create = client.post("/api/po-ean-formats", json=config_payload)
    assert r_create.status_code == 200
    cfg_id = r_create.json()["id"]
    assert cfg_id

    # 4. Import for PO 1 using the newly-created config_id
    csv1 = (
        "Style,Colour,Size,Barcode\n"
        "ZC-101,Tan,7,8908888000001\n"
        "ZC-101,Tan,8,8908888000002\n"
    ).encode("utf-8")
    files1 = {"file": ("zecode_po1.csv", csv1, "text/csv")}
    r_imp1 = client.post(
        f"/api/pos/{str(po1_oid)}/ean-codes/import",
        files=files1,
        data={"config_id": cfg_id, "overwrite_existing": "false"},
    )
    assert r_imp1.status_code == 200
    assert r_imp1.json()["imported"] == 2

    # 5. Import for PO 2 (SECOND FILE, same client) with NO config_id or config_json passed!
    # Confirms client-name lookup auto-resolves the saved config!
    csv2 = (
        "Style,Colour,Size,Barcode\n"
        "ZC-202,Navy,9,8908888000003\n"
    ).encode("utf-8")
    files2 = {"file": ("zecode_po2.csv", csv2, "text/csv")}
    r_imp2 = client.post(
        f"/api/pos/{str(po2_oid)}/ean-codes/import",
        files=files2,
        data={"overwrite_existing": "false"},
    )
    assert r_imp2.status_code == 200
    assert r_imp2.json()["imported"] == 1
    assert r_imp2.json()["unmatched_count"] == 0


def test_po_ean_formula_cells_evaluation(client_app):
    """
    Verify that formula-containing cells in Excel files return their computed values
    (via openpyxl data_only=True) rather than literal formula strings like '=F12*2'.
    """
    import zipfile
    import xml.etree.ElementTree as ET
    from routes.online_orders import _parse_tabular_bytes

    client, db, po_id = client_app
    import openpyxl

    # 1. Build an openpyxl workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Barcodes"
    ws.append(["Style Code", "Color", "Size", "EAN Code", "Net Qty"])
    # Row 1: Regular values
    ws.append(["ART-ALPHA", "Black", 7, "8901000000001", "=F2*2"])

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    # 2. Inject cached value <v> for the formula cell in sheet1.xml to simulate Excel's saved calculated output
    # Openpyxl writes <c r="E2" t="str"><f>=F2*2</f></c>. We add <v>100</v> to simulate an evaluated workbook.
    in_zip = zipfile.ZipFile(bio, "r")
    out_bio = io.BytesIO()
    out_zip = zipfile.ZipFile(out_bio, "w", zipfile.ZIP_DEFLATED)

    for item in in_zip.infolist():
        data = in_zip.read(item.filename)
        if item.filename == "xl/worksheets/sheet1.xml":
            xml_str = data.decode("utf-8")
            # Replace the cell definition for E2 to include cached value <v>100</v>
            xml_str = re.sub(r'<c r="E2"[^>]*>.*?<\/c>', '<c r="E2"><f>F2*2</f><v>100</v></c>', xml_str)
            data = xml_str.encode("utf-8")
        out_zip.writestr(item, data)

    in_zip.close()
    out_zip.close()
    xlsx_content = out_bio.getvalue()

    # 3. Parse via _parse_tabular_bytes and verify computed value is read, NOT the formula string
    headers, rows = _parse_tabular_bytes(
        content=xlsx_content,
        filename="barcodes_with_formulas.xlsx",
        sheet_locator=SheetLocator(type="first_sheet"),
        header_locator=HeaderLocator(type="fixed_row", row=0),
    )

    assert len(rows) == 1
    # Net Qty should be '100', NOT '=F2*2'
    assert rows[0]["Net Qty"] == "100"
    assert rows[0]["Style Code"] == "ART-ALPHA"
    assert rows[0]["Size"] == "7"

    # 4. Also test full import endpoint with this file
    files = {"file": ("barcodes_with_formulas.xlsx", xlsx_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "config_json": json.dumps({
            "name": "Formula Format",
            "column_map": {
                "style_code": "Style Code",
                "color": "Color",
                "size": "Size",
                "ean_code": "EAN Code",
            },
        }),
        "overwrite_existing": "false",
    }
    r = client.post(f"/api/pos/{po_id}/ean-codes/import", files=files, data=data)
    assert r.status_code == 200
    assert r.json()["imported"] == 1


def test_full_workflow_new_client_po_mapping_import_and_qc_pack_prefill(client_app):
    """
    Full realistic end-to-end workflow:
    1. New client PO arrives ('Metro Shoes Ltd') with PO line items.
    2. Jobs for this PO exist at stage qc_pack.
    3. Barcode file arrives with a never-before-seen format ('Article Name', 'Shade', 'Size No', 'UPC Code', 'Retail Price').
    4. Call preview-headers to detect headers and sample data.
    5. User maps columns and saves format config 'Metro Standard Barcodes'.
    6. Import barcode file using newly created config -> verify 100% matching rows imported.
    7. Retrieve PO EAN codes (prefill check for QC-pack UI) -> verify exact barcodes returned by size.
    8. Execute QC-pack confirmation (confirm_qc_pack / pack_carton) -> verify cartons are created with auto-filled EAN codes!
    """
    client, db, _ = client_app

    # 1. Setup new client PO for 'Metro Shoes Ltd'
    po_oid = ObjectId("654321654321654321654399")
    po_id_str = str(po_oid)
    po_doc = {
        "_id": po_oid,
        "po_number": "PO-METRO-2026",
        "client_name": "Metro Shoes Ltd",
        "client": "Metro",
        "line_items": [
            {"style_code": "METRO-RUNNER", "color": "Olive", "size": "7", "quantity": 40},
            {"style_code": "METRO-RUNNER", "color": "Olive", "size": "8", "quantity": 60},
        ],
    }
    db.pos.store[po_id_str] = po_doc

    # 2. Setup production jobs for this PO at stage 'qc_pack'
    job1_oid = ObjectId("654321654321654321654401")
    job2_oid = ObjectId("654321654321654321654402")
    style_oid = ObjectId("654321654321654321654400")

    job1_doc = {
        "_id": job1_oid,
        "po_id": po_id_str,
        "po_number": "PO-METRO-2026",
        "style_id": str(style_oid),
        "style_code": "METRO-RUNNER",
        "color": "Olive",
        "size": "7",
        "quantity": 40,
        "completed_qty": 40,
        "stage": "qc_pack",
    }
    job2_doc = {
        "_id": job2_oid,
        "po_id": po_id_str,
        "po_number": "PO-METRO-2026",
        "style_id": str(style_oid),
        "style_code": "METRO-RUNNER",
        "color": "Olive",
        "size": "8",
        "quantity": 60,
        "completed_qty": 60,
        "stage": "qc_pack",
    }
    db.production_jobs.store[str(job1_oid)] = job1_doc
    db.production_jobs.store[str(job2_oid)] = job2_doc

    # 3. Barcode file in a never-before-seen format arrives
    csv_raw = (
        "Article Name,Shade,Size No,UPC Code,Retail Price,Remarks\n"
        "METRO-RUNNER,Olive,7,8909876000007,1999,First batch\n"
        "METRO-RUNNER,Olive,8,8909876000008,1999,First batch\n"
    ).encode("utf-8")

    # 4. Preview headers
    files = {"file": ("metro_barcodes_2026.csv", csv_raw, "text/csv")}
    r_hdr = client.post(f"/api/pos/{po_id_str}/ean-codes/preview-headers", files=files)
    assert r_hdr.status_code == 200
    hdr_data = r_hdr.json()
    assert hdr_data["headers"] == ["Article Name", "Shade", "Size No", "UPC Code", "Retail Price", "Remarks"]

    # 5. Save new format config based on user's column assignments
    cfg_payload = {
        "name": "Metro Standard Barcodes",
        "client_name": "Metro Shoes Ltd",
        "column_map": {
            "style_code": "Article Name",
            "color": "Shade",
            "size": "Size No",
            "ean_code": "UPC Code",
        },
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "active": True,
    }
    r_save_fmt = client.post("/api/po-ean-formats", json=cfg_payload)
    assert r_save_fmt.status_code == 200
    cfg_id = r_save_fmt.json()["id"]
    assert cfg_id

    # 6. Import the barcode file for the PO
    files_imp = {"file": ("metro_barcodes_2026.csv", csv_raw, "text/csv")}
    r_imp = client.post(
        f"/api/pos/{po_id_str}/ean-codes/import",
        files=files_imp,
        data={"config_id": cfg_id, "overwrite_existing": "false"},
    )
    assert r_imp.status_code == 200
    imp_res = r_imp.json()
    assert imp_res["ok"] is True
    assert imp_res["imported"] == 2
    assert imp_res["unmatched_count"] == 0

    # 7. Verify EAN codes list endpoint (used by QC-Pack UI for prefilling)
    r_list = client.get(f"/api/pos/{po_id_str}/ean-codes")
    assert r_list.status_code == 200
    stored_items = r_list.json()["items"]
    assert len(stored_items) == 2
    ean_by_size = {item["size"]: item["ean_code"] for item in stored_items}
    assert ean_by_size["7"] == "8909876000007"
    assert ean_by_size["8"] == "8909876000008"

    # 8. Confirm QC-Pack Confirmation auto-fills EAN codes into cartons
    qc_pack_payload = {
        "job_ids": [str(job1_oid), str(job2_oid)],
        "cartons": [
            {"size": "7", "qty": 40},
            {"size": "8", "qty": 60},
        ],
        "eans": [],  # Empty payload eans - must auto-fill from PO EAN codes!
    }
    r_qc = client.post("/api/packing/confirm-qc-pack", json=qc_pack_payload)
    assert r_qc.status_code == 200
    assert r_qc.json()["ok"] is True

    # Verify packing cartons in DB have auto-filled EAN codes
    carton_records = list(db.packing_cartons.store.values())
    assert len(carton_records) == 2
    carton_eans = {c["size"]: c["ean_code"] for c in carton_records}
    assert carton_eans["7"] == "8909876000007"
    assert carton_eans["8"] == "8909876000008"


