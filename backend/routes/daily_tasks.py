"""Daily Tasks, Approver Sign-Off, and Expense-Linked Shopping Lists Routes."""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from models.daily_tasks import (
    DailyTaskCreate,
    DailyTaskStatusUpdate,
    DailyTaskCommentCreate,
    DailyListCreate,
    DailyListItemCreate,
    DailyListItemUpdate,
    DailyListSettleIn,
)
from models.expenses import EXPENSE_CATEGORIES
from routes.banking import sync_bank_account_balance

log = logging.getLogger(__name__)

daily_tasks_router = APIRouter(prefix="/api", tags=["Daily Tasks & Shopping Lists"])

VOICE_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads",
    "voice_notes",
)
os.makedirs(VOICE_UPLOAD_DIR, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    # IST (+05:30) for daily factory operations
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).date().isoformat()


def _tomorrow_str() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return (datetime.now(ist).date() + timedelta(days=1)).isoformat()


def _oid(val: str) -> ObjectId:
    try:
        return ObjectId(val)
    except Exception:
        raise HTTPException(400, "Invalid object ID format")


def _stringify(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


def _get_db(request: Request):
    db = getattr(request.app, "mongodb", None)
    if db is not None:
        return db
    import server
    return getattr(server, "db", None)


async def _get_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user:
        return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    db = _get_db(request)
    fn = await get_current_user_factory(db)
    return await fn(request)


async def _create_notification(db, user_id: Optional[str], title: str, message: str, link: str = "/daily-tasks", notif_type: str = "daily_task"):
    if not user_id or not hasattr(db, "notifications") or db.notifications is None:
        return
    try:
        await db.notifications.insert_one({
            "user_id": str(user_id),
            "title": title,
            "message": message,
            "type": notif_type,
            "link": link,
            "read": False,
            "created_at": _now_iso(),
        })
    except Exception as exc:
        log.warning(f"Failed to insert notification: {exc}")


async def _auto_carry_forward(db, today: str):
    """Automatically escalate unfinished tasks from past dates to today as P0."""
    if not hasattr(db, "daily_tasks") or db.daily_tasks is None:
        return
    past_cursor = db.daily_tasks.find({
        "task_date": {"$lt": today},
        "status": {"$in": ["pending", "in_progress", "needs_input"]},
    })
    past_tasks = await past_cursor.to_list(200)
    for t in past_tasks:
        prev_date = t.get("carried_from_date") or t.get("task_date")
        count = int(t.get("carry_forward_count") or 0) + 1
        await db.daily_tasks.update_one(
            {"_id": t["_id"]},
            {
                "$set": {
                    "task_date": today,
                    "priority": "P0",
                    "carried_from_date": prev_date,
                    "carry_forward_count": count,
                    "updated_at": _now_iso(),
                }
            },
        )


@daily_tasks_router.get("/daily-tasks")
async def list_daily_tasks(
    request: Request,
    date: Optional[str] = None,
    view: str = "all",
):
    db = _get_db(request)
    user = await _get_user(request)
    today = date or _today_str()
    user_id = str(user.get("id") or user.get("_id") or "")

    await _auto_carry_forward(db, _today_str())

    query = {}
    if view == "today":
        query["task_date"] = today
    elif view == "approvals":
        query["status"] = "pending_approval"
    elif view == "needs_input":
        query["status"] = "needs_input"
    elif view == "history":
        query["status"] = "done"

    docs = await db.daily_tasks.find(query).sort([("priority", 1), ("created_at", -1)]).to_list(500)
    tasks = [_stringify(d) for d in docs]

    # Attach comment counts
    task_ids = [t["id"] for t in tasks]
    comment_counts = {}
    if task_ids and hasattr(db, "daily_task_comments") and db.daily_task_comments is not None:
        c_docs = await db.daily_task_comments.find({"task_id": {"$in": task_ids}}).to_list(2000)
        for c in c_docs:
            tid = str(c.get("task_id") or "")
            comment_counts[tid] = comment_counts.get(tid, 0) + 1
    for t in tasks:
        t["comment_count"] = comment_counts.get(t["id"], 0)

    # Summary metrics for today
    today_docs = await db.daily_tasks.find({"task_date": today}).to_list(500)
    total_today = len(today_docs)
    done_today = sum(1 for d in today_docs if d.get("status") == "done")
    pending_approval_count = sum(1 for d in docs if d.get("status") == "pending_approval")
    needs_input_count = sum(1 for d in docs if d.get("status") == "needs_input")
    carried_count = sum(1 for d in today_docs if int(d.get("carry_forward_count") or 0) > 0)

    # Load assignable users
    users_list = []
    if hasattr(db, "users") and db.users is not None:
        u_docs = await db.users.find({}, {"password": 0, "hashed_password": 0}).to_list(200)
        for u in u_docs:
            users_list.append({
                "id": str(u.get("_id")),
                "name": u.get("name") or u.get("username") or u.get("email") or "User",
                "role": u.get("role") or "staff",
            })

    # Load active bank accounts for shopping list settlement
    bank_accounts = []
    if hasattr(db, "bank_accounts") and db.bank_accounts is not None:
        b_docs = await db.bank_accounts.find({"active": {"$ne": False}}).sort("name", 1).to_list(100)
        bank_accounts = [_stringify(b) for b in b_docs]

    return {
        "tasks": tasks,
        "summary": {
            "total_today": total_today,
            "done_today": done_today,
            "completion_pct": round((done_today / total_today) * 100) if total_today else 0,
            "pending_approval_count": pending_approval_count,
            "needs_input_count": needs_input_count,
            "carried_forward_count": carried_count,
        },
        "current_user": {
            "id": user_id,
            "name": user.get("name") or user.get("email") or "User",
            "role": user.get("role") or "admin",
        },
        "users": users_list,
        "expense_categories": EXPENSE_CATEGORIES,
        "bank_accounts": bank_accounts,
    }


@daily_tasks_router.post("/daily-tasks", status_code=201)
async def create_daily_task(payload: DailyTaskCreate, request: Request):
    db = _get_db(request)
    user = await _get_user(request)
    user_id = str(user.get("id") or user.get("_id") or "")
    user_name = user.get("name") or user.get("email") or "Partner"

    now = _now_iso()
    doc = {
        "title": payload.title.strip(),
        "description": (payload.description or "").strip(),
        "task_type": payload.task_type,
        "priority": payload.priority,
        "project": payload.project or "Factory Ops",
        "task_date": payload.task_date or _today_str(),
        "due_time": payload.due_time or "17:30",
        "assignee_id": payload.assignee_id or user_id,
        "assignee_name": payload.assignee_name or user_name,
        "assignee_role": payload.assignee_role or user.get("role") or "staff",
        "assigned_by_id": user_id,
        "assigned_by_name": user_name,
        "approver_id": payload.approver_id or user_id,
        "approver_name": payload.approver_name or user_name,
        "status": "pending",
        "erp_ref_type": payload.erp_ref_type,
        "erp_ref_label": payload.erp_ref_label,
        "photos": [p.model_dump() for p in payload.photos],
        "voice_notes": [v.model_dump() for v in payload.voice_notes],
        "carried_from_date": None,
        "carry_forward_count": 0,
        "non_completion_reason": None,
        "completed_at": None,
        "closed_by": None,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.daily_tasks.insert_one(doc)
    doc["_id"] = res.inserted_id

    if doc["assignee_id"] and doc["assignee_id"] != user_id:
        await _create_notification(
            db,
            doc["assignee_id"],
            f"New {doc['priority']} Task Assigned",
            f"{user_name} assigned: {doc['title']} (Approver: {doc['approver_name']})",
        )

    out = _stringify(doc)
    out["comment_count"] = 0
    return out


@daily_tasks_router.patch("/daily-tasks/{task_id}/status")
async def update_daily_task_status(task_id: str, payload: DailyTaskStatusUpdate, request: Request):
    db = _get_db(request)
    user = await _get_user(request)
    user_id = str(user.get("id") or user.get("_id") or "")
    user_name = user.get("name") or user.get("email") or "User"
    user_role = (user.get("role") or "").lower()

    task = await db.daily_tasks.find_one({"_id": _oid(task_id)})
    if not task:
        raise HTTPException(404, "Task not found")

    new_status = payload.status
    updates = {"updated_at": _now_iso()}

    if new_status == "done":
        # Only designated approver or admin can approve & close
        approver_id = str(task.get("approver_id") or "")
        if approver_id and approver_id != user_id and user_role != "admin":
            raise HTTPException(403, f"Only the designated approver ({task.get('approver_name')}) or Admin can approve & close this task.")
        updates["status"] = "done"
        updates["completed_at"] = _now_iso()
        updates["closed_by"] = user_name
        if task.get("assignee_id") and str(task.get("assignee_id")) != user_id:
            await _create_notification(
                db,
                str(task["assignee_id"]),
                "Task Approved & Closed",
                f"{user_name} approved & closed: {task.get('title')}",
            )
    elif new_status == "reopened":
        updates["status"] = "in_progress"
        updates["completed_at"] = None
        updates["closed_by"] = None
        if task.get("assignee_id") and str(task.get("assignee_id")) != user_id:
            await _create_notification(
                db,
                str(task["assignee_id"]),
                "Task Reopened",
                f"{user_name} reopened: {task.get('title')}",
            )
    elif new_status == "pending_approval":
        updates["status"] = "pending_approval"
        if task.get("approver_id"):
            await _create_notification(
                db,
                str(task["approver_id"]),
                "Task Ready for Your Approval",
                f"{user_name} marked '{task.get('title')}' done and awaits your approval.",
            )
    elif new_status == "needs_input":
        updates["status"] = "needs_input"
        target = task.get("approver_id") or task.get("assigned_by_id")
        if target:
            await _create_notification(
                db,
                str(target),
                "Task Needs Partner Input",
                f"{user_name} reverted '{task.get('title')}': {payload.note or 'Clarification needed'}",
            )
    elif new_status == "carried_forward":
        if not payload.non_completion_reason or not payload.non_completion_reason.category.strip():
            raise HTTPException(400, "A non-completion reason is required to carry forward a task.")
        updates["task_date"] = _tomorrow_str()
        updates["priority"] = "P0"
        updates["status"] = "pending"
        updates["carried_from_date"] = task.get("carried_from_date") or task.get("task_date")
        updates["carry_forward_count"] = int(task.get("carry_forward_count") or 0) + 1
        updates["non_completion_reason"] = {
            "category": payload.non_completion_reason.category,
            "note": payload.non_completion_reason.note or "",
            "logged_by": user_name,
            "logged_at": _now_iso(),
        }
    else:
        updates["status"] = new_status

    await db.daily_tasks.update_one({"_id": _oid(task_id)}, {"$set": updates})
    updated = await db.daily_tasks.find_one({"_id": _oid(task_id)})

    # Log system comment for auditability
    if payload.note or new_status in ("done", "reopened", "pending_approval", "needs_input", "carried_forward"):
        status_label = {
            "done": "Approved & Closed task",
            "reopened": "Reopened task",
            "pending_approval": "Marked Done — sent for Approver sign-off",
            "needs_input": "Requested Partner Input",
            "carried_forward": f"Carried forward to tomorrow as P0 ({payload.non_completion_reason.category if payload.non_completion_reason else ''})",
        }.get(new_status, f"Updated status to {new_status}")
        msg = f"[{status_label}]" + (f" {payload.note}" if payload.note else "")
        await db.daily_task_comments.insert_one({
            "task_id": task_id,
            "author_id": user_id,
            "author_name": user_name,
            "author_role": user.get("role") or "staff",
            "message": msg,
            "is_system": True,
            "photos": [],
            "voice_notes": [],
            "created_at": _now_iso(),
        })

    return _stringify(updated)


@daily_tasks_router.get("/daily-tasks/{task_id}/comments")
async def get_task_comments(task_id: str, request: Request):
    db = _get_db(request)
    await _get_user(request)
    docs = await db.daily_task_comments.find({"task_id": task_id}).sort("created_at", 1).to_list(500)
    return [_stringify(d) for d in docs]


@daily_tasks_router.post("/daily-tasks/{task_id}/comments", status_code=201)
async def add_task_comment(task_id: str, payload: DailyTaskCommentCreate, request: Request):
    db = _get_db(request)
    user = await _get_user(request)
    user_id = str(user.get("id") or user.get("_id") or "")
    user_name = user.get("name") or user.get("email") or "User"

    task = await db.daily_tasks.find_one({"_id": _oid(task_id)})
    if not task:
        raise HTTPException(404, "Task not found")
    if task.get("status") == "done":
        raise HTTPException(403, "Task is closed. Reopen the task before sending messages.")

    if not (payload.message or "").strip() and not payload.photos and not payload.voice_notes:
        raise HTTPException(400, "Message, photo, or voice note is required.")

    doc = {
        "task_id": task_id,
        "author_id": user_id,
        "author_name": user_name,
        "author_role": user.get("role") or "staff",
        "message": (payload.message or "").strip(),
        "mentions": payload.mentions,
        "photos": [p.model_dump() for p in payload.photos],
        "voice_notes": [v.model_dump() for v in payload.voice_notes],
        "is_system": False,
        "created_at": _now_iso(),
    }
    res = await db.daily_task_comments.insert_one(doc)
    doc["_id"] = res.inserted_id

    # Notify counterparty
    recipients = {str(task.get("assignee_id") or ""), str(task.get("assigned_by_id") or ""), str(task.get("approver_id") or "")}
    recipients.discard("")
    recipients.discard(user_id)
    for rid in recipients:
        await _create_notification(
            db,
            rid,
            f"New Message on '{task.get('title')}'",
            f"{user_name}: {doc['message'] or 'Sent an attachment'}",
        )

    return _stringify(doc)


@daily_tasks_router.post("/daily-tasks/upload-audio")
async def upload_voice_note(request: Request, file: UploadFile = File(...)):
    await _get_user(request)
    ext = os.path.splitext(file.filename or "voice.webm")[1] or ".webm"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(VOICE_UPLOAD_DIR, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    return {"url": f"/api/daily-tasks/audio/{filename}", "mime_type": file.content_type or "audio/webm"}


@daily_tasks_router.get("/daily-tasks/audio/{filename}")
async def serve_voice_note(filename: str):
    safe_name = os.path.basename(filename)
    filepath = os.path.join(VOICE_UPLOAD_DIR, safe_name)
    if not os.path.isfile(filepath):
        raise HTTPException(404, "Audio file not found")
    return FileResponse(filepath)


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM SHOPPING & CHECKLISTS (Linked to Expenses & Bank Reconciliation)
# ─────────────────────────────────────────────────────────────────────────────

@daily_tasks_router.get("/daily-lists")
async def get_daily_lists(request: Request):
    db = _get_db(request)
    await _get_user(request)
    docs = await db.daily_lists.find({}).sort("created_at", -1).to_list(200)
    return [_stringify(d) for d in docs]


@daily_tasks_router.post("/daily-lists", status_code=201)
async def create_daily_list(payload: DailyListCreate, request: Request):
    db = _get_db(request)
    user = await _get_user(request)
    doc = {
        "title": payload.title.strip(),
        "list_type": payload.list_type,
        "project": payload.project or "Factory Ops",
        "items": [],
        "settlements": [],
        "created_by": user.get("name") or user.get("email") or "User",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    res = await db.daily_lists.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _stringify(doc)


@daily_tasks_router.post("/daily-lists/{list_id}/items", status_code=201)
async def add_daily_list_item(list_id: str, payload: DailyListItemCreate, request: Request):
    db = _get_db(request)
    await _get_user(request)
    list_doc = await db.daily_lists.find_one({"_id": _oid(list_id)})
    if not list_doc:
        raise HTTPException(404, "List not found")

    item = {
        "id": uuid.uuid4().hex[:12],
        "text": payload.text.strip(),
        "qty": (payload.qty or "").strip(),
        "expense_category": payload.expense_category or "Other Expenses",
        "estimated_amount": float(payload.estimated_amount or 0.0),
        "actual_amount": float(payload.actual_amount) if payload.actual_amount is not None else float(payload.estimated_amount or 0.0),
        "shop_note": (payload.shop_note or "").strip(),
        "done": False,
        "settled": False,
        "expense_id": None,
        "settlement_mode": None,
        "bank_account_id": None,
        "created_at": _now_iso(),
    }
    await db.daily_lists.update_one(
        {"_id": _oid(list_id)},
        {"$push": {"items": item}, "$set": {"updated_at": _now_iso()}},
    )
    updated = await db.daily_lists.find_one({"_id": _oid(list_id)})
    return _stringify(updated)


@daily_tasks_router.patch("/daily-lists/{list_id}/items/{item_id}")
async def update_daily_list_item(list_id: str, item_id: str, payload: DailyListItemUpdate, request: Request):
    db = _get_db(request)
    user = await _get_user(request)
    list_doc = await db.daily_lists.find_one({"_id": _oid(list_id)})
    if not list_doc:
        raise HTTPException(404, "List not found")

    items = list(list_doc.get("items") or [])
    target_idx = next((idx for idx, it in enumerate(items) if it.get("id") == item_id), None)
    if target_idx is None:
        raise HTTPException(404, "List item not found")

    item = dict(items[target_idx])
    if item.get("settled") and payload.done is False:
        raise HTTPException(400, "Cannot uncheck an already settled & synced item.")

    if payload.text is not None:
        item["text"] = payload.text.strip()
    if payload.qty is not None:
        item["qty"] = payload.qty.strip()
    if payload.expense_category is not None:
        item["expense_category"] = payload.expense_category
    if payload.estimated_amount is not None:
        item["estimated_amount"] = float(payload.estimated_amount)
    if payload.actual_amount is not None:
        item["actual_amount"] = float(payload.actual_amount)
    if payload.shop_note is not None:
        item["shop_note"] = payload.shop_note.strip()
    if payload.done is not None:
        item["done"] = bool(payload.done)
        if item["done"]:
            item["bought_by"] = user.get("name") or user.get("email") or "User"
            item["bought_at"] = _now_iso()

    items[target_idx] = item
    await db.daily_lists.update_one(
        {"_id": _oid(list_id)},
        {"$set": {"items": items, "updated_at": _now_iso()}},
    )
    updated = await db.daily_lists.find_one({"_id": _oid(list_id)})
    return _stringify(updated)


@daily_tasks_router.delete("/daily-lists/{list_id}/items/{item_id}")
async def delete_daily_list_item(list_id: str, item_id: str, request: Request):
    db = _get_db(request)
    await _get_user(request)
    list_doc = await db.daily_lists.find_one({"_id": _oid(list_id)})
    if not list_doc:
        raise HTTPException(404, "List not found")
    items = [it for it in (list_doc.get("items") or []) if not (it.get("id") == item_id and not it.get("settled"))]
    await db.daily_lists.update_one(
        {"_id": _oid(list_id)},
        {"$set": {"items": items, "updated_at": _now_iso()}},
    )
    updated = await db.daily_lists.find_one({"_id": _oid(list_id)})
    return _stringify(updated)


@daily_tasks_router.post("/daily-lists/{list_id}/settle")
async def settle_daily_list(list_id: str, payload: DailyListSettleIn, request: Request):
    """Sum bought & unsettled items, record Expenses, and Transfer or Withdraw from Bank Account."""
    db = _get_db(request)
    user = await _get_user(request)
    user_name = user.get("name") or user.get("email") or "User"

    list_doc = await db.daily_lists.find_one({"_id": _oid(list_id)})
    if not list_doc:
        raise HTTPException(404, "List not found")

    bank_acc = await db.bank_accounts.find_one({"_id": _oid(payload.bank_account_id)})
    if not bank_acc:
        raise HTTPException(404, "Selected bank account not found")

    items = list(list_doc.get("items") or [])
    to_settle = [it for it in items if it.get("done") and not it.get("settled")]
    if not to_settle:
        raise HTTPException(400, "No bought & unsettled items to settle in this list.")

    total_amount = round(sum(float(it.get("actual_amount") or it.get("estimated_amount") or 0.0) for it in to_settle), 2)
    if total_amount <= 0:
        raise HTTPException(400, "Total settlement amount must be greater than ₹0.")

    settle_date = payload.date or _today_str()
    payee = (payload.payee or list_doc.get("title") or "Shopping List").strip()
    bank_account_id = str(bank_acc["_id"])
    bank_label = bank_acc.get("name") or bank_acc.get("bank_name") or "Bank Account"
    now = _now_iso()

    cash_ledger_id = None
    paid_via = "bank"
    if payload.settlement_mode == "cash_withdrawal":
        paid_via = "cash"
        cl_doc = {
            "bank_account_id": bank_account_id,
            "amount": total_amount,
            "remaining_balance": 0.0,
            "date": settle_date,
            "notes": f"Cash withdrawal for Shopping List: {list_doc.get('title')} ({len(to_settle)} items). {payload.notes or ''}".strip(),
            "source": "daily_list_settlement",
            "created_by": user_name,
            "created_at": now,
        }
        if hasattr(db, "cash_ledger") and db.cash_ledger is not None:
            cl_res = await db.cash_ledger.insert_one(cl_doc)
            cash_ledger_id = str(cl_res.inserted_id)

    expense_ids = []
    for it in items:
        if it.get("done") and not it.get("settled"):
            amt = round(float(it.get("actual_amount") or it.get("estimated_amount") or 0.0), 2)
            if amt <= 0:
                continue
            exp_doc = {
                "category": it.get("expense_category") or "Other Expenses",
                "amount": amt,
                "date": settle_date,
                "payee": payee,
                "notes": f"[List: {list_doc.get('title')}] {it.get('text')}{' (' + it.get('qty') + ')' if it.get('qty') else ''} — {payload.settlement_mode.replace('_', ' ').title()} ({bank_label})",
                "paid_via": paid_via,
                "bank_account_id": bank_account_id,
                "cash_ledger_id": cash_ledger_id,
                "cash_account_id": None,
                "is_recurring": False,
                "status": "confirmed",
                "source_list_id": list_id,
                "source_list_item_id": it.get("id"),
                "created_by": user_name,
                "created_at": now,
            }
            exp_res = await db.expenses.insert_one(exp_doc)
            eid = str(exp_res.inserted_id)
            expense_ids.append(eid)
            it["settled"] = True
            it["settled_at"] = now
            it["expense_id"] = eid
            it["settlement_mode"] = payload.settlement_mode
            it["bank_account_id"] = bank_account_id

    settlement_record = {
        "id": uuid.uuid4().hex[:10],
        "date": settle_date,
        "total_amount": total_amount,
        "item_count": len(expense_ids),
        "settlement_mode": payload.settlement_mode,
        "bank_account_id": bank_account_id,
        "bank_account_name": bank_label,
        "cash_ledger_id": cash_ledger_id,
        "expense_ids": expense_ids,
        "settled_by": user_name,
        "settled_at": now,
    }

    await db.daily_lists.update_one(
        {"_id": _oid(list_id)},
        {
            "$set": {"items": items, "updated_at": now},
            "$push": {"settlements": settlement_record},
        },
    )

    try:
        await sync_bank_account_balance(db, bank_account_id)
    except Exception as exc:
        log.warning(f"Bank balance sync warning after list settlement: {exc}")

    updated = await db.daily_lists.find_one({"_id": _oid(list_id)})
    return {
        "list": _stringify(updated),
        "settlement": settlement_record,
    }
