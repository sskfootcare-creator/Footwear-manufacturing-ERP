"""Expense Master, Recurring Expense Scheduler & Simple P&L Routes."""

import re
import logging
import calendar
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from models.expenses import (
    EXPENSE_CATEGORIES,
    ExpenseIn,
    ExpenseUpdate,
    RecurringExpenseIn,
    RecurringExpenseUpdate,
)
from auth import require_roles

log = logging.getLogger(__name__)

expenses_router = APIRouter(prefix="/api", tags=["Expenses & P&L"])


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


async def _check_and_generate_recurring_expenses_db(db) -> dict:
    """Auto-generates due/overdue Expense entries for all active RecurringExpense templates."""
    today_dt = datetime.now(timezone.utc).date()
    today_str = today_dt.isoformat()
    current_ym = today_str[:7]

    active_templates = await db.recurring_expenses.find({"active": True}).to_list(1000)
    generated_count = 0
    updated_count = 0

    for tmpl in active_templates:
        tid = str(tmpl["_id"])
        due_day = int(tmpl.get("due_day", 1))
        start_date = tmpl.get("start_date", "2000-01-01")
        end_date = tmpl.get("end_date")

        if start_date > today_str:
            continue
        if end_date and end_date < today_str:
            continue

        year, month = today_dt.year, today_dt.month
        max_days = calendar.monthrange(year, month)[1]
        target_day = min(due_day, max_days)
        target_date_str = f"{year:04d}-{month:02d}-{target_day:02d}"

        existing = await db.expenses.find_one({
            "recurring_expense_id": tid,
            "date": {"$regex": f"^{current_ym}"}
        })

        if not existing:
            status = "overdue" if today_str > target_date_str else "due"
            exp_doc = {
                "category": tmpl.get("category", "Rent & Utilities"),
                "amount": float(tmpl.get("amount", 0)),
                "date": target_date_str,
                "payee": tmpl.get("payee", "Payee"),
                "notes": tmpl.get("notes") or f"Auto-generated recurring expense for {current_ym}",
                "receipt": None,
                "bank_account_id": tmpl.get("bank_account_id"),
                "is_recurring": True,
                "recurring_expense_id": tid,
                "status": status,
                "created_at": now_iso(),
                "created_by": "system_scheduler",
            }
            await db.expenses.insert_one(exp_doc)
            generated_count += 1
        else:
            if existing.get("status") == "due" and today_str > target_date_str:
                await db.expenses.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"status": "overdue", "updated_at": now_iso()}}
                )
                updated_count += 1

    return {"generated_count": generated_count, "updated_count": updated_count}


# ---------- EXPENSE CRUD (STATIC PATHS FIRST) ----------

@expenses_router.post("/expenses")
async def create_expense(payload: ExpenseIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    amount = float(payload.amount)
    if amount <= 0:
        raise HTTPException(400, "Expense amount must be greater than 0")

    if payload.paid_via == "cash":
        if not payload.cash_ledger_id:
            raise HTTPException(400, "cash_ledger_id is required when paid_via is 'cash'")
        cash_entry = await db.cash_ledger.find_one({"_id": oid(payload.cash_ledger_id)})
        if not cash_entry:
            raise HTTPException(404, f"Cash ledger entry '{payload.cash_ledger_id}' not found")
        remaining = float(cash_entry.get("remaining_balance") or 0.0)
        if amount > remaining + 0.001:
            raise HTTPException(
                400,
                f"Insufficient cash in ledger entry. Available remaining balance: ₹{remaining:.2f}, Requested expense amount: ₹{amount:.2f}",
            )
        # Decrement cash_ledger entry's remaining balance
        await db.cash_ledger.update_one(
            {"_id": oid(payload.cash_ledger_id)},
            {"$inc": {"remaining_balance": -round(amount, 2)}}
        )
        bank_account_id = None
        cash_ledger_id = str(payload.cash_ledger_id)
    else:
        bank_account_id = payload.bank_account_id
        cash_ledger_id = None

    doc = {
        "category": payload.category,
        "amount": amount,
        "date": payload.date,
        "payee": payload.payee,
        "notes": payload.notes or "",
        "receipt": payload.receipt,
        "paid_via": payload.paid_via,
        "cash_ledger_id": cash_ledger_id,
        "bank_account_id": bank_account_id,
        "is_recurring": bool(payload.is_recurring),
        "recurring_expense_id": payload.recurring_expense_id or "",
        "status": payload.status or "confirmed",
        "created_at": now_iso(),
        "created_by": u.get("email") or u.get("name", ""),
    }
    res = await db.expenses.insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_activity_db(
        db,
        "CREATE", "expenses",
        f"Created expense ₹{payload.amount} ({payload.category}) for {payload.payee}",
        u.get("email") or u.get("name", "")
    )
    return stringify(doc)


@expenses_router.get("/expenses")
async def list_expenses(
    request: Request,
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 1000
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {}
    if category and str(category).lower() != "all":
        q["category"] = str(category)
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = str(from_date)
        if to_date:
            date_q["$lte"] = str(to_date)
        q["date"] = date_q
    if search:
        s_regex = {"$regex": re.escape(str(search)), "$options": "i"}
        q["$or"] = [
            {"payee": s_regex},
            {"category": s_regex},
            {"notes": s_regex},
        ]
    docs = await db.expenses.find(q).sort([("date", -1), ("created_at", -1)]).limit(limit).to_list(limit)
    return [stringify(d) for d in docs]


# ---------- RECURRING EXPENSES ----------

@expenses_router.post("/expenses/recurring", status_code=201)
async def create_recurring_expense(payload: RecurringExpenseIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = {
        "category": payload.category,
        "payee": payload.payee,
        "amount": float(payload.amount),
        "frequency": payload.frequency,
        "start_date": payload.start_date,
        "due_day": int(payload.due_day),
        "end_date": payload.end_date,
        "bank_account_id": payload.bank_account_id,
        "active": payload.active,
        "notes": payload.notes or "",
        "created_at": now_iso(),
        "created_by": u.get("email") or u.get("name", ""),
    }
    res = await db.recurring_expenses.insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_activity_db(
        db,
        "CREATE", "recurring_expenses",
        f"Created recurring expense '{payload.category}' (₹{payload.amount}) for {payload.payee}",
        u.get("email") or u.get("name", "")
    )
    await _check_and_generate_recurring_expenses_db(db)
    return stringify(doc)


@expenses_router.get("/expenses/recurring")
async def list_recurring_expenses(request: Request, active_only: bool = False):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {"active": True} if active_only else {}
    docs = await db.recurring_expenses.find(q).sort("created_at", -1).to_list(1000)
    return [stringify(d) for d in docs]


@expenses_router.post("/expenses/check-recurring")
async def trigger_check_recurring_expenses(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    return await _check_and_generate_recurring_expenses_db(db)


@expenses_router.get("/expenses/due-queue")
async def get_expenses_due_queue(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    await _check_and_generate_recurring_expenses_db(db)
    docs = await db.expenses.find({"status": {"$in": ["due", "overdue"]}}).sort("date", 1).to_list(1000)
    return [stringify(d) for d in docs]


@expenses_router.get("/expenses/recurring/{rid}")
async def get_recurring_expense(rid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.recurring_expenses.find_one({"_id": oid(rid)})
    if not doc:
        raise HTTPException(404, "Recurring expense template not found")
    return stringify(doc)


@expenses_router.patch("/expenses/recurring/{rid}")
async def update_recurring_expense(rid: str, payload: RecurringExpenseUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.recurring_expenses.find_one({"_id": oid(rid)})
    if not doc:
        raise HTTPException(404, "Recurring expense template not found")
    
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if updates:
        updates["updated_at"] = now_iso()
        await db.recurring_expenses.update_one({"_id": oid(rid)}, {"$set": updates})
        doc.update(updates)
        await log_activity_db(db, "UPDATE", "recurring_expenses", f"Updated recurring expense template id={rid}", u.get("email") or u.get("name", ""))
    return stringify(doc)


@expenses_router.delete("/expenses/recurring/{rid}")
async def delete_recurring_expense(rid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.recurring_expenses.find_one({"_id": oid(rid)})
    if not doc:
        raise HTTPException(404, "Recurring expense template not found")
    await db.recurring_expenses.delete_one({"_id": oid(rid)})
    await log_activity_db(db, "DELETE", "recurring_expenses", f"Deleted recurring expense template id={rid}", u.get("email") or u.get("name", ""))
    return {"ok": True}


# ---------- SIMPLE P&L ----------

@expenses_router.get("/reports/pnl")
@expenses_router.get("/expenses/pnl")
async def get_simple_pnl(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    
    # 1. Invoices Revenue
    inv_q = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        inv_q["$or"] = [
            {"invoice_date": date_q},
            {"invoice_iso_date": date_q},
            {"created_at": date_q}
        ]
    invoices = await db.invoices.find(inv_q).to_list(5000)
    invoices_revenue = 0.0
    for inv in invoices:
        val = inv.get("grand_total") or inv.get("total_amount") or inv.get("total") or 0.0
        invoices_revenue += float(val)
        
    # 2. Reconciled Settlements Revenue
    settle_q = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        settle_q["$or"] = [
            {"settlement_date": date_q},
            {"created_at": date_q}
        ]
    settlements = await db.online_settlements.find(settle_q).to_list(5000)
    settlements_revenue = 0.0
    for st in settlements:
        val = st.get("net_payout") or st.get("invoiced_amount") or st.get("settlement_value") or 0.0
        settlements_revenue += float(val)

    total_revenue = invoices_revenue + settlements_revenue

    # 3. Material Cost
    ven_po_q = {"status": {"$ne": "cancelled"}}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        ven_po_q["$or"] = [
            {"created_at": date_q},
            {"expected_delivery_date": date_q}
        ]
    vendor_pos = await db.vendor_pos.find(ven_po_q).to_list(5000)
    material_cost = 0.0
    for po in vendor_pos:
        tot = po.get("total_amount") or po.get("grand_total")
        if tot is None:
            tot = sum(float(li.get("amount", 0) or 0) for li in po.get("line_items", []))
        material_cost += float(tot or 0)

    # 4. Labor Cost (Payroll earnings)
    labor_cost = 0.0
    try:
        import server
        report_payroll_fn = getattr(server, "report_payroll", None)
        if report_payroll_fn:
            payroll_res = await report_payroll_fn(request, from_date=from_date, to_date=to_date)
            if isinstance(payroll_res, dict) and "rows" in payroll_res:
                labor_cost = sum(float(r.get("total_earning", 0) or 0) for r in payroll_res["rows"])
            elif isinstance(payroll_res, list):
                labor_cost = sum(float(r.get("total_earning", 0) or 0) for r in payroll_res)
    except Exception as e:
        log.warning(f"Failed to calculate labor cost for P&L: {e}")

    # 5. Expenses (Confirmed only)
    exp_q = {"status": {"$nin": ["due", "overdue"]}}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        exp_q["date"] = date_q
    expenses_docs = await db.expenses.find(exp_q).to_list(5000)

    total_expenses = 0.0
    recurring_expenses_total = 0.0
    variable_expenses_total = 0.0

    category_totals = defaultdict(float)
    monthly_expenses = defaultdict(float)
    monthly_recurring_expenses = defaultdict(float)
    monthly_variable_expenses = defaultdict(float)
    monthly_revenue = defaultdict(float)
    monthly_material = defaultdict(float)
    monthly_labor = defaultdict(float)

    for exp in expenses_docs:
        amt = float(exp.get("amount", 0) or 0)
        cat = exp.get("category", "Uncategorized")
        dt = str(exp.get("date", ""))[:7] or "Unknown"
        is_rec = bool(exp.get("is_recurring")) or bool(exp.get("recurring_expense_id"))

        total_expenses += amt
        category_totals[cat] += amt
        monthly_expenses[dt] += amt

        if is_rec:
            recurring_expenses_total += amt
            monthly_recurring_expenses[dt] += amt
        else:
            variable_expenses_total += amt
            monthly_variable_expenses[dt] += amt

    for inv in invoices:
        val = float(inv.get("grand_total") or inv.get("total_amount") or inv.get("total") or 0)
        dt = str(inv.get("invoice_date") or inv.get("invoice_iso_date") or inv.get("created_at") or "")[:7] or "Unknown"
        monthly_revenue[dt] += val

    for st in settlements:
        val = float(st.get("net_payout") or st.get("invoiced_amount") or st.get("settlement_value") or 0)
        dt = str(st.get("settlement_date") or st.get("created_at") or "")[:7] or "Unknown"
        monthly_revenue[dt] += val

    for po in vendor_pos:
        tot = po.get("total_amount") or po.get("grand_total")
        if tot is None:
            tot = sum(float(li.get("amount", 0) or 0) for li in po.get("line_items", []))
        dt = str(po.get("created_at") or po.get("expected_delivery_date") or "")[:7] or "Unknown"
        monthly_material[dt] += float(tot or 0)

    # Monthly breakdown aggregation
    all_months = sorted(list(set(list(monthly_expenses.keys()) + list(monthly_revenue.keys()) + list(monthly_material.keys()))))
    monthly_breakdown = []
    for m in all_months:
        if m == "Unknown" and len(all_months) > 1:
            continue
        m_rev = monthly_revenue.get(m, 0.0)
        m_mat = monthly_material.get(m, 0.0)
        m_lab = monthly_labor.get(m, 0.0)
        m_exp = monthly_expenses.get(m, 0.0)
        m_rec_exp = monthly_recurring_expenses.get(m, 0.0)
        m_var_exp = monthly_variable_expenses.get(m, 0.0)
        m_net = m_rev - m_mat - m_lab - m_exp
        monthly_breakdown.append({
            "month": m,
            "revenue": round(m_rev, 2),
            "material_cost": round(m_mat, 2),
            "labor_cost": round(m_lab, 2),
            "expenses": round(m_exp, 2),
            "recurring_expenses": round(m_rec_exp, 2),
            "variable_expenses": round(m_var_exp, 2),
            "net_profit": round(m_net, 2)
        })

    gross_profit = total_revenue - material_cost - labor_cost
    net_profit = gross_profit - total_expenses

    return {
        "revenue": round(total_revenue, 2),
        "invoices_revenue": round(invoices_revenue, 2),
        "settlements_revenue": round(settlements_revenue, 2),
        "material_cost": round(material_cost, 2),
        "labor_cost": round(labor_cost, 2),
        "expenses": round(total_expenses, 2),
        "recurring_expenses": round(recurring_expenses_total, 2),
        "variable_expenses": round(variable_expenses_total, 2),
        "gross_profit": round(gross_profit, 2),
        "net_profit": round(net_profit, 2),
        "category_totals": {k: round(v, 2) for k, v in category_totals.items()},
        "monthly_breakdown": monthly_breakdown,
    }


# ---------- EXPENSE INSTANCE OPERATIONS ({eid}) ----------

@expenses_router.post("/expenses/{eid}/confirm")
async def confirm_expense(eid: str, request: Request, payload: Optional[dict] = None):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = await db.expenses.find_one({"_id": oid(eid)})
    if not doc:
        raise HTTPException(404, "Expense not found")
    
    update_fields = {"status": "confirmed", "confirmed_at": now_iso(), "confirmed_by": u.get("email") or u.get("name", "")}
    if payload:
        if "amount" in payload and payload["amount"] is not None:
            update_fields["amount"] = float(payload["amount"])
        if "payee" in payload and payload["payee"]:
            update_fields["payee"] = payload["payee"]
        if "date" in payload and payload["date"]:
            update_fields["date"] = payload["date"]
        if "notes" in payload:
            update_fields["notes"] = payload["notes"]
        if "receipt" in payload:
            update_fields["receipt"] = payload["receipt"]
        if "category" in payload and payload["category"]:
            update_fields["category"] = payload["category"]

    await db.expenses.update_one({"_id": oid(eid)}, {"$set": update_fields})
    doc = await db.expenses.find_one({"_id": oid(eid)})
    await log_activity_db(
        db,
        "CONFIRM", "expenses",
        f"Confirmed recurring expense id={eid} (₹{doc.get('amount')})",
        u.get("email") or u.get("name", "")
    )
    return stringify(doc)


@expenses_router.get("/expenses/{eid}")
async def get_expense(eid: str, request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    try:
        doc = await db.expenses.find_one({"_id": oid(eid)})
    except Exception:
        raise HTTPException(404, "Expense not found")
    if not doc:
        raise HTTPException(404, "Expense not found")
    return stringify(doc)


@expenses_router.put("/expenses/{eid}")
async def update_expense(eid: str, payload: ExpenseUpdate, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    try:
        doc = await db.expenses.find_one({"_id": oid(eid)})
    except Exception:
        raise HTTPException(404, "Expense not found")
    if not doc:
        raise HTTPException(404, "Expense not found")
    
    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if update_data:
        update_data["updated_at"] = now_iso()
        await db.expenses.update_one({"_id": oid(eid)}, {"$set": update_data})
        doc.update(update_data)
        await log_activity_db(db, "UPDATE", "expenses", f"Updated expense id={eid}", u.get("email") or u.get("name", ""))
    return stringify(doc)


@expenses_router.delete("/expenses/{eid}")
async def delete_expense(eid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    try:
        doc = await db.expenses.find_one({"_id": oid(eid)})
    except Exception:
        raise HTTPException(404, "Expense not found")
    if not doc:
        raise HTTPException(404, "Expense not found")
    if doc.get("paid_via") == "cash" and doc.get("cash_ledger_id") and hasattr(db, "cash_ledger"):
        await db.cash_ledger.update_one(
            {"_id": oid(doc["cash_ledger_id"])},
            {"$inc": {"remaining_balance": round(float(doc.get("amount") or 0.0), 2)}}
        )
    await db.expenses.delete_one({"_id": oid(eid)})
    await log_activity_db(
        db,
        "DELETE", "expenses",
        f"Deleted expense ₹{doc.get('amount')} ({doc.get('category')})",
        u.get("email") or u.get("name", "")
    )
    return {"ok": True, "deleted_id": eid}
