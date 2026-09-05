"""B2B Purchase Orders, Production Jobs & Stages, Defect Tracking, and Production Card Routes."""

import io
import os
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any
from collections import defaultdict
from io import BytesIO

from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from auth import get_current_user_factory, require_roles
from models.orders import POIn, POLineItem, ProductionStageUpdate, PRODUCTION_STAGES
from models.materials import QuantityUpdate
from models.components import ComponentUpdate
from models.workers import AssignmentUpdate, BulkAssign
from models.vendors import GRNIn, GRNLineItem, DefectIn, PaymentIn
from rate_limiter import upload_rate_limiter, pdf_rate_limiter
from po_extractor import extract_po_from_pdf, extract_po_from_xlsx
from pdf_card import build_production_card, build_production_card_dual_a4

log = logging.getLogger("pos_routes")

pos_router = APIRouter(prefix="/api", tags=["Purchase Orders & Production"])


def get_db():
    import server
    return server.db


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
            doc[key] = [stringify(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in value]
    return doc


async def _get_user(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    fn = await get_current_user_factory(get_db())
    return await fn(request)


async def _log_activity(action: str, category: str, details: str, email: str, db=None):
    db = db if db is not None else get_db()
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "by": email,
            "created_at": now_iso(),
        })
    except Exception as e:
        log.warning(f"Failed to write audit log: {e}")

async def _get_stage_durations(db=None) -> Dict[str, float]:
    defaults = {"procurement": 24.0, "cutting": 48.0, "stitching": 48.0, "assembly": 48.0, "finishing": 24.0, "packaging": 24.0, "dispatch": 24.0}
    if db is None:
        import server
        db = getattr(server, "db", None)
    if db is None or not hasattr(db, "settings"):
        return defaults
    try:
        doc = await db.settings.find_one({"_id": "stage_durations"})
        if isinstance(doc, dict) and doc.get("durations"):
            return {**defaults, **doc["durations"]}
    except Exception:
        pass
    return defaults


def _compute_deadline(entered_iso: str, duration_hours: float) -> str:
    import server
    if hasattr(server, "_compute_deadline"):
        return server._compute_deadline(entered_iso, duration_hours)
    try:
        t = datetime.fromisoformat(entered_iso)
        return (t + timedelta(hours=duration_hours)).isoformat()
    except Exception:
        return ""


def _overdue_hours(deadline_iso: Optional[str]) -> float:
    import server
    if hasattr(server, "_overdue_hours"):
        return server._overdue_hours(deadline_iso)
    if not deadline_iso:
        return 0.0
    try:
        dl = datetime.fromisoformat(deadline_iso)
        now = datetime.now(timezone.utc)
        hrs = (now - dl).total_seconds() / 3600.0
        return round(hrs, 1) if hrs > 0 else 0.0
    except Exception:
        return 0.0


async def next_grn_no(db=None) -> str:
    db = db if db is not None else get_db()
    c = await db.counters.find_one_and_update(
        {"_id": "grn_no"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = c["seq"] if c else 1
    return f"GRN-{seq:05d}"


async def next_payment_no(db=None) -> str:
    db = db if db is not None else get_db()
    c = await db.counters.find_one_and_update(
        {"_id": "payment_no"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = c["seq"] if c else 1
    return f"PAY-{seq:05d}"


# ── Costing & Profitability Helpers ──────────────────────────────────────────

async def compute_style_costing_async(style: dict, db=None, color: Optional[str] = None) -> dict:
    db = db if db is not None else get_db()
    import server
    if hasattr(server, "compute_style_costing_async"):
        return await server.compute_style_costing_async(style, db, color=color)
    if hasattr(server, "compute_style_costing_from_jobs"):
        try:
            style_id = str(style.get("_id", style.get("id", "")))
            style_code = style.get("code", "")
            if not style_id and not style_code:
                return server.compute_style_costing_from_jobs(style, [], color=color)
            qc = []
            if style_id:
                qc.append({"style_id": style_id})
            if style_code:
                qc.append({"style_code": style_code})
            fetched_jobs = await db.production_jobs.find(
                {"$or": qc} if len(qc) > 1 else qc[0]
            ).to_list(500)
            return server.compute_style_costing_from_jobs(style, fetched_jobs, color=color)
        except Exception:
            return server.compute_style_costing_from_jobs(style, [], color=color)
    return {}


async def compute_po_profitability(po_line: dict, style_obj: dict, db=None) -> dict:
    db = db if db is not None else get_db()
    po_color = po_line.get("color")
    c = await compute_style_costing_async(style_obj, db, color=po_color)
    bom_cost = float(c.get("materials_cost", 0))
    overhead = float(c.get("overhead_cost", 0))
    packing = float(c.get("packing_cost", 0) or style_obj.get("packing_cost", 0) or 0)
    labor_cost = float(c.get("labor_cost", 0))
    labor_source = c.get("labor_source", "estimated")

    unit_price = float(po_line.get("unit_price", 0))
    total_cost = round(bom_cost + labor_cost + packing, 2)
    profit = round(unit_price - total_cost, 2) if unit_price > 0 else None
    profit_pct = round(profit / unit_price * 100, 1) if (profit is not None and unit_price > 0) else None

    return {
        "style_code": style_obj.get("code", "") or po_line.get("style_code", ""),
        "unit_price": round(unit_price, 2),
        "bom_cost": round(bom_cost, 2),
        "labor_cost": round(labor_cost, 2),
        "labor_source": labor_source,
        "is_estimated": labor_source == "estimated",
        "overhead_cost": round(overhead, 2),
        "packing_cost": round(packing, 2),
        "total_cost": total_cost,
        "profit": profit,
        "profit_pct": profit_pct,
    }


def _format_po_line_profitability(po_line: dict, style_obj: dict, costing: dict) -> dict:
    bom_cost = float(costing.get("materials_cost", 0))
    overhead = float(costing.get("overhead_cost", 0))
    packing = float(costing.get("packing_cost", 0) or style_obj.get("packing_cost", 0) or 0)
    labor_cost = float(costing.get("labor_cost", 0))
    labor_source = costing.get("labor_source", "estimated")

    unit_price = float(po_line.get("unit_price", 0))
    total_cost = round(bom_cost + labor_cost + packing, 2)
    profit = round(unit_price - total_cost, 2) if unit_price > 0 else None
    profit_pct = round(profit / unit_price * 100, 1) if (profit is not None and unit_price > 0) else None

    return {
        "style_code": style_obj.get("code", "") or po_line.get("style_code", ""),
        "unit_price": round(unit_price, 2),
        "bom_cost": round(bom_cost, 2),
        "labor_cost": round(labor_cost, 2),
        "labor_source": labor_source,
        "is_estimated": labor_source == "estimated",
        "overhead_cost": round(overhead, 2),
        "packing_cost": round(packing, 2),
        "total_cost": total_cost,
        "profit": profit,
        "profit_pct": profit_pct,
    }


async def _attach_po_profitability(po_docs: list, db=None):
    db = db if db is not None else get_db()
    codes = set()
    ids = set()
    for d in po_docs:
        for item in d.get("line_items", []):
            if item.get("style_code"):
                codes.add(item["style_code"].strip())
            if item.get("style_id"):
                try:
                    ids.add(oid(item["style_id"]))
                except Exception:
                    pass

    query_or = []
    if codes:
        query_or.append({"code": {"$in": list(codes)}})
    if ids:
        query_or.append({"_id": {"$in": list(ids)}})

    styles_map = {}
    unique_styles = []
    seen_style_keys = set()
    if query_or:
        styles = await db.styles.find({"$or": query_or} if len(query_or) > 1 else query_or[0]).to_list(10000)
        for s in styles:
            s_code = s.get("code", "")
            s_id = str(s.get("_id", ""))
            if s_code:
                styles_map[s_code] = s
            if s_id:
                styles_map[s_id] = s
            st_key = s_id or s_code
            if st_key and st_key not in seen_style_keys:
                seen_style_keys.add(st_key)
                unique_styles.append(s)

    # 1. Collect all style_ids and style_codes present across styles_map
    style_ids = [str(s.get("_id") or s.get("id")) for s in unique_styles if (s.get("_id") or s.get("id"))]
    style_codes = [s.get("code") for s in unique_styles if s.get("code")]

    jobs_by_style_id = defaultdict(list)
    jobs_by_style_code = defaultdict(list)

    # 2. Run ONE query: db.production_jobs.find({"$or": [{"style_id": {"$in": [...]}}, {"style_code": {"$in": [...]}}]})
    if style_ids or style_codes:
        job_or = []
        if style_ids:
            job_or.append({"style_id": {"$in": style_ids}})
        if style_codes:
            job_or.append({"style_code": {"$in": style_codes}})
        job_query = {"$or": job_or} if len(job_or) > 1 else job_or[0]
        all_jobs = await db.production_jobs.find(job_query).to_list(50000)

        # 3. Group the results into a dict keyed by style_id/style_code in memory
        for job in all_jobs:
            jid = job.get("style_id")
            if jid:
                jobs_by_style_id[str(jid)].append(job)
            jcode = job.get("style_code")
            if jcode:
                jobs_by_style_code[jcode].append(job)

    # Precompute costing per unique style
    from routes.styles import compute_style_costing_from_jobs
    costing_cache = {}
    for s in unique_styles:
        sid = str(s.get("_id") or s.get("id") or "")
        scode = s.get("code", "")
        matched_jobs = []
        seen_job_ids = set()
        for job in jobs_by_style_id.get(sid, []):
            job_id_key = str(job.get("_id", id(job)))
            if job_id_key not in seen_job_ids:
                seen_job_ids.add(job_id_key)
                matched_jobs.append(job)
        for job in jobs_by_style_code.get(scode, []):
            job_id_key = str(job.get("_id", id(job)))
            if job_id_key not in seen_job_ids:
                seen_job_ids.add(job_id_key)
                matched_jobs.append(job)

        c = compute_style_costing_from_jobs(s, matched_jobs)
        if sid:
            costing_cache[sid] = c
        if scode:
            costing_cache[scode] = c

    for d in po_docs:
        for item in d.get("line_items", []):
            code = (item.get("style_code") or "").strip()
            sid = str(item.get("style_id") or "")
            style_doc = styles_map.get(code) or styles_map.get(sid)
            if style_doc:
                item_color = item.get("color")
                if item_color and (style_doc.get("color_material_overrides") or style_doc.get("color_bom_overrides")) :
                    style_id_str = str(style_doc.get("_id") or style_doc.get("id") or "")
                    style_code_str = style_doc.get("code", "")
                    matched_jobs = []
                    seen_job_ids = set()
                    for job in jobs_by_style_id.get(style_id_str, []):
                        job_id_key = str(job.get("_id", id(job)))
                        if job_id_key not in seen_job_ids:
                            seen_job_ids.add(job_id_key)
                            matched_jobs.append(job)
                    for job in jobs_by_style_code.get(style_code_str, []):
                        job_id_key = str(job.get("_id", id(job)))
                        if job_id_key not in seen_job_ids:
                            seen_job_ids.add(job_id_key)
                            matched_jobs.append(job)
                    costing = compute_style_costing_from_jobs(style_doc, matched_jobs, color=item_color)
                else:
                    costing = costing_cache.get(code) or costing_cache.get(sid)
                    if costing is None:
                        # In-memory lookup from grouped jobs dict without DB queries
                        style_id_str = str(style_doc.get("_id") or style_doc.get("id") or "")
                        style_code_str = style_doc.get("code", "")
                        matched_jobs = []
                        seen_job_ids = set()
                        for job in jobs_by_style_id.get(style_id_str, []):
                            job_id_key = str(job.get("_id", id(job)))
                            if job_id_key not in seen_job_ids:
                                seen_job_ids.add(job_id_key)
                                matched_jobs.append(job)
                        for job in jobs_by_style_code.get(style_code_str, []):
                            job_id_key = str(job.get("_id", id(job)))
                            if job_id_key not in seen_job_ids:
                                seen_job_ids.add(job_id_key)
                                matched_jobs.append(job)
                        costing = compute_style_costing_from_jobs(style_doc, matched_jobs)

                bom_cost = float(costing.get("materials_cost", 0))
                overhead = float(costing.get("overhead_cost", 0))
                packing = float(costing.get("packing_cost", 0) or style_doc.get("packing_cost", 0) or 0)
                labor_cost = float(costing.get("labor_cost", 0))
                labor_source = costing.get("labor_source", "estimated")

                unit_price = float(item.get("unit_price", 0))
                total_cost = round(bom_cost + labor_cost + packing, 2)
                profit = round(unit_price - total_cost, 2) if unit_price > 0 else None
                profit_pct = round(profit / unit_price * 100, 1) if (profit is not None and unit_price > 0) else None

                item["profitability"] = {
                    "style_code": style_doc.get("code", "") or item.get("style_code", ""),
                    "unit_price": round(unit_price, 2),
                    "bom_cost": round(bom_cost, 2),
                    "labor_cost": round(labor_cost, 2),
                    "labor_source": labor_source,
                    "is_estimated": labor_source == "estimated",
                    "overhead_cost": round(overhead, 2),
                    "packing_cost": round(packing, 2),
                    "total_cost": total_cost,
                    "profit": profit,
                    "profit_pct": profit_pct,
                }


async def _attach_po_status(po_docs: list, db=None):
    """Compute and attach derived completion status for purchase orders.
    A PO is completed when ALL its production_jobs are archived/dispatched AND it has at least one invoice/dispatch on file.
    """
    db = db if db is not None else get_db()
    if not po_docs:
        return

    pid_strs = []
    pid_oids = []
    po_nums = []
    for d in po_docs:
        raw_id = d.get("_id") or d.get("id")
        if raw_id:
            s_id = str(raw_id)
            pid_strs.append(s_id)
            if ObjectId.is_valid(s_id):
                try:
                    pid_oids.append(oid(s_id))
                except Exception:
                    pass
        num = d.get("po_number")
        if num:
            po_nums.append(str(num))

    job_query_or = []
    if pid_strs:
        job_query_or.append({"po_id": {"$in": pid_strs}})
    if pid_oids:
        job_query_or.append({"po_id": {"$in": pid_oids}})
    if po_nums:
        job_query_or.append({"po_number": {"$in": po_nums}})

    jobs = []
    if job_query_or and hasattr(db, "production_jobs"):
        try:
            jobs = await db.production_jobs.find(
                {"$or": job_query_or} if len(job_query_or) > 1 else job_query_or[0],
                {"po_id": 1, "po_number": 1, "archived": 1, "stage": 1, "invoice_generated_at": 1, "status": 1}
            ).to_list(10000)
        except Exception as e:
            log.warning(f"Error querying production_jobs in _attach_po_status: {e}")

    inv_query_or = []
    if pid_strs:
        inv_query_or.append({"po_id": {"$in": pid_strs}})
        inv_query_or.append({"po_ids": {"$in": pid_strs}})
    if po_nums:
        inv_query_or.append({"po_number": {"$in": po_nums}})
        inv_query_or.append({"po_numbers": {"$in": po_nums}})

    invoices = []
    if inv_query_or and hasattr(db, "invoices"):
        try:
            invoices = await db.invoices.find(
                {"$or": inv_query_or} if len(inv_query_or) > 1 else inv_query_or[0],
                {"po_id": 1, "po_ids": 1, "po_number": 1, "po_numbers": 1}
            ).to_list(10000)
        except Exception as e:
            log.warning(f"Error querying invoices in _attach_po_status: {e}")

    dr_query_or = []
    if pid_strs:
        dr_query_or.append({"po_id": {"$in": pid_strs}})
        dr_query_or.append({"po_ids": {"$in": pid_strs}})
    if po_nums:
        dr_query_or.append({"po_number": {"$in": po_nums}})
        dr_query_or.append({"po_numbers": {"$in": po_nums}})

    dispatch_records = []
    if dr_query_or and hasattr(db, "dispatch_records"):
        try:
            dispatch_records = await db.dispatch_records.find(
                {"$or": dr_query_or} if len(dr_query_or) > 1 else dr_query_or[0],
                {"po_id": 1, "po_ids": 1, "po_number": 1, "po_numbers": 1}
            ).to_list(10000)
        except Exception as e:
            log.warning(f"Error querying dispatch_records in _attach_po_status: {e}")

    def _is_job_finished(j: dict) -> bool:
        return bool(
            j.get("archived") is True
            or j.get("stage") in ("dispatched", "completed")
            or j.get("status") in ("dispatched", "completed")
            or j.get("invoice_generated_at")
        )

    for d in po_docs:
        d_id = str(d.get("_id") or d.get("id") or "")
        d_num = str(d.get("po_number") or "")

        po_jobs = [
            j for j in jobs
            if (d_id and str(j.get("po_id") or "") == d_id)
            or (d_num and str(j.get("po_number") or "") == d_num)
        ]

        po_invoices = [
            inv for inv in invoices
            if (d_id and str(inv.get("po_id") or "") == d_id)
            or (d_id and isinstance(inv.get("po_ids"), list) and d_id in [str(x) for x in inv["po_ids"]])
            or (d_num and (str(inv.get("po_number") or "") == d_num or (isinstance(inv.get("po_numbers"), list) and d_num in inv["po_numbers"])))
        ]

        po_dispatches = [
            dr for dr in dispatch_records
            if (d_id and str(dr.get("po_id") or "") == d_id)
            or (d_id and isinstance(dr.get("po_ids"), list) and d_id in [str(x) for x in dr["po_ids"]])
            or (d_num and (str(dr.get("po_number") or "") == d_num or (isinstance(dr.get("po_numbers"), list) and d_num in dr["po_numbers"])))
        ]

        has_jobs = len(po_jobs) > 0
        all_jobs_done = has_jobs and all(_is_job_finished(j) for j in po_jobs)
        has_invoice_or_dispatch = (len(po_invoices) > 0) or (len(po_dispatches) > 0)

        is_completed = bool(all_jobs_done and has_invoice_or_dispatch)
        d["is_completed"] = is_completed
        d["computed_status"] = "completed" if is_completed else "active"
        if is_completed:
            d["status"] = "completed"
        elif not d.get("status") or d.get("status") == "completed":
            d["status"] = "active"


async def validate_po_styles(payload: POIn, db=None):
    """Validate and normalise style codes on a PO payload."""
    db = db if db is not None else get_db()
    import server
    from routes.sku_map import resolve_style

    all_styles = await db.styles.find({}, {"code": 1}).to_list(10000)
    existing_codes_upper = {s["code"].strip().upper(): s["code"] for s in all_styles}

    # Pass 1 — exact match
    unresolved = []
    for i, li in enumerate(payload.line_items):
        ext_code = (li.style_code or "").strip()
        if not ext_code:
            raise HTTPException(422, {
                "message": f"Line item #{i+1} has no style_code.",
                "unresolved_line_items": [],
            })
        if ext_code.upper() in existing_codes_upper:
            li.style_code = existing_codes_upper[ext_code.upper()]
        else:
            unresolved.append((i, ext_code))

    # Pass 2 — resolve_style() sku_map lookup
    still_missing = []
    for i, ext_code in unresolved:
        li_obj = payload.line_items[i]
        result = await resolve_style(
            source_type="b2b_client",
            source_name=payload.client_name,
            external_sku=ext_code,
            external_color=li_obj.color or None,
            external_size=str(li_obj.size) if li_obj.size else None,
            db=db,
        )
        if result["matched"] and result["match_via"] == "sku_map" and result.get("matched_exact", True):
            payload.line_items[i].style_code = result["style_code"]
            if result["color"] and result["color"] != (li_obj.color or ""):
                payload.line_items[i].color = result["color"]
            if result["size"] and result["size"] != str(li_obj.size or ""):
                payload.line_items[i].size = result["size"]
            payload.line_items[i].__dict__["_sku_map_meta"] = {
                "mapped_from_sku": result["mapped_from_sku"],
                "mapping_id":      result["mapping_id"],
            }
        elif result["matched"] and result["match_via"] == "style_code" and result.get("matched_exact", True):
            payload.line_items[i].style_code = result["style_code"]
        else:
            still_missing.append({
                "line_index":    i,
                "external_code": ext_code,
                "description":   li_obj.description or "",
                "color":         li_obj.color or "",
                "size":          str(li_obj.size or ""),
                "quantity":      li_obj.quantity,
            })

    # Pass 3 — refuse the PO if anything is still unresolved
    if still_missing:
        raise HTTPException(422, {
            "message": (
                f"{len(still_missing)} line item(s) reference style codes that "
                f"don't exist in our catalogue. Map each external code to an "
                f"existing SSK style (or create the styles first), then re-submit."
            ),
            "unresolved_line_items": still_missing,
            "client_name":           payload.client_name,
        })


async def _sync_po_sku_mappings(client_name: str, line_items: list, user_email: str, db=None):
    """Automatically persist or update SKU mappings for PO line items where external_sku is provided."""
    db = db if db is not None else get_db()
    from routes.sku_map import _norm_marketplace, _norm_key, _update_unmatched_jobs_for_sku_mapping

    client_name = (client_name or "").strip()
    if not client_name or not line_items:
        return

    all_styles = await db.styles.find({}, {"code": 1, "_id": 1}).to_list(10000)
    styles_by_code = {s["code"].strip().upper(): s for s in all_styles}

    for li in line_items:
        ext_sku = (li.get("external_sku") if isinstance(li, dict) else getattr(li, "external_sku", "")) or ""
        ext_sku = ext_sku.strip()
        style_code = (li.get("style_code") if isinstance(li, dict) else getattr(li, "style_code", "")) or ""
        style_code = style_code.strip()
        if not ext_sku or not style_code:
            continue
        if ext_sku.upper() == style_code.upper():
            continue

        style = styles_by_code.get(style_code.upper())
        if not style:
            continue

        existing = await db.sku_map.find_one({
            "source_type": "b2b_client",
            "source_name_key": _norm_marketplace(client_name),
            "external_sku_key": _norm_key(ext_sku),
        })
        if not existing:
            desc = (li.get("description") if isinstance(li, dict) else getattr(li, "description", "")) or ""
            mapping_doc = {
                "style_id": str(style["_id"]),
                "style_code": style["code"],
                "source_type": "b2b_client",
                "source_name": client_name,
                "external_sku": ext_sku,
                "external_style_name": desc,
                "source_name_key": _norm_marketplace(client_name),
                "external_sku_key": _norm_key(ext_sku),
                "color_map": {},
                "size_map": {},
                "image_url": "",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "created_by": user_email,
            }
            try:
                res = await db.sku_map.insert_one(mapping_doc)
                mapping_doc["id"] = str(res.inserted_id)
                await _log_activity("CREATE", "sku_map", f"Auto-mapped {ext_sku} ({client_name}) → {style['code']} from PO", user_email, db=db)
                await _update_unmatched_jobs_for_sku_mapping(res.inserted_id, mapping_doc, db=db)
            except DuplicateKeyError:
                pass


def _archive_if_complete(job_update: dict) -> None:
    if job_update.get("invoice_generated_at") and job_update.get("packing_generated_at"):
        job_update["archived"] = True
        job_update["archived_at"] = now_iso()


async def _flag_jobs(job_ids: list, field: str, db=None) -> None:
    db = db if db is not None else get_db()
    if not job_ids:
        return
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    now = now_iso()
    update_fields = {field: now}
    if field == "invoice_generated_at":
        update_fields["stage"] = "dispatched"
        update_fields["stage_entered_at"] = now
        update_fields["stage_deadline"] = None

    await db.production_jobs.update_many(
        {"_id": {"$in": obj_ids}},
        {"$set": update_fields},
    )
    
    if field == "invoice_generated_at":
        for o_id in obj_ids:
            await db.production_jobs.update_one(
                {"_id": o_id},
                {"$push": {"history": {
                    "stage": "dispatched", "at": now, "by": "system",
                    "notes": "Invoice generated and job dispatched",
                    "qc_pass": None, "rejected_qty": 0
                }}}
            )

    docs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    archive_ids = [d["_id"] for d in docs if d.get("invoice_generated_at") and d.get("packing_generated_at")]
    if archive_ids:
        await db.production_jobs.update_many(
            {"_id": {"$in": archive_ids}},
            {"$set": {"archived": True, "archived_at": now}},
        )


async def _build_client_ledger(cid_or_name: str, db=None) -> dict:
    db = db if db is not None else get_db()
    from routes.invoice_packing import (
        _aggregate_payments_for_invoices,
        _aggregate_grn_adjustments,
        _decorate_invoice,
        _invoice_iso_date,
        _due_iso,
    )

    client_name = cid_or_name
    if cid_or_name and ObjectId.is_valid(cid_or_name):
        c_doc = await db.clients.find_one({"_id": oid(cid_or_name)})
        if c_doc and c_doc.get("name"):
            client_name = c_doc["name"]
        else:
            inv_doc = await db.invoices.find_one({"_id": oid(cid_or_name)})
            if inv_doc and inv_doc.get("client_name"):
                client_name = inv_doc["client_name"]

    invs = await db.invoices.find({"client_name": client_name}, {"file_b64": 0}).to_list(2000)
    grns = await db.grns.find({"client_name": client_name}).to_list(2000)
    pays = await db.payments.find({"client_name": client_name}).to_list(2000)

    price_idx: dict[str, dict] = {}
    for inv in invs:
        iid = str(inv["_id"])
        prices = {(li.get("style_code"), li.get("color"), str(li.get("size") or "")):
                  float(li.get("unit_price") or 0) for li in (inv.get("line_items_snapshot") or [])}
        price_idx[iid] = prices

    entries = []
    transactions = []
    for inv in invs:
        d = inv.get("invoice_iso_date") or _invoice_iso_date(inv.get("invoice_date", ""))
        grand = float(inv.get("grand_total") or inv.get("net_amount") or 0)
        due_date = _due_iso(inv["grn_date"], int(inv.get("payment_terms_days") or 45)) if inv.get("grn_date") else inv.get("due_date")
        entries.append({
            "date": d,
            "vch_type": "Invoice",
            "vch_no": inv.get("invoice_no"),
            "particulars": f"Inv {inv.get('invoice_no')} · {(inv.get('po_numbers') or [inv.get('po_number')])[0] or ''}",
            "debit": grand,
            "credit": 0.0,
            "ref_id": str(inv["_id"]),
            "due_date": due_date,
            "grn_date": inv.get("grn_date"),
        })

    for g in grns:
        prices = price_idx.get(g.get("invoice_id", ""), {})
        short_value = 0.0
        for ln in g.get("line_items", []):
            short = max(0, int(ln.get("dispatched_qty", 0)) - int(ln.get("accepted_qty", 0)))
            unit = prices.get((ln.get("style_code"), ln.get("color"), str(ln.get("size") or ""))) or 0
            short_value += short * unit
        if short_value > 0:
            entries.append({
                "date": g.get("grn_date") or g.get("received_date") or "",
                "vch_type": "GR Adj",
                "vch_no": g.get("grn_no"),
                "particulars": f"GRN {g.get('grn_no')} · short/rejected {g.get('total_dispatched',0) - g.get('total_accepted',0)} pcs",
                "debit": 0.0,
                "credit": round(short_value, 2),
                "ref_id": str(g["_id"]),
            })

    for p in pays:
        entries.append({
            "date": p.get("payment_date") or "",
            "vch_type": "Payment",
            "vch_no": p.get("payment_no"),
            "particulars": f"{p.get('mode')} · {p.get('reference', '')}".strip(" ·"),
            "debit": 0.0,
            "credit": float(p.get("amount") or 0),
            "ref_id": str(p["_id"]),
            "mode": p.get("mode"),
            "reference": p.get("reference"),
        })

    entries.sort(key=lambda e: (e["date"] or "", e["vch_type"]))
    bal = 0.0
    for e in entries:
        bal += float(e["debit"]) - float(e["credit"])
        bal = round(bal, 2)
        e["debit"] = round(float(e["debit"]), 2)
        e["credit"] = round(float(e["credit"]), 2)
        e["balance"] = bal
        e["running_balance"] = bal
        tx_item = {
            "type": e["vch_type"].lower().replace(" ", "_"),
            "vch_type": e["vch_type"],
            "date": e["date"],
            "reference": e.get("vch_no") or e.get("ref_id"),
            "description": e["particulars"],
            "debit": e["debit"],
            "credit": e["credit"],
            "running_balance": bal,
            "due_date": e.get("due_date"),
        }
        transactions.append(tx_item)

    inv_ids = [str(d["_id"]) for d in invs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids, db=db)
    grn_map = await _aggregate_grn_adjustments(inv_ids, db=db)
    decorated = [_decorate_invoice(d, pay_map, grn_map) for d in invs]

    today = datetime.now(timezone.utc).date()
    ageing_buckets = {
        "current": 0.0,
        "days_1_30": 0.0,
        "days_31_60": 0.0,
        "days_60_plus": 0.0,
    }

    tot_invoiced = sum(float(r.get("net_amount") or 0) for r in decorated)
    tot_received = sum(float(r.get("received_amount") or 0) for r in decorated)

    for r in decorated:
        outstanding = float(r.get("outstanding") or 0)
        if outstanding <= 0:
            continue
        due_str = r.get("due_date") or r.get("invoice_date")
        if not due_str:
            ageing_buckets["current"] = round(ageing_buckets["current"] + outstanding, 2)
            continue
        try:
            due = datetime.strptime(str(due_str)[:10], "%Y-%m-%d").date()
            days_overdue = (today - due).days
        except Exception:
            days_overdue = 0

        if days_overdue <= 0:
            ageing_buckets["current"] = round(ageing_buckets["current"] + outstanding, 2)
        elif 1 <= days_overdue <= 30:
            ageing_buckets["days_1_30"] = round(ageing_buckets["days_1_30"] + outstanding, 2)
        elif 31 <= days_overdue <= 60:
            ageing_buckets["days_31_60"] = round(ageing_buckets["days_31_60"] + outstanding, 2)
        else:
            ageing_buckets["days_60_plus"] = round(ageing_buckets["days_60_plus"] + outstanding, 2)

    aging_list = [
        {"bucket": "0-30", "amount": round(ageing_buckets["days_1_30"] + ageing_buckets["current"], 2), "count": 0},
        {"bucket": "31-60", "amount": ageing_buckets["days_31_60"], "count": 0},
        {"bucket": "60+", "amount": ageing_buckets["days_60_plus"], "count": 0},
    ]

    return {
        "client_name": client_name,
        "total_invoiced": round(tot_invoiced, 2),
        "total_received": round(tot_received, 2),
        "closing_balance": bal,
        "balance_type": "Dr" if bal >= 0 else "Cr",
        "aging": aging_list,
        "ageing_buckets": ageing_buckets,
        "ledger": entries,
        "transactions": transactions,
    }


# ── B2B Profitability Endpoint ──────────────────────────────────────────────

@pos_router.get("/b2b-profitability")
async def get_b2b_profitability(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    style_id: Optional[str] = Query(None),
    db_override: Any = None,
):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db_inst = db_override or getattr(getattr(request, "app", None), "state", None) and getattr(request.app.state, "db", None) or get_db()

    today_str = now_iso()[:10]
    if not date_to or not date_to.strip():
        date_to = today_str
    if not date_from or not date_from.strip():
        try:
            d_to = datetime.strptime(date_to[:10], "%Y-%m-%d")
            date_from = (d_to - timedelta(days=30)).strftime("%Y-%m-%d")
        except Exception:
            date_from = "2000-01-01"

    inv_query = {}
    if date_from and date_to:
        inv_query["$or"] = [
            {"invoice_date": {"$gte": date_from, "$lte": date_to + "T23:59:59"}},
            {"invoice_iso_date": {"$gte": date_from, "$lte": date_to + "T23:59:59"}},
            {"supply_date": {"$gte": date_from, "$lte": date_to + "T23:59:59"}},
            {"created_at": {"$gte": date_from, "$lte": date_to + "T23:59:59"}},
        ]

    invoices = await db_inst.invoices.find(inv_query, {"file_b64": 0}).sort("created_at", -1).to_list(5000)

    pos_map = {}
    po_ids = set()
    for inv in invoices:
        if inv.get("po_id"):
            try:
                po_ids.add(oid(inv["po_id"]))
            except Exception:
                pass

    if po_ids:
        pos_list = await db_inst.pos.find({"_id": {"$in": list(po_ids)}}).to_list(5000)
        for p in pos_list:
            pos_map[str(p["_id"])] = stringify(p)
            if p.get("po_number"):
                pos_map[p["po_number"]] = stringify(p)

    all_lines = []
    if not invoices:
        po_query = {}
        if date_from and date_to:
            po_query["$or"] = [
                {"po_date": {"$gte": date_from, "$lte": date_to + "T23:59:59"}},
                {"created_at": {"$gte": date_from, "$lte": date_to + "T23:59:59"}},
            ]
        po_docs = await db_inst.pos.find(po_query).sort("created_at", -1).to_list(5000)
        for p in po_docs:
            p_str = stringify(p)
            c_name = p_str.get("client_name") or p_str.get("client", {}).get("name") or "Unknown Client"
            c_id = p_str.get("client_id") or ""
            p_date = (p_str.get("po_date") or p_str.get("created_at") or "")[:10]
            po_no = p_str.get("po_number", "PO-N/A")

            for item in p_str.get("line_items", []):
                all_lines.append({
                    "po_id": p_str.get("id"),
                    "po_number": po_no,
                    "invoice_no": None,
                    "invoice_date": p_date,
                    "client_id": c_id,
                    "client_name": c_name,
                    "item": item,
                })
    else:
        for inv in invoices:
            inv_str = stringify(inv)
            inv_no = inv_str.get("invoice_no") or "INV-N/A"
            inv_date = (inv_str.get("invoice_date") or inv_str.get("invoice_iso_date") or inv_str.get("created_at") or "")[:10]
            po_id = inv_str.get("po_id")
            po_obj = pos_map.get(str(po_id)) or pos_map.get(inv_str.get("po_number")) or {}
            c_name = inv_str.get("client_name") or po_obj.get("client_name") or "Unknown Client"
            c_id = po_obj.get("client_id") or ""

            line_items = inv_str.get("line_items_snapshot") or inv_str.get("line_items") or po_obj.get("line_items", [])
            for item in line_items:
                all_lines.append({
                    "po_id": po_id,
                    "po_number": inv_str.get("po_number") or po_obj.get("po_number") or "PO-N/A",
                    "invoice_no": inv_no,
                    "invoice_date": inv_date,
                    "client_id": c_id,
                    "client_name": c_name,
                    "item": item,
                })

    if client_id and isinstance(client_id, str):
        c_id_lower = client_id.lower().strip()
        all_lines = [
            l for l in all_lines
            if (l["client_id"] and str(l["client_id"]).lower() == c_id_lower) or
               (l["client_name"] and c_id_lower in str(l["client_name"]).lower())
        ]

    codes = set()
    sids = set()
    for l in all_lines:
        it = l["item"]
        if it.get("style_code"):
            codes.add(str(it["style_code"]).strip())
        if it.get("style_id"):
            try:
                sids.add(oid(it["style_id"]))
            except Exception:
                pass

    query_styles = []
    if codes:
        query_styles.append({"code": {"$in": list(codes)}})
    if sids:
        query_styles.append({"_id": {"$in": list(sids)}})

    styles_map = {}
    unique_styles = []
    seen_style_keys = set()
    if query_styles:
        found_styles = await db_inst.styles.find({"$or": query_styles} if len(query_styles) > 1 else query_styles[0]).to_list(10000)
        for s in found_styles:
            s_code = s.get("code", "")
            s_id = str(s.get("_id", ""))
            if s_code:
                styles_map[s_code] = s
            if s_id:
                styles_map[s_id] = s
            st_key = s_id or s_code
            if st_key and st_key not in seen_style_keys:
                seen_style_keys.add(st_key)
                unique_styles.append(s)

    # 1. Batch fetch production jobs for all unique styles
    style_ids = [str(s.get("_id") or s.get("id")) for s in unique_styles if (s.get("_id") or s.get("id"))]
    style_codes = [s.get("code") for s in unique_styles if s.get("code")]

    jobs_by_style_id = defaultdict(list)
    jobs_by_style_code = defaultdict(list)

    if style_ids or style_codes:
        job_or = []
        if style_ids:
            job_or.append({"style_id": {"$in": style_ids}})
        if style_codes:
            job_or.append({"style_code": {"$in": style_codes}})
        job_query = {"$or": job_or} if len(job_or) > 1 else job_or[0]
        all_jobs = await db_inst.production_jobs.find(job_query).to_list(50000)
        for job in all_jobs:
            jid = job.get("style_id")
            if jid:
                jobs_by_style_id[str(jid)].append(job)
            jcode = job.get("style_code")
            if jcode:
                jobs_by_style_code[jcode].append(job)

    from routes.styles import compute_style_costing_from_jobs
    costing_cache = {}
    for s in unique_styles:
        sid = str(s.get("_id") or s.get("id") or "")
        scode = s.get("code", "")
        matched_jobs = []
        seen_job_ids = set()
        for job in jobs_by_style_id.get(sid, []):
            job_id_key = str(job.get("_id", id(job)))
            if job_id_key not in seen_job_ids:
                seen_job_ids.add(job_id_key)
                matched_jobs.append(job)
        for job in jobs_by_style_code.get(scode, []):
            job_id_key = str(job.get("_id", id(job)))
            if job_id_key not in seen_job_ids:
                seen_job_ids.add(job_id_key)
                matched_jobs.append(job)

        c = compute_style_costing_from_jobs(s, matched_jobs)
        if sid:
            costing_cache[sid] = c
        if scode:
            costing_cache[scode] = c

    processed_lines = []
    by_client_map = {}
    by_style_map = {}
    by_month_map = {}

    total_revenue = 0.0
    total_cost = 0.0
    total_profit = 0.0
    total_pairs = 0

    confirmed_revenue = 0.0
    confirmed_cost = 0.0
    confirmed_profit = 0.0
    confirmed_lines_count = 0

    estimated_revenue = 0.0
    estimated_cost = 0.0
    estimated_profit = 0.0
    estimated_lines_count = 0

    for l in all_lines:
        it = l["item"]
        code = str(it.get("style_code") or "").strip()
        sid = str(it.get("style_id") or "")
        style_doc = styles_map.get(code) or styles_map.get(sid)

        if style_id and isinstance(style_id, str):
            st_id_lower = style_id.lower().strip()
            if style_doc:
                s_code = str(style_doc.get("code", "")).lower()
                s_id = str(style_doc.get("_id", "")).lower()
                if st_id_lower not in (s_code, s_id):
                    continue
            elif st_id_lower not in (code.lower(), sid.lower()):
                continue

        qty = int(it.get("quantity") or it.get("qty") or it.get("pairs") or 1)
        if style_doc:
            item_color = it.get("color")
            if item_color and (style_doc.get("color_material_overrides") or style_doc.get("color_bom_overrides")):
                style_id_str = str(style_doc.get("_id") or style_doc.get("id") or "")
                style_code_str = style_doc.get("code", "")
                matched_jobs = []
                seen_job_ids = set()
                for job in jobs_by_style_id.get(style_id_str, []):
                    job_id_key = str(job.get("_id", id(job)))
                    if job_id_key not in seen_job_ids:
                        seen_job_ids.add(job_id_key)
                        matched_jobs.append(job)
                for job in jobs_by_style_code.get(style_code_str, []):
                    job_id_key = str(job.get("_id", id(job)))
                    if job_id_key not in seen_job_ids:
                        seen_job_ids.add(job_id_key)
                        matched_jobs.append(job)
                costing = compute_style_costing_from_jobs(style_doc, matched_jobs, color=item_color)
            else:
                costing = costing_cache.get(code) or costing_cache.get(sid)
                if costing is None:
                    style_id_str = str(style_doc.get("_id") or style_doc.get("id") or "")
                    style_code_str = style_doc.get("code", "")
                    matched_jobs = []
                    seen_job_ids = set()
                    for job in jobs_by_style_id.get(style_id_str, []):
                        job_id_key = str(job.get("_id", id(job)))
                        if job_id_key not in seen_job_ids:
                            seen_job_ids.add(job_id_key)
                            matched_jobs.append(job)
                    for job in jobs_by_style_code.get(style_code_str, []):
                        job_id_key = str(job.get("_id", id(job)))
                        if job_id_key not in seen_job_ids:
                            seen_job_ids.add(job_id_key)
                            matched_jobs.append(job)
                    costing = compute_style_costing_from_jobs(style_doc, matched_jobs)

            bom_cost = float(costing.get("materials_cost", 0))
            overhead = float(costing.get("overhead_cost", 0))
            packing = float(costing.get("packing_cost", 0) or style_doc.get("packing_cost", 0) or 0)
            labor_cost = float(costing.get("labor_cost", 0))
            labor_source = costing.get("labor_source", "estimated")

            unit_price = float(it.get("unit_price", 0))
            total_cost_val = round(bom_cost + labor_cost + packing, 2)
            profit_val = round(unit_price - total_cost_val, 2) if unit_price > 0 else None
            profit_pct_val = round(profit_val / unit_price * 100, 1) if (profit_val is not None and unit_price > 0) else None

            prof = {
                "style_code": style_doc.get("code", "") or it.get("style_code", ""),
                "unit_price": round(unit_price, 2),
                "bom_cost": round(bom_cost, 2),
                "labor_cost": round(labor_cost, 2),
                "labor_source": labor_source,
                "is_estimated": labor_source == "estimated",
                "overhead_cost": round(overhead, 2),
                "packing_cost": round(packing, 2),
                "total_cost": total_cost_val,
                "profit": profit_val,
                "profit_pct": profit_pct_val,
            }
        else:
            u_price = float(it.get("unit_price") or it.get("price") or it.get("rate") or 0)
            prof = {
                "unit_price": u_price,
                "bom_cost": 0.0,
                "labor_cost": 0.0,
                "labor_source": "estimated",
                "is_estimated": True,
                "overhead_cost": 0.0,
                "packing_cost": 0.0,
                "total_cost": 0.0,
                "profit": u_price,
                "profit_pct": 100.0 if u_price > 0 else 0.0,
            }

        unit_price = float(prof.get("unit_price", 0))
        unit_bom = float(prof.get("bom_cost", 0))
        unit_labor = float(prof.get("labor_cost", 0))
        unit_overhead = float(prof.get("overhead_cost", 0))
        unit_packing = float(prof.get("packing_cost", 0))
        unit_total_cost = float(prof.get("total_cost", 0))
        is_est = bool(prof.get("is_estimated", True))

        line_rev = round(unit_price * qty, 2)
        line_cst = round(unit_total_cost * qty, 2)
        line_prf = round((unit_price - unit_total_cost) * qty, 2)
        line_prf_pct = round((line_prf / line_rev * 100), 1) if line_rev > 0 else 0.0

        style_code_disp = code or (style_doc.get("code") if style_doc else "N/A")
        style_name_disp = it.get("style_name") or (style_doc.get("name") if style_doc else "Unknown Style")
        c_name = l["client_name"]
        inv_d = l["invoice_date"] or "N/A"
        month_key = inv_d[:7] if len(inv_d) >= 7 else "N/A"

        line_rec = {
            "id": f"{l['po_number']}_{style_code_disp}_{qty}",
            "po_number": l["po_number"],
            "invoice_no": l["invoice_no"],
            "invoice_date": inv_d,
            "client_name": c_name,
            "style_code": style_code_disp,
            "style_name": style_name_disp,
            "quantity": qty,
            "unit_price": unit_price,
            "bom_cost": unit_bom,
            "labor_cost": unit_labor,
            "labor_source": prof.get("labor_source", "estimated"),
            "is_estimated": is_est,
            "overhead_cost": unit_overhead,
            "packing_cost": unit_packing,
            "unit_total_cost": unit_total_cost,
            "line_revenue": line_rev,
            "line_cost": line_cst,
            "line_profit": line_prf,
            "profit_pct": line_prf_pct,
        }
        processed_lines.append(line_rec)

        total_revenue += line_rev
        total_cost += line_cst
        total_profit += line_prf
        total_pairs += qty

        if is_est:
            estimated_revenue += line_rev
            estimated_cost += line_cst
            estimated_profit += line_prf
            estimated_lines_count += 1
        else:
            confirmed_revenue += line_rev
            confirmed_cost += line_cst
            confirmed_profit += line_prf
            confirmed_lines_count += 1

        if c_name not in by_client_map:
            by_client_map[c_name] = {
                "client_name": c_name,
                "total_pairs": 0,
                "total_revenue": 0.0,
                "total_cost": 0.0,
                "total_profit": 0.0,
                "confirmed_profit": 0.0,
                "confirmed_lines_count": 0,
                "estimated_profit": 0.0,
                "estimated_lines_count": 0,
                "lines": [],
            }
        bc = by_client_map[c_name]
        bc["total_pairs"] += qty
        bc["total_revenue"] += line_rev
        bc["total_cost"] += line_cst
        bc["total_profit"] += line_prf
        if is_est:
            bc["estimated_profit"] += line_prf
            bc["estimated_lines_count"] += 1
        else:
            bc["confirmed_profit"] += line_prf
            bc["confirmed_lines_count"] += 1
        bc["lines"].append(line_rec)

        if style_code_disp not in by_style_map:
            by_style_map[style_code_disp] = {
                "style_code": style_code_disp,
                "style_name": style_name_disp,
                "total_pairs": 0,
                "total_revenue": 0.0,
                "total_cost": 0.0,
                "total_profit": 0.0,
                "confirmed_profit": 0.0,
                "confirmed_lines_count": 0,
                "estimated_profit": 0.0,
                "estimated_lines_count": 0,
                "lines": [],
            }
        bs = by_style_map[style_code_disp]
        bs["total_pairs"] += qty
        bs["total_revenue"] += line_rev
        bs["total_cost"] += line_cst
        bs["total_profit"] += line_prf
        if is_est:
            bs["estimated_profit"] += line_prf
            bs["estimated_lines_count"] += 1
        else:
            bs["confirmed_profit"] += line_prf
            bs["confirmed_lines_count"] += 1
        bs["lines"].append(line_rec)

        if month_key not in by_month_map:
            by_month_map[month_key] = {
                "month": month_key,
                "total_pairs": 0,
                "total_revenue": 0.0,
                "total_cost": 0.0,
                "total_profit": 0.0,
                "confirmed_profit": 0.0,
                "confirmed_lines_count": 0,
                "estimated_profit": 0.0,
                "estimated_lines_count": 0,
            }
        bm = by_month_map[month_key]
        bm["total_pairs"] += qty
        bm["total_revenue"] += line_rev
        bm["total_cost"] += line_cst
        bm["total_profit"] += line_prf
        if is_est:
            bm["estimated_profit"] += line_prf
            bm["estimated_lines_count"] += 1
        else:
            bm["confirmed_profit"] += line_prf
            bm["confirmed_lines_count"] += 1

    def _finalize_list(item_map):
        res = []
        for k, v in item_map.items():
            v["total_revenue"] = round(v["total_revenue"], 2)
            v["total_cost"] = round(v["total_cost"], 2)
            v["total_profit"] = round(v["total_profit"], 2)
            v["confirmed_profit"] = round(v["confirmed_profit"], 2)
            v["estimated_profit"] = round(v["estimated_profit"], 2)
            v["profit_pct"] = round((v["total_profit"] / v["total_revenue"] * 100), 1) if v["total_revenue"] > 0 else 0.0
            res.append(v)
        res.sort(key=lambda x: x["total_profit"], reverse=True)
        return res

    by_client = _finalize_list(by_client_map)
    by_style = _finalize_list(by_style_map)

    by_month = []
    for k, v in by_month_map.items():
        v["total_revenue"] = round(v["total_revenue"], 2)
        v["total_cost"] = round(v["total_cost"], 2)
        v["total_profit"] = round(v["total_profit"], 2)
        v["confirmed_profit"] = round(v["confirmed_profit"], 2)
        v["estimated_profit"] = round(v["estimated_profit"], 2)
        v["profit_pct"] = round((v["total_profit"] / v["total_revenue"] * 100), 1) if v["total_revenue"] > 0 else 0.0
        by_month.append(v)
    by_month.sort(key=lambda x: x["month"])

    tot_rev = round(total_revenue, 2)
    tot_cst = round(total_cost, 2)
    tot_prf = round(total_profit, 2)
    tot_pct = round((tot_prf / tot_rev * 100), 1) if tot_rev > 0 else 0.0

    return {
        "summary": {
            "total_revenue": tot_rev,
            "total_cost": tot_cst,
            "total_profit": tot_prf,
            "profit_pct": tot_pct,
            "total_pairs": total_pairs,
            "confirmed_revenue": round(confirmed_revenue, 2),
            "confirmed_cost": round(confirmed_cost, 2),
            "confirmed_profit": round(confirmed_profit, 2),
            "confirmed_lines_count": confirmed_lines_count,
            "estimated_revenue": round(estimated_revenue, 2),
            "estimated_cost": round(estimated_cost, 2),
            "estimated_profit": round(estimated_profit, 2),
            "estimated_lines_count": estimated_lines_count,
            "total_lines_count": len(processed_lines),
        },
        "by_client": by_client,
        "by_style": by_style,
        "by_month": by_month,
        "lines": processed_lines,
    }


# ── Purchase Orders Endpoints ────────────────────────────────────────────────

@pos_router.get("/pos")
async def list_pos(request: Request, status: Optional[str] = Query(None)):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = get_db()
    docs = await db.pos.find({}).sort("created_at", -1).to_list(1000)
    await _attach_po_profitability(docs, db)
    await _attach_po_status(docs, db)
    if status == "completed":
        docs = [d for d in docs if d.get("is_completed")]
    elif status == "active":
        docs = [d for d in docs if not d.get("is_completed")]
    return [stringify(d) for d in docs]


@pos_router.get("/pos/{pid}")
async def get_po(pid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = get_db()
    d = await db.pos.find_one({"_id": oid(pid)})
    if not d:
        raise HTTPException(404, "Not found")
    await _attach_po_profitability([d], db)
    await _attach_po_status([d], db)
    return stringify(d)


@pos_router.post("/pos/validate-styles")
async def validate_po_styles_endpoint(payload: POIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = get_db()
    await validate_po_styles(payload, db=db)
    return {"ok": True, "line_count": len(payload.line_items)}


@pos_router.post("/pos")
async def create_po(payload: POIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    await validate_po_styles(payload, db=db)
    po_num = payload.po_number.strip()
    if await db.pos.find_one({"po_number": {"$regex": f"^{re.escape(po_num)}$", "$options": "i"}}):
        raise HTTPException(status_code=409, detail=f"Purchase Order with PO number '{po_num}' already exists")
    payload.po_number = po_num
    doc = payload.model_dump()
    doc["status"] = "pending"
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    if not doc.get("total_quantity"):
        doc["total_quantity"] = sum(li["quantity"] for li in doc["line_items"])
    if not doc.get("subtotal"):
        doc["subtotal"] = sum(li["amount"] for li in doc["line_items"])
    try:
        res = await db.pos.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Purchase Order with PO number '{po_num}' already exists")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)

    jobs = []
    durations = await _get_stage_durations(db=db)
    entered = now_iso()
    deadline = _compute_deadline(entered, durations.get("procurement", 24))
    
    all_styles = await db.styles.find({}, {"code": 1, "_id": 1}).to_list(10000)
    style_id_map = {s["code"].strip().upper(): str(s["_id"]) for s in all_styles}

    sku_meta_by_code = {}
    for li_obj in payload.line_items:
        meta = getattr(li_obj, "__dict__", {}).get("_sku_map_meta")
        if meta:
            sku_meta_by_code[li_obj.style_code.strip().upper()] = meta

    for li in doc["line_items"]:
        style_code_upper = li["style_code"].strip().upper()
        style_id = style_id_map.get(style_code_upper)
        sku_meta = sku_meta_by_code.get(style_code_upper)

        if style_id and sku_meta:
            match_status = "mapped"
        elif style_id:
            match_status = "matched"
        else:
            match_status = "unmatched"

        jobs.append({
            "source_type": "b2b_client",
            "po_id": doc["id"],
            "po_number": doc["po_number"],
            "client_name": doc["client_name"],
            "style_code": li["style_code"],
            "style_id": style_id,
            "style_match_status": match_status,
            **(({"mapped_from_sku": sku_meta["mapped_from_sku"], "sku_mapping_id": sku_meta["mapping_id"]}) if sku_meta else {}),
            "description": li.get("description", ""),
            "color": li.get("color", ""),
            "size": li.get("size", ""),
            "quantity": li["quantity"],
            "completed_qty": 0,
            "stage": "planning",
            "rejected_qty": 0,
            "delivery_date": doc.get("delivery_date", ""),
            "stage_entered_at": entered,
            "stage_deadline": deadline,
            "split_from_job_id": None,
            "split_history": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "history": [{"stage": "planning", "at": now_iso(), "by": u["email"], "notes": "Job created in planning"}],
        })
    if jobs:
        await db.production_jobs.insert_many(jobs)

    await _sync_po_sku_mappings(doc.get("client_name"), doc.get("line_items", []), u.get("email", "system"), db=db)
    return doc


@pos_router.patch("/pos/{pid}")
async def update_po(pid: str, payload: POIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    await validate_po_styles(payload, db=db)
    po_num = payload.po_number.strip()
    if await db.pos.find_one({"po_number": {"$regex": f"^{re.escape(po_num)}$", "$options": "i"}, "_id": {"$ne": oid(pid)}}):
        raise HTTPException(status_code=409, detail=f"Purchase Order with PO number '{po_num}' already exists")
    payload.po_number = po_num
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.pos.update_one({"_id": oid(pid)}, {"$set": update})
    await _sync_po_sku_mappings(update.get("client_name"), update.get("line_items", []), u.get("email", "system"), db=db)
    return stringify(await db.pos.find_one({"_id": oid(pid)}))


@pos_router.delete("/pos/{pid}")
async def delete_po(pid: str, request: Request, force: bool = False):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    po = await db.pos.find_one({"_id": oid(pid)})
    if not po:
        raise HTTPException(404, "Purchase Order not found")
    po_num = po.get("po_number", "N/A")

    disp_count = await db.dispatch_records.count_documents({"$or": [{"po_id": pid}, {"po_ids": pid}]})
    inv_docs = await db.invoices.find({"$or": [{"po_id": pid}, {"po_ids": pid}]}).to_list(1000)
    inv_count = len(inv_docs)

    if (disp_count > 0 or inv_count > 0) and not force:
        inv_nos = ", ".join([i.get("invoice_no", "") for i in inv_docs if i.get("invoice_no")][:3])
        history_desc = []
        if disp_count > 0:
            history_desc.append(f"{disp_count} dispatch record(s)")
        if inv_count > 0:
            history_desc.append(f"{inv_count} invoice(s)" + (f" ({inv_nos})" if inv_nos else ""))

        raise HTTPException(
            409,
            f"Cannot delete PO — it has dispatch/invoice history: {', '.join(history_desc)}. "
            "To remove this PO and clean up its un-dispatched invoice(s), confirm Force Delete."
        )

    # If force is true and invoices exist, clean up linked invoices, payments, and cartons
    if inv_docs:
        from routes.invoice_packing import _get_max_invoice_seq
        for inv in inv_docs:
            inv_id_str = str(inv["_id"])
            await db.payments.delete_many({"invoice_id": inv_id_str})
            await db.dispatch_records.delete_many({"$or": [{"invoice_id": inv_id_str}, {"invoice_no": inv.get("invoice_no")}]})
            await db.packing_cartons.update_many(
                {"invoice_id": inv_id_str},
                {"$set": {"status": "packed", "invoice_id": None, "box_number": None}}
            )
            await db.invoices.delete_one({"_id": inv["_id"]})

        try:
            today = datetime.now(timezone.utc)
            yr = today.year
            fy_start = yr - 1 if today.month < 4 else yr
            fy_end = fy_start + 1
            fy_label = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}"
            min_seq = 16 if fy_label == "26-27" else 1
            max_existing = await _get_max_invoice_seq(fy_label, db=db)
            target_seq = max(min_seq - 1, max_existing)
            await db.counters.update_one(
                {"_id": f"invoice_{fy_label}"},
                {"$set": {"seq": target_seq}},
                upsert=True,
            )
        except Exception as e:
            log.warning(f"Failed to resync invoice counter after PO force deletion: {e}")

    from routes.materials import _compute_material_inventory_summary

    jobs = await db.production_jobs.find({
        "$or": [
            {"po_id": pid},
            {"po_id": oid(pid)} if ObjectId.is_valid(pid) else {"po_id": pid},
            {"po_number": po_num},
        ]
    }).to_list(10000)

    job_id_strs = [str(j["_id"]) for j in jobs]
    job_oids = [j["_id"] for j in jobs]

    mov_query = {
        "$or": [
            {"job_id": {"$in": job_id_strs}},
            {"job_id": {"$in": job_oids}},
            {"po_id": pid},
        ]
    }
    existing_movements = await db.inventory_movements.find(mov_query).to_list(10000)

    reversal_movements = []
    materials_to_update = set()

    for m in existing_movements:
        if m.get("is_reversal"):
            continue
        mtype = m.get("type")
        qty = float(m.get("quantity", 0) or 0)
        mid = m.get("material_id")
        if not mid or (qty <= 0 and mtype != "adjustment"):
            continue

        materials_to_update.add(mid)

        if mtype == "out":
            rev_type = "in"
            rev_qty = qty
        elif mtype == "in":
            rev_type = "out"
            rev_qty = qty
        else:
            rev_type = "adjustment"
            rev_qty = -qty

        reversal_movements.append({
            "material_id": mid,
            "material_code": m.get("material_code", ""),
            "material_name": m.get("material_name", ""),
            "unit": m.get("unit", ""),
            "type": rev_type,
            "quantity": rev_qty,
            "rate": m.get("rate"),
            "party": f"Reversal (PO {po_num})",
            "job_id": m.get("job_id"),
            "po_id": pid,
            "notes": f"Compensating reversal of {mtype} movement ({str(m.get('_id', ''))}) due to deletion of PO {po_num}",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "by": u["email"],
            "created_at": now_iso(),
            "is_reversal": True,
            "reversal_of": str(m.get("_id", "")),
        })

    if reversal_movements:
        await db.inventory_movements.insert_many(reversal_movements)

        for mid in materials_to_update:
            try:
                summary = await _compute_material_inventory_summary(mid, db=db)
                mat_doc = await db.materials.find_one({"_id": oid(mid)})
                fallback_rate = (mat_doc.get("rate") or 0.0) if mat_doc else 0.0
                await db.materials.update_one(
                    {"_id": oid(mid)},
                    {"$set": {
                        "balance": round(summary["balance"], 2),
                        "weighted_avg_rate": round(summary["weighted_avg_rate"], 2),
                        "last_purchase_rate": round(summary["last_rate"], 2) if summary["last_rate"] else fallback_rate,
                        "updated_at": now_iso(),
                    }}
                )
            except Exception as e:
                log.error(f"Error updating material {mid} during PO deletion reversal: {e}")

    if job_id_strs:
        comp_movs = await db.component_stock_movements.find({
            "$or": [
                {"reference_id": {"$in": job_id_strs}},
                {"reference_id": pid},
            ]
        }).to_list(10000)

        for cm in comp_movs:
            if cm.get("is_reversal"):
                continue
            cmtype = cm.get("movement_type")
            cqty = int(cm.get("quantity", 0) or 0)
            cid = cm.get("component_id")
            if not cid or cqty <= 0:
                continue

            comp = await db.component_master.find_one({"_id": oid(cid) if isinstance(cid, str) else cid})
            if comp:
                if cmtype == "production_reserve":
                    await db.component_master.update_one(
                        {"_id": comp["_id"]},
                        {"$inc": {"reserved_stock": -cqty}, "$set": {"updated_at": now_iso()}}
                    )
                elif cmtype == "production_issue":
                    await db.component_master.update_one(
                        {"_id": comp["_id"]},
                        {"$inc": {"current_stock": cqty}, "$set": {"updated_at": now_iso()}}
                    )

    rev_count = len(reversal_movements)
    await _log_activity(
        "DELETE",
        "po",
        f"Deleted PO {po_num} (ID: {pid}): deleted {len(jobs)} production jobs, posted {rev_count} compensating inventory reversal movements to restore stock",
        u["email"],
        db=db,
    )

    await db.production_jobs.delete_many({
        "$or": [
            {"po_id": pid},
            {"po_id": oid(pid)} if ObjectId.is_valid(pid) else {"po_id": pid},
            {"po_number": po_num},
        ]
    })
    await db.pos.delete_one({"_id": oid(pid)})
    return {"ok": True, "reversed_movements_count": rev_count}


@pos_router.post("/pos/extract", dependencies=[Depends(upload_rate_limiter)])
async def extract_po(file: UploadFile = File(...), force_ai: bool = False, request: Request = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds the maximum limit of 10MB.")
    fname = (file.filename or "").lower()
    try:
        if fname.endswith(".pdf"):
            data = await extract_po_from_pdf(content, force_ai=force_ai)
        elif fname.endswith(".xlsx") or fname.endswith(".xls"):
            data = await extract_po_from_xlsx(content, force_ai=force_ai)
        else:
            raise HTTPException(400, "Only PDF or Excel (xlsx) files are supported")
        return data
    except HTTPException:
        raise
    except Exception as e:
        log.exception("PO extraction failed")
        raise HTTPException(500, f"Extraction failed: {e}")


# ── Goods Receipt Notes (GRN) ────────────────────────────────────────────────

@pos_router.post("/grns")
async def create_grn(payload: GRNIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    from routes.invoice_packing import _aggregate_grn_adjustments, _due_iso

    inv = await db.invoices.find_one({"_id": oid(payload.invoice_id)})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    grn_no = await next_grn_no(db=db)
    lines = []
    total_disp = total_recv = total_acc = total_rej = 0
    for idx, li in enumerate(payload.line_items, 1):
        disp = int(li.dispatched_qty or 0)
        recv = int(li.received_qty if li.received_qty is not None else disp)
        rej = int(li.rejected_qty or 0)

        if recv > disp:
            line_desc = f"{li.style_code} ({li.color}/{li.size})" if (li.style_code or li.color or li.size) else f"Line #{idx}"
            raise HTTPException(
                status_code=400,
                detail=f"Received quantity ({recv}) cannot exceed dispatched quantity ({disp}) for {line_desc}."
            )

        if rej > recv:
            line_desc = f"{li.style_code} ({li.color}/{li.size})" if (li.style_code or li.color or li.size) else f"Line #{idx}"
            raise HTTPException(
                status_code=400,
                detail=f"Rejected quantity ({rej}) cannot exceed received quantity ({recv}) for {line_desc}."
            )

        acc = int(li.accepted_qty if li.accepted_qty is not None else (recv - rej))
        acc = max(0, min(recv - rej, disp))

        lines.append({
            "style_code": li.style_code, "description": li.description,
            "color": li.color, "size": li.size,
            "dispatched_qty": disp, "received_qty": recv,
            "accepted_qty": acc, "rejected_qty": rej,
            "rejection_reason": li.rejection_reason,
        })
        total_disp += disp; total_recv += recv; total_acc += acc; total_rej += rej

    doc = {
        "grn_no": grn_no, "grn_date": payload.grn_date,
        "received_date": payload.received_date or payload.grn_date,
        "invoice_id": payload.invoice_id, "invoice_no": inv.get("invoice_no"),
        "po_id": inv.get("po_id"), "po_number": inv.get("po_number"),
        "client_name": inv.get("client_name"),
        "client_reference": payload.client_reference,
        "notes": payload.notes,
        "line_items": lines,
        "total_dispatched": total_disp, "total_received": total_recv,
        "total_accepted": total_acc, "total_rejected": total_rej,
        "by": u["email"], "created_at": now_iso(),
    }
    res = await db.grns.insert_one(doc)
    doc["_id"] = res.inserted_id

    grn_map = await _aggregate_grn_adjustments([str(inv["_id"])], db=db)
    grn_entry = grn_map.get(str(inv["_id"]), {})
    grn_adj = round(float(grn_entry.get("adjustment", 0)), 2)
    grand = float(inv.get("grand_total") or 0)
    net_amount = max(0.0, round(grand - grn_adj, 2))

    credit_days = int(inv.get("payment_terms_days") or 45)
    due_date = _due_iso(payload.grn_date, credit_days)
    await db.invoices.update_one(
        {"_id": inv["_id"]},
        {
            "$set": {
                "grn_date": payload.grn_date,
                "grn_no": grn_no,
                "grn_recorded": True,
                "grn_adjustment": grn_adj,
                "net_amount": net_amount,
                "due_date": due_date,
                "updated_at": now_iso(),
            }
        }
    )
    return stringify(doc)


@pos_router.get("/grns")
async def list_grns(request: Request, invoice_id: Optional[str] = None,
                    client: Optional[str] = None, limit: int = 300):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = get_db()
    q: dict = {}
    if invoice_id:
        q["invoice_id"] = str(invoice_id)
    if client:
        q["client_name"] = {"$regex": re.escape(str(client)), "$options": "i"}
    docs = await db.grns.find(q).sort("grn_date", -1).to_list(limit)
    return [stringify(d) for d in docs]


@pos_router.get("/grns/{gid}")
async def get_grn(gid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = get_db()
    doc = await db.grns.find_one({"_id": oid(gid)})
    if not doc:
        raise HTTPException(404, "GRN not found")
    return stringify(doc)


@pos_router.delete("/grns/{gid}")
async def delete_grn(gid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    from routes.invoice_packing import _aggregate_grn_adjustments, _due_iso

    grn_doc = await db.grns.find_one({"_id": oid(gid)})
    if not grn_doc:
        raise HTTPException(404, "GRN not found")
    invoice_id = grn_doc.get("invoice_id")
    r = await db.grns.delete_one({"_id": oid(gid)})
    if not r.deleted_count:
        raise HTTPException(404, "GRN not found")

    if invoice_id:
        remaining_grn = await db.grns.find_one({"invoice_id": invoice_id}, sort=[("grn_date", -1)])
        inv = await db.invoices.find_one({"_id": oid(invoice_id)})
        if inv:
            grn_map = await _aggregate_grn_adjustments([str(inv["_id"])], db=db)
            grn_entry = grn_map.get(str(inv["_id"]), {})
            grn_adj = round(float(grn_entry.get("adjustment", 0)), 2)
            grand = float(inv.get("grand_total") or 0)
            net_amount = max(0.0, round(grand - grn_adj, 2))

            if remaining_grn:
                credit_days = int(inv.get("payment_terms_days") or 45)
                due_date = _due_iso(remaining_grn["grn_date"], credit_days)
                await db.invoices.update_one(
                    {"_id": inv["_id"]},
                    {
                        "$set": {
                            "grn_date": remaining_grn["grn_date"],
                            "grn_no": remaining_grn.get("grn_no"),
                            "grn_recorded": True,
                            "grn_adjustment": grn_adj,
                            "net_amount": net_amount,
                            "due_date": due_date,
                            "updated_at": now_iso(),
                        }
                    }
                )
            else:
                await db.invoices.update_one(
                    {"_id": inv["_id"]},
                    {
                        "$set": {
                            "grn_date": None,
                            "grn_no": None,
                            "grn_recorded": False,
                            "grn_adjustment": 0.0,
                            "net_amount": grand,
                            "due_date": None,
                            "updated_at": now_iso(),
                        }
                    }
                )
    return {"ok": True}


# ── Client Payments ─────────────────────────────────────────────────────────

@pos_router.post("/payments")
async def create_payment(payload: PaymentIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    
    if payload.vendor_id:
        vendor = await db.vendors.find_one({"_id": oid(payload.vendor_id)})
        if not vendor:
            raise HTTPException(404, "Vendor not found")
        payment_no = await next_payment_no(db=db)
        doc = {
            "payment_no": payment_no,
            "payment_date": payload.payment_date,
            "amount": round(float(payload.amount), 2),
            "mode": payload.mode,
            "reference": payload.reference,
            "bank": payload.bank,
            "notes": payload.notes,
            "type": "vendor_payment",
            "vendor_id": str(vendor["_id"]),
            "vendor_name": vendor.get("name"),
            "vendor_po_id": payload.vendor_po_id or "",
            "by": u["email"],
            "created_at": now_iso(),
        }
        res = await db.payments.insert_one(doc)
        doc["_id"] = res.inserted_id
        await _log_activity("create_vendor_payment", "vendor_payments", f"Created Vendor Payment '{payment_no}' of ₹{payload.amount} for {vendor.get('name')}", u["email"], db=db)
        return stringify(doc)

    if not payload.invoice_ids:
        raise HTTPException(400, "At least one invoice required")
    invoices = await db.invoices.find({"_id": {"$in": [oid(i) for i in payload.invoice_ids]}}).to_list(50)
    if not invoices:
        raise HTTPException(404, "No invoices found")

    from routes.invoice_packing import _aggregate_payments_for_invoices, _aggregate_grn_adjustments

    invoices.sort(key=lambda d: (d.get("due_date") or "", d.get("invoice_date") or ""))
    inv_ids_str = [str(d["_id"]) for d in invoices]
    existing_paid = await _aggregate_payments_for_invoices(inv_ids_str, db=db)
    existing_grn = await _aggregate_grn_adjustments(inv_ids_str, db=db)
    remaining = float(payload.amount)
    allocations: dict[str, float] = {}
    for d in invoices:
        iid = str(d["_id"])
        grn_adj = float(existing_grn.get(iid, {}).get("adjustment", 0) if isinstance(existing_grn.get(iid), dict) else (existing_grn.get(iid) or 0))
        net = float(d.get("net_amount") if d.get("net_amount") is not None else max(0.0, float(d.get("grand_total") or 0) - grn_adj))
        outstanding = max(0.0, net - existing_paid.get(iid, 0))

        if outstanding <= 0:
            continue
        take = round(min(outstanding, remaining), 2)
        if take > 0:
            allocations[iid] = take
            remaining = round(remaining - take, 2)
        if remaining <= 0:
            break
    if not allocations:
        raise HTTPException(400, "Selected invoices are already fully paid")
    payment_no = await next_payment_no(db=db)
    doc = {
        "payment_no": payment_no,
        "payment_date": payload.payment_date,
        "amount": round(float(payload.amount), 2),
        "advance_amount": round(remaining, 2) if remaining > 0 else 0,
        "mode": payload.mode, "reference": payload.reference, "bank": payload.bank,
        "notes": payload.notes,
        "invoice_ids": list(allocations.keys()),
        "allocations": allocations,
        "client_name": invoices[0].get("client_name"),
        "by": u["email"], "created_at": now_iso(),
    }
    res = await db.payments.insert_one(doc)
    doc["_id"] = res.inserted_id
    return stringify(doc)


@pos_router.get("/payments")
async def list_payments(request: Request, invoice_id: Optional[str] = None,
                        client: Optional[str] = None, limit: int = 500):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    q: dict = {}
    if invoice_id:
        q["invoice_ids"] = str(invoice_id)
    if client:
        q["client_name"] = {"$regex": re.escape(str(client)), "$options": "i"}
    docs = await db.payments.find(q).sort("payment_date", -1).to_list(limit)
    return [stringify(d) for d in docs]


@pos_router.delete("/payments/{pid}")
async def delete_payment(pid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    r = await db.payments.delete_one({"_id": oid(pid)})
    if not r.deleted_count:
        raise HTTPException(404, "Payment not found")
    return {"ok": True}


# ── Clients / AR Summary & Ledger ───────────────────────────────────────────

@pos_router.get("/clients")
async def list_clients(request: Request):
    """Return unique clients seen on invoices + their aggregate AR snapshot."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    from routes.invoice_packing import _aggregate_payments_for_invoices, _aggregate_grn_adjustments, _decorate_invoice

    docs = await db.invoices.find({}, {"file_b64": 0}).to_list(5000)
    if not docs:
        return []
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids, db=db)
    grn_map = await _aggregate_grn_adjustments(inv_ids, db=db)
    decorated = [_decorate_invoice(d, pay_map, grn_map) for d in docs]
    summary: dict[str, dict] = {}
    for r in decorated:
        client = r.get("client_name") or "—"
        slot = summary.setdefault(client, {
            "client_name": client, "invoice_count": 0,
            "total_invoiced": 0.0, "total_received": 0.0,
            "outstanding": 0.0, "overdue_count": 0, "overdue_amount": 0.0,
        })
        slot["invoice_count"] += 1
        slot["total_invoiced"] += float(r.get("net_amount") or 0)
        slot["total_received"] += float(r.get("received_amount") or 0)
        slot["outstanding"] += float(r.get("outstanding") or 0)
        if r.get("status") == "overdue":
            slot["overdue_count"] += 1
            slot["overdue_amount"] += float(r.get("outstanding") or 0)
    out = list(summary.values())
    for s in out:
        for k in ("total_invoiced", "total_received", "outstanding", "overdue_amount"):
            s[k] = round(s[k], 2)
    out.sort(key=lambda s: -s["outstanding"])
    return out


@pos_router.get("/clients/{cid}/ledger")
async def client_ledger(cid: str, request: Request):
    """Client ledger and aging breakdown."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = get_db()
    return await _build_client_ledger(cid, db=db)


# ── Production Reports ──────────────────────────────────────────────────────

@pos_router.get("/reports/cost-variance")
async def report_cost_variance(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production", "sales")(u)
    db = get_db()
    import server

    styles = await db.styles.find({}).to_list(1000)
    style_costs = {}
    for s in styles:
        s_obj = stringify(s)
        c = server.compute_style_costing(s_obj) if hasattr(server, "compute_style_costing") else {}
        style_costs[s["code"]] = {
            "name": s.get("name"),
            "computed_cost": c.get("total_cost", 0),
            "selling_price": c.get("selling_price", 0)
        }
        
    po_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        po_query["po_date"] = date_q
        
    pos = await db.pos.find(po_query).to_list(1000)
    rows = []
    for p in pos:
        for li in p.get("line_items", []):
            code = li.get("style_code", "")
            sc = style_costs.get(code, {})
            cost = sc.get("computed_cost", 0)
            sell = li.get("unit_price", 0)
            variance = sell - cost
            margin_pct = (variance / cost * 100) if cost else 0
            rows.append({
                "po_number": p.get("po_number"), "client": p.get("client_name"),
                "style_code": code, "style_name": sc.get("name", "—"),
                "computed_cost": round(cost, 2), "po_unit_price": round(sell, 2),
                "variance": round(variance, 2), "margin_pct": round(margin_pct, 2),
                "quantity": li.get("quantity", 0),
                "total_variance": round(variance * li.get("quantity", 0), 2),
            })
    rows.sort(key=lambda r: r["margin_pct"])
    return rows


@pos_router.get("/reports/stage-cycle-time")
async def report_stage_cycle_time(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    
    job_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        job_query["created_at"] = date_q
        
    jobs = await db.production_jobs.find(job_query).to_list(5000)
    from collections import defaultdict
    durations = defaultdict(list)
    for j in jobs:
        hist = sorted(j.get("history", []), key=lambda h: h.get("at", ""))
        for i in range(1, len(hist)):
            prev, cur = hist[i - 1], hist[i]
            try:
                t_prev = datetime.fromisoformat(prev["at"])
                t_cur = datetime.fromisoformat(cur["at"])
                hours = (t_cur - t_prev).total_seconds() / 3600
                if hours >= 0:
                    durations[(prev["stage"], cur["stage"])].append(hours)
            except Exception:
                continue
    out = []
    for (frm, to), vals in durations.items():
        out.append({
            "from_stage": frm, "to_stage": to, "samples": len(vals),
            "avg_hours": round(sum(vals) / len(vals), 2),
            "min_hours": round(min(vals), 2), "max_hours": round(max(vals), 2),
        })
    out.sort(key=lambda r: r["avg_hours"], reverse=True)
    return out


@pos_router.get("/reports/defect-rate")
async def report_defect_rate(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    
    defect_query = {}
    job_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        defect_query["created_at"] = date_q
        job_query["created_at"] = date_q
        
    defects = await db.defects.find(defect_query).to_list(2000)
    jobs = await db.production_jobs.find(job_query).to_list(5000)
    from collections import defaultdict
    stage_qty = defaultdict(int)
    for j in jobs:
        for h in j.get("history", []):
            stage_qty[h.get("stage", "")] += j.get("quantity", 0)
    by_stage = defaultdict(lambda: {"defective": 0, "rework": 0, "rejected": 0, "cost": 0.0, "incidents": 0})
    by_type = defaultdict(lambda: {"defective": 0, "cost": 0.0, "incidents": 0})
    total_defective = 0
    total_cost = 0.0
    for d in defects:
        s = d.get("stage", "unknown")
        by_stage[s]["defective"] += d.get("defective_qty", 0)
        by_stage[s]["rework"] += d.get("rework_qty", 0)
        by_stage[s]["rejected"] += d.get("final_rejection_qty", 0)
        by_stage[s]["cost"] += d.get("cost", 0) or 0
        by_stage[s]["incidents"] += 1
        t = d.get("defect_type", "unknown")
        by_type[t]["defective"] += d.get("defective_qty", 0)
        by_type[t]["cost"] += d.get("cost", 0) or 0
        by_type[t]["incidents"] += 1
        total_defective += d.get("defective_qty", 0)
        total_cost += d.get("cost", 0) or 0
    stages_out = []
    for stage, v in by_stage.items():
        produced = stage_qty.get(stage, 0)
        rate = (v["defective"] / produced * 100) if produced else 0
        stages_out.append({
            "stage": stage, "produced_qty": produced,
            "defective_qty": v["defective"], "rework_qty": v["rework"],
            "rejected_qty": v["rejected"], "cost": round(v["cost"], 2),
            "incidents": v["incidents"], "defect_rate_pct": round(rate, 2),
        })
    stages_out.sort(key=lambda r: r["defect_rate_pct"], reverse=True)
    types_out = [{"type": k, **v, "cost": round(v["cost"], 2)} for k, v in by_type.items()]
    types_out.sort(key=lambda r: r["defective"], reverse=True)
    return {
        "by_stage": stages_out, "by_type": types_out,
        "totals": {"total_defective": total_defective, "total_cost": round(total_cost, 2), "total_incidents": len(defects)},
    }


@pos_router.get("/dashboard/overdue")
async def overdue_jobs(request: Request):
    """Returns active jobs whose stage_deadline has passed (excluding dispatched)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    jobs = await db.production_jobs.find({"stage": {"$ne": "dispatched"}}).to_list(5000)
    out = []
    durations = await _get_stage_durations(db=db)
    for j in jobs:
        dl = j.get("stage_deadline")
        if not dl:
            entered = j.get("stage_entered_at") or j.get("updated_at") or j.get("created_at")
            if entered:
                dl = _compute_deadline(entered, durations.get(j.get("stage", "procurement"), 24))
        hrs_over = _overdue_hours(dl)
        if hrs_over > 0:
            s = stringify(j)
            s["stage_deadline"] = dl
            s["overdue_hours"] = hrs_over
            out.append(s)
    out.sort(key=lambda r: -r["overdue_hours"])
    return out


@pos_router.get("/production/unmatched-styles")
async def unmatched_styles(request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    jobs = await db.production_jobs.find({
        "archived": {"$ne": True},
        "stage": {"$ne": "dispatched"},
        "$or": [
            {"style_match_status": "unmatched"},
            {"inventory_consume_error": {"$regex": "style", "$options": "i"}},
        ],
    }).to_list(2000)

    groups: dict[str, dict] = {}
    for j in jobs:
        code = j.get("style_code") or "(blank)"
        if code not in groups:
            groups[code] = {"style_code": code, "job_count": 0, "jobs": []}
        groups[code]["job_count"] += 1
        groups[code]["jobs"].append({
            "id": str(j["_id"]),
            "po_number": j.get("po_number"),
            "color": j.get("color"),
            "size": j.get("size"),
            "quantity": j.get("quantity"),
            "stage": j.get("stage"),
            "style_match_status": j.get("style_match_status"),
            "inventory_consume_error": j.get("inventory_consume_error"),
            "created_at": j.get("created_at"),
        })

    result = list(groups.values())
    result.sort(key=lambda g: -g["job_count"])
    return result


@pos_router.get("/reports/monthly-production")
async def report_monthly_production(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    
    job_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        job_query["created_at"] = date_q
        
    jobs = await db.production_jobs.find(job_query).to_list(10000)
    from collections import defaultdict
    monthly = defaultdict(lambda: {"started": 0, "dispatched": 0})
    for j in jobs:
        created = (j.get("created_at") or "")[:7]
        if created:
            monthly[created]["started"] += j.get("quantity", 0) or 0
        if j.get("stage") == "dispatched":
            disp_at = (j.get("updated_at") or "")[:7]
            if disp_at:
                monthly[disp_at]["dispatched"] += j.get("quantity", 0) or 0
    rows = [{"month": m, **v} for m, v in sorted(monthly.items())]
    if from_date or to_date:
        return rows
    return rows[-12:]


@pos_router.get("/reports/karigar-output")
async def report_karigar_output(request: Request,
                                from_date: Optional[str] = None, to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    if not from_date:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-01")
    if not to_date:
        to_date = datetime.now(timezone.utc).date().isoformat()
    payroll = await report_payroll(request, from_date=from_date, to_date=to_date)
    rows = [{
        "worker_id": r["worker_id"], "name": r["name"], "skill": r["skill"],
        "pairs": r["total_pairs"], "earnings": r["total_earning"], "bonus": r.get("total_bonus", 0),
    } for r in payroll["rows"]]
    rows.sort(key=lambda r: -r["pairs"])
    return rows


# ── Production Jobs Endpoints ───────────────────────────────────────────────

@pos_router.get("/production/jobs")
async def list_jobs(request: Request, include_archived: bool = False, source_type: Optional[str] = "b2b_client"):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    q: dict = {}
    if not include_archived:
        q = {"archived": {"$ne": True}}
    if source_type and source_type != "all":
        if source_type == "b2b_client":
            q["source_type"] = {"$in": ["b2b_client", None]}
        else:
            q["source_type"] = str(source_type)
    docs = await db.production_jobs.find(q).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@pos_router.get("/production/archive")
async def list_archive(request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    docs = await db.production_jobs.find({"archived": True}).sort("archived_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@pos_router.patch("/production/jobs/{jid}")
async def update_job(jid: str, payload: ProductionStageUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    
    from routes.materials import _auto_consume_inventory

    # Material requirement gate before moving OUT of procurement stage
    if job.get("stage") == "procurement" and payload.stage != "procurement":
        style = None
        if job.get("style_id") and ObjectId.is_valid(str(job["style_id"])):
            style = await db.styles.find_one({"_id": oid(job["style_id"])})
        if not style:
            style = await db.styles.find_one({"code": job.get("style_code")})
        if not style or not style.get("bom"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot move out of Procurement: Style '{job.get('style_code')}' has no BOM defined in Style Master. Please configure BOM in Styles Master first."
            )
        
        if not job.get("inventory_consumed"):
            try:
                consumed = await _auto_consume_inventory(job, u["email"], db=db)
                refreshed_job = await db.production_jobs.find_one({"_id": oid(jid)})
                if refreshed_job and refreshed_job.get("inventory_consume_error"):
                    err = refreshed_job.get("inventory_consume_error")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot move out of Procurement: Material requirement / inventory consumption failed — {err}"
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot move out of Procurement: Material requirement failed — {str(e)}"
                )

    # Parallel-completion gate before moving to lasting stage
    if payload.stage == "lasting":
        comp = job.get("components") or {}
        upper_done = bool(comp.get("upper_done"))
        bottom_done = bool(comp.get("bottom_done"))
        if not upper_done or not bottom_done:
            if not upper_done and not bottom_done:
                msg = "Cannot move to lasting: upper and bottom/insole not completed"
            elif not upper_done:
                msg = "Cannot move to lasting: upper not completed"
            else:
                msg = "Cannot move to lasting: bottom/insole not completed"
            raise HTTPException(status_code=400, detail=msg)

    update = {"updated_at": now_iso()}
    if job.get("stage") != payload.stage:
        try:
            curr_idx = PRODUCTION_STAGES.index(job.get("stage", "procurement"))
            target_idx = PRODUCTION_STAGES.index(payload.stage)
        except ValueError:
            curr_idx = 0
            target_idx = 0
            
        user_roles = u.get("roles", [u.get("role")] if u.get("role") else [])
        is_production_only = "production" in user_roles and not any(r in user_roles for r in ["admin", "manager"])
        if is_production_only and abs(target_idx - curr_idx) > 1 and not getattr(payload, "confirm_skip", False):
            raise HTTPException(
                status_code=400,
                detail="Skipping stages requires explicit confirmation. Please confirm stage skip."
            )
            
        durations = await _get_stage_durations(db=db)
        entered = now_iso()
        hours = float(durations.get(payload.stage, 24))
        update["stage"] = payload.stage
        update["stage_entered_at"] = entered
        update["stage_deadline"] = _compute_deadline(entered, hours) if payload.stage != "dispatched" else None
        
    if payload.completed_qty is not None:
        update["completed_qty"] = payload.completed_qty
        curr_stage = payload.stage if payload.stage else job.get("stage")
        asgn = (job.get("assignments") or {}).get(curr_stage) or {}
        if asgn.get("worker_id"):
            w_rate = asgn.get("rate_per_pair")
            if w_rate is None:
                w_doc = await db.workers.find_one({"_id": oid(asgn["worker_id"])})
                w_rate = float(w_doc.get("rate_per_pair", 0) or 0) if w_doc else 0.0
            else:
                w_rate = float(w_rate or 0)
            completed_by = {
                "worker_id": str(asgn["worker_id"]),
                "worker_name": asgn.get("worker_name", ""),
                "rate_per_pair": w_rate,
                "at": now_iso(),
            }
            update["completed_by"] = completed_by
            update[f"assignments.{curr_stage}.completed_by"] = completed_by
            update[f"assignments.{curr_stage}.completed_qty"] = payload.completed_qty
            update[f"assignments.{curr_stage}.completed_at"] = now_iso()
    if payload.rejected_qty is not None:
        update["rejected_qty"] = payload.rejected_qty
    if payload.qc_pass is not None:
        update["qc_pass"] = payload.qc_pass
    history_entry = {
        "stage": payload.stage, "at": now_iso(), "by": u["email"],
        "notes": payload.notes or "",
        "qc_pass": payload.qc_pass, "rejected_qty": payload.rejected_qty,
        "completed_qty": payload.completed_qty,
        "completed_by": update.get("completed_by"),
    }
    mongo_update: dict = {"$set": update, "$push": {"history": history_entry}}
    if job.get("stage") != payload.stage:
        mongo_update["$unset"] = {"ready_for_pickup": ""}
    await db.production_jobs.update_one({"_id": oid(jid)}, mongo_update)
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@pos_router.patch("/production/jobs/{jid}/components")
async def update_job_components(jid: str, payload: ComponentUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    comps = job.get("components") or {"upper_done": False, "bottom_done": False, "sole_done": False}
    for k in ("upper_done", "bottom_done", "sole_done"):
        v = getattr(payload, k)
        if v is not None:
            comps[k] = bool(v)
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": {"components": comps, "updated_at": now_iso()},
         "$push": {"history": {"event": "component_update", "components": comps,
                               "at": now_iso(), "by": u["email"], "notes": payload.notes or ""}}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@pos_router.patch("/production/jobs/{jid}/assignment")
async def update_job_assignment(jid: str, payload: AssignmentUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    assignments = job.get("assignments") or {}
    prev_asgn = assignments.get(payload.role) or {}
    if payload.worker_id:
        worker = await db.workers.find_one({"_id": oid(payload.worker_id)})
        if not worker:
            raise HTTPException(404, "Worker not found")
        rate = payload.rate_per_pair if payload.rate_per_pair is not None else worker.get("rate_per_pair", 0)
        new_asgn = {
            "worker_id": payload.worker_id,
            "worker_name": worker.get("name", ""),
            "rate_per_pair": float(rate or 0),
        }
        if prev_asgn.get("completed_by"):
            new_asgn["completed_by"] = prev_asgn["completed_by"]
        if prev_asgn.get("completed_qty") is not None:
            new_asgn["completed_qty"] = prev_asgn["completed_qty"]
        if prev_asgn.get("completed_at"):
            new_asgn["completed_at"] = prev_asgn["completed_at"]
        assignments[payload.role] = new_asgn
    else:
        assignments.pop(payload.role, None)
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": {"assignments": assignments, "updated_at": now_iso()},
         "$push": {"history": {"event": "assignment_update", "role": payload.role,
                               "worker_id": payload.worker_id,
                               "worker_name": assignments.get(payload.role, {}).get("worker_name", ""),
                               "rate_per_pair": assignments.get(payload.role, {}).get("rate_per_pair"),
                               "at": now_iso(), "by": u["email"]}}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@pos_router.patch("/production/jobs/{jid}/quantity")
async def update_job_quantity(jid: str, payload: QuantityUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    update = {"updated_at": now_iso()}
    old_qty = job.get("quantity", 0)
    if payload.quantity is not None:
        update["quantity"] = int(payload.quantity)
    if payload.completed_qty is not None:
        update["completed_qty"] = int(payload.completed_qty)
        curr_stage = job.get("stage")
        asgn = (job.get("assignments") or {}).get(curr_stage) or {}
        if asgn.get("worker_id"):
            w_rate = asgn.get("rate_per_pair")
            if w_rate is None:
                w_doc = await db.workers.find_one({"_id": oid(asgn["worker_id"])})
                w_rate = float(w_doc.get("rate_per_pair", 0) or 0) if w_doc else 0.0
            else:
                w_rate = float(w_rate or 0)
            completed_by = {
                "worker_id": str(asgn["worker_id"]),
                "worker_name": asgn.get("worker_name", ""),
                "rate_per_pair": w_rate,
                "at": now_iso(),
            }
            update["completed_by"] = completed_by
            update[f"assignments.{curr_stage}.completed_by"] = completed_by
            update[f"assignments.{curr_stage}.completed_qty"] = int(payload.completed_qty)
            update[f"assignments.{curr_stage}.completed_at"] = now_iso()
    if payload.rejected_qty is not None:
        update["rejected_qty"] = int(payload.rejected_qty)
    history_entry = {
        "event": "quantity_update", "old_quantity": old_qty,
        "new_quantity": update.get("quantity", old_qty),
        "completed_qty": update.get("completed_qty"),
        "rejected_qty": update.get("rejected_qty"),
        "completed_by": update.get("completed_by"),
        "reason": payload.reason or "",
        "at": now_iso(), "by": u["email"],
    }
    await db.production_jobs.update_one(
        {"_id": oid(jid)}, {"$set": update, "$push": {"history": history_entry}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@pos_router.post("/production/bulk-assign")
async def bulk_assign(payload: BulkAssign, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    if not payload.job_ids:
        raise HTTPException(400, "job_ids required")
    worker_name = ""
    rate = float(payload.rate_per_pair or 0)
    if payload.worker_id:
        w = await db.workers.find_one({"_id": oid(payload.worker_id)})
        if not w:
            raise HTTPException(404, "Worker not found")
        worker_name = w.get("name", "")
        if payload.rate_per_pair is None:
            rate = float(w.get("rate_per_pair", 0) or 0)

    obj_ids = []
    for jid in payload.job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    affected = 0
    for j in jobs:
        assignments = j.get("assignments") or {}
        prev_asgn = assignments.get(payload.role) or {}
        if payload.worker_id:
            new_asgn = {
                "worker_id": payload.worker_id,
                "worker_name": worker_name,
                "rate_per_pair": rate,
            }
            if prev_asgn.get("completed_by"):
                new_asgn["completed_by"] = prev_asgn["completed_by"]
            if prev_asgn.get("completed_qty") is not None:
                new_asgn["completed_qty"] = prev_asgn["completed_qty"]
            if prev_asgn.get("completed_at"):
                new_asgn["completed_at"] = prev_asgn["completed_at"]
            assignments[payload.role] = new_asgn
        else:
            assignments.pop(payload.role, None)
        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {"$set": {"assignments": assignments, "updated_at": now_iso()},
             "$push": {"history": {"event": "bulk_assignment", "role": payload.role,
                                   "worker_id": payload.worker_id, "worker_name": worker_name,
                                   "rate_per_pair": rate,
                                   "at": now_iso(), "by": u["email"]}}}
        )
        affected += 1
    return {"affected": affected, "role": payload.role, "worker_id": payload.worker_id, "worker_name": worker_name, "rate_per_pair": rate}


def extract_role_completions(j: dict, role: str, worker_map: dict) -> list[dict]:
    """
    Extracts all completion slices for a specific role on a job `j`.
    Attributes each slice of completed work to the worker who actually did it at that moment.
    If multiple completions/reassignments occurred, splits earnings proportionally across historical assignees.
    Falls back to current assignment attribution for legacy records without completed_by data.
    """
    hist = j.get("history") or []
    role_milestones = []
    for h in hist:
        if not isinstance(h, dict):
            continue
        h_role = h.get("role") or (h.get("stage") if h.get("stage") not in ("dispatched", "completed", "procurement") else None)
        if h_role != role:
            continue

        c_qty = h.get("completed_qty")
        if c_qty is None or int(c_qty) <= 0:
            continue

        c_by = h.get("completed_by")
        if not c_by or not isinstance(c_by, dict) or not c_by.get("worker_id"):
            if h.get("worker_id"):
                c_by = {
                    "worker_id": str(h["worker_id"]),
                    "worker_name": h.get("worker_name", ""),
                    "rate_per_pair": h.get("rate_per_pair"),
                    "at": h.get("at", ""),
                }

        if c_by and isinstance(c_by, dict) and c_by.get("worker_id"):
            role_milestones.append({
                "qty": int(c_qty),
                "completed_by": c_by,
                "at": h.get("at") or "",
            })

    # Sort milestones chronologically
    role_milestones.sort(key=lambda m: (m["at"], m["qty"]))

    completions = []
    prev_qty = 0
    if role_milestones:
        for m in role_milestones:
            q = m["qty"]
            delta = q - prev_qty
            if delta > 0:
                c_by = m["completed_by"]
                wid = str(c_by["worker_id"])
                if c_by.get("rate_per_pair") is not None:
                    rate = float(c_by["rate_per_pair"] or 0)
                else:
                    rate = float(worker_map.get(wid, {}).get("rate_per_pair", 0) or 0)
                completions.append({
                    "worker_id": wid,
                    "pairs": delta,
                    "rate": rate,
                    "at": m["at"],
                })
                prev_qty = q

        # Check if total completed_qty recorded on assignments/job exceeds the milestones
        a = (j.get("assignments") or {}).get(role) or {}
        if isinstance(a, str):
            a = {"worker_id": a}
        elif not isinstance(a, dict):
            a = {}
        rfp = j.get("ready_for_pickup") or {}

        target_qty = prev_qty
        if a.get("completed_qty") is not None and int(a.get("completed_qty", 0) or 0) > prev_qty:
            target_qty = int(a["completed_qty"])
        elif rfp.get("role") == role and int(rfp.get("completed_qty", 0) or 0) > prev_qty:
            target_qty = int(rfp["completed_qty"])
        elif j.get("stage") == role and int(j.get("completed_qty", 0) or 0) > prev_qty:
            target_qty = int(j["completed_qty"])
        elif j.get("stage") == "dispatched" and int(j.get("quantity", 0) or 0) > prev_qty:
            target_qty = int(j["quantity"])

        if target_qty > prev_qty:
            delta = target_qty - prev_qty
            curr_c_by = a.get("completed_by")
            if not curr_c_by and rfp.get("role") == role and rfp.get("completed_by"):
                curr_c_by = rfp.get("completed_by")
            if not curr_c_by and j.get("stage") == role and isinstance(j.get("completed_by"), dict):
                curr_c_by = j.get("completed_by")

            wid = str(curr_c_by.get("worker_id")) if (curr_c_by and curr_c_by.get("worker_id")) else (str(a.get("worker_id")) if a.get("worker_id") else None)
            if wid:
                if curr_c_by and curr_c_by.get("rate_per_pair") is not None:
                    rate = float(curr_c_by["rate_per_pair"] or 0)
                elif a.get("rate_per_pair") is not None:
                    rate = float(a.get("rate_per_pair") or 0)
                else:
                    rate = float(worker_map.get(wid, {}).get("rate_per_pair", 0) or 0)
                at_val = (curr_c_by.get("at") if curr_c_by else (j.get("updated_at") or j.get("created_at") or ""))
                completions.append({
                    "worker_id": wid,
                    "pairs": delta,
                    "rate": rate,
                    "at": at_val,
                })
        return completions

    # Fallback when no history completion milestones exist (e.g. single snapshot or legacy jobs)
    a = (j.get("assignments") or {}).get(role) or {}
    if isinstance(a, str):
        a = {"worker_id": a}
    elif not isinstance(a, dict):
        a = {}
    rfp = j.get("ready_for_pickup") or {}
    c_by = a.get("completed_by")
    if not c_by and rfp.get("role") == role and rfp.get("completed_by"):
        c_by = rfp.get("completed_by")
    if not c_by and j.get("stage") == role and isinstance(j.get("completed_by"), dict):
        c_by = j.get("completed_by")

    wid = str(c_by.get("worker_id")) if (c_by and c_by.get("worker_id")) else (str(a.get("worker_id")) if a.get("worker_id") else None)
    if not wid:
        return []

    role_comp = a.get("completed_qty")
    if role_comp is None or role_comp == 0:
        if rfp.get("worker_id") == wid and rfp.get("role") == role:
            role_comp = rfp.get("completed_qty", 0) or 0
        elif j.get("stage") == role:
            role_comp = j.get("completed_qty", 0) or 0
        elif j.get("stage") == "dispatched":
            role_comp = j.get("quantity", 0)
        else:
            role_comp = j.get("completed_qty", 0) or 0

    if not role_comp or int(role_comp) <= 0:
        return []

    if c_by and c_by.get("rate_per_pair") is not None:
        rate = float(c_by.get("rate_per_pair") or 0)
    elif a.get("rate_per_pair") is not None:
        rate = float(a.get("rate_per_pair") or 0)
    else:
        rate = float(worker_map.get(wid, {}).get("rate_per_pair", 0) or 0)

    at_val = (c_by.get("at") if c_by else (j.get("updated_at") or j.get("created_at") or ""))
    return [{
        "worker_id": wid,
        "pairs": int(role_comp),
        "rate": rate,
        "at": at_val,
    }]


# ── Payroll & Wage Slip Endpoints ───────────────────────────────────────────

async def compute_payroll(db=None, from_date: Optional[str] = None, to_date: Optional[str] = None) -> dict:
    db = db if db is not None else get_db()
    workers = await db.workers.find({}).to_list(500)
    worker_map = {str(w["_id"]): w for w in workers}

    q = {}
    if from_date:
        q["updated_at"] = {"$gte": from_date}
    if to_date:
        q.setdefault("updated_at", {})
        q["updated_at"]["$lte"] = to_date + "T23:59:59Z"
    jobs = await db.production_jobs.find(q).to_list(5000)

    styles = await db.styles.find({}).to_list(1000)
    styles_cache = {str(s.get("code")).strip().upper(): stringify(s) for s in styles if s.get("code")}

    earnings = {}
    raw_jobs_by_worker = {}
    for j in jobs:
        roles_to_check = set()
        for r in (j.get("assignments") or {}).keys():
            roles_to_check.add(r)
        for h in j.get("history") or []:
            if h.get("role"):
                roles_to_check.add(h["role"])
            if h.get("stage") and h.get("stage") not in ("dispatched", "completed", "procurement"):
                roles_to_check.add(h["stage"])
        if j.get("stage") and j.get("stage") not in ("dispatched", "completed", "procurement"):
            roles_to_check.add(j["stage"])

        for role in roles_to_check:
            slices = extract_role_completions(j, role, worker_map)
            for s in slices:
                wid = s["worker_id"]
                w = worker_map.get(wid)
                if not w:
                    continue
                role_comp = s["pairs"]
                rate = s["rate"]
                earn = rate * role_comp
                if wid not in earnings:
                    earnings[wid] = {
                        "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
                        "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
                        "bonus_pct": float(w.get("bonus_pct", 0) or 0),
                        "target_cycle_days": float(w.get("target_cycle_days", 0) or 0),
                        "total_pairs": 0, "total_earning": 0.0,
                        "total_bonus": 0.0,
                        "advances_taken": 0.0, "advances_open": 0.0,
                        "payments_paid": 0.0,
                        "net_payable": 0.0,
                        "by_role": {}, "jobs": [],
                    }
                    raw_jobs_by_worker[wid] = []
                earnings[wid]["total_pairs"] += role_comp
                earnings[wid]["total_earning"] += earn
                earnings[wid]["by_role"][role] = earnings[wid]["by_role"].get(role, 0) + role_comp

                bonus_amt = 0
                bp = float(w.get("bonus_pct", 0) or 0)
                td = float(w.get("target_cycle_days", 0) or 0)
                if bp > 0 and td > 0:
                    hist = j.get("history") or []
                    assign_at = None
                    done_at = None
                    for h in hist:
                        if h.get("event") in ("assignment_update", "bulk_assignment") and h.get("role") == role and h.get("worker_id") == wid:
                            assign_at = h.get("at")
                        if h.get("stage") == "dispatched":
                            done_at = h.get("at")
                    if not done_at and s.get("at"):
                        done_at = s.get("at")
                    if assign_at and done_at:
                        try:
                            delta_days = (datetime.fromisoformat(done_at) - datetime.fromisoformat(assign_at)).total_seconds() / 86400
                            if 0 <= delta_days <= td:
                                bonus_amt = round(earn * bp / 100, 2)
                                earnings[wid]["total_bonus"] += bonus_amt
                        except Exception:
                            pass

                raw_jobs_by_worker[wid].append({
                    "job_id": str(j["_id"]),
                    "po_number": j.get("po_number"),
                    "style_code": j.get("style_code"),
                    "color": j.get("color"),
                    "size": j.get("size"),
                    "role": role,
                    "pairs": role_comp,
                    "rate": rate,
                    "earning": round(earn, 2),
                    "bonus": bonus_amt,
                })

    for wid, e in earnings.items():
        raw_list = raw_jobs_by_worker.get(wid, [])
        grouped_cards = {}
        for item in raw_list:
            po_num = str(item.get("po_number") or "").strip()
            style_code = str(item.get("style_code") or "").strip()
            color = str(item.get("color") or "").strip()
            role = str(item.get("role") or "").strip()
            if po_num and po_num != "—":
                ckey = f"{po_num}_{style_code}_{color}_{role}"
            else:
                ckey = f"single_{item['job_id']}_{role}"

            if ckey not in grouped_cards:
                st_info = styles_cache.get(style_code.upper(), {})
                img = st_info.get("image_url") or st_info.get("image_thumbnail_url") or st_info.get("photo_link") or ""
                grouped_cards[ckey] = {
                    "id": item["job_id"],
                    "job_id": item["job_id"],
                    "po_number": po_num or "—",
                    "style_code": style_code,
                    "color": color,
                    "role": role,
                    "stage": "dispatched" if item.get("stage") == "dispatched" else role,
                    "rate_per_pair": item["rate"],
                    "rate": item["rate"],
                    "total_quantity": 0,
                    "quantity": 0,
                    "completed_qty": 0,
                    "pairs": 0,
                    "total_earning": 0.0,
                    "earning": 0.0,
                    "bonus": 0.0,
                    "image_url": img,
                    "image_thumbnail_url": img,
                    "article_name": st_info.get("name", ""),
                    "is_completed": True,
                    "sizes": [],
                    "size_map": {},
                }
            gc = grouped_cards[ckey]
            gc["total_quantity"] += item["pairs"]
            gc["quantity"] += item["pairs"]
            gc["completed_qty"] += item["pairs"]
            gc["pairs"] += item["pairs"]
            gc["total_earning"] = round(gc["total_earning"] + item["earning"], 2)
            gc["earning"] = gc["total_earning"]
            gc["bonus"] = round(gc["bonus"] + item["bonus"], 2)
            
            sz_str = str(item.get("size", "—"))
            if sz_str not in gc["size_map"]:
                gc["size_map"][sz_str] = {
                    "job_id": item["job_id"],
                    "size": sz_str,
                    "ordered_qty": item["pairs"],
                    "completed_qty": item["pairs"],
                    "pairs": item["pairs"],
                }
            else:
                gc["size_map"][sz_str]["ordered_qty"] += item["pairs"]
                gc["size_map"][sz_str]["completed_qty"] += item["pairs"]
                gc["size_map"][sz_str]["pairs"] += item["pairs"]

        for gc in grouped_cards.values():
            def parse_sz(s_item):
                s = str(s_item.get("size", 999))
                return float(s) if s.replace('.', '', 1).isdigit() else 999
            gc["sizes"] = sorted(list(gc.pop("size_map").values()), key=parse_sz)

        e["jobs"] = list(grouped_cards.values())

    adv_q = {}
    if from_date:
        adv_q["date"] = {"$gte": from_date}
    if to_date:
        adv_q.setdefault("date", {})
        adv_q["date"]["$lte"] = to_date
    advances = await db.advances.find(adv_q).to_list(5000)
    adv_by_worker = {}
    for a in advances:
        wid = a.get("worker_id")
        if not wid:
            continue
        adv_by_worker.setdefault(wid, []).append(a)

    for wid, e in earnings.items():
        for a in adv_by_worker.get(wid, []):
            amt = float(a.get("amount", 0) or 0)
            ttype = a.get("txn_type") or "advance"
            if ttype == "advance":
                e["advances_taken"] += amt
                if not a.get("settled"):
                    e["advances_open"] += amt
            elif ttype == "payment":
                e["payments_paid"] += amt
            elif ttype == "bonus":
                e["total_bonus"] += amt
        gross = e["total_earning"] + e["total_bonus"]
        e["net_payable"] = round(gross - e["advances_open"] - e["payments_paid"], 2)
        e["total_earning"] = round(e["total_earning"], 2)
        e["total_bonus"] = round(e["total_bonus"], 2)
        e["advances_taken"] = round(e["advances_taken"], 2)
        e["advances_open"] = round(e["advances_open"], 2)
        e["payments_paid"] = round(e["payments_paid"], 2)

    for wid, advs in adv_by_worker.items():
        if wid in earnings:
            continue
        w = worker_map.get(wid)
        if not w:
            continue
        taken = sum(float(a.get("amount", 0) or 0) for a in advs if (a.get("txn_type") or "advance") == "advance")
        open_amt = sum(float(a.get("amount", 0) or 0) for a in advs if (a.get("txn_type") or "advance") == "advance" and not a.get("settled"))
        paid = sum(float(a.get("amount", 0) or 0) for a in advs if a.get("txn_type") == "payment")
        bon = sum(float(a.get("amount", 0) or 0) for a in advs if a.get("txn_type") == "bonus")
        earnings[wid] = {
            "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
            "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
            "bonus_pct": float(w.get("bonus_pct", 0) or 0),
            "target_cycle_days": float(w.get("target_cycle_days", 0) or 0),
            "total_pairs": 0, "total_earning": 0.0, "total_bonus": round(bon, 2),
            "advances_taken": round(taken, 2), "advances_open": round(open_amt, 2),
            "payments_paid": round(paid, 2),
            "net_payable": round(bon - open_amt - paid, 2),
            "by_role": {}, "jobs": [],
        }

    # Query wage payment records for actual disbursements against this period
    wp_q: dict = {}
    if from_date:
        wp_q["period_from"] = from_date
    if to_date:
        wp_q["period_to"] = to_date

    wage_payments_list = []
    if hasattr(db, "wage_payments") and db.wage_payments is not None:
        try:
            cursor = db.wage_payments.find(wp_q if (from_date or to_date) else {})
            if hasattr(cursor, "to_list"):
                res = cursor.to_list(5000)
                if hasattr(res, "__await__"):
                    wage_payments_list = await res
                elif isinstance(res, list):
                    wage_payments_list = res
        except Exception:
            wage_payments_list = []

    wp_by_worker = {}
    for wp in wage_payments_list:
        wid_key = str(wp.get("worker_id"))
        wp_by_worker.setdefault(wid_key, []).append(wp)

    for wid, wps in wp_by_worker.items():
        if wid in earnings:
            continue
        w = worker_map.get(wid)
        if not w:
            continue
        earnings[wid] = {
            "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
            "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
            "bonus_pct": float(w.get("bonus_pct", 0) or 0),
            "target_cycle_days": float(w.get("target_cycle_days", 0) or 0),
            "total_pairs": 0, "total_earning": 0.0, "total_bonus": 0.0,
            "advances_taken": 0.0, "advances_open": 0.0,
            "payments_paid": 0.0,
            "net_payable": 0.0,
            "by_role": {}, "jobs": [],
        }

    rows = list(earnings.values())

    for r in rows:
        wid = str(r["worker_id"])
        w_payments = wp_by_worker.get(wid, [])
        disbursed = round(sum(float(p.get("amount") or 0.0) for p in w_payments), 2)
        net_payable = float(r.get("net_payable") or 0.0)
        remaining_balance = round(net_payable - disbursed, 2)

        override_reasons = [str(p["override_reason"]).strip() for p in w_payments if p.get("override_reason")]

        r["computed_owed"] = net_payable
        r["actual_paid"] = disbursed
        r["disbursed_amount"] = disbursed
        r["remaining_owed"] = remaining_balance
        r["balance_owed"] = remaining_balance
        r["is_overpaid"] = disbursed > net_payable + 0.01
        r["override_reasons"] = override_reasons
        r["override_reason"] = ", ".join(override_reasons) if override_reasons else None
        r["payment_status"] = (
            "overpaid" if disbursed > net_payable + 0.01
            else "paid" if (disbursed >= net_payable and net_payable > 0)
            else "partially_paid" if disbursed > 0
            else "unpaid"
        )
        r["wage_payments"] = [stringify(p) for p in w_payments]

    rows.sort(key=lambda r: r["net_payable"], reverse=True)
    grand = round(sum(r["total_earning"] for r in rows), 2)
    grand_bonus = round(sum(r["total_bonus"] for r in rows), 2)
    grand_advances = round(sum(r["advances_open"] for r in rows), 2)
    grand_payments = round(sum(r["payments_paid"] for r in rows), 2)
    grand_disbursed = round(sum(r.get("disbursed_amount", 0.0) for r in rows), 2)
    grand_balance_owed = round(sum(r.get("balance_owed", 0.0) for r in rows), 2)

    return {
        "rows": rows,
        "grand_total": grand,
        "grand_bonus": grand_bonus,
        "grand_advances_open": grand_advances,
        "grand_payments": grand_payments,
        "grand_net_payable": round(grand + grand_bonus - grand_advances - grand_payments, 2),
        "grand_disbursed": grand_disbursed,
        "grand_actual_paid": grand_disbursed,
        "grand_balance_owed": grand_balance_owed,
        "grand_remaining_owed": grand_balance_owed,
        "worker_count": len(rows),
        "from_date": from_date, "to_date": to_date,
    }


@pos_router.get("/reports/payroll")
async def report_payroll(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    return await compute_payroll(from_date=from_date, to_date=to_date)


@pos_router.get("/reports/payroll.pdf")
async def report_payroll_pdf(request: Request,
                             from_date: Optional[str] = None,
                             to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    data = await report_payroll(request, from_date, to_date)
    from pdf_payroll import build_payroll_summary
    pdf_bytes = build_payroll_summary(data)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="payroll-{from_date or ""}-{to_date or ""}.pdf"'},
    )


@pos_router.get("/reports/payroll/{worker_id}.pdf")
async def report_wage_slip_pdf(worker_id: str, request: Request,
                               from_date: Optional[str] = None,
                               to_date: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    data = await report_payroll(request, from_date, to_date)
    row = next((r for r in data["rows"] if r["worker_id"] == worker_id), None)
    if not row:
        raise HTTPException(404, "No payroll data for this karigar in the period")
    advances = await db.advances.find({"worker_id": worker_id}).sort("date", -1).to_list(500)
    advances_list = [stringify(a) for a in advances]
    from pdf_payroll import build_wage_slip
    pdf_bytes = build_wage_slip(row, advances_list, data["from_date"], data["to_date"])
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="wage-slip-{row["name"].replace(" ", "_")}.pdf"'},
    )


# ── Production Cards ────────────────────────────────────────────────────────

@pos_router.post("/production/card.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def production_card_pdf(payload: dict, request: Request, variant: str = Query("single")):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(500)
    if not jobs:
        raise HTTPException(404, "Jobs not found")
    j0 = jobs[0]
    sizes = []
    seen = set()
    for j in sorted(jobs, key=lambda x: (float(x.get("size", 999)) if str(x.get("size", "")).replace('.', '', 1).isdigit() else 999)):
        sz = str(j.get("size", "—"))
        if sz in seen:
            continue
        seen.add(sz)
        sizes.append({"size": sz, "quantity": j.get("quantity", 0)})
    total_qty = sum(j.get("quantity", 0) for j in jobs)
    comp = {
        "upper_done": all((j.get("components") or {}).get("upper_done") for j in jobs),
        "bottom_done": all((j.get("components") or {}).get("bottom_done") for j in jobs),
        "sole_done": all((j.get("components") or {}).get("sole_done") for j in jobs),
    }
    group = {
        "po_number": j0.get("po_number", ""),
        "client_name": j0.get("client_name", ""),
        "style_code": j0.get("style_code", ""),
        "color": j0.get("color", ""),
        "description": j0.get("description", ""),
        "delivery_date": j0.get("delivery_date", ""),
        "sizes": sizes,
        "total_qty": total_qty,
        "components": comp,
        "assignments": j0.get("assignments") or {},
    }
    style = await db.styles.find_one({"code": j0.get("style_code")})
    style_d = stringify(style) if style else None
    is_dual = variant == "dual" or payload.get("variant") == "dual" or payload.get("dual") is True
    if is_dual:
        pdf_bytes = build_production_card_dual_a4(group, style_d)
    else:
        pdf_bytes = build_production_card(group, style_d)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="card-{group["po_number"]}-{group["style_code"]}-{group["color"]}.pdf"'},
    )


# ── Defects Tracking ────────────────────────────────────────────────────────

@pos_router.get("/defects")
async def list_defects(request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    docs = await db.defects.find({}).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@pos_router.post("/defects")
async def create_defect(payload: DefectIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    doc = payload.model_dump()
    doc["reported_by"] = u["email"]
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.defects.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc


@pos_router.patch("/defects/{did}")
async def update_defect(did: str, payload: DefectIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db()
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    if update["status"] == "closed":
        update["closed_at"] = now_iso()
    await db.defects.update_one({"_id": oid(did)}, {"$set": update})
    return stringify(await db.defects.find_one({"_id": oid(did)}))


@pos_router.delete("/defects/{did}")
async def delete_defect(did: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    await db.defects.delete_one({"_id": oid(did)})
    return {"ok": True}
