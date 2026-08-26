"""Finished Goods Inventory & Movements Routes."""

import re
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from fastapi import APIRouter, HTTPException, Request, Depends, Query, File, UploadFile
from fastapi.responses import PlainTextResponse

from models.inventory import (
    FgInventoryIn,
    FgInventoryUpdate,
    StockReservation,
    StockRelease,
    FgStockMovementIn,
    InventoryReservationIn,
    MovementType,
    ReferenceType,
    AdjustmentField,
)
from auth import require_roles
from routes.components import _build_size_matrix_pivot

log = logging.getLogger(__name__)

inventory_router = APIRouter(prefix="/api", tags=["Finished Goods Inventory"])

STANDARD_SIZES = ["35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46"]

# ── FG Movement Engine ────────────────────────────────────────────────
# Map movement_type → dict of {fg_inventory_field: signed_delta_multiplier}.
# `quantity` from the request is multiplied by these to produce the delta applied to each field.
_MOVEMENT_DELTAS = {
    "production_in":     {"ready_stock_qty":  1},
    "reserved":          {"reserved_qty":     1},
    "unreserved":        {"reserved_qty":    -1},
    "dispatched":        {"ready_stock_qty": -1, "reserved_qty": -1},
    "return_in":         {"return_qty":       1},
    "return_restocked":  {"return_qty":      -1, "ready_stock_qty": 1},
    "return_damaged":    {"return_qty":      -1, "damaged_qty":    1},
    "liquidation_out":   {"ready_stock_qty": -1, "liquidation_qty": 1},
    # "adjustment" is dynamic — applied via payload.adjustment_field
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(400, "Invalid object ID format")


async def _get_user(request: Request):
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    db = getattr(request.app, "mongodb", None) or server.db
    fn = await get_current_user_factory(db)
    return await fn(request)


# ═══════════════════════════════════════════════════════════════════════
# ══ FG INVENTORY ENGINE & HELPERS ═══════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════

async def _seed_fg_inventory_for_lifecycle(lifecycle_doc: dict, user_email: str, db=None) -> dict:
    """Auto-create fg_inventory rows for every planned (color, size) pair, at
    ready_stock_qty=0 and min_stock_level=planned_min_stock. Idempotent — if a row
    already exists for a (style_id, color, size), only the min_stock_level is updated
    (never overwrites existing quantities).

    Returns a summary: {created, updated, pairs}
    """
    if db is None:
        import server
        db = server.db

    style_id  = lifecycle_doc["style_id"]
    colors    = [c for c in (lifecycle_doc.get("planned_colors") or []) if c and str(c).strip()]
    sizes     = [s for s in (lifecycle_doc.get("planned_sizes")  or []) if s and str(s).strip()]
    min_stock = int(lifecycle_doc.get("planned_min_stock") or 25)

    if not colors or not sizes:
        return {"created": 0, "updated": 0, "pairs": 0,
                "note": "No planned colors/sizes — nothing seeded"}

    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    style_code = style["code"] if style else lifecycle_doc.get("style_code", "")

    created = 0
    updated = 0
    now = now_iso()
    for color in colors:
        for size in sizes:
            row = await db.fg_inventory.find_one({
                "style_id": ObjectId(style_id),
                "color":    color,
                "size":     size,
            })
            if row:
                # Only bump the min_stock_level; never touch quantities
                await db.fg_inventory.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"min_stock_level": min_stock, "updated_at": now}}
                )
                updated += 1
            else:
                try:
                    await db.fg_inventory.insert_one({
                        "style_id":         ObjectId(style_id),
                        "style_code":       style_code,
                        "color":            color,
                        "size":             size,
                        "ready_stock_qty":  0,
                        "reserved_qty":     0,
                        "in_transit_qty":   0,
                        "return_qty":       0,
                        "damaged_qty":      0,
                        "liquidation_qty":  0,
                        "min_stock_level":  min_stock,
                        "updated_at":       now,
                    })
                    created += 1
                except DuplicateKeyError:
                    pass

    return {
        "created": created,
        "updated": updated,
        "pairs":   len(colors) * len(sizes),
        "style_code": style_code,
    }


async def _get_or_create_fg_row(style_id: str, color: str, size: str, db=None):
    """Return the fg_inventory row for (style_id, color, size). Auto-create at zero if absent."""
    if db is None:
        import server
        db = server.db

    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    if not style:
        raise HTTPException(404, f"Style '{style_id}' not found")
    row = await db.fg_inventory.find_one({
        "style_id": ObjectId(style_id),
        "color": color,
        "size":  size,
    })
    if row:
        return row
    doc = {
        "style_id":         ObjectId(style_id),
        "style_code":       style["code"],
        "color":            color,
        "size":             size,
        "ready_stock_qty":  0,
        "reserved_qty":     0,
        "in_transit_qty":   0,
        "return_qty":       0,
        "damaged_qty":      0,
        "liquidation_qty":  0,
        "min_stock_level":  25,
        "updated_at":       now_iso(),
    }
    try:
        res = await db.fg_inventory.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc
    except DuplicateKeyError:
        return await db.fg_inventory.find_one({
            "style_id": ObjectId(style_id), "color": color, "size": size,
        })


async def _resolve_style_by_code(code: str, db=None):
    """Resolve a style_code → style ObjectId. Returns None if not found."""
    if not code:
        return None
    if db is None:
        import server
        db = server.db
    doc = await db.styles.find_one({"code": code.strip()})
    return doc


async def _apply_movement(payload: "FgStockMovementIn", user_email: str, skip_location_sync: bool = False, db=None):
    """Single write path to fg_inventory. Creates a ledger row and updates the inventory
    row atomically. Blocks any movement that would push a field below zero.

    Also, for movement_type in {"reserved", "unreserved", "dispatched"} it maintains the
    inventory_reservations collection linked via `online_order_id`.
    """
    if db is None:
        import server
        db = server.db

    row = await _get_or_create_fg_row(payload.style_id, payload.color, payload.size, db=db)

    # ── Build the delta dict (field → signed change) ────────────────────
    if payload.movement_type == "adjustment":
        if not payload.adjustment_field:
            raise HTTPException(400, "adjustment_field is required for movement_type='adjustment'")
        # For adjustment, `quantity` may be negative (raw delta)
        delta = {payload.adjustment_field: int(payload.quantity)}
    else:
        if payload.quantity <= 0:
            raise HTTPException(400, "quantity must be > 0 for this movement_type")
        multipliers = _MOVEMENT_DELTAS.get(payload.movement_type)
        if multipliers is None:
            raise HTTPException(400, f"Unsupported movement_type '{payload.movement_type}'")
        delta = {f: m * int(payload.quantity) for f, m in multipliers.items()}

    # ── Validate no field goes below zero ───────────────────────────────
    for field, d in delta.items():
        current = int(row.get(field, 0))
        if current + d < 0:
            raise HTTPException(
                400,
                f"Movement would push {field} below zero (current {current}, delta {d}). "
                f"Movement blocked."
            )

    # ── Atomic $inc with concurrency guard (match on current values) ────
    match_filter = {"_id": row["_id"]}
    for field in delta:
        match_filter[field] = int(row.get(field, 0))

    update = {
        "$inc": {field: int(d) for field, d in delta.items()},
        "$set": {"updated_at": now_iso()},
    }
    res = await db.fg_inventory.update_one(match_filter, update)
    if res.modified_count == 0:
        raise HTTPException(
            409,
            "Concurrent modification detected on fg_inventory. Please retry the movement."
        )

    # ── Post the ledger row ─────────────────────────────────────────────
    mv_doc = {
        "style_id":       ObjectId(payload.style_id),
        "style_code":     row.get("style_code", ""),
        "color":          payload.color,
        "size":           payload.size,
        "movement_type":  payload.movement_type,
        "quantity":       int(payload.quantity),
        "reference_type": payload.reference_type,
        "reference_id":   payload.reference_id or "",
        "notes":          payload.notes or "",
        "delta":          {k: int(v) for k, v in delta.items()},
        "created_at":     now_iso(),
        "by":             user_email,
    }
    if payload.movement_type == "adjustment":
        mv_doc["adjustment_field"] = payload.adjustment_field
    mv_res = await db.fg_stock_movements.insert_one(mv_doc)
    mv_doc["_id"] = mv_res.inserted_id

    # ── Maintain inventory_reservations for reserve / unreserve / dispatch ──
    if payload.movement_type == "reserved" and payload.online_order_id:
        await db.inventory_reservations.insert_one({
            "style_id":        ObjectId(payload.style_id),
            "style_code":      row.get("style_code", ""),
            "color":           payload.color,
            "size":            payload.size,
            "qty":             int(payload.quantity),
            "online_order_id": payload.online_order_id,
            "reserved_at":     now_iso(),
            "released_at":     None,
            "status":          "active",
        })
    elif payload.movement_type == "unreserved" and payload.online_order_id:
        await db.inventory_reservations.update_many(
            {
                "online_order_id": payload.online_order_id,
                "style_id":        ObjectId(payload.style_id),
                "color":           payload.color,
                "size":            payload.size,
                "status":          "active",
            },
            {"$set": {"status": "released", "released_at": now_iso()}}
        )
    elif payload.movement_type == "dispatched" and payload.online_order_id:
        await db.inventory_reservations.update_many(
            {
                "online_order_id": payload.online_order_id,
                "style_id":        ObjectId(payload.style_id),
                "color":           payload.color,
                "size":            payload.size,
                "status":          "active",
            },
            {"$set": {"status": "fulfilled", "released_at": now_iso()}}
        )

    updated = await db.fg_inventory.find_one({"_id": row["_id"]})
    updated = stringify(updated)
    u_ready = updated.get("ready_stock_qty", 0)
    u_res   = updated.get("reserved_qty", 0)
    u_dmg   = updated.get("damaged_qty", 0)
    u_liq   = updated.get("liquidation_qty", 0)
    u_min   = updated.get("min_stock_level", 25)
    updated["available_qty"] = u_ready - u_res - u_dmg - u_liq
    updated["is_low_stock"]  = u_ready < u_min

    # ── Warehouse location sync (Phase WMS) ─────────────────────────────
    location_result = None
    if not skip_location_sync:
        try:
            import server
            sync_fn = getattr(server, "_sync_warehouse_locations", None)
            if sync_fn:
                location_result = await sync_fn(payload, user_email)
        except Exception as _wms_err:
            log.warning(f"WMS sync failed for {payload.movement_type}: {_wms_err}")

    mv_out = stringify(mv_doc)
    return {"inventory": updated, "movement": mv_out, "warehouse": location_result}


# ═══════════════════════════════════════════════════════════════════════
# ══ FG INVENTORY ENDPOINTS ═════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════

@inventory_router.get("/fg-inventory")
async def list_fg_inventory(
    request: Request,
    style_id: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: Optional[bool] = None
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    query = {}
    if style_id:
        try:
            query["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if color:
        query["color"] = color
    if size:
        query["size"] = size
    
    if search:
        search_regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"style_code": search_regex},
            {"color": search_regex},
            {"size": search_regex}
        ]
    
    docs = await db.fg_inventory.find(query).to_list(2000)
    out = []
    for d in docs:
        d = stringify(d)
        ready = d.get("ready_stock_qty", 0)
        reserved = d.get("reserved_qty", 0)
        damaged = d.get("damaged_qty", 0)
        liq = d.get("liquidation_qty", 0)
        min_stock = d.get("min_stock_level", 25)
        
        available = ready - reserved - damaged - liq
        d["available_qty"] = available
        d["is_low_stock"] = ready < min_stock
        
        if low_stock is not None:
            if low_stock and not d["is_low_stock"]:
                continue
            if not low_stock and d["is_low_stock"]:
                continue
        
        out.append(d)
    return out


@inventory_router.post("/fg-inventory/movements")
async def create_fg_movement(request: Request, payload: FgStockMovementIn):
    """Single write path to fg_inventory. Creates a movement ledger row and atomically
    updates the inventory row. Auto-creates the fg_inventory row at zero if none exists.
    Blocks any movement that would push a quantity below zero.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    return await _apply_movement(payload, u.get("email") or u.get("name", ""), db=db)


@inventory_router.post("/fg-inventory/bulk-movements")
async def bulk_fg_movements(request: Request, payload: dict):
    """Apply many movements in one request. Best-effort: each row is validated and
    applied independently; failures are reported per-row and don't abort the batch.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    movements = (payload or {}).get("movements") or []
    if not isinstance(movements, list) or not movements:
        raise HTTPException(400, "movements must be a non-empty list")
    if len(movements) > 2000:
        raise HTTPException(400, "Batch too large — max 2000 movements per request")

    results = []
    ok_count  = 0
    err_count = 0
    for idx, row in enumerate(movements):
        try:
            mv = FgStockMovementIn(**row)
            out = await _apply_movement(mv, u.get("email") or u.get("name", ""), db=db)
            results.append({
                "index":     idx,
                "style_id":  mv.style_id,
                "color":     mv.color,
                "size":      mv.size,
                "movement":  mv.movement_type,
                "ok":        True,
                "delta":     out["movement"].get("delta"),
            })
            ok_count += 1
        except HTTPException as he:
            results.append({
                "index":    idx,
                "row":      row,
                "ok":       False,
                "error":    str(he.detail),
                "status":   he.status_code,
            })
            err_count += 1
        except Exception as e:
            results.append({
                "index":    idx,
                "row":      row,
                "ok":       False,
                "error":    str(e),
                "status":   500,
            })
            err_count += 1

    return {
        "total":    len(movements),
        "success":  ok_count,
        "failed":   err_count,
        "results":  results,
    }


@inventory_router.post("/fg-inventory/import-csv")
async def import_fg_stock_csv(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="If true, only preview — nothing is written."),
):
    """Import many FG stock movements from a CSV file."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV appears to be empty or unreadable")

    norm_map = {(h or "").strip().lower().replace(" ", "_"): h for h in reader.fieldnames}

    def col(row, key):
        h = norm_map.get(key)
        return (row.get(h, "") if h else "").strip() if isinstance(row.get(h, ""), str) else row.get(h, "")

    parsed = []
    errors = []
    style_code_cache = {}

    for line_no, r in enumerate(reader, start=2):
        code = col(r, "style_code")
        sid  = col(r, "style_id")
        color = col(r, "color")
        size  = str(col(r, "size") or "").strip()
        try:
            qty = int(float(str(col(r, "quantity") or "0")))
        except Exception:
            qty = None
        mv_type = (col(r, "movement_type") or "production_in").strip().lower()
        ref_type = (col(r, "reference_type") or "manual").strip().lower()
        ref_id  = col(r, "reference_id") or ""
        notes   = col(r, "notes") or ""
        adj_fld = col(r, "adjustment_field") or None
        oo_id   = col(r, "online_order_id") or None

        if not (code or sid):
            errors.append({"line": line_no, "error": "Missing style_code / style_id"})
            continue
        if not color:
            errors.append({"line": line_no, "error": "Missing color"})
            continue
        if not size:
            errors.append({"line": line_no, "error": "Missing size"})
            continue
        if qty is None:
            errors.append({"line": line_no, "error": "quantity is not a valid number"})
            continue
        if qty == 0:
            continue

        resolved_sid = sid
        if not resolved_sid:
            if code in style_code_cache:
                resolved_sid = style_code_cache[code]
            else:
                sdoc = await _resolve_style_by_code(code, db=db)
                if not sdoc:
                    errors.append({"line": line_no, "error": f"Unknown style_code '{code}'"})
                    continue
                resolved_sid = str(sdoc["_id"])
                style_code_cache[code] = resolved_sid

        row = {
            "style_id":       resolved_sid,
            "color":          color,
            "size":           size,
            "movement_type":  mv_type,
            "quantity":       qty,
            "reference_type": ref_type if ref_type in ("manual","job","online_order","return") else "manual",
            "reference_id":   ref_id,
            "notes":          notes,
        }
        if mv_type == "adjustment":
            if not adj_fld:
                errors.append({"line": line_no, "error": "adjustment_field is required for movement_type='adjustment'"})
                continue
            row["adjustment_field"] = adj_fld
        if oo_id:
            row["online_order_id"] = oo_id
        row["_line"] = line_no
        parsed.append(row)

    if dry_run:
        return {
            "dry_run": True,
            "parsed":  parsed,
            "errors":  errors,
            "summary": {
                "total_rows_seen":  len(parsed) + len(errors),
                "valid":            len(parsed),
                "invalid":          len(errors),
            },
        }

    results = []
    ok = 0
    err = 0
    for row in parsed:
        line = row.pop("_line", None)
        try:
            mv = FgStockMovementIn(**row)
            out = await _apply_movement(mv, u.get("email") or u.get("name", ""), db=db)
            results.append({"line": line, "ok": True, "delta": out["movement"].get("delta")})
            ok += 1
        except HTTPException as he:
            results.append({"line": line, "ok": False, "error": str(he.detail)})
            err += 1
        except Exception as e:
            results.append({"line": line, "ok": False, "error": str(e)})
            err += 1

    return {
        "committed": True,
        "summary": {
            "total_rows_seen": len(parsed) + len(errors),
            "attempted":       len(parsed),
            "success":         ok,
            "failed":          err,
            "parse_errors":    len(errors),
        },
        "results":       results,
        "parse_errors":  errors,
    }


@inventory_router.get("/fg-inventory/csv-template")
async def download_fg_csv_template(request: Request):
    """Return a ready-to-fill CSV template with headers + one commented example row."""
    await _get_user(request)
    csv_text = (
        "style_code,color,size,movement_type,quantity,reference_type,reference_id,notes,adjustment_field,online_order_id\n"
        "# Fill one row per (style, color, size). Leave quantity blank / 0 to skip a row.\n"
        "# movement_type defaults to production_in (adds ready stock). Other types:\n"
        "#   reserved, unreserved, dispatched, return_in, return_restocked,\n"
        "#   return_damaged, liquidation_out, adjustment (needs adjustment_field).\n"
        "33-1065-ME,SILVER,36,production_in,10,manual,,First lot from production,,\n"
        "33-1065-ME,SILVER,37,production_in,20,manual,,,,\n"
        "33-1065-ME,GOLD,38,production_in,30,manual,,,,\n"
    )
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fg_stock_template.csv"'},
    )


@inventory_router.get("/fg-inventory/movements")
async def list_fg_movements(
    request: Request,
    style_id: Optional[str]      = None,
    movement_type: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str]  = None,
    from_date: Optional[str]     = None,
    to_date: Optional[str]       = None,
    limit: int                    = 500,
):
    """Ledger view of every fg_inventory movement. Ordered newest first."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    query: dict = {}
    if style_id:
        try:
            query["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if movement_type:
        query["movement_type"] = movement_type
    if reference_type:
        query["reference_type"] = reference_type
    if reference_id:
        query["reference_id"] = reference_id
    if from_date or to_date:
        date_q: dict = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        query["created_at"] = date_q
    docs = await db.fg_stock_movements.find(query).sort("created_at", -1).to_list(int(limit))
    return [stringify(d) for d in docs]


@inventory_router.get("/fg-inventory/by-style/{style_id}")
async def get_fg_inventory_by_style(request: Request, style_id: str):
    """Full color × size breakdown for a single style, with computed available_qty
    and low-stock flag per row. Non-breaking sibling of /fg-inventory/{id}.
    """
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    rows = await db.fg_inventory.find({"style_id": ObjectId(style_id)}).to_list(500)
    out_rows = []
    colors: set = set()
    sizes:  set = set()
    for r in rows:
        r = stringify(r)
        ready = int(r.get("ready_stock_qty", 0))
        res   = int(r.get("reserved_qty",   0))
        dmg   = int(r.get("damaged_qty",    0))
        liq   = int(r.get("liquidation_qty", 0))
        mn    = int(r.get("min_stock_level", 25))
        r["available_qty"] = ready - res - dmg - liq
        r["is_low_stock"]  = ready < mn
        out_rows.append(r)
        if r.get("color"): colors.add(r["color"])
        if r.get("size"):  sizes.add(r["size"])

    active = await db.inventory_reservations.find({
        "style_id": ObjectId(style_id),
        "status":   "active",
    }).to_list(500)
    active_reservations = [stringify(a) for a in active]

    size_matrix = _build_size_matrix_pivot(
        out_rows,
        qty_field="ready_stock_qty",
        reserved_field="reserved_qty",
    )

    return {
        "style": {
            "id":    str(style["_id"]),
            "code":  style["code"],
            "name":  style.get("name", ""),
            "image_url":           style.get("image_url", ""),
            "image_display_url":   style.get("image_display_url", ""),
            "image_thumbnail_url": style.get("image_thumbnail_url", ""),
        },
        "rows":                out_rows,
        "colors":              sorted(colors),
        "sizes":               sorted(sizes),
        "standard_sizes":      STANDARD_SIZES,
        "size_matrix":         size_matrix,
        "active_reservations": active_reservations,
    }


@inventory_router.put("/fg-inventory/size-matrix")
async def put_fg_inventory_size_matrix(request: Request, payload: dict):
    """Bulk-seed FG ready stock via a color × size matrix in a single call."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    style_id     = (payload or {}).get("style_id", "")
    color        = (payload or {}).get("color", "").strip()
    size_matrix  = (payload or {}).get("size_matrix") or {}
    mv_type      = (payload or {}).get("movement_type", "production_in").strip()
    reference_id = (payload or {}).get("reference_id", "")
    notes        = (payload or {}).get("notes", "")

    if not style_id:
        raise HTTPException(400, "style_id is required")
    if not color:
        raise HTTPException(400, "color is required")
    if not size_matrix:
        raise HTTPException(400, "size_matrix must be a non-empty {size: qty} dict")

    results = []
    ok_count  = 0
    err_count = 0

    for size_str, qty_raw in size_matrix.items():
        try:
            qty = int(float(str(qty_raw or 0)))
        except Exception:
            results.append({"size": size_str, "ok": False, "error": "quantity is not a valid number"})
            err_count += 1
            continue

        if qty == 0:
            continue

        try:
            mv = FgStockMovementIn(
                style_id       = style_id,
                color          = color,
                size           = str(size_str).strip(),
                movement_type  = mv_type,
                quantity       = qty,
                reference_type = "manual",
                reference_id   = reference_id or "",
                notes          = notes or f"Size-matrix bulk entry for {color}/{size_str}",
            )
            out = await _apply_movement(mv, u.get("email") or u.get("name", ""), db=db)
            results.append({
                "size":  size_str,
                "qty":   qty,
                "ok":    True,
                "delta": out["movement"].get("delta"),
            })
            ok_count += 1
        except HTTPException as he:
            results.append({"size": size_str, "qty": qty, "ok": False, "error": str(he.detail)})
            err_count += 1
        except Exception as e:
            results.append({"size": size_str, "qty": qty, "ok": False, "error": str(e)})
            err_count += 1

    return {
        "style_id": style_id,
        "color":    color,
        "success":  ok_count,
        "failed":   err_count,
        "results":  results,
    }


@inventory_router.get("/inventory-reservations")
async def list_inventory_reservations(
    request: Request,
    online_order_id: Optional[str] = None,
    style_id: Optional[str]        = None,
    status: Optional[str]          = None,
):
    """Read-only view of the reservations ledger — which orders are holding which stock."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    query: dict = {}
    if online_order_id:
        query["online_order_id"] = online_order_id
    if style_id:
        try:
            query["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if status:
        query["status"] = status
    docs = await db.inventory_reservations.find(query).sort("reserved_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@inventory_router.get("/fg-inventory/{id}")
async def get_fg_inventory_item(request: Request, id: str):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.fg_inventory.find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(404, "Inventory record not found")
    doc = stringify(doc)
    ready = doc.get("ready_stock_qty", 0)
    reserved = doc.get("reserved_qty", 0)
    damaged = doc.get("damaged_qty", 0)
    liq = doc.get("liquidation_qty", 0)
    min_stock = doc.get("min_stock_level", 25)
    
    doc["available_qty"] = ready - reserved - damaged - liq
    doc["is_low_stock"] = ready < min_stock
    return doc


@inventory_router.post("/fg-inventory")
async def create_fg_inventory(request: Request, payload: FgInventoryIn):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    
    style = await db.styles.find_one({"_id": ObjectId(payload.style_id)})
    if not style:
        raise HTTPException(400, "Style does not exist")
        
    doc = {
        "style_id": ObjectId(payload.style_id),
        "style_code": style["code"],
        "color": payload.color,
        "size": payload.size,
        "ready_stock_qty": payload.ready_stock_qty,
        "reserved_qty": payload.reserved_qty,
        "in_transit_qty": payload.in_transit_qty,
        "return_qty": payload.return_qty,
        "damaged_qty": payload.damaged_qty,
        "liquidation_qty": payload.liquidation_qty,
        "min_stock_level": payload.min_stock_level,
        "updated_at": now_iso()
    }
    try:
        res = await db.fg_inventory.insert_one(doc)
        doc["_id"] = res.inserted_id
        doc = stringify(doc)
        
        ready = doc.get("ready_stock_qty", 0)
        reserved = doc.get("reserved_qty", 0)
        damaged = doc.get("damaged_qty", 0)
        liq = doc.get("liquidation_qty", 0)
        min_stock = doc.get("min_stock_level", 25)
        
        doc["available_qty"] = ready - reserved - damaged - liq
        doc["is_low_stock"] = ready < min_stock
        return doc
    except DuplicateKeyError:
        raise HTTPException(400, "Inventory entry for this style/color/size already exists")


@inventory_router.patch("/fg-inventory/{id}")
async def update_fg_inventory(request: Request, id: str, payload: FgInventoryUpdate):
    """Config-only patch: only `min_stock_level` may be updated here. Every stock-qty
    change MUST go through POST /api/fg-inventory/movements so the ledger stays intact.
    """
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    payload_data = payload.model_dump(exclude_unset=True)
    stock_fields = {"ready_stock_qty", "reserved_qty", "in_transit_qty",
                    "return_qty", "damaged_qty", "liquidation_qty"}
    illegal = [k for k in payload_data.keys() if k in stock_fields and payload_data[k] is not None]
    if illegal:
        raise HTTPException(
            400,
            f"Direct edits to {illegal} are forbidden. Post a movement via "
            f"POST /api/fg-inventory/movements (movement_type='adjustment', "
            f"adjustment_field='{illegal[0]}') to change stock quantities."
        )

    update_data = {k: v for k, v in payload_data.items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No fields to update")

    update_data["updated_at"] = now_iso()
    res = await db.fg_inventory.update_one(
        {"_id": ObjectId(id)},
        {"$set": update_data}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Inventory record not found")

    doc = await db.fg_inventory.find_one({"_id": ObjectId(id)})
    doc = stringify(doc)
    ready = doc.get("ready_stock_qty", 0)
    reserved = doc.get("reserved_qty", 0)
    damaged = doc.get("damaged_qty", 0)
    liq = doc.get("liquidation_qty", 0)
    min_stock = doc.get("min_stock_level", 25)

    doc["available_qty"] = ready - reserved - damaged - liq
    doc["is_low_stock"] = ready < min_stock
    return doc


@inventory_router.post("/fg-inventory/reserve")
async def reserve_stock(request: Request, payload: StockReservation):
    """Legacy convenience wrapper — routes through the movement engine."""
    u = await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    mv = FgStockMovementIn(
        style_id       = payload.style_id,
        color          = payload.color,
        size           = payload.size,
        movement_type  = "reserved",
        quantity       = payload.quantity,
        reference_type = "manual",
        reference_id   = "",
        notes          = "Legacy /reserve call",
    )
    result = await _apply_movement(mv, u.get("email") or u.get("name", ""), db=db)
    return {"success": True, "message": f"Reserved {payload.quantity} pairs", **result}


@inventory_router.post("/fg-inventory/release")
async def release_stock(request: Request, payload: StockRelease):
    """Legacy convenience wrapper — routes through the movement engine.

    release_type == "ship"   → "dispatched" movement (decrement ready + reserved)
    release_type == "cancel" → "unreserved" movement (decrement reserved only)
    """
    u = await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    mv_type = "dispatched" if payload.release_type == "ship" else "unreserved"
    mv = FgStockMovementIn(
        style_id       = payload.style_id,
        color          = payload.color,
        size           = payload.size,
        movement_type  = mv_type,
        quantity       = payload.quantity,
        reference_type = "manual",
        reference_id   = "",
        notes          = f"Legacy /release call ({payload.release_type})",
    )
    result = await _apply_movement(mv, u.get("email") or u.get("name", ""), db=db)
    return {"success": True, "message": f"Released {payload.quantity} pairs via {payload.release_type}", **result}
