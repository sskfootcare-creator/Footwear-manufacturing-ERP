"""Enterprise ERP Reporting Suite Routes.
Provides high-performance aggregation endpoints for:
- Executive Total Business Summary
- Raw Materials & Inventory Valuation
- Production Line Throughput & WIP
- Invoices & Sales Performance
- Vendor Procurement & AP Aging
- Client Receivables & AR Aging
- Comprehensive P&L Statement
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from auth import require_roles

log = logging.getLogger(__name__)

reports_router = APIRouter(prefix="/api", tags=["Reports"])


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


def _get_db(request: Request):
    return getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")


# ── 1. EXECUTIVE / TOTAL BUSINESS SUMMARY ──────────────────────────────────────

@reports_router.get("/reports/business-summary")
async def report_business_summary(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    # 1. B2B Invoices Revenue & Receivables
    inv_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq: Dict[str, Any] = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        inv_query["$or"] = [
            {"invoice_date": dq},
            {"created_at": dq},
            {"invoice_iso_date": dq}
        ]

    invoices = await db.invoices.find(inv_query).to_list(10000)
    total_b2b_invoiced = sum(float(i.get("grand_total") or i.get("total_amount") or 0.0) for i in invoices)
    total_b2b_paid = sum(float(i.get("paid_amount") or 0.0) for i in invoices)
    total_b2b_balance = sum(float(i.get("balance_due") or (float(i.get("grand_total") or i.get("total_amount") or 0.0) - float(i.get("paid_amount") or 0.0))) for i in invoices)

    # 2. Online Revenue
    settle_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        settle_query["$or"] = [{"settlement_date": dq}, {"created_at": dq}]
    settlements = await db.online_settlements_detailed.find(settle_query).to_list(5000)
    if not settlements:
        settlements = await db.online_settlements.find(settle_query).to_list(5000)
    total_online_revenue = sum(float(s.get("net_payout") or s.get("settlement_value") or s.get("invoiced_amount") or 0.0) for s in settlements)

    gross_revenue = round(total_b2b_invoiced + total_online_revenue, 2)

    # 3. Vendor Procurement Spend & Payables
    po_query: Dict[str, Any] = {"status": {"$ne": "cancelled"}}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        po_query["created_at"] = dq

    vpos = await db.vendor_purchase_orders.find(po_query).to_list(10000)
    if not vpos:
        vpos = await db.vendor_pos.find(po_query).to_list(10000)

    total_procurement = sum(float(p.get("total_amount") or 0.0) for p in vpos)
    total_vendor_paid = sum(float(p.get("paid_amount") or 0.0) for p in vpos)
    total_vendor_balance = sum(float(p.get("balance_due") or (float(p.get("total_amount") or 0.0) - float(p.get("paid_amount") or 0.0))) for p in vpos)

    # 4. Labor Cost / Karigar Wages
    labor_cost = 0.0
    try:
        import server
        payroll_fn = getattr(server, "report_payroll", None)
        if payroll_fn:
            pres = await payroll_fn(request, from_date=from_date, to_date=to_date)
            if isinstance(pres, dict) and "rows" in pres:
                labor_cost = sum(float(r.get("total_earning", 0) or 0) for r in pres["rows"])
    except Exception as e:
        log.warning(f"Error computing labor cost: {e}")

    # 5. Operating Expenses
    exp_query: Dict[str, Any] = {"status": {"$nin": ["due", "overdue"]}}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date
        exp_query["date"] = dq

    expenses = await db.expenses.find(exp_query).to_list(10000)
    filtered_expenses = [
        e for e in expenses
        if str(e.get("category", "")).lower() not in ["raw materials", "labor", "wages"]
    ]
    total_operating_expenses = sum(float(e.get("amount") or 0.0) for e in filtered_expenses)

    # Net Operating Profit
    cogs = round(total_procurement + labor_cost, 2)
    gross_profit = round(gross_revenue - cogs, 2)
    gross_margin_pct = round((gross_profit / gross_revenue * 100), 2) if gross_revenue > 0 else 0.0
    net_profit = round(gross_profit - total_operating_expenses, 2)
    net_margin_pct = round((net_profit / gross_revenue * 100), 2) if gross_revenue > 0 else 0.0

    # 6. Liquid Funds (Bank & Cash Accounts)
    bank_accs = await db.bank_accounts.find({"active": True}).to_list(100)
    cash_accs = await db.cash_accounts.find({"active": True}).to_list(100)
    total_bank_balance = sum(float(b.get("current_balance") or 0.0) for b in bank_accs)
    total_cash_balance = sum(float(c.get("current_balance") or 0.0) for c in cash_accs)
    total_liquid_funds = round(total_bank_balance + total_cash_balance, 2)

    # 7. Production Pipeline
    jobs = await db.production_jobs.find({"archived": {"$ne": True}}).to_list(10000)
    pipeline_jobs_count = len(jobs)
    pipeline_pairs_count = sum(int(j.get("quantity") or 0) for j in jobs if j.get("stage") != "dispatched")
    dispatched_pairs_count = sum(int(j.get("quantity") or 0) for j in jobs if j.get("stage") == "dispatched")

    # 8. Raw Material Inventory Valuation
    materials = await db.materials.find({}).to_list(5000)
    inventory_valuation = sum(
        float(m.get("balance") or m.get("current_stock") or 0.0) * float(m.get("weighted_avg_rate") or m.get("rate") or 0.0)
        for m in materials
    )

    # 9. Monthly Financial Trend (Last 6 Months)
    monthly_map = defaultdict(lambda: {"revenue": 0.0, "procurement": 0.0, "expenses": 0.0, "profit": 0.0})
    for inv in invoices:
        m = str(inv.get("invoice_date") or inv.get("created_at") or "")[:7]
        if m:
            monthly_map[m]["revenue"] += float(inv.get("grand_total") or inv.get("total_amount") or 0.0)
    for po in vpos:
        m = str(po.get("created_at") or "")[:7]
        if m:
            monthly_map[m]["procurement"] += float(po.get("total_amount") or 0.0)
    for exp in filtered_expenses:
        m = str(exp.get("date") or "")[:7]
        if m:
            monthly_map[m]["expenses"] += float(exp.get("amount") or 0.0)

    for m, data in monthly_map.items():
        data["profit"] = round(data["revenue"] - (data["procurement"] + data["expenses"]), 2)
        data["revenue"] = round(data["revenue"], 2)
        data["procurement"] = round(data["procurement"], 2)
        data["expenses"] = round(data["expenses"], 2)

    monthly_trend = [{"month": k, **v} for k, v in sorted(monthly_map.items())][-6:]

    return {
        "gross_revenue": gross_revenue,
        "total_b2b_invoiced": round(total_b2b_invoiced, 2),
        "total_online_revenue": round(total_online_revenue, 2),
        "total_procurement": round(total_procurement, 2),
        "labor_cost": round(labor_cost, 2),
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "operating_expenses": round(total_operating_expenses, 2),
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
        "total_ar_receivables": round(total_b2b_balance, 2),
        "total_ap_payables": round(total_vendor_balance, 2),
        "total_liquid_funds": total_liquid_funds,
        "total_bank_balance": round(total_bank_balance, 2),
        "total_cash_balance": round(total_cash_balance, 2),
        "pipeline_jobs_count": pipeline_jobs_count,
        "pipeline_pairs_count": pipeline_pairs_count,
        "dispatched_pairs_count": dispatched_pairs_count,
        "inventory_valuation": round(inventory_valuation, 2),
        "monthly_trend": monthly_trend,
    }


# ── 2. RAW MATERIALS & INVENTORY VALUATION ──────────────────────────────────────

@reports_router.get("/reports/inventory-materials")
async def report_inventory_materials(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = _get_db(request)

    materials = await db.materials.find({}).to_list(10000)
    
    category_summary = defaultdict(lambda: {"items_count": 0, "total_stock": 0.0, "total_valuation": 0.0})
    material_rows = []
    total_valuation = 0.0
    low_stock_count = 0
    out_of_stock_count = 0

    for m in materials:
        stock = float(m.get("balance") or m.get("current_stock") or 0.0)
        rate = float(m.get("weighted_avg_rate") or m.get("rate") or 0.0)
        reorder = float(m.get("reorder_level") or m.get("min_stock") or 10.0)
        val = round(stock * rate, 2)
        total_valuation += val

        cat = m.get("category") or "General"
        category_summary[cat]["items_count"] += 1
        category_summary[cat]["total_stock"] += stock
        category_summary[cat]["total_valuation"] += val

        if stock <= 0:
            status = "Out of Stock"
            out_of_stock_count += 1
        elif stock <= reorder:
            status = "Low Stock"
            low_stock_count += 1
        else:
            status = "Adequate"

        material_rows.append({
            "id": str(m["_id"]),
            "code": m.get("code") or "—",
            "name": m.get("name") or "Unnamed Material",
            "category": cat,
            "unit": m.get("unit") or "units",
            "current_stock": round(stock, 2),
            "weighted_avg_rate": round(rate, 2),
            "last_purchase_rate": round(float(m.get("last_purchase_rate") or rate), 2),
            "total_valuation": val,
            "reorder_level": reorder,
            "status": status,
        })

    material_rows.sort(key=lambda r: -r["total_valuation"])

    # Movements in period
    mov_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq: Dict[str, Any] = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date
        mov_query["date"] = dq

    movements = await db.inventory_movements.find(mov_query).to_list(10000)
    inward_qty = sum(float(m.get("quantity", 0)) for m in movements if m.get("type") in ["in", "GRN", "receipt"])
    inward_val = sum(float(m.get("quantity", 0)) * float(m.get("rate", 0)) for m in movements if m.get("type") in ["in", "GRN", "receipt"])
    outward_qty = sum(float(m.get("quantity", 0)) for m in movements if m.get("type") in ["out", "consumption", "issue"])
    outward_val = sum(float(m.get("quantity", 0)) * float(m.get("rate", 0)) for m in movements if m.get("type") in ["out", "consumption", "issue"])

    cat_list = [
        {
            "category": k,
            "items_count": v["items_count"],
            "total_stock": round(v["total_stock"], 2),
            "total_valuation": round(v["total_valuation"], 2),
        }
        for k, v in category_summary.items()
    ]
    cat_list.sort(key=lambda c: -c["total_valuation"])

    return {
        "total_items": len(materials),
        "total_valuation": round(total_valuation, 2),
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "inward_movement_qty": round(inward_qty, 2),
        "inward_movement_val": round(inward_val, 2),
        "outward_movement_qty": round(outward_qty, 2),
        "outward_movement_val": round(outward_val, 2),
        "categories": cat_list,
        "materials": material_rows,
    }


# ── 3. PRODUCTION LINE OVERVIEW & STAGE WIP ─────────────────────────────────────

@reports_router.get("/reports/production-overview")
async def report_production_overview(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = _get_db(request)

    job_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq: Dict[str, Any] = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        job_query["created_at"] = dq

    jobs = await db.production_jobs.find(job_query).to_list(10000)

    stages_order = [
        "procurement", "cutting", "folding", "attachment",
        "stitching", "lasting", "sole_pasting", "finishing", "qc_pack", "dispatched"
    ]
    stage_wip = {s: {"stage": s, "job_count": 0, "total_pairs": 0} for s in stages_order}

    total_pairs_started = 0
    total_pairs_dispatched = 0
    active_jobs = 0

    for j in jobs:
        st = j.get("stage", "procurement")
        qty = int(j.get("quantity", 0) or 0)
        total_pairs_started += qty

        if st in stage_wip:
            stage_wip[st]["job_count"] += 1
            stage_wip[st]["total_pairs"] += qty

        if st == "dispatched":
            total_pairs_dispatched += qty
        else:
            active_jobs += 1

    stage_breakdown = [stage_wip[s] for s in stages_order]

    # Defects in period
    defects = await db.defects.find({}).to_list(2000)
    total_defects = len(defects)
    total_rejected_pairs = sum(int(d.get("quantity", 1) or 1) for d in defects)

    return {
        "total_jobs": len(jobs),
        "active_jobs": active_jobs,
        "total_pairs_started": total_pairs_started,
        "total_pairs_dispatched": total_pairs_dispatched,
        "total_defects": total_defects,
        "total_rejected_pairs": total_rejected_pairs,
        "stage_breakdown": stage_breakdown,
    }


# ── 4. INVOICES & SALES PERFORMANCE ───────────────────────────────────────────

@reports_router.get("/reports/invoices-sales")
async def report_invoices_sales(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    inv_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq: Dict[str, Any] = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        inv_query["$or"] = [
            {"invoice_date": dq},
            {"created_at": dq},
            {"invoice_iso_date": dq}
        ]

    invoices = await db.invoices.find(inv_query).sort("created_at", -1).to_list(10000)

    total_invoiced = 0.0
    total_paid = 0.0
    total_balance = 0.0
    client_sales = defaultdict(lambda: {"invoices_count": 0, "total_billed": 0.0, "total_paid": 0.0, "total_balance": 0.0})
    rows = []

    for inv in invoices:
        grand = float(inv.get("grand_total") or inv.get("total_amount") or 0.0)
        paid = float(inv.get("paid_amount") or 0.0)
        bal = float(inv.get("balance_due") or max(0.0, grand - paid))
        c_name = inv.get("client_name") or inv.get("buyer_name") or "Direct Customer"

        total_invoiced += grand
        total_paid += paid
        total_balance += bal

        client_sales[c_name]["invoices_count"] += 1
        client_sales[c_name]["total_billed"] += grand
        client_sales[c_name]["total_paid"] += paid
        client_sales[c_name]["total_balance"] += bal

        st = "paid" if bal <= 0 and grand > 0 else ("partially_paid" if paid > 0 else "unpaid")

        rows.append({
            "id": str(inv["_id"]),
            "invoice_number": inv.get("invoice_number") or inv.get("invoice_no") or "—",
            "invoice_date": inv.get("invoice_date") or str(inv.get("created_at", ""))[:10],
            "client_name": c_name,
            "total_pairs": int(inv.get("total_pairs") or inv.get("total_quantity") or 0),
            "grand_total": round(grand, 2),
            "paid_amount": round(paid, 2),
            "balance_due": round(bal, 2),
            "status": st,
        })

    top_clients = [
        {"client_name": k, **{sk: round(sv, 2) if isinstance(sv, float) else sv for sk, sv in v.items()}}
        for k, v in sorted(client_sales.items(), key=lambda item: -item[1]["total_billed"])
    ]

    return {
        "total_invoices": len(invoices),
        "total_invoiced": round(total_invoiced, 2),
        "total_paid": round(total_paid, 2),
        "total_balance": round(total_balance, 2),
        "collection_rate_pct": round((total_paid / total_invoiced * 100), 2) if total_invoiced > 0 else 0.0,
        "top_clients": top_clients[:10],
        "invoices": rows,
    }


# ── 5. VENDOR PROCUREMENT & AP REPORT ──────────────────────────────────────────

@reports_router.get("/reports/vendor-procurement")
async def report_vendor_procurement(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    po_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq: Dict[str, Any] = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        po_query["created_at"] = dq

    vpos = await db.vendor_purchase_orders.find(po_query).sort("created_at", -1).to_list(10000)
    if not vpos:
        vpos = await db.vendor_pos.find(po_query).sort("created_at", -1).to_list(10000)

    total_po_value = 0.0
    total_paid = 0.0
    total_balance = 0.0
    total_ordered_qty = 0.0
    total_received_qty = 0.0

    vendor_summary = defaultdict(lambda: {
        "pos_count": 0, "total_amount": 0.0, "paid_amount": 0.0, "balance_due": 0.0,
        "ordered_qty": 0.0, "received_qty": 0.0
    })
    po_rows = []

    ap_aging = {"0_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0}
    now_dt = datetime.now(timezone.utc)

    for p in vpos:
        amt = float(p.get("total_amount") or 0.0)
        pd = float(p.get("paid_amount") or 0.0)
        bal = float(p.get("balance_due") or max(0.0, amt - pd))
        vname = p.get("vendor_name") or "Unknown Vendor"

        ord_q = sum(float(li.get("quantity") or 0.0) for li in p.get("line_items", []))
        rec_q = sum(float(li.get("received_quantity") or 0.0) for li in p.get("line_items", []))

        total_po_value += amt
        total_paid += pd
        total_balance += bal
        total_ordered_qty += ord_q
        total_received_qty += rec_q

        vendor_summary[vname]["pos_count"] += 1
        vendor_summary[vname]["total_amount"] += amt
        vendor_summary[vname]["paid_amount"] += pd
        vendor_summary[vname]["balance_due"] += bal
        vendor_summary[vname]["ordered_qty"] += ord_q
        vendor_summary[vname]["received_qty"] += rec_q

        if bal > 0:
            created_str = str(p.get("created_at") or "")[:10]
            try:
                created_dt = datetime.fromisoformat(created_str).replace(tzinfo=timezone.utc)
                age_days = (now_dt - created_dt).days
            except Exception:
                age_days = 0

            if age_days <= 30:
                ap_aging["0_30"] += bal
            elif age_days <= 60:
                ap_aging["31_60"] += bal
            elif age_days <= 90:
                ap_aging["61_90"] += bal
            else:
                ap_aging["90_plus"] += bal

        po_rows.append({
            "id": str(p["_id"]),
            "po_number": p.get("po_number") or "—",
            "vendor_name": vname,
            "created_at": str(p.get("created_at", ""))[:10],
            "expected_delivery_date": p.get("expected_delivery_date") or "—",
            "ordered_quantity": round(ord_q, 2),
            "received_quantity": round(rec_q, 2),
            "total_amount": round(amt, 2),
            "paid_amount": round(pd, 2),
            "balance_due": round(bal, 2),
            "status": p.get("status", "draft"),
        })

    vendors_breakdown = [
        {"vendor_name": k, **{sk: round(sv, 2) if isinstance(sv, float) else sv for sk, sv in v.items()}}
        for k, v in sorted(vendor_summary.items(), key=lambda item: -item[1]["total_amount"])
    ]

    fulfillment_rate = round((total_received_qty / total_ordered_qty * 100), 2) if total_ordered_qty > 0 else 0.0

    return {
        "total_pos": len(vpos),
        "total_po_value": round(total_po_value, 2),
        "total_paid": round(total_paid, 2),
        "total_balance_due": round(total_balance, 2),
        "total_ordered_qty": round(total_ordered_qty, 2),
        "total_received_qty": round(total_received_qty, 2),
        "fulfillment_rate_pct": fulfillment_rate,
        "ap_aging": {k: round(v, 2) for k, v in ap_aging.items()},
        "vendors": vendors_breakdown,
        "purchase_orders": po_rows,
    }


# ── 6. CLIENT RECEIVABLES & AR REPORT ──────────────────────────────────────────

@reports_router.get("/reports/client-receivables")
async def report_client_receivables(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    clients = await db.clients.find({}).to_list(1000)
    invoices = await db.invoices.find({}).to_list(10000)

    now_dt = datetime.now(timezone.utc)
    client_map = {}
    for c in clients:
        cid = str(c["_id"])
        client_map[c.get("name") or cid] = {
            "client_id": cid,
            "name": c.get("name") or "Unnamed Client",
            "contact_person": c.get("contact_person") or "—",
            "phone": c.get("phone") or "—",
            "payment_terms_days": c.get("payment_terms_days", 30),
            "invoiced_total": 0.0,
            "paid_total": 0.0,
            "balance_due": 0.0,
            "aging_bucket": "0-30",
        }

    ar_aging = {"0_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0}

    for inv in invoices:
        c_name = inv.get("client_name") or inv.get("buyer_name")
        if not c_name:
            continue
        if c_name not in client_map:
            client_map[c_name] = {
                "client_id": str(inv.get("client_id") or ""),
                "name": c_name,
                "contact_person": "—",
                "phone": "—",
                "payment_terms_days": 30,
                "invoiced_total": 0.0,
                "paid_total": 0.0,
                "balance_due": 0.0,
                "aging_bucket": "0-30",
            }

        grand = float(inv.get("grand_total") or inv.get("total_amount") or 0.0)
        paid = float(inv.get("paid_amount") or 0.0)
        bal = float(inv.get("balance_due") or max(0.0, grand - paid))

        client_map[c_name]["invoiced_total"] += grand
        client_map[c_name]["paid_total"] += paid
        client_map[c_name]["balance_due"] += bal

        if bal > 0:
            inv_date_str = str(inv.get("invoice_date") or inv.get("created_at") or "")[:10]
            try:
                inv_dt = datetime.fromisoformat(inv_date_str).replace(tzinfo=timezone.utc)
                age_days = (now_dt - inv_dt).days
            except Exception:
                age_days = 0

            if age_days <= 30:
                ar_aging["0_30"] += bal
                client_map[c_name]["aging_bucket"] = "0-30"
            elif age_days <= 60:
                ar_aging["31_60"] += bal
                client_map[c_name]["aging_bucket"] = "31-60"
            elif age_days <= 90:
                ar_aging["61_90"] += bal
                client_map[c_name]["aging_bucket"] = "61-90"
            else:
                ar_aging["90_plus"] += bal
                client_map[c_name]["aging_bucket"] = "90+"

    client_rows = [
        {
            **v,
            "invoiced_total": round(v["invoiced_total"], 2),
            "paid_total": round(v["paid_total"], 2),
            "balance_due": round(v["balance_due"], 2),
        }
        for v in client_map.values()
    ]
    client_rows.sort(key=lambda c: -c["balance_due"])

    total_invoiced = sum(c["invoiced_total"] for c in client_rows)
    total_paid = sum(c["paid_total"] for c in client_rows)
    total_outstanding = sum(c["balance_due"] for c in client_rows)

    return {
        "total_clients": len(client_rows),
        "total_invoiced": round(total_invoiced, 2),
        "total_paid": round(total_paid, 2),
        "total_outstanding": round(total_outstanding, 2),
        "ar_aging": {k: round(v, 2) for k, v in ar_aging.items()},
        "clients": client_rows,
    }


# ── 7. DETAILED P&L REPORT ───────────────────────────────────────────────────

@reports_router.get("/reports/pnl-detailed")
async def report_pnl_detailed(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    # 1. Operating Revenue
    inv_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq: Dict[str, Any] = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        inv_query["$or"] = [{"invoice_date": dq}, {"created_at": dq}, {"invoice_iso_date": dq}]
    invoices = await db.invoices.find(inv_query).to_list(10000)
    b2b_revenue = sum(float(i.get("grand_total") or i.get("total_amount") or 0.0) for i in invoices)

    settle_query: Dict[str, Any] = {}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        settle_query["$or"] = [{"settlement_date": dq}, {"created_at": dq}]
    settlements = await db.online_settlements_detailed.find(settle_query).to_list(5000)
    if not settlements:
        settlements = await db.online_settlements.find(settle_query).to_list(5000)
    online_revenue = sum(float(s.get("net_payout") or s.get("settlement_value") or s.get("invoiced_amount") or 0.0) for s in settlements)

    gross_revenue = round(b2b_revenue + online_revenue, 2)

    # 2. COGS: Raw Materials & Direct Labor
    po_query: Dict[str, Any] = {"status": {"$ne": "cancelled"}}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date + "T23:59:59.999Z" if len(to_date) == 10 else to_date
        po_query["created_at"] = dq
    vpos = await db.vendor_purchase_orders.find(po_query).to_list(10000)
    if not vpos:
        vpos = await db.vendor_pos.find(po_query).to_list(10000)
    material_cogs = sum(float(p.get("total_amount") or 0.0) for p in vpos)

    labor_cogs = 0.0
    try:
        import server
        payroll_fn = getattr(server, "report_payroll", None)
        if payroll_fn:
            pres = await payroll_fn(request, from_date=from_date, to_date=to_date)
            if isinstance(pres, dict) and "rows" in pres:
                labor_cogs = sum(float(r.get("total_earning", 0) or 0) for r in pres["rows"])
    except Exception as e:
        log.warning(f"Error computing labor COGS: {e}")

    total_cogs = round(material_cogs + labor_cogs, 2)
    gross_profit = round(gross_revenue - total_cogs, 2)
    gross_margin_pct = round((gross_profit / gross_revenue * 100), 2) if gross_revenue > 0 else 0.0

    # 3. Operating Expenses by Category
    exp_query: Dict[str, Any] = {"status": {"$nin": ["due", "overdue"]}}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = from_date
        if to_date:
            dq["$lte"] = to_date
        exp_query["date"] = dq
    expenses = await db.expenses.find(exp_query).to_list(10000)

    category_breakdown = defaultdict(float)
    monthly_trend_map = defaultdict(lambda: {"revenue": 0.0, "cogs": 0.0, "opex": 0.0, "profit": 0.0})

    for exp in expenses:
        cat = str(exp.get("category", "General & Administrative"))
        if cat.lower() in ["raw materials", "wages", "labor"]:
            continue
        amt = float(exp.get("amount") or 0.0)
        category_breakdown[cat] += amt
        m = str(exp.get("date") or "")[:7]
        if m:
            monthly_trend_map[m]["opex"] += amt

    total_opex = sum(category_breakdown.values())
    net_profit = round(gross_profit - total_opex, 2)
    net_margin_pct = round((net_profit / gross_revenue * 100), 2) if gross_revenue > 0 else 0.0

    # Monthly schedule
    for inv in invoices:
        m = str(inv.get("invoice_date") or inv.get("created_at") or "")[:7]
        if m:
            monthly_trend_map[m]["revenue"] += float(inv.get("grand_total") or inv.get("total_amount") or 0.0)
    for po in vpos:
        m = str(po.get("created_at") or "")[:7]
        if m:
            monthly_trend_map[m]["cogs"] += float(po.get("total_amount") or 0.0)

    monthly_pnl = []
    for m, d in sorted(monthly_trend_map.items()):
        gp = d["revenue"] - d["cogs"]
        np = gp - d["opex"]
        monthly_pnl.append({
            "month": m,
            "revenue": round(d["revenue"], 2),
            "cogs": round(d["cogs"], 2),
            "gross_profit": round(gp, 2),
            "opex": round(d["opex"], 2),
            "net_profit": round(np, 2),
            "net_margin_pct": round((np / d["revenue"] * 100), 2) if d["revenue"] > 0 else 0.0,
        })

    cat_list = [{"category": k, "amount": round(v, 2)} for k, v in sorted(category_breakdown.items(), key=lambda i: -i[1])]

    return {
        "gross_revenue": gross_revenue,
        "b2b_revenue": round(b2b_revenue, 2),
        "online_revenue": round(online_revenue, 2),
        "material_cogs": round(material_cogs, 2),
        "labor_cogs": round(labor_cogs, 2),
        "total_cogs": total_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "total_opex": round(total_opex, 2),
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
        "expense_categories": cat_list,
        "monthly_pnl": monthly_pnl[-12:],
    }
