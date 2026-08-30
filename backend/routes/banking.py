"""Banking & Statement Reconciliation Routes."""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query

from models.banking import (
    BankAccountIn,
    BankAccountUpdate,
    BankStatementLineIn,
    BankStatementLineUpdate,
)
from auth import require_roles

log = logging.getLogger(__name__)

banking_router = APIRouter(prefix="/api", tags=["banking"])


def _get_db(request: Request):
    return getattr(request.app, "mongodb", None) or getattr(__import__("server"), "db")


async def _get_user(request: Request) -> dict:
    getter = getattr(request.app, "get_current_user", None)
    if not getter:
        from server import get_current_user as getter
    return await getter(request)


def _oid(val: str) -> ObjectId:
    try:
        return ObjectId(str(val))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ObjectId format")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: dict) -> dict:
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, dict):
            doc[k] = stringify(v)
        elif isinstance(v, list):
            doc[k] = [stringify(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
    return doc


# ---------------------------------------------------------------------------
# Bank Accounts CRUD
# ---------------------------------------------------------------------------

@banking_router.get("/banking/accounts")
async def list_bank_accounts(
    request: Request,
    active: Optional[bool] = None,
    account_type: Optional[str] = None,
    search: Optional[str] = None,
):
    """List all configured bank accounts (e.g. HDFC - Online, UCO Bank - Offline)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = _get_db(request)

    q: Dict[str, Any] = {}
    if active is not None:
        q["active"] = bool(active)
    if account_type:
        q["account_type"] = str(account_type)
    if search:
        rx = {"$regex": re.escape(str(search)), "$options": "i"}
        q["$or"] = [{"name": rx}, {"bank_name": rx}, {"account_number_last4": rx}]

    docs = await db.bank_accounts.find(q).sort("name", 1).to_list(1000)
    return [stringify(d) for d in docs]


@banking_router.post("/banking/accounts", status_code=201)
async def create_bank_account(payload: BankAccountIn, request: Request):
    """Create a new bank account."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    doc = {
        "name": payload.name.strip(),
        "bank_name": payload.bank_name.strip(),
        "account_number_last4": payload.account_number_last4.strip(),
        "account_type": payload.account_type,
        "opening_balance": float(payload.opening_balance),
        "opening_balance_date": payload.opening_balance_date,
        "active": payload.active,
        "created_at": _now_iso(),
        "created_by": u.get("email") or u.get("name", ""),
    }
    res = await db.bank_accounts.insert_one(doc)
    created = await db.bank_accounts.find_one({"_id": res.inserted_id})
    return stringify(created)


@banking_router.get("/banking/accounts/{id}")
async def get_bank_account(id: str, request: Request):
    """Retrieve a single bank account by ID."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = _get_db(request)

    doc = await db.bank_accounts.find_one({"_id": _oid(id)})
    if not doc:
        raise HTTPException(404, "Bank account not found")
    return stringify(doc)


@banking_router.patch("/banking/accounts/{id}")
async def update_bank_account(id: str, payload: BankAccountUpdate, request: Request):
    """Update bank account details."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        doc = await db.bank_accounts.find_one({"_id": _oid(id)})
        if not doc:
            raise HTTPException(404, "Bank account not found")
        return stringify(doc)

    updates["updated_at"] = _now_iso()
    updates["updated_by"] = u.get("email") or u.get("name", "")

    res = await db.bank_accounts.update_one({"_id": _oid(id)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Bank account not found")

    updated = await db.bank_accounts.find_one({"_id": _oid(id)})
    return stringify(updated)


@banking_router.delete("/banking/accounts/{id}")
async def delete_bank_account(id: str, request: Request):
    """Deactivate or delete a bank account."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    lines_count = await db.bank_statement_lines.count_documents({"bank_account_id": id})
    if lines_count > 0:
        # Soft-delete by setting active=False if statement lines exist
        await db.bank_accounts.update_one({"_id": _oid(id)}, {"$set": {"active": False, "updated_at": _now_iso()}})
        return {"ok": True, "message": "Bank account has existing statement lines and was deactivated."}

    res = await db.bank_accounts.delete_one({"_id": _oid(id)})
    if res.deleted_count == 0:
        raise HTTPException(404, "Bank account not found")
    return {"ok": True, "message": "Bank account deleted."}


# ---------------------------------------------------------------------------
# Bank Statement Lines
# ---------------------------------------------------------------------------

@banking_router.get("/banking/statement-lines")
async def list_statement_lines(
    request: Request,
    bank_account_id: Optional[str] = None,
    match_status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
    skip: int = 0,
):
    """List bank statement lines with reconciliation and match status."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    q: Dict[str, Any] = {}
    if bank_account_id:
        q["bank_account_id"] = str(bank_account_id)
    if match_status:
        q["match_status"] = str(match_status)
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = str(from_date)
        if to_date:
            dq["$lte"] = str(to_date)
        q["date"] = dq
    if search:
        rx = {"$regex": re.escape(str(search)), "$options": "i"}
        q["$or"] = [{"narration": rx}, {"reference_no": rx}]

    docs = await db.bank_statement_lines.find(q).sort([("date", -1), ("_id", -1)]).skip(skip).limit(limit).to_list(limit)
    total = await db.bank_statement_lines.count_documents(q)
    return {
        "total": total,
        "items": [stringify(d) for d in docs],
    }


@banking_router.post("/banking/statement-lines", status_code=201)
async def create_statement_lines(lines: List[BankStatementLineIn], request: Request):
    """Insert one or more bank statement lines."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    if not lines:
        raise HTTPException(400, "No statement lines provided")

    now = _now_iso()
    user_email = u.get("email") or u.get("name", "")

    to_insert = []
    for l in lines:
        row = l.dict()
        row["imported_at"] = row.get("imported_at") or now
        row["imported_by"] = row.get("imported_by") or user_email
        to_insert.append(row)

    res = await db.bank_statement_lines.insert_many(to_insert)
    return {
        "ok": True,
        "inserted_count": len(res.inserted_ids),
        "inserted_ids": [str(i) for i in res.inserted_ids],
    }


# ---------------------------------------------------------------------------
# Bank Statement Import & Config
# ---------------------------------------------------------------------------

from models.sku_map import SheetLocator, HeaderLocator
from models.banking import (
    StatementImportConfigIn,
    StatementImportConfigUpdate,
    STATEMENT_CANONICAL_FIELDS,
)
from routes.online_orders import _parse_tabular_bytes, _resolve_column


def _parse_date_to_iso(date_str: str, custom_format: Optional[str] = None) -> str:
    """Normalize various bank statement date formats to standard ISO YYYY-MM-DD."""
    s = str(date_str or "").strip()
    if not s:
        return ""
    if custom_format:
        try:
            return datetime.strptime(s, custom_format).strftime("%Y-%m-%d")
        except Exception:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]

    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y/%m/%d", "%Y-%m-%d",
        "%d %b %Y", "%d-%b-%Y", "%d/%b/%Y",
        "%d %B %Y", "%d-%B-%Y", "%d/%B/%Y",
        "%b %d, %Y", "%B %d, %Y",
        "%d-%b-%y", "%d/%b/%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s.split(" ")[0] if " " in s and len(s) > 11 else s, fmt).strftime("%Y-%m-%d")
        except Exception:
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except Exception:
                continue
    return s[:10]


def _parse_amount(val: Any) -> float:
    """Safely convert dirty amount strings with currency symbols and commas to float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in ["-", "--", "NA", "N/A", "null", "None"]:
        return 0.0
    s_clean = re.sub(r"[₹RsINR,\s]", "", s, flags=re.IGNORECASE)
    s_clean = re.sub(r"(dr|cr)", "", s_clean, flags=re.IGNORECASE).strip()
    if s_clean.startswith("(") and s_clean.endswith(")"):
        s_clean = f"-{s_clean[1:-1]}"
    try:
        return float(s_clean)
    except Exception:
        return 0.0


@banking_router.get("/banking/accounts/{id}/statement-format")
@banking_router.get("/bank-accounts/{id}/statement-format")
async def get_statement_format(id: str, request: Request):
    """Get the saved statement column-mapping format for a bank account."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    doc = await db.bank_accounts.find_one({"_id": _oid(id)})
    if not doc:
        raise HTTPException(404, "Bank account not found")
    return {
        "bank_account_id": id,
        "bank_name": doc.get("bank_name"),
        "canonical_fields": STATEMENT_CANONICAL_FIELDS,
        "statement_format": doc.get("statement_format"),
    }


@banking_router.put("/banking/accounts/{id}/statement-format")
@banking_router.put("/bank-accounts/{id}/statement-format")
@banking_router.post("/banking/accounts/{id}/statement-format")
@banking_router.post("/bank-accounts/{id}/statement-format")
async def save_statement_format(id: str, payload: StatementImportConfigIn, request: Request):
    """Configure or update the statement column-mapping format for a bank account."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    fmt_data = payload.dict()
    res = await db.bank_accounts.update_one(
        {"_id": _oid(id)},
        {"$set": {"statement_format": fmt_data, "updated_at": _now_iso()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Bank account not found")

    updated = await db.bank_accounts.find_one({"_id": _oid(id)})
    return stringify(updated)


async def _handle_statement_import(
    id: str,
    file: UploadFile,
    dry_run: bool,
    request: Request,
) -> dict:
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    acc = await db.bank_accounts.find_one({"_id": _oid(id)})
    if not acc:
        raise HTTPException(404, "Bank account not found")

    cfg = acc.get("statement_format")
    if not cfg or not cfg.get("column_map"):
        raise HTTPException(
            400,
            f"Bank account '{acc.get('name')}' does not have a saved statement column-map format. "
            "Please configure the statement format before importing."
        )

    sheet_loc = SheetLocator(**(cfg.get("sheet_locator") or {"type": "first_sheet"}))
    header_loc = HeaderLocator(**(cfg.get("header_locator") or {"type": "fixed_row", "row": 0}))
    skip_rows = int(cfg.get("skip_rows_after_header") or 0)
    col_map = cfg.get("column_map") or {}
    custom_date_fmt = cfg.get("date_format")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")

    headers, raw_rows = _parse_tabular_bytes(content, file.filename, sheet_loc, header_loc, skip_rows)
    if not headers or not raw_rows:
        raise HTTPException(400, "Could not extract tabular header and data rows from file")

    date_col = _resolve_column(col_map.get("date", ""), headers)
    narr_col = _resolve_column(col_map.get("narration", ""), headers)
    ref_col = _resolve_column(col_map.get("reference", ""), headers) if col_map.get("reference") else None
    debit_col = _resolve_column(col_map.get("debit_amount", ""), headers) if col_map.get("debit_amount") else None
    credit_col = _resolve_column(col_map.get("credit_amount", ""), headers) if col_map.get("credit_amount") else None
    bal_col = _resolve_column(col_map.get("balance", ""), headers) if col_map.get("balance") else None

    if not date_col:
        raise HTTPException(400, f"Configured date column '{col_map.get('date')}' not found in file headers: {headers}")
    if not narr_col:
        raise HTTPException(400, f"Configured narration column '{col_map.get('narration')}' not found in file headers: {headers}")

    now = _now_iso()
    user_email = u.get("email") or u.get("name", "")

    statement_lines = []
    for r in raw_rows:
        date_raw = r.get(date_col, "")
        narr_raw = r.get(narr_col, "")
        if not date_raw and not narr_raw:
            continue

        ref_raw = r.get(ref_col, "") if ref_col else ""
        debit_val = _parse_amount(r.get(debit_col)) if debit_col else 0.0
        credit_val = _parse_amount(r.get(credit_col)) if credit_col else 0.0
        bal_val = _parse_amount(r.get(bal_col)) if bal_col and r.get(bal_col) not in ["", None] else None

        line_doc = {
            "bank_account_id": id,
            "date": _parse_date_to_iso(date_raw, custom_date_fmt),
            "narration": str(narr_raw).strip(),
            "reference_no": str(ref_raw).strip() if ref_raw else "",
            "debit_amount": abs(float(debit_val)),
            "credit_amount": abs(float(credit_val)),
            "running_balance": float(bal_val) if bal_val is not None else None,
            "match_status": "unmatched",
            "matched_to": None,
            "imported_at": now,
            "imported_by": user_email,
        }
        statement_lines.append(line_doc)

    if not statement_lines:
        raise HTTPException(400, "No valid statement transaction rows extracted from the file")

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "bank_account_id": id,
            "bank_account_name": acc.get("name"),
            "total_file_rows": len(raw_rows),
            "parsed_count": len(statement_lines),
            "sample": statement_lines[:5],
        }

    res = await db.bank_statement_lines.insert_many(statement_lines)
    return {
        "ok": True,
        "dry_run": False,
        "bank_account_id": id,
        "bank_account_name": acc.get("name"),
        "total_file_rows": len(raw_rows),
        "inserted_count": len(res.inserted_ids),
        "sample": [stringify(s) for s in statement_lines[:5]],
    }


@banking_router.post("/bank-accounts/{id}/statement/import")
@banking_router.post("/banking/accounts/{id}/statement/import")
async def import_bank_statement(
    id: str,
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
):
    """Import statement file (CSV/XLSX) using the bank account's saved column-map configuration."""
    return await _handle_statement_import(id, file, dry_run, request)


@banking_router.patch("/banking/statement-lines/{id}/match")
async def match_statement_line(id: str, payload: BankStatementLineUpdate, request: Request):
    """Update match status or link a statement line to an internal payment/settlement/expense."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    updates = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not updates:
        doc = await db.bank_statement_lines.find_one({"_id": _oid(id)})
        if not doc:
            raise HTTPException(404, "Statement line not found")
        return stringify(doc)

    updates["updated_at"] = _now_iso()
    updates["updated_by"] = u.get("email") or u.get("name", "")

    res = await db.bank_statement_lines.update_one({"_id": _oid(id)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Statement line not found")

    updated = await db.bank_statement_lines.find_one({"_id": _oid(id)})
    return stringify(updated)


# ---------------------------------------------------------------------------
# Auto-Reconciliation Engine
# ---------------------------------------------------------------------------

def _parse_dt(d_val: Any) -> Optional[datetime]:
    if not d_val:
        return None
    s = str(d_val).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


async def _handle_reconcile_account(
    id: str,
    date_window_days: int,
    amount_tolerance: float,
    dry_run: bool,
    request: Request,
) -> dict:
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    acc = await db.bank_accounts.find_one({"_id": _oid(id)})
    if not acc:
        raise HTTPException(404, "Bank account not found")

    account_id_str = str(acc["_id"])
    account_type = acc.get("account_type", "b2b_client")

    unmatched_lines = await db.bank_statement_lines.find({
        "bank_account_id": account_id_str,
        "match_status": "unmatched",
    }).sort("date", 1).to_list(5000)

    if not unmatched_lines:
        return {
            "ok": True,
            "dry_run": dry_run,
            "bank_account_id": account_id_str,
            "bank_account_name": acc.get("name"),
            "total_unmatched_evaluated": 0,
            "auto_matched_count": 0,
            "ambiguous_count": 0,
            "no_match_count": 0,
            "matched_details": [],
        }

    claimed_ids = set()
    matched_results = []
    ambiguous_count = 0
    no_match_count = 0

    now = _now_iso()
    account_filter = {"$in": [None, "", account_id_str]}

    online_settlements_raw = await db.online_settlements.find({
        "bank_account_id": account_filter,
    }).to_list(10000)

    client_payments_raw = await db.payments.find({
        "type": {"$ne": "vendor_payment"},
        "vendor_id": {"$in": [None, ""]},
        "bank_account_id": account_filter,
    }).to_list(10000)

    vendor_payments_raw = await db.payments.find({
        "$or": [
            {"type": "vendor_payment"},
            {"vendor_id": {"$nin": [None, ""]}},
        ],
        "bank_account_id": account_filter,
    }).to_list(10000)

    expenses_raw = await db.expenses.find({
        "bank_account_id": account_filter,
    }).to_list(10000)

    for line in unmatched_lines:
        line_id = line["_id"]
        stmt_dt = _parse_dt(line.get("date"))
        credit = float(line.get("credit_amount") or 0.0)
        debit = float(line.get("debit_amount") or 0.0)

        # ── CREDIT Matching (Money In)
        if credit > 0:
            candidates = []
            if account_type == "online_channel":
                for s in online_settlements_raw:
                    s_id = str(s["_id"])
                    if s_id in claimed_ids:
                        continue
                    s_amount = float(s.get("net_payout") or s.get("settlement_amount") or 0.0)
                    s_dt = _parse_dt(s.get("settlement_date") or s.get("date") or s.get("created_at"))
                    if abs(s_amount - credit) <= amount_tolerance:
                        if stmt_dt and s_dt:
                            if abs((s_dt - stmt_dt).days) <= date_window_days:
                                candidates.append(("settlement", s))
                        else:
                            candidates.append(("settlement", s))
            else:
                for p in client_payments_raw:
                    p_id = str(p["_id"])
                    if p_id in claimed_ids:
                        continue
                    p_amount = float(p.get("amount") or 0.0)
                    p_dt = _parse_dt(p.get("payment_date") or p.get("created_at"))
                    if abs(p_amount - credit) <= amount_tolerance:
                        if stmt_dt and p_dt:
                            if abs((p_dt - stmt_dt).days) <= date_window_days:
                                candidates.append(("payment", p))
                        else:
                            candidates.append(("payment", p))

            if len(candidates) == 1:
                target_type, match_doc = candidates[0]
                ref_id = str(match_doc["_id"])
                claimed_ids.add(ref_id)
                matched_item = {
                    "statement_line_id": str(line_id),
                    "statement_date": line.get("date"),
                    "narration": line.get("narration"),
                    "amount": credit,
                    "side": "credit",
                    "matched_type": target_type,
                    "ref_id": ref_id,
                }
                matched_results.append(matched_item)

                if not dry_run:
                    await db.bank_statement_lines.update_one(
                        {"_id": line_id},
                        {"$set": {
                            "match_status": "matched",
                            "matched_to": {"type": target_type, "ref_id": ref_id},
                            "updated_at": now,
                        }}
                    )
                    if target_type == "settlement":
                        await db.online_settlements.update_one(
                            {"_id": match_doc["_id"]},
                            {"$set": {"bank_account_id": account_id_str, "updated_at": now}}
                        )
                    elif target_type == "payment":
                        await db.payments.update_one(
                            {"_id": match_doc["_id"]},
                            {"$set": {"bank_account_id": account_id_str, "updated_at": now}}
                        )
            elif len(candidates) > 1:
                ambiguous_count += 1
            else:
                no_match_count += 1

        # ── DEBIT Matching (Money Out)
        elif debit > 0:
            candidates = []
            for vp in vendor_payments_raw:
                vp_id = str(vp["_id"])
                if vp_id in claimed_ids:
                    continue
                vp_amount = float(vp.get("amount") or 0.0)
                vp_dt = _parse_dt(vp.get("payment_date") or vp.get("created_at"))
                if abs(vp_amount - debit) <= amount_tolerance:
                    if stmt_dt and vp_dt:
                        if abs((vp_dt - stmt_dt).days) <= date_window_days:
                            candidates.append(("vendor_payment", vp))
                    else:
                        candidates.append(("vendor_payment", vp))

            for exp in expenses_raw:
                exp_id = str(exp["_id"])
                if exp_id in claimed_ids:
                    continue
                exp_amount = float(exp.get("amount") or 0.0)
                exp_dt = _parse_dt(exp.get("date") or exp.get("created_at"))
                if abs(exp_amount - debit) <= amount_tolerance:
                    if stmt_dt and exp_dt:
                        if abs((exp_dt - stmt_dt).days) <= date_window_days:
                            candidates.append(("expense", exp))
                    else:
                        candidates.append(("expense", exp))

            if len(candidates) == 1:
                target_type, match_doc = candidates[0]
                ref_id = str(match_doc["_id"])
                claimed_ids.add(ref_id)
                matched_item = {
                    "statement_line_id": str(line_id),
                    "statement_date": line.get("date"),
                    "narration": line.get("narration"),
                    "amount": debit,
                    "side": "debit",
                    "matched_type": target_type,
                    "ref_id": ref_id,
                }
                matched_results.append(matched_item)

                if not dry_run:
                    await db.bank_statement_lines.update_one(
                        {"_id": line_id},
                        {"$set": {
                            "match_status": "matched",
                            "matched_to": {"type": target_type, "ref_id": ref_id},
                            "updated_at": now,
                        }}
                    )
                    if target_type == "vendor_payment":
                        await db.payments.update_one(
                            {"_id": match_doc["_id"]},
                            {"$set": {"bank_account_id": account_id_str, "updated_at": now}}
                        )
                    elif target_type == "expense":
                        await db.expenses.update_one(
                            {"_id": match_doc["_id"]},
                            {"$set": {"bank_account_id": account_id_str, "updated_at": now}}
                        )
            elif len(candidates) > 1:
                ambiguous_count += 1
            else:
                no_match_count += 1

    return {
        "ok": True,
        "dry_run": dry_run,
        "bank_account_id": account_id_str,
        "bank_account_name": acc.get("name"),
        "total_unmatched_evaluated": len(unmatched_lines),
        "auto_matched_count": len(matched_results),
        "ambiguous_count": ambiguous_count,
        "no_match_count": no_match_count,
        "date_window_days": date_window_days,
        "amount_tolerance": amount_tolerance,
        "matched_details": matched_results,
    }


@banking_router.post("/banking/accounts/{id}/reconcile")
@banking_router.post("/bank-accounts/{id}/reconcile")
async def reconcile_bank_account(
    id: str,
    request: Request,
    date_window_days: int = Query(3, ge=0, le=30),
    amount_tolerance: float = Query(1.0, ge=0.0, le=100.0),
    dry_run: bool = Query(False),
):
    """Run auto-reconciliation on unmatched statement lines against ERP records within tolerance & date window."""
    return await _handle_reconcile_account(id, date_window_days, amount_tolerance, dry_run, request)


# ---------------------------------------------------------------------------
# Transfer Pairs & Reconciliation Summary (Stage 4 & Stage 5)
# ---------------------------------------------------------------------------

from models.banking import TransferConfirmIn


@banking_router.get("/banking/transfers/suggested")
@banking_router.get("/bank-accounts/transfers/suggested")
async def get_suggested_transfers(
    request: Request,
    date_window_days: int = Query(3, ge=0, le=30),
    amount_tolerance: float = Query(1.0, ge=0.0, le=100.0),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """Scan across bank accounts for potential transfer pairs (debit in account A, credit in account B)."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    q: Dict[str, Any] = {"match_status": "unmatched"}
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = str(from_date)
        if to_date:
            dq["$lte"] = str(to_date)
        q["date"] = dq

    all_unmatched = await db.bank_statement_lines.find(q).sort("date", 1).to_list(10000)

    # Fetch accounts map
    accounts = await db.bank_accounts.find({}).to_list(1000)
    acc_map = {str(a["_id"]): a.get("name", "Unknown Account") for a in accounts}

    debits = [l for l in all_unmatched if float(l.get("debit_amount") or 0.0) > 0]
    credits = [l for l in all_unmatched if float(l.get("credit_amount") or 0.0) > 0]

    suggested_pairs = []
    used_credit_ids = set()

    for d in debits:
        d_id = str(d["_id"])
        d_acc = str(d.get("bank_account_id"))
        d_amt = float(d.get("debit_amount") or 0.0)
        d_dt = _parse_dt(d.get("date"))

        for c in credits:
            c_id = str(c["_id"])
            c_acc = str(c.get("bank_account_id"))

            # Transfers must be between DIFFERENT accounts
            if d_acc == c_acc:
                continue

            if c_id in used_credit_ids:
                continue

            c_amt = float(c.get("credit_amount") or 0.0)
            if abs(d_amt - c_amt) <= amount_tolerance:
                c_dt = _parse_dt(c.get("date"))
                day_diff = abs((c_dt - d_dt).days) if (c_dt and d_dt) else 0

                if day_diff <= date_window_days:
                    pair_doc = {
                        "pair_id": f"{d_id}:{c_id}",
                        "from_line": {
                            "id": d_id,
                            "bank_account_id": d_acc,
                            "bank_account_name": acc_map.get(d_acc, d_acc),
                            "date": d.get("date"),
                            "narration": d.get("narration"),
                            "reference_no": d.get("reference_no", ""),
                            "amount": d_amt,
                            "side": "debit",
                        },
                        "to_line": {
                            "id": c_id,
                            "bank_account_id": c_acc,
                            "bank_account_name": acc_map.get(c_acc, c_acc),
                            "date": c.get("date"),
                            "narration": c.get("narration"),
                            "reference_no": c.get("reference_no", ""),
                            "amount": c_amt,
                            "side": "credit",
                        },
                        "amount_diff": round(abs(d_amt - c_amt), 2),
                        "day_diff": day_diff,
                    }
                    suggested_pairs.append(pair_doc)

    return {
        "ok": True,
        "total_suggestions": len(suggested_pairs),
        "date_window_days": date_window_days,
        "amount_tolerance": amount_tolerance,
        "pairs": suggested_pairs,
    }


@banking_router.post("/banking/transfers/confirm")
@banking_router.post("/bank-accounts/transfers/confirm")
async def confirm_transfer_pair(payload: TransferConfirmIn, request: Request):
    """Explicitly confirm a transfer pair between two bank accounts."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    from_line = await db.bank_statement_lines.find_one({"_id": _oid(payload.from_line_id)})
    if not from_line:
        raise HTTPException(404, f"Sending statement line '{payload.from_line_id}' not found")

    to_line = await db.bank_statement_lines.find_one({"_id": _oid(payload.to_line_id)})
    if not to_line:
        raise HTTPException(404, f"Receiving statement line '{payload.to_line_id}' not found")

    if str(from_line.get("bank_account_id")) == str(to_line.get("bank_account_id")):
        raise HTTPException(400, "Transfer must be between two different bank accounts")

    if float(from_line.get("debit_amount") or 0.0) <= 0:
        raise HTTPException(400, "From-line must be a debit (withdrawal)")
    if float(to_line.get("credit_amount") or 0.0) <= 0:
        raise HTTPException(400, "To-line must be a credit (deposit)")

    now = _now_iso()
    user_email = u.get("email") or u.get("name", "")

    await db.bank_statement_lines.update_one(
        {"_id": from_line["_id"]},
        {"$set": {
            "match_status": "transfer",
            "matched_to": {"type": "transfer", "ref_id": str(to_line["_id"])},
            "transfer_notes": payload.notes or "",
            "confirmed_by": user_email,
            "updated_at": now,
        }}
    )

    await db.bank_statement_lines.update_one(
        {"_id": to_line["_id"]},
        {"$set": {
            "match_status": "transfer",
            "matched_to": {"type": "transfer", "ref_id": str(from_line["_id"])},
            "transfer_notes": payload.notes or "",
            "confirmed_by": user_email,
            "updated_at": now,
        }}
    )

    return {
        "ok": True,
        "message": "Transfer pair successfully confirmed and marked.",
        "from_line_id": str(from_line["_id"]),
        "to_line_id": str(to_line["_id"]),
    }


@banking_router.get("/banking/reconciliation/summary")
@banking_router.get("/bank-accounts/reconciliation/summary")
async def get_reconciliation_summary(
    request: Request,
    bank_account_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """
    Get financial reconciliation summary across bank statements.
    EXCLUDES transfer pairs from income/expense totals as internal liquidity moves.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    q: Dict[str, Any] = {}
    if bank_account_id:
        q["bank_account_id"] = str(bank_account_id)
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = str(from_date)
        if to_date:
            dq["$lte"] = str(to_date)
        q["date"] = dq

    docs = await db.bank_statement_lines.find(q).to_list(20000)
    accounts = await db.bank_accounts.find({}).to_list(1000)
    acc_map = {str(a["_id"]): a for a in accounts}

    total_income = 0.0
    matched_income = 0.0
    unmatched_income = 0.0

    total_expenses = 0.0
    matched_expenses = 0.0
    unmatched_expenses = 0.0

    total_transfers = 0.0
    transfer_count = 0
    ignored_count = 0

    per_account_stats = {}
    for acc_id_key, acc_doc in acc_map.items():
        per_account_stats[acc_id_key] = {
            "bank_account_id": acc_id_key,
            "name": acc_doc.get("name"),
            "bank_name": acc_doc.get("bank_name"),
            "account_type": acc_doc.get("account_type"),
            "opening_balance": acc_doc.get("opening_balance", 0.0),
            "income": 0.0,
            "matched_income": 0.0,
            "unmatched_income": 0.0,
            "expenses": 0.0,
            "matched_expenses": 0.0,
            "unmatched_expenses": 0.0,
            "transfers_in": 0.0,
            "transfers_out": 0.0,
            "total_lines": 0,
        }

    for d in docs:
        acc_id = str(d.get("bank_account_id"))
        status = d.get("match_status", "unmatched")
        credit = float(d.get("credit_amount") or 0.0)
        debit = float(d.get("debit_amount") or 0.0)

        acc_stat = per_account_stats.get(acc_id)
        if acc_stat:
            acc_stat["total_lines"] += 1

        if status == "transfer":
            transfer_count += 1
            if debit > 0:
                total_transfers += debit
                if acc_stat:
                    acc_stat["transfers_out"] += debit
            elif credit > 0:
                if acc_stat:
                    acc_stat["transfers_in"] += credit
            # Strictly EXCLUDED from income/expenses
            continue

        if status == "ignored":
            ignored_count += 1
            continue

        # Revenue / Income (Credits)
        if credit > 0:
            total_income += credit
            if acc_stat:
                acc_stat["income"] += credit
            if status == "matched":
                matched_income += credit
                if acc_stat:
                    acc_stat["matched_income"] += credit
            else:
                unmatched_income += credit
                if acc_stat:
                    acc_stat["unmatched_income"] += credit

        # Expenses / Outflows (Debits)
        if debit > 0:
            total_expenses += debit
            if acc_stat:
                acc_stat["expenses"] += debit
            if status == "matched":
                matched_expenses += debit
                if acc_stat:
                    acc_stat["matched_expenses"] += debit
            else:
                unmatched_expenses += debit
                if acc_stat:
                    acc_stat["unmatched_expenses"] += debit

    net_operating_cashflow = round(total_income - total_expenses, 2)

    return {
        "ok": True,
        "filter": {
            "bank_account_id": bank_account_id,
            "from_date": from_date,
            "to_date": to_date,
        },
        "summary": {
            "total_income": round(total_income, 2),
            "matched_income": round(matched_income, 2),
            "unmatched_income": round(unmatched_income, 2),
            "total_expenses": round(total_expenses, 2),
            "matched_expenses": round(matched_expenses, 2),
            "unmatched_expenses": round(unmatched_expenses, 2),
            "net_operating_cashflow": net_operating_cashflow,
            "total_transfers_volume": round(total_transfers, 2),
            "transfer_lines_count": transfer_count,
            "ignored_lines_count": ignored_count,
            "total_statement_lines": len(docs),
        },
        "accounts": list(per_account_stats.values()),
    }


@banking_router.get("/banking/unmatched-erp-candidates")
@banking_router.get("/bank-accounts/unmatched-erp-candidates")
async def get_unmatched_erp_candidates(
    request: Request,
    bank_account_id: Optional[str] = None,
    side: Optional[str] = Query("all"),
    search: Optional[str] = None,
    limit: int = 200,
):
    """
    List ERP-side transactions (settlements, client payments, vendor payments, expenses)
    that are not yet reconciled / linked to a bank account.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    account_type = "b2b_client"
    account_filter = {"$in": [None, ""]}
    if bank_account_id:
        acc = await db.bank_accounts.find_one({"_id": _oid(bank_account_id)})
        if acc:
            account_type = acc.get("account_type", "b2b_client")
            account_filter = {"$in": [None, "", str(acc["_id"])]}

    candidates = []

    # 1. Credits (Settlements / Client Payments)
    if side in ["credit", "all"]:
        if account_type == "online_channel" or not bank_account_id:
            s_q = {"bank_account_id": account_filter}
            if search:
                s_rx = {"$regex": re.escape(str(search)), "$options": "i"}
                s_q["$or"] = [{"seller_order_id": s_rx}, {"order_release_id": s_rx}, {"platform": s_rx}]
            settlements = await db.online_settlements.find(s_q).sort("settlement_date", -1).limit(limit).to_list(limit)
            for s in settlements:
                candidates.append({
                    "type": "settlement",
                    "id": str(s["_id"]),
                    "date": s.get("settlement_date") or s.get("created_at", "")[:10],
                    "amount": float(s.get("net_payout") or s.get("settlement_amount") or 0.0),
                    "description": f"{s.get('platform', 'Online').upper()} Settlement - Order {s.get('seller_order_id') or s.get('order_release_id') or str(s.get('_id', ''))}",
                    "side": "credit",
                    "party": s.get("platform", "Online"),
                    "reference": s.get("payment_id") or s.get("neft_ref") or "",
                })

        if account_type == "b2b_client" or not bank_account_id:
            p_q = {
                "type": {"$ne": "vendor_payment"},
                "vendor_id": {"$in": [None, ""]},
                "bank_account_id": account_filter,
            }
            if search:
                p_rx = {"$regex": re.escape(str(search)), "$options": "i"}
                p_q["$or"] = [{"client_name": p_rx}, {"reference": p_rx}, {"payment_no": p_rx}]
            payments = await db.payments.find(p_q).sort("payment_date", -1).limit(limit).to_list(limit)
            for p in payments:
                candidates.append({
                    "type": "payment",
                    "id": str(p["_id"]),
                    "date": p.get("payment_date", "")[:10],
                    "amount": float(p.get("amount") or 0.0),
                    "description": f"Client Payment {p.get('payment_no', '')} - {p.get('client_name', 'Client')}",
                    "side": "credit",
                    "party": p.get("client_name", "Client"),
                    "reference": p.get("reference") or p.get("payment_no") or "",
                })

    # 2. Debits (Vendor Payments / Expenses)
    if side in ["debit", "all"]:
        vp_q = {
            "$or": [{"type": "vendor_payment"}, {"vendor_id": {"$nin": [None, ""]}}],
            "bank_account_id": account_filter,
        }
        if search:
            vp_rx = {"$regex": re.escape(str(search)), "$options": "i"}
            vp_q["$or"] = [{"vendor_name": vp_rx}, {"reference": vp_rx}, {"payment_no": vp_rx}]
        vendor_payments = await db.payments.find(vp_q).sort("payment_date", -1).limit(limit).to_list(limit)
        for vp in vendor_payments:
            candidates.append({
                "type": "vendor_payment",
                "id": str(vp["_id"]),
                "date": vp.get("payment_date", "")[:10],
                "amount": float(vp.get("amount") or 0.0),
                "description": f"Vendor Payment {vp.get('payment_no', '')} - {vp.get('vendor_name', 'Vendor')}",
                "side": "debit",
                "party": vp.get("vendor_name", "Vendor"),
                "reference": vp.get("reference") or vp.get("payment_no") or "",
            })

        e_q = {"bank_account_id": account_filter}
        if search:
            e_rx = {"$regex": re.escape(str(search)), "$options": "i"}
            e_q["$or"] = [{"payee": e_rx}, {"category": e_rx}, {"notes": e_rx}]
        expenses = await db.expenses.find(e_q).sort("date", -1).limit(limit).to_list(limit)
        for exp in expenses:
            candidates.append({
                "type": "expense",
                "id": str(exp["_id"]),
                "date": exp.get("date", "")[:10],
                "amount": float(exp.get("amount") or 0.0),
                "description": f"{exp.get('category', 'Expense')} - {exp.get('payee', 'Payee')}",
                "side": "debit",
                "party": exp.get("payee", ""),
                "reference": exp.get("category", ""),
            })

    return {
        "ok": True,
        "total": len(candidates),
        "candidates": candidates[:limit],
    }




