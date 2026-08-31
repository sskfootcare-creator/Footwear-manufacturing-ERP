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

    last4 = payload.account_number_last4.strip() if payload.account_number_last4 else ""
    if not last4 and payload.account_number:
        last4 = payload.account_number.strip()[-4:]

    doc = {
        "name": payload.name.strip(),
        "bank_name": payload.bank_name.strip(),
        "account_number_last4": last4,
        "account_number": (payload.account_number or "").strip() or None,
        "ifsc": (payload.ifsc or "").strip().upper() or None,
        "branch": (payload.branch or "").strip() or None,
        "account_type": payload.account_type,
        "opening_balance": float(payload.opening_balance),
        "opening_balance_date": payload.opening_balance_date,
        "statement_format": payload.statement_format.dict() if payload.statement_format else None,
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

    # Collect cash_ledger IDs for cash_withdrawal lines to populate audit trail details
    cash_ledger_ids = [
        d["matched_to"]["ref_id"]
        for d in docs
        if isinstance(d.get("matched_to"), dict) and d["matched_to"].get("type") == "cash_withdrawal" and d["matched_to"].get("ref_id")
    ]
    cash_ledger_map = {}
    if cash_ledger_ids and hasattr(db, "cash_ledger") and db.cash_ledger is not None:
        try:
            cl_obj_ids = []
            for cid in cash_ledger_ids:
                try:
                    cl_obj_ids.append(_oid(cid))
                except Exception:
                    pass
            cl_cursor = db.cash_ledger.find({"_id": {"$in": cl_obj_ids}})
            if hasattr(cl_cursor, "to_list"):
                res = cl_cursor.to_list(len(cl_obj_ids) + 10)
                if hasattr(res, "__await__"):
                    cl_docs = await res
                elif isinstance(res, list):
                    cl_docs = res
                else:
                    cl_docs = []
                cash_ledger_map = {str(c["_id"]): c for c in cl_docs}
        except Exception:
            cash_ledger_map = {}

    wage_payments_by_cl = {}
    if cash_ledger_ids and hasattr(db, "wage_payments") and db.wage_payments is not None:
        try:
            wp_cursor = db.wage_payments.find({"cash_ledger_id": {"$in": [str(c) for c in cash_ledger_ids]}})
            if hasattr(wp_cursor, "to_list"):
                res = wp_cursor.to_list(1000)
                if hasattr(res, "__await__"):
                    wp_docs = await res
                elif isinstance(res, list):
                    wp_docs = res
                else:
                    wp_docs = []
                for wp in wp_docs:
                    clid = str(wp.get("cash_ledger_id"))
                    wage_payments_by_cl.setdefault(clid, []).append(wp)
        except Exception:
            wage_payments_by_cl = {}

    items = []
    for d in docs:
        sd = stringify(d)
        if isinstance(d.get("matched_to"), dict) and d["matched_to"].get("type") == "cash_withdrawal":
            ref_id = str(d["matched_to"].get("ref_id"))
            cl_doc = cash_ledger_map.get(ref_id, {})
            wps = wage_payments_by_cl.get(ref_id, [])
            allocated = round(sum(float(wp.get("amount") or 0.0) for wp in wps), 2)
            withdrawn = float(cl_doc.get("amount") or d.get("debit_amount") or 0.0)
            rem = float(cl_doc.get("remaining_balance") if cl_doc.get("remaining_balance") is not None else (withdrawn - allocated))
            sd["cash_ledger_info"] = {
                "cash_ledger_id": ref_id,
                "withdrawal_amount": withdrawn,
                "remaining_balance": round(rem, 2),
                "allocated_amount": allocated,
                "wage_payment_count": len(wps),
                "wage_payments": [stringify(wp) for wp in wps],
            }
        items.append(sd)

    return {
        "total": total,
        "items": items,
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
from routes.online_orders import _parse_tabular_bytes, _resolve_column, _detect_tabular_file_format, _parse_xlrd_workbook, _is_html_content, _parse_html_table


def _extract_statement_metadata(content: bytes, filename: str) -> Dict[str, str]:
    """
    Extract account metadata (account_number, ifsc, branch) from statement header rows.
    """
    fmt = _detect_tabular_file_format(content, filename)
    rows_raw = []
    if fmt == "html_xls":
        try:
            rows_raw = _parse_html_table(content)
        except Exception:
            pass
    elif fmt == "xls":
        try:
            rows_raw = _parse_xlrd_workbook(content, SheetLocator(type="first_sheet"))
        except Exception:
            # Try HTML fallback
            if _is_html_content(content):
                try:
                    rows_raw = _parse_html_table(content)
                except Exception:
                    pass
    elif fmt == "xlsx":
        try:
            import openpyxl
            from io import BytesIO
            wb = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
            sheet = wb.worksheets[0]
            for r in sheet.iter_rows(values_only=True):
                rows_raw.append([str(c) if c is not None else "" for c in r])
        except Exception:
            if _is_html_content(content):
                try:
                    rows_raw = _parse_html_table(content)
                except Exception:
                    pass
    elif fmt == "csv":
        try:
            import csv, io
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                import csv, io
                text = content.decode("latin-1")
            except Exception:
                text = ""
        if text:
            reader = csv.reader(io.StringIO(text))
            rows_raw = list(reader)

    meta: Dict[str, str] = {}
    for r in rows_raw:
        row_cells = []
        for c in r:
            s = str(c).strip()
            if s and (not row_cells or s != row_cells[-1]):
                row_cells.append(s)

        for i, cell in enumerate(row_cells):
            cell_lc = cell.lower()
            if not meta.get("account_number"):
                if re.search(r"^(?:account\s*no\.?|acct\s*no\.?|a/c\s*no\.?|number\s*:?)$", cell_lc) and i + 1 < len(row_cells):
                    next_val = re.sub(r"[^\d]", "", row_cells[i + 1])
                    if 9 <= len(next_val) <= 20:
                        meta["account_number"] = next_val
                else:
                    m_acc = re.search(r"(?:account\s*no\.?|acct\s*no\.?|a/c\s*no\.?|number\s*:)\s*(\d{9,20})", cell, re.IGNORECASE)
                    if m_acc:
                        meta["account_number"] = m_acc.group(1)

            if not meta.get("ifsc"):
                if re.search(r"^ifsc\s*(?:code)?\s*:?$", cell_lc) and i + 1 < len(row_cells):
                    next_val = row_cells[i + 1].strip().upper()
                    if re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", next_val):
                        meta["ifsc"] = next_val
                else:
                    m_ifsc = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", cell)
                    if m_ifsc:
                        meta["ifsc"] = m_ifsc.group(1).upper()

            if not meta.get("branch"):
                if re.search(r"^branch\s*:?$", cell_lc) and i + 1 < len(row_cells):
                    next_val = row_cells[i + 1].strip()
                    if next_val and next_val.lower() != "branch":
                        meta["branch"] = next_val
                else:
                    m_br = re.search(r"branch\s*:\s*([A-Za-z0-9\s]+?)(?:\s{2,}|$)", cell, re.IGNORECASE)
                    if m_br:
                        val = m_br.group(1).strip()
                        if val:
                            meta["branch"] = val

    if meta.get("account_number") and not meta.get("account_number_last4"):
        meta["account_number_last4"] = meta["account_number"][-4:]

    return meta


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


DEFAULT_BANK_FORMAT_TEMPLATES = {
    "uco": {
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {
            "type": "scan_for_columns",
            "must_contain_any": [
                "Tran. Date", "Transaction Date", "Value Date",
                "Withdrawl", "Withdrawal", "Deposit", "Balance",
                "Narration", "Description"
            ]
        },
        "skip_rows_after_header": 0,
        "column_map": {
            "date": "Tran. Date",
            "narration": "Narration",
            "reference": "Chq. No.",
            "debit_amount": "Withdrawl",
            "credit_amount": "Deposit",
            "balance": "Balance",
        },
        "date_format": "%d/%m/%Y",
        "notes": "Standard UCO Bank Corporate / Retail Netbanking XLS/CSV template (date from Tran. Date)"
    },
    "hdfc": {
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {
            "type": "scan_for_columns",
            "must_contain_any": [
                "Date", "Narration", "Chq./Ref.No.",
                "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"
            ]
        },
        "skip_rows_after_header": 0,
        "column_map": {
            "date": "Date",
            "narration": "Narration",
            "reference": "Chq./Ref.No.",
            "debit_amount": "Withdrawal Amt.",
            "credit_amount": "Deposit Amt.",
            "balance": "Closing Balance",
        },
        "date_format": "%d/%m/%Y",
        "notes": "Standard HDFC Bank Statement template"
    }
}


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
        "default_templates": DEFAULT_BANK_FORMAT_TEMPLATES,
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
    confirm_account_update: bool,
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
        bank_name_lower = (acc.get("bank_name") or acc.get("name") or "").lower()
        if "uco" in bank_name_lower:
            cfg = DEFAULT_BANK_FORMAT_TEMPLATES.get("uco")
        elif "hdfc" in bank_name_lower:
            cfg = DEFAULT_BANK_FORMAT_TEMPLATES.get("hdfc")
        else:
            cfg = DEFAULT_BANK_FORMAT_TEMPLATES.get("uco")

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

    detected_fmt = _detect_tabular_file_format(content, file.filename)
    log.info("Statement import: file=%s, size=%d bytes, detected_format=%s", file.filename, len(content), detected_fmt)

    headers, raw_rows = _parse_tabular_bytes(content, file.filename, sheet_loc, header_loc, skip_rows)
    log.info("Statement import: parsed headers=%s, data_rows=%d", headers, len(raw_rows) if raw_rows else 0)
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
            "remarks": "",
            "imported_at": now,
            "imported_by": user_email,
        }
        statement_lines.append(line_doc)

    if not statement_lines:
        raise HTTPException(400, "No valid statement transaction rows extracted from the file")

    # Extract metadata from statement header for auto-populate suggestion (requires explicit user confirmation)
    extracted_meta = _extract_statement_metadata(content, file.filename)
    suggested_update: Dict[str, str] = {}
    if extracted_meta.get("account_number") and not acc.get("account_number"):
        suggested_update["account_number"] = extracted_meta["account_number"]
    if extracted_meta.get("ifsc") and not acc.get("ifsc"):
        suggested_update["ifsc"] = extracted_meta["ifsc"]
    if extracted_meta.get("branch") and not acc.get("branch"):
        suggested_update["branch"] = extracted_meta["branch"]
    if extracted_meta.get("account_number_last4") and not acc.get("account_number_last4"):
        suggested_update["account_number_last4"] = extracted_meta["account_number_last4"]

    applied_account_update = None
    is_confirmed = isinstance(confirm_account_update, bool) and confirm_account_update
    if is_confirmed and suggested_update and not dry_run:
        upd = dict(suggested_update)
        upd["updated_at"] = _now_iso()
        upd["updated_by"] = user_email
        await db.bank_accounts.update_one({"_id": _oid(id)}, {"$set": upd})
        applied_account_update = suggested_update
        suggested_update = {}

    if dry_run:
        res_dict = {
            "ok": True,
            "dry_run": True,
            "bank_account_id": id,
            "bank_account_name": acc.get("name"),
            "total_file_rows": len(raw_rows),
            "parsed_count": len(statement_lines),
            "sample": statement_lines[:5],
        }
        if suggested_update:
            res_dict["suggested_account_update"] = suggested_update
            res_dict["requires_account_confirmation"] = True
            res_dict["account_update_prompt"] = (
                "Statement header contains bank details: "
                + ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in suggested_update.items())
                + ". Confirm update to save these to the bank account."
            )
        return res_dict

    res = await db.bank_statement_lines.insert_many(statement_lines)
    res_dict = {
        "ok": True,
        "dry_run": False,
        "bank_account_id": id,
        "bank_account_name": acc.get("name"),
        "total_file_rows": len(raw_rows),
        "inserted_count": len(res.inserted_ids),
        "sample": [stringify(s) for s in statement_lines[:5]],
    }
    if suggested_update:
        res_dict["suggested_account_update"] = suggested_update
        res_dict["requires_account_confirmation"] = True
        res_dict["account_update_prompt"] = (
            "Statement header contains bank details: "
            + ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in suggested_update.items())
            + ". Confirm update to save these to the bank account."
        )
    if applied_account_update:
        res_dict["applied_account_update"] = applied_account_update
    return res_dict


@banking_router.post("/bank-accounts/{id}/statement/import")
@banking_router.post("/banking/accounts/{id}/statement/import")
async def import_bank_statement(
    id: str,
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    confirm_account_update: bool = Query(False),
):
    """Import statement file (CSV/XLS/XLSX) using the bank account's saved column-map configuration."""
    return await _handle_statement_import(id, file, dry_run, confirm_account_update, request)


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

from models.banking import TransferConfirmIn, CashWithdrawalConfirmIn

# Common cash withdrawal narration indicators: ATM, CASH, SELF, CWDR, NFS, EAW, etc.
_CASH_WITHDRAWAL_REGEX = re.compile(
    r'(?:^|[\s\-_/.,:])(ATM|CASH|SELF|CWDR|NFS|EAW|CSH|SELF\s*CHQ|SELF\s*CHEQUE|CASH\s*WDL|CASH\s*WITHDRAWAL)(?:$|[\s\-_/.,:])',
    re.IGNORECASE,
)


def _is_cash_withdrawal_candidate(narration: Optional[str]) -> bool:
    if not narration:
        return False
    return bool(_CASH_WITHDRAWAL_REGEX.search(narration))


@banking_router.get("/banking/cash-withdrawals/suggested")
@banking_router.get("/bank-accounts/cash-withdrawals/suggested")
async def get_suggested_cash_withdrawals(
    request: Request,
    bank_account_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    """Scan unmatched debit statement lines for potential cash withdrawal patterns (ATM, CASH, SELF, etc.)."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    q: Dict[str, Any] = {
        "match_status": "unmatched",
        "debit_amount": {"$gt": 0},
    }
    if bank_account_id and bank_account_id != "all":
        q["bank_account_id"] = str(bank_account_id)
    if from_date or to_date:
        dq = {}
        if from_date:
            dq["$gte"] = str(from_date)
        if to_date:
            dq["$lte"] = str(to_date)
        q["date"] = dq

    docs = await db.bank_statement_lines.find(q).sort("date", -1).to_list(5000)

    # Fetch accounts map
    accounts = await db.bank_accounts.find({}).to_list(1000)
    acc_map = {str(a["_id"]): a.get("name", "Unknown Account") for a in accounts}

    candidates = []
    for d in docs:
        narration = d.get("narration") or ""
        if _is_cash_withdrawal_candidate(narration):
            c_doc = stringify(d)
            c_doc["bank_account_name"] = acc_map.get(str(d.get("bank_account_id")), "Unknown Account")
            c_doc["amount"] = float(d.get("debit_amount") or 0.0)
            c_doc["suggestion_reason"] = "Narration matches cash withdrawal pattern (ATM/CASH/SELF)"
            candidates.append(c_doc)

    return {
        "ok": True,
        "total_suggestions": len(candidates),
        "candidates": candidates,
    }


@banking_router.post("/banking/cash-withdrawals/confirm")
@banking_router.post("/bank-accounts/cash-withdrawals/confirm")
async def confirm_cash_withdrawal(payload: CashWithdrawalConfirmIn, request: Request):
    """Explicitly confirm a statement line as cash withdrawal, create cash_ledger entry, and mark line matched."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = _get_db(request)

    line = await db.bank_statement_lines.find_one({"_id": _oid(payload.statement_line_id)})
    if not line:
        raise HTTPException(404, f"Statement line '{payload.statement_line_id}' not found")

    amount = float(line.get("debit_amount") or 0.0)
    if amount <= 0:
        raise HTTPException(400, "Cash withdrawal line must have a debit amount > 0")

    now = _now_iso()
    user_email = u.get("email") or u.get("name", "")

    # Create document in new collection cash_ledger
    cash_ledger_doc = {
        "bank_account_id": str(line.get("bank_account_id")),
        "source_statement_line_id": str(line["_id"]),
        "date": line.get("date"),
        "amount": amount,
        "remaining_balance": amount,
        "notes": payload.notes or line.get("narration") or "Cash withdrawal from bank",
        "created_at": now,
        "created_by": user_email,
    }
    res = await db.cash_ledger.insert_one(cash_ledger_doc)
    cash_ledger_id = str(res.inserted_id)

    # Update statement line to matched with matched_to: cash_withdrawal
    await db.bank_statement_lines.update_one(
        {"_id": line["_id"]},
        {"$set": {
            "match_status": "matched",
            "matched_to": {
                "type": "cash_withdrawal",
                "ref_id": cash_ledger_id,
            },
            "updated_at": now,
            "updated_by": user_email,
        }}
    )

    return {
        "ok": True,
        "message": "Cash withdrawal successfully confirmed and added to Cash Ledger.",
        "statement_line_id": str(line["_id"]),
        "cash_ledger_id": cash_ledger_id,
        "amount": amount,
        "remaining_balance": amount,
    }


@banking_router.get("/banking/cash-ledger")
@banking_router.get("/bank-accounts/cash-ledger")
async def list_cash_ledger(
    request: Request,
    bank_account_id: Optional[str] = None,
    limit: int = 200,
):
    """List cash ledger entries and total cash-in-hand remaining balance with linked wage disbursements."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales")(u)
    db = _get_db(request)

    q: Dict[str, Any] = {}
    if bank_account_id and bank_account_id != "all":
        q["bank_account_id"] = str(bank_account_id)

    docs = await db.cash_ledger.find(q).sort("date", -1).to_list(limit)
    total_withdrawn = sum(float(d.get("amount") or 0.0) for d in docs)
    total_remaining_balance = sum(float(d.get("remaining_balance") or 0.0) for d in docs)

    # Populate linked wage payments per cash_ledger entry
    cash_ids = [str(d["_id"]) for d in docs]
    wage_payments_by_cl = {}
    if cash_ids and hasattr(db, "wage_payments") and db.wage_payments is not None:
        try:
            wp_cursor = db.wage_payments.find({"cash_ledger_id": {"$in": cash_ids}})
            if hasattr(wp_cursor, "to_list"):
                res = wp_cursor.to_list(1000)
                if hasattr(res, "__await__"):
                    wp_docs = await res
                elif isinstance(res, list):
                    wp_docs = res
                else:
                    wp_docs = []
                for wp in wp_docs:
                    clid = str(wp.get("cash_ledger_id"))
                    wage_payments_by_cl.setdefault(clid, []).append(wp)
        except Exception:
            wage_payments_by_cl = {}

    items = []
    for d in docs:
        sd = stringify(d)
        wps = wage_payments_by_cl.get(str(d["_id"]), [])
        allocated = round(sum(float(wp.get("amount") or 0.0) for wp in wps), 2)
        withdrawn = float(d.get("amount") or 0.0)
        rem = float(d.get("remaining_balance") if d.get("remaining_balance") is not None else (withdrawn - allocated))
        sd["allocated_amount"] = allocated
        sd["remaining_balance"] = round(rem, 2)
        sd["wage_payment_count"] = len(wps)
        sd["wage_payments"] = [stringify(wp) for wp in wps]
        items.append(sd)

    return {
        "ok": True,
        "total_count": len(docs),
        "total_withdrawn": round(total_withdrawn, 2),
        "total_remaining_balance": round(total_remaining_balance, 2),
        "items": items,
    }


@banking_router.get("/banking/cash-ledger/{cash_ledger_id}")
@banking_router.get("/bank-accounts/cash-ledger/{cash_ledger_id}")
async def get_cash_ledger_detail(cash_ledger_id: str, request: Request):
    """Get cash ledger entry details with all linked wage payments funded by this withdrawal."""
    u = await _get_user(request)
    require_roles("admin", "manager", "sales", "production")(u)
    db = _get_db(request)

    doc = await db.cash_ledger.find_one({"_id": _oid(cash_ledger_id)})
    if not doc:
        raise HTTPException(404, f"Cash ledger entry '{cash_ledger_id}' not found")

    wage_payments = []
    if hasattr(db, "wage_payments") and db.wage_payments is not None:
        try:
            wp_cursor = db.wage_payments.find({"cash_ledger_id": str(cash_ledger_id)})
            if hasattr(wp_cursor, "to_list"):
                res = wp_cursor.to_list(500)
                if hasattr(res, "__await__"):
                    wage_payments = await res
                elif isinstance(res, list):
                    wage_payments = res
        except Exception:
            wage_payments = []

    wage_payments_list = [stringify(wp) for wp in wage_payments]
    allocated_amount = round(sum(float(wp.get("amount") or 0.0) for wp in wage_payments), 2)
    withdrawal_amount = float(doc.get("amount") or 0.0)
    remaining_balance = float(doc.get("remaining_balance") if doc.get("remaining_balance") is not None else (withdrawal_amount - allocated_amount))

    return {
        "ok": True,
        "cash_ledger": stringify(doc),
        "withdrawal_amount": withdrawal_amount,
        "allocated_amount": allocated_amount,
        "remaining_balance": round(remaining_balance, 2),
        "wage_payments": wage_payments_list,
        "wage_payment_count": len(wage_payments_list),
    }


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
    for acc_id_key, acc_stat in per_account_stats.items():
        acc_stat["total_reconciled_credits"] = round(acc_stat["matched_income"], 2)
        acc_stat["total_reconciled_debits"] = round(acc_stat["matched_expenses"], 2)
        acc_stat["net_statement_flow"] = round(acc_stat["income"] - acc_stat["expenses"], 2)

    # Cash in hand remaining balance from cash_ledger
    cash_docs = []
    if hasattr(db, "cash_ledger") and db.cash_ledger is not None:
        try:
            cash_q: Dict[str, Any] = {}
            if bank_account_id and bank_account_id != "all":
                cash_q["bank_account_id"] = str(bank_account_id)
            cursor = db.cash_ledger.find(cash_q)
            if hasattr(cursor, "to_list"):
                res = cursor.to_list(5000)
                if hasattr(res, "__await__"):
                    cash_docs = await res
                elif isinstance(res, list):
                    cash_docs = res
        except Exception:
            cash_docs = []

    total_cash_in_hand = round(sum(float(cd.get("remaining_balance") or 0.0) for cd in cash_docs), 2)
    total_cash_withdrawn = round(sum(float(cd.get("amount") or 0.0) for cd in cash_docs), 2)

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
            "total_cash_in_hand": total_cash_in_hand,
            "total_cash_withdrawn": total_cash_withdrawn,
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




