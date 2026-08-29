"""Invoicing, Packing Lists, Carton Labels & Unified Dispatch Router."""

import io
import re
import zipfile
import base64
import logging
from io import BytesIO
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import StreamingResponse, JSONResponse
from bson import ObjectId
from pymongo import ReturnDocument
from pydantic import BaseModel, Field

from auth import require_roles
from rate_limiter import pdf_rate_limiter, upload_rate_limiter
from pdf_docs import generate_dispatch_challan_pdf, build_invoice
from packing_list import (
    build_default_packing_list,
    build_from_template,
    build_dispatch_packing_list,
    build_carton_list_xlsx,
    build_packing_list_pdf,
    VENDOR,
    DEFAULT_SIZES,
)
from pdf_carton_label import build_carton_labels
from models.invoice_packing import (
    InvoiceGenerate,
    DispatchCreate,
    PackingListGenerate,
    MergedPackingListGenerate,
    PackingTemplateIn,
)

log = logging.getLogger("erp")

invoice_packing_router = APIRouter(prefix="/api", tags=["Invoice & Packing List"])

DEFAULT_CREDIT_DAYS = 45
DEFAULT_STAGE_HOURS = {
    "procurement": 24, "cutting": 24, "folding": 8, "attachment": 8,
    "stitching": 48, "lasting": 24, "sole_pasting": 12, "finishing": 12,
    "qc_pack": 12, "dispatched": 0,
}


# ── Local helpers ──────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(val):
    if isinstance(val, ObjectId):
        return val
    try:
        return ObjectId(str(val))
    except Exception:
        raise HTTPException(400, f"Invalid ObjectId: {val}")


def stringify(doc):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
        elif isinstance(v, dict):
            d[k] = stringify(v)
        elif isinstance(v, list):
            d[k] = [stringify(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
    return d


async def _get_user(request: Request) -> dict:
    getter = getattr(request.app.state, "get_current_user", None)
    if getter:
        return await getter(request)
    from server import get_current_user
    return await get_current_user(request)


async def log_activity(action: str, category: str, details: str, user_email: str, db=None) -> None:
    if db is None:
        db = getattr(__import__("server"), "db")
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "user": user_email,
            "created_at": now_iso(),
        })
    except Exception as e:
        log.warning(f"Failed to log activity {action}: {e}")


async def _get_stage_durations(db=None) -> Dict[str, float]:
    if db is None:
        db = getattr(__import__("server"), "db")
    doc = await db.settings.find_one({"_id": "stage_durations"})
    out = dict(DEFAULT_STAGE_HOURS)
    if doc and isinstance(doc.get("hours"), dict):
        out.update({k: float(v) for k, v in doc["hours"].items() if isinstance(v, (int, float))})
    return out


def _compute_deadline(entered_iso: str, hours: float) -> str:
    try:
        s = entered_iso.replace("Z", "+00:00") if entered_iso.endswith("Z") else entered_iso
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except Exception:
        t = datetime.now(timezone.utc)
    return (t + timedelta(hours=float(hours or 0))).isoformat()


# ── Domain Models ─────────────────────────────────────────────────────────
class CartonIn(BaseModel):
    job_id: str
    size: str
    qty: int


class EanCodeSimple(BaseModel):
    size: str
    ean_code: str


class CartonRowSimple(BaseModel):
    size: str
    qty: int


class QcPackConfirmIn(BaseModel):
    job_ids: List[str]
    eans: List[EanCodeSimple]
    cartons: List[CartonRowSimple]


class EanCodeIn(BaseModel):
    style_id: str
    color: str
    size: str
    ean_code: str


# ── Invoicing Sequence and AR Helpers ─────────────────────────────────────
async def _get_max_invoice_seq(fy_label: str, db=None) -> int:
    """Find the highest sequence number across db.invoices and db.dispatch_records for given FY."""
    if db is None:
        db = getattr(__import__("server"), "db")
    prefix = f"SSK{fy_label}-"
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    max_seq = 0

    # 1. Scan db.invoices
    inv_docs = await db.invoices.find(
        {"invoice_no": {"$regex": rf"^{re.escape(prefix)}"}},
        {"invoice_no": 1}
    ).to_list(10000)
    for doc in inv_docs:
        ino = str(doc.get("invoice_no") or "")
        m = pattern.match(ino)
        if m:
            try:
                max_seq = max(max_seq, int(m.group(1)))
            except ValueError:
                pass

    # 2. Scan db.dispatch_records
    dr_docs = await db.dispatch_records.find(
        {"invoice_no": {"$regex": rf"^{re.escape(prefix)}"}},
        {"invoice_no": 1}
    ).to_list(10000)
    for doc in dr_docs:
        ino = str(doc.get("invoice_no") or "")
        m = pattern.match(ino)
        if m:
            try:
                max_seq = max(max_seq, int(m.group(1)))
            except ValueError:
                pass

    return max_seq


async def next_invoice_no(db=None) -> str:
    """Generate strictly-serial SSK<FY>-XXX format (e.g. SSK26-27-020)."""
    if db is None:
        db = getattr(__import__("server"), "db")
    today = datetime.now(timezone.utc)
    yr = today.year
    if today.month < 4:
        fy_start = yr - 1
    else:
        fy_start = yr
    fy_end = fy_start + 1
    fy_label = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}"

    min_seq = 16 if fy_label == "26-27" else 1

    max_existing = await _get_max_invoice_seq(fy_label, db=db)
    baseline = max(min_seq - 1, max_existing)

    counter_id = f"invoice_{fy_label}"
    counter_doc = await db.counters.find_one({"_id": counter_id})
    cur_seq = int(counter_doc.get("seq", 0)) if counter_doc else 0
    if cur_seq < baseline:
        await db.counters.update_one(
            {"_id": counter_id},
            {"$set": {"seq": baseline}},
            upsert=True,
        )

    counter = await db.counters.find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int(counter.get("seq", baseline + 1))
    return f"SSK{fy_label}-{seq:03d}"


def _extract_credit_days(payment_terms_text: str | None) -> int:
    """Pull credit days from a free-text payment-terms field. Falls back to DEFAULT_CREDIT_DAYS."""
    if not payment_terms_text:
        return DEFAULT_CREDIT_DAYS
    m = re.search(r"(\d{1,3})\s*(?:days|d)?\b", str(payment_terms_text), flags=re.I)
    if m:
        n = int(m.group(1))
        if 0 < n < 365:
            return n
    return DEFAULT_CREDIT_DAYS


def _due_iso(invoice_date_str: str, credit_days: int) -> str:
    """Convert an invoice_date (DD/MM/YYYY) + credit_days into YYYY-MM-DD."""
    try:
        if "/" in invoice_date_str:
            base = datetime.strptime(invoice_date_str, "%d/%m/%Y")
        else:
            base = datetime.strptime(invoice_date_str[:10], "%Y-%m-%d")
    except Exception:
        base = datetime.now()
    return (base + timedelta(days=int(credit_days))).date().isoformat()


def _compute_invoice_totals(po: dict, line_items: list[dict]) -> dict:
    """Subtotal + CGST/SGST/IGST + grand_total + net_amount from line items, using PO rates."""
    subtotal = sum(float(li.get("amount") or 0) for li in line_items)
    qty = sum(int(li.get("quantity") or 0) for li in line_items)
    cgst_rate = float(po.get("cgst_rate") or 0)
    sgst_rate = float(po.get("sgst_rate") or 0)
    igst_rate = float(po.get("igst_rate") or 0)
    cgst_amt = round(subtotal * cgst_rate / 100, 2)
    sgst_amt = round(subtotal * sgst_rate / 100, 2)
    igst_amt = round(subtotal * igst_rate / 100, 2)
    grand = round(subtotal + cgst_amt + sgst_amt + igst_amt, 2)
    return {
        "subtotal": round(subtotal, 2),
        "total_quantity": qty,
        "cgst_amount": cgst_amt, "sgst_amount": sgst_amt, "igst_amount": igst_amt,
        "cgst_rate": cgst_rate, "sgst_rate": sgst_rate, "igst_rate": igst_rate,
        "grand_total": grand,
        "net_amount": grand,
        "grn_adjustment": 0.0,
    }


def _invoice_iso_date(d: str) -> str:
    """Normalise an invoice_date (DD/MM/YYYY) to YYYY-MM-DD for consistent sorting."""
    try:
        if "/" in d:
            return datetime.strptime(d, "%d/%m/%Y").date().isoformat()
        return datetime.strptime(d[:10], "%Y-%m-%d").date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def _decorate_invoice(doc: dict, payments_map: dict | None = None, grns_map: dict | None = None) -> dict:
    """Compute live status + outstanding from saved invoice doc + payments/grns aggregates."""
    inv = stringify(doc)
    iid = inv.get("id")
    paid = float((payments_map or {}).get(iid, 0))
    
    grn_entry = (grns_map or {}).get(iid, 0)
    if isinstance(grn_entry, dict):
        grn_adj = float(grn_entry.get("adjustment", 0))
        grn_date = grn_entry.get("grn_date") or inv.get("grn_date")
        grn_no = grn_entry.get("grn_no") or inv.get("grn_no")
    else:
        grn_adj = float(grn_entry or 0)
        grn_date = inv.get("grn_date")
        grn_no = inv.get("grn_no")

    grand = float(inv.get("grand_total") or 0)
    if grn_adj == 0.0 and inv.get("grn_adjustment"):
        grn_adj = float(inv.get("grn_adjustment") or 0.0)

    net_after_grn = max(0.0, round(grand - grn_adj, 2))
    outstanding = max(0.0, round(net_after_grn - paid, 2))
    inv["received_amount"] = round(paid, 2)
    inv["grn_adjustment"] = round(grn_adj, 2)
    inv["net_amount"] = net_after_grn
    inv["outstanding"] = outstanding
    inv["grn_date"] = grn_date
    inv["grn_no"] = grn_no
    inv["grn_recorded"] = bool(grn_date)

    credit_days = int(inv.get("payment_terms_days") or 45)
    if grn_date:
        due = _due_iso(grn_date, credit_days)
        inv["due_date"] = due
    else:
        due = None
        inv["due_date"] = None

    today_iso = datetime.now().date().isoformat()
    if outstanding <= 0.01:
        inv["status"] = "paid"
    elif paid > 0.01:
        inv["status"] = "partial"
    elif due and due < today_iso:
        inv["status"] = "overdue"
    else:
        inv["status"] = "pending"

    if due:
        try:
            days = (datetime.fromisoformat(due).date() - datetime.now().date()).days
            inv["days_to_due"] = days
        except Exception:
            inv["days_to_due"] = None
    else:
        inv["days_to_due"] = None

    return inv


async def _aggregate_payments_for_invoices(invoice_ids: list[str], db=None) -> dict[str, float]:
    """Returns invoice_id -> total received (across all payments)."""
    if not invoice_ids:
        return {}
    if db is None:
        db = getattr(__import__("server"), "db")
    payments = await db.payments.find({"invoice_ids": {"$in": invoice_ids}}).to_list(5000)
    out: dict[str, float] = {iid: 0.0 for iid in invoice_ids}
    for p in payments:
        allocs = p.get("allocations") or {}
        if allocs:
            for iid, amt in allocs.items():
                if iid in out:
                    out[iid] += float(amt or 0)
        else:
            amt = float(p.get("amount") or 0)
            ids = [i for i in (p.get("invoice_ids") or []) if i in out]
            if ids:
                share = amt / len(ids)
                for iid in ids:
                    out[iid] += share
    return out


async def _aggregate_grn_adjustments(invoice_ids: list[str], db=None) -> dict[str, dict]:
    """Returns invoice_id -> {adjustment: float, grn_date: str, grn_no: str} across all GRNs."""
    if not invoice_ids:
        return {}
    if db is None:
        db = getattr(__import__("server"), "db")
    grns = await db.grns.find({"invoice_id": {"$in": invoice_ids}}).sort("grn_date", 1).to_list(5000)
    out: dict[str, dict] = {iid: {"adjustment": 0.0, "grn_date": None, "grn_no": None} for iid in invoice_ids}
    invoices = await db.invoices.find({"_id": {"$in": [oid(i) for i in invoice_ids]}}).to_list(5000)
    inv_by_id = {str(d["_id"]): d for d in invoices}
    for g in grns:
        iid = g.get("invoice_id")
        if iid in out:
            if g.get("grn_date"):
                out[iid]["grn_date"] = g.get("grn_date")
            if g.get("grn_no"):
                out[iid]["grn_no"] = g.get("grn_no")
        inv = inv_by_id.get(iid)
        if not inv:
            continue
        prices = {(li.get("style_code"), li.get("color"), str(li.get("size") or "")):
                  float(li.get("unit_price") or 0) for li in (inv.get("line_items_snapshot") or [])}
        for ln in g.get("line_items", []):
            short = max(0, int(ln.get("dispatched_qty", 0)) - int(ln.get("accepted_qty", 0)))
            key = (ln.get("style_code"), ln.get("color"), str(ln.get("size") or ""))
            unit = prices.get(key) or 0
            if iid in out:
                out[iid]["adjustment"] += short * unit
    return out


async def _generate_invoice_payload(po: dict, job_ids: list[str] | None, db=None) -> tuple[dict, list[dict]]:
    """Returns (po-augmented, line_items) for invoice generation, grouped by (style_code, color)."""
    if db is None:
        db = getattr(__import__("server"), "db")
    po_items = po.get("line_items", [])
    po_price_idx = {}
    for li in po_items:
        key = (li.get("style_code"), li.get("color"), str(li.get("size", "")))
        po_price_idx[key] = li

    raw_items = []
    if job_ids:
        obj_ids = []
        for jid in job_ids:
            try:
                obj_ids.append(oid(jid))
            except HTTPException:
                continue
        jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
        for j in jobs:
            key = (j.get("style_code"), j.get("color"), str(j.get("size", "")))
            li_src = po_price_idx.get(key, {})
            comp = j.get("completed_qty")
            qty = comp if (comp is not None and comp > 0) else j.get("quantity", 0)
            unit_price = li_src.get("unit_price") or j.get("unit_price") or 0
            raw_items.append({
                "style_code": j.get("style_code", ""),
                "description": j.get("description") or li_src.get("description", ""),
                "color": j.get("color", ""),
                "size": str(j.get("size", "")),
                "hsn_code": li_src.get("hsn_code", "") or "64029990",
                "quantity": qty,
                "unit_price": unit_price,
                "amount": round(qty * unit_price, 2),
                "mrp": li_src.get("mrp", ""),
            })
    else:
        pid = str(po.get("_id") or po.get("id") or "")
        jobs = []
        if pid:
            try:
                jobs = await db.production_jobs.find({"po_id": pid}).to_list(5000)
            except Exception:
                jobs = []
        if jobs:
            for j in jobs:
                key = (j.get("style_code"), j.get("color"), str(j.get("size", "")))
                li_src = po_price_idx.get(key, {})
                comp = j.get("completed_qty")
                qty = comp if (comp is not None and comp > 0) else j.get("quantity", 0)
                unit_price = li_src.get("unit_price") or j.get("unit_price") or 0
                raw_items.append({
                    "style_code": j.get("style_code", ""),
                    "description": j.get("description") or li_src.get("description", ""),
                    "color": j.get("color", ""),
                    "size": str(j.get("size", "")),
                    "hsn_code": li_src.get("hsn_code", "") or "64029990",
                    "quantity": qty,
                    "unit_price": unit_price,
                    "amount": round(qty * unit_price, 2),
                    "mrp": li_src.get("mrp", ""),
                })
        else:
            for li in po_items:
                comp = li.get("completed_qty")
                qty = comp if (comp is not None and comp > 0) else li.get("quantity", 0)
                unit_price = li.get("unit_price", 0)
                raw_items.append({
                    "style_code": li.get("style_code", ""),
                    "description": li.get("description", ""),
                    "color": li.get("color", ""),
                    "size": str(li.get("size", "")),
                    "hsn_code": li.get("hsn_code", "") or "64029990",
                    "quantity": qty,
                    "unit_price": unit_price,
                    "amount": round(qty * unit_price, 2),
                    "mrp": li.get("mrp", ""),
                })

    # Group by (style_code, color) — 1 row per single style single color
    grouped: dict = {}
    for item in raw_items:
        sc = (item.get("style_code") or "").strip()
        color = (item.get("color") or "").strip()
        g_key = (sc, color)

        desc = (item.get("description") or "").strip()
        clean_desc = re.sub(r'(\s+\d+|\s*/?\s*Sz\s*\d+)+$', '', desc, flags=re.IGNORECASE).strip()

        if g_key not in grouped:
            grouped[g_key] = {
                "style_code": sc,
                "description": clean_desc,
                "color": color,
                "hsn_code": item.get("hsn_code", "") or "64029990",
                "quantity": 0,
                "unit_price": float(item.get("unit_price") or 0),
                "mrp": item.get("mrp", ""),
            }
        grouped[g_key]["quantity"] += int(item.get("quantity", 0) or 0)
        if clean_desc and not grouped[g_key]["description"]:
            grouped[g_key]["description"] = clean_desc

    line_items = []
    for g in grouped.values():
        qty = g["quantity"]
        unit_price = float(g["unit_price"] or 0)
        line_items.append({
            "style_code": g["style_code"],
            "description": g["description"],
            "color": g["color"],
            "hsn_code": g["hsn_code"],
            "quantity": qty,
            "unit_price": unit_price,
            "amount": round(qty * unit_price, 2),
            "mrp": g["mrp"],
        })

    return po, line_items


async def _enrich_cartons_with_mapped_sku(cartons: list[dict], db=None) -> list[dict]:
    """Enrich carton dicts with mapped_from_sku / external_sku if available from jobs/pos/sku_map."""
    if not cartons:
        return cartons
    if db is None:
        db = getattr(__import__("server"), "db")

    job_ids = list({str(c["job_id"]) for c in cartons if c.get("job_id")})
    job_docs = []
    if job_ids:
        valid_oids = [oid(j) for j in job_ids if ObjectId.is_valid(j)]
        if valid_oids:
            job_docs = await db.production_jobs.find({"_id": {"$in": valid_oids}}).to_list(10000)
    job_map = {str(j["_id"]): j for j in job_docs}

    po_ids = list(
        {str(j.get("po_id")) for j in job_docs if j.get("po_id")} |
        {str(c.get("po_id")) for c in cartons if c.get("po_id")}
    )
    po_docs = []
    if po_ids:
        valid_poids = [oid(p) for p in po_ids if ObjectId.is_valid(p)]
        if valid_poids:
            po_docs = await db.pos.find({"_id": {"$in": valid_poids}}).to_list(1000)
    po_map = {str(p["_id"]): p for p in po_docs}

    style_ids = list(
        {str(j.get("style_id")) for j in job_docs if j.get("style_id")} |
        {str(c.get("style_id")) for c in cartons if c.get("style_id")}
    )
    sku_mappings = []
    if style_ids:
        sku_mappings = await db.sku_map.find(
            {"style_id": {"$in": [s for s in style_ids if s]}}
        ).to_list(10000)
    sku_map_by_style_id = {str(m.get("style_id")): m.get("external_sku") for m in sku_mappings if m.get("external_sku")}

    for c in cartons:
        existing = c.get("mapped_from_sku") or c.get("external_sku")
        if existing:
            c["mapped_from_sku"] = existing
            c["external_sku"] = existing
            continue

        job = job_map.get(str(c.get("job_id")))
        if job:
            mapped_sku = job.get("mapped_from_sku") or job.get("external_sku") or job.get("po_style_code")
            if mapped_sku:
                c["mapped_from_sku"] = mapped_sku
                c["external_sku"] = mapped_sku
                continue

            po = po_map.get(str(job.get("po_id") or c.get("po_id")))
            if po and po.get("line_items"):
                c_style = c.get("style_code")
                c_color = c.get("color")
                c_size = str(c.get("size", ""))
                for li in po.get("line_items", []):
                    if li.get("style_code") == c_style and li.get("color") == c_color and str(li.get("size", "")) == c_size:
                        li_mapped = li.get("mapped_from_sku") or li.get("external_sku") or li.get("external_code") or li.get("raw_style_code")
                        if li_mapped:
                            c["mapped_from_sku"] = li_mapped
                            c["external_sku"] = li_mapped
                            break
                if c.get("mapped_from_sku"):
                    continue

            sid = str(job.get("style_id") or c.get("style_id") or "")
            if sid in sku_map_by_style_id:
                c["mapped_from_sku"] = sku_map_by_style_id[sid]
                c["external_sku"] = sku_map_by_style_id[sid]
                continue

    return cartons


async def _flag_jobs(job_ids: list, field: str, db=None) -> None:
    """Mark a batch of jobs with a timestamped field. If the other flag is also
    present, additionally mark archived=True/archived_at."""
    if not job_ids:
        return
    if db is None:
        db = getattr(__import__("server"), "db")
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


async def _build_packing_payload(po: dict, job_ids: list[str] | None, db=None) -> dict:
    """Build a PO-like dict suitable for the packing list generator."""
    po_aug, items = await _generate_invoice_payload(po, job_ids, db=db)
    out = dict(po_aug)
    out["line_items"] = items
    out["total_quantity"] = sum((li.get("quantity") or 0) for li in items)
    return out


def _packing_options_from_payload(p) -> dict:
    """Pull all manual / shipping fields from the request payload."""
    return {
        "carton_dim": p.carton_dim,
        "pcs_per_box": p.pcs_per_box,
        "net_wt_per_carton": p.net_wt_per_carton,
        "gross_wt_per_carton": p.gross_wt_per_carton,
        "dispatch_date": p.dispatch_date or "",
        "transporter": p.transporter or "",
        "vehicle_no": p.vehicle_no or "",
        "driver_name": p.driver_name or "",
        "driver_phone": p.driver_phone or "",
        "site_code": p.site_code or "",
        "destination": p.destination or "",
        "port": p.port or "",
        "notes": p.notes or "",
    }


async def _auto_pick_template(client_name: str, db=None) -> Optional[str]:
    """Return template_id whose alias matches client_name; case-insensitive."""
    if not client_name:
        return None
    if db is None:
        db = getattr(__import__("server"), "db")
    docs = await db.packing_templates.find({}).to_list(200)
    cn = client_name.upper()
    best = None
    for d in docs:
        aliases = [a.upper().strip() for a in (d.get("aliases") or []) if a and a.strip()]
        if not aliases:
            if d.get("client_name", "").strip().upper() == cn:
                return str(d["_id"])
            continue
        if any(a in cn or cn in a for a in aliases):
            best = str(d["_id"])
            break
    return best


async def _generate_packing_bytes(payload_po: dict, options: dict, template_id: Optional[str], cartons: Optional[list] = None, invoice_no: str = "", db=None) -> bytes:
    """Resolve template (explicit or auto) and produce the xlsx bytes."""
    if db is None:
        db = getattr(__import__("server"), "db")
    tpl_id = template_id
    if not tpl_id:
        tpl_id = await _auto_pick_template(payload_po.get("client_name", ""), db=db)
    if tpl_id:
        tdoc = await db.packing_templates.find_one({"_id": oid(tpl_id)})
        if not tdoc:
            raise HTTPException(404, "Packing template not found")
        tpl_bytes = base64.b64decode(tdoc["file_b64"])
        return build_from_template(tpl_bytes, payload_po, options, cartons=cartons)
    if cartons is not None:
        return build_dispatch_packing_list(cartons, payload_po, invoice_no, options)
    return build_default_packing_list(payload_po, options)


# ── Invoice Endpoints ─────────────────────────────────────────────────────
@invoice_packing_router.post("/admin/resync-invoice-sequence")
async def resync_invoice_sequence(request: Request):
    """Admin endpoint to audit and synchronize the invoice sequence counter with database records."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    today = datetime.now(timezone.utc)
    yr = today.year
    fy_start = yr - 1 if today.month < 4 else yr
    fy_end = fy_start + 1
    fy_label = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}"
    min_seq = 16 if fy_label == "26-27" else 1

    max_existing = await _get_max_invoice_seq(fy_label, db=db)
    target_seq = max(min_seq - 1, max_existing)

    counter_id = f"invoice_{fy_label}"
    await db.counters.update_one(
        {"_id": counter_id},
        {"$set": {"seq": target_seq}},
        upsert=True,
    )

    return {
        "ok": True,
        "fy_label": fy_label,
        "max_existing_seq": max_existing,
        "synced_counter_seq": target_seq,
        "next_invoice_will_be": f"SSK{fy_label}-{target_seq + 1:03d}",
    }


@invoice_packing_router.get("/pos/{pid}/invoices")
async def list_po_invoices(pid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "PO not found")
    po_number = doc.get("po_number")
    query_or = [{"po_id": pid}]
    if po_number:
        query_or.extend([{"po_numbers": po_number}, {"po_number": po_number}])
    
    docs = await db.invoices.find({"$or": query_or}, {"file_b64": 0}).sort("created_at", -1).to_list(100)
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids, db=db)
    grn_map = await _aggregate_grn_adjustments(inv_ids, db=db)
    return [_decorate_invoice(d, pay_map, grn_map) for d in docs]


@invoice_packing_router.get("/pos/{pid}/invoice.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def po_invoice(pid: str, request: Request):
    u = await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "Not found")
    po = stringify(doc)

    po_number = po.get("po_number")
    query_or = [{"po_id": pid}]
    if po_number:
        query_or.extend([{"po_numbers": po_number}, {"po_number": po_number}])
    existing = await db.invoices.find({"$or": query_or}).sort("created_at", -1).to_list(100)

    if len(existing) == 1:
        inv = existing[0]
        file_b64 = inv.get("file_b64")
        if file_b64:
            pdf_bytes = base64.b64decode(file_b64)
        else:
            inv_no = inv.get("invoice_no") or po.get("invoice_no") or await next_invoice_no(db=db)
            inv_date = inv.get("invoice_date") or po.get("invoice_date") or datetime.now().strftime("%d/%m/%Y")
            po_payload, line_items = await _generate_invoice_payload(po, None, db=db)
            pdf_bytes = build_invoice(po_payload, inv_no, inv_date, line_items=line_items)
            encoded = base64.b64encode(pdf_bytes).decode("ascii")
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"file_b64": encoded}})
        inv_no = inv.get("invoice_no") or "invoice"
        return StreamingResponse(
            BytesIO(pdf_bytes), media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{inv_no}.pdf"'},
        )
    elif len(existing) > 1:
        inv_list = [
            {
                "id": str(inv["_id"]),
                "invoice_no": inv.get("invoice_no"),
                "invoice_date": inv.get("invoice_date"),
                "job_ids": inv.get("job_ids", []),
                "grand_total": inv.get("grand_total"),
                "created_at": inv.get("created_at"),
            }
            for inv in existing
        ]
        return JSONResponse({"multiple": True, "invoices": inv_list})

    invoice_no = po.get("invoice_no")
    invoice_date = po.get("invoice_date")
    if not invoice_no:
        invoice_no = await next_invoice_no(db=db)
        invoice_date = datetime.now().strftime("%d/%m/%Y")
        await db.pos.update_one({"_id": oid(pid)}, {"$set": {"invoice_no": invoice_no, "invoice_date": invoice_date}})
        po["invoice_no"] = invoice_no
        po["invoice_date"] = invoice_date

    po, line_items = await _generate_invoice_payload(po, None, db=db)
    pdf_bytes = build_invoice(po, invoice_no, invoice_date, line_items=line_items)

    totals = _compute_invoice_totals(po, line_items)
    credit_days = _extract_credit_days(po.get("payment_terms", ""))
    invoice_iso = _invoice_iso_date(invoice_date)
    user_email = u.get("email", "system") if isinstance(u, dict) else "system"
    inv_doc = {
        "invoice_no": invoice_no,
        "invoice_date": invoice_date,
        "invoice_iso_date": invoice_iso,
        "due_date": None,
        "grn_date": None,
        "grn_recorded": False,
        "payment_terms_days": credit_days,
        "po_id": pid,
        "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")] if po.get("po_number") else [],
        "client_name": po.get("client_name"),
        "job_ids": [],
        "line_items_snapshot": line_items,
        **totals,
        "transport_mode": "",
        "vehicle_no": "",
        "supply_date": "",
        "by": user_email,
        "created_at": now_iso(),
        "file_b64": base64.b64encode(pdf_bytes).decode("ascii"),
        "merged": False,
    }
    await db.invoices.insert_one(inv_doc)

    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_no}.pdf"'},
    )


@invoice_packing_router.post("/invoices/job", dependencies=[Depends(pdf_rate_limiter)])
async def invoice_for_jobs(payload: InvoiceGenerate, request: Request):
    """Generate an invoice for a subset of production jobs (dispatched). Supports merging."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)

    if payload.job_ids:
        dr_existing = await db.dispatch_records.find_one({"job_ids": {"$in": payload.job_ids}})
        if dr_existing and dr_existing.get("invoice_file_b64"):
            raw_pdf = base64.b64decode(dr_existing.get("invoice_file_b64") or "")
            if raw_pdf:
                inv_no = dr_existing.get("invoice_no", "invoice")
                return StreamingResponse(
                    BytesIO(raw_pdf), media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'inline; filename="{inv_no}.pdf"',
                        "X-Dispatch-Record-Id": str(dr_existing["_id"]),
                        "X-Invoice-Id": str(dr_existing.get("invoice_id") or dr_existing["_id"]),
                        "X-Invoice-No": inv_no,
                    },
                )

        inv_existing = await db.invoices.find_one({"job_ids": {"$in": payload.job_ids}})
        if inv_existing and inv_existing.get("file_b64"):
            raw_pdf = base64.b64decode(inv_existing.get("file_b64") or "")
            if raw_pdf:
                inv_no = inv_existing.get("invoice_no", "invoice")
                return StreamingResponse(
                    BytesIO(raw_pdf), media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'inline; filename="{inv_no}.pdf"',
                        "X-Invoice-Id": str(inv_existing["_id"]),
                        "X-Invoice-No": inv_no,
                    },
                )

    po, line_items = await _generate_invoice_payload(po, payload.job_ids, db=db)
    invoice_no = await next_invoice_no(db=db)
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    pdf_bytes = build_invoice(
        po, invoice_no, invoice_date,
        transport_mode=payload.transport_mode or "",
        vehicle_no=payload.vehicle_no or "",
        supply_date=payload.supply_date or "",
        line_items=line_items,
    )
    totals = _compute_invoice_totals(po, line_items)
    credit_days = _extract_credit_days(po.get("payment_terms", ""))
    invoice_iso = _invoice_iso_date(invoice_date)
    inv_doc = {
        "invoice_no": invoice_no, "invoice_date": invoice_date,
        "invoice_iso_date": invoice_iso,
        "due_date": None, "payment_terms_days": credit_days,
        "grn_date": None, "grn_recorded": False,
        "po_id": payload.po_id, "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")],
        "client_name": po.get("client_name"),
        "job_ids": payload.job_ids or [],
        "line_items_snapshot": line_items,
        **totals,
        "transport_mode": payload.transport_mode, "vehicle_no": payload.vehicle_no,
        "supply_date": payload.supply_date,
        "by": u["email"], "created_at": now_iso(),
        "file_b64": base64.b64encode(pdf_bytes).decode("ascii"),
        "merged": False,
    }
    res = await db.invoices.insert_one(inv_doc)
    cartons = await db.packing_cartons.find({"job_id": {"$in": payload.job_ids or []}, "status": "packed"}).to_list(10000)
    for idx, carton in enumerate(cartons):
        await db.packing_cartons.update_one(
            {"_id": carton["_id"]},
            {"$set": {
                "status": "dispatched",
                "invoice_id": str(res.inserted_id),
                "box_number": idx + 1
            }}
        )
    await _flag_jobs(payload.job_ids or [], "invoice_generated_at", db=db)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice_no}.pdf"',
            "X-Invoice-Id": str(res.inserted_id),
        },
    )


@invoice_packing_router.delete("/invoices/{id}")
async def delete_invoice(id: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    inv = await db.invoices.find_one({"_id": oid(id)})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    
    job_ids = inv.get("job_ids", [])
    if job_ids:
        obj_ids = [oid(j) for j in job_ids]
        await db.production_jobs.update_many(
            {"_id": {"$in": obj_ids}},
            {"$set": {"stage": "qc_pack"}, "$unset": {"invoice_generated_at": ""}}
        )
        for o_id in obj_ids:
            await db.production_jobs.update_one(
                {"_id": o_id},
                {"$push": {"history": {
                    "stage": "qc_pack", "at": now_iso(), "by": u["email"],
                    "notes": f"Invoice {inv.get('invoice_no')} deleted; stage reverted to QC & Pack",
                    "qc_pass": None, "rejected_qty": 0
                }}}
            )
    
    await db.packing_cartons.update_many(
        {"invoice_id": id},
        {"$set": {
            "status": "packed",
            "invoice_id": None,
            "box_number": None
        }}
    )
    
    await db.payments.delete_many({"invoice_id": id})
    await db.invoices.delete_one({"_id": oid(id)})
    await db.dispatch_records.delete_many({"$or": [{"invoice_id": id}, {"invoice_no": inv.get("invoice_no")}]})

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
        log.warning(f"Failed to resync invoice counter after deletion: {e}")

    return {"ok": True}


@invoice_packing_router.post("/invoices/merged", dependencies=[Depends(pdf_rate_limiter)])
async def merged_invoice(payload: dict, request: Request):
    """Generate a single merged invoice across multiple POs/jobs.
    All entries must share the same client and PO.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    entries = payload.get("entries", [])
    if not entries:
        raise HTTPException(400, "No entries")

    first_po = await db.pos.find_one({"_id": oid(entries[0]["po_id"])})
    if not first_po:
        raise HTTPException(404, "First PO not found")
    parent = stringify(first_po)

    all_items = []
    po_numbers = []
    job_ids_all = []
    for e in entries:
        po_doc = await db.pos.find_one({"_id": oid(e["po_id"])})
        if not po_doc:
            continue
        po_x = stringify(po_doc)
        po_numbers.append(po_x.get("po_number", ""))
        _, lis = await _generate_invoice_payload(po_x, e.get("job_ids"), db=db)
        all_items.extend(lis)
        job_ids_all.extend(e.get("job_ids") or [])

    if len(set([p for p in po_numbers if p])) > 1:
        raise HTTPException(400, "Cannot merge invoices across different POs")

    if not all_items:
        raise HTTPException(400, "No line items found across entries")

    merged_grouped: dict = {}
    for item in all_items:
        sc = (item.get("style_code") or "").strip()
        color = (item.get("color") or "").strip()
        g_key = (sc, color)
        if g_key not in merged_grouped:
            merged_grouped[g_key] = dict(item)
        else:
            merged_grouped[g_key]["quantity"] += item.get("quantity", 0)
            merged_grouped[g_key]["amount"] = round(
                merged_grouped[g_key]["quantity"] * float(merged_grouped[g_key].get("unit_price") or 0), 2
            )
    all_items = list(merged_grouped.values())

    invoice_no = await next_invoice_no(db=db)
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    parent["po_number"] = ", ".join([p for p in po_numbers if p])
    pdf_bytes = build_invoice(
        parent, invoice_no, invoice_date,
        transport_mode=payload.get("transport_mode", ""),
        vehicle_no=payload.get("vehicle_no", ""),
        supply_date=payload.get("supply_date", ""),
        line_items=all_items,
    )
    credit_days_m = _extract_credit_days(parent.get("payment_terms", ""))
    
    # Renumber packing cartons continuously across all merged jobs and regenerate carton labels
    cartons_m = await db.packing_cartons.find({"job_id": {"$in": job_ids_all}}).sort([("size", 1), ("_id", 1)]).to_list(10000)
    cartons_list = [stringify(c) for c in cartons_m]
    total_cartons = len(cartons_list)
    for idx, carton in enumerate(cartons_list):
        carton["box_number"] = idx + 1
        carton["total_cartons"] = total_cartons

    merged_labels_b64 = None
    if cartons_list:
        cartons_list = await _enrich_cartons_with_mapped_sku(cartons_list, db=db)
        merged_labels_pdf = build_carton_labels(cartons_list, parent.get("po_number", ""), invoice_no)
        merged_labels_b64 = base64.b64encode(merged_labels_pdf).decode("ascii")

    inv_doc_m = {
        "invoice_no": invoice_no, "invoice_date": invoice_date,
        "invoice_iso_date": _invoice_iso_date(invoice_date),
        "due_date": None,
        "payment_terms_days": credit_days_m,
        "grn_date": None, "grn_recorded": False,
        "merged": True, "po_numbers": po_numbers, "job_ids": job_ids_all,
        "po_id": str(first_po.get("_id")),
        "po_number": " + ".join(po_numbers),
        "client_name": parent.get("client_name"),
        "line_items_snapshot": all_items,
        **_compute_invoice_totals(parent, all_items),
        "by": u["email"], "created_at": now_iso(),
        "file_b64": base64.b64encode(pdf_bytes).decode("ascii"),
        "carton_labels_file_b64": merged_labels_b64,
    }
    res_m = await db.invoices.insert_one(inv_doc_m)

    for idx, carton in enumerate(cartons_list):
        await db.packing_cartons.update_one(
            {"_id": oid(carton["id"])},
            {"$set": {
                "status": "dispatched",
                "invoice_id": str(res_m.inserted_id),
                "box_number": idx + 1
            }}
        )
    await _flag_jobs(job_ids_all, "invoice_generated_at", db=db)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice_no}.pdf"',
            "X-Invoice-Id": str(res_m.inserted_id),
        },
    )


@invoice_packing_router.get("/pos/{pid}/challan.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def po_challan(pid: str, request: Request, dispatch_qty: Optional[int] = None,
                     transporter: str = "", vehicle: str = ""):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "Not found")
    po = stringify(doc)
    pdf_bytes = generate_dispatch_challan_pdf(po, dispatch_qty=dispatch_qty,
                                              transporter=transporter, vehicle=vehicle)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="challan-{po.get("po_number","po")}.pdf"'},
    )


@invoice_packing_router.get("/invoices/cash-forecast")
async def get_inflow_cash_forecast(request: Request):
    """Weekly cash inflow forecast based on GRN-calculated due dates for vendor payment planning."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    docs = await db.invoices.find({"legacy": {"$ne": True}}, {"file_b64": 0}).sort("created_at", -1).to_list(1000)
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids, db=db)
    grn_map = await _aggregate_grn_adjustments(inv_ids, db=db)
    rows = [_decorate_invoice(d, pay_map, grn_map) for d in docs]

    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())

    weeks = []
    for w in range(8):
        w_start = start_of_week + timedelta(days=w * 7)
        w_end = w_start + timedelta(days=6)
        label = "This Week" if w == 0 else ("Next Week" if w == 1 else f"Week {w+1}")
        weeks.append({
            "week_index": w,
            "label": label,
            "start_date": w_start.isoformat(),
            "end_date": w_end.isoformat(),
            "display_range": f"{w_start.strftime('%d %b')} – {w_end.strftime('%d %b')}",
            "total_amount": 0.0,
            "invoice_count": 0,
            "invoices": [],
        })

    overdue_bucket = {"label": "Overdue / Immediate", "total_amount": 0.0, "invoice_count": 0, "invoices": []}
    awaiting_grn_bucket = {"label": "Awaiting GRN", "total_amount": 0.0, "invoice_count": 0, "invoices": []}
    future_bucket = {"label": "8+ Weeks Out", "total_amount": 0.0, "invoice_count": 0, "invoices": []}
    by_date_map: dict[str, dict] = {}

    for r in rows:
        outstanding = float(r.get("outstanding") or 0)
        if outstanding <= 0.01:
            continue
        
        due_str = r.get("due_date")
        if not due_str:
            awaiting_grn_bucket["total_amount"] += outstanding
            awaiting_grn_bucket["invoice_count"] += 1
            awaiting_grn_bucket["invoices"].append({
                "id": r.get("id"),
                "invoice_no": r.get("invoice_no"),
                "client_name": r.get("client_name"),
                "invoice_date": r.get("invoice_date"),
                "outstanding": outstanding,
                "status": r.get("status"),
                "payment_terms_days": r.get("payment_terms_days", 45),
            })
            continue

        try:
            due_d = datetime.strptime(str(due_str)[:10], "%Y-%m-%d").date()
        except Exception:
            awaiting_grn_bucket["total_amount"] += outstanding
            awaiting_grn_bucket["invoice_count"] += 1
            awaiting_grn_bucket["invoices"].append(r)
            continue

        inv_summary = {
            "id": r.get("id"),
            "invoice_no": r.get("invoice_no"),
            "client_name": r.get("client_name"),
            "due_date": due_str,
            "grn_date": r.get("grn_date"),
            "grn_no": r.get("grn_no"),
            "outstanding": outstanding,
            "status": r.get("status"),
            "days_to_due": r.get("days_to_due"),
        }

        if due_str not in by_date_map:
            by_date_map[due_str] = {
                "date": due_str,
                "formatted_date": due_d.strftime("%a, %d %b %Y"),
                "days_to_go": (due_d - today).days,
                "total_amount": 0.0,
                "invoices": [],
            }
        by_date_map[due_str]["total_amount"] += outstanding
        by_date_map[due_str]["invoices"].append(inv_summary)

        if due_d < today:
            overdue_bucket["total_amount"] += outstanding
            overdue_bucket["invoice_count"] += 1
            overdue_bucket["invoices"].append(inv_summary)
        else:
            diff_days = (due_d - start_of_week).days
            w_idx = diff_days // 7
            if 0 <= w_idx < len(weeks):
                weeks[w_idx]["total_amount"] += outstanding
                weeks[w_idx]["invoice_count"] += 1
                weeks[w_idx]["invoices"].append(inv_summary)
            else:
                future_bucket["total_amount"] += outstanding
                future_bucket["invoice_count"] += 1
                future_bucket["invoices"].append(inv_summary)

    overdue_bucket["total_amount"] = round(overdue_bucket["total_amount"], 2)
    awaiting_grn_bucket["total_amount"] = round(awaiting_grn_bucket["total_amount"], 2)
    future_bucket["total_amount"] = round(future_bucket["total_amount"], 2)
    for w in weeks:
        w["total_amount"] = round(w["total_amount"], 2)

    by_date_list = sorted(by_date_map.values(), key=lambda x: x["date"])
    for d_item in by_date_list:
        d_item["total_amount"] = round(d_item["total_amount"], 2)

    total_scheduled = sum(w["total_amount"] for w in weeks) + overdue_bucket["total_amount"] + future_bucket["total_amount"]
    total_pipeline = total_scheduled + awaiting_grn_bucket["total_amount"]

    return {
        "as_of_date": today.isoformat(),
        "total_scheduled": round(total_scheduled, 2),
        "total_pipeline": round(total_pipeline, 2),
        "overdue": overdue_bucket,
        "weeks": [w for w in weeks if w["total_amount"] > 0 or w["week_index"] < 4],
        "future": future_bucket,
        "awaiting_grn": awaiting_grn_bucket,
        "by_date": by_date_list,
    }


@invoice_packing_router.get("/invoices")
async def list_invoices(request: Request, client: Optional[str] = None,
                        status: Optional[str] = None, include_legacy: bool = False,
                        limit: int = 500):
    """Return all generated invoices, decorated with live status + outstanding."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if not include_legacy:
        q["legacy"] = {"$ne": True}
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    docs = await db.invoices.find(q, {"file_b64": 0}).sort("created_at", -1).to_list(limit)
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids, db=db)
    grn_map = await _aggregate_grn_adjustments(inv_ids, db=db)
    rows = [_decorate_invoice(d, pay_map, grn_map) for d in docs]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows


@invoice_packing_router.get("/invoices/overdue")
async def overdue_invoices(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    docs = await db.invoices.find({}, {"file_b64": 0}).sort("due_date", 1).to_list(500)
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids, db=db)
    grn_map = await _aggregate_grn_adjustments(inv_ids, db=db)
    rows = [_decorate_invoice(d, pay_map, grn_map) for d in docs]
    return [r for r in rows if r["status"] == "overdue"]


@invoice_packing_router.get("/invoices/{iid}")
async def get_invoice(iid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.invoices.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Invoice not found")
    pay_map = await _aggregate_payments_for_invoices([iid], db=db)
    grn_map = await _aggregate_grn_adjustments([iid], db=db)
    inv = _decorate_invoice(doc, pay_map, grn_map)
    inv.pop("file_b64", None)
    payments = await db.payments.find({"invoice_ids": iid}).sort("payment_date", -1).to_list(200)
    grns = await db.grns.find({"invoice_id": iid}).sort("grn_date", -1).to_list(200)
    inv["payments"] = [stringify(p) for p in payments]
    inv["grns"] = [stringify(g) for g in grns]
    return inv


@invoice_packing_router.get("/invoices/{iid}/file", dependencies=[Depends(pdf_rate_limiter)])
async def download_invoice_file(iid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.invoices.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Invoice not found")
    raw = base64.b64decode(doc.get("file_b64", "") or b"")
    if not raw:
        raise HTTPException(404, "No PDF stored for this invoice (predates persistence). Regenerate from the PO.")
    fname = f"{doc.get('invoice_no', 'invoice')}.pdf"
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@invoice_packing_router.get("/invoices/{iid}/carton-labels", dependencies=[Depends(pdf_rate_limiter)])
async def download_invoice_carton_labels(iid: str, request: Request):
    """Re-download carton labels PDF stored on an invoice without regeneration."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.invoices.find_one({"_id": oid(iid)}, {"carton_labels_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Invoice not found")
    raw = base64.b64decode(doc.get("carton_labels_file_b64", "") or b"")
    if not raw:
        raise HTTPException(404, "No carton labels stored for this invoice")
    fname = f"CartonLabels-{doc.get('invoice_no', 'invoice')}.pdf"
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── EAN Codes & Packing Cartons ──────────────────────────────────────────
@invoice_packing_router.get("/packing/ean-codes")
async def get_ean_codes(style_id: str, request: Request, color: str | None = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {"style_id": style_id}
    if color:
        q["color"] = color
    codes = await db.sku_ean_codes.find(q).to_list(1000)
    return [stringify(c) for c in codes]


@invoice_packing_router.post("/packing/ean-codes")
async def create_ean_code(payload: EanCodeIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {"style_id": payload.style_id, "color": payload.color, "size": payload.size}
    existing = await db.sku_ean_codes.find_one(q)
    if existing:
        await db.sku_ean_codes.update_one(q, {"$set": {"ean_code": payload.ean_code, "updated_at": now_iso()}})
        return {"ok": True, "id": str(existing["_id"])}
    else:
        doc = {**q, "ean_code": payload.ean_code, "created_at": now_iso()}
        res = await db.sku_ean_codes.insert_one(doc)
        return {"ok": True, "id": str(res.inserted_id)}


@invoice_packing_router.get("/packing/cartons")
async def get_cartons(request: Request, job_id: Optional[str] = None, job_ids: Optional[str] = None):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {}
    if job_ids:
        q["job_id"] = {"$in": job_ids.split(",")}
    elif job_id:
        q["job_id"] = job_id
    cartons = await db.packing_cartons.find(q).to_list(1000)
    return [stringify(c) for c in cartons]


@invoice_packing_router.post("/packing/cartons")
async def pack_carton(payload: CartonIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job = await db.production_jobs.find_one({"_id": oid(payload.job_id)})
    if not job:
        raise HTTPException(404, "Job not found")
    
    ean_code = ""
    if job.get("style_id"):
        ean_doc = await db.sku_ean_codes.find_one({
            "style_id": str(job["style_id"]),
            "color": job.get("color"),
            "size": payload.size
        })
        ean_code = ean_doc["ean_code"] if ean_doc else ""
    
    mapped_sku = job.get("mapped_from_sku") or job.get("external_sku")
    doc = {
        "job_id": payload.job_id,
        "po_id": job.get("po_id"),
        "style_id": job.get("style_id"),
        "style_code": job.get("style_code"),
        "mapped_from_sku": mapped_sku,
        "external_sku": mapped_sku,
        "color": job.get("color"),
        "size": payload.size,
        "ean_code": ean_code,
        "qty": payload.qty,
        "box_number": None,
        "invoice_id": None,
        "packed_at": now_iso(),
        "packed_by": u["email"],
        "status": "packed"
    }
    res = await db.packing_cartons.insert_one(doc)
    return {"ok": True, "id": str(res.inserted_id)}


@invoice_packing_router.delete("/packing/cartons/{cid}")
async def delete_carton(cid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    await db.packing_cartons.delete_one({"_id": oid(cid)})
    return {"ok": True}


@invoice_packing_router.post("/packing/confirm-qc-pack")
async def confirm_qc_pack(payload: QcPackConfirmIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    if not payload.job_ids:
        raise HTTPException(400, "No job IDs provided")
        
    job_objs = []
    for jid in payload.job_ids:
        job = await db.production_jobs.find_one({"_id": oid(jid)})
        if not job:
            raise HTTPException(404, f"Job {jid} not found")
        job_objs.append(job)
        
    style_id = job_objs[0].get("style_id")
    style_code = job_objs[0].get("style_code")
    po_id = job_objs[0].get("po_id")
    color = job_objs[0].get("color")
    job_obj_map = {str(j["_id"]): j for j in job_objs}
    
    for job in job_objs:
        if job.get("style_id") != style_id or job.get("color") != color:
            raise HTTPException(400, "All jobs must share the same style and color")

    for item in payload.eans:
        if not item.ean_code.strip():
            continue
        q = {"style_id": str(style_id), "color": color, "size": item.size}
        existing = await db.sku_ean_codes.find_one(q)
        if existing:
            await db.sku_ean_codes.update_one(q, {"$set": {"ean_code": item.ean_code.strip(), "updated_at": now_iso()}})
        else:
            doc = {**q, "ean_code": item.ean_code.strip(), "created_at": now_iso()}
            await db.sku_ean_codes.insert_one(doc)

    await db.packing_cartons.delete_many({"job_id": {"$in": payload.job_ids}})

    carton_docs = []
    ean_map = {}
    async for e in db.sku_ean_codes.find({"style_id": str(style_id), "color": color}):
        ean_map[e["size"]] = e["ean_code"]

    job_by_size = {job.get("size"): str(job["_id"]) for job in job_objs}

    for c in payload.cartons:
        size = c.size
        qty = c.qty
        job_id = job_by_size.get(size)
        if not job_id:
            raise HTTPException(400, f"Size {size} not found in color group jobs")
        ean_code = ean_map.get(size, "")
        target_job = job_obj_map.get(job_id, job_objs[0])
        mapped_sku = target_job.get("mapped_from_sku") or target_job.get("external_sku")
        
        carton_docs.append({
            "job_id": job_id,
            "po_id": str(po_id),
            "style_id": str(style_id),
            "style_code": style_code,
            "mapped_from_sku": mapped_sku,
            "external_sku": mapped_sku,
            "color": color,
            "size": size,
            "ean_code": ean_code,
            "qty": qty,
            "box_number": None,
            "invoice_id": None,
            "packed_at": now_iso(),
            "packed_by": u["email"],
            "status": "packed"
        })

    if carton_docs:
        await db.packing_cartons.insert_many(carton_docs)

    durations = await _get_stage_durations(db=db)
    entered = now_iso()
    hours = float(durations.get("qc_pack", 12))
    deadline = _compute_deadline(entered, hours)
    
    for job in job_objs:
        stage_changing = job.get("stage") != "qc_pack"
        update = {
            "stage": "qc_pack",
            "stage_entered_at": entered,
            "stage_deadline": deadline,
            "updated_at": now_iso()
        }
        if stage_changing:
            history_entry = {
                "stage": "qc_pack", "at": entered, "by": u["email"],
                "notes": "QC & Pack Carton packing confirmed",
                "qc_pass": None, "rejected_qty": 0
            }
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": update, "$push": {"history": history_entry}}
            )
        else:
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": update}
            )

    return {"ok": True, "count": len(carton_docs)}


@invoice_packing_router.get("/production/jobs/carton-labels", dependencies=[Depends(pdf_rate_limiter)])
async def get_direct_carton_labels(job_ids: str, request: Request):
    """Generate carton labels directly for given job IDs."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    jids = job_ids.split(",")
    carton_docs = await db.packing_cartons.find({"job_id": {"$in": jids}}).sort([("size", 1), ("_id", 1)]).to_list(1000)
    if not carton_docs:
        raise HTTPException(400, "No cartons packed for these jobs")

    job_docs = await db.production_jobs.find({"_id": {"$in": [oid(jid) for jid in jids]}}).to_list(1000)
    po_numbers = {job.get("po_number") for job in job_docs if job and job.get("po_number")}
    if len(po_numbers) > 1:
        raise HTTPException(400, "Cannot merge carton labels for multiple PO numbers")

    cartons = [stringify(c) for c in carton_docs]
    total_cartons = len(cartons)
    for idx, c in enumerate(cartons):
        c["box_number"] = idx + 1
        c["total_cartons"] = total_cartons

    cartons = await _enrich_cartons_with_mapped_sku(cartons, db=db)

    job = await db.production_jobs.find_one({"_id": oid(jids[0])})
    po_number = job.get("po_number", "DRAFT") if job else "DRAFT"

    invoice_no = "DRAFT"
    invoice_id = next((c.get("invoice_id") for c in cartons if c.get("invoice_id")), None)
    if invoice_id:
        invoice = await db.invoices.find_one({"_id": oid(invoice_id)})
        if invoice:
            invoice_no = invoice.get("invoice_no", "DRAFT")

    pdf_bytes = build_carton_labels(cartons, po_number, invoice_no)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CartonLabels-{invoice_no}.pdf"'},
    )


@invoice_packing_router.get("/production/jobs/carton-list", dependencies=[Depends(pdf_rate_limiter)])
async def get_direct_carton_list(job_ids: str, request: Request):
    """Generate carton list directly for given job IDs."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    jids = job_ids.split(",")
    carton_docs = await db.packing_cartons.find({"job_id": {"$in": jids}}).sort([("size", 1), ("_id", 1)]).to_list(1000)
    if not carton_docs:
        raise HTTPException(400, "No cartons packed for these jobs")

    job_docs = await db.production_jobs.find({"_id": {"$in": [oid(jid) for jid in jids]}}).to_list(1000)
    po_numbers = {job.get("po_number") for job in job_docs if job and job.get("po_number")}
    if len(po_numbers) > 1:
        raise HTTPException(400, "Cannot merge carton lists for multiple PO numbers")

    cartons = [stringify(c) for c in carton_docs]
    total_cartons = len(cartons)
    for idx, c in enumerate(cartons):
        c["box_number"] = idx + 1
        c["total_cartons"] = total_cartons

    cartons = await _enrich_cartons_with_mapped_sku(cartons, db=db)

    job = await db.production_jobs.find_one({"_id": oid(jids[0])})
    po_doc = await db.pos.find_one({"_id": oid(job["po_id"])}) if (job and job.get("po_id")) else None
    po = stringify(po_doc) if po_doc else {"po_number": "DRAFT"}

    invoice_no = "DRAFT"
    invoice_id = next((c.get("invoice_id") for c in cartons if c.get("invoice_id")), None)
    if invoice_id:
        invoice = await db.invoices.find_one({"_id": oid(invoice_id)})
        if invoice:
            invoice_no = invoice.get("invoice_no", "DRAFT")

    pl_options = {
        "carton_dim": "60x50x30 CMS",
        "net_wt_per_carton": "",
        "gross_wt_per_carton": "",
        "dispatch_date": "",
        "transporter": "",
        "vehicle_no": "",
        "driver_name": "",
        "driver_phone": "",
        "site_code": "",
        "destination": "",
        "port": "",
        "notes": "",
    }
    excel_bytes = build_carton_list_xlsx(cartons, po, invoice_no, pl_options)
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="CartonList-{invoice_no}.xlsx"'},
    )


# ── Unified Dispatch & Dispatch Records ────────────────────────────────────
@invoice_packing_router.post("/dispatch", dependencies=[Depends(pdf_rate_limiter)])
async def create_dispatch(payload: DispatchCreate, request: Request):
    """Unified dispatch action for one or more qc_pack jobs."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    if not payload.job_ids:
        raise HTTPException(400, "job_ids required")

    # 1. Load PO
    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)

    # 1.5 Handle partial dispatch / job splitting if dispatch_quantities is provided
    effective_job_ids = []
    dispatch_qty_map = payload.dispatch_quantities or {}

    for jid in payload.job_ids:
        orig_job = await db.production_jobs.find_one({"_id": oid(jid)})
        if not orig_job:
            effective_job_ids.append(jid)
            continue

        orig_qty = int(orig_job.get("quantity", 0))
        target_qty = int(dispatch_qty_map.get(jid, orig_qty)) if (jid in dispatch_qty_map) else orig_qty

        if 0 < target_qty < orig_qty:
            # Partial dispatch: split job
            rem_qty = orig_qty - target_qty
            orig_comp = orig_job.get("completed_qty", 0) or 0
            new_comp = min(target_qty, orig_comp)
            rem_comp = min(rem_qty, max(0, orig_comp - target_qty))

            # Split assignments
            orig_asgn = orig_job.get("assignments") or {}
            new_asgn = {}
            rem_asgn = {}
            if isinstance(orig_asgn, dict):
                for role_k, role_v in orig_asgn.items():
                    if isinstance(role_v, dict):
                        nv = dict(role_v)
                        rv = dict(role_v)
                        r_comp = role_v.get("completed_qty")
                        if r_comp is not None:
                            nv["completed_qty"] = min(target_qty, r_comp)
                            rv["completed_qty"] = min(rem_qty, max(0, r_comp - target_qty))
                        new_asgn[role_k] = nv
                        rem_asgn[role_k] = rv
                    else:
                        new_asgn[role_k] = role_v
                        rem_asgn[role_k] = role_v

            new_job_oid = ObjectId()
            now = now_iso()

            # 1. Create NEW split job (inherits assignments, full history, split lineage)
            new_job_doc = dict(orig_job)
            new_job_doc["_id"] = new_job_oid
            new_job_doc["id"] = str(new_job_oid)
            new_job_doc["quantity"] = target_qty
            new_job_doc["completed_qty"] = new_comp
            new_job_doc["assignments"] = new_asgn
            new_job_doc["split_from_job_id"] = str(orig_job["_id"])
            new_job_doc["created_at"] = now
            new_job_doc["updated_at"] = now

            new_split_hist = list(orig_job.get("split_history") or [])
            new_split_hist.append({
                "event": "created_from_split",
                "from_job_id": str(orig_job["_id"]),
                "split_qty": target_qty,
                "at": now,
                "by": u.get("email", "system"),
            })
            new_job_doc["split_history"] = new_split_hist

            new_hist = list(orig_job.get("history") or [])
            new_hist.append({
                "event": "created_from_split",
                "from_job_id": str(orig_job["_id"]),
                "split_qty": target_qty,
                "at": now,
                "by": u.get("email", "system"),
                "notes": f"Split from job {orig_job['_id']} for partial dispatch of {target_qty} pairs",
            })
            new_job_doc["history"] = new_hist

            await db.production_jobs.insert_one(new_job_doc)

            # 2. Update ORIGINAL job (remains active in current stage with reduced quantity)
            orig_split_hist = list(orig_job.get("split_history") or [])
            orig_split_hist.append({
                "event": "split",
                "split_to_job_id": str(new_job_oid),
                "split_qty": target_qty,
                "remaining_qty": rem_qty,
                "at": now,
                "by": u.get("email", "system"),
            })
            orig_hist = list(orig_job.get("history") or [])
            orig_hist.append({
                "event": "split",
                "at": now,
                "by": u.get("email", "system"),
                "notes": f"Partial dispatch split: {target_qty} pairs split to job {new_job_oid}, {rem_qty} pairs remaining",
            })

            await db.production_jobs.update_one(
                {"_id": orig_job["_id"]},
                {"$set": {
                    "quantity": rem_qty,
                    "completed_qty": rem_comp,
                    "assignments": rem_asgn,
                    "split_history": orig_split_hist,
                    "history": orig_hist,
                    "updated_at": now,
                }}
            )

            # 3. Reassign corresponding packed cartons to new_job_oid
            orig_cartons = await db.packing_cartons.find({"job_id": jid, "status": "packed"}).to_list(5000)
            allocated = 0
            for c in orig_cartons:
                c_q = c.get("qty", 0)
                if allocated + c_q <= target_qty or allocated < target_qty:
                    await db.packing_cartons.update_one(
                        {"_id": c["_id"]},
                        {"$set": {"job_id": str(new_job_oid)}}
                    )
                    allocated += c_q

            effective_job_ids.append(str(new_job_oid))
        else:
            effective_job_ids.append(jid)

    # 2. Load packed cartons
    carton_docs = await db.packing_cartons.find(
        {"job_id": {"$in": effective_job_ids}, "status": "packed"}
    ).sort([("size", 1), ("_id", 1)]).to_list(50000)

    if not carton_docs:
        raise HTTPException(400, "No packed cartons found for these jobs — run QC Pack first")

    cartons = [stringify(c) for c in carton_docs]

    # 3. Assign box_number 1..N
    for idx, c in enumerate(cartons):
        c["box_number"] = idx + 1

    cartons = await _enrich_cartons_with_mapped_sku(cartons, db=db)

    # 4. Build line items from packed qty
    po_items = po.get("line_items", [])
    qty_agg: dict = {}
    for c in cartons:
        sc = (c.get("style_code") or "").strip()
        color = (c.get("color") or "").strip()
        key = (sc, color)
        if key not in qty_agg:
            li_src = next((li for li in po_items if (li.get("style_code") or "").strip() == sc and (li.get("color") or "").strip() == color), {})
            desc = (li_src.get("description") or "").strip()
            clean_desc = re.sub(r'(\s+\d+|\s*/?\s*Sz\s*\d+)+$', '', desc, flags=re.IGNORECASE).strip()
            qty_agg[key] = {
                "style_code": sc,
                "color": color,
                "qty": 0,
                "unit_price": float(li_src.get("unit_price") or 0),
                "description": clean_desc,
                "hsn_code": li_src.get("hsn_code") or "64029990",
                "mrp": li_src.get("mrp", ""),
            }
        qty_agg[key]["qty"] += (c.get("qty") or 0)

    line_items = [
        {
            "style_code": v["style_code"],
            "description": v["description"],
            "color": v["color"],
            "hsn_code": v["hsn_code"],
            "quantity": v["qty"],
            "unit_price": v["unit_price"],
            "amount": round(v["qty"] * v["unit_price"], 2),
            "mrp": v["mrp"],
        }
        for v in qty_agg.values()
        if v["qty"] > 0
    ]

    if not line_items:
        raise HTTPException(400, "No packed quantities found — carton rows may have 0 qty")

    # 5. Invoice PDF
    existing_inv = await db.invoices.find_one({"job_ids": {"$in": effective_job_ids}})
    if existing_inv and existing_inv.get("invoice_no"):
        invoice_no = existing_inv["invoice_no"]
        invoice_date = existing_inv.get("invoice_date") or datetime.now().strftime("%d/%m/%Y")
    else:
        invoice_no = await next_invoice_no(db=db)
        invoice_date = datetime.now().strftime("%d/%m/%Y")
    invoice_pdf = build_invoice(
        po, invoice_no, invoice_date,
        transport_mode=payload.transport_mode or "",
        vehicle_no=payload.vehicle_no or "",
        supply_date=payload.supply_date or "",
        line_items=line_items,
    )

    # 6. Packing list XLSX
    total_qty = sum(li["quantity"] for li in line_items)
    total_cartons = len(cartons)
    payload_po = dict(po)
    payload_po["line_items"] = line_items
    payload_po["total_quantity"] = total_qty
    payload_po["total_cartons"] = total_cartons
    payload_po["po_number"] = po.get("po_number", "")

    pl_options = {
        "carton_dim": payload.carton_dim or "60x50x30 CMS",
        "pcs_per_box": None,
        "net_wt_per_carton": payload.net_wt_per_carton or "",
        "gross_wt_per_carton": payload.gross_wt_per_carton or "",
        "dispatch_date": payload.dispatch_date or "",
        "transporter": payload.transporter or "",
        "vehicle_no": payload.vehicle_no or "",
        "driver_name": payload.driver_name or "",
        "driver_phone": payload.driver_phone or "",
        "site_code": payload.site_code or "",
        "destination": payload.destination or "",
        "port": payload.port or "",
        "notes": payload.notes or "",
    }
    packing_xlsx = await _generate_packing_bytes(payload_po, pl_options, payload.template_id, cartons=cartons, invoice_no=invoice_no, db=db)

    total_cartons = len(cartons)
    for c in cartons:
        c["total_cartons"] = total_cartons

    # 7. Carton Labels PDF & Carton List Excel
    labels_pdf = build_carton_labels(cartons, po.get("po_number", ""), invoice_no)
    carton_list_xlsx = build_carton_list_xlsx(cartons, po, invoice_no, pl_options)

    # 8. Store invoice record
    totals = _compute_invoice_totals(po, line_items)
    credit_days = _extract_credit_days(po.get("payment_terms", ""))
    inv_doc = {
        "invoice_no": invoice_no,
        "invoice_date": invoice_date,
        "invoice_iso_date": _invoice_iso_date(invoice_date),
        "due_date": None,
        "payment_terms_days": credit_days,
        "grn_date": None,
        "grn_recorded": False,
        "po_id": payload.po_id,
        "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")],
        "client_name": po.get("client_name"),
        "job_ids": effective_job_ids,
        "line_items_snapshot": line_items,
        **totals,
        "transport_mode": payload.transport_mode,
        "vehicle_no": payload.vehicle_no,
        "supply_date": payload.supply_date,
        "by": u["email"],
        "created_at": now_iso(),
        "file_b64": base64.b64encode(invoice_pdf).decode("ascii"),
        "merged": False,
    }
    inv_res = await db.invoices.insert_one(inv_doc)
    invoice_id = str(inv_res.inserted_id)

    # 9. Persist carton updates
    for c in cartons:
        await db.packing_cartons.update_one(
            {"_id": oid(c["id"])},
            {"$set": {
                "status": "dispatched",
                "invoice_id": invoice_id,
                "box_number": c["box_number"],
            }},
        )

    # 10. Persist dispatch_record
    snapshot = [
        {
            "box_number": c["box_number"],
            "ean_code": c.get("ean_code"),
            "qty": c.get("qty"),
            "size": c.get("size"),
            "color": c.get("color"),
            "style_code": c.get("style_code"),
            "style_id": c.get("style_id"),
            "job_id": c.get("job_id"),
        }
        for c in cartons
    ]
    dispatch_doc = {
        "invoice_id": invoice_id,
        "invoice_no": invoice_no,
        "dispatched_at": now_iso(),
        "dispatched_by": u["email"],
        "client_name": po.get("client_name"),
        "po_ids": [payload.po_id],
        "po_numbers": [po.get("po_number", "")],
        "job_ids": effective_job_ids,
        "packing_cartons_snapshot": snapshot,
        "total_cartons": total_cartons,
        "total_qty": total_qty,
        "invoice_file_b64": base64.b64encode(invoice_pdf).decode("ascii"),
        "packing_list_file_b64": base64.b64encode(packing_xlsx).decode("ascii"),
        "carton_labels_file_b64": base64.b64encode(labels_pdf).decode("ascii"),
        "carton_list_file_b64": base64.b64encode(carton_list_xlsx).decode("ascii"),
    }
    dr_res = await db.dispatch_records.insert_one(dispatch_doc)
    dispatch_record_id = str(dr_res.inserted_id)

    # 11. Advance job stages
    await _flag_jobs(effective_job_ids, "invoice_generated_at", db=db)

    # 12. ZIP all documents
    date_tag = datetime.now().strftime("%Y%m%d-%H%M")
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"Invoice-{invoice_no}.pdf", invoice_pdf)
        zf.writestr(f"PackingList-{invoice_no}-{date_tag}.xlsx", packing_xlsx)
        zf.writestr(f"CartonLabels-{invoice_no}.pdf", labels_pdf)
        zf.writestr(f"CartonList-{invoice_no}-{date_tag}.xlsx", carton_list_xlsx)
    zip_buf.seek(0)

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="Dispatch-{invoice_no}-{date_tag}.zip"',
            "X-Dispatch-Record-Id": dispatch_record_id,
            "X-Invoice-No": invoice_no,
        },
    )


@invoice_packing_router.get("/dispatch-records")
async def list_dispatch_records(
    request: Request,
    client: Optional[str] = None,
    po_number: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 200,
):
    """List all dispatch records (file bytes excluded for size)."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    if po_number:
        q["po_numbers"] = {"$elemMatch": {"$regex": re.escape(po_number), "$options": "i"}}
    if job_id:
        q["job_ids"] = job_id
    proj = {
        "invoice_file_b64": 0,
        "packing_list_file_b64": 0,
        "carton_labels_file_b64": 0,
        "carton_list_file_b64": 0,
    }
    docs = await db.dispatch_records.find(q, proj).sort("dispatched_at", -1).to_list(limit)
    return [stringify(d) for d in docs]


@invoice_packing_router.get("/dispatch-records/{dr_id}")
async def get_dispatch_record(dr_id: str, request: Request):
    """Full dispatch record detail (excludes file bytes)."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.dispatch_records.find_one(
        {"_id": oid(dr_id)},
        {"invoice_file_b64": 0, "packing_list_file_b64": 0, "carton_labels_file_b64": 0, "carton_list_file_b64": 0},
    )
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    return stringify(doc)


@invoice_packing_router.get("/dispatch-records/{dr_id}/invoice", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_invoice(dr_id: str, request: Request):
    """Re-download the invoice PDF exactly as generated at dispatch time."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"invoice_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = base64.b64decode(doc.get("invoice_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Invoice file not stored for this record")
    inv_no = doc.get("invoice_no", "invoice")
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Invoice-{inv_no}.pdf"'},
    )


@invoice_packing_router.get("/dispatch-records/{dr_id}/packing-list", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_packing_list(dr_id: str, request: Request):
    """Re-download the packing list XLSX as generated at dispatch time."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"packing_list_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = base64.b64decode(doc.get("packing_list_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Packing list file not stored for this record")
    inv_no = doc.get("invoice_no", "dispatch")
    return StreamingResponse(
        BytesIO(raw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="PackingList-{inv_no}.xlsx"'},
    )


@invoice_packing_router.get("/dispatch-records/{dr_id}/carton-labels", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_carton_labels(dr_id: str, request: Request):
    """Re-download the carton labels PDF as generated at dispatch time."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"carton_labels_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = base64.b64decode(doc.get("carton_labels_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Carton labels file not stored for this record")
    inv_no = doc.get("invoice_no", "dispatch")
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CartonLabels-{inv_no}.pdf"'},
    )


@invoice_packing_router.get("/dispatch-records/{dr_id}/carton-list", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_carton_list(dr_id: str, request: Request):
    """Re-download the carton list XLSX as generated at dispatch time."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"carton_list_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = base64.b64decode(doc.get("carton_list_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Carton list file not stored for this record")
    inv_no = doc.get("invoice_no", "dispatch")
    return StreamingResponse(
        BytesIO(raw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="CartonList-{inv_no}.xlsx"'},
    )


@invoice_packing_router.post("/dispatch-records/{dr_id}/reprint", dependencies=[Depends(pdf_rate_limiter)])
async def reprint_dispatch_zip(dr_id: str, request: Request):
    """Re-download all dispatch documents as a ZIP (for reprinting)."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    inv_no = doc.get("invoice_no", "dispatch")
    invoice_pdf = base64.b64decode(doc.get("invoice_file_b64") or "")
    packing_xlsx = base64.b64decode(doc.get("packing_list_file_b64") or "")
    labels_pdf = base64.b64decode(doc.get("carton_labels_file_b64") or "")
    carton_list_xlsx = base64.b64decode(doc.get("carton_list_file_b64") or "")
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if invoice_pdf:
            zf.writestr(f"Invoice-{inv_no}.pdf", invoice_pdf)
        if packing_xlsx:
            zf.writestr(f"PackingList-{inv_no}.xlsx", packing_xlsx)
        if labels_pdf:
            zf.writestr(f"CartonLabels-{inv_no}.pdf", labels_pdf)
        if carton_list_xlsx:
            zf.writestr(f"CartonList-{inv_no}.xlsx", carton_list_xlsx)
    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Reprint-{inv_no}.zip"'},
    )


# ── Packing Lists & Templates ─────────────────────────────────────────────
@invoice_packing_router.post("/packing-lists/job", dependencies=[Depends(pdf_rate_limiter)])
async def generate_packing_list(payload: PackingListGenerate, request: Request):
    """Generate a packing-list xlsx for a single PO (optionally filtered by jobs)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)
    payload_po = await _build_packing_payload(po, payload.job_ids, db=db)
    options = _packing_options_from_payload(payload)
    cartons = await db.packing_cartons.find({"job_id": {"$in": [oid(j) for j in payload.job_ids or []]}}).sort([("box_number", 1), ("_id", 1)]).to_list(1000)
    cartons = [stringify(c) for c in cartons] if cartons else None
    xlsx_bytes = await _generate_packing_bytes(payload_po, options, payload.template_id, cartons=cartons, db=db)

    rec = {
        "po_id": payload.po_id, "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")],
        "client_name": po.get("client_name"),
        "job_ids": payload.job_ids or [],
        "template_id": payload.template_id,
        "options": options, "by": u["email"], "created_at": now_iso(),
        "file_b64": base64.b64encode(xlsx_bytes).decode("ascii"),
        "merged": False,
    }
    res = await db.packing_lists.insert_one(rec)
    await _flag_jobs(payload.job_ids or [], "packing_generated_at", db=db)

    fname = f"PackingList-{po.get('po_number','po')}-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Packing-List-Id": str(res.inserted_id),
        },
    )


@invoice_packing_router.post("/packing-lists/merged", dependencies=[Depends(pdf_rate_limiter)])
async def generate_merged_packing_list(payload: MergedPackingListGenerate, request: Request):
    """Generate ONE packing list covering jobs from multiple POs of the same client."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    if not payload.job_ids:
        raise HTTPException(400, "Provide job_ids to merge")
    jobs = await db.production_jobs.find({"_id": {"$in": [oid(j) for j in payload.job_ids]}}).to_list(2000)
    if not jobs:
        raise HTTPException(404, "No jobs found")
    po_ids = list({j.get("po_id") for j in jobs if j.get("po_id")})
    po_docs = await db.pos.find({"_id": {"$in": [oid(p) for p in po_ids]}}).to_list(200)
    if not po_docs:
        raise HTTPException(404, "No POs found for these jobs")
    po_docs = [stringify(p) for p in po_docs]

    po_numbers = [p.get("po_number", "") for p in po_docs]
    if len(set([p for p in po_numbers if p])) > 1:
        raise HTTPException(400, "Cannot merge packing lists across different POs")
    parent = po_docs[0]

    job_ids_str = [str(j["_id"]) for j in jobs]
    all_items: list[dict] = []
    for p in po_docs:
        _, items = await _generate_invoice_payload(p, job_ids_str, db=db)
        if payload.sectioned:
            for it in items:
                it["_po_number"] = p.get("po_number", "")
        all_items.extend(items)

    payload_po = dict(parent)
    payload_po["line_items"] = all_items
    payload_po["total_quantity"] = sum((li.get("quantity") or 0) for li in all_items)
    payload_po["po_number"] = " + ".join(po_numbers)

    options = _packing_options_from_payload(payload)
    cartons = await db.packing_cartons.find({"job_id": {"$in": [oid(j) for j in job_ids_str]}}).sort([("box_number", 1), ("_id", 1)]).to_list(1000)
    cartons = [stringify(c) for c in cartons] if cartons else None
    xlsx_bytes = await _generate_packing_bytes(payload_po, options, payload.template_id, cartons=cartons, db=db)

    rec = {
        "merged": True, "po_numbers": po_numbers, "client_name": parent.get("client_name"),
        "job_ids": job_ids_str, "template_id": payload.template_id,
        "options": options, "by": u["email"], "created_at": now_iso(),
        "file_b64": base64.b64encode(xlsx_bytes).decode("ascii"),
    }
    res = await db.packing_lists.insert_one(rec)
    await _flag_jobs(job_ids_str, "packing_generated_at", db=db)

    fname = f"PackingList-MERGED-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Packing-List-Id": str(res.inserted_id),
        },
    )


@invoice_packing_router.get("/packing-lists")
async def list_packing_lists(request: Request, po_id: Optional[str] = None,
                             client: Optional[str] = None, limit: int = 200):
    """List saved packing lists. Optional filters: by po_id or client_name."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if po_id:
        q["po_id"] = po_id
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    docs = await db.packing_lists.find(q, {"file_b64": 0}).sort("created_at", -1).to_list(limit)
    return [stringify(d) for d in docs]


@invoice_packing_router.get("/packing-lists/{plid}/file", dependencies=[Depends(pdf_rate_limiter)])
async def download_packing_list(plid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.packing_lists.find_one({"_id": oid(plid)})
    if not doc:
        raise HTTPException(404, "Packing list not found")
    raw = base64.b64decode(doc.get("file_b64", "") or b"")
    if not raw:
        raise HTTPException(404, "File not stored for this entry")
    label = "MERGED" if doc.get("merged") else doc.get("po_number", "po")
    fname = doc.get("filename") or f"packing_list_{label}.xlsx"
    return StreamingResponse(
        BytesIO(raw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@invoice_packing_router.post("/packing-list/preview")
async def preview_packing_list(payload: dict, request: Request):
    """Generate structured JSON preview of the packing list for pre-generation verification."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    po_id = payload.get("po_id")
    po_doc = None
    if po_id:
        po_doc = await db.pos.find_one({"_id": oid(po_id)})
    if not po_doc:
        po_doc = payload.get("po") or {}

    po = stringify(po_doc) if po_doc else {}
    line_items = po.get("line_items", [])

    pcs_per_box = int(payload.get("pcs_per_box") or 20)
    net_wt_unit = float(payload.get("net_wt_per_carton") or 10.8)
    gross_wt_unit = float(payload.get("gross_wt_per_carton") or 12.0)
    carton_dim = payload.get("carton_dim") or po.get("carton_dim") or "60x50x30 CMS"

    agg = {}
    for li in line_items:
        st = str(li.get("style_code") or "").strip()
        co = str(li.get("color") or "").strip()
        slot = agg.setdefault((st, co), {"style": st, "color": co, "by_size": {s: 0 for s in DEFAULT_SIZES}, "total": 0})
        sz = str(li.get("size") or "").strip()
        q = int(li.get("quantity") or 0)
        if sz in slot["by_size"]:
            slot["by_size"][sz] += q
        slot["total"] += q

    rows = []
    total_pcs = 0
    total_cartons = 0
    total_net_wt = 0.0
    total_gross_wt = 0.0
    ctn_seq = 1

    for (st, co), rec in agg.items():
        n_boxes = max(1, (rec["total"] + pcs_per_box - 1) // pcs_per_box)
        c_range = f"{ctn_seq}-{ctn_seq + n_boxes - 1}" if n_boxes > 1 else str(ctn_seq)
        r_net = round(n_boxes * net_wt_unit, 3)
        r_gross = round(n_boxes * gross_wt_unit, 3)

        rows.append({
            "site_code": po.get("site_code") or "ZC_BLR-WH",
            "style": st,
            "color": co,
            "carton_no": c_range,
            "by_size": rec["by_size"],
            "pcs_per_carton": rec["total"],
            "per_carton": pcs_per_box,
            "total_cartons": n_boxes,
            "total_pcs": rec["total"],
            "net_weight": r_net,
            "gross_weight": r_gross,
        })
        ctn_seq += n_boxes
        total_pcs += rec["total"]
        total_cartons += n_boxes
        total_net_wt += r_net
        total_gross_wt += r_gross

    order_qty_map = {s: 0 for s in DEFAULT_SIZES}
    for li in line_items:
        sz = str(li.get("size") or "").strip()
        if sz in order_qty_map:
            order_qty_map[sz] += int(li.get("quantity") or 0)

    pack_qty_map = {s: 0 for s in DEFAULT_SIZES}
    for r in rows:
        for s in DEFAULT_SIZES:
            pack_qty_map[s] += r["by_size"].get(s, 0)

    excess_short_map = {s: pack_qty_map[s] - order_qty_map[s] for s in DEFAULT_SIZES}
    excess_short_pct_map = {}
    for s in DEFAULT_SIZES:
        ord_q = order_qty_map[s]
        excess_short_pct_map[s] = f"{((excess_short_map[s] / ord_q) * 100):.2f}%" if ord_q > 0 else "0.00%"

    tot_order = sum(order_qty_map.values())
    tot_pack = sum(pack_qty_map.values())
    tot_diff = tot_pack - tot_order
    tot_diff_pct = f"{((tot_diff / tot_order) * 100):.2f}%" if tot_order > 0 else "0.00%"

    return {
        "vendor": VENDOR,
        "destination": {
            "name": po.get("client_name") or "ZECODE-BANGLORE-2220 ZECODE-BANGLORE-2220",
            "address": po.get("client_address") or po.get("shipping_address") or "PLOT NO. 2J/2K, 3RD PHASE KIADB OBEDENAHALLI INDUSTRIAL AREA BANGLORE, KARNATAKA DODDABALLAPUR 561 BENGALURU KARNATAKA 561203",
            "gstin": po.get("client_gstin") or "29AAACS6995D2ZX",
        },
        "po": {
            "po_number": po.get("po_number", ""),
            "po_date": po.get("po_date", ""),
            "total_pcs": total_pcs,
            "total_cartons": total_cartons,
            "carton_dimension": carton_dim,
        },
        "sizes": DEFAULT_SIZES,
        "rows": rows,
        "grand_total": {
            "size_totals": pack_qty_map,
            "total_cartons": total_cartons,
            "total_pcs": total_pcs,
            "net_weight": round(total_net_wt, 3),
            "gross_weight": round(total_gross_wt, 3),
        },
        "order_summary": {
            "order_qty": order_qty_map,
            "pack_qty": pack_qty_map,
            "excess_short": excess_short_map,
            "excess_short_pct": excess_short_pct_map,
            "total_order_qty": tot_order,
            "total_pack_qty": tot_pack,
            "total_excess_short": tot_diff,
            "total_excess_short_pct": tot_diff_pct,
        }
    }


@invoice_packing_router.post("/packing-list/validate")
async def validate_packing_list(payload: dict, request: Request):
    """Validate packing list inputs before generation."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    errors = []

    po_id = payload.get("po_id")
    po_doc = None
    if po_id:
        po_doc = await db.pos.find_one({"_id": oid(po_id)})
    if not po_doc:
        po_doc = payload.get("po")
    if not po_doc:
        errors.append("PO not found or invalid PO data.")

    if po_doc:
        line_items = po_doc.get("line_items", [])
        if not line_items:
            errors.append("PO has no line items.")
        for idx, li in enumerate(line_items):
            qty = li.get("quantity")
            if qty is None or int(qty) < 0:
                errors.append(f"Line item #{idx+1} has invalid quantity: {qty}")
            if not li.get("style_code"):
                errors.append(f"Line item #{idx+1} missing style code.")

    carton_dim = payload.get("carton_dim") or (po_doc.get("carton_dim") if po_doc else None) or "60x50x30 CMS"
    if not carton_dim or not str(carton_dim).strip():
        errors.append("Carton dimension is required.")

    return {"valid": len(errors) == 0, "errors": errors}


@invoice_packing_router.get("/pos/{pid}/packing-list.pdf")
async def get_po_packing_list_pdf(pid: str, request: Request):
    """Generate and stream PDF packing list for a PO matching master visual reference PDF."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    po_doc = await db.pos.find_one({"_id": oid(pid)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)
    pdf_bytes = build_packing_list_pdf(po)
    fname = f"PackingList-{po.get('po_number','po')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'}
    )


@invoice_packing_router.get("/pos/{pid}/packing-list.xlsx")
async def get_po_packing_list_xlsx(pid: str, request: Request):
    """Generate and stream Excel packing list for a PO matching master visual reference PDF."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    po_doc = await db.pos.find_one({"_id": oid(pid)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)
    xlsx_bytes = build_default_packing_list(po)
    fname = f"PackingList-{po.get('po_number','po')}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )


@invoice_packing_router.get("/packing-templates")
async def list_packing_templates(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    docs = await db.packing_templates.find({}, {"file_b64": 0}).to_list(200)
    return [stringify(d) for d in docs]


@invoice_packing_router.post("/packing-templates")
async def create_packing_template(payload: PackingTemplateIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    try:
        raw = base64.b64decode(payload.file_b64.split(",", 1)[-1] if "," in payload.file_b64 else payload.file_b64)
        import openpyxl as _ox
        _ox.load_workbook(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, f"Invalid xlsx file: {e}")

    doc = {
        "client_name": payload.client_name.strip(),
        "name": payload.name.strip(),
        "aliases": [a.strip() for a in (payload.aliases or []) if a and a.strip()],
        "file_b64": payload.file_b64,
        "by": u["email"],
        "created_at": now_iso(),
    }
    res = await db.packing_templates.insert_one(doc)
    doc["_id"] = res.inserted_id
    safe = stringify(doc)
    safe.pop("file_b64", None)
    await log_activity("create_packing_template", "settings", f"Created packing template: {payload.name}", u["email"], db=db)
    return safe


@invoice_packing_router.delete("/packing-templates/{tid}")
async def delete_packing_template(tid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    t = await db.packing_templates.find_one({"_id": oid(tid)})
    if not t:
        raise HTTPException(404, "Template not found")
    await db.packing_templates.delete_one({"_id": oid(tid)})
    await log_activity("delete_packing_template", "settings", f"Deleted packing template: {t.get('name')}", u["email"], db=db)
    return {"ok": True}
