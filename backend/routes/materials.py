"""Raw Materials, BOM Items & Inventory Valuation Routes."""

import re
import logging
from collections import defaultdict
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import StreamingResponse

from models.materials import (
    MaterialIn,
    BomItem,
    LaborItem,
    QuantityUpdate,
    InventoryMovement,
)
from auth import require_roles
from pdf_procurement import build_material_requirement, _is_swatch_item
from routes.styles import get_effective_bom

log = logging.getLogger(__name__)

materials_router = APIRouter(prefix="/api", tags=["Materials & Inventory"])


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


# ═══════════════════════════════════════════════════════════════════════
# ══ MATERIAL SYNC & INVENTORY VALUATION HELPERS ═════════════════════════
# ═══════════════════════════════════════════════════════════════════════

async def _sync_material_to_component(mat_doc: dict, db=None):
    """Sync raw material to component inventory if marked as component or linked."""
    if db is None:
        import server
        db = server.db

    is_comp = mat_doc.get("is_component")
    if not is_comp:
        return
    cat = mat_doc.get("component_category") or mat_doc.get("category", "").title()
    category_map = {
        "Upper": "Upper", "Sole": "Sole", "Lining": "Other",
        "Accessory": "Other", "Consumable": "Other", "Packing": "Packaging", "Other": "Other"
    }
    comp_cat = cat if cat in ["Upper", "Sole", "Insole", "Sockliner", "Bottom", "Lace", "Box", "Tag", "Label", "Packaging", "Other"] else category_map.get(cat, "Other")
    
    code = mat_doc.get("code", "").strip()
    mat_id = str(mat_doc.get("_id") or mat_doc.get("id"))
    image_url = mat_doc.get("image_url", "")
    image_display_url = mat_doc.get("image_display_url", "")
    image_thumbnail_url = mat_doc.get("image_thumbnail_url", "")
    name = mat_doc.get("name", "")
    unit = mat_doc.get("unit", "pair")
    vendor = mat_doc.get("preferred_vendor_id", "")
    reorder = int(mat_doc.get("reorder_level", 0))
    color = mat_doc.get("color", "")

    existing = await db.component_master.find({"component_code": code}).to_list(1000)
    if existing:
        await db.component_master.update_many(
            {"component_code": code},
            {"$set": {
                "material_id": mat_id,
                "component_name": name,
                "component_category": comp_cat,
                "color": color,
                "image_url": image_url,
                "image_display_url": image_display_url,
                "image_thumbnail_url": image_thumbnail_url,
                "updated_at": now_iso(),
            }}
        )
    else:
        comp_doc = {
            "component_code": code,
            "component_name": name,
            "component_category": comp_cat,
            "color": color,
            "size": "",
            "vendor": vendor,
            "unit": unit,
            "current_stock": 0,
            "reserved_stock": 0,
            "reorder_level": reorder,
            "minimum_stock": reorder,
            "lead_time_days": 0,
            "active": True,
            "material_id": mat_id,
            "image_url": image_url,
            "image_display_url": image_display_url,
            "image_thumbnail_url": image_thumbnail_url,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        try:
            await db.component_master.insert_one(comp_doc)
        except DuplicateKeyError:
            pass


def _calculate_material_weighted_avg(mat: Optional[dict], movements: list) -> dict:
    """Calculate stock balance, last purchase rate/date, weighted-average cost rate, and stock valuation
    using chronological moving weighted average.

    Formula on incoming stock (type == 'in' or positive adjustment):
        weighted_avg_rate = (existing_value + new_qty * new_rate) / (existing_qty + new_qty)
    """
    sorted_movs = sorted(
        movements,
        key=lambda m: (m.get("date") or "", m.get("created_at") or "", str(m.get("_id", "")))
    )

    base_rate = float(mat.get("rate") or 0.0) if mat else 0.0
    stock_in = 0.0
    stock_out = 0.0
    adjustments = 0.0
    last_rate = 0.0
    last_date = ""
    current_stock = 0.0
    current_avg_rate = base_rate
    has_explicit_rate = False

    for m in sorted_movs:
        mtype = m.get("type")
        qty = float(m.get("quantity", 0) or 0.0)
        m_rate = m.get("rate")
        has_rate = m_rate is not None and m_rate != ""
        rate_val = float(m_rate) if has_rate else None

        if mtype == "in":
            stock_in += qty
            if rate_val is not None:
                last_rate = rate_val
                has_explicit_rate = True
            last_date = m.get("date") or m.get("created_at", "")

            effective_in_rate = rate_val if rate_val is not None else current_avg_rate
            if current_stock <= 0:
                current_stock = current_stock + qty
                current_avg_rate = effective_in_rate
            else:
                existing_val = current_stock * current_avg_rate
                new_val = qty * effective_in_rate
                new_qty = current_stock + qty
                current_avg_rate = (existing_val + new_val) / new_qty if new_qty > 0 else effective_in_rate
                current_stock = new_qty

        elif mtype == "out":
            stock_out += qty
            current_stock -= qty

        else:  # adjustment
            adjustments += qty
            if qty > 0:
                adj_rate = rate_val if rate_val is not None else current_avg_rate
                if current_stock <= 0:
                    current_stock = current_stock + qty
                    if rate_val is not None:
                        current_avg_rate = adj_rate
                        has_explicit_rate = True
                else:
                    existing_val = current_stock * current_avg_rate
                    new_val = qty * adj_rate
                    new_qty = current_stock + qty
                    current_avg_rate = (existing_val + new_val) / new_qty if new_qty > 0 else adj_rate
                    current_stock = new_qty
            else:
                current_stock += qty

    balance = stock_in - stock_out + adjustments
    final_avg_rate = current_avg_rate if (has_explicit_rate or current_avg_rate > 0) else base_rate
    final_val = round(balance * final_avg_rate, 2)

    return {
        "stock_in": stock_in,
        "stock_out": stock_out,
        "adjustments": adjustments,
        "balance": balance,
        "last_rate": last_rate if last_rate > 0 else base_rate,
        "last_date": last_date,
        "weighted_avg_rate": final_avg_rate,
        "value": final_val,
    }


async def _compute_material_inventory_summary(material_id: str, mat_doc: Optional[dict] = None, db=None) -> dict:
    """Helper to compute inventory summary for a single material."""
    if db is None:
        import server
        db = server.db
    if mat_doc is None:
        try:
            mat_doc = await db.materials.find_one({"_id": oid(material_id)})
        except Exception:
            mat_doc = None
    movements = await db.inventory_movements.find({"material_id": material_id}).to_list(10000)
    return _calculate_material_weighted_avg(mat_doc or {}, movements)


async def _get_material_balance(material_id: str, db=None) -> float:
    """Calculate the net balance of a raw material from its inventory movements."""
    if db is None:
        import server
        db = server.db
    movements = await db.inventory_movements.find({"material_id": material_id}).to_list(10000)
    stock = 0.0
    for m in movements:
        qty = float(m.get("quantity", 0) or 0)
        mtype = m.get("type")
        if mtype == "in":
            stock += qty
        elif mtype == "out":
            stock -= qty
        else:
            stock += qty
    return stock


async def _compute_material_requirement(job_ids: list[str], db=None) -> dict:
    """Aggregate material requirements across jobs based on their style BOM and yield."""
    if db is None:
        import server
        db = server.db

    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    style_codes = list({j.get("style_code") for j in jobs})
    styles = await db.styles.find({"code": {"$in": style_codes}}).to_list(500)
    style_map = {s["code"]: stringify(s) for s in styles}

    materials = await db.materials.find({}).to_list(2000)
    mat_map = {str(m["_id"]): stringify(m) for m in materials}

    requirements = {}
    color_requirements = defaultdict(dict)
    color_pairs = defaultdict(int)
    jobs_summary = []
    for j in jobs:
        st = style_map.get(j.get("style_code"))
        pairs = j.get("quantity", 0)
        job_color = (j.get("color") or "").strip() or "Standard"
        color_pairs[job_color] += pairs
        jobs_summary.append({
            "po_number": j.get("po_number"),
            "style_code": j.get("style_code"),
            "color": j.get("color"),
            "total_pairs": pairs,
            "sizes_text": f"Size {j.get('size','')}",
        })
        if not st or not pairs:
            continue
        effective_bom = get_effective_bom(st, j.get("color"))
        for b_item in effective_bom:
            b = b_item.model_dump() if hasattr(b_item, "model_dump") else (b_item if isinstance(b_item, dict) else dict(b_item))
            mid = b.get("material_id") or b.get("material_code")
            code = b.get("material_code") or ""
            name = b.get("material_name") or ""
            unit = b.get("unit") or ""
            mat_info = mat_map.get(str(mid)) or mat_map.get(code) or {}
            raw_yld = b.get("yield_per_unit")
            def_yld = b.get("default_yield_per_unit") or mat_info.get("default_yield_per_unit")
            if raw_yld is not None and float(raw_yld) > 0:
                yld = float(raw_yld)
            elif def_yld is not None and float(def_yld) > 0:
                yld = float(def_yld)
            else:
                yld = 1.0
            qty = float(b.get("quantity", 0))
            waste = float(b.get("waste_pct", 0) or 0)
            rate = float(b.get("rate") or mat_info.get("cost_per_unit") or mat_info.get("rate") or mat_info.get("purchase_rate") or 0)
            per_pair = (qty / yld) * (1 + waste / 100)
            total_qty = per_pair * pairs

            cat = (mat_map.get(str(mid), {}).get("category") or mat_info.get("category") or b.get("section") or "other")
            is_swatch = _is_swatch_item(cat, "")

            raw_col = (b.get("color") or "").strip()
            if raw_col:
                color = raw_col
            elif is_swatch and job_color:
                color = job_color
            else:
                color = (mat_info.get("color") or "").strip() if is_swatch else ""

            key = (code or mid, color)
            is_sole = (cat or "").strip().lower() == "sole"
            job_size = str(j.get("size", "") or "").strip()

            if key not in requirements:
                requirements[key] = {
                    "code": code, "name": name, "category": cat, "unit": unit, "color": color,
                    "rate": rate, "total_qty_required": 0.0, "total_cost": 0.0,
                }
                if is_sole:
                    requirements[key]["size_breakdown"] = {}
            elif not requirements[key]["rate"] and rate > 0:
                requirements[key]["rate"] = rate

            requirements[key]["total_qty_required"] += total_qty
            requirements[key]["total_cost"] += total_qty * rate

            if is_sole:
                if "size_breakdown" not in requirements[key] or requirements[key]["size_breakdown"] is None:
                    requirements[key]["size_breakdown"] = {}
                sz_key = job_size if job_size else "Standard"
                requirements[key]["size_breakdown"][sz_key] = requirements[key]["size_breakdown"].get(sz_key, 0.0) + total_qty

            # Track per-color breakdown
            c_dict = color_requirements[job_color]
            if key not in c_dict:
                c_dict[key] = {
                    "code": code, "name": name, "category": cat, "unit": unit, "color": color,
                    "rate": rate, "total_qty_required": 0.0, "total_cost": 0.0,
                }
                if is_sole:
                    c_dict[key]["size_breakdown"] = {}
            elif not c_dict[key]["rate"] and rate > 0:
                c_dict[key]["rate"] = rate

            c_dict[key]["total_qty_required"] += total_qty
            c_dict[key]["total_cost"] += total_qty * rate

            if is_sole:
                if "size_breakdown" not in c_dict[key] or c_dict[key]["size_breakdown"] is None:
                    c_dict[key]["size_breakdown"] = {}
                sz_key = job_size if job_size else "Standard"
                c_dict[key]["size_breakdown"][sz_key] = c_dict[key]["size_breakdown"].get(sz_key, 0.0) + total_qty

    material_lines = []
    for v in requirements.values():
        v["total_qty_required"] = round(v["total_qty_required"], 2)
        v["total_cost"] = round(v["total_cost"], 2)
        if "size_breakdown" in v and v["size_breakdown"] is not None:
            sorted_breakdown = {}
            for sz in sorted(v["size_breakdown"].keys(), key=lambda x: (float(x) if x.replace('.', '', 1).isdigit() else 999, str(x))):
                val = round(v["size_breakdown"][sz], 2)
                sorted_breakdown[sz] = int(val) if val == int(val) else val
            v["size_breakdown"] = sorted_breakdown
        material_lines.append(v)
    material_lines.sort(key=lambda m: (m["category"], m["code"], m.get("color", "")))

    by_color = {}
    for col, c_reqs in color_requirements.items():
        c_mat_lines = []
        for v in c_reqs.values():
            v_copy = dict(v)
            v_copy["total_qty_required"] = round(v_copy["total_qty_required"], 2)
            v_copy["total_cost"] = round(v_copy["total_cost"], 2)
            if "size_breakdown" in v_copy and v_copy["size_breakdown"] is not None:
                sorted_bd = {}
                for sz in sorted(v_copy["size_breakdown"].keys(), key=lambda x: (float(x) if x.replace('.', '', 1).isdigit() else 999, str(x))):
                    val = round(v_copy["size_breakdown"][sz], 2)
                    sorted_bd[sz] = int(val) if val == int(val) else val
                v_copy["size_breakdown"] = sorted_bd
            c_mat_lines.append(v_copy)
        c_mat_lines.sort(key=lambda m: (m["category"], m["code"], m.get("color", "")))
        by_color[col] = {
            "color": col,
            "total_pairs": color_pairs[col],
            "materials": c_mat_lines,
        }

    summary_agg = {}
    for js in jobs_summary:
        key = (js["po_number"], js["style_code"], js["color"])
        if key not in summary_agg:
            summary_agg[key] = {"po_number": js["po_number"], "style_code": js["style_code"],
                                "color": js["color"], "total_pairs": 0, "_sizes": []}
        summary_agg[key]["total_pairs"] += js["total_pairs"]
        sz = js["sizes_text"].replace("Size ", "")
        if sz and sz not in summary_agg[key]["_sizes"]:
            summary_agg[key]["_sizes"].append(sz)
    summary_out = []
    for v in summary_agg.values():
        summary_out.append({
            "po_number": v["po_number"], "style_code": v["style_code"], "color": v["color"],
            "total_pairs": v["total_pairs"],
            "sizes_text": ", ".join(sorted(v["_sizes"], key=lambda x: (float(x) if x.replace('.', '', 1).isdigit() else 999))),
        })
    return {"jobs": summary_out, "materials": material_lines, "by_color": by_color}


async def _auto_consume_inventory(job: dict, by_email: str, db=None) -> bool:
    """When a job advances from procurement → cutting, auto-create stock-out movements
    for each BOM material based on job's quantity × yield-adjusted consumption.
    Idempotent: marks job.inventory_consumed=True so we don't double-deduct.
    """
    if db is None:
        import server
        db = server.db

    if job.get("inventory_consumed"):
        return False
    style = None
    if job.get("style_id"):
        style = await db.styles.find_one({"_id": oid(job["style_id"])})
    if not style:
        style = await db.styles.find_one({"code": job.get("style_code")})
    if not style:
        await db.production_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {"inventory_consume_error": f"Style '{job.get('style_code')}' not found in Style Master"}}
        )
        return False
    style_d = stringify(style)
    pairs = job.get("quantity", 0)
    effective_bom = get_effective_bom(style_d, job.get("color"))
    if not pairs or not effective_bom:
        return False

    mat_codes = [b.material_code if hasattr(b, "material_code") else b.get("material_code") for b in effective_bom]
    materials = await db.materials.find({"code": {"$in": mat_codes}}).to_list(500)
    by_code = {m["code"]: m for m in materials}

    movements = []
    temp_balances = {}
    for b in effective_bom:
        b_dict = b.model_dump() if hasattr(b, "model_dump") else (b if isinstance(b, dict) else dict(b))
        mat = by_code.get(b_dict.get("material_code")) or {}
        raw_yld = b.get("yield_per_unit")
        def_yld = b.get("default_yield_per_unit") or mat.get("default_yield_per_unit")
        if raw_yld is not None and float(raw_yld) > 0:
            yld = float(raw_yld)
        elif def_yld is not None and float(def_yld) > 0:
            yld = float(def_yld)
        else:
            yld = 1.0
        qty = float(b.get("quantity") or b.get("qty") or 1.0)
        waste = float(b.get("waste_pct", 0) or 0)
        consume = pairs * (qty / yld) * (1 + waste / 100)
        if consume <= 0:
            continue
        mat = by_code.get(b.get("material_code"))
        if not mat:
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"inventory_consume_error": f"Material '{b.get('material_code')}' not found"}}
            )
            return False
        mat_id = str(mat["_id"])
        if mat_id not in temp_balances:
            temp_balances[mat_id] = await _get_material_balance(mat_id, db=db)
        if temp_balances[mat_id] - consume < 0:
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"inventory_consume_error": f"Insufficient stock for '{mat.get('name')}'"}}
            )
            return False
        temp_balances[mat_id] -= consume

        rate = float(b.get("rate") or mat.get("cost_per_unit") or mat.get("rate") or 0)
        movements.append({
            "material_id": mat_id,
            "material_code": mat.get("code"),
            "material_name": mat.get("name"),
            "unit": mat.get("unit"),
            "type": "out",
            "quantity": round(consume, 4),
            "rate": rate,
            "party": f"Job {job.get('po_number','')} · {job.get('style_code','')} · {job.get('color','')} · Sz {job.get('size','')}",
            "job_id": str(job["_id"]),
            "notes": "Auto-consumed when stage moved past Procurement",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "by": by_email,
            "created_at": now_iso(),
            "auto": True,
        })
    if movements:
        await db.inventory_movements.insert_many(movements)
        await db.production_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {"inventory_consumed": True, "inventory_consumed_at": now_iso(), "inventory_consume_error": None}}
        )
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# ══ RAW MATERIAL ENDPOINTS ══════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════

@materials_router.get("/materials")
async def list_materials(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    docs = await db.materials.find({}).sort("name", 1).to_list(2000)
    return [stringify(d) for d in docs]


@materials_router.post("/materials")
async def create_material(payload: MaterialIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    code = payload.code.strip()
    if await db.materials.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}):
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    payload.code = code
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    try:
        res = await db.materials.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    ret = dict(doc)
    ret.pop("_id", None)
    ret["id"] = str(res.inserted_id)
    await _sync_material_to_component(ret, db=db)
    return ret


@materials_router.patch("/materials/{mid}")
async def update_material(mid: str, payload: MaterialIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    code = payload.code.strip()
    if await db.materials.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "_id": {"$ne": oid(mid)}}):
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    payload.code = code
    update = payload.model_dump()
    update.pop("balance", None)
    if update.get("weighted_avg_rate") is None:
        update.pop("weighted_avg_rate", None)
    if update.get("last_purchase_rate") is None:
        update.pop("last_purchase_rate", None)
    update["updated_at"] = now_iso()
    try:
        await db.materials.update_one({"_id": oid(mid)}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    updated_doc = stringify(await db.materials.find_one({"_id": oid(mid)}))
    await _sync_material_to_component(updated_doc, db=db)
    return updated_doc


@materials_router.delete("/materials/{mid}")
async def delete_material(mid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    await db.materials.delete_one({"_id": oid(mid)})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════
# ══ INVENTORY MOVEMENTS & STOCK VALUATION ENDPOINTS ════════════════════
# ═══════════════════════════════════════════════════════════════════════

@materials_router.get("/inventory")
async def list_inventory(request: Request):
    """List all materials with computed stock balance and weighted-average valuation."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    materials = await db.materials.find({}).to_list(2000)
    movements = await db.inventory_movements.find({}).to_list(20000)

    mov_by_mat = defaultdict(list)
    for m in movements:
        mid = m.get("material_id")
        if mid:
            mov_by_mat[mid].append(m)

    out = []
    for mat in materials:
        mat_id = str(mat["_id"])
        summary = _calculate_material_weighted_avg(mat, mov_by_mat.get(mat_id, []))
        out.append({
            "material_id": mat_id,
            "code": mat.get("code"),
            "name": mat.get("name"),
            "category": mat.get("category"),
            "color": mat.get("color", ""),
            "unit": mat.get("unit"),
            "current_rate": mat.get("rate"),
            "last_purchase_rate": round(summary["last_rate"], 2) if summary["last_rate"] else mat.get("rate", 0),
            "last_purchase_date": summary["last_date"],
            "weighted_avg_rate": round(summary["weighted_avg_rate"], 2),
            "stock_in": round(summary["stock_in"], 2),
            "stock_out": round(summary["stock_out"], 2),
            "adjustments": round(summary["adjustments"], 2),
            "balance": round(summary["balance"], 2),
            "value": summary["value"],
            "image_url": mat.get("image_url", ""),
            "image_display_url": mat.get("image_display_url", ""),
            "image_thumbnail_url": mat.get("image_thumbnail_url", ""),
        })
    out.sort(key=lambda r: (r["category"] or "", r["name"] or ""))
    return out


@materials_router.get("/inventory/movements")
async def list_movements(
    request: Request,
    material_id: Optional[str] = None,
    limit: int = 200,
    skip: int = 0,
    page: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    type: Optional[str] = None,
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if material_id:
        q["material_id"] = material_id
    if type:
        q["type"] = type

    if start_date or end_date:
        conds = []
        if start_date:
            conds.append({
                "$or": [
                    {"created_at": {"$gte": start_date[:10]}},
                    {"date": {"$gte": start_date[:10]}},
                ]
            })
        if end_date:
            end_val = end_date[:10] + "T23:59:59.999999Z" if "T" not in end_date else end_date
            conds.append({
                "$or": [
                    {"created_at": {"$lte": end_val}},
                    {"date": {"$lte": end_date[:10]}},
                ]
            })
        if len(conds) == 1:
            q.update(conds[0])
        elif len(conds) > 1:
            q["$and"] = conds

    if page and page > 0:
        skip = (page - 1) * limit

    docs = await db.inventory_movements.find(q).sort("created_at", -1).skip(skip).to_list(limit)
    return [stringify(d) for d in docs]


@materials_router.post("/inventory/movements")
async def create_movement(payload: InventoryMovement, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    try:
        mat = await db.materials.find_one({"_id": oid(payload.material_id)})
    except HTTPException:
        mat = None
    if not mat:
        raise HTTPException(404, "Material not found")

    deduction_qty = 0.0
    if payload.type == "out":
        deduction_qty = payload.quantity
    elif payload.type == "adjustment" and payload.quantity < 0:
        deduction_qty = -payload.quantity

    add_qty = 0.0
    if payload.type == "in":
        add_qty = payload.quantity
    elif payload.type == "adjustment" and payload.quantity > 0:
        add_qty = payload.quantity

    if mat.get("balance") is None:
        init_bal = await _get_material_balance(payload.material_id, db=db)
        await db.materials.update_one(
            {"_id": mat["_id"], "balance": {"$exists": False}},
            {"$set": {"balance": init_bal}}
        )
        mat["balance"] = init_bal

    if deduction_qty > 0:
        res = await db.materials.update_one(
            {"_id": mat["_id"], "balance": {"$gte": deduction_qty}},
            {"$inc": {"balance": -deduction_qty}, "$set": {"updated_at": now_iso()}}
        )
        if res.matched_count == 0:
            fresh_mat = await db.materials.find_one({"_id": mat["_id"]})
            cur_bal = fresh_mat.get("balance", 0.0) if fresh_mat else 0.0
            raise HTTPException(
                status_code=400,
                detail=f"Deduction of {deduction_qty} {mat.get('unit', '')} exceeds current stock balance ({round(cur_bal, 2)} {mat.get('unit', '')})."
            )

    doc = payload.model_dump()
    doc["material_code"] = mat.get("code")
    doc["material_name"] = mat.get("name")
    doc["unit"] = mat.get("unit")
    doc["created_at"] = now_iso()
    doc["by"] = u.get("email") or u.get("name", "")
    if not doc.get("date"):
        doc["date"] = datetime.now(timezone.utc).date().isoformat()

    try:
        res = await db.inventory_movements.insert_one(doc)
    except Exception as e:
        if deduction_qty > 0:
            await db.materials.update_one({"_id": mat["_id"]}, {"$inc": {"balance": deduction_qty}})
        raise e

    ret = dict(doc)
    ret.pop("_id", None)
    ret["id"] = str(res.inserted_id)

    if add_qty > 0:
        await db.materials.update_one(
            {"_id": mat["_id"]},
            {"$inc": {"balance": add_qty}, "$set": {"updated_at": now_iso()}}
        )

    try:
        summary = await _compute_material_inventory_summary(payload.material_id, mat, db=db)
        await db.materials.update_one(
            {"_id": mat["_id"]},
            {"$set": {
                "balance": round(summary["balance"], 2),
                "weighted_avg_rate": round(summary["weighted_avg_rate"], 2),
                "last_purchase_rate": round(summary["last_rate"], 2) if summary["last_rate"] else (mat.get("rate") or 0.0),
                "updated_at": now_iso(),
            }}
        )
    except Exception:
        pass

    return ret


@materials_router.delete("/inventory/movements/{mid}")
async def delete_movement(mid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    mov = await db.inventory_movements.find_one({"_id": oid(mid)})
    await db.inventory_movements.delete_one({"_id": oid(mid)})
    if mov and mov.get("material_id"):
        try:
            summary = await _compute_material_inventory_summary(mov["material_id"], db=db)
            mat_doc = await db.materials.find_one({"_id": oid(mov["material_id"])})
            fallback_rate = (mat_doc.get("rate") or 0.0) if mat_doc else 0.0
            await db.materials.update_one(
                {"_id": oid(mov["material_id"])},
                {"$set": {
                    "weighted_avg_rate": round(summary["weighted_avg_rate"], 2),
                    "last_purchase_rate": round(summary["last_rate"], 2) if summary["last_rate"] else fallback_rate,
                    "updated_at": now_iso(),
                }}
            )
        except Exception:
            pass
    return {"ok": True}


@materials_router.post("/inventory/shortage")
async def inventory_shortage(payload: dict, request: Request):
    """Given job_ids, compute material requirement and compare with current stock to expose shortage."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    req = await _compute_material_requirement(job_ids, db=db)

    bal_list = await list_inventory(request)
    bal_map = {(b["code"], b["name"]): b for b in bal_list}

    materials = await db.materials.find({}).to_list(2000)
    mat_details = {(m.get("code"), m.get("name")): m for m in materials}

    vendors = await db.vendors.find({}).to_list(2000)
    vendor_map = {str(v["_id"]): v for v in vendors}

    rows = []
    for m in req["materials"]:
        key = (m["code"], m["name"])
        b = bal_map.get(key, {"balance": 0, "unit": m["unit"]})
        shortage = max(0, m["total_qty_required"] - b.get("balance", 0))

        mat_doc = mat_details.get(key) or {}
        pref_v_id = mat_doc.get("preferred_vendor_id") or ""
        pref_v_name = ""
        if pref_v_id:
            try:
                v_doc = vendor_map.get(pref_v_id)
                if v_doc:
                    pref_v_name = v_doc.get("name")
            except Exception:
                pass

        rows.append({
            "code": m["code"], "name": m["name"], "unit": m["unit"],
            "required": m["total_qty_required"],
            "in_stock": b.get("balance", 0),
            "shortage": round(shortage, 2),
            "purchase_cost_estimated": round(shortage * m["rate"], 2),
            "material_id": str(mat_doc.get("_id")) if mat_doc else "",
            "reorder_level": mat_doc.get("reorder_level", 0),
            "preferred_vendor_id": pref_v_id,
            "preferred_vendor_name": pref_v_name,
            "rate": m["rate"],
        })
    return {"jobs": req["jobs"], "shortage": rows}


@materials_router.get("/inventory/alerts")
async def inventory_alerts(request: Request):
    """List materials whose balance <= reorder_level."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    inv_rows = await list_inventory(request)
    alerts = []
    materials = await db.materials.find({}).to_list(2000)
    rl = {str(m["_id"]): float(m.get("reorder_level", 0) or 0) for m in materials}
    for r in inv_rows:
        threshold = rl.get(r["material_id"], 0)
        if threshold > 0 and r["balance"] <= threshold:
            alerts.append({**r, "reorder_level": threshold, "shortfall": round(threshold - r["balance"], 2)})
    alerts.sort(key=lambda x: x["balance"])
    return alerts


# ═══════════════════════════════════════════════════════════════════════
# ══ PROCUREMENT MATERIAL REQUIREMENTS ENDPOINTS ════════════════════════
# ═══════════════════════════════════════════════════════════════════════

@materials_router.post("/procurement/requirement")
async def procurement_requirement(payload: dict, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    return await _compute_material_requirement(job_ids, db=db)


@materials_router.post("/procurement/requirement.pdf")
async def procurement_requirement_pdf(payload: dict, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    scope_label = payload.get("scope_label") or f"{len(job_ids)} production card(s)"
    notes = payload.get("notes", "")
    split_by_color = bool(payload.get("split_by_color", False))
    data = await _compute_material_requirement(job_ids, db=db)
    pdf_bytes = build_material_requirement(
        scope_label,
        data["jobs"],
        data["materials"],
        notes,
        split_by_color=split_by_color,
        by_color=data.get("by_color")
    )
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="material-requirement-{datetime.now().strftime("%Y%m%d-%H%M")}.pdf"'},
    )
