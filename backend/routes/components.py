"""Component Master, Color x Size Inventory Matrix, Stock Movements & BOM Mapping Routes."""

import re
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from models.components import (
    ComponentIn,
    ComponentMasterUpdate,
    ComponentBulkMatrix,
    ComponentMovementIn,
    StyleComponentMappingIn,
    StyleComponentMappingUpdate,
)
from auth import require_roles

components_router = APIRouter(prefix="/api", tags=["Component Inventory & BOM"])

STANDARD_SIZES = ["36", "37", "38", "39", "40", "41"]


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


async def log_activity_db(db, action: str, category: str, details: str, email: str):
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "by": email,
            "created_at": now_iso()
        })
    except Exception:
        pass


def _serialize_component(doc: dict) -> dict:
    """Attach the derived available_stock and image metadata before returning to clients."""
    out = stringify(doc)
    out["available_stock"] = int(out.get("current_stock", 0)) - int(out.get("reserved_stock", 0))
    out["material_id"] = out.get("material_id") or ""
    out["image_url"] = out.get("image_url") or ""
    out["image_display_url"] = out.get("image_display_url") or ""
    out["image_thumbnail_url"] = out.get("image_thumbnail_url") or ""
    return out


def _build_size_matrix_pivot(
    rows: List[dict],
    qty_field:      str = "current_stock",
    reserved_field: str = "reserved_stock",
    sizes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, dict]]:
    """Build a {color: {size: {qty, reserved}}} nested pivot from a flat list of rows."""
    target_sizes = sizes or STANDARD_SIZES
    matrix: Dict[str, Dict[str, dict]] = {}

    for row in rows:
        color = str(row.get("color") or "").strip() or "—"
        size  = str(row.get("size")  or "").strip() or "—"
        if color not in matrix:
            matrix[color] = {
                sz: {"qty": 0, "reserved": 0} for sz in target_sizes
            }
        matrix[color][size] = {
            "qty":      int(row.get(qty_field,      0) or 0),
            "reserved": int(row.get(reserved_field, 0) or 0),
        }

    return matrix


def _apply_component_movement(mov_type: str, quantity: int,
                              adjustment_dir: Optional[str]) -> Dict[str, int]:
    """Return the {current_delta, reserved_delta} that this movement applies."""
    q = int(quantity)
    if q <= 0:
        raise HTTPException(400, "quantity must be a positive integer")

    if mov_type == "purchase_in":
        return {"current_delta":  q,  "reserved_delta":  0}
    if mov_type == "return_in":
        return {"current_delta":  q,  "reserved_delta":  0}
    if mov_type == "adjustment":
        if adjustment_dir not in ("increase", "decrease"):
            raise HTTPException(400, "adjustment requires adjustment_dir='increase' or 'decrease'")
        sign = 1 if adjustment_dir == "increase" else -1
        return {"current_delta": sign * q, "reserved_delta": 0}
    if mov_type in ("production_reserve", "online_reserve"):
        return {"current_delta": 0,  "reserved_delta":  q}
    if mov_type == "unreserve":
        return {"current_delta": 0,  "reserved_delta": -q}
    if mov_type in ("production_issue", "online_issue"):
        return {"current_delta": -q, "reserved_delta": -q}
    raise HTTPException(400, f"Unsupported movement_type '{mov_type}'")


async def _record_component_movement(db, component: dict, payload: ComponentMovementIn,
                                     user_email: str) -> dict:
    """Atomically apply a movement to a component_master row and write a ledger entry."""
    MAX_RETRIES = 3

    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            component = await db.component_master.find_one({"_id": component["_id"]})
            if not component:
                raise HTTPException(404, "Component row disappeared during movement — abort")

        delta = _apply_component_movement(payload.movement_type, payload.quantity,
                                          payload.adjustment_dir)
        before_current  = int(component.get("current_stock",  0))
        before_reserved = int(component.get("reserved_stock", 0))
        new_current     = before_current  + delta["current_delta"]
        new_reserved    = before_reserved + delta["reserved_delta"]

        if new_current < 0:
            raise HTTPException(400,
                f"Movement would take current_stock negative "
                f"({before_current} → {new_current})")
        if new_reserved < 0:
            raise HTTPException(400,
                f"Movement would take reserved_stock negative "
                f"({before_reserved} → {new_reserved})")
        if new_reserved > new_current:
            raise HTTPException(400,
                f"Movement would over-reserve: reserved_stock ({new_reserved}) "
                f"> current_stock ({new_current})")

        now = now_iso()
        match_filter = {
            "_id":            component["_id"],
            "current_stock":  before_current,
            "reserved_stock": before_reserved,
        }
        inc_doc: dict = {}
        if delta["current_delta"]  != 0: inc_doc["current_stock"]  = delta["current_delta"]
        if delta["reserved_delta"] != 0: inc_doc["reserved_stock"] = delta["reserved_delta"]

        res = await db.component_master.update_one(
            match_filter,
            {
                "$inc": inc_doc,
                "$set": {"updated_at": now},
            } if inc_doc else {"$set": {"updated_at": now}},
        )

        if res.modified_count == 0:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            raise HTTPException(
                409,
                "Concurrent modification detected on component_master after "
                f"{MAX_RETRIES} retries. Please retry the movement."
            )

        ledger = {
            "component_id":    component["_id"],
            "component_code":  component.get("component_code", ""),
            "component_name":  component.get("component_name", ""),
            "color":           component.get("color", ""),
            "size":            component.get("size", ""),
            "movement_type":   payload.movement_type,
            "quantity":        int(payload.quantity),
            "current_delta":   delta["current_delta"],
            "reserved_delta":  delta["reserved_delta"],
            "current_before":  before_current,
            "current_after":   new_current,
            "reserved_before": before_reserved,
            "reserved_after":  new_reserved,
            "reference_type":  payload.reference_type or "manual",
            "reference_id":    payload.reference_id or "",
            "style_id":        oid(payload.style_id) if payload.style_id else None,
            "notes":           (payload.notes or "").strip(),
            "created_at":      now,
            "by":              user_email,
        }
        res_l = await db.component_stock_movements.insert_one(ledger)
        ledger["_id"] = res_l.inserted_id

        await log_activity_db(
            db,
            "MOVEMENT", "component",
            f"{component.get('component_code')} "
            f"({component.get('color','') or '—'}/{component.get('size','') or '—'}): "
            f"{payload.movement_type} x {payload.quantity} "
            f"→ stock={new_current}, reserved={new_reserved}",
            user_email,
        )
        return {
            "ledger":    stringify(ledger),
            "component": _serialize_component({
                **component,
                "current_stock":  new_current,
                "reserved_stock": new_reserved,
                "updated_at":     now,
            }),
        }

    raise HTTPException(409, "Component movement failed after retries")


# ---------- ENDPOINTS ----------

@components_router.get("/components")
async def list_components(
    request: Request,
    code:       Optional[str] = None,
    category:   Optional[str] = None,
    color:      Optional[str] = None,
    size:       Optional[str] = None,
    active:     Optional[bool] = None,
    low_stock:  Optional[bool] = None,
    search:     Optional[str] = None,
):
    """Return a flat list of component rows."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if code:     q["component_code"] = code
    if category: q["component_category"] = category
    if color:    q["color"] = color
    if size:     q["size"] = size
    if active is not None: q["active"] = active
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"component_code": rx}, {"component_name": rx}, {"vendor": rx}]

    rows = await db.component_master.find(q).sort([("component_code", 1), ("color", 1), ("size", 1)]).to_list(10000)
    result = [_serialize_component(r) for r in rows]
    if low_stock:
        result = [r for r in result
                  if int(r.get("minimum_stock", 0)) > 0
                  and int(r.get("available_stock", 0)) <= int(r.get("minimum_stock", 0))]
    return result


@components_router.get("/components/size-matrix/{component_code}")
async def get_component_size_matrix(component_code: str, request: Request):
    """Return a unified color x size matrix for a single component code."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    rows = await db.component_master.find(
        {"component_code": component_code}
    ).sort([("color", 1), ("size", 1)]).to_list(10000)

    if not rows:
        raise HTTPException(404, f"No components found with code '{component_code}'")

    serialized = [_serialize_component(r) for r in rows]
    matrix = _build_size_matrix_pivot(
        serialized,
        qty_field="current_stock",
        reserved_field="reserved_stock",
    )

    all_sizes = sorted(
        set(STANDARD_SIZES) | {str(r.get("size") or "") for r in serialized if r.get("size")},
        key=lambda x: (int(x) if x.isdigit() else 9999, x),
    )

    sample = rows[0]
    return {
        "component_code":     component_code,
        "component_name":     sample.get("component_name", ""),
        "component_category": sample.get("component_category", ""),
        "unit":               sample.get("unit", "pair"),
        "standard_sizes":     STANDARD_SIZES,
        "all_sizes":          all_sizes,
        "colors":             sorted(matrix.keys()),
        "matrix":             matrix,
        "flat_rows":          serialized,
    }


@components_router.post("/components")
async def create_component(payload: ComponentIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    now = now_iso()
    doc = {
        **payload.model_dump(),
        "reserved_stock": 0,
        "created_at":     now,
        "updated_at":     now,
        "created_by":     u.get("email") or u.get("name", ""),
    }
    if int(doc["current_stock"]) < 0:
        raise HTTPException(400, "current_stock must be >= 0")
    try:
        res = await db.component_master.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409,
            f"A component with code='{payload.component_code}', color='{payload.color or ''}', "
            f"size='{payload.size or ''}' already exists")
    doc["_id"] = res.inserted_id

    if int(payload.current_stock) > 0:
        opening = ComponentMovementIn(
            component_id=str(res.inserted_id),
            movement_type="purchase_in",
            quantity=int(payload.current_stock),
            reference_type="opening_balance",
            notes="Opening balance at row creation",
        )
        rewound = {**doc, "current_stock": 0, "reserved_stock": 0}
        await db.component_master.update_one({"_id": res.inserted_id},
            {"$set": {"current_stock": 0, "reserved_stock": 0}})
        await _record_component_movement(db, rewound, opening, u.get("email") or u.get("name", ""))

    fresh = await db.component_master.find_one({"_id": res.inserted_id})
    await log_activity_db(db, "CREATE", "component",
        f"{payload.component_code} ({payload.color or '—'}/{payload.size or '—'}) created",
        u.get("email") or u.get("name", ""))
    return _serialize_component(fresh)


@components_router.put("/components/{cid}")
async def update_component(cid: str, payload: ComponentMasterUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.component_master.find_one({"_id": oid(cid)})
    if not doc:
        raise HTTPException(404, "Component not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        return _serialize_component(doc)
    update["updated_at"] = now_iso()
    code = doc.get("component_code")
    shared_keys = {"component_name", "component_category", "vendor", "unit", "image_url", "image_display_url", "image_thumbnail_url", "material_id"}
    shared_update = {k: v for k, v in update.items() if k in shared_keys}
    if code and shared_update:
        await db.component_master.update_many({"component_code": code}, {"$set": shared_update})
    await db.component_master.update_one({"_id": doc["_id"]}, {"$set": update})
    
    mat_id = update.get("material_id") or doc.get("material_id")
    if mat_id and ("image_url" in update or "component_name" in update):
        mat_update = {}
        if "image_url" in update:
            mat_update["image_url"] = update.get("image_url", "")
            mat_update["image_display_url"] = update.get("image_display_url", "")
            mat_update["image_thumbnail_url"] = update.get("image_thumbnail_url", "")
        if mat_update:
            mat_update["updated_at"] = now_iso()
            await db.materials.update_one({"_id": oid(mat_id)}, {"$set": mat_update})

    await log_activity_db(db, "UPDATE", "component",
        f"{doc['component_code']} metadata updated: {', '.join(update.keys())}", u.get("email") or u.get("name", ""))
    return _serialize_component(await db.component_master.find_one({"_id": doc["_id"]}))


@components_router.delete("/components/{cid}")
async def deactivate_component(cid: str, request: Request):
    """Soft-delete a component master row."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.component_master.find_one({"_id": oid(cid)})
    if not doc:
        raise HTTPException(404, "Component not found")

    if int(doc.get("current_stock", 0)) > 0 or int(doc.get("reserved_stock", 0)) > 0:
        raise HTTPException(400,
            "Cannot delete: component has non-zero stock. Zero out via an adjustment movement first.")

    active_bom_links = await db.style_component_mapping.find(
        {"component_id": cid, "active": True}
    ).to_list(200)

    if active_bom_links:
        style_codes = []
        for link in active_bom_links:
            style_doc = await db.styles.find_one({"_id": ObjectId(link["style_id"])}, {"code": 1})
            style_codes.append((style_doc or {}).get("code", link["style_id"]))
        raise HTTPException(
            409,
            f"Cannot deactivate component '{doc['component_code']}': "
            f"it is referenced in active BOM links for {len(active_bom_links)} style(s): "
            f"{', '.join(style_codes)}. Remove the BOM links first."
        )

    now = now_iso()
    cascade_result = await db.style_component_mapping.update_many(
        {"component_id": cid},
        {"$set": {"active": False, "updated_at": now}},
    )

    await db.component_master.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "active":     False,
            "deleted_at": now,
            "updated_at": now,
        }}
    )
    await log_activity_db(
        db,
        "DELETE", "component",
        f"{doc['component_code']} ({doc.get('color','')}/{doc.get('size','')}) deactivated; "
        f"{cascade_result.modified_count} BOM mapping(s) also deactivated.",
        u.get("email") or u.get("name", ""),
    )
    return {
        "ok":                     True,
        "id":                     cid,
        "bom_links_deactivated":  cascade_result.modified_count,
    }


@components_router.post("/components/bulk-matrix")
async def create_component_bulk_matrix(payload: ComponentBulkMatrix, request: Request):
    """Create or extend multiple (color, size) rows for one component in one shot."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    now = now_iso()
    created, updated, skipped = 0, 0, 0
    results = []
    for row in payload.rows:
        color = str(row.get("color", "") or "").strip()
        size  = str(row.get("size",  "") or "").strip()
        opening = int(row.get("opening_qty") or 0)
        if opening < 0:
            results.append({"color": color, "size": size, "status": "invalid_qty"})
            continue
        try:
            doc = {
                "component_code":     payload.component_code,
                "component_name":     payload.component_name,
                "component_category": payload.component_category,
                "color":              color,
                "size":               size,
                "vendor":             payload.vendor or "",
                "unit":               payload.unit or "pair",
                "current_stock":      0,
                "reserved_stock":     0,
                "reorder_level":      int(payload.reorder_level),
                "minimum_stock":      int(payload.minimum_stock),
                "lead_time_days":     int(payload.lead_time_days),
                "active":             True,
                "material_id":        payload.material_id or "",
                "image_url":           payload.image_url or "",
                "image_display_url":   payload.image_display_url or "",
                "image_thumbnail_url": payload.image_thumbnail_url or "",
                "created_at":         now,
                "updated_at":         now,
                "created_by":         u.get("email") or u.get("name", ""),
            }
            res = await db.component_master.insert_one(doc)
            doc["_id"] = res.inserted_id
            if opening > 0:
                await _record_component_movement(
                    db,
                    doc,
                    ComponentMovementIn(
                        component_id=str(res.inserted_id),
                        movement_type="purchase_in",
                        quantity=opening,
                        reference_type="opening_balance",
                        notes="Opening balance from bulk matrix",
                    ),
                    u.get("email") or u.get("name", ""),
                )
            created += 1
            results.append({"color": color, "size": size, "status": "created", "qty": opening})
        except DuplicateKeyError:
            if opening > 0:
                existing = await db.component_master.find_one({
                    "component_code": payload.component_code,
                    "color":          color,
                    "size":           size,
                })
                if existing:
                    try:
                        await _record_component_movement(
                            db,
                            existing,
                            ComponentMovementIn(
                                component_id=str(existing["_id"]),
                                movement_type="purchase_in",
                                quantity=opening,
                                reference_type="bulk_matrix_topup",
                                notes="Stock added via bulk matrix (extend mode)",
                            ),
                            u.get("email") or u.get("name", ""),
                        )
                        updated += 1
                        results.append({
                            "color": color, "size": size,
                            "status": "stock_added", "qty": opening,
                        })
                    except HTTPException as he:
                        results.append({
                            "color": color, "size": size,
                            "status": "movement_failed",
                            "error":  str(he.detail),
                        })
                else:
                    skipped += 1
                    results.append({"color": color, "size": size, "status": "exists"})
            else:
                skipped += 1
                results.append({"color": color, "size": size, "status": "exists"})
    await log_activity_db(
        db,
        "BULK", "component",
        f"{payload.component_code}: {created} rows created, {updated} rows topped-up, {skipped} skipped",
        u.get("email") or u.get("name", ""),
    )
    return {
        "created":  created,
        "updated":  updated,
        "skipped":  skipped,
        "results":  results,
    }


@components_router.post("/components/movements")
async def post_component_movement(payload: ComponentMovementIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    comp = await db.component_master.find_one({"_id": oid(payload.component_id)})
    if not comp:
        raise HTTPException(404, "Component not found")
    return await _record_component_movement(db, comp, payload, u.get("email") or u.get("name", ""))


@components_router.get("/components/movements")
async def list_component_movements(
    request: Request,
    component_id:  Optional[str] = None,
    movement_type: Optional[str] = None,
    style_id:      Optional[str] = None,
    reference_type: Optional[str] = None,
    limit: int = 500,
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if component_id:  q["component_id"] = oid(component_id)
    if movement_type: q["movement_type"] = movement_type
    if style_id:      q["style_id"] = oid(style_id)
    if reference_type: q["reference_type"] = reference_type
    rows = await db.component_stock_movements.find(q).sort("created_at", -1).to_list(min(limit, 2000))
    out = []
    for r in rows:
        s = stringify(r)
        if isinstance(r.get("style_id"), ObjectId):
            s["style_id"] = str(r["style_id"])
        if isinstance(r.get("component_id"), ObjectId):
            s["component_id"] = str(r["component_id"])
        out.append(s)
    return out


# ---------- STYLE ⇄ COMPONENT BOM MAPPING ----------

@components_router.get("/style-component-mapping")
async def list_style_component_mapping(
    request: Request,
    style_id:     Optional[str] = None,
    component_id: Optional[str] = None,
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if style_id:     q["style_id"] = oid(style_id)
    if component_id: q["component_id"] = oid(component_id)
    rows = await db.style_component_mapping.find(q).to_list(5000)

    comp_ids  = list({r["component_id"] for r in rows if r.get("component_id")})
    style_ids = list({r["style_id"]     for r in rows if r.get("style_id")})
    comps  = {c["_id"]: c for c in await db.component_master.find({"_id": {"$in": comp_ids}}).to_list(5000)}
    styles = {s["_id"]: s for s in await db.styles.find({"_id": {"$in": style_ids}}).to_list(5000)}

    out = []
    for r in rows:
        s = stringify(r)
        s["style_id"]     = str(r.get("style_id"))     if r.get("style_id") else None
        s["component_id"] = str(r.get("component_id")) if r.get("component_id") else None
        comp  = comps.get(r.get("component_id"))
        style = styles.get(r.get("style_id"))
        if comp:
            s["component_code"]     = comp.get("component_code", "")
            s["component_name"]     = comp.get("component_name", "")
            s["component_category"] = comp.get("component_category", "")
            s["component_color"]    = comp.get("color", "")
            s["component_size"]     = comp.get("size", "")
            s["current_stock"]      = int(comp.get("current_stock", 0))
            s["reserved_stock"]     = int(comp.get("reserved_stock", 0))
            s["available_stock"]    = s["current_stock"] - s["reserved_stock"]
        if style:
            s["style_code"] = style.get("code", "")
            s["style_name"] = style.get("name", "")
        out.append(s)
    out.sort(key=lambda x: (x.get("style_code",""), x.get("component_category",""), x.get("component_code","")))
    return out


@components_router.post("/style-component-mapping")
async def create_style_component_mapping(payload: StyleComponentMappingIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    style = await db.styles.find_one({"_id": oid(payload.style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    comp = await db.component_master.find_one({"_id": oid(payload.component_id)})
    if not comp:
        raise HTTPException(404, "Component not found")
    now = now_iso()
    doc = {
        "style_id":           oid(payload.style_id),
        "component_id":       oid(payload.component_id),
        "component_category": comp.get("component_category", ""),
        "quantity_per_pair":  float(payload.quantity_per_pair),
        "wastage_percent":    float(payload.wastage_percent),
        "active":             bool(payload.active),
        "created_at":         now,
        "updated_at":         now,
        "created_by":         u.get("email") or u.get("name", ""),
    }
    try:
        res = await db.style_component_mapping.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409,
            f"Style '{style['code']}' already has component '{comp['component_code']}' mapped.")
    doc["_id"] = res.inserted_id
    await log_activity_db(db, "CREATE", "style_component_mapping",
        f"{style['code']} ← {comp['component_code']} @ {payload.quantity_per_pair}/pair", u.get("email") or u.get("name", ""))
    s = stringify(doc)
    s["style_id"]     = str(doc["style_id"])
    s["component_id"] = str(doc["component_id"])
    return s


@components_router.put("/style-component-mapping/{mid}")
async def update_style_component_mapping(mid: str, payload: StyleComponentMappingUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.style_component_mapping.find_one({"_id": oid(mid)})
    if not doc:
        raise HTTPException(404, "Mapping not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        return {"ok": True}
    update["updated_at"] = now_iso()
    await db.style_component_mapping.update_one({"_id": doc["_id"]}, {"$set": update})
    await log_activity_db(db, "UPDATE", "style_component_mapping",
        f"Mapping {mid} updated: {', '.join(update.keys())}", u.get("email") or u.get("name", ""))
    return {"ok": True}


@components_router.delete("/style-component-mapping/{mid}")
async def delete_style_component_mapping(mid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.style_component_mapping.find_one({"_id": oid(mid)})
    if not doc:
        raise HTTPException(404, "Mapping not found")
    await db.style_component_mapping.delete_one({"_id": doc["_id"]})
    await log_activity_db(db, "DELETE", "style_component_mapping",
        f"Mapping {mid} deleted", u.get("email") or u.get("name", ""))
    return {"ok": True}
