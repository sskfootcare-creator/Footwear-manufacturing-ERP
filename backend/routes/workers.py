"""Workers, Karigars, Worker Auth/Login, Self-Service & Advances Routes."""

import os
from typing import Optional, List
from io import BytesIO
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Response, Depends, Query
from fastapi.responses import StreamingResponse

from models.workers import (
    WorkerIn,
    SetPinIn,
    WorkerLoginIn,
    ReadyForPickupIn,
    AdvanceIn,
)
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    set_auth_cookies,
    require_roles,
)
from rate_limiter import pdf_rate_limiter
from pdf_card import build_production_card, build_production_card_dual_a4

workers_router = APIRouter(prefix="/api", tags=["Workers & Karigars"])

PRODUCTION_STAGES = [
    "procurement", "cutting", "folding", "attachment",
    "stitching", "lasting", "sole_pasting", "finishing", "qc_pack", "dispatched",
]


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
    user = getattr(request.state, "user", None)
    if user:
        return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    db = getattr(request.app, "mongodb", None) or getattr(server, "db", None)
    fn = await get_current_user_factory(db)
    return await fn(request)


def _format_worker(doc: dict) -> dict:
    if not doc:
        return doc
    sd = stringify(doc)
    sd["has_pin"] = bool(doc.get("pin_hash"))
    sd.pop("pin_hash", None)
    return sd


# ---------- WORKERS CRUD ----------

@workers_router.get("/workers")
async def list_workers(request: Request):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    docs = await db.workers.find({}).sort("name", 1).to_list(500)
    return [_format_worker(d) for d in docs]


@workers_router.post("/workers")
async def create_worker(payload: WorkerIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.workers.insert_one(doc)
    created = await db.workers.find_one({"_id": res.inserted_id})
    return _format_worker(created)


@workers_router.patch("/workers/{wid}")
async def update_worker(wid: str, payload: WorkerIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.workers.update_one({"_id": oid(wid)}, {"$set": update})
    updated = await db.workers.find_one({"_id": oid(wid)})
    return _format_worker(updated)


@workers_router.delete("/workers/{wid}")
async def delete_worker(wid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    await db.workers.update_one({"_id": oid(wid)}, {"$set": {"active": False, "updated_at": now_iso()}})
    return {"ok": True}


@workers_router.patch("/workers/{wid}/set-pin")
async def set_worker_pin(wid: str, payload: SetPinIn, request: Request):
    """Admin/manager: set or reset a worker's 4–6 digit numeric PIN for the karigar app."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    worker = await db.workers.find_one({"_id": oid(wid)})
    if not worker:
        raise HTTPException(404, "Worker not found")
    pin_hash = hash_password(payload.pin)
    await db.workers.update_one(
        {"_id": oid(wid)},
        {"$set": {"pin_hash": pin_hash, "updated_at": now_iso()}}
    )
    return {"ok": True, "worker_id": wid}


# ---------- WORKER AUTH (karigar login) ----------

@workers_router.post("/auth/worker-login")
async def worker_login(payload: WorkerLoginIn, request: Request, response: Response):
    """Worker (karigar) login via phone + PIN. Issues a JWT with role='worker'."""
    import server
    db = getattr(request.app, "mongodb", None) or server.db

    from rate_limiter import _is_test_mode
    test_ip = request.headers.get("x-test-rate-limit-client-ip") if _is_test_mode() else None
    client_ip = test_ip or (request.client.host if request.client else "unknown")
    limiter_key = f"wpin:{client_ip}"
    if hasattr(server, "check_rate_limit"):
        await server.check_rate_limit(limiter_key)

    phone = (payload.phone or "").strip()
    worker = await db.workers.find_one({"phone": phone, "active": {"$ne": False}})
    pin_hash = worker.get("pin_hash", "") if worker else ""

    if not worker or not pin_hash or not verify_password(payload.pin, pin_hash):
        if hasattr(server, "record_login_failure"):
            await server.record_login_failure(limiter_key)
        raise HTTPException(status_code=401, detail="Invalid phone or PIN")

    if hasattr(server, "clear_login_failures"):
        await server.clear_login_failures(limiter_key)

    wid = str(worker["_id"])
    access = create_access_token(wid, phone, "worker", worker_id=wid)
    set_auth_cookies(response, access)
    return {
        "worker_id": wid,
        "name": worker.get("name", ""),
        "skill": worker.get("skill", ""),
        "role": "worker",
        "access_token": access,
    }


# ---------- WORKER SELF-SERVICE ENDPOINTS (/my/...) ----------

@workers_router.get("/my/tasks")
async def my_tasks(request: Request, scope: Optional[str] = "active"):
    """Worker-only: list jobs assigned to the calling worker."""
    u = await _get_user(request)
    if u.get("role") != "worker":
        raise HTTPException(status_code=403, detail="Worker access only")
    caller_wid = u.get("worker_id") or u.get("id")

    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    jobs = await db.production_jobs.find({}).to_list(5000)
    styles_cache = {}

    grouped = {}
    for job in jobs:
        assigns = job.get("assignments") or {}
        po_num = job.get("po_number") or ""
        style_code = job.get("style_code") or ""
        color = job.get("color") or ""
        curr_stage = job.get("stage", "")

        for role, asgn in assigns.items():
            if asgn.get("worker_id") == caller_wid:
                if po_num and po_num != "—":
                    gkey = f"{po_num}_{style_code}_{color}_{curr_stage}_{role}"
                else:
                    gkey = f"single_{str(job['_id'])}_{curr_stage}_{role}"

                if gkey not in grouped:
                    grouped[gkey] = {
                        "po_number": po_num or "—",
                        "client_name": job.get("client_name"),
                        "style_code": style_code,
                        "color": color,
                        "stage": curr_stage,
                        "delivery_date": job.get("delivery_date"),
                        "stage_entered_at": job.get("stage_entered_at"),
                        "stage_deadline": job.get("stage_deadline"),
                        "role": role,
                        "rate_per_pair": asgn.get("rate_per_pair"),
                        "jobs": [],
                    }
                grouped[gkey]["jobs"].append(job)

    results = []
    for gkey, g in grouped.items():
        role = g["role"]
        curr_stage = g["stage"]

        def parse_sz(j):
            s = str(j.get("size", 999))
            return float(s) if s.replace('.', '', 1).isdigit() else 999

        sorted_jobs = sorted(g["jobs"], key=parse_sz)
        primary_job = sorted_jobs[0]
        job_ids = [str(j["_id"]) for j in sorted_jobs]

        sizes = []
        total_ordered = 0
        total_completed = 0
        total_rfp_qty = 0
        rfp_notes = ""
        any_rfp = False

        for j in sorted_jobs:
            q = j.get("quantity") or 0
            c = j.get("completed_qty") or 0
            rfp = j.get("ready_for_pickup") or {}
            rfp_by_me = (rfp.get("worker_id") == caller_wid and rfp.get("role") == role)

            if rfp_by_me:
                any_rfp = True
                rfp_q = rfp.get("completed_qty", 0) or 0
                total_rfp_qty += rfp_q
                if rfp.get("notes"):
                    rfp_notes = rfp.get("notes")
            else:
                rfp_q = 0

            total_ordered += q
            total_completed += c

            sizes.append({
                "job_id": str(j["_id"]),
                "size": str(j.get("size", "—")),
                "ordered_qty": q,
                "completed_qty": c,
                "rfp_qty": rfp_q,
                "is_rfp": rfp_by_me,
            })

        all_completed = any_rfp or (curr_stage == "dispatched")
        is_active = not all_completed

        if scope == "active" and not is_active:
            continue
        elif scope == "completed" and not all_completed:
            continue
        elif scope not in ("active", "completed", "all"):
            if not is_active:
                continue

        style_code = g["style_code"]
        if style_code not in styles_cache:
            st_doc = await db.styles.find_one({"code": style_code})
            styles_cache[style_code] = stringify(st_doc) if st_doc else {}
        st_info = styles_cache[style_code]

        safe = {
            "id": str(primary_job["_id"]),
            "job_ids": job_ids,
            "po_number": g["po_number"],
            "client_name": g["client_name"],
            "style_code": style_code,
            "color": g["color"],
            "total_quantity": total_ordered,
            "quantity": total_ordered,
            "completed_qty": total_completed,
            "stage": curr_stage,
            "stage_entered_at": g["stage_entered_at"],
            "stage_deadline": g["stage_deadline"],
            "ready_for_pickup": {
                "role": role,
                "worker_id": caller_wid,
                "completed_qty": total_rfp_qty,
                "notes": rfp_notes,
            } if any_rfp else None,
            "delivery_date": g["delivery_date"],
            "is_completed": all_completed or any_rfp,
            "image_url": st_info.get("image_url") or st_info.get("image_thumbnail_url"),
            "image_thumbnail_url": st_info.get("image_thumbnail_url") or st_info.get("image_url"),
            "article_name": st_info.get("name", ""),
            "my_assignment": {
                "role": role,
                "rate_per_pair": g["rate_per_pair"],
            },
            "sizes": sizes,
        }
        results.append(safe)

    return results


@workers_router.get("/my/tasks/{job_id}/card.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def my_task_production_card_pdf(job_id: str, request: Request, variant: str = Query("single")):
    """Worker-only: stream the printable A4 Production Card PDF for a job assigned to the calling worker."""
    u = await _get_user(request)
    if u.get("role") != "worker":
        raise HTTPException(status_code=403, detail="Worker access only")
    caller_wid = u.get("worker_id") or u.get("id")

    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job = await db.production_jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "Job not found")

    assigns = job.get("assignments") or {}
    assigned_workers = {a.get("worker_id") for a in assigns.values()}
    if caller_wid not in assigned_workers:
        raise HTTPException(403, "You are not assigned to this job")

    po_num = job.get("po_number")
    style_code = job.get("style_code")
    color = job.get("color")

    q = {}
    if po_num:
        q["po_number"] = po_num
    if style_code:
        q["style_code"] = style_code
    if color:
        q["color"] = color

    sibling_jobs = await db.production_jobs.find(q).to_list(500) if q else [job]
    if not sibling_jobs:
        sibling_jobs = [job]

    j0 = sibling_jobs[0]
    sizes = []
    seen = set()
    for j in sorted(sibling_jobs, key=lambda x: (float(x.get("size", 999)) if str(x.get("size", "")).replace('.', '', 1).isdigit() else 999)):
        sz = str(j.get("size", "—"))
        if sz in seen:
            continue
        seen.add(sz)
        sizes.append({"size": sz, "quantity": j.get("quantity", 0)})

    total_qty = sum(j.get("quantity", 0) for j in sibling_jobs)
    comp = {
        "upper_done": all((j.get("components") or {}).get("upper_done") for j in sibling_jobs),
        "bottom_done": all((j.get("components") or {}).get("bottom_done") for j in sibling_jobs),
        "sole_done": all((j.get("components") or {}).get("sole_done") for j in sibling_jobs),
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
    if variant == "dual":
        pdf_bytes = build_production_card_dual_a4(group, style_d)
    else:
        pdf_bytes = build_production_card(group, style_d)

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="ProductionCard-{group["style_code"]}-{group["color"]}.pdf"'
        },
    )


@workers_router.get("/my/tasks/{job_id}/details")
async def my_task_details(job_id: str, request: Request):
    """Worker-only: return full Production Card data JSON."""
    u = await _get_user(request)
    if u.get("role") != "worker":
        raise HTTPException(status_code=403, detail="Worker access only")
    caller_wid = u.get("worker_id") or u.get("id")

    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job = await db.production_jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "Job not found")

    assigns = job.get("assignments") or {}
    assigned_workers = {a.get("worker_id") for a in assigns.values()}
    if caller_wid not in assigned_workers:
        raise HTTPException(403, "You are not assigned to this job")

    po_num = job.get("po_number")
    style_code = job.get("style_code")
    color = job.get("color")

    q = {}
    if po_num:
        q["po_number"] = po_num
    if style_code:
        q["style_code"] = style_code
    if color:
        q["color"] = color

    sibling_jobs = await db.production_jobs.find(q).to_list(500) if q else [job]
    if not sibling_jobs:
        sibling_jobs = [job]

    j0 = sibling_jobs[0]
    sizes = []
    seen = set()
    total_completed_qty = 0
    for j in sorted(sibling_jobs, key=lambda x: (float(x.get("size", 999)) if str(x.get("size", "")).replace('.', '', 1).isdigit() else 999)):
        sz = str(j.get("size", "—"))
        if sz in seen:
            continue
        seen.add(sz)
        c_qty = j.get("completed_qty", 0) or (j.get("ready_for_pickup") or {}).get("completed_qty", 0) or 0
        total_completed_qty += c_qty
        sizes.append({
            "size": sz,
            "quantity": j.get("quantity", 0),
            "completed_qty": c_qty,
        })

    total_qty = sum(j.get("quantity", 0) for j in sibling_jobs)
    style = await db.styles.find_one({"code": style_code})
    style_d = stringify(style) if style else {}

    my_asgn_role = next((r for r, a in assigns.items() if a.get("worker_id") == caller_wid), None)
    my_asgn = assigns.get(my_asgn_role, {}) if my_asgn_role else {}

    return {
        "job_id": job_id,
        "po_number": j0.get("po_number", "—"),
        "client_name": j0.get("client_name", "—"),
        "style_code": style_code,
        "article_name": style_d.get("name", ""),
        "color": color,
        "delivery_date": j0.get("delivery_date", "—"),
        "stage": j0.get("stage", "—"),
        "sizes": sizes,
        "total_qty": total_qty,
        "total_completed_qty": total_completed_qty,
        "image_url": style_d.get("image_url") or style_d.get("image_display_url"),
        "image_thumbnail_url": style_d.get("image_thumbnail_url") or style_d.get("image_url"),
        "components": j0.get("components") or {},
        "assignments": j0.get("assignments") or {},
        "bom_items": style_d.get("bom_items") or style_d.get("components") or [],
        "my_assignment": {
            "role": my_asgn_role,
            "rate_per_pair": my_asgn.get("rate_per_pair"),
        },
    }


@workers_router.patch("/my/tasks/{job_id}/ready-for-pickup")
async def ready_for_pickup(job_id: str, payload: ReadyForPickupIn, request: Request):
    """Worker-only: flag a job or grouped job (size-wise) as ready for the manager to collect."""
    u = await _get_user(request)
    if u.get("role") != "worker":
        raise HTTPException(status_code=403, detail="Worker access only")
    caller_wid = u.get("worker_id") or u.get("id")

    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    job = await db.production_jobs.find_one({"_id": oid(job_id)})
    if not job:
        raise HTTPException(404, "Job not found")

    current_stage = job.get("stage", "")
    assigns = job.get("assignments") or {}
    
    worker_role = current_stage
    current_asgn = assigns.get(current_stage) or {}
    if current_asgn.get("worker_id") != caller_wid:
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this job at its current stage"
        )

    po_num = job.get("po_number")
    style_code = job.get("style_code")
    color = job.get("color") or ""

    if po_num and po_num != "—":
        q = {"po_number": po_num, "style_code": style_code, "color": color}
        sibling_jobs = await db.production_jobs.find(q).to_list(500)
        sibling_jobs = [j for j in sibling_jobs if (j.get("assignments") or {}).get(worker_role, {}).get("worker_id") == caller_wid]
        if not sibling_jobs:
            sibling_jobs = [job]
    else:
        sibling_jobs = [job]

    now = now_iso()
    sb = payload.size_breakdown or {}

    total_marked = 0
    for j in sibling_jobs:
        jid_str = str(j["_id"])
        sz_str = str(j.get("size", ""))

        if jid_str in sb:
            q_val = int(sb[jid_str])
        elif sz_str in sb:
            q_val = int(sb[sz_str])
        elif payload.completed_qty is not None:
            q_val = payload.completed_qty if len(sibling_jobs) == 1 else j.get("quantity", 0)
        else:
            q_val = j.get("quantity", 0)

        total_marked += q_val

        worker_rate = current_asgn.get("rate_per_pair")
        if worker_rate is None:
            w_doc = await db.workers.find_one({"_id": oid(caller_wid)})
            worker_rate = float(w_doc.get("rate_per_pair", 0) or 0) if w_doc else 0.0
        else:
            worker_rate = float(worker_rate or 0)

        completed_by = {
            "worker_id": str(caller_wid),
            "worker_name": current_asgn.get("worker_name") or u.get("name", ""),
            "rate_per_pair": worker_rate,
            "at": now,
        }

        rfp = {
            "role": worker_role,
            "worker_id": caller_wid,
            "worker_name": u.get("name", ""),
            "rate_per_pair": worker_rate,
            "completed_qty": q_val,
            "completed_by": completed_by,
            "at": now,
            "notes": payload.notes or "",
        }

        update_dict = {
            "ready_for_pickup": rfp,
            "completed_qty": q_val,
            "completed_by": completed_by,
            "updated_at": now,
            f"components.{current_stage}_done": True,
            f"components.{current_stage}_completed_qty": q_val,
            f"assignments.{current_stage}.status": "completed",
            f"assignments.{current_stage}.completed_qty": q_val,
            f"assignments.{current_stage}.completed_at": now,
            f"assignments.{current_stage}.completed_by": completed_by,
        }

        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {
                "$set": update_dict,
                "$push": {
                    "history": {
                        "event": "marked_ready",
                        "role": current_stage,
                        "worker_id": caller_wid,
                        "by": u.get("name", ""),
                        "completed_qty": q_val,
                        "completed_by": completed_by,
                        "notes": payload.notes or "",
                        "at": now,
                    }
                },
            },
        )

    notif = {
        "type": "pickup_ready",
        "job_id": job_id,
        "style_code": job.get("style_code", ""),
        "stage": current_stage,
        "worker_id": caller_wid,
        "worker_name": u.get("name", ""),
        "completed_qty": total_marked,
        "notes": payload.notes or "",
        "at": now,
        "read": False,
        "read_by": None,
        "read_at": None,
        "created_at": now,
    }
    await db.notifications.insert_one(notif)

    rfp_summary = {
        "role": current_stage,
        "worker_id": caller_wid,
        "completed_qty": total_marked,
        "at": now,
        "notes": payload.notes or "",
    }
    return {"ok": True, "completed_qty": total_marked, "ready_for_pickup": rfp_summary}


# ---------- WORKER SELF-SERVICE PAYROLL ----------

@workers_router.get("/my/payroll")
async def my_payroll(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """Worker-only: per-karigar earnings for the calling worker (self-scoped)."""
    u = await _get_user(request)
    if u.get("role") != "worker":
        raise HTTPException(status_code=403, detail="Worker access only")
    caller_wid = u.get("worker_id") or u.get("id")

    if not from_date:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-01")
    if not to_date:
        to_date = datetime.now(timezone.utc).date().isoformat()

    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    from routes.pos import compute_payroll
    full = await compute_payroll(db=db, from_date=from_date, to_date=to_date)
    rows = full.get("rows", [])
    my_row = next((r for r in rows if r.get("worker_id") == caller_wid), None)
    if not my_row:
        my_row = {
            "worker_id": caller_wid,
            "name": u.get("name", ""),
            "skill": u.get("skill", ""),
            "total_pairs": 0,
            "total_earning": 0.0,
            "total_bonus": 0.0,
            "net_payable": 0.0,
            "by_role": {},
            "jobs": [],
        }
    return {"from_date": from_date, "to_date": to_date, "payroll": my_row}


# ---------- ADVANCES & LEDGER ----------

@workers_router.get("/advances")
async def list_advances(request: Request, worker_id: Optional[str] = None):
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    q = {}
    if worker_id:
        q["worker_id"] = worker_id
    docs = await db.advances.find(q).sort("date", -1).to_list(2000)
    return [stringify(d) for d in docs]


@workers_router.post("/advances")
async def create_advance(payload: AdvanceIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    worker = await db.workers.find_one({"_id": oid(payload.worker_id)})
    if not worker:
        raise HTTPException(404, "Worker not found")
    doc = payload.model_dump()
    doc["worker_name"] = worker.get("name", "")
    doc["date"] = doc.get("date") or datetime.now(timezone.utc).date().isoformat()
    doc["settled"] = False
    doc["by"] = u.get("email") or u.get("name", "")
    doc["created_at"] = now_iso()
    res = await db.advances.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc


@workers_router.get("/workers/{wid}/ledger")
async def worker_ledger(wid: str, request: Request,
                        from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Per-worker chronological ledger of earnings (credit) and payments/advances (debit)."""
    await _get_user(request)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    w = await db.workers.find_one({"_id": oid(wid)})
    if not w:
        raise HTTPException(404, "Worker not found")
    worker = stringify(w)

    bonus_pct = float(worker.get("bonus_pct", 0) or 0)
    target_cycle_days = float(worker.get("target_cycle_days", 0) or 0)

    job_q = {}
    if from_date:
        job_q["updated_at"] = {"$gte": from_date}
    if to_date:
        job_q.setdefault("updated_at", {})
        job_q["updated_at"]["$lte"] = to_date + "T23:59:59Z"
    jobs = await db.production_jobs.find(job_q).to_list(5000)

    from routes.pos import extract_role_completions
    entries = []
    worker_map = {wid: worker}
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
                if s["worker_id"] != wid:
                    continue
                role_comp = s["pairs"]
                rate = s["rate"]
                earning = round(rate * role_comp, 2)
                entry_date = (s.get("at") or j.get("updated_at") or j.get("created_at") or "")[:10]
                entries.append({
                    "date": entry_date,
                    "txn_type": "earning",
                    "amount": earning,
                    "description": f"{j.get('po_number','')} · {j.get('style_code','')} · {j.get('color','')} · Sz {j.get('size','')} · {role.upper()} ({role_comp} prs × ₹{rate}/pr)",
                    "ref": j.get("po_number"),
                })

                if bonus_pct > 0 and target_cycle_days > 0:
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
                            delta = (datetime.fromisoformat(done_at) - datetime.fromisoformat(assign_at)).total_seconds() / 86400
                            if 0 <= delta <= target_cycle_days:
                                bonus = round(earning * bonus_pct / 100, 2)
                                entries.append({
                                    "date": done_at[:10],
                                    "txn_type": "bonus",
                                    "amount": bonus,
                                    "description": f"Productivity bonus ({bonus_pct}%) for completing in {delta:.1f} days (target {target_cycle_days}d) · {j.get('style_code')} {j.get('color')}",
                                    "ref": j.get("po_number"),
                                })
                        except Exception:
                            pass

    adv_q = {"worker_id": wid}
    if from_date:
        adv_q["date"] = {"$gte": from_date}
    if to_date:
        adv_q.setdefault("date", {})
        adv_q["date"]["$lte"] = to_date
    advs = await db.advances.find(adv_q).to_list(5000)
    for a in advs:
        a_str = stringify(a)
        amt = float(a_str.get("amount", 0) or 0)
        ttype = a_str.get("txn_type") or "advance"
        if ttype in ("advance", "payment"):
            signed = -amt
        elif ttype == "bonus":
            signed = amt
        else:
            signed = amt
        entries.append({
            "id": a_str.get("id"),
            "date": (a_str.get("date") or a_str.get("created_at", ""))[:10],
            "txn_type": ttype,
            "amount": signed,
            "description": a_str.get("notes") or {
                "advance": "Advance taken", "payment": "Payment paid out",
                "bonus": "Manual bonus", "adjustment": "Adjustment"
            }.get(ttype, ttype),
            "settled": a_str.get("settled", False),
        })

    entries.sort(key=lambda e: (e["date"] or "", 0 if e["txn_type"] in ("earning", "bonus") else 1))

    bal = 0.0
    for e in entries:
        bal = round(bal + e["amount"], 2)
        e["balance"] = bal

    total_earned = round(sum(e["amount"] for e in entries if e["txn_type"] in ("earning", "bonus")), 2)
    total_paid = round(sum(-e["amount"] for e in entries if e["txn_type"] in ("advance", "payment")), 2)
    return {
        "worker": {
            "id": wid, "name": worker.get("name"), "skill": worker.get("skill"),
            "phone": worker.get("phone"), "rate_per_pair": worker.get("rate_per_pair"),
            "bonus_pct": bonus_pct, "target_cycle_days": target_cycle_days,
        },
        "entries": entries,
        "total_earned": total_earned,
        "total_paid": total_paid,
        "balance": round(total_earned - total_paid, 2),
        "from_date": from_date, "to_date": to_date,
    }


@workers_router.patch("/advances/{aid}")
async def update_advance(aid: str, payload: dict, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    update = {}
    if "settled" in payload:
        update["settled"] = bool(payload["settled"])
        update["settled_at"] = now_iso() if payload["settled"] else None
    if "amount" in payload:
        update["amount"] = float(payload["amount"])
    if "notes" in payload:
        update["notes"] = payload["notes"]
    await db.advances.update_one({"_id": oid(aid)}, {"$set": update})
    return stringify(await db.advances.find_one({"_id": oid(aid)}))


@workers_router.delete("/advances/{aid}")
async def delete_advance(aid: str, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")
    await db.advances.delete_one({"_id": oid(aid)})
    return {"ok": True}
