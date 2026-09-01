"""PO Barcode / EAN Codes Routes & Configurable File Import Service."""

import io
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Query
from pymongo.errors import DuplicateKeyError

from auth import get_current_user_factory, require_roles
from models.po_ean import (
    PoEanCodeIn, PoEanImportFormatConfigIn, PoEanImportFormatConfigUpdate,
    PoEanImportRequest, PoEanImportResult, PoEanImportItem
)
from models.sku_map import SheetLocator, HeaderLocator
from rate_limiter import upload_rate_limiter

log = logging.getLogger("po_ean_routes")

po_ean_router = APIRouter(prefix="/api", tags=["PO Barcodes & EAN Import"])


def _get_db(request: Request = None):
    if request and getattr(request.app, "mongodb", None):
        return request.app.mongodb
    import server
    return server.db


async def _get_user(request: Request):
    db = _get_db(request)
    fn = await get_current_user_factory(db)
    return await fn(request)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(v) -> ObjectId:
    try:
        return ObjectId(v)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def stringify(doc: dict) -> dict:
    if doc is None:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, dict):
            doc[key] = stringify(value)
        elif isinstance(value, list):
            doc[key] = [stringify(x) if isinstance(x, dict) else str(x) if isinstance(x, ObjectId) else x for x in value]
    return doc


DEFAULT_PO_EAN_FORMAT_CONFIGS = [
    {
        "name": "Generic EAN Template",
        "client_name": "",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "style_code": "Style Code",
            "color": "Color",
            "size": "Size",
            "ean_code": "EAN Code",
            "po_number": "PO Number",
        },
        "notes": "Standard layout: Style Code, Color, Size, EAN Code, PO Number",
        "active": True,
    },
    {
        "name": "Bata Barcodes Format",
        "client_name": "Bata",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "scan_for_columns", "must_contain_any": ["Article", "Color", "Size", "Barcode", "EAN"]},
        "skip_rows_after_header": 0,
        "column_map": {
            "style_code": "Article No",
            "color": "Colour",
            "size": "Size",
            "ean_code": "Barcode",
            "po_number": "PO No",
        },
        "notes": "Bata supplier barcode sheet format",
        "active": True,
    },
    {
        "name": "Ajio B2B Barcodes",
        "client_name": "Ajio",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "scan_for_columns", "must_contain_any": ["Style", "Color", "Size", "EAN", "PO"]},
        "skip_rows_after_header": 0,
        "column_map": {
            "style_code": "Style Code",
            "color": "Color",
            "size": "Size",
            "ean_code": "EAN",
            "po_number": "PO Number",
        },
        "notes": "Ajio B2B barcode template with EAN/UPC",
        "active": True,
    },
    {
        "name": "Shein Barcodes Format",
        "client_name": "Shein",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "style_code": "SKU",
            "color": "Color",
            "size": "Size",
            "ean_code": "Bar Code",
            "po_number": "PO",
        },
        "notes": "Shein client barcode format",
        "active": True,
    },
]


async def _seed_po_ean_format_configs(db=None) -> int:
    """Seed default PO EAN format presets."""
    if db is None:
        import server
        db = server.db
    seeded = 0
    try:
        await db.po_ean_format_configs.create_index("name", unique=True, name="po_ean_format_name_unique")
    except Exception as e:
        log.warning(f"Could not create po_ean_format_configs unique index: {e}")

    for cfg in DEFAULT_PO_EAN_FORMAT_CONFIGS:
        existing = await db.po_ean_format_configs.find_one({"name": cfg["name"]})
        if not existing:
            doc = {**cfg, "created_at": now_iso(), "updated_at": now_iso()}
            await db.po_ean_format_configs.insert_one(doc)
            seeded += 1
    return seeded


# ─────────────────────────────────────────────────────────────────────────────
# Format Config Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@po_ean_router.get("/po-ean-formats")
async def list_po_ean_format_configs(request: Request, active: Optional[bool] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = _get_db(request)
    q = {}
    if active is not None:
        q["active"] = active
    docs = await db.po_ean_format_configs.find(q).sort("name", 1).to_list(100)
    return [stringify(d) for d in docs]


@po_ean_router.post("/po-ean-formats")
async def create_po_ean_format_config(payload: PoEanImportFormatConfigIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    existing = await db.po_ean_format_configs.find_one({"name": payload.name})
    if existing:
        raise HTTPException(400, f"Format config with name '{payload.name}' already exists")
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.po_ean_format_configs.insert_one(doc)
    return {"ok": True, "id": str(res.inserted_id)}


@po_ean_router.put("/po-ean-formats/{fmt_id}")
async def update_po_ean_format_config(fmt_id: str, payload: PoEanImportFormatConfigUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    existing = await db.po_ean_format_configs.find_one({"_id": oid(fmt_id)})
    if not existing:
        raise HTTPException(404, "Format config not found")
    upd = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not upd:
        return {"ok": True, "id": fmt_id}
    upd["updated_at"] = now_iso()
    await db.po_ean_format_configs.update_one({"_id": oid(fmt_id)}, {"$set": upd})
    return {"ok": True, "id": fmt_id}


@po_ean_router.delete("/po-ean-formats/{fmt_id}")
async def delete_po_ean_format_config(fmt_id: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    res = await db.po_ean_format_configs.delete_one({"_id": oid(fmt_id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Format config not found")
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Parse File and Resolve Style / Color / Size / EAN
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_mapped_field_value(row: dict, col_name: Optional[str]) -> str:
    if not col_name:
        return ""
    col_str = str(col_name).strip()
    if col_str in row:
        return str(row[col_str] or "").strip()
    # Case-insensitive fallback
    col_lower = col_str.lower()
    for k, v in row.items():
        if k and str(k).strip().lower() == col_lower:
            return str(v or "").strip()
    return ""


async def _resolve_style_for_row(
    raw_style: str,
    raw_color: str,
    raw_size: str,
    client_name: str,
    po_lines: List[dict],
    db,
) -> Tuple[str, str, str, bool, Optional[str]]:
    """
    Resolve raw style / SKU reference to internal style_code, color, size.
    Checks:
    1. Direct match with a style in PO line items
    2. Direct match with any style in db.styles (by code)
    3. Resolver via sku_map (resolve_style)
    """
    style_code = raw_style
    color = raw_color
    size = raw_size
    matched = False
    style_id = None

    # Check direct in PO line items
    for line in po_lines:
        po_code = line.get("style_code") or line.get("code") or ""
        if po_code.lower() == raw_style.lower():
            style_code = po_code
            matched = True
            style_id = str(line.get("style_id") or "")
            break

    # Check direct in db.styles
    if not matched and db is not None:
        st_doc = await db.styles.find_one({"code": {"$regex": f"^{raw_style}$", "$options": "i"}})
        if st_doc:
            style_code = st_doc.get("code", raw_style)
            style_id = str(st_doc["_id"])
            matched = True

    # Resolver via resolve_style if available
    if not matched and db is not None:
        try:
            from routes.sku_map import resolve_style
            res = await resolve_style(
                source_type="client_barcode",
                source_name=client_name or "Client",
                external_sku=raw_style,
                external_color=raw_color,
                external_size=raw_size,
                db=db,
            )
            if res.get("matched") and res.get("style_code"):
                style_code = res["style_code"]
                color = res.get("color") or color
                size = res.get("size") or size
                style_id = res.get("style_id")
                matched = True
        except Exception as e:
            log.debug(f"resolve_style check error: {e}")

    return style_code, color, size, matched, style_id


# ─────────────────────────────────────────────────────────────────────────────
# PO EAN Codes CRUD & Preview/Import Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@po_ean_router.get("/pos/{po_id}/ean-codes")
async def list_po_ean_codes(po_id: str, request: Request):
    """List stored EAN codes for a specific PO."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = _get_db(request)
    po = await db.pos.find_one({"_id": oid(po_id)})
    if not po:
        raise HTTPException(404, "PO not found")
    
    docs = await db.po_ean_codes.find({"po_id": po_id}).sort([("style_code", 1), ("color", 1), ("size", 1)]).to_list(2000)
    return {
        "ok": True,
        "po_id": po_id,
        "po_number": po.get("po_number"),
        "client": po.get("client"),
        "count": len(docs),
        "items": [stringify(d) for d in docs],
    }


@po_ean_router.post("/pos/{po_id}/ean-codes/preview-upload", dependencies=[Depends(upload_rate_limiter)])
async def preview_po_ean_upload(
    po_id: str,
    request: Request,
    file: UploadFile = File(...),
    config_json: Optional[str] = Form(None),
):
    """
    Parse uploaded barcode file (CSV/XLSX/XLS) according to sheet & header locator and column map.
    Returns preview of extracted rows, matched style/color/size against PO line items, and duplicate flags.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = _get_db(request)
    po = await db.pos.find_one({"_id": oid(po_id)})
    if not po:
        raise HTTPException(404, "PO not found")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")

    cfg_dict = {}
    if config_json:
        try:
            cfg_dict = json.loads(config_json)
        except Exception:
            raise HTTPException(400, "Invalid config_json format")

    sheet_loc_data = cfg_dict.get("sheet_locator") or {"type": "first_sheet"}
    header_loc_data = cfg_dict.get("header_locator") or {"type": "fixed_row", "row": 0}
    skip_rows = int(cfg_dict.get("skip_rows_after_header") or 0)
    column_map = cfg_dict.get("column_map") or {}

    sheet_loc = SheetLocator(**sheet_loc_data)
    header_loc = HeaderLocator(**header_loc_data)

    from routes.online_orders import _parse_tabular_bytes
    try:
        headers, parsed_rows = _parse_tabular_bytes(
            content=content,
            filename=file.filename,
            sheet_locator=sheet_loc,
            header_locator=header_loc,
            skip_rows_after_header=skip_rows,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Error parsing tabular file: {str(e)}")

    if not parsed_rows:
        return {
            "ok": True,
            "filename": file.filename,
            "headers": headers,
            "total_rows": 0,
            "extracted_items": [],
            "duplicate_keys": [],
            "po_matched_count": 0,
            "errors": ["No data rows found after applying sheet and header locators"],
        }

    po_lines = po.get("items") or []
    # Build a lookup set of (style_code.lower(), color.lower(), size.lower()) from PO line items
    po_item_set = set()
    for item in po_lines:
        sc = str(item.get("style_code") or "").strip().lower()
        col = str(item.get("color") or "").strip().lower()
        sz = str(item.get("size") or "").strip().lower()
        if sc and sz:
            po_item_set.add((sc, col, sz))

    extracted_items = []
    seen_in_batch = {}
    duplicate_keys = []
    po_matched_count = 0

    col_style = column_map.get("style_code") or column_map.get("external_sku") or column_map.get("style_ref") or "Style Code"
    col_color = column_map.get("color") or "Color"
    col_size = column_map.get("size") or "Size"
    col_ean = column_map.get("ean_code") or column_map.get("barcode") or "EAN Code"
    col_po = column_map.get("po_number")

    for idx, row in enumerate(parsed_rows):
        raw_style = _resolve_mapped_field_value(row, col_style)
        raw_color = _resolve_mapped_field_value(row, col_color)
        raw_size = _resolve_mapped_field_value(row, col_size)
        raw_ean = _resolve_mapped_field_value(row, col_ean)
        raw_po = _resolve_mapped_field_value(row, col_po) if col_po else None

        if not raw_style and not raw_ean:
            continue

        resolved_style, resolved_color, resolved_size, style_matched, _ = await _resolve_style_for_row(
            raw_style=raw_style,
            raw_color=raw_color,
            raw_size=raw_size,
            client_name=po.get("client", ""),
            po_lines=po_lines,
            db=db,
        )

        key = (resolved_style.strip().lower(), (resolved_color or "").strip().lower(), str(resolved_size or "").strip().lower())
        is_po_match = key in po_item_set or (key[0], "", key[2]) in po_item_set
        if is_po_match:
            po_matched_count += 1

        is_duplicate = False
        if key in seen_in_batch:
            is_duplicate = True
            duplicate_keys.append({
                "style_code": resolved_style,
                "color": resolved_color,
                "size": resolved_size,
                "first_row": seen_in_batch[key],
                "duplicate_row": idx + 1,
            })
        else:
            seen_in_batch[key] = idx + 1

        extracted_items.append({
            "row_number": idx + 1,
            "raw_style": raw_style,
            "raw_color": raw_color,
            "raw_size": raw_size,
            "style_code": resolved_style,
            "color": resolved_color,
            "size": resolved_size,
            "ean_code": raw_ean,
            "po_number": raw_po or po.get("po_number"),
            "is_po_match": is_po_match,
            "is_duplicate_in_file": is_duplicate,
            "raw_row": row,
        })

    # Check for existing items in po_ean_codes
    existing_records = await db.po_ean_codes.find({"po_id": po_id}).to_list(2000)
    existing_map = {
        (d["style_code"].lower(), (d.get("color") or "").lower(), str(d.get("size") or "").lower()): d["ean_code"]
        for d in existing_records
    }

    for item in extracted_items:
        k = (item["style_code"].lower(), (item["color"] or "").lower(), str(item["size"] or "").lower())
        if k in existing_map:
            item["exists_in_db"] = True
            item["existing_ean"] = existing_map[k]
        else:
            item["exists_in_db"] = False

    return {
        "ok": True,
        "filename": file.filename,
        "headers": headers,
        "total_rows": len(parsed_rows),
        "extracted_items": extracted_items,
        "duplicate_keys": duplicate_keys,
        "po_matched_count": po_matched_count,
        "existing_in_db_count": len(existing_records),
    }


@po_ean_router.post("/pos/{po_id}/ean-codes/import", dependencies=[Depends(upload_rate_limiter)])
async def import_po_ean_codes(
    po_id: str,
    request: Request,
):
    """
    Import EAN barcodes for a specific PO.
    Accepts:
      1. Multipart file upload with optional config_id, config_json, overwrite_existing
      2. OR JSON body payload (PoEanImportRequest)
    Validates each row against the PO's line items.
    Matching rows are saved to po_ean_codes scoped to po_id.
    Unmatched rows (invalid style/color/size for this PO) are clearly flagged in unmatched_rows.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = _get_db(request)
    po = await db.pos.find_one({"_id": oid(po_id)})
    if not po:
        raise HTTPException(404, "PO not found")

    content_type = request.headers.get("content-type", "")
    items_to_import: List[PoEanImportItem] = []
    overwrite = False
    total_parsed_rows = 0
    unmatched_rows: List[dict] = []

    # Build valid PO line-item sets for strict validation
    po_lines = po.get("line_items") or po.get("items") or []
    po_exact_set = set()
    po_style_size_set = set()
    po_ext_set = set()

    for li in po_lines:
        sc = str(li.get("style_code") or "").strip().lower()
        col = str(li.get("color") or "").strip().lower()
        sz = str(li.get("size") or "").strip().lower()
        ext = str(li.get("external_sku") or "").strip().lower()
        if sc and sz:
            po_exact_set.add((sc, col, sz))
            po_style_size_set.add((sc, sz))
        if ext and sz:
            po_ext_set.add((ext, col, sz))
            po_ext_set.add((ext, sz))

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if not uploaded_file or not hasattr(uploaded_file, "read"):
            raise HTTPException(400, "No file uploaded in multipart request")

        cfg_id = form.get("config_id")
        cfg_str = form.get("config_json")
        overwrite_raw = form.get("overwrite_existing")
        overwrite = str(overwrite_raw).lower() in ("true", "1", "yes")

        cfg_dict = {}
        if cfg_str:
            try:
                cfg_dict = json.loads(cfg_str)
            except Exception:
                raise HTTPException(400, "Invalid config_json format")
        elif cfg_id:
            cfg_doc = await db.po_ean_format_configs.find_one({"_id": oid(cfg_id)})
            if cfg_doc:
                cfg_dict = cfg_doc
        elif po.get("barcode_format_id"):
            cfg_doc = await db.po_ean_format_configs.find_one({"_id": oid(po["barcode_format_id"])})
            if cfg_doc:
                cfg_dict = cfg_doc
        elif po.get("client_name") or po.get("client"):
            c_name = po.get("client_name") or po.get("client") or ""
            cfg_doc = await db.po_ean_format_configs.find_one({
                "client_name": {"$regex": f"^{c_name}$", "$options": "i"},
                "active": True
            })
            if cfg_doc:
                cfg_dict = cfg_doc

        sheet_loc_data = cfg_dict.get("sheet_locator") or {"type": "first_sheet"}
        header_loc_data = cfg_dict.get("header_locator") or {"type": "fixed_row", "row": 0}
        skip_rows = int(cfg_dict.get("skip_rows_after_header") or 0)
        column_map = cfg_dict.get("column_map") or {}

        sheet_loc = SheetLocator(**sheet_loc_data)
        header_loc = HeaderLocator(**header_loc_data)

        from routes.online_orders import _parse_tabular_bytes
        file_bytes = await uploaded_file.read()
        if not file_bytes:
            raise HTTPException(400, "Uploaded file is empty")

        headers, parsed_rows = _parse_tabular_bytes(
            content=file_bytes,
            filename=uploaded_file.filename,
            sheet_locator=sheet_loc,
            header_locator=header_loc,
            skip_rows_after_header=skip_rows,
        )
        total_parsed_rows = len(parsed_rows)

        col_style = column_map.get("style_code") or column_map.get("external_sku") or column_map.get("style_ref") or "Style Code"
        col_color = column_map.get("color") or "Color"
        col_size = column_map.get("size") or "Size"
        col_ean = column_map.get("ean_code") or column_map.get("barcode") or "EAN Code"
        col_po = column_map.get("po_number")

        for idx, row in enumerate(parsed_rows):
            raw_style = _resolve_mapped_field_value(row, col_style)
            raw_color = _resolve_mapped_field_value(row, col_color)
            raw_size = _resolve_mapped_field_value(row, col_size)
            raw_ean = _resolve_mapped_field_value(row, col_ean)
            raw_po = _resolve_mapped_field_value(row, col_po) if col_po else None

            if not raw_style and not raw_ean:
                continue

            resolved_style, resolved_color, resolved_size, style_matched, _ = await _resolve_style_for_row(
                raw_style=raw_style,
                raw_color=raw_color,
                raw_size=raw_size,
                client_name=po.get("client_name") or po.get("client", ""),
                po_lines=po_lines,
                db=db,
            )

            # Strict PO line item membership check
            key_exact = (resolved_style.strip().lower(), (resolved_color or "").strip().lower(), str(resolved_size or "").strip().lower())
            key_style_sz = (resolved_style.strip().lower(), str(resolved_size or "").strip().lower())
            key_ext_exact = (raw_style.strip().lower(), (raw_color or "").strip().lower(), str(raw_size or "").strip().lower())
            key_ext_sz = (raw_style.strip().lower(), str(raw_size or "").strip().lower())

            is_valid_po_item = (
                key_exact in po_exact_set or
                key_style_sz in po_style_size_set or
                key_ext_exact in po_ext_set or
                key_ext_sz in po_ext_set
            ) if po_lines else True

            if not is_valid_po_item:
                unmatched_rows.append({
                    "row_number": idx + 1,
                    "raw_style": raw_style,
                    "raw_color": raw_color,
                    "raw_size": raw_size,
                    "style_code": resolved_style,
                    "color": resolved_color,
                    "size": resolved_size,
                    "ean_code": raw_ean,
                    "reason": f"Style/color/size '{raw_style} / {raw_color} / {raw_size}' does not match any valid line item in PO #{po.get('po_number')}",
                })
                continue

            items_to_import.append(PoEanImportItem(
                style_code=resolved_style,
                color=resolved_color,
                size=str(resolved_size),
                ean_code=raw_ean,
                po_number=raw_po or po.get("po_number"),
                raw_row=row,
            ))

    else:
        # JSON body request
        body_json = await request.json()
        payload = PoEanImportRequest(**body_json)
        overwrite = payload.overwrite_existing
        total_parsed_rows = len(payload.items)

        for idx, it in enumerate(payload.items):
            sc = it.style_code.strip()
            col = (it.color or "").strip()
            sz = str(it.size or "").strip()

            key_exact = (sc.lower(), col.lower(), sz.lower())
            key_style_sz = (sc.lower(), sz.lower())

            is_valid_po_item = (key_exact in po_exact_set or key_style_sz in po_style_size_set) if po_lines else True
            if not is_valid_po_item:
                unmatched_rows.append({
                    "row_number": idx + 1,
                    "raw_style": sc,
                    "raw_color": col,
                    "raw_size": sz,
                    "style_code": sc,
                    "color": col,
                    "size": sz,
                    "ean_code": it.ean_code,
                    "reason": f"Style/color/size '{sc} / {col} / {sz}' does not match any valid line item in PO #{po.get('po_number')}",
                })
                continue

            items_to_import.append(it)

    inserted_count = 0
    skipped_duplicates = 0
    conflicts = []
    seen_keys = set()
    user_email = u.get("email", "unknown")

    # Pre-fetch existing for this PO
    existing_cursor = db.po_ean_codes.find({"po_id": po_id})
    existing_docs = await existing_cursor.to_list(5000)
    existing_map = {
        (d["style_code"].strip().lower(), (d.get("color") or "").strip().lower(), str(d.get("size") or "").strip().lower()): d
        for d in existing_docs
    }

    for item in items_to_import:
        sc = item.style_code.strip()
        col = (item.color or "").strip()
        sz = str(item.size or "").strip()
        ean = item.ean_code.strip()

        if not sc or not sz or not ean:
            continue

        key = (sc.lower(), col.lower(), sz.lower())

        # Check intra-batch duplicate
        if key in seen_keys:
            skipped_duplicates += 1
            conflicts.append({
                "style_code": sc,
                "color": col,
                "size": sz,
                "ean_code": ean,
                "reason": "Duplicate within import batch",
            })
            continue
        seen_keys.add(key)

        # Check existing DB record
        if key in existing_map:
            prev = existing_map[key]
            if not overwrite:
                skipped_duplicates += 1
                conflicts.append({
                    "style_code": sc,
                    "color": col,
                    "size": sz,
                    "incoming_ean": ean,
                    "existing_ean": prev.get("ean_code"),
                    "reason": "Already exists in PO EAN records",
                })
                continue
            else:
                # Update existing record
                await db.po_ean_codes.update_one(
                    {"_id": prev["_id"]},
                    {"$set": {
                        "ean_code": ean,
                        "updated_at": now_iso(),
                        "updated_by": user_email,
                    }}
                )
                inserted_count += 1
                continue

        # Insert new record
        doc = {
            "po_id": po_id,
            "po_number": item.po_number or po.get("po_number", ""),
            "style_code": sc,
            "color": col,
            "size": sz,
            "ean_code": ean,
            "imported_at": now_iso(),
            "imported_by": user_email,
        }

        try:
            await db.po_ean_codes.insert_one(doc)
            inserted_count += 1
        except DuplicateKeyError:
            skipped_duplicates += 1
            conflicts.append({
                "style_code": sc,
                "color": col,
                "size": sz,
                "ean_code": ean,
                "reason": "Duplicate key error on (po_id, style_code, color, size)",
            })

    # Return summary
    return PoEanImportResult(
        ok=True,
        po_id=po_id,
        po_number=po.get("po_number", ""),
        total_rows=total_parsed_rows,
        imported=inserted_count,
        skipped_duplicates=skipped_duplicates,
        unmatched_count=len(unmatched_rows),
        unmatched_rows=unmatched_rows,
        conflicts=conflicts,
        errors=[],
    )


@po_ean_router.delete("/pos/{po_id}/ean-codes")
async def delete_po_ean_codes(po_id: str, request: Request):
    """Delete all imported EAN codes for a PO."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)
    res = await db.po_ean_codes.delete_many({"po_id": po_id})
    return {"ok": True, "deleted_count": res.deleted_count}
