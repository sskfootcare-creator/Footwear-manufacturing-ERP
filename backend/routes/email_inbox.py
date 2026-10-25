"""Gmail Inbox Automation Routes for SSK Footcare ERP.

Automates Goods Receipt Note (GRN) and Payment recording from incoming Gmail messages.
Provides endpoints for:
- Gmail synchronization and live inbox status
- Listing parsed inbox events (pending review, auto-recorded, processed, dismissed)
- One-click approval and manual execution of GRNs and Payments
- Live ERP cross-referencing and test parsing
- Automation rules and thresholds
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Body, Query
from bson import ObjectId

from auth import get_current_user_factory, require_roles
from services.email_service import get_email_config, now_iso
from services.gmail_inbox_service import fetch_recent_emails
from services.gmail_extractor_service import parse_and_match_email, _safe_float

log = logging.getLogger("email_inbox_router")

email_inbox_router = APIRouter(prefix="/api/gmail-inbox", tags=["Gmail Inbox Automation"])


def oid(val: Any) -> ObjectId:
    if isinstance(val, ObjectId):
        return val
    try:
        return ObjectId(str(val))
    except Exception:
        raise HTTPException(400, f"Invalid ObjectId: {val}")


def stringify(doc: Any) -> Any:
    if isinstance(doc, list):
        return [stringify(x) for x in doc]
    if isinstance(doc, dict):
        res = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                res[k] = str(v)
            elif isinstance(v, dict):
                res[k] = stringify(v)
            elif isinstance(v, list):
                res[k] = stringify(v)
            else:
                res[k] = v
        if "_id" in res and "id" not in res:
            res["id"] = res["_id"]
        return res
    return doc


def _decorate_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    erp_match = item.get("erp_match") or {}
    matched_inv = erp_match.get("matched_invoice") or {}
    matched_bank = erp_match.get("matched_bank_account") or {}
    extracted = item.get("extracted_data") or {}

    item["matched_invoice_id"] = str(matched_inv.get("id") or matched_inv.get("_id") or "") or None
    item["matched_invoice_no"] = matched_inv.get("invoice_no")
    item["matched_bank_account_id"] = str(matched_bank.get("id") or matched_bank.get("_id") or "") or None
    item["matched_bank_name"] = matched_bank.get("name") or matched_bank.get("bank_name")
    item["auto_recorded"] = (item.get("status") == "auto_recorded")

    if "total_accepted" in extracted and "accepted_pairs" not in extracted:
        extracted["accepted_pairs"] = extracted["total_accepted"]
    if "total_rejected" in extracted and "rejected_pairs" not in extracted:
        extracted["rejected_pairs"] = extracted["total_rejected"]
    if "total_received" in extracted and "total_pairs" not in extracted:
        extracted["total_pairs"] = extracted["total_received"]
    if "reference" in extracted and "utr_number" not in extracted:
        extracted["utr_number"] = extracted["reference"]
    if "mode" in extracted and "payment_mode" not in extracted:
        extracted["payment_mode"] = extracted["mode"]

    return item


def get_db(request: Request):
    db = getattr(request.app, "mongodb", None)
    if db is None:
        import server
        db = server.db
    return db


async def _get_user(request: Request) -> dict:
    if request is None:
        return {"id": "system", "email": "system@sskfootcare.com", "role": "admin", "roles": ["admin"]}
    user = getattr(getattr(request, "state", None), "user", None)
    if user:
        return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    db = get_db(request)
    from auth import get_current_user_factory
    getter = await get_current_user_factory(db)
    return await getter(request)



# ── Status and Sync Endpoints ──────────────────────────────────────────────────

@email_inbox_router.get("/status")
async def get_inbox_status(request: Request):
    """Return Gmail connection status, pending items count, and sync timestamp."""
    user = await _get_user(request)
    db = get_db(request)
    cfg = await get_email_config(db)

    has_oauth = bool(cfg.get("gmail_client_id") and cfg.get("gmail_refresh_token"))
    has_app_pwd = bool(cfg.get("gmail_user") and cfg.get("gmail_app_password"))
    connected = has_oauth or has_app_pwd

    # Count pending and processed inbox events
    pending_grn = await db.gmail_inbox_items.count_documents({"category": "GRN", "status": {"$in": ["pending", "pending_review"]}})
    pending_pay = await db.gmail_inbox_items.count_documents({"category": "PAYMENT", "status": {"$in": ["pending", "pending_review"]}})
    auto_recorded = await db.gmail_inbox_items.count_documents({"status": "auto_recorded"})
    processed = await db.gmail_inbox_items.count_documents({"status": "processed"})

    rules_doc = await db.settings.find_one({"_id": "gmail_automation_rules"}) or {}
    last_sync = rules_doc.get("last_sync_at")

    return {
        "connected": connected,
        "email_account": cfg.get("gmail_user") or ("Authorized Google Account" if has_oauth else ""),
        "provider": cfg.get("provider") or ("gmail_api" if has_oauth else "smtp"),
        "pending_grn_count": pending_grn,
        "pending_payment_count": pending_pay,
        "auto_recorded_count": auto_recorded,
        "processed_count": processed,
        "total_active_count": pending_grn + pending_pay,
        "last_sync_at": last_sync,
        "automation_rules": {
            "auto_record_grn": rules_doc.get("auto_record_grn", False),
            "auto_record_payments": rules_doc.get("auto_record_payments", False),
            "min_confidence": rules_doc.get("min_confidence", 0.90),
            "auto_sync_interval_mins": rules_doc.get("auto_sync_interval_mins", 15),
            "require_exact_invoice_match": rules_doc.get("require_exact_invoice_match", True),
        }
    }


@email_inbox_router.post("/sync")
async def sync_gmail_inbox(
    request: Request,
    max_results: int = Query(30, ge=1, le=100),
):
    """Fetch recent emails from Gmail, parse them, match with ERP records, and auto-record if rules allow."""
    user = await _get_user(request)
    require_roles("admin", "manager", "sales")(user)
    db = get_db(request)
    cfg = await get_email_config(db)

    # 1. Fetch raw messages from Gmail
    try:
        emails = await fetch_recent_emails(cfg, max_results=max_results)
    except Exception as e:
        log.error("Failed to fetch emails from Gmail: %s", e)
        raise HTTPException(400, f"Gmail fetch failed: {str(e)}")

    rules_doc = await db.settings.find_one({"_id": "gmail_automation_rules"}) or {}
    auto_grn = rules_doc.get("auto_record_grn", False)
    auto_pay = rules_doc.get("auto_record_payments", False)
    min_conf = float(rules_doc.get("min_confidence", 0.90))

    new_items = 0
    auto_recorded_count = 0
    parsed_items = []

    for email_dict in emails:
        mid = email_dict.get("message_id")
        if not mid:
            continue

        # Check if already processed or stored
        existing = await db.gmail_inbox_items.find_one({"message_id": mid})
        if existing and existing.get("status") in ["processed", "auto_recorded", "dismissed"]:
            continue

        # 2. Parse and match
        parsed = await parse_and_match_email(email_dict, db=db)
        if parsed.get("category") == "OTHER":
            continue

        # 3. Check Auto-Recording criteria
        auto_record_done = False
        if parsed.get("category") == "GRN" and auto_grn and parsed.get("confidence", 0) >= min_conf:
            if parsed.get("erp_match", {}).get("is_matched") and parsed.get("erp_match", {}).get("matched_invoice"):
                try:
                    res_rec = await _record_grn_internal(db, parsed["extracted_data"], parsed["erp_match"]["matched_invoice"]["id"], by="Gmail Auto-Recorder")
                    parsed["status"] = "auto_recorded"
                    parsed["recorded_entity"] = res_rec
                    auto_recorded_count += 1
                    auto_record_done = True
                except Exception as gre:
                    log.warning("Auto-GRN recording failed for %s: %s", mid, gre)

        elif parsed.get("category") == "PAYMENT" and auto_pay and parsed.get("confidence", 0) >= min_conf:
            if parsed.get("erp_match", {}).get("is_matched") and parsed.get("erp_match", {}).get("suggested_allocations"):
                try:
                    res_pay = await _record_payment_internal(db, parsed["extracted_data"], parsed["erp_match"]["suggested_allocations"], by="Gmail Auto-Recorder")
                    parsed["status"] = "auto_recorded"
                    parsed["recorded_entity"] = res_pay
                    auto_recorded_count += 1
                    auto_record_done = True
                except Exception as pre:
                    log.warning("Auto-Payment recording failed for %s: %s", mid, pre)

        # 4. Upsert into database
        if existing:
            await db.gmail_inbox_items.update_one({"_id": existing["_id"]}, {"$set": parsed})
            parsed["_id"] = existing["_id"]
        else:
            insert_res = await db.gmail_inbox_items.insert_one(parsed)
            parsed["_id"] = insert_res.inserted_id
            new_items += 1

        parsed_items.append(parsed)

    # Update last sync timestamp
    await db.settings.update_one(
        {"_id": "gmail_automation_rules"},
        {"$set": {"last_sync_at": now_iso()}},
        upsert=True
    )

    return {
        "status": "success",
        "fetched_count": len(emails),
        "relevant_count": len(parsed_items),
        "new_items_saved": new_items,
        "auto_recorded_count": auto_recorded_count,
        "scanned": len(emails),
        "created": new_items,
        "auto_recorded": auto_recorded_count,
        "items": stringify([_decorate_item(p) for p in parsed_items[:20]]),
    }


# ── Listing and Review Endpoints ───────────────────────────────────────────────

@email_inbox_router.get("/items")
async def list_inbox_items(
    request: Request,
    category: Optional[str] = Query(None, description="GRN | PAYMENT | ALL"),
    status: Optional[str] = Query(None, description="pending_review | processed | auto_recorded | dismissed | ALL"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Retrieve inbox items with filtering by category and processing status."""
    user = await _get_user(request)
    db = get_db(request)
    query: Dict[str, Any] = {}

    if category and category.upper() != "ALL":
        c_u = category.upper()
        query["category"] = {"$in": [c_u, c_u.lower()]}

    if status and status.upper() != "ALL":
        s_low = status.lower()
        if s_low in ("pending", "pending_review"):
            query["status"] = {"$in": ["pending", "pending_review"]}
        elif s_low in ("recorded", "processed"):
            query["status"] = {"$in": ["recorded", "processed", "auto_recorded"]}
        else:
            query["status"] = s_low

    cursor = db.gmail_inbox_items.find(query).sort("created_at", -1).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    total = await db.gmail_inbox_items.count_documents(query)

    return {
        "items": stringify([_decorate_item(it) for it in items]),
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@email_inbox_router.get("/items/{item_id}")
async def get_inbox_item(item_id: str, request: Request):
    """Fetch details of a single inbox event."""
    user = await _get_user(request)
    db = get_db(request)
    item = await db.gmail_inbox_items.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(404, "Inbox item not found")
    return stringify(_decorate_item(item))


# ── Approval & Dismissal Endpoints ─────────────────────────────────────────────

@email_inbox_router.post("/items/{item_id}/approve")
async def approve_and_record_item(
    item_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
):
    """Approve and record the parsed GRN or Payment into SSK Footwear ERP core collections."""
    user = await _get_user(request)
    require_roles("admin", "manager", "sales")(user)
    db = get_db(request)

    item = await db.gmail_inbox_items.find_one({"_id": oid(item_id)})
    if not item:
        raise HTTPException(404, "Inbox item not found")

    if item.get("status") in ["processed", "auto_recorded"]:
        raise HTTPException(400, "Item has already been recorded")

    cat = str(item.get("category") or "").upper()
    extracted = item.get("extracted_data") or {}
    erp_match = item.get("erp_match") or {}

    # Map frontend override aliases
    if payload.get("override_amount") is not None:
        extracted["amount"] = _safe_float(payload["override_amount"])
    if payload.get("override_utr") is not None:
        extracted["reference"] = payload["override_utr"]
    if payload.get("override_payment_date") is not None:
        extracted["payment_date"] = payload["override_payment_date"]
    if payload.get("override_accepted_qty") is not None:
        extracted["total_accepted"] = int(payload["override_accepted_qty"])
    if payload.get("override_rejected_qty") is not None:
        extracted["total_rejected"] = int(payload["override_rejected_qty"])
    if payload.get("remarks") is not None:
        extracted["notes"] = payload["remarks"]
    if payload.get("payment_mode") is not None:
        extracted["mode"] = payload["payment_mode"]

    # Merge remaining user overrides if supplied in body
    for k, v in payload.items():
        if v is not None and not k.startswith("override_"):
            extracted[k] = v

    recorded_info = None

    # 1. APPROVE GRN
    if cat == "GRN":
        inv_id = (
            payload.get("invoice_id")
            or payload.get("override_invoice_id")
            or item.get("matched_invoice_id")
            or erp_match.get("matched_invoice", {}).get("id")
            or erp_match.get("matched_invoice", {}).get("_id")
        )
        if not inv_id:
            raise HTTPException(400, "An Invoice must be selected to record a GRN.")
        recorded_info = await _record_grn_internal(db, extracted, str(inv_id), by=user.get("email", "admin"))

    # 2. APPROVE PAYMENT
    elif cat == "PAYMENT":
        allocations = payload.get("allocations") or erp_match.get("suggested_allocations") or {}
        inv_id = (
            payload.get("invoice_id")
            or payload.get("override_invoice_id")
            or item.get("matched_invoice_id")
            or erp_match.get("matched_invoice", {}).get("id")
            or erp_match.get("matched_invoice", {}).get("_id")
        )
        if not allocations:
            amt = float(extracted.get("amount") or 0.0)
            if inv_id and amt > 0:
                allocations = {str(inv_id): amt}
            else:
                raise HTTPException(400, "At least one Invoice allocation is required to record payment.")

        bank_acc_id = (
            payload.get("bank_account_id")
            or payload.get("override_bank_account_id")
            or item.get("matched_bank_account_id")
            or erp_match.get("matched_bank_account", {}).get("id")
            or erp_match.get("matched_bank_account", {}).get("_id")
        )
        recorded_info = await _record_payment_internal(
            db, extracted, allocations, bank_account_id=str(bank_acc_id) if bank_acc_id else None, by=user.get("email", "admin")
        )

    else:
        raise HTTPException(400, f"Cannot approve item of category '{cat}'")

    # Update item status
    await db.gmail_inbox_items.update_one(
        {"_id": item["_id"]},
        {"$set": {
            "status": "processed",
            "processed_at": now_iso(),
            "processed_by": user.get("email", "admin"),
            "recorded_entity": recorded_info,
            "updated_at": now_iso(),
        }}
    )

    return {
        "status": "success",
        "message": f"Successfully recorded {cat} in SSK Footwear ERP.",
        "recorded_entity": recorded_info,
    }


@email_inbox_router.post("/items/{item_id}/dismiss")
async def dismiss_inbox_item(item_id: str, request: Request):
    """Dismiss an irrelevant or duplicate email item."""
    user = await _get_user(request)
    require_roles("admin", "manager", "sales")(user)
    db = get_db(request)
    res = await db.gmail_inbox_items.update_one(
        {"_id": oid(item_id)},
        {"$set": {"status": "dismissed", "dismissed_by": user.get("email", "admin"), "updated_at": now_iso()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Inbox item not found")
    return {"status": "success", "message": "Item marked as dismissed."}


# ── Interactive Test & Rules Endpoints ─────────────────────────────────────────

@email_inbox_router.post("/test-parse")
async def test_parse_email_text(
    request: Request,
    payload: Dict[str, Any] = Body(...),
):
    """Test the parser and ERP matcher against custom email subject and text without saving."""
    user = await _get_user(request)
    db = get_db(request)
    mock_email = {
        "message_id": "test_mock_preview",
        "subject": payload.get("subject", ""),
        "body_text": payload.get("body_text", ""),
        "from_header": payload.get("sender", "test.sender@example.com"),
        "from_email": payload.get("sender", "test.sender@example.com"),
        "sender_name": "Preview Tester",
        "received_iso": now_iso(),
        "snippet": payload.get("body_text", "")[:120],
        "attachments": [],
    }
    result = await parse_and_match_email(mock_email, db=db)
    return stringify(_decorate_item(result))


@email_inbox_router.get("/rules")
async def get_automation_rules(request: Request):
    """Get active auto-record configuration."""
    user = await _get_user(request)
    db = get_db(request)
    doc = await db.settings.find_one({"_id": "gmail_automation_rules"}) or {}
    return {
        "auto_record_grn": doc.get("auto_record_grn", False),
        "auto_record_payments": doc.get("auto_record_payments", False),
        "min_confidence": doc.get("min_confidence", 0.90),
        "auto_sync_interval_mins": doc.get("auto_sync_interval_mins", 15),
        "require_exact_invoice_match": doc.get("require_exact_invoice_match", True),
    }


@email_inbox_router.put("/rules")
async def update_automation_rules(
    request: Request,
    payload: Dict[str, Any] = Body(...),
):
    """Update auto-record thresholds and toggles."""
    user = await _get_user(request)
    require_roles("admin", "manager")(user)
    db = get_db(request)

    save_doc = {
        "auto_record_grn": bool(payload.get("auto_record_grn", False)),
        "auto_record_payments": bool(payload.get("auto_record_payments", False)),
        "min_confidence": max(0.50, min(1.0, float(payload.get("min_confidence", 0.90)))),
        "auto_sync_interval_mins": max(5, int(payload.get("auto_sync_interval_mins", 15))),
        "require_exact_invoice_match": bool(payload.get("require_exact_invoice_match", True)),
        "updated_at": now_iso(),
        "updated_by": user.get("email", "admin"),
    }
    await db.settings.update_one(
        {"_id": "gmail_automation_rules"},
        {"$set": save_doc},
        upsert=True
    )
    return {"status": "success", "rules": save_doc}


# ── Internal Recording Helpers ─────────────────────────────────────────────────

async def _record_grn_internal(db, extracted_data: Dict[str, Any], invoice_id: str, by: str = "system") -> Dict[str, Any]:
    """Internal helper to create a valid GRN in db.grns matching pos.py logic."""
    from routes.pos import next_grn_no

    inv = await db.invoices.find_one({"_id": oid(invoice_id)})
    if not inv:
        inv = await db.invoices.find_one({"_id": str(invoice_id)})
    if not inv:
        raise HTTPException(404, f"Target invoice {invoice_id} not found.")

    inv_id_str = str(inv["_id"])
    inv_no_str = inv.get("invoice_no") or ""

    existing_grn = await db.grns.find_one({
        "$or": [{"invoice_id": inv_id_str}, {"invoice_no": inv_no_str}]
    })
    grn_no = existing_grn["grn_no"] if existing_grn and existing_grn.get("grn_no") else await next_grn_no(db=db)

    # Prepare line items
    raw_lines = extracted_data.get("line_items") or []
    lines = []
    total_disp = total_recv = total_acc = total_rej = 0

    if raw_lines:
        for li in raw_lines:
            d = int(li.get("dispatched_qty") or 0)
            r = int(li.get("received_qty") if li.get("received_qty") is not None else d)
            rej = int(li.get("rejected_qty") or 0)
            acc = int(li.get("accepted_qty") if li.get("accepted_qty") is not None else max(0, r - rej))
            lines.append({
                "style_code": li.get("style_code") or "",
                "description": li.get("description") or "",
                "color": li.get("color") or "",
                "size": str(li.get("size") or ""),
                "dispatched_qty": d,
                "received_qty": r,
                "accepted_qty": acc,
                "rejected_qty": rej,
                "rejection_reason": li.get("rejection_reason"),
            })
            total_disp += d
            total_recv += r
            total_acc += acc
            total_rej += rej
    else:
        # Construct single aggregate line
        tot_d = int(extracted_data.get("total_dispatched") or inv.get("total_pairs") or inv.get("total_quantity") or 0)
        tot_r = int(extracted_data.get("total_received") or tot_d)
        tot_rej = int(extracted_data.get("total_rejected") or 0)
        tot_acc = int(extracted_data.get("total_accepted") or max(0, tot_r - tot_rej))
        lines.append({
            "style_code": inv.get("style_code") or "BATCH",
            "description": f"GRN for {inv_no_str}",
            "color": "Standard",
            "size": "Mixed",
            "dispatched_qty": tot_d,
            "received_qty": tot_r,
            "accepted_qty": tot_acc,
            "rejected_qty": tot_rej,
            "rejection_reason": None,
        })
        total_disp = tot_d
        total_recv = tot_r
        total_acc = tot_acc
        total_rej = tot_rej

    grn_date = extracted_data.get("grn_date") or extracted_data.get("received_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    doc = {
        "grn_no": grn_no,
        "grn_date": grn_date,
        "received_date": grn_date,
        "invoice_id": inv_id_str,
        "invoice_no": inv_no_str,
        "po_id": inv.get("po_id"),
        "po_number": inv.get("po_number"),
        "client_name": inv.get("client_name"),
        "client_reference": extracted_data.get("client_reference") or "",
        "notes": extracted_data.get("notes") or f"Automated via Gmail Inbox by {by}",
        "line_items": lines,
        "total_dispatched": total_disp,
        "total_received": total_recv,
        "total_accepted": total_acc,
        "total_rejected": total_rej,
        "by": by,
        "updated_at": now_iso(),
    }

    if existing_grn:
        doc["created_at"] = existing_grn.get("created_at") or now_iso()
        await db.grns.update_one({"_id": existing_grn["_id"]}, {"$set": doc})
        doc["_id"] = str(existing_grn["_id"])
    else:
        doc["created_at"] = now_iso()
        res = await db.grns.insert_one(doc)
        doc["_id"] = str(res.inserted_id)

    # Flag invoice as GRN recorded
    await db.invoices.update_one(
        {"_id": inv["_id"]},
        {"$set": {"grn_recorded": True, "grn_date": grn_date, "grn_no": grn_no}}
    )

    log.info("Successfully recorded GRN %s for Invoice %s", grn_no, inv_no_str)
    return {
        "type": "grn",
        "grn_id": doc["_id"],
        "grn_no": grn_no,
        "invoice_no": inv_no_str,
        "total_accepted": total_acc,
        "total_rejected": total_rej,
    }


async def _record_payment_internal(
    db,
    extracted_data: Dict[str, Any],
    allocations: Dict[str, float],
    bank_account_id: Optional[str] = None,
    by: str = "system",
) -> Dict[str, Any]:
    """Internal helper to record client payment into db.payments and sync bank balances."""
    from routes.pos import next_payment_no

    total_amount = round(sum(float(v) for v in allocations.values()), 2)
    if total_amount <= 0:
        total_amount = round(float(extracted_data.get("amount") or 0.0), 2)
    if total_amount <= 0:
        raise HTTPException(400, "Payment amount must be greater than zero.")

    payment_no = await next_payment_no(db=db)
    payment_date = extracted_data.get("payment_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mode = extracted_data.get("mode") or "Bank Transfer"
    reference = extracted_data.get("reference") or ""

    # Resolve bank account name
    bank_name = extracted_data.get("bank") or ""
    if bank_account_id:
        try:
            ba = await db.bank_accounts.find_one({"_id": oid(bank_account_id)})
            if ba:
                bank_name = ba.get("bank_name") or ba.get("name") or bank_name
        except Exception:
            pass

    invoice_ids = list(allocations.keys())

    doc = {
        "payment_no": payment_no,
        "payment_date": payment_date,
        "amount": total_amount,
        "mode": mode,
        "reference": reference,
        "bank": bank_name,
        "bank_account_id": str(bank_account_id) if bank_account_id else "",
        "account_type": "bank",
        "notes": extracted_data.get("notes") or f"Automated via Gmail Inbox by {by}",
        "type": "client_payment",
        "invoice_ids": invoice_ids,
        "allocations": allocations,
        "by": by,
        "created_at": now_iso(),
    }

    res = await db.payments.insert_one(doc)
    doc["_id"] = str(res.inserted_id)

    # Sync live bank account balance if account selected
    if bank_account_id:
        try:
            from routes.banking import sync_bank_account_balance
            await sync_bank_account_balance(db, str(bank_account_id))
        except Exception as se:
            log.warning("Could not sync bank account balance: %s", se)

    # Check and update invoice statuses
    for iid, alloc_amt in allocations.items():
        try:
            inv = await db.invoices.find_one({"_id": oid(iid)})
            if inv:
                # Recalculate status
                grand_tot = float(inv.get("net_amount") or inv.get("grand_total") or 0.0)
                # Query all payments for this invoice
                all_p = await db.payments.find({"invoice_ids": str(inv["_id"])}).to_list(100)
                total_paid = sum(float(p.get("allocations", {}).get(str(inv["_id"]), 0.0) or p.get("amount", 0.0)) for p in all_p)
                new_status = "PAID" if total_paid >= (grand_tot - 0.5) else ("PARTIALLY_PAID" if total_paid > 0 else inv.get("status"))
                await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": new_status, "total_paid": total_paid}})
        except Exception as ie:
            log.warning("Could not update invoice %s payment status: %s", iid, ie)

    log.info("Successfully recorded Client Payment %s of ₹%s (Ref: %s)", payment_no, total_amount, reference)
    return {
        "type": "payment",
        "payment_id": doc["_id"],
        "payment_no": payment_no,
        "amount": total_amount,
        "reference": reference,
        "invoices_affected": len(invoice_ids),
    }
