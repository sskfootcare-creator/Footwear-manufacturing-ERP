"""Vendors, Vendor Purchase Orders, Material Receiving, Payments & AP Aging Routes."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from models.vendors import (
    VendorIn,
    VendorUpdate,
    VendorPOIn,
    VendorPOUpdate,
    VendorPOReceiveIn,
    PaymentIn,
)
from auth import require_roles

vendors_router = APIRouter(prefix="/api", tags=["Vendors & Accounts Payable"])


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


async def next_payment_no(db) -> str:
    seq = await db.counters.find_one_and_update(
        {"_id": "payment_seq"}, {"$inc": {"v": 1}}, upsert=True, return_document=True,
    )
    n = (seq or {}).get("v", 1)
    return f"RCT-{datetime.now().year}-{n:04d}"


async def next_vendor_po_no(db) -> str:
    seq = await db.counters.find_one_and_update(
        {"_id": "vendor_po_seq"}, {"$inc": {"v": 1}}, upsert=True, return_document=True,
    )
    n = (seq or {}).get("v", 1)
    return f"PO-VEN-{datetime.now().year}-{n:04d}"


# ---------- VENDOR LEDGER & AGEING (Accounts Payable) ----------

async def _build_vendor_ledger(db, vid: str) -> dict:
    vendor = await db.vendors.find_one({"_id": oid(vid)})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    
    vendor_name = vendor.get("name", "")
    terms_days = vendor.get("payment_terms_days", 30)

    # 1. Fetch receives for this vendor
    rec_docs = await db.vendor_po_receives.find({"vendor_id": vid}).to_list(5000)
    seen_receipt_ids = {r.get("receipt_id") for r in rec_docs if r.get("receipt_id")}

    pos = await db.vendor_purchase_orders.find({"vendor_id": vid}).to_list(2000)
    po_id_map = {str(p["_id"]): p.get("po_number") for p in pos}
    po_ids = list(po_id_map.keys())

    movements = await db.inventory_movements.find({
        "type": "in",
        "$or": [
            {"vendor_po_id": {"$in": po_ids}},
            {"party": vendor_name}
        ]
    }).to_list(5000)

    mov_grouped = defaultdict(list)
    for m in movements:
        rid = m.get("receipt_id") or str(m["_id"])
        if rid not in seen_receipt_ids:
            mov_grouped[rid].append(m)

    receives_list = []
    for r in rec_docs:
        receives_list.append({
            "type": "receive",
            "date": r.get("receipt_date") or str(r.get("created_at", ""))[:10],
            "created_at": r.get("created_at", ""),
            "reference": r.get("receipt_id") or r.get("po_number") or "GRN",
            "po_number": r.get("po_number", ""),
            "description": f"Material Receipt (PO: {r.get('po_number', 'N/A')})",
            "credit": round(float(r.get("total_amount", 0)), 2),
            "debit": 0.0,
            "items": r.get("items", []),
        })

    for rid, m_list in mov_grouped.items():
        tot_amt = sum(float(m.get("quantity", 0)) * float(m.get("rate", 0)) for m in m_list)
        first_m = m_list[0]
        po_num = po_id_map.get(first_m.get("vendor_po_id"), "")
        receives_list.append({
            "type": "receive",
            "date": first_m.get("date") or str(first_m.get("created_at", ""))[:10],
            "created_at": first_m.get("created_at", ""),
            "reference": rid,
            "po_number": po_num,
            "description": f"Material Receipt (PO: {po_num or 'N/A'})",
            "credit": round(tot_amt, 2),
            "debit": 0.0,
            "items": [
                {
                    "material_id": m.get("material_id"),
                    "material_name": m.get("material_name"),
                    "quantity": m.get("quantity"),
                    "rate": m.get("rate"),
                    "amount": round(float(m.get("quantity", 0)) * float(m.get("rate", 0)), 2),
                }
                for m in m_list
            ]
        })

    # 2. Fetch payments for this vendor
    pay_docs = await db.payments.find({
        "$or": [
            {"vendor_id": vid},
            {"type": "vendor_payment", "vendor_name": vendor_name}
        ]
    }).to_list(5000)

    payments_list = []
    for p in pay_docs:
        amt = float(p.get("amount", 0))
        payments_list.append({
            "type": "payment",
            "date": p.get("payment_date") or str(p.get("created_at", ""))[:10],
            "created_at": p.get("created_at", ""),
            "reference": p.get("payment_no") or p.get("reference") or "PAYMENT",
            "description": f"Payment via {p.get('mode', 'Bank')} ({p.get('reference') or 'N/A'})",
            "credit": 0.0,
            "debit": round(amt, 2),
            "mode": p.get("mode"),
            "notes": p.get("notes", ""),
        })

    # 3. Combine & sort chronologically
    all_tx = receives_list + payments_list
    all_tx.sort(key=lambda x: (x["date"], x["created_at"]))

    running_bal = 0.0
    transactions = []
    for tx in all_tx:
        if tx["type"] == "receive":
            running_bal += tx["credit"]
        else:
            running_bal -= tx["debit"]
        running_bal = round(running_bal, 2)
        tx["running_balance"] = running_bal
        transactions.append(tx)

    tot_rec = round(sum(t["credit"] for t in receives_list), 2)
    tot_paid = round(sum(t["debit"] for t in payments_list), 2)
    cur_bal = round(tot_rec - tot_paid, 2)

    return {
        "vendor_id": vid,
        "vendor_name": vendor_name,
        "payment_terms_days": terms_days,
        "total_received": tot_rec,
        "total_paid": tot_paid,
        "current_balance": cur_bal,
        "transactions": transactions,
        "_receives": receives_list,
        "_payments": payments_list,
    }


def _compute_ageing_buckets(ledger_data: dict) -> dict:
    vid = ledger_data["vendor_id"]
    vname = ledger_data["vendor_name"]
    terms_days = ledger_data["payment_terms_days"]
    cur_bal = ledger_data["current_balance"]
    receives = ledger_data.get("_receives", [])

    current_date = datetime.now(timezone.utc).date()

    out = {
        "vendor_id": vid,
        "vendor_name": vname,
        "payment_terms_days": terms_days,
        "outstanding_balance": cur_bal,
        "current": 0.0,
        "days_1_30": 0.0,
        "days_31_60": 0.0,
        "days_60_plus": 0.0,
    }

    if cur_bal <= 0:
        return out

    receives_sorted = sorted(receives, key=lambda r: (r["date"], r.get("created_at", "")))
    tot_paid = ledger_data["total_paid"]

    rem_paid = tot_paid
    unpaid_receives = []
    for r in receives_sorted:
        c_amt = r["credit"]
        if rem_paid >= c_amt:
            rem_paid -= c_amt
        else:
            unpaid_amt = round(c_amt - rem_paid, 2)
            rem_paid = 0.0
            unpaid_receives.append({"date": r["date"], "amount": unpaid_amt})

    if not unpaid_receives and cur_bal > 0:
        out["current"] = round(cur_bal, 2)
        return out

    for ur in unpaid_receives:
        try:
            r_date = datetime.strptime(ur["date"][:10], "%Y-%m-%d").date()
            age_days = (current_date - r_date).days
        except Exception:
            age_days = 0

        amt = ur["amount"]
        if age_days <= 0:
            out["current"] = round(out["current"] + amt, 2)
        elif 1 <= age_days <= 30:
            out["days_1_30"] = round(out["days_1_30"] + amt, 2)
        elif 31 <= age_days <= 60:
            out["days_31_60"] = round(out["days_31_60"] + amt, 2)
        else:
            out["days_60_plus"] = round(out["days_60_plus"] + amt, 2)

    return out


# ---------- VENDORS CRUD ----------

@vendors_router.get("/vendors")
async def list_vendors(request: Request, include_inactive: bool = False, limit: int = 500):
    """Return all vendor master records. Default hides inactive vendors."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {} if include_inactive else {"active": {"$ne": False}}
    docs = await db.vendors.find(q).sort("name", 1).to_list(limit)
    return [stringify(d) for d in docs]


@vendors_router.post("/vendors", status_code=201)
async def create_vendor(payload: VendorIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = {
        **payload.model_dump(),
        "by": u.get("email") or u.get("name", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    try:
        res = await db.vendors.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"A vendor named '{payload.name}' already exists.")
    doc["_id"] = res.inserted_id
    await log_activity_db(db, "create_vendor", "vendors", f"Created vendor '{payload.name}'", u.get("email", ""))
    return stringify(doc)


@vendors_router.get("/vendors/ageing")
async def get_all_vendors_ageing(request: Request, include_inactive: bool = False):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {} if include_inactive else {"active": {"$ne": False}}
    vendors = await db.vendors.find(q).sort("name", 1).to_list(1000)
    
    records = []
    total_outstanding = 0.0
    total_current = 0.0
    total_1_30 = 0.0
    total_31_60 = 0.0
    total_60_plus = 0.0

    for v in vendors:
        vid = str(v["_id"])
        ledger = await _build_vendor_ledger(db, vid)
        ageing = _compute_ageing_buckets(ledger)
        records.append(ageing)

        total_outstanding += ageing["outstanding_balance"]
        total_current += ageing["current"]
        total_1_30 += ageing["days_1_30"]
        total_31_60 += ageing["days_31_60"]
        total_60_plus += ageing["days_60_plus"]

    return {
        "summary": {
            "total_vendors": len(records),
            "total_outstanding": round(total_outstanding, 2),
            "total_current": round(total_current, 2),
            "total_days_1_30": round(total_1_30, 2),
            "total_days_31_60": round(total_31_60, 2),
            "total_days_60_plus": round(total_60_plus, 2),
        },
        "vendors": records
    }

@vendors_router.get("/vendors/{vid}/ledger")
async def get_vendor_ledger(vid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    ledger = await _build_vendor_ledger(db, vid)
    ledger.pop("_receives", None)
    ledger.pop("_payments", None)
    return ledger


@vendors_router.post("/vendors/{vid}/payments", status_code=201)
async def create_vendor_payment(vid: str, payload: PaymentIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    vendor = await db.vendors.find_one({"_id": oid(vid)})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    payment_no = await next_payment_no(db)
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
        "by": u.get("email") or u.get("name", ""),
        "created_at": now_iso(),
    }
    res = await db.payments.insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_activity_db(db, "create_vendor_payment", "vendor_payments", f"Created Vendor Payment '{payment_no}' of ₹{payload.amount} for {vendor.get('name')}", u.get("email", ""))
    return stringify(doc)


@vendors_router.get("/vendors/{vid}")
async def get_vendor(vid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.vendors.find_one({"_id": oid(vid)})
    if not doc:
        raise HTTPException(404, "Vendor not found")
    return stringify(doc)


@vendors_router.patch("/vendors/{vid}")
async def update_vendor(vid: str, payload: VendorUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    updates["updated_at"] = now_iso()
    r = await db.vendors.update_one({"_id": oid(vid)}, {"$set": updates})
    if not r.matched_count:
        raise HTTPException(404, "Vendor not found")
    doc = await db.vendors.find_one({"_id": oid(vid)})
    await log_activity_db(db, "update_vendor", "vendors", f"Updated vendor id={vid}", u.get("email", ""))
    return stringify(doc)


@vendors_router.delete("/vendors/{vid}")
async def deactivate_vendor(vid: str, request: Request):
    """Soft-delete: sets active=False to preserve AP history."""
    u = await _get_user(request)
    require_roles("admin")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.vendors.find_one({"_id": oid(vid)})
    if not doc:
        raise HTTPException(404, "Vendor not found")
    await db.vendors.update_one({"_id": oid(vid)}, {"$set": {"active": False, "updated_at": now_iso()}})
    await log_activity_db(db, "deactivate_vendor", "vendors", f"Deactivated vendor '{doc.get('name')}'", u.get("email", ""))
    return {"ok": True}


# ---------- VENDOR PURCHASE ORDERS ----------

@vendors_router.get("/vendor-pos")
async def list_vendor_pos(request: Request, vendor_id: Optional[str] = None, status: Optional[str] = None, limit: int = 500):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q: dict = {}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if status:
        q["status"] = status
    docs = await db.vendor_purchase_orders.find(q).sort("created_at", -1).to_list(limit)
    
    vendors = await db.vendors.find({}).to_list(2000)
    vendor_map = {str(v["_id"]): v.get("name", "") for v in vendors}
    
    out = []
    for d in docs:
        d = stringify(d)
        d["vendor_name"] = vendor_map.get(d.get("vendor_id", ""), "Unknown Vendor")
        for li in d.get("line_items", []):
            if "received_quantity" not in li:
                li["received_quantity"] = 0.0
        out.append(d)
    return out


@vendors_router.post("/vendor-pos", status_code=201)
async def create_vendor_po(payload: VendorPOIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    vendor = await db.vendors.find_one({"_id": oid(payload.vendor_id)})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
        
    po_no = await next_vendor_po_no(db)
    doc = {
        **payload.model_dump(),
        "po_number": po_no,
        "by": u.get("email") or u.get("name", ""),
        "processed_receipt_ids": [],
        "created_at": now_iso(),
        "updated_at": now_iso()
    }
    res = await db.vendor_purchase_orders.insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_activity_db(db, "create_vendor_po", "vendor_pos", f"Created Vendor PO '{po_no}'", u.get("email", ""))
    return stringify(doc)


@vendors_router.get("/vendor-pos/{id}")
async def get_vendor_po(id: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.vendor_purchase_orders.find_one({"_id": oid(id)})
    if not doc:
        raise HTTPException(404, "Vendor Purchase Order not found")
    vendor = await db.vendors.find_one({"_id": oid(doc.get("vendor_id"))})
    out = stringify(doc)
    out["vendor_name"] = vendor.get("name", "Unknown Vendor") if vendor else "Unknown Vendor"
    for li in out.get("line_items", []):
        if "received_quantity" not in li:
            li["received_quantity"] = 0.0
    return out


@vendors_router.patch("/vendor-pos/{id}")
async def update_vendor_po(id: str, payload: VendorPOUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    
    if "vendor_id" in updates:
        vendor = await db.vendors.find_one({"_id": oid(updates["vendor_id"])})
        if not vendor:
            raise HTTPException(404, "Vendor not found")

    updates["updated_at"] = now_iso()
    r = await db.vendor_purchase_orders.update_one({"_id": oid(id)}, {"$set": updates})
    if not r.matched_count:
        raise HTTPException(404, "Vendor Purchase Order not found")
        
    doc = await db.vendor_purchase_orders.find_one({"_id": oid(id)})
    await log_activity_db(db, "update_vendor_po", "vendor_pos", f"Updated Vendor PO id={id}", u.get("email", ""))
    return stringify(doc)


@vendors_router.post("/vendor-pos/{id}/receive")
async def receive_vendor_po(id: str, payload: VendorPOReceiveIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    
    po = await db.vendor_purchase_orders.find_one({"_id": oid(id)})
    if not po:
        raise HTTPException(404, "Vendor Purchase Order not found")
        
    receipt_id = payload.receipt_id
    processed = po.get("processed_receipt_ids") or []
    if receipt_id in processed:
        return stringify(po)
        
    vendor = await db.vendors.find_one({"_id": oid(po.get("vendor_id"))})
    vendor_name = vendor.get("name", "Unknown Vendor") if vendor else "Unknown Vendor"
    
    line_items = po.get("line_items") or []
    for li in line_items:
        if "received_quantity" not in li:
            li["received_quantity"] = 0.0
            
    li_map = {li["material_id"]: li for li in line_items}
    
    movements = []
    material_ids = [item.material_id for item in payload.items]
    materials_list = await db.materials.find({"_id": {"$in": [oid(mid) for mid in material_ids]}}).to_list(100)
    materials_map = {str(m["_id"]): m for m in materials_list}
    
    for item in payload.items:
        if item.material_id not in li_map:
            raise HTTPException(400, f"Material {item.material_id} is not in PO line items")
        if item.quantity <= 0:
            continue
            
        li = li_map[item.material_id]
        li["received_quantity"] = round(li["received_quantity"] + item.quantity, 4)
        
        mat = materials_map.get(item.material_id)
        if not mat:
            raise HTTPException(404, f"Material {item.material_id} not found in DB")
            
        movements.append({
            "material_id": item.material_id,
            "material_code": mat.get("code"),
            "material_name": mat.get("name"),
            "unit": mat.get("unit"),
            "type": "in",
            "quantity": item.quantity,
            "rate": li.get("rate") or mat.get("rate") or 0.0,
            "party": vendor_name,
            "vendor_po_id": str(po["_id"]),
            "receipt_id": receipt_id,
            "notes": f"Received against PO {po.get('po_number')}",
            "by": u.get("email") or u.get("name", ""),
            "date": payload.receipt_date or datetime.now(timezone.utc).date().isoformat(),
            "created_at": now_iso(),
            "auto": True
        })
        
    if movements:
        all_received = True
        any_received = False
        for li in line_items:
            req_qty = li.get("quantity", 0)
            rec_qty = li.get("received_quantity", 0)
            if rec_qty < req_qty:
                all_received = False
            if rec_qty > 0:
                any_received = True
                
        new_status = po.get("status", "draft")
        if all_received:
            new_status = "received"
        elif any_received:
            new_status = "partially_received"
            
        processed.append(receipt_id)
        
        await db.vendor_purchase_orders.update_one(
            {"_id": po["_id"]},
            {"$set": {
                "line_items": line_items,
                "status": new_status,
                "processed_receipt_ids": processed,
                "updated_at": now_iso()
            }}
        )
        await db.inventory_movements.insert_many(movements)
        for m in movements:
            try:
                mid = m.get("material_id")
                if mid:
                    import server
                    if hasattr(server, "_compute_material_inventory_summary"):
                        summary = await server._compute_material_inventory_summary(mid)
                        await db.materials.update_one(
                            {"_id": oid(mid)},
                            {"$set": {
                                "weighted_avg_rate": round(summary["weighted_avg_rate"], 2),
                                "last_purchase_rate": round(summary["last_rate"], 2),
                                "updated_at": now_iso(),
                            }}
                        )
            except Exception:
                pass
        total_receive_amount = sum(round(float(m["quantity"]) * float(m["rate"]), 2) for m in movements)

        receive_doc = {
            "vendor_id": str(po.get("vendor_id")),
            "vendor_po_id": str(po["_id"]),
            "po_number": po.get("po_number"),
            "receipt_id": receipt_id,
            "receipt_date": payload.receipt_date or datetime.now(timezone.utc).date().isoformat(),
            "items": [
                {
                    "material_id": m["material_id"],
                    "material_code": m["material_code"],
                    "material_name": m["material_name"],
                    "quantity": m["quantity"],
                    "rate": m["rate"],
                    "amount": round(float(m["quantity"]) * float(m["rate"]), 2),
                }
                for m in movements
            ],
            "total_amount": round(total_receive_amount, 2),
            "by": u.get("email") or u.get("name", ""),
            "created_at": now_iso(),
        }
        await db.vendor_po_receives.insert_one(receive_doc)
        po = await db.vendor_purchase_orders.find_one({"_id": po["_id"]})
        
    await log_activity_db(db, "receive_vendor_po", "vendor_pos", f"Received materials for PO {po.get('po_number')} (receipt: {receipt_id})", u.get("email", ""))
    return stringify(po)


@vendors_router.delete("/vendor-pos/{id}")
async def delete_vendor_po(id: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    r = await db.vendor_purchase_orders.delete_one({"_id": oid(id)})
    if not r.deleted_count:
        raise HTTPException(404, "Vendor Purchase Order not found")
    await log_activity_db(db, "delete_vendor_po", "vendor_pos", f"Deleted Vendor PO id={id}", u.get("email", ""))
    return {"ok": True}
