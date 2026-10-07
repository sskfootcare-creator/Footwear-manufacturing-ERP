"""Investor entity, advances, repayments, and portal endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Response, Depends

from models.investors import (
    InvestorIn, InvestorUpdate, InvestorAdvanceCreateIn, InvestorBatchAdvanceCreateIn,
    InvestorRepayActionIn, InvestorBulkRepayActionIn, SetInvestorPinIn, InvestorLoginIn
)
from auth import (
    hash_password, verify_password, create_access_token, set_auth_cookies,
    get_current_user_factory
)
from services.investor_service import compute_investor_funding_required
from services.supabase_investor_service import (
    sync_investor_advance_to_supabase,
    sync_investor_repayment_to_supabase
)

log = logging.getLogger(__name__)

investors_router = APIRouter(prefix="/api", tags=["Investors"])


def oid(val: Any) -> ObjectId:
    if isinstance(val, ObjectId):
        return val
    try:
        return ObjectId(str(val))
    except Exception:
        raise HTTPException(400, f"Invalid ObjectId: {val}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: Any) -> Any:
    if isinstance(doc, list):
        return [stringify(d) for d in doc]
    if isinstance(doc, dict):
        res = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                res[k] = str(v)
            elif isinstance(v, (dict, list)):
                res[k] = stringify(v)
            else:
                res[k] = v
        return res
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc


def get_db(request: Request):
    import server
    return getattr(request.app, "mongodb", None) or getattr(server, "db", None)


async def _get_user(request: Request):
    import server
    db = get_db(request)
    getter = await get_current_user_factory(db)
    return await getter(request)


def require_admin_or_manager(user: dict):
    role = user.get("role", "")
    if role not in ("admin", "manager"):
        raise HTTPException(403, "Admin or Manager access required")


def require_investor(user: dict):
    role = user.get("role", "")
    if role != "investor":
        raise HTTPException(403, "Investor access required")


# =============================================================================
# 1. INVESTOR CRUD & MANAGEMENT (Stage 1 & 2)
# =============================================================================

@investors_router.post("/investors", status_code=201)
async def create_investor(payload: InvestorIn, request: Request):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    clean_phone = (payload.phone or "").strip()
    clean_email = (payload.email or "").strip().lower()

    if clean_phone:
        existing = await db.investors.find_one({"phone": clean_phone, "active": {"$ne": False}})
        if existing:
            raise HTTPException(400, f"Investor with phone {clean_phone} already exists")

    doc = {
        "name": payload.name.strip(),
        "contact": (payload.contact or "").strip(),
        "phone": clean_phone,
        "email": clean_email,
        "default_margin_per_pair": float(payload.default_margin_per_pair),
        "active": payload.active,
        "notes": payload.notes or "",
        "created_at": now_iso(),
        "created_by": user.get("email") or user.get("name", ""),
    }
    if payload.pin:
        doc["pin_hash"] = hash_password(payload.pin)

    res = await db.investors.insert_one(doc)
    doc["_id"] = res.inserted_id
    doc.pop("pin_hash", None)
    return stringify(doc)


@investors_router.get("/investors")
async def list_investors(request: Request, active_only: bool = False):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    q = {"active": True} if active_only else {}
    docs = await db.investors.find(q).sort("created_at", -1).to_list(1000)
    for d in docs:
        d.pop("pin_hash", None)
    return stringify(docs)


async def generate_bank_statement_ledger(
    db,
    investor_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """
    Builds a double-entry bank passbook statement of all commercial transactions
    between SSK Footcare and Investor Partners (GL 2020-INV Advances Payable & 5030-INV Margin).
    """
    investor_name = "Consolidated Capital Partners Account"
    investor_info = None
    if investor_id:
        inv = await db.investors.find_one({"_id": oid(investor_id)})
        if inv:
            investor_name = inv.get("name", "Capital Partner")
            investor_info = {
                "id": str(inv["_id"]),
                "name": inv.get("name"),
                "contact": inv.get("contact"),
                "phone": inv.get("phone"),
                "email": inv.get("email"),
            }

    valid_inv_ids = {str(i["_id"]) for i in await db.investors.find({}, {"_id": 1}).to_list(1000)}
    adv_q = {}
    rep_q = {}
    if investor_id:
        adv_q["investor_id"] = investor_id
        rep_q["investor_id"] = investor_id
    elif valid_inv_ids:
        adv_q["investor_id"] = {"$in": list(valid_inv_ids)}
        rep_q["investor_id"] = {"$in": list(valid_inv_ids)}

    advances = await db.investor_advances.find(adv_q).to_list(2000)
    repayments = await db.investor_repayments.find(rep_q).to_list(2000)

    # Build advance lookup for repayment enrichments
    adv_map = {str(a["_id"]): a for a in advances}

    entries = []

    # 1. Advance Disbursements (Credit to Capital Liability Account 2020)
    for adv in advances:
        adv_id_str = str(adv["_id"])
        ts = adv.get("created_at") or adv.get("advance_date") or ""
        date_str = adv.get("advance_date") or (ts[:10] if ts else "")
        amount = float(adv.get("amount") or 0.0)
        po_num = adv.get("po_number") or "N/A"
        pairs = int(adv.get("pairs") or 0)
        is_rollover = "Rollover" in (adv.get("notes") or "")

        entries.append({
            "id": f"ADV-{adv_id_str}",
            "raw_id": adv_id_str,
            "type": "ADVANCE",
            "category": "Rollover Capital Commit" if is_rollover else "PO Capital Commit",
            "voucher_no": f"VCH-ADV-{adv_id_str[-6:].upper()}",
            "date": date_str,
            "timestamp": ts,
            "batch_id": adv.get("batch_id"),
            "investor_id": str(adv.get("investor_id", "")),
            "investor_name": adv.get("investor_name", investor_name),
            "po_number": po_num,
            "pairs": pairs,
            "narration": f"{'Rollover Advance' if is_rollover else 'PO Advance Disbursement'}: #{po_num} ({pairs:,} pairs) · Credit to Advances Payable GL 2020",
            "channel": "ROLLOVER_JOURNAL" if is_rollover else "CAPITAL_INFLOW",
            "debit": 0.0,
            "credit": round(amount, 2),
            "margin_paid": 0.0,
            "cash_outflow": 0.0,
            "status": (adv.get("status") or "active").upper(),
            "gl_account": "2020-INV (Payable Inflow)",
        })

    # 2. Settlements & Repayments (Debits to Capital Liability 2020 & Margin 5030)
    for rep in repayments:
        rep_id_str = str(rep["_id"])
        ts = rep.get("created_at") or rep.get("payout_date") or ""
        date_str = rep.get("payout_date") or (ts[:10] if ts else "")
        principal = float(rep.get("principal_amount") or 0.0)
        margin = float(rep.get("margin_amount") or 0.0)
        total_payout = float(rep.get("total_payout") or 0.0)
        reinvested = bool(rep.get("reinvested"))

        parent_adv = adv_map.get(str(rep.get("advance_id", "")))
        po_num = (parent_adv.get("po_number") if parent_adv else None) or "PO"
        pairs = int(rep.get("pairs") or (parent_adv.get("pairs") if parent_adv else 0) or 0)
        mode = rep.get("mode") or "Bank Transfer"

        if reinvested:
            target_ref = rep.get("target_po_number") or (f"Advance #{str(rep.get('reinvested_into_advance_id'))[-6:]}" if rep.get("reinvested_into_advance_id") else "New PO")
            narration = f"Capital Rollover & Margin Payout: Principal ₹{principal:,.2f} rolled into {target_ref}; Margin ₹{margin:,.2f} disbursed via {mode}"
            channel = "ROLLOVER_JOURNAL"
            category = "Reinvestment Rollover"
            cash_out = margin  # Only margin leaves the bank/cash in reinvestment!
        else:
            narration = f"Full Settlement: PO #{po_num} Principal ₹{principal:,.2f} (GL 2020) + Margin Yield ₹{margin:,.2f} (GL 5030) via {mode}"
            channel = "DIRECT_BANK"
            category = "Full Cash Repayment"
            cash_out = total_payout

        entries.append({
            "id": f"REP-{rep_id_str}",
            "raw_id": rep_id_str,
            "type": "REINVESTMENT" if reinvested else "REPAYMENT",
            "category": category,
            "voucher_no": f"VCH-REP-{rep_id_str[-6:].upper()}",
            "date": date_str,
            "timestamp": ts,
            "batch_id": rep.get("batch_repayment_id"),
            "investor_id": str(rep.get("investor_id", "")),
            "investor_name": rep.get("investor_name", investor_name),
            "po_number": po_num,
            "pairs": pairs,
            "narration": narration,
            "channel": channel,
            "debit": round(principal, 2),
            "credit": 0.0,
            "margin_paid": round(margin, 2),
            "cash_outflow": round(cash_out, 2),
            "status": "REINVESTED" if reinvested else "SETTLED",
            "gl_account": "2020-INV / 5030-INV",
        })

    # Sort strictly chronologically to accurately compute the running balance
    entries.sort(key=lambda x: (x["date"] or "", x["timestamp"] or "", x["id"]))

    running_bal = 0.0
    for e in entries:
        running_bal += (e["credit"] - e["debit"])
        e["running_balance"] = round(running_bal, 2)

    # Calculate global totals
    total_credit_inflow = sum(e["credit"] for e in entries)
    total_principal_repaid = sum(e["debit"] for e in entries)
    total_margin_paid = sum(e["margin_paid"] for e in entries)
    total_cash_outflow = sum(e["cash_outflow"] for e in entries)
    current_outstanding = running_bal

    # Apply date filters if provided
    filtered_entries = entries
    opening_balance = 0.0
    if from_date:
        before_entries = [e for e in entries if e["date"] < from_date]
        opening_balance = sum(e["credit"] - e["debit"] for e in before_entries)
        filtered_entries = [e for e in filtered_entries if e["date"] >= from_date]
    if to_date:
        filtered_entries = [e for e in filtered_entries if e["date"] <= to_date]

    if category and category != "all":
        cat_lower = category.lower()
        if cat_lower == "advances":
            filtered_entries = [e for e in filtered_entries if e["type"] == "ADVANCE"]
        elif cat_lower == "repayments":
            filtered_entries = [e for e in filtered_entries if e["type"] == "REPAYMENT"]
        elif cat_lower == "reinvestments":
            filtered_entries = [e for e in filtered_entries if e["type"] == "REINVESTMENT"]

    # Return in reverse chronological order for statement viewing (latest at top)
    display_entries = list(reversed(filtered_entries))

    return {
        "statement_title": "SSK Footcare Industrial - Investor Ledger & Statement of Account",
        "account_holder": investor_name,
        "investor_info": investor_info,
        "statement_date": datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S UTC"),
        "period_from": from_date or (entries[0]["date"] if entries else "Genesis"),
        "period_to": to_date or (entries[-1]["date"] if entries else datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "currency": "INR",
        "gl_accounts": [
            {"code": "2020-INV", "name": "Investor Advances Payable (Current Liability)"},
            {"code": "5030-INV", "name": "Investor Margin / Finance Cost (Direct Cost)"},
            {"code": "1010/1020", "name": "Settlement Disbursed via Bank / Cash Accounts"}
        ],
        "opening_balance": round(opening_balance, 2),
        "total_credit_inflow": round(total_credit_inflow, 2),
        "total_principal_repaid": round(total_principal_repaid, 2),
        "total_margin_paid": round(total_margin_paid, 2),
        "total_cash_outflow": round(total_cash_outflow, 2),
        "closing_balance": round(current_outstanding, 2),
        "transactions_count": len(display_entries),
        "transactions": display_entries,
    }


@investors_router.get("/investors/ledger")
@investors_router.get("/investors/bank-statement")
@investors_router.get("/investors-bank-statement")
async def get_bank_statement(
    request: Request,
    investor_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category: Optional[str] = None,
):
    """Admin/Manager endpoint to retrieve certified Investor Ledger for partner accounts."""
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)
    statement = await generate_bank_statement_ledger(
        db,
        investor_id=investor_id,
        from_date=from_date,
        to_date=to_date,
        category=category,
    )
    return statement


@investors_router.get("/investors/{iid}")
async def get_investor(iid: str, request: Request):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    doc = await db.investors.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Investor not found")
    doc.pop("pin_hash", None)
    return stringify(doc)


@investors_router.patch("/investors/{iid}")
async def update_investor(iid: str, payload: InvestorUpdate, request: Request):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    doc = await db.investors.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Investor not found")

    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if updates:
        updates["updated_at"] = now_iso()
        await db.investors.update_one({"_id": oid(iid)}, {"$set": updates})
        doc.update(updates)
    doc.pop("pin_hash", None)
    return stringify(doc)


@investors_router.post("/investors/{iid}/pin")
async def set_investor_pin(iid: str, payload: SetInvestorPinIn, request: Request):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    doc = await db.investors.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Investor not found")

    pin_hash = hash_password(payload.pin)
    await db.investors.update_one({"_id": oid(iid)}, {"$set": {"pin_hash": pin_hash, "updated_at": now_iso()}})
    return {"ok": True, "message": "Investor PIN set successfully"}


# =============================================================================
# 2. ADVANCE CREATION (Stage 2)
# =============================================================================

async def _create_batch_advances_internal(
    iid: str,
    po_ids: List[str],
    include_opex: bool,
    margin_per_pair: Optional[float],
    advance_date: Optional[str],
    notes: Optional[str],
    bank_account_id: Optional[str],
    payment_mode: Optional[str],
    reference: Optional[str],
    user: Dict[str, Any],
    db: Any
):
    investor = await db.investors.find_one({"_id": oid(iid)})
    if not investor:
        raise HTTPException(404, "Investor not found")

    if margin_per_pair is not None and margin_per_pair >= 0:
        margin_per_pair_used = float(margin_per_pair)
    else:
        margin_per_pair_used = float(investor.get("default_margin_per_pair", 10.0))

    adv_date = advance_date or datetime.now(timezone.utc).date().isoformat()
    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"

    # Resolve bank account if provided
    bank_doc = None
    if bank_account_id:
        try:
            bank_doc = await db.bank_accounts.find_one({"_id": oid(bank_account_id)})
        except Exception:
            pass
        if not bank_doc:
            bank_doc = await db.bank_accounts.find_one({"_id": str(bank_account_id)})

    created_advances = []
    total_funding = 0.0
    total_pairs = 0

    for idx, p_id in enumerate(po_ids):
        # Apply opex once on the first PO of the batch if include_opex is True
        apply_opex = bool(include_opex) if idx == 0 else False
        funding = await compute_investor_funding_required(
            po_id=p_id,
            include_opex=apply_opex,
            db=db
        )

        pairs = int(funding.get("pairs", 0))
        amt = round(float(funding["total_funding_required"]), 2)
        total_funding += amt
        total_pairs += pairs

        adv_doc = {
            "investor_id": str(investor["_id"]),
            "investor_name": investor.get("name", "Investor"),
            "po_id": str(funding["po_id"]),
            "po_number": funding.get("po_number", ""),
            "pairs": pairs,
            "amount": amt,
            "margin_per_pair": margin_per_pair_used,
            "batch_id": batch_id,
            "bank_account_id": str(bank_account_id) if bank_account_id else None,
            "bank_name": (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else None,
            "payment_mode": payment_mode or "Bank Transfer",
            "reference": reference or "",
            "breakdown": {
                "bom_cost": funding["breakdown"]["bom_cost"],
                "labour_cost": funding["breakdown"]["labour_cost"],
                "labor_cost": funding["breakdown"]["labor_cost"],
                "opex_cost": funding["breakdown"]["opex_cost"],
                "opex_included": apply_opex,
            },
            "advance_date": adv_date,
            "status": "active",
            "notes": notes or "",
            "created_at": now_iso(),
            "created_by": user.get("email") or user.get("name", ""),
        }
        res = await db.investor_advances.insert_one(adv_doc)
        adv_doc["_id"] = res.inserted_id

        # Inflow to Company Bank Account via db.payments
        if bank_account_id:
            try:
                payment_doc = {
                    "payment_date": adv_date,
                    "amount": amt,
                    "mode": payment_mode or "Bank Transfer",
                    "reference": reference or "",
                    "bank": (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else "Bank",
                    "bank_account_id": str(bank_account_id),
                    "account_type": "bank",
                    "notes": f"Investor capital advance for PO #{adv_doc.get('po_number')} ({investor.get('name')})",
                    "type": "investor_funding",
                    "investor_id": str(investor["_id"]),
                    "investor_name": investor.get("name", "Investor"),
                    "advance_id": str(adv_doc["_id"]),
                    "po_id": str(adv_doc.get("po_id", "")),
                    "po_number": adv_doc.get("po_number", ""),
                    "by": user.get("email") or user.get("name", ""),
                    "created_at": now_iso(),
                }
                await db.payments.insert_one(payment_doc)
            except Exception as pe:
                log.warning("Could not insert banking payment for advance %s: %s", adv_doc["_id"], pe)

        try:
            sync_investor_advance_to_supabase(adv_doc, investor_doc=investor)
        except Exception as se:
            log.warning("Supabase investor advance sync skipped for PO %s: %s", adv_doc.get("po_number"), se)

        created_advances.append(adv_doc)

    # Live synchronize bank account balance
    if bank_account_id:
        try:
            from routes.banking import sync_bank_account_balance
            await sync_bank_account_balance(db, str(bank_account_id))
        except Exception as be:
            log.warning("Could not sync live bank balance: %s", be)

    return {
        "ok": True,
        "batch_id": batch_id,
        "investor_id": str(investor["_id"]),
        "investor_name": investor.get("name", ""),
        "total_amount": round(total_funding, 2),
        "total_pairs": total_pairs,
        "count": len(created_advances),
        "advances": stringify(created_advances)
    }


@investors_router.post("/investors/{iid}/advances", status_code=201)
async def create_investor_advance(iid: str, payload: InvestorAdvanceCreateIn, request: Request):
    """
    Creates an investor advance (single PO or multiple POs in batch) via Stage 1's calculation:
    Takes include_opex and an optional margin_per_pair override as input.
    Deposits funding directly into selected company bank account.
    """
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    # Batch support directly on this endpoint if po_ids list is provided
    if payload.po_ids and len(payload.po_ids) > 0:
        return await _create_batch_advances_internal(
            iid=iid,
            po_ids=payload.po_ids,
            include_opex=payload.include_opex,
            margin_per_pair=payload.margin_per_pair,
            advance_date=payload.advance_date,
            notes=payload.notes,
            bank_account_id=payload.bank_account_id,
            payment_mode=payload.payment_mode,
            reference=payload.reference,
            user=user,
            db=db
        )

    if not payload.po_id:
        raise HTTPException(400, "Either 'po_id' or 'po_ids' must be specified")

    investor = await db.investors.find_one({"_id": oid(iid)})
    if not investor:
        raise HTTPException(404, "Investor not found")

    # Margin per pair used: explicit override or investor default
    if payload.margin_per_pair is not None and payload.margin_per_pair >= 0:
        margin_per_pair_used = float(payload.margin_per_pair)
    else:
        margin_per_pair_used = float(investor.get("default_margin_per_pair", 10.0))

    # Compute funding required using Stage 1 calculation (reuses compute_po_profitability)
    funding = await compute_investor_funding_required(
        po_id=payload.po_id,
        include_opex=payload.include_opex,
        db=db
    )

    bank_doc = None
    if payload.bank_account_id:
        try:
            bank_doc = await db.bank_accounts.find_one({"_id": oid(payload.bank_account_id)})
        except Exception:
            pass
        if not bank_doc:
            bank_doc = await db.bank_accounts.find_one({"_id": str(payload.bank_account_id)})

    amt = round(float(funding["total_funding_required"]), 2)
    adv_date = payload.advance_date or datetime.now(timezone.utc).date().isoformat()

    adv_doc = {
        "investor_id": str(investor["_id"]),
        "investor_name": investor.get("name", "Investor"),
        "po_id": str(funding["po_id"]),
        "po_number": funding.get("po_number", ""),
        "pairs": funding.get("pairs", 0),
        "amount": amt,
        "margin_per_pair": margin_per_pair_used,
        "bank_account_id": str(payload.bank_account_id) if payload.bank_account_id else None,
        "bank_name": (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else None,
        "payment_mode": payload.payment_mode or "Bank Transfer",
        "reference": payload.reference or "",
        "breakdown": {
            "bom_cost": funding["breakdown"]["bom_cost"],
            "labour_cost": funding["breakdown"]["labour_cost"],
            "labor_cost": funding["breakdown"]["labor_cost"],
            "opex_cost": funding["breakdown"]["opex_cost"],
            "opex_included": bool(payload.include_opex),
        },
        "advance_date": adv_date,
        "status": "active",  # "active" | "repaid" | "reinvested"
        "notes": payload.notes or "",
        "created_at": now_iso(),
        "created_by": user.get("email") or user.get("name", ""),
    }

    res = await db.investor_advances.insert_one(adv_doc)
    adv_doc["_id"] = res.inserted_id

    # Inflow to Company Bank Account via db.payments
    if payload.bank_account_id:
        try:
            payment_doc = {
                "payment_date": adv_date,
                "amount": amt,
                "mode": payload.payment_mode or "Bank Transfer",
                "reference": payload.reference or "",
                "bank": (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else "Bank",
                "bank_account_id": str(payload.bank_account_id),
                "account_type": "bank",
                "notes": f"Investor capital advance for PO #{adv_doc.get('po_number')} ({investor.get('name')})",
                "type": "investor_funding",
                "investor_id": str(investor["_id"]),
                "investor_name": investor.get("name", "Investor"),
                "advance_id": str(adv_doc["_id"]),
                "po_id": str(adv_doc.get("po_id", "")),
                "po_number": adv_doc.get("po_number", ""),
                "by": user.get("email") or user.get("name", ""),
                "created_at": now_iso(),
            }
            await db.payments.insert_one(payment_doc)
            from routes.banking import sync_bank_account_balance
            await sync_bank_account_balance(db, str(payload.bank_account_id))
        except Exception as pe:
            log.warning("Could not sync live bank balance for advance %s: %s", adv_doc["_id"], pe)

    # Optional mirror to Supabase financial ledger (fire-and-forget safety)
    try:
        sync_investor_advance_to_supabase(adv_doc, investor_doc=investor)
    except Exception as se:
        log.warning("Supabase investor advance sync skipped: %s", se)

    return stringify(adv_doc)


@investors_router.post("/investors/{iid}/advances/batch", status_code=201)
async def create_investor_batch_advances(iid: str, payload: InvestorBatchAdvanceCreateIn, request: Request):
    """Fund multiple purchase orders simultaneously under one investor."""
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)
    return await _create_batch_advances_internal(
        iid=iid,
        po_ids=payload.po_ids,
        include_opex=payload.include_opex,
        margin_per_pair=payload.margin_per_pair,
        advance_date=payload.advance_date,
        notes=payload.notes,
        bank_account_id=payload.bank_account_id,
        payment_mode=payload.payment_mode,
        reference=payload.reference,
        user=user,
        db=db
    )


@investors_router.get("/investors/{iid}/advances")
async def list_advances_for_investor(iid: str, request: Request):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    docs = await db.investor_advances.find({"investor_id": str(iid)}).sort("advance_date", -1).to_list(1000)
    return stringify(docs)


@investors_router.get("/investors-advances/all")
async def list_all_advances(
    request: Request,
    status: Optional[str] = None,
    investor_id: Optional[str] = None,
    po_id: Optional[str] = None
):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    q = {}
    if status:
        q["status"] = status
    if investor_id:
        q["investor_id"] = investor_id
    if po_id:
        q["po_id"] = po_id

    docs = await db.investor_advances.find(q).sort("created_at", -1).to_list(1000)
    return stringify(docs)


@investors_router.get("/investors-advances/preview-calculation")
async def preview_advance_calculation(
    po_id: str,
    include_opex: bool = False,
    request: Request = None
):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)
    funding = await compute_investor_funding_required(
        po_id=po_id,
        include_opex=include_opex,
        db=db
    )
    return stringify(funding)


@investors_router.post("/investors-advances/preview-batch")
async def preview_batch_advance_calculation(
    payload: Dict[str, Any],
    request: Request
):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    po_ids = payload.get("po_ids") or []
    include_opex = bool(payload.get("include_opex", False))

    if not po_ids:
        raise HTTPException(400, "po_ids list cannot be empty")

    items = []
    total_funding = 0.0
    total_pairs = 0

    for idx, p_id in enumerate(po_ids):
        apply_opex = include_opex if idx == 0 else False
        funding = await compute_investor_funding_required(
            po_id=p_id,
            include_opex=apply_opex,
            db=db
        )
        amt = round(float(funding["total_funding_required"]), 2)
        pairs = int(funding.get("pairs", 0))
        total_funding += amt
        total_pairs += pairs
        items.append({
            "po_id": str(funding["po_id"]),
            "po_number": funding.get("po_number", ""),
            "pairs": pairs,
            "funding_required": amt,
            "breakdown": funding.get("breakdown", {}),
        })

    return stringify({
        "items": items,
        "total_funding_required": round(total_funding, 2),
        "total_pairs": total_pairs,
        "count": len(items)
    })


# =============================================================================
# 3. REPAYMENT & REINVESTMENT TRIGGER (Stage 4 & Stage 3)
# =============================================================================

@investors_router.get("/investors/advances/pending-client-payment")
async def get_advances_pending_action(request: Request):
    """
    Finds active investor advances whose PO has invoices with client payments landed.
    Surfaces the two explicit actions: 'Repay in full' and 'Pay margin & reinvest into [new PO]'.
    """
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    active_advances = await db.investor_advances.find({"status": "active"}).to_list(1000)
    results = []

    for adv in active_advances:
        po_id_str = str(adv.get("po_id", ""))
        po_num = adv.get("po_number", "")

        inv_query = []
        if po_id_str:
            try:
                inv_query.append({"po_id": oid(po_id_str)})
            except Exception:
                pass
            inv_query.append({"po_id": po_id_str})
        if po_num:
            inv_query.append({"po_number": po_num})

        invoices = []
        if inv_query:
            invoices = await db.invoices.find({"$or": inv_query}).to_list(100)

        total_invoiced = sum(float(inv.get("grand_total") or 0.0) for inv in invoices)
        invoice_ids = [str(inv["_id"]) for inv in invoices]

        # Check client payments against these invoices
        payments = []
        if invoice_ids:
            payments = await db.payments.find({"invoice_ids": {"$in": invoice_ids}}).to_list(100)

        total_received = sum(float(p.get("amount") or 0.0) for p in payments)

        # Margin calculation
        pairs = int(adv.get("pairs") or 0)
        margin_rate = float(adv.get("margin_per_pair") or 10.0)
        principal = float(adv.get("amount") or 0.0)
        margin_amount = round(pairs * margin_rate, 2)
        total_payout = round(principal + margin_amount, 2)

        results.append({
            "advance": stringify(adv),
            "invoices_count": len(invoices),
            "total_invoiced": total_invoiced,
            "total_client_payments_received": total_received,
            "has_client_payment": total_received > 0,
            "calculated_principal": principal,
            "calculated_margin": margin_amount,
            "calculated_total_payout": total_payout,
            "available_actions": [
                {
                    "action": "repay_in_full",
                    "label": "Repay in Full",
                    "description": f"Pay principal (₹{principal}) + margin (₹{margin_amount}) = ₹{total_payout}"
                },
                {
                    "action": "reinvest",
                    "label": "Pay Margin & Reinvest Principal",
                    "description": f"Disburse margin (₹{margin_amount}) in cash and roll forward principal (₹{principal}) into a new PO"
                }
            ]
        })

    return results


@investors_router.post("/investors/advances/{adv_id}/repay")
async def execute_repay_or_reinvest(adv_id: str, payload: InvestorRepayActionIn, request: Request):
    """
    Executes repayment action explicitly:
    - 'repay_in_full': Debit Investor Advances Payable (principal) + Debit Investor Margin (margin),
                       Credit Bank/Cash for the full amount — real cash out.
    - 'reinvest': Margin paid in cash first; principal rolled forward as non-cash entry into new PO advance.
    """
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    adv = await db.investor_advances.find_one({"_id": oid(adv_id)})
    if not adv:
        raise HTTPException(404, "Investor advance not found")
    if adv.get("status") != "active":
        raise HTTPException(400, f"Advance status is '{adv.get('status')}', only active advances can be repaid/reinvested")

    investor = await db.investors.find_one({"_id": oid(adv.get("investor_id"))})
    if not investor:
        raise HTTPException(404, "Investor associated with advance not found")

    pairs = int(adv.get("pairs") or 0)
    principal_amount = round(float(adv.get("amount") or 0.0), 2)

    # Negotiable margin rate per deal
    if payload.margin_per_pair_override is not None and payload.margin_per_pair_override >= 0:
        margin_per_pair_used = float(payload.margin_per_pair_override)
    else:
        margin_per_pair_used = float(adv.get("margin_per_pair") or investor.get("default_margin_per_pair", 10.0))

    margin_amount = round(margin_per_pair_used * pairs, 2)
    payout_date = payload.payout_date or datetime.now(timezone.utc).date().isoformat()

    if payload.action == "repay_in_full":
        # ── (a) Straight Repayment Path ──────────────────────────────────────
        repayment_doc = {
            "advance_id": str(adv["_id"]),
            "investor_id": str(adv["investor_id"]),
            "investor_name": adv.get("investor_name", ""),
            "principal_amount": principal_amount,
            "margin_per_pair_used": margin_per_pair_used,
            "pairs": pairs,
            "margin_amount": margin_amount,
            "total_payout": round(principal_amount + margin_amount, 2),
            "payout_date": payout_date,
            "reinvested": False,
            "reinvested_into_advance_id": None,
            "mode": payload.mode or "Bank Transfer",
            "bank_account_id": payload.bank_account_id,
            "notes": payload.notes or "",
            "created_at": now_iso(),
            "created_by": user.get("email") or user.get("name", ""),
        }
        res_rep = await db.investor_repayments.insert_one(repayment_doc)
        repayment_doc["_id"] = res_rep.inserted_id

        # Update advance status to repaid
        await db.investor_advances.update_one(
            {"_id": adv["_id"]},
            {"$set": {
                "status": "repaid",
                "repayment_id": str(res_rep.inserted_id),
                "repaid_at": now_iso()
            }}
        )

        # Inflow/Outflow to Company Bank Account via db.payments
        eff_mode = payload.payment_mode or payload.mode or "Bank Transfer"
        eff_ref = payload.reference or payload.notes or ""
        if payload.bank_account_id and eff_mode != "Cash":
            try:
                bank_doc = await db.bank_accounts.find_one({"_id": oid(payload.bank_account_id)})
                if not bank_doc:
                    bank_doc = await db.bank_accounts.find_one({"_id": str(payload.bank_account_id)})
                pmt_doc = {
                    "payment_date": payout_date,
                    "amount": round(principal_amount + margin_amount, 2),
                    "mode": eff_mode,
                    "reference": eff_ref,
                    "bank": (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else "Bank",
                    "bank_account_id": str(payload.bank_account_id),
                    "account_type": "bank",
                    "notes": f"Investor repayment for PO #{adv.get('po_number')} ({investor.get('name')})",
                    "type": "investor_repayment",
                    "investor_id": str(investor["_id"]),
                    "investor_name": investor.get("name", "Investor"),
                    "advance_id": str(adv["_id"]),
                    "repayment_id": str(res_rep.inserted_id),
                    "by": user.get("email") or user.get("name", ""),
                    "created_at": now_iso(),
                }
                await db.payments.insert_one(pmt_doc)
                from routes.banking import sync_bank_account_balance
                await sync_bank_account_balance(db, str(payload.bank_account_id))
            except Exception as pe:
                log.warning("Could not sync live bank balance for repayment %s: %s", repayment_doc["_id"], pe)

        # Sync Straight Repayment to Supabase Ledger
        try:
            sync_investor_repayment_to_supabase(
                repayment_doc=repayment_doc,
                investor_doc=investor,
                is_reinvestment=False,
                payment_mode=payload.mode or "BANK_TRANSFER",
                bank_account_id=payload.bank_account_id
            )
        except Exception as se:
            log.warning("Supabase repayment sync skipped: %s", se)

        return {
            "ok": True,
            "action": "repay_in_full",
            "repayment": stringify(repayment_doc),
            "advance_status": "repaid"
        }

    elif payload.action == "reinvest":
        # ── (b) Reinvestment Path ───────────────────────────────────────────
        if not payload.target_po_id:
            raise HTTPException(400, "target_po_id is required for reinvestment")

        target_po = await db.pos.find_one({"_id": oid(payload.target_po_id)})
        if not target_po:
            target_po = await db.pos.find_one({"_id": str(payload.target_po_id)})
        if not target_po:
            target_po = await db.pos.find_one({"po_number": str(payload.target_po_id)})
        if not target_po:
            raise HTTPException(404, f"Target Purchase Order '{payload.target_po_id}' not found")

        # Compute target PO funding breakdown
        funding_target = await compute_investor_funding_required(
            po_id=str(target_po["_id"]),
            include_opex=bool(payload.include_opex_for_reinvestment),
            db=db
        )

        # Create new advance rolled forward with the same principal amount
        new_advance_doc = {
            "investor_id": str(adv["investor_id"]),
            "investor_name": adv.get("investor_name", ""),
            "po_id": str(target_po["_id"]),
            "po_number": target_po.get("po_number", ""),
            "pairs": funding_target.get("pairs", 0),
            "amount": principal_amount,  # rolled over principal
            "margin_per_pair": margin_per_pair_used,
            "breakdown": funding_target.get("breakdown", {}),
            "advance_date": payout_date,
            "status": "active",
            "rolled_over_from_advance_id": str(adv["_id"]),
            "notes": f"Reinvested from Advance {str(adv['_id'])}",
            "created_at": now_iso(),
            "created_by": user.get("email") or user.get("name", ""),
        }
        res_new_adv = await db.investor_advances.insert_one(new_advance_doc)
        new_advance_doc["_id"] = res_new_adv.inserted_id

        # Record repayment of old advance (margin paid, principal rolled forward)
        repayment_doc = {
            "advance_id": str(adv["_id"]),
            "investor_id": str(adv["investor_id"]),
            "investor_name": adv.get("investor_name", ""),
            "principal_amount": principal_amount,
            "margin_per_pair_used": margin_per_pair_used,
            "pairs": pairs,
            "margin_amount": margin_amount,
            "total_payout": margin_amount,  # Cash payout is margin only
            "payout_date": payout_date,
            "reinvested": True,
            "reinvested_into_advance_id": str(res_new_adv.inserted_id),
            "target_po_id": str(target_po["_id"]),
            "target_po_number": target_po.get("po_number", ""),
            "mode": payload.mode or "Bank Transfer",
            "bank_account_id": payload.bank_account_id,
            "notes": payload.notes or "",
            "created_at": now_iso(),
            "created_by": user.get("email") or user.get("name", ""),
        }
        res_rep = await db.investor_repayments.insert_one(repayment_doc)
        repayment_doc["_id"] = res_rep.inserted_id

        # Update old advance status to reinvested
        await db.investor_advances.update_one(
            {"_id": adv["_id"]},
            {"$set": {
                "status": "reinvested",
                "reinvested_into_advance_id": str(res_new_adv.inserted_id),
                "repayment_id": str(res_rep.inserted_id),
                "reinvested_at": now_iso()
            }}
        )

        # Margin payout via db.payments
        eff_mode = payload.payment_mode or payload.mode or "Bank Transfer"
        eff_ref = payload.reference or payload.notes or ""
        if payload.bank_account_id and margin_amount > 0 and eff_mode != "Cash":
            try:
                bank_doc = await db.bank_accounts.find_one({"_id": oid(payload.bank_account_id)})
                if not bank_doc:
                    bank_doc = await db.bank_accounts.find_one({"_id": str(payload.bank_account_id)})
                pmt_doc = {
                    "payment_date": payout_date,
                    "amount": margin_amount,
                    "mode": eff_mode,
                    "reference": eff_ref,
                    "bank": (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else "Bank",
                    "bank_account_id": str(payload.bank_account_id),
                    "account_type": "bank",
                    "notes": f"Investor margin yield disbursement for PO #{adv.get('po_number')} ({investor.get('name')})",
                    "type": "investor_repayment",
                    "investor_id": str(investor["_id"]),
                    "investor_name": investor.get("name", "Investor"),
                    "advance_id": str(adv["_id"]),
                    "repayment_id": str(res_rep.inserted_id),
                    "by": user.get("email") or user.get("name", ""),
                    "created_at": now_iso(),
                }
                await db.payments.insert_one(pmt_doc)
                from routes.banking import sync_bank_account_balance
                await sync_bank_account_balance(db, str(payload.bank_account_id))
            except Exception as pe:
                log.warning("Could not sync live bank balance for margin disbursement %s: %s", repayment_doc["_id"], pe)

        # Sync Reinvestment to Supabase Ledger
        try:
            sync_investor_repayment_to_supabase(
                repayment_doc=repayment_doc,
                investor_doc=investor,
                is_reinvestment=True,
                new_advance_doc=new_advance_doc,
                payment_mode=payload.mode or "BANK_TRANSFER",
                bank_account_id=payload.bank_account_id
            )
        except Exception as se:
            log.warning("Supabase reinvestment sync skipped: %s", se)

        return {
            "ok": True,
            "action": "reinvest",
            "margin_payout": margin_amount,
            "new_advance": stringify(new_advance_doc),
            "repayment": stringify(repayment_doc),
            "old_advance_status": "reinvested"
        }

    else:
        raise HTTPException(400, f"Unsupported action '{payload.action}'")


@investors_router.post("/investors/advances/bulk-repay")
async def execute_bulk_repay(payload: InvestorBulkRepayActionIn, request: Request):
    """
    Executes repayment or reinvestment for multiple advances simultaneously in a single transaction action.
    """
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    if not payload.advance_ids:
        raise HTTPException(400, "advance_ids list cannot be empty")

    batch_repayment_id = f"BREP-{uuid.uuid4().hex[:8].upper()}"
    payout_date = payload.payout_date or datetime.now(timezone.utc).date().isoformat()

    results = []
    total_principal = 0.0
    total_margin = 0.0
    total_payout = 0.0

    target_po = None
    funding_target = None
    if payload.action == "reinvest":
        if not payload.target_po_id:
            raise HTTPException(400, "target_po_id is required for reinvestment")
        target_po = await db.pos.find_one({"_id": oid(payload.target_po_id)})
        if not target_po:
            target_po = await db.pos.find_one({"_id": str(payload.target_po_id)})
        if not target_po:
            target_po = await db.pos.find_one({"po_number": str(payload.target_po_id)})
        if not target_po:
            raise HTTPException(404, f"Target Purchase Order '{payload.target_po_id}' not found")

        funding_target = await compute_investor_funding_required(
            po_id=str(target_po["_id"]),
            include_opex=bool(payload.include_opex_for_reinvestment),
            db=db
        )

    for adv_id in payload.advance_ids:
        adv = await db.investor_advances.find_one({"_id": oid(adv_id)})
        if not adv:
            raise HTTPException(404, f"Investor advance '{adv_id}' not found")
        if adv.get("status") != "active":
            raise HTTPException(400, f"Advance '{adv.get('po_number') or adv_id}' is not active (status: {adv.get('status')})")

        investor = await db.investors.find_one({"_id": oid(adv.get("investor_id"))})
        if not investor:
            raise HTTPException(404, f"Investor for advance '{adv_id}' not found")

        pairs = int(adv.get("pairs") or 0)
        principal_amount = round(float(adv.get("amount") or 0.0), 2)

        if payload.margin_per_pair_override is not None and payload.margin_per_pair_override >= 0:
            margin_per_pair_used = float(payload.margin_per_pair_override)
        else:
            margin_per_pair_used = float(adv.get("margin_per_pair") or investor.get("default_margin_per_pair", 10.0))

        margin_amount = round(margin_per_pair_used * pairs, 2)
        total_principal += principal_amount
        total_margin += margin_amount

        if payload.action == "repay_in_full":
            payout = round(principal_amount + margin_amount, 2)
            total_payout += payout

            repayment_doc = {
                "advance_id": str(adv["_id"]),
                "investor_id": str(adv["investor_id"]),
                "investor_name": adv.get("investor_name", ""),
                "principal_amount": principal_amount,
                "margin_per_pair_used": margin_per_pair_used,
                "pairs": pairs,
                "margin_amount": margin_amount,
                "total_payout": payout,
                "payout_date": payout_date,
                "batch_repayment_id": batch_repayment_id,
                "reinvested": False,
                "reinvested_into_advance_id": None,
                "mode": payload.mode or "Bank Transfer",
                "bank_account_id": payload.bank_account_id,
                "notes": payload.notes or "",
                "created_at": now_iso(),
                "created_by": user.get("email") or user.get("name", ""),
            }
            res_rep = await db.investor_repayments.insert_one(repayment_doc)
            repayment_doc["_id"] = res_rep.inserted_id

            await db.investor_advances.update_one(
                {"_id": adv["_id"]},
                {"$set": {
                    "status": "repaid",
                    "repayment_id": str(res_rep.inserted_id),
                    "batch_repayment_id": batch_repayment_id,
                    "repaid_at": now_iso()
                }}
            )

            try:
                sync_investor_repayment_to_supabase(
                    repayment_doc=repayment_doc,
                    investor_doc=investor,
                    is_reinvestment=False,
                    payment_mode=payload.mode or "BANK_TRANSFER",
                    bank_account_id=payload.bank_account_id
                )
            except Exception as se:
                log.warning("Supabase bulk repayment sync skipped for advance %s: %s", adv_id, se)

            results.append(repayment_doc)

        elif payload.action == "reinvest":
            payout = margin_amount
            total_payout += payout

            new_advance_doc = {
                "investor_id": str(adv["investor_id"]),
                "investor_name": adv.get("investor_name", ""),
                "po_id": str(target_po["_id"]),
                "po_number": target_po.get("po_number", ""),
                "pairs": funding_target.get("pairs", 0),
                "amount": principal_amount,
                "margin_per_pair": margin_per_pair_used,
                "breakdown": funding_target.get("breakdown", {}),
                "advance_date": payout_date,
                "status": "active",
                "rolled_over_from_advance_id": str(adv["_id"]),
                "batch_repayment_id": batch_repayment_id,
                "notes": f"Reinvested from Advance {str(adv['_id'])}",
                "created_at": now_iso(),
                "created_by": user.get("email") or user.get("name", ""),
            }
            res_new_adv = await db.investor_advances.insert_one(new_advance_doc)
            new_advance_doc["_id"] = res_new_adv.inserted_id

            repayment_doc = {
                "advance_id": str(adv["_id"]),
                "investor_id": str(adv["investor_id"]),
                "investor_name": adv.get("investor_name", ""),
                "principal_amount": principal_amount,
                "margin_per_pair_used": margin_per_pair_used,
                "pairs": pairs,
                "margin_amount": margin_amount,
                "total_payout": margin_amount,
                "payout_date": payout_date,
                "batch_repayment_id": batch_repayment_id,
                "reinvested": True,
                "reinvested_into_advance_id": str(res_new_adv.inserted_id),
                "target_po_id": str(target_po["_id"]),
                "target_po_number": target_po.get("po_number", ""),
                "mode": payload.mode or "Bank Transfer",
                "bank_account_id": payload.bank_account_id,
                "notes": payload.notes or "",
                "created_at": now_iso(),
                "created_by": user.get("email") or user.get("name", ""),
            }
            res_rep = await db.investor_repayments.insert_one(repayment_doc)
            repayment_doc["_id"] = res_rep.inserted_id

            await db.investor_advances.update_one(
                {"_id": adv["_id"]},
                {"$set": {
                    "status": "reinvested",
                    "repayment_id": str(res_rep.inserted_id),
                    "reinvested_into_advance_id": str(res_new_adv.inserted_id),
                    "batch_repayment_id": batch_repayment_id,
                    "reinvested_at": now_iso()
                }}
            )

            try:
                sync_investor_repayment_to_supabase(
                    repayment_doc=repayment_doc,
                    investor_doc=investor,
                    is_reinvestment=True,
                    new_advance_doc=new_advance_doc,
                    payment_mode=payload.mode or "BANK_TRANSFER",
                    bank_account_id=payload.bank_account_id
                )
            except Exception as se:
                log.warning("Supabase bulk reinvestment sync skipped for advance %s: %s", adv_id, se)

            results.append(repayment_doc)

    # Inflow/Outflow to Company Bank Account via db.payments
    # Inflow/Outflow to Company Bank Account via db.payments
    eff_mode = payload.payment_mode or payload.mode or "Bank Transfer"
    eff_ref = payload.reference or payload.notes or ""
    if payload.bank_account_id and total_payout > 0 and eff_mode != "Cash":
        try:
            bank_doc = await db.bank_accounts.find_one({"_id": oid(payload.bank_account_id)})
            if not bank_doc:
                bank_doc = await db.bank_accounts.find_one({"_id": str(payload.bank_account_id)})
            b_name = (bank_doc.get("bank_name") or bank_doc.get("account_name", "Bank")) if bank_doc else "Bank"
            for r_doc in results:
                p_amt = float(r_doc.get("total_payout") or 0.0)
                if p_amt <= 0:
                    continue
                pmt_doc = {
                    "payment_date": payout_date,
                    "amount": round(p_amt, 2),
                    "mode": eff_mode,
                    "reference": eff_ref,
                    "bank": b_name,
                    "bank_account_id": str(payload.bank_account_id),
                    "account_type": "bank",
                    "notes": f"Batch investor repayment #{batch_repayment_id} ({r_doc.get('investor_name')})",
                    "type": "investor_repayment",
                    "investor_id": str(r_doc.get("investor_id", "")),
                    "investor_name": r_doc.get("investor_name", "Investor"),
                    "advance_id": str(r_doc.get("advance_id", "")),
                    "repayment_id": str(r_doc.get("_id", "")),
                    "batch_repayment_id": batch_repayment_id,
                    "by": user.get("email") or user.get("name", ""),
                    "created_at": now_iso(),
                }
                await db.payments.insert_one(pmt_doc)
            from routes.banking import sync_bank_account_balance
            await sync_bank_account_balance(db, str(payload.bank_account_id))
        except Exception as pe:
            log.warning("Could not sync live bank balance for bulk repayment: %s", pe)

    return {
        "ok": True,
        "batch_repayment_id": batch_repayment_id,
        "action": payload.action,
        "settled_count": len(results),
        "total_principal": round(total_principal, 2),
        "total_margin": round(total_margin, 2),
        "total_payout": round(total_payout, 2),
        "repayments": stringify(results)
    }


@investors_router.get("/investors/repayments/all")
async def list_all_repayments(request: Request, investor_id: Optional[str] = None):
    user = await _get_user(request)
    require_admin_or_manager(user)
    db = get_db(request)

    q = {}
    if investor_id:
        q["investor_id"] = investor_id
    reps = await db.investor_repayments.find(q).sort("created_at", -1).to_list(1000)
    return stringify(reps)


# =============================================================================
# 4. INVESTOR PORTAL (Stage 5 — Scoped, Read-Only, Server-Side Enforced)
# =============================================================================

@investors_router.post("/auth/investor-login")
async def investor_login(payload: InvestorLoginIn, request: Request, response: Response):
    """Investor self-login via phone/email + numeric PIN. Issues JWT with role='investor'."""
    db = get_db(request)

    ident = (payload.identifier or "").strip()
    clean_pin = (payload.pin or "").strip()

    if not ident or not clean_pin:
        raise HTTPException(401, "Invalid login credentials")

    investor = await db.investors.find_one({
        "$or": [
            {"phone": ident},
            {"email": ident.lower()},
            {"contact": ident}
        ],
        "active": {"$ne": False}
    })
    pin_hash = investor.get("pin_hash", "") if investor else ""

    if not investor or not pin_hash or not verify_password(clean_pin, pin_hash):
        raise HTTPException(401, "Invalid phone/email or PIN")

    iid = str(investor["_id"])
    access = create_access_token(
        user_id=iid,
        email=investor.get("email") or ident,
        role="investor",
        allowed_modules=["investor_portal"]
    )
    set_auth_cookies(response, access)

    return {
        "investor_id": iid,
        "name": investor.get("name", ""),
        "role": "investor",
        "access_token": access,
    }


@investors_router.get("/investor-portal/advances")
async def portal_get_advances(request: Request):
    """
    Returns investor's own advances only.
    Server-side collapses bom_cost/labour_cost/opex_cost breakdown into the single 'amount' total.
    The breakdown is NOT included in the response at all.
    """
    user = await _get_user(request)
    require_investor(user)
    db = get_db(request)

    iid = user["investor_id"]
    advances = await db.investor_advances.find({"investor_id": iid}).sort("advance_date", -1).to_list(500)

    scoped_results = []
    for adv in advances:
        scoped_results.append({
            "id": str(adv["_id"]),
            "advance_date": adv.get("advance_date", ""),
            "amount": round(float(adv.get("amount") or 0.0), 2),
            "status": adv.get("status", "active"),
            "po_reference": adv.get("po_number") or str(adv.get("po_id", "")),
            "po_id": str(adv.get("po_id", "")),
            "pairs": int(adv.get("pairs") or 0),
        })

    return scoped_results


@investors_router.get("/investor-portal/pos/{po_id}")
async def portal_get_po_detail(po_id: str, request: Request):
    """
    ONLY for POs the logged-in investor has actually funded.
    Verifies po_id belongs to one of their advances first, 404 otherwise.
    Returns: PO number, style, quantity, dispatch/GRN status, invoice status,
             amount received from client so far, amount still receivable,
             and their own repayment status.
    Client unit price, vendor costs, and company-wide P&L stay out.
    """
    user = await _get_user(request)
    require_investor(user)
    db = get_db(request)

    iid = user["investor_id"]

    # Verify advance belongs to this investor
    adv_query = {"investor_id": iid}
    try:
        adv_query["$or"] = [{"po_id": str(po_id)}, {"po_id": oid(po_id)}]
    except Exception:
        adv_query["po_id"] = str(po_id)

    adv = await db.investor_advances.find_one(adv_query)
    if not adv:
        # Also check by po_number
        po_doc_lookup = await db.pos.find_one({"_id": oid(po_id)}) if ObjectId.is_valid(po_id) else None
        if po_doc_lookup and po_doc_lookup.get("po_number"):
            adv = await db.investor_advances.find_one({"investor_id": iid, "po_number": po_doc_lookup["po_number"]})

    if not adv:
        raise HTTPException(404, "Purchase Order not found or not funded by this investor")

    # Fetch PO
    po = await db.pos.find_one({"_id": oid(adv.get("po_id"))}) if ObjectId.is_valid(adv.get("po_id")) else None
    if not po and adv.get("po_number"):
        po = await db.pos.find_one({"po_number": adv["po_number"]})

    po_number = (po and po.get("po_number")) or adv.get("po_number") or ""
    quantity = int((po and (po.get("total_quantity") or po.get("quantity"))) or adv.get("pairs") or 0)

    # Styles summary
    styles_list = []
    if po:
        for item in po.get("line_items", []):
            sc = item.get("style_code") or ""
            if sc and sc not in styles_list:
                styles_list.append(sc)
    style_str = ", ".join(styles_list) if styles_list else (po and po.get("style_code") or "Standard")

    # Invoices and client payments
    inv_query = []
    if adv.get("po_id"):
        inv_query.append({"po_id": str(adv["po_id"])})
    if po_number:
        inv_query.append({"po_number": po_number})

    invoices = await db.invoices.find({"$or": inv_query}).to_list(100) if inv_query else []
    total_invoiced = sum(float(inv.get("grand_total") or 0.0) for inv in invoices)
    invoice_ids = [str(inv["_id"]) for inv in invoices]

    payments = []
    if invoice_ids:
        payments = await db.payments.find({"invoice_ids": {"$in": invoice_ids}}).to_list(100)

    amount_received = sum(float(p.get("amount") or 0.0) for p in payments)
    amount_receivable = max(0.0, round(total_invoiced - amount_received, 2))

    # Dispatch / GRN status
    dispatch_status = "In Production"
    if invoices:
        all_paid = all(inv.get("status") == "paid" for inv in invoices)
        dispatch_status = "Dispatched & Invoiced" if not all_paid else "Dispatched & Fully Paid"
    elif po and po.get("status"):
        dispatch_status = po.get("status").capitalize()

    invoice_status = "Pending Invoice"
    if invoices:
        invoice_status = f"{len(invoices)} Invoices Raised"

    # Repayment status for this investor
    adv_status = adv.get("status", "active")
    repayment_status = "outstanding"
    if adv_status == "repaid":
        repayment_status = "repaid"
    elif adv_status == "reinvested":
        repayment_status = "reinvested"

    return {
        "po_number": po_number,
        "style": style_str,
        "quantity": quantity,
        "dispatch_status": dispatch_status,
        "invoice_status": invoice_status,
        "amount_received_from_client_so_far": round(amount_received, 2),
        "amount_still_receivable": amount_receivable,
        "repayment_status": repayment_status,
        "funding_total": round(float(adv.get("amount") or 0.0), 2),
    }


@investors_router.get("/investor-portal/summary")
async def portal_get_summary(request: Request):
    """Returns top-level metric tiles for investor dashboard."""
    user = await _get_user(request)
    require_investor(user)
    db = get_db(request)

    iid = user["investor_id"]
    advances = await db.investor_advances.find({"investor_id": iid}).to_list(500)
    repayments = await db.investor_repayments.find({"investor_id": iid}).to_list(500)

    total_funded = sum(float(a.get("amount") or 0.0) for a in advances)
    total_repaid_principal = sum(float(r.get("principal_amount") or 0.0) for r in repayments if not r.get("reinvested"))
    total_margin_earned = sum(float(r.get("margin_amount") or 0.0) for r in repayments)

    active_advances = [a for a in advances if a.get("status") == "active"]
    outstanding_balance = sum(float(a.get("amount") or 0.0) for a in active_advances)

    return {
        "investor_name": user.get("name", "Investor"),
        "total_funded": round(total_funded, 2),
        "total_repaid": round(total_repaid_principal, 2),
        "total_margin_earned": round(total_margin_earned, 2),
        "outstanding_balance": round(outstanding_balance, 2),
        "active_advances_count": len(active_advances),
    }


@investors_router.get("/investor-portal/bank-statement")
async def get_investor_portal_bank_statement(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category: Optional[str] = None,
):
    """Scoped endpoint for logged-in investor to access their personal bank statement passbook."""
    user = await _get_user(request)
    require_investor(user)
    db = get_db(request)
    iid = user["investor_id"]
    statement = await generate_bank_statement_ledger(
        db,
        investor_id=iid,
        from_date=from_date,
        to_date=to_date,
        category=category,
    )
    return statement

