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

    cash_account_id = None
    if payload.paid_via == "cash":
        target_cash_id = payload.cash_account_id or payload.cash_ledger_id
        if not target_cash_id:
            raise HTTPException(400, "cash_account_id or cash_ledger_id is required when paid_via is 'cash'")

        # 1. Check if target_cash_id matches a cash_account (or source bank account)
        ca_doc = None
        if hasattr(db, "cash_accounts") and db.cash_accounts is not None:
            try:
                ca_doc = await db.cash_accounts.find_one({"_id": oid(target_cash_id)})
            except Exception:
                pass
            if not ca_doc:
                try:
                    ca_doc = await db.cash_accounts.find_one({"_id": str(target_cash_id)})
                except Exception:
                    pass
            if not ca_doc:
                try:
                    ca_doc = await db.cash_accounts.find_one({"source_bank_account_id": str(target_cash_id)})
                except Exception:
                    pass

        if ca_doc:
            src_bank_id = str(ca_doc.get("source_bank_account_id") or "")
            ca_id = str(ca_doc.get("_id") or ca_doc.get("id"))
            ca_name = ca_doc.get("name") or "Cash Account"

            q_bank_ids = [src_bank_id]
            try:
                q_bank_ids.append(oid(src_bank_id))
            except Exception:
                pass

            cl_entries = []
            if hasattr(db, "cash_ledger") and db.cash_ledger is not None:
                cur = db.cash_ledger.find({
                    "bank_account_id": {"$in": q_bank_ids},
                    "remaining_balance": {"$gt": 0}
                }).sort("date", 1)
                if hasattr(cur, "to_list"):
                    res = cur.to_list(1000)
                    if hasattr(res, "__await__"):
                        cl_entries = await res
                    elif isinstance(res, list):
                        cl_entries = res
                    else:
                        cl_entries = []
                elif hasattr(cur, "__iter__"):
                    cl_entries = list(cur)

            total_available = sum(float(c.get("remaining_balance") or 0.0) for c in cl_entries)
            if round(total_available, 2) < round(amount, 2):
                raise HTTPException(
                    400,
                    f"Insufficient cash in account '{ca_name}'. Available remaining balance: ₹{total_available:.2f}, Requested expense amount: ₹{amount:.2f}",
                )

            # Draw down across cash_ledger entries in FIFO order
            to_deduct = round(amount, 2)
            primary_cl_id = None
            for entry in cl_entries:
                rem = float(entry.get("remaining_balance") or 0.0)
                if rem <= 0:
                    continue
                deduct = min(rem, to_deduct)
                await db.cash_ledger.update_one(
                    {"_id": entry["_id"], "remaining_balance": {"$gte": round(deduct, 2)}},
                    {"$inc": {"remaining_balance": -round(deduct, 2)}}
                )
                if not primary_cl_id:
                    primary_cl_id = str(entry["_id"])
                to_deduct = round(to_deduct - deduct, 2)
                if to_deduct <= 0:
                    break

            bank_account_id = src_bank_id
            cash_ledger_id = primary_cl_id or str(target_cash_id)
            cash_account_id = ca_id
        else:
            cash_entry = await db.cash_ledger.find_one({"_id": oid(target_cash_id)})
            if not cash_entry:
                raise HTTPException(404, f"Cash ledger entry '{target_cash_id}' not found")
            remaining = float(cash_entry.get("remaining_balance") or 0.0)
            if round(remaining, 2) < round(amount, 2):
                raise HTTPException(
                    400,
                    f"Insufficient cash in ledger entry. Available remaining balance: ₹{remaining:.2f}, Requested expense amount: ₹{amount:.2f}",
                )
            result = await db.cash_ledger.update_one(
                {"_id": oid(target_cash_id), "remaining_balance": {"$gte": round(amount, 2)}},
                {"$inc": {"remaining_balance": -round(amount, 2)}},
            )
            if result.modified_count == 0:
                raise HTTPException(400, "Insufficient cash or concurrent update conflict. Please retry.")
            bank_account_id = str(cash_entry.get("bank_account_id") or "") or None
            cash_ledger_id = str(target_cash_id)
            if bank_account_id and hasattr(db, "cash_accounts") and db.cash_accounts is not None:
                ca_entry = await db.cash_accounts.find_one({"source_bank_account_id": bank_account_id})
                if ca_entry:
                    cash_account_id = str(ca_entry.get("_id") or ca_entry.get("id"))
    else:
        bank_account_id = payload.bank_account_id
        cash_ledger_id = None
        cash_account_id = None

    doc = {
        "category": payload.category,
        "amount": amount,
        "date": payload.date,
        "payee": payload.payee,
        "notes": payload.notes or "",
        "receipt": payload.receipt,
        "paid_via": payload.paid_via,
        "cash_ledger_id": cash_ledger_id,
        "cash_account_id": cash_account_id,
        "bank_account_id": bank_account_id,
        "is_recurring": bool(payload.is_recurring),
        "recurring_expense_id": payload.recurring_expense_id or "",
        "status": payload.status or "confirmed",
        "linked_wage_payment_id": payload.linked_wage_payment_id or None,
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


# ---------- EXPORT DATA (EXPENSES & PURCHASES) ----------

@expenses_router.get("/expenses/export-data")
async def export_expenses_and_purchases(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    export_type: Optional[str] = "all",
    category: Optional[str] = None,
    search: Optional[str] = None,
):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")

    # 1. Fetch Expenses
    exp_q = {}
    if category and str(category).lower() != "all":
        exp_q["category"] = str(category)
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = str(from_date)
        if to_date:
            date_q["$lte"] = str(to_date)
        exp_q["date"] = date_q
    if search:
        s_regex = {"$regex": re.escape(str(search)), "$options": "i"}
        exp_q["$or"] = [
            {"payee": s_regex},
            {"category": s_regex},
            {"notes": s_regex},
        ]

    # Build lookup maps for bank & cash accounts
    banks_map = {}
    if getattr(db, "bank_accounts", None) is not None:
        try:
            b_list = await db.bank_accounts.find({}).to_list(1000)
            for b in b_list:
                bid = str(b.get("_id", ""))
                bname = b.get("name") or b.get("bank_name") or "Bank"
                if b.get("account_number_last4"):
                    bname += f" (••{b.get('account_number_last4')})"
                banks_map[bid] = bname
        except Exception:
            pass

    cash_map = {}
    if getattr(db, "cash_accounts", None) is not None:
        try:
            c_list = await db.cash_accounts.find({}).to_list(1000)
            for c in c_list:
                cid = str(c.get("_id", ""))
                cash_map[cid] = c.get("name") or "Cash Account"
                if c.get("source_bank_account_id"):
                    cash_map[str(c["source_bank_account_id"])] = c.get("name") or "Cash Account"
        except Exception:
            pass

    expenses_docs = []
    if export_type in ["expenses", "all"]:
        raw_expenses = await db.expenses.find(exp_q).sort([("date", -1), ("created_at", -1)]).to_list(10000)
        for e in raw_expenses:
            b_id = str(e.get("bank_account_id") or "")
            c_id = str(e.get("cash_account_id") or e.get("cash_ledger_id") or "")
            b_name = e.get("bank_account_name") or e.get("bank_name") or banks_map.get(b_id) or "—"
            c_name = e.get("cash_account_name") or cash_map.get(c_id) or "—"
            expenses_docs.append({
                "id": str(e.get("_id", "")),
                "date": e.get("date") or str(e.get("created_at", ""))[:10],
                "category": e.get("category", "General"),
                "payee": e.get("payee", "—"),
                "amount": float(e.get("amount", 0) or 0),
                "paid_via": e.get("paid_via", "bank"),
                "bank_account_name": b_name,
                "cash_account_name": c_name,
                "status": e.get("status", "paid"),
                "notes": e.get("notes", "") or "—",
                "is_recurring": bool(e.get("recurring_expense_id") or e.get("is_recurring")),
            })

    # 2. Fetch Purchases / Vendor POs
    purchases_docs = []
    if export_type in ["purchases", "all"]:
        po_q = {"status": {"$ne": "cancelled"}}
        if from_date or to_date:
            date_q = {}
            if from_date:
                date_q["$gte"] = str(from_date)
            if to_date:
                date_q["$lte"] = f"{to_date}T23:59:59.999Z" if len(to_date) == 10 else str(to_date)
            po_q["$or"] = [
                {"created_at": date_q},
                {"expected_delivery_date": {"$gte": from_date or "2000-01-01", "$lte": to_date or "2099-12-31"}},
            ]

        raw_pos = []
        if getattr(db, "vendor_purchase_orders", None) is not None:
            raw_pos = await db.vendor_purchase_orders.find(po_q).sort([("created_at", -1)]).to_list(10000)
        if not raw_pos and getattr(db, "vendor_pos", None) is not None:
            raw_pos = await db.vendor_pos.find(po_q).sort([("created_at", -1)]).to_list(10000)

        vendors_map = {}
        if getattr(db, "vendors", None) is not None:
            v_list = await db.vendors.find({}).to_list(1000)
            vendors_map = {str(v["_id"]): v.get("name", "") for v in v_list}

        for po in raw_pos:
            vid = str(po.get("vendor_id", ""))
            vname = po.get("vendor_name") or vendors_map.get(vid) or "Unknown Vendor"

            line_items = po.get("line_items", [])
            mat_names = [li.get("material_name") or li.get("material_id", "") for li in line_items if li.get("material_name") or li.get("material_id")]
            items_desc = ", ".join(mat_names[:4]) + (f" (+{len(mat_names) - 4} more)" if len(mat_names) > 4 else "")
            if not items_desc:
                items_desc = "Materials Procurement"

            tot_qty = sum(float(li.get("quantity", 0) or 0) for li in line_items)
            rec_qty = sum(float(li.get("received_quantity", 0) or 0) for li in line_items)

            amt = float(po.get("total_amount") or po.get("grand_total") or sum(float(li.get("amount", 0) or 0) for li in line_items))
            paid = float(po.get("paid_amount", 0) or 0)
            bal = float(po.get("balance_due") if po.get("balance_due") is not None else max(0.0, amt - paid))
            created_date = str(po.get("created_at", ""))[:10] or "—"

            purchases_docs.append({
                "id": str(po.get("_id", "")),
                "po_number": po.get("po_number") or "—",
                "date": created_date,
                "vendor_name": vname,
                "items_description": items_desc,
                "total_quantity": round(tot_qty, 2),
                "received_quantity": round(rec_qty, 2),
                "total_amount": round(amt, 2),
                "paid_amount": round(paid, 2),
                "balance_due": round(bal, 2),
                "status": po.get("status", "sent"),
                "expected_delivery_date": po.get("expected_delivery_date") or "—",
            })

        if search:
            s_lower = str(search).lower()
            purchases_docs = [
                p for p in purchases_docs
                if s_lower in p["vendor_name"].lower()
                or s_lower in p["po_number"].lower()
                or s_lower in p["items_description"].lower()
            ]

    total_exp_amt = sum(e["amount"] for e in expenses_docs)
    total_pur_amt = sum(p["total_amount"] for p in purchases_docs)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "export_type": export_type,
        "expenses": expenses_docs,
        "purchases": purchases_docs,
        "summary": {
            "expenses_count": len(expenses_docs),
            "expenses_amount": round(total_exp_amt, 2),
            "purchases_count": len(purchases_docs),
            "purchases_amount": round(total_pur_amt, 2),
            "total_outflow_amount": round(total_exp_amt + total_pur_amt, 2),
        }
    }


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
    vendor_pos = []
    if getattr(db, "vendor_purchase_orders", None) is not None:
        vendor_pos = await db.vendor_purchase_orders.find(ven_po_q).to_list(5000)
    if not vendor_pos and getattr(db, "vendor_pos", None) is not None:
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
        if "bank_account_id" in payload:
            update_fields["bank_account_id"] = payload["bank_account_id"]
        if "paid_via" in payload:
            update_fields["paid_via"] = payload["paid_via"]
        if "cash_account_id" in payload:
            update_fields["cash_account_id"] = payload["cash_account_id"]
        if "cash_ledger_id" in payload:
            update_fields["cash_ledger_id"] = payload["cash_ledger_id"]

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
    if doc.get("paid_via") == "cash" and hasattr(db, "cash_ledger"):
        cl_id = doc.get("cash_ledger_id")
        if cl_id:
            try:
                await db.cash_ledger.update_one(
                    {"_id": oid(cl_id)},
                    {"$inc": {"remaining_balance": round(float(doc.get("amount") or 0.0), 2)}}
                )
            except Exception:
                try:
                    await db.cash_ledger.update_one(
                        {"_id": str(cl_id)},
                        {"$inc": {"remaining_balance": round(float(doc.get("amount") or 0.0), 2)}}
                    )
                except Exception:
                    pass
    await db.expenses.delete_one({"_id": oid(eid)})
    await log_activity_db(
        db,
        "DELETE", "expenses",
        f"Deleted expense ₹{doc.get('amount')} ({doc.get('category')})",
        u.get("email") or u.get("name", "")
    )
    return {"ok": True, "deleted_id": eid}
