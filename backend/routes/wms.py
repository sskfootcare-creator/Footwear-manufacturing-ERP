"""Warehouse Management System (WMS) Routes & Online Commerce Storage Layer."""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel

from models.wms import (
    PicklistItemIn,
    PicklistIn,
    PickItemIn,
    PicklistPatchIn,
    LocationBlockIn,
    ProduceCellIn,
    ProductionCardIn,
)
from models.inventory import FgStockMovementIn
from auth import require_roles
from routes.inventory import _apply_movement

log = logging.getLogger(__name__)

wms_router = APIRouter(prefix="/api", tags=["Warehouse Management System (WMS)"])

# ── WMS Constants ────────────────────────────────────────────────────────
WAREHOUSE_ROWS = 10
RACKS_PER_ROW  = 3
RACKS          = [1, 2, 3]
CELLS_PER_RACK = 8
CAPACITY       = 40                  # pairs per cell
ROW_PAIRS      = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]


# ── Helper Utilities ─────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: Any) -> Any:
    if doc is None:
        return None
    if isinstance(doc, list):
        return [stringify(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            if k == "_id":
                out["id"] = str(v)
            elif isinstance(v, ObjectId):
                out[k] = str(v)
            elif isinstance(v, (datetime,)):
                out[k] = v.isoformat()
            elif isinstance(v, (dict, list)):
                out[k] = stringify(v)
            else:
                out[k] = v
        return out
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc


def oid(val: str) -> ObjectId:
    try:
        return ObjectId(str(val))
    except Exception:
        raise HTTPException(400, f"Invalid ObjectId '{val}'")


async def _get_user(request: Request) -> dict:
    get_user_fn = getattr(request.app, "get_current_user", None) or getattr(__import__("server"), "get_current_user")
    return await get_user_fn(request)


async def log_activity(action: str, entity_type: str, details: str, user_email: str, db=None):
    if db is None:
        db = getattr(__import__("server"), "db")
    doc = {
        "action": action,
        "entity_type": entity_type,
        "details": details,
        "user": user_email,
        "timestamp": now_iso(),
    }
    try:
        await db.audit_logs.insert_one(doc)
    except Exception as e:
        log.warning(f"Failed to log activity: {e}")


def _make_location_code(row: int, rack: int, cell: int) -> str:
    """Format location code: e.g. R01-RK1-C01 … R10-RK3-C08."""
    return f"R{row:02d}-RK{rack}-C{cell:02d}"


def _recompute_status(occupied: int, capacity: int) -> str:
    if occupied <= 0:
        return "empty"
    if occupied >= capacity:
        return "full"
    return "partial"


async def _seed_warehouse_locations(db=None) -> int:
    """Idempotent — inserts any missing cells into warehouse_locations."""
    if db is None:
        db = getattr(__import__("server"), "db")
    to_upsert = []
    for r in range(1, WAREHOUSE_ROWS + 1):
        for rack in range(1, RACKS_PER_ROW + 1):
            for c in range(1, CELLS_PER_RACK + 1):
                code = _make_location_code(r, rack, c)
                zone = "main"
                pair_group = (r - 1) // 2 + 1
                aisle_before = (r % 2 == 1 and r != 1)
                to_upsert.append({
                    "location_code":   code,
                    "rack":            rack,
                    "row":             r,
                    "cell":            c,
                    "zone":            zone,
                    "pair_group":      pair_group,
                    "aisle_before":    aisle_before,
                    "capacity_pairs":  CAPACITY,
                    "occupied_pairs":  0,
                    "available_pairs": CAPACITY,
                    "status":          "empty",
                    "block_reason":    None,
                    "created_at":      now_iso(),
                    "updated_at":      now_iso(),
                })
    inserted = 0
    for doc in to_upsert:
        doc_on_insert = {k: v for k, v in doc.items() if k not in ("pair_group", "aisle_before", "zone")}
        res = await db.warehouse_locations.update_one(
            {"location_code": doc["location_code"]},
            {"$setOnInsert": doc_on_insert,
             "$set": {
                 "pair_group":   doc["pair_group"],
                 "aisle_before": doc["aisle_before"],
                 "zone":         doc["zone"],
             }},
            upsert=True,
        )
        if res.upserted_id:
            inserted += 1

    await db.warehouse_locations.update_many(
        {"zone": {"$exists": False}},
        [{"$set": {"zone": "main"}}]
    )
    return inserted


async def _allocate_to_locations(style_id, style_code, color, size, qty, user_email,
                                  reference_type="", reference_id="", zone="main",
                                  prefer_existing_sku_cells=False, db=None) -> dict:
    """Sequentially fill cells until qty placed."""
    if db is None:
        db = getattr(__import__("server"), "db")
    remaining = int(qty)
    placements = []
    guard = 0

    sid_oid = ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else str(style_id)

    # Phase A — same-SKU consolidation
    if prefer_existing_sku_cells and remaining > 0:
        existing_cur = db.fg_location_inventory.find({
            "$or": [{"style_id": sid_oid}, {"style_id": str(style_id)}],
            "color": color, "size": size,
        }).sort([("created_at", 1), ("location_code", 1)])
        async for inv in existing_cur:
            if remaining <= 0:
                break
            code = inv.get("location_code")
            wloc = await db.warehouse_locations.find_one({
                "location_code": code, "zone": zone,
                "status": {"$ne": "blocked"}, "available_pairs": {"$gt": 0},
            })
            if not wloc:
                continue
            place_qty = min(remaining, int(wloc["available_pairs"]))
            new_occupied  = int(wloc["occupied_pairs"]) + place_qty
            new_available = int(wloc["available_pairs"]) - place_qty
            new_status    = _recompute_status(new_occupied, int(wloc["capacity_pairs"]))
            res = await db.warehouse_locations.update_one(
                {"_id": wloc["_id"], "available_pairs": wloc["available_pairs"]},
                {"$set": {"occupied_pairs": new_occupied, "available_pairs": new_available,
                          "status": new_status, "updated_at": now_iso()}},
            )
            if res.modified_count == 0:
                continue
            await db.fg_location_inventory.update_one(
                {"_id": inv["_id"]},
                {"$inc": {"qty": place_qty},
                 "$set": {"style_code": style_code, "updated_at": now_iso()}},
            )
            placements.append({"location_code": code, "qty": place_qty,
                                "rack": wloc["rack"], "row": wloc["row"], "cell": wloc["cell"],
                                "zone": zone, "consolidated": True})
            remaining -= place_qty

    # Phase B — sequential fill from first empty/partial cell in zone
    while remaining > 0 and guard < 500:
        guard += 1
        loc = await db.warehouse_locations.find_one(
            {"available_pairs": {"$gt": 0}, "status": {"$ne": "blocked"}, "zone": zone},
            sort=[("location_code", 1)],
        )
        if not loc:
            log.warning(f"WMS: {zone} zone full — {remaining} pairs unplaced for {style_code}/{color}/{size}")
            break
        place_qty = min(remaining, int(loc["available_pairs"]))
        new_occupied  = int(loc["occupied_pairs"]) + place_qty
        new_available = int(loc["available_pairs"]) - place_qty
        new_status    = _recompute_status(new_occupied, int(loc["capacity_pairs"]))
        res = await db.warehouse_locations.update_one(
            {"_id": loc["_id"], "available_pairs": loc["available_pairs"]},
            {"$set": {
                "occupied_pairs":  new_occupied,
                "available_pairs": new_available,
                "status":          new_status,
                "updated_at":      now_iso(),
            }},
        )
        if res.modified_count == 0:
            continue
        await db.fg_location_inventory.update_one(
            {"style_id": sid_oid, "color": color, "size": size,
             "location_code": loc["location_code"]},
            {"$inc": {"qty": place_qty},
             "$set": {"style_code": style_code, "updated_at": now_iso()},
             "$setOnInsert": {"created_at": now_iso()}},
            upsert=True,
        )
        placements.append({"location_code": loc["location_code"], "qty": place_qty,
                            "rack": loc["rack"], "row": loc["row"], "cell": loc["cell"],
                            "zone": zone})
        remaining -= place_qty
    return {"placed_qty": int(qty) - remaining, "unplaced_qty": remaining, "placements": placements}


async def _deduct_from_locations(style_id, color, size, qty, user_email,
                                  reference_type="", reference_id="", zone=None, db=None) -> dict:
    """FIFO deduction: oldest fg_location_inventory doc first."""
    if db is None:
        db = getattr(__import__("server"), "db")
    remaining = int(qty)
    removals = []
    guard = 0
    allowed_codes = None
    if zone:
        allowed_codes = set()
        async for w in db.warehouse_locations.find({"zone": zone}, {"location_code": 1}):
            allowed_codes.add(w["location_code"])
    
    sid_oid = ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else str(style_id)

    while remaining > 0 and guard < 500:
        guard += 1
        q = {
            "$or": [{"style_id": sid_oid}, {"style_id": str(style_id)}],
            "color": color, "size": size, "qty": {"$gt": 0}
        }
        if allowed_codes is not None:
            q["location_code"] = {"$in": list(allowed_codes)}
        loc_inv = await db.fg_location_inventory.find_one(
            q, sort=[("created_at", 1), ("location_code", 1)],
        )
        if not loc_inv:
            break
        take = min(remaining, int(loc_inv["qty"]))
        new_qty = int(loc_inv["qty"]) - take
        if new_qty <= 0:
            await db.fg_location_inventory.delete_one({"_id": loc_inv["_id"]})
        else:
            await db.fg_location_inventory.update_one(
                {"_id": loc_inv["_id"]},
                {"$set": {"qty": new_qty, "updated_at": now_iso()}},
            )
        wloc = await db.warehouse_locations.find_one({"location_code": loc_inv["location_code"]})
        if wloc:
            new_occupied  = max(0, int(wloc["occupied_pairs"]) - take)
            new_available = min(int(wloc["capacity_pairs"]),
                                int(wloc["available_pairs"]) + take)
            new_status    = _recompute_status(new_occupied, int(wloc["capacity_pairs"])) \
                              if wloc.get("status") != "blocked" else "blocked"
            await db.warehouse_locations.update_one(
                {"_id": wloc["_id"]},
                {"$set": {"occupied_pairs": new_occupied,
                          "available_pairs": new_available,
                          "status": new_status,
                          "updated_at": now_iso()}},
            )
        removals.append({"location_code": loc_inv["location_code"], "qty": take})
        remaining -= take
    return {"deducted_qty": int(qty) - remaining, "shortfall": remaining, "removals": removals}


async def _deduct_from_specific_location(style_id, color, size, qty, location_code, db=None) -> bool:
    """Deduct qty from a specific location. Used by picklist confirm."""
    if db is None:
        db = getattr(__import__("server"), "db")
    qty = int(qty)
    sid_oid = ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else str(style_id)

    loc_inv = await db.fg_location_inventory.find_one({
        "$or": [{"style_id": sid_oid}, {"style_id": str(style_id)}],
        "color": color, "size": size,
        "location_code": location_code,
    })
    if not loc_inv:
        raise HTTPException(400, f"No stock of {color}/{size} at {location_code}")
    res = await db.fg_location_inventory.update_one(
        {"_id": loc_inv["_id"], "qty": {"$gte": qty}, "reserved_qty": {"$gte": qty}},
        {"$inc": {"qty": -qty, "reserved_qty": -qty}, "$set": {"updated_at": now_iso()}},
    )
    if not res.modified_count:
        latest = await db.fg_location_inventory.find_one({"_id": loc_inv["_id"]})
        have = int((latest or {}).get("qty", 0) or 0)
        reserved = int((latest or {}).get("reserved_qty", 0) or 0)
        raise HTTPException(400, f"Insufficient reserved stock at {location_code}: qty={have}, reserved={reserved}, need {qty}")
    wloc = await db.warehouse_locations.find_one({"location_code": location_code})
    if wloc:
        new_occ = max(0, int(wloc["occupied_pairs"]) - int(qty))
        new_av  = min(int(wloc["capacity_pairs"]), int(wloc["available_pairs"]) + int(qty))
        new_st  = _recompute_status(new_occ, int(wloc["capacity_pairs"])) \
                    if wloc.get("status") != "blocked" else "blocked"
        await db.warehouse_locations.update_one(
            {"_id": wloc["_id"]},
            {"$set": {"occupied_pairs": new_occ, "available_pairs": new_av,
                      "status": new_st, "updated_at": now_iso()}},
        )
    return True


async def _sync_warehouse_locations(payload, user_email: str, db=None):
    """Central hook called from _apply_movement(). Maps FG movements -> warehouse actions."""
    if db is None:
        db = getattr(__import__("server"), "db")
    mt = payload.movement_type
    qty = int(payload.quantity)
    style_id, color, size = payload.style_id, payload.color, payload.size
    
    style_oid = ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else str(style_id)
    style = await db.styles.find_one({"_id": style_oid})
    style_code = style.get("code", "") if style else ""
    ref = payload.reference_type
    ref_id = payload.reference_id or ""

    if mt in ("production_in",):
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main", db=db)
    elif mt == "return_restocked":
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main",
                                                 prefer_existing_sku_cells=True, db=db)
    elif mt == "return_in":
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main", db=db)
    elif mt in ("dispatched", "liquidation_out", "return_damaged"):
        if qty > 0:
            return await _deduct_from_locations(style_id, color, size, qty,
                                                 user_email, ref, ref_id, db=db)
    elif mt == "adjustment" and getattr(payload, "adjustment_field", None) == "ready_stock_qty":
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main", db=db)
        elif qty < 0:
            return await _deduct_from_locations(style_id, color, size, abs(qty),
                                                 user_email, ref, ref_id, db=db)
    return None


async def _find_style_home_cell(style_id: str, db=None) -> Optional[str]:
    """Return the location_code where this style is currently stocked with the most qty."""
    if db is None:
        db = getattr(__import__("server"), "db")
    try:
        oid_v = ObjectId(style_id)
    except Exception:
        return None
    pipeline = [
        {"$match": {"$or": [{"style_id": oid_v}, {"style_id": str(style_id)}], "qty": {"$gt": 0}}},
        {"$group": {"_id": "$location_code", "total": {"$sum": "$qty"}}},
        {"$sort": {"total": -1}},
        {"$limit": 1},
    ]
    docs = await db.fg_location_inventory.aggregate(pipeline).to_list(1)
    return docs[0]["_id"] if docs else None


async def _pick_new_cell_for_style(style_id: str, db=None) -> Optional[str]:
    """When a style has never been stocked, pick the first empty main cell."""
    if db is None:
        db = getattr(__import__("server"), "db")
    home = await _find_style_home_cell(style_id, db=db)
    if home:
        return home
    async for w in db.warehouse_locations.find(
        {"zone": "main", "status": "empty"}
    ).sort([("row", 1), ("rack", 1), ("cell", 1)]).limit(1):
        return w["location_code"]
    return None


async def _next_picklist_no(db=None) -> str:
    """PL-YYYYMMDD-NNN sequential."""
    if db is None:
        db = getattr(__import__("server"), "db")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"PL-{today}-"
    last = await db.picklists.find({"picklist_no": {"$regex": f"^{prefix}"}}) \
                             .sort("picklist_no", -1).limit(1).to_list(1)
    seq = 1
    if last:
        try:
            seq = int(last[0]["picklist_no"].split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:03d}"


async def _generate_picklist_for_order(order_id: str, channel: str, order_lines: List[dict],
                                        user_email: str, db=None) -> Tuple[dict, dict, dict]:
    """Build a picklist for an online order using FIFO allocation."""
    if db is None:
        db = getattr(__import__("server"), "db")

    items = []
    covered = {}     # (style_id,color,size) -> qty covered
    uncovered = {}   # (style_id,color,size) -> qty short
    reservations_to_book = []
    loc_reservations_to_book = []

    for line in order_lines:
        style_id   = line.get("style_id")
        style_code = line.get("style_code", "")
        color      = line.get("color", "")
        size       = line.get("size", "")
        need       = int(line.get("quantity", 0))
        if not style_id or need <= 0:
            continue
        
        remaining = need
        picked = []
        sid_oid = ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else str(style_id)
        q_loc = {
            "$or": [{"style_id": sid_oid}, {"style_id": str(style_id)}],
            "qty": {"$gt": 0},
        }
        color_val = (color or "").strip()
        size_val  = (size  or "").strip()
        if color_val:
            q_loc["color"] = {"$regex": f"^{re.escape(color_val)}$", "$options": "i"}
        if size_val:
            q_loc["size"]  = {"$regex": f"^{re.escape(size_val)}$",  "$options": "i"}

        cur = db.fg_location_inventory.find(q_loc).sort([("created_at", 1), ("location_code", 1)])
        async for loc in cur:
            if remaining <= 0:
                break
            wloc_check = await db.warehouse_locations.find_one({"location_code": loc.get("location_code")})
            if wloc_check and wloc_check.get("status") == "blocked":
                continue
            qty_val = int(loc.get("qty", 0) or 0)
            res_val = int(loc.get("reserved_qty", 0) or 0)
            free_here = qty_val - res_val
            if free_here <= 0:
                continue
            take = min(remaining, free_here)
            picked.append({
                "loc_inv_id":    loc["_id"],
                "location_code": loc["location_code"], "qty": take,
                "style_id":      str(loc["style_id"]), "style_code": style_code,
                "color":         color, "size": size,
            })
            remaining -= take

        codes = list({p["location_code"] for p in picked})
        wloc_map = {}
        if codes:
            async for w in db.warehouse_locations.find({"location_code": {"$in": codes}}):
                wloc_map[w["location_code"]] = w
        for p in picked:
            w = wloc_map.get(p["location_code"], {})
            item = {
                "style_id":      p["style_id"], "style_code": p["style_code"],
                "color":         p["color"],    "size":       p["size"],
                "location_code": p["location_code"], "qty":    p["qty"],
                "rack":          w.get("rack"), "row":        w.get("row"),
                "cell":          w.get("cell"),
                "picked":        False, "picked_at": None,
            }
            items.append(item)
            loc_reservations_to_book.append((p["loc_inv_id"], p["qty"]))

        covered_qty = need - remaining
        if covered_qty > 0:
            covered[(style_id, color, size)] = covered_qty
            reservations_to_book.append({
                "style_id": style_id, "color": color, "size": size,
                "qty": covered_qty, "style_code": style_code,
            })
        if remaining > 0:
            uncovered[(style_id, color, size)] = remaining

    picklist_no = await _next_picklist_no(db=db)
    doc = {
        "picklist_no": picklist_no,
        "order_id":    order_id,
        "channel":     channel,
        "status":      "pending",
        "picker":      None,
        "items":       items,
        "total_items": len(items),
        "total_qty":   sum(i["qty"] for i in items),
        "created_at":  now_iso(),
        "updated_at":  now_iso(),
        "created_by":  user_email,
        "completed_at": None,
    }
    if items:
        # Book location-level reservations
        booked_loc_reservations = []
        for loc_inv_id, take in loc_reservations_to_book:
            try:
                take = int(take)
                res = await db.fg_location_inventory.update_one(
                    {
                        "_id": loc_inv_id,
                        "$expr": {"$gte": [{"$subtract": ["$qty", {"$ifNull": ["$reserved_qty", 0]}]}, take]},
                    },
                    {"$inc": {"reserved_qty": take}, "$set": {"updated_at": now_iso()}},
                )
                if not res.modified_count:
                    raise HTTPException(409, "Stock was allocated by another request; retry picklist generation")
                booked_loc_reservations.append((loc_inv_id, take))
            except Exception as e:
                for booked_id, booked_qty in booked_loc_reservations:
                    await db.fg_location_inventory.update_one(
                        {"_id": booked_id},
                        {"$inc": {"reserved_qty": -int(booked_qty)}, "$set": {"updated_at": now_iso()}},
                    )
                if isinstance(e, HTTPException):
                    raise
                log.warning(f"Location reservation increment failed: {e}")
                raise HTTPException(409, "Could not reserve WMS stock for picklist")
        
        # Book SKU-level reservations for covered portion
        for r in reservations_to_book:
            try:
                mv = FgStockMovementIn(
                    style_id=r["style_id"], color=r["color"], size=r["size"],
                    movement_type="reserved", quantity=int(r["qty"]),
                    reference_type="online_order", reference_id=order_id,
                    online_order_id=order_id, notes=f"Auto-reserved for picklist {picklist_no}",
                )
                await _apply_movement(mv, user_email, skip_location_sync=True)
            except Exception as e:
                log.warning(f"Reservation booking failed for {r}: {e}")
        res = await db.picklists.insert_one(doc)
        doc["_id"] = res.inserted_id
    return doc, covered, uncovered


# ── Warehouse Endpoints ──────────────────────────────────────────────────

@wms_router.get("/warehouse/locations")
async def wms_list_locations(
    request: Request,
    rack: Optional[str] = None,
    status: Optional[str] = None,
    zone: Optional[str] = None,
    search: Optional[str] = None,
):
    """List all warehouse cells with capacity/occupied stats."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {}
    if rack:
        try:
            q["rack"] = int(rack)
        except ValueError:
            q["rack"] = rack.upper()
    if status: q["status"] = status
    if zone:   q["zone"] = zone
    if search: q["location_code"] = {"$regex": search, "$options": "i"}
    docs = await db.warehouse_locations.find(q).sort("location_code", 1).to_list(500)
    return [stringify(d) for d in docs]


@wms_router.patch("/warehouse/locations/{code}/block")
async def wms_block_location(request: Request, code: str, payload: LocationBlockIn):
    """Block or unblock a cell for repairs / maintenance / damage."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    code = code.upper().strip()
    loc = await db.warehouse_locations.find_one({"location_code": code})
    if not loc:
        raise HTTPException(404, "Location not found")
    if payload.blocked:
        new_status = "blocked"
        upd = {"status": new_status, "block_reason": payload.reason or "manually blocked",
               "blocked_at": now_iso(), "blocked_by": u["email"], "updated_at": now_iso()}
    else:
        new_status = _recompute_status(int(loc["occupied_pairs"]), int(loc["capacity_pairs"]))
        upd = {"status": new_status, "block_reason": None,
               "blocked_at": None, "blocked_by": None, "updated_at": now_iso()}
    await db.warehouse_locations.update_one({"_id": loc["_id"]}, {"$set": upd})
    await log_activity("UPDATE", "warehouse_locations",
                        f"{'Blocked' if payload.blocked else 'Unblocked'} {code}: {payload.reason or '-'}", u["email"], db=db)
    return stringify(await db.warehouse_locations.find_one({"_id": loc["_id"]}))


@wms_router.get("/warehouse/locations/{code}")
async def wms_get_location(request: Request, code: str):
    """Get one cell + list all SKUs stored in it."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    loc = await db.warehouse_locations.find_one({"location_code": code.upper()})
    if not loc:
        raise HTTPException(404, "Location not found")
    contents = await db.fg_location_inventory.find({"location_code": code.upper()}).to_list(500)
    return {"location": stringify(loc), "contents": [stringify(c) for c in contents]}


@wms_router.post("/warehouse/seed-locations")
async def wms_seed(request: Request):
    """Idempotently seed all cells for the current layout."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    inserted = await _seed_warehouse_locations(db=db)
    total = await db.warehouse_locations.count_documents({})
    return {"inserted": inserted, "total": total}


@wms_router.post("/warehouse/rebuild-layout")
async def wms_rebuild_layout(request: Request):
    """DESTRUCTIVE: drop `warehouse_locations` and reseed with the current layout."""
    u = await _get_user(request)
    require_roles("admin")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    dropped = await db.warehouse_locations.count_documents({})
    await db.warehouse_locations.delete_many({})
    inserted = await _seed_warehouse_locations(db=db)

    now = now_iso()
    moved   = 0
    skipped = 0
    style_home: dict = {}
    fill: dict = {}

    async def _next_cell_for(style_id: str, qty_needed: int) -> Optional[str]:
        home = style_home.get(style_id)
        if home and fill.get(home, 0) + qty_needed <= CAPACITY:
            return home
        async for w in db.warehouse_locations.find({"zone": "main"}).sort([("row", 1), ("rack", 1), ("cell", 1)]):
            code = w["location_code"]
            if fill.get(code, 0) + qty_needed <= CAPACITY:
                style_home[style_id] = code
                return code
        return None

    cur = db.fg_location_inventory.find({}).sort([("style_id", 1), ("color", 1), ("size", 1)])
    async for inv in cur:
        qty = int(inv.get("qty", 0))
        if qty <= 0:
            await db.fg_location_inventory.delete_one({"_id": inv["_id"]})
            continue
        sid = str(inv.get("style_id"))
        new_code = await _next_cell_for(sid, qty)
        if not new_code:
            skipped += 1
            continue
        cell = await db.warehouse_locations.find_one({"location_code": new_code})
        await db.fg_location_inventory.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "location_code": new_code,
                "rack":          cell.get("rack") if cell else None,
                "row":           cell.get("row")  if cell else None,
                "cell":          cell.get("cell") if cell else None,
                "updated_at":    now,
            }},
        )
        fill[new_code] = fill.get(new_code, 0) + qty
        moved += 1

    for code, occ in fill.items():
        await db.warehouse_locations.update_one(
            {"location_code": code},
            {"$set": {
                "occupied_pairs":  occ,
                "available_pairs": max(0, CAPACITY - occ),
                "status":          _recompute_status(occ, CAPACITY),
                "updated_at":      now,
            }},
        )
    return {
        "dropped_cells":  dropped,
        "inserted_cells": inserted,
        "capacity_per_cell": CAPACITY,
        "total_capacity_pairs": CAPACITY * inserted,
        "fg_locations_migrated": moved,
        "fg_locations_skipped_no_room": skipped,
        "style_home_assignments": len(style_home),
    }


@wms_router.get("/warehouse/fg-locations")
async def wms_fg_location_inventory(
    request: Request,
    style_id: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    location_code: Optional[str] = None,
):
    """List fg_location_inventory rows."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {}
    if style_id:
        try:
            q["$or"] = [{"style_id": ObjectId(style_id)}, {"style_id": str(style_id)}]
        except Exception:
            q["style_id"] = str(style_id)
    if color: q["color"] = color
    if size:  q["size"] = size
    if location_code: q["location_code"] = location_code.upper()
    docs = await db.fg_location_inventory.find(q).sort("location_code", 1).to_list(2000)
    return [stringify(d) for d in docs]


@wms_router.get("/warehouse/dashboard")
async def wms_dashboard(request: Request):
    """Aggregate stats for the warehouse dashboard."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    locs = await db.warehouse_locations.find({}).to_list(1000)
    total_cells      = len(locs)
    total_capacity   = sum(int(l.get("capacity_pairs", 0))  for l in locs)
    total_occupied   = sum(int(l.get("occupied_pairs", 0))  for l in locs)
    total_available  = sum(int(l.get("available_pairs", 0)) for l in locs)
    empty_cells      = sum(1 for l in locs if l.get("status") == "empty")
    partial_cells    = sum(1 for l in locs if l.get("status") == "partial")
    full_cells       = sum(1 for l in locs if l.get("status") == "full")
    blocked_cells    = sum(1 for l in locs if l.get("status") == "blocked")

    by_rack = {}
    for r in RACKS:
        rlocs = [l for l in locs if l.get("rack") == r]
        by_rack[r] = {
            "total_cells":     len(rlocs),
            "occupied_pairs":  sum(int(l.get("occupied_pairs", 0)) for l in rlocs),
            "available_pairs": sum(int(l.get("available_pairs", 0)) for l in rlocs),
            "capacity_pairs":  sum(int(l.get("capacity_pairs", 0)) for l in rlocs),
            "empty_cells":     sum(1 for l in rlocs if l.get("status") == "empty"),
            "partial_cells":   sum(1 for l in rlocs if l.get("status") == "partial"),
            "full_cells":      sum(1 for l in rlocs if l.get("status") == "full"),
        }

    active_picklists   = await db.picklists.count_documents({"status": {"$in": ["pending", "in_progress"]}})
    pending_picklists  = await db.picklists.count_documents({"status": "pending"})
    completed_today    = await db.picklists.count_documents({
        "status": "completed",
        "completed_at": {"$gte": now_iso()[:10] + "T00:00:00Z"},
    })

    distinct_skus = len(await db.fg_location_inventory.distinct("style_id"))
    utilization_pct = round((total_occupied / total_capacity * 100), 2) if total_capacity else 0

    by_zone = {
        "main": {
            "cells":           len(locs),
            "capacity_pairs":  total_capacity,
            "occupied_pairs":  total_occupied,
            "available_pairs": total_available,
        },
    }

    return {
        "total_cells":       total_cells,
        "total_capacity":    total_capacity,
        "total_occupied":    total_occupied,
        "total_available":   total_available,
        "utilization_pct":   utilization_pct,
        "empty_cells":       empty_cells,
        "partial_cells":     partial_cells,
        "full_cells":        full_cells,
        "blocked_cells":     blocked_cells,
        "distinct_skus":     distinct_skus,
        "active_picklists":  active_picklists,
        "pending_picklists": pending_picklists,
        "completed_today":   completed_today,
        "by_rack":           by_rack,
        "by_zone":           by_zone,
    }


# ── Picklist Endpoints ───────────────────────────────────────────────────

@wms_router.get("/picklists")
async def list_picklists(
    request: Request,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    order_id: Optional[str] = None,
    picker: Optional[str] = None,
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {}
    if status:   q["status"] = status
    if channel:  q["channel"] = channel.lower()
    if order_id: q["order_id"] = order_id
    if picker:   q["picker"] = picker
    docs = await db.picklists.find(q).sort("created_at", -1).to_list(500)
    return [stringify(d) for d in docs]


@wms_router.get("/picklists/{pid}")
async def get_picklist(request: Request, pid: str):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    try:
        doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(404, "Picklist not found")
    
    style_ids = list({ObjectId(i["style_id"]) for i in doc.get("items", []) if i.get("style_id") and ObjectId.is_valid(str(i["style_id"]))})
    style_map: dict = {}
    if style_ids:
        async for s in db.styles.find({"_id": {"$in": style_ids}}):
            style_map[str(s["_id"])] = {
                "image_url":              s.get("image_url", ""),
                "image_display_url":      s.get("image_display_url", ""),
                "image_thumbnail_url":    s.get("image_thumbnail_url", ""),
                "style_name":             s.get("name", ""),
            }
    for it in doc.get("items", []):
        info = style_map.get(str(it.get("style_id")), {})
        it["image_url"]           = info.get("image_url", "")
        it["image_display_url"]   = info.get("image_display_url", "")
        it["image_thumbnail_url"] = info.get("image_thumbnail_url", "")
        it["style_name"]          = info.get("style_name", "")
    return stringify(doc)


@wms_router.post("/picklists")
async def create_picklist(request: Request, payload: PicklistIn):
    """Manually create a picklist."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    lines = [{
        "style_id": i.style_id, "style_code": i.style_code,
        "color": i.color, "size": i.size, "quantity": i.qty,
    } for i in payload.items]
    doc, covered, uncovered = await _generate_picklist_for_order(
        payload.order_id, payload.channel, lines, u["email"], db=db)
    return {"picklist": stringify(doc),
            "covered": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in covered.items()},
            "uncovered": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in uncovered.items()}}


@wms_router.patch("/picklists/{pid}")
async def patch_picklist(request: Request, pid: str, payload: PicklistPatchIn):
    u = await _get_user(request)
    require_roles("admin", "manager", "production", "operator")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    upd = {"updated_at": now_iso()}
    if payload.picker is not None: upd["picker"] = payload.picker
    if payload.status is not None: upd["status"] = payload.status
    try:
        res = await db.picklists.update_one({"_id": ObjectId(pid)}, {"$set": upd})
    except Exception:
        raise HTTPException(404, "Picklist not found")
    if not res.matched_count:
        raise HTTPException(404, "Picklist not found")
    doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    return stringify(doc)


@wms_router.post("/picklists/{pid}/pick-item")
async def pick_item(request: Request, pid: str, payload: PickItemIn):
    """Confirm a pick: verify scan matches, deduct from that specific location."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production", "operator")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    try:
        doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(404, "Picklist not found")
    if payload.item_index < 0 or payload.item_index >= len(doc.get("items", [])):
        raise HTTPException(400, "Invalid item_index")
    if doc.get("status") in ("cancelled", "completed"):
        raise HTTPException(400, f"Cannot pick item from {doc.get('status')} picklist")
    item = doc["items"][payload.item_index]
    if item.get("picked"):
        raise HTTPException(400, "Item already picked")
    if payload.scanned_location.upper().strip() != item["location_code"].upper():
        raise HTTPException(400,
            f"Scan mismatch — expected {item['location_code']}, got {payload.scanned_location}")
    wloc = await db.warehouse_locations.find_one({"location_code": item["location_code"]})
    if wloc and wloc.get("status") == "blocked":
        raise HTTPException(400, f"Location {item['location_code']} is blocked")

    now = now_iso()
    claim = await db.picklists.update_one(
        {"_id": ObjectId(pid), "status": {"$nin": ["cancelled", "completed"]}, f"items.{payload.item_index}.picked": {"$ne": True}},
        {"$set": {f"items.{payload.item_index}.picked": True, f"items.{payload.item_index}.picked_at": now, f"items.{payload.item_index}.picked_by": u["email"], "updated_at": now}},
    )
    if not claim.modified_count:
        raise HTTPException(400, "Item already picked or picklist is closed")

    # Deduct qty from that exact location
    await _deduct_from_specific_location(
        item["style_id"], item["color"], item["size"],
        int(item["qty"]), item["location_code"], db=db
    )

    # Post the 'dispatched' ledger row
    try:
        mv = FgStockMovementIn(
            style_id=item["style_id"], color=item["color"], size=item["size"],
            movement_type="dispatched", quantity=int(item["qty"]),
            reference_type="online_order", reference_id=doc["order_id"],
            online_order_id=doc["order_id"], notes=f"Picklist {doc['picklist_no']} item {payload.item_index}",
        )
        await _apply_movement(mv, u["email"], skip_location_sync=True)
    except Exception as e:
        log.warning(f"Dispatched ledger failed: {e}")

    doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    all_picked = all(bool(i.get("picked")) for i in doc["items"])
    new_status = "completed" if all_picked else "in_progress"
    upd = {"items": doc["items"], "status": new_status, "updated_at": now}
    if all_picked:
        upd["completed_at"] = now
    await db.picklists.update_one({"_id": ObjectId(pid)}, {"$set": upd})
    updated = await db.picklists.find_one({"_id": ObjectId(pid)})
    return stringify(updated)


@wms_router.delete("/picklists/{pid}")
async def delete_picklist(request: Request, pid: str):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    try:
        doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(404, "Picklist not found")
    if doc.get("status") == "completed":
        raise HTTPException(400, "Cannot delete a completed picklist. Use returns flow instead.")
    
    # Release location-level reservations on unpicked items
    for it in doc.get("items", []):
        if it.get("picked"):
            continue
        try:
            sid_oid = ObjectId(it["style_id"]) if ObjectId.is_valid(str(it["style_id"])) else str(it["style_id"])
            await db.fg_location_inventory.update_one(
                {"$or": [{"style_id": sid_oid}, {"style_id": str(it["style_id"])}],
                 "color": it["color"], "size": it["size"], "location_code": it["location_code"]},
                {"$inc": {"reserved_qty": -int(it["qty"])}, "$set": {"updated_at": now_iso()}},
            )
        except Exception:
            pass
            
    # Release active reservations tied to this order
    if doc.get("order_id"):
        await db.inventory_reservations.update_many(
            {"online_order_id": doc["order_id"], "status": "active"},
            {"$set": {"status": "released", "released_at": now_iso()}},
        )
        for it in doc.get("items", []):
            if it.get("picked"):
                continue
            try:
                mv = FgStockMovementIn(
                    style_id=it["style_id"], color=it["color"], size=it["size"],
                    movement_type="unreserved", quantity=int(it["qty"]),
                    reference_type="online_order", reference_id=doc["order_id"],
                    online_order_id=doc["order_id"],
                    notes=f"Picklist {doc['picklist_no']} cancelled",
                )
                await _apply_movement(mv, u["email"], skip_location_sync=True)
            except Exception:
                pass
    await db.picklists.delete_one({"_id": ObjectId(pid)})
    return {"ok": True}


# ── Warehouse Reports ────────────────────────────────────────────────────

@wms_router.get("/warehouse/reports/capacity")
async def report_capacity(request: Request):
    """Total capacity, used, available; per-rack breakdown."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    locs = await db.warehouse_locations.find({}).to_list(1000)
    total_capacity  = sum(int(l.get("capacity_pairs", 0))  for l in locs)
    total_occupied  = sum(int(l.get("occupied_pairs", 0))  for l in locs)
    total_available = sum(int(l.get("available_pairs", 0)) for l in locs)
    by_rack = []
    for r in RACKS:
        rlocs = [l for l in locs if l.get("rack") == r]
        cap = sum(int(l.get("capacity_pairs", 0)) for l in rlocs)
        occ = sum(int(l.get("occupied_pairs", 0)) for l in rlocs)
        by_rack.append({
            "rack": r,
            "cells": len(rlocs),
            "capacity_pairs":  cap,
            "occupied_pairs":  occ,
            "available_pairs": cap - occ,
            "utilization_pct": round((occ / cap * 100), 2) if cap else 0,
        })
    return {
        "total_cells":     len(locs),
        "total_capacity":  total_capacity,
        "total_occupied":  total_occupied,
        "total_available": total_available,
        "utilization_pct": round((total_occupied / total_capacity * 100), 2) if total_capacity else 0,
        "by_rack":         by_rack,
    }


@wms_router.get("/warehouse/reports/location-utilization")
async def report_location_utilization(request: Request):
    """Per-cell utilization + top 20 fullest and 20 emptiest."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    locs = await db.warehouse_locations.find({}).to_list(1000)
    rows = []
    for l in locs:
        cap = int(l.get("capacity_pairs", 0) or 0)
        occ = int(l.get("occupied_pairs", 0) or 0)
        rows.append({
            "location_code":   l["location_code"],
            "rack":            l.get("rack"),
            "row":             l.get("row"),
            "cell":            l.get("cell"),
            "capacity_pairs":  cap,
            "occupied_pairs":  occ,
            "available_pairs": cap - occ,
            "utilization_pct": round((occ / cap * 100), 2) if cap else 0,
            "status":          l.get("status"),
        })
    rows.sort(key=lambda r: r["location_code"])
    fullest = sorted(rows, key=lambda r: -r["utilization_pct"])[:20]
    emptiest = sorted([r for r in rows if r["utilization_pct"] < 100], key=lambda r: r["utilization_pct"])[:20]
    return {"rows": rows, "fullest": fullest, "emptiest": emptiest}


@wms_router.get("/warehouse/reports/picking-efficiency")
async def report_picking_efficiency(request: Request, days: int = 30):
    """Picker efficiency: picks/hour, avg completion time, orders picked."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    picklists = await db.picklists.find({
        "status": "completed",
        "completed_at": {"$gte": since},
    }).to_list(2000)
    per_picker = {}
    grand = {"picklists": 0, "items": 0, "qty": 0, "avg_minutes": 0}
    total_minutes = 0.0
    total_pl = 0
    for pl in picklists:
        picker = pl.get("picker") or pl.get("created_by") or "unknown"
        try:
            started = pl.get("created_at", "").replace("Z", "+00:00")
            ended = pl.get("completed_at", "").replace("Z", "+00:00")
            t1 = datetime.fromisoformat(started)
            t2 = datetime.fromisoformat(ended)
            minutes = max(0.0, (t2 - t1).total_seconds() / 60.0)
        except Exception:
            minutes = 0.0
        items_count = len(pl.get("items", []))
        qty_count = sum(int(i.get("qty", 0)) for i in pl.get("items", []))
        row = per_picker.setdefault(picker, {"picker": picker, "picklists": 0,
                                              "items": 0, "qty": 0, "total_minutes": 0.0})
        row["picklists"] += 1
        row["items"]     += items_count
        row["qty"]       += qty_count
        row["total_minutes"] += minutes
        total_minutes += minutes
        total_pl += 1
        grand["picklists"] += 1
        grand["items"]     += items_count
        grand["qty"]       += qty_count

    for row in per_picker.values():
        row["avg_minutes_per_picklist"] = round(row["total_minutes"] / max(row["picklists"], 1), 2)
        row["items_per_hour"] = round((row["items"] / row["total_minutes"] * 60), 2) if row["total_minutes"] else 0
        row["total_minutes"] = round(row["total_minutes"], 2)
    grand["avg_minutes_per_picklist"] = round(total_minutes / max(total_pl, 1), 2)
    grand["items_per_hour"] = round((grand["items"] / total_minutes * 60), 2) if total_minutes else 0
    return {"days": int(days), "grand_total": grand,
            "per_picker": sorted(per_picker.values(), key=lambda r: -r["picklists"])}


# ── Pending Product List & Production Matrix ─────────────────────────────

@wms_router.get("/production/pending-list")
async def pending_product_list(request: Request):
    """Online-channel production jobs not yet dispatched, with component-availability flag."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    jobs = await db.production_jobs.find({
        "source_type": "online_channel",
        "stage": {"$ne": "dispatched"},
    }).sort("created_at", 1).to_list(2000)

    style_ids = list({str(j.get("style_id")) for j in jobs if j.get("style_id")})
    comp_stock_by_style = {}
    for sid in style_ids:
        try:
            oid_val = ObjectId(sid)
        except Exception:
            comp_stock_by_style[sid] = {"components_available": False, "shortages": []}
            continue
        bom = await db.style_component_mapping.find({
            "style_id": oid_val, "active": {"$ne": False},
        }).to_list(200)
        if not bom:
            comp_stock_by_style[sid] = {"components_available": True, "shortages": [],
                                         "note": "No BOM mapped"}
            continue
        shortages = []
        ok = True
        for b in bom:
            comp = await db.component_master.find_one({"_id": ObjectId(b["component_id"])})
            if not comp:
                continue
            cur = int(comp.get("current_stock", 0)) - int(comp.get("reserved_stock", 0))
            need_per_pair = float(b.get("quantity_per_pair", b.get("qty_per_pair", 1)) or 1)
            if cur <= 0:
                ok = False
                shortages.append({
                    "component_code": comp.get("component_code"),
                    "component_name": comp.get("component_name"),
                    "available":      cur,
                    "per_pair":       need_per_pair,
                })
        comp_stock_by_style[sid] = {"components_available": ok, "shortages": shortages}

    out = []
    style_lookup: dict = {}
    if style_ids:
        style_object_ids = [ObjectId(sid) for sid in style_ids if ObjectId.is_valid(sid)]
        if style_object_ids:
            async for s in db.styles.find({"_id": {"$in": style_object_ids}}):
                style_lookup[str(s["_id"])] = {
                    "image_url":              s.get("image_url", ""),
                    "image_display_url":      s.get("image_display_url", ""),
                    "image_thumbnail_url":    s.get("image_thumbnail_url", ""),
                    "style_name":             s.get("name", ""),
                }
    for j in jobs:
        jd = stringify(j)
        sid = jd.get("style_id")
        info = comp_stock_by_style.get(sid, {"components_available": False, "shortages": []})
        jd["components_available"] = bool(info.get("components_available"))
        jd["component_shortages"]  = info.get("shortages", [])
        s_meta = style_lookup.get(sid, {})
        jd["image_url"]           = s_meta.get("image_url", "")
        jd["image_display_url"]   = s_meta.get("image_display_url", "")
        jd["image_thumbnail_url"] = s_meta.get("image_thumbnail_url", "")
        jd["style_name"]          = s_meta.get("style_name", "")
        out.append(jd)
    out.sort(key=lambda x: (not x.get("components_available"), x.get("created_at", "")))
    return out


@wms_router.post("/production/pending-list/snapshot")
async def create_pending_list_snapshot(request: Request, payload: Optional[dict] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    filter_used = (payload or {}).get("filter_used", "all")
    
    jobs = await pending_product_list(request)
    
    pending = len(jobs)
    ready = sum(1 for j in jobs if j.get("components_available"))
    shortage = sum(1 for j in jobs if not j.get("components_available"))
    total_pairs = sum(int(j.get("quantity", 0)) for j in jobs)
    
    doc = {
        "saved_at": now_iso(),
        "saved_by": u["email"],
        "filter_used": filter_used,
        "totals": {
            "pending": pending,
            "ready": ready,
            "shortage": shortage,
            "total_pairs": total_pairs
        },
        "jobs": jobs
    }
    
    res = await db.pending_list_snapshots.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@wms_router.get("/production/pending-list/snapshots")
async def list_pending_list_snapshots(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    docs = await db.pending_list_snapshots.find({}, {"jobs": 0}).sort("saved_at", -1).to_list(1000)
    return [stringify(d) for d in docs]


@wms_router.get("/production/pending-list/snapshots/{id}")
async def get_pending_list_snapshot(id: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.pending_list_snapshots.find_one({"_id": oid(id)})
    if not doc:
        raise HTTPException(404, "Snapshot not found")
    return stringify(doc)


@wms_router.post("/production/produce-cell")
async def produce_cell(request: Request, payload: ProduceCellIn):
    """Complete production for a specific (style, color, size) cell."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    if payload.produced_qty <= 0:
        raise HTTPException(400, "produced_qty must be > 0")

    sid_oid = ObjectId(payload.style_id) if ObjectId.is_valid(str(payload.style_id)) else str(payload.style_id)

    q: dict = {
        "$or": [{"style_id": sid_oid}, {"style_id": str(payload.style_id)}],
        "color":    payload.color,
        "size":     payload.size,
        "stage":    {"$ne": "dispatched"},
    }
    if payload.channel_filter == "online_channel":
        q["source_type"] = "online_channel"
    elif payload.channel_filter == "b2b_client":
        q["source_type"] = {"$in": ["b2b_client", None]}

    jobs = await db.production_jobs.find(q).sort("created_at", 1).to_list(500)
    pending_total = sum(int(j.get("quantity", 0)) - int(j.get("completed_qty", 0) or 0) for j in jobs)

    style = await db.styles.find_one({"$or": [{"_id": sid_oid}, {"_id": str(payload.style_id)}]})
    if not style:
        raise HTTPException(404, "Style not found")
    style_code = style.get("code", "")

    produced = int(payload.produced_qty)
    is_short = produced < pending_total
    is_over  = produced > pending_total
    if is_short and not (payload.reason or "").strip():
        raise HTTPException(422, "Short production must include a reason.")

    bom_used: list[dict] = []
    if payload.use_components:
        bom = await db.style_component_mapping.find({
            "$or": [{"style_id": sid_oid}, {"style_id": str(payload.style_id)}],
            "active": {"$ne": False},
        }).to_list(200)
        if not bom:
            raise HTTPException(
                412,
                {"code": "no_production_card",
                 "message": "No production card (BOM) mapped for this style. "
                            "Create one before consuming components — or set use_components=false to skip.",
                 "style_id": payload.style_id, "style_code": style_code},
            )
        shortages: list[dict] = []
        deductions: list[tuple[dict, int]] = []
        for b in bom:
            per   = float(b.get("quantity_per_pair", b.get("qty_per_pair", 1)) or 1)
            waste = float(b.get("wastage_percent", 0) or 0) / 100.0
            deduct = int(round(produced * per * (1 + waste)))
            if deduct <= 0:
                continue
            comp = await db.component_master.find_one({"_id": ObjectId(b["component_id"])})
            if not comp:
                continue
            current = int(comp.get("current_stock", 0))
            if deduct > current:
                shortages.append({
                    "component_id":   str(comp["_id"]),
                    "component_code": comp.get("component_code"),
                    "component_name": comp.get("component_name"),
                    "needed":         deduct,
                    "available":      current,
                    "shortfall":      deduct - current,
                })
            deductions.append((comp, deduct))
        if shortages and not payload.force_negative_stock:
            raise HTTPException(
                409,
                {"code": "component_shortage",
                 "message": f"{len(shortages)} component(s) would go below zero. Re-submit with force_negative_stock=true to proceed anyway.",
                 "style_code": style_code,
                 "produced":   produced,
                 "shortages":  shortages},
            )
        for comp, deduct in deductions:
            new_stock = int(comp.get("current_stock", 0)) - deduct
            await db.component_master.update_one(
                {"_id": comp["_id"]},
                {"$set": {"current_stock": new_stock, "updated_at": now_iso()},
                 "$push": {"history": {"event": "produce_cell", "at": now_iso(),
                                       "by": u["email"], "style_code": style_code,
                                       "color": payload.color, "size": payload.size,
                                       "pairs": produced, "deducted": deduct,
                                       "new_stock": new_stock}}},
            )
            bom_used.append({
                "component_id":   str(comp["_id"]),
                "component_code": comp.get("component_code"),
                "component_name": comp.get("component_name"),
                "deducted":       deduct,
                "new_stock":      new_stock,
            })

    remaining_to_cover = min(produced, pending_total)
    covered_job_ids: list[str] = []
    for j in jobs:
        if remaining_to_cover <= 0:
            break
        job_pending = int(j.get("quantity", 0)) - int(j.get("completed_qty", 0) or 0)
        take = min(job_pending, remaining_to_cover)
        new_completed = int(j.get("completed_qty", 0) or 0) + take
        new_stage = payload.dispatch_stage if new_completed >= int(j.get("quantity", 0)) else "packing"
        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {"$set": {"completed_qty": new_completed, "stage": new_stage, "updated_at": now_iso()},
             "$push": {"history": {"event": "produced", "at": now_iso(), "by": u["email"],
                                   "produced_qty": take, "new_completed": new_completed,
                                   "reason": payload.reason or ""}}},
        )
        covered_job_ids.append(str(j["_id"]))
        remaining_to_cover -= take

    shortfall = pending_total - produced if is_short else 0
    if is_short:
        await db.short_production_log.insert_one({
            "style_id":    payload.style_id,
            "style_code":  style_code,
            "color":       payload.color,
            "size":        payload.size,
            "pending_qty": pending_total,
            "produced_qty": produced,
            "shortfall":   shortfall,
            "reason":      payload.reason or "",
            "logged_by":   u["email"],
            "created_at":  now_iso(),
        })

    excess = produced - pending_total if is_over else 0
    excess_placed_at: Optional[str] = None
    if excess > 0:
        home = await _pick_new_cell_for_style(payload.style_id, db=db) or "R01-RK1-C01"
        excess_placed_at = home
        try:
            mv = FgStockMovementIn(
                style_id=payload.style_id, color=payload.color, size=payload.size,
                movement_type="production_in", quantity=int(excess),
                reference_type="produce_cell_excess", reference_id="",
                notes=f"Excess of {excess} pairs over pending {pending_total} for {style_code}",
            )
            await _apply_movement(mv, u["email"], skip_location_sync=True)
        except Exception:
            log.exception("Excess fg_stock movement failed")
        
        cell = await db.warehouse_locations.find_one({"location_code": home})
        capacity = int(cell.get("capacity_pairs", CAPACITY)) if cell else CAPACITY
        room = capacity - int(cell.get("occupied_pairs", 0)) if cell else capacity
        put_here = min(excess, room)
        if put_here > 0:
            await db.fg_location_inventory.update_one(
                {"style_id": sid_oid, "color": payload.color,
                 "size": payload.size, "location_code": home},
                {"$inc": {"qty": put_here},
                 "$setOnInsert": {"style_code": style_code, "created_at": now_iso(),
                                  "rack": cell.get("rack") if cell else None,
                                  "row":  cell.get("row")  if cell else None,
                                  "cell": cell.get("cell") if cell else None},
                 "$set": {"updated_at": now_iso()}},
                upsert=True,
            )
            new_occ = int(cell.get("occupied_pairs", 0)) + put_here if cell else put_here
            await db.warehouse_locations.update_one(
                {"location_code": home},
                {"$set": {"occupied_pairs":  new_occ,
                          "available_pairs": max(0, capacity - new_occ),
                          "status":          _recompute_status(new_occ, capacity),
                          "updated_at":      now_iso()}},
            )

    return {
        "ok":                  True,
        "style_code":          style_code,
        "color":               payload.color,
        "size":                payload.size,
        "pending_before":      pending_total,
        "produced":            produced,
        "shortfall":           shortfall,
        "excess":              excess,
        "excess_placed_at":    excess_placed_at,
        "jobs_updated":        len(covered_job_ids),
        "bom_components_used": bom_used,
    }


@wms_router.post("/production/production-card")
async def create_production_card(request: Request, payload: ProductionCardIn):
    """Bulk-upsert a style's BOM (production card)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    sid_oid = ObjectId(payload.style_id) if ObjectId.is_valid(payload.style_id) else payload.style_id

    await db.style_component_mapping.update_many(
        {"$or": [{"style_id": sid_oid}, {"style_id": str(payload.style_id)}], "active": {"$ne": False}},
        {"$set": {"active": False, "updated_at": now_iso()}},
    )
    inserted = []
    for c in payload.components:
        comp_id = c.get("component_id")
        if not comp_id:
            continue
        cid_oid = ObjectId(comp_id) if ObjectId.is_valid(str(comp_id)) else str(comp_id)
        doc = {
            "style_id":          sid_oid,
            "component_id":      cid_oid,
            "quantity_per_pair": float(c.get("quantity_per_pair", 1) or 1),
            "wastage_percent":   float(c.get("wastage_percent", 0) or 0),
            "active":            True,
            "created_at":        now_iso(),
            "updated_at":        now_iso(),
            "created_by":        u["email"],
        }
        r = await db.style_component_mapping.insert_one(doc)
        inserted.append(str(r.inserted_id))
    return {"style_id": payload.style_id, "mapping_ids": inserted, "count": len(inserted)}


@wms_router.get("/production/short-log")
async def list_short_production(request: Request, style_code: Optional[str] = None):
    """Historical short-production log."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if style_code:
        q["style_code"] = style_code
    rows = await db.short_production_log.find(q).sort("created_at", -1).to_list(1000)
    return [stringify(r) for r in rows]


@wms_router.get("/production/style-variants/{sid}")
async def style_variants(sid: str, request: Request):
    """Return every (color, size) pair seen for this style."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    sid_oid = ObjectId(sid) if ObjectId.is_valid(sid) else sid

    colors, sizes = set(), set()
    async for r in db.fg_location_inventory.find({"$or": [{"style_id": sid_oid}, {"style_id": str(sid)}]}, {"color": 1, "size": 1}):
        if r.get("color"): colors.add(str(r["color"]))
        if r.get("size"):  sizes.add(str(r["size"]))
    async for r in db.production_jobs.find({"$or": [{"style_id": sid_oid}, {"style_id": str(sid)}]}, {"color": 1, "size": 1}):
        if r.get("color"): colors.add(str(r["color"]))
        if r.get("size"):  sizes.add(str(r["size"]))
    lc = await db.style_lifecycle.find_one({"style_id": sid})
    if lc:
        for c in (lc.get("planned_colors") or []):
            if c: colors.add(str(c))
        for s in (lc.get("planned_sizes")  or []):
            if s: sizes.add(str(s))

    def _sortsz(s):
        try: return (0, float(s))
        except (ValueError, TypeError):
            return (1, s)

    return {
        "colors": sorted(colors),
        "sizes":  sorted(sizes, key=_sortsz),
    }


@wms_router.get("/production/bom-feasibility/{sid}")
async def bom_feasibility(sid: str, request: Request, pairs: int = 1):
    """Preview whether a run of `pairs` of style `sid` can be produced with current component stock."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    if pairs <= 0:
        return {"feasible": True, "components": [], "missing_bom": False, "pairs": 0}
    
    sid_oid = ObjectId(sid) if ObjectId.is_valid(sid) else sid
    bom = await db.style_component_mapping.find({
        "$or": [{"style_id": sid_oid}, {"style_id": str(sid)}], "active": {"$ne": False},
    }).to_list(200)
    if not bom:
        return {"feasible": False, "components": [], "missing_bom": True, "pairs": pairs}

    comps = []
    feasible = True
    for b in bom:
        per   = float(b.get("quantity_per_pair", b.get("qty_per_pair", 1)) or 1)
        waste = float(b.get("wastage_percent", 0) or 0) / 100.0
        needed = int(round(pairs * per * (1 + waste)))
        comp = await db.component_master.find_one({"_id": ObjectId(b["component_id"]) if ObjectId.is_valid(str(b["component_id"])) else str(b["component_id"])})
        if not comp:
            continue
        available = int(comp.get("current_stock", 0))
        short = max(0, needed - available)
        if short > 0:
            feasible = False
        comps.append({
            "component_id":   str(comp["_id"]),
            "component_code": comp.get("component_code"),
            "component_name": comp.get("component_name"),
            "needed":         needed,
            "available":      available,
            "shortfall":      short,
        })
    return {"feasible": feasible, "components": comps, "missing_bom": False, "pairs": pairs}
