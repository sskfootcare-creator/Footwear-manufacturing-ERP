"""Marketplace Online Orders, Configured Imports, Dispatch Imports, Monthly Reports, and Settlement Routes."""

import io
import os
import re
import csv
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any, Tuple
from collections import defaultdict
from io import BytesIO
import inspect

from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Query
from bson import ObjectId
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from auth import get_current_user_factory, require_roles
from models.orders import POIn, POLineItem, ProductionStageUpdate
from models.sku_map import Platform, SheetLocator, HeaderLocator
from rate_limiter import upload_rate_limiter, bulk_import_rate_limiter

log = logging.getLogger("online_orders_routes")

online_orders_router = APIRouter(prefix="/api", tags=["Online Orders & Marketplace Imports"])


def get_db():
    import server
    return server.db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(v) -> ObjectId:
    try:
        return ObjectId(v)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


def stringify(doc: dict) -> dict:
    if doc is None:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, dict):
            doc[key] = stringify(value)
        elif isinstance(value, list):
            doc[key] = [stringify(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in value]
    return doc


async def _safe_find_one(collection, *args, **kwargs):
    if collection is None:
        return None
    fn = getattr(collection, "find_one", None)
    if not fn:
        return None
    try:
        res = fn(*args, **kwargs)
        if inspect.isawaitable(res):
            return await res
        if isinstance(res, dict):
            return res
        return None
    except Exception:
        return None


async def _safe_update_one(collection, *args, **kwargs):
    if collection is None:
        return None
    fn = getattr(collection, "update_one", None)
    if not fn:
        return None
    try:
        res = fn(*args, **kwargs)
        if inspect.isawaitable(res):
            return await res
        return res
    except Exception:
        return None


async def _safe_to_list(cursor, limit=500):
    if cursor is None:
        return []
    try:
        if inspect.isawaitable(cursor):
            cursor = await cursor
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(limit)
            if inspect.isawaitable(res):
                return await res
            return res or []
        if isinstance(cursor, list):
            return cursor
        return []
    except Exception:
        return []


async def _get_user(request: Optional[Request] = None):
    if request is not None:
        user = getattr(request.state, "user", None)
        if user:
            return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    from auth import get_current_user_factory
    fn = await get_current_user_factory(get_db())
    return await fn(request)


async def _log_activity(action: str, category: str, details: str, email: str, db=None):
    db = db if db is not None else get_db()
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "user": email,
            "timestamp": now_iso(),
        })
    except Exception as e:
        log.warning(f"Failed to log activity: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Canonical Fields & Schemas
# ═══════════════════════════════════════════════════════════════════════

ORDER_CANONICAL_FIELDS = [
    "order_id", "order_item_id", "shipment_id",
    "order_date", "dispatch_by_date",
    "leaf_sku", "myntra_sku_code", "color", "size",
    "product_title", "qty",
    "selling_price", "invoice_amount",
    "order_state", "tracking_id",
    "buyer_name", "city", "state", "pincode",
    "bin_barcode",
]

DISPATCH_CANONICAL_FIELDS = [
    "order_id", "order_release_id",
    "leaf_sku", "channel_sku",
    "packed_on", "status",
    "mrp", "selling_value",
    "cgst", "sgst", "igst",
    "tracking_id",
    "destination_city", "destination_state", "destination_pincode",
    "store_packet_id",
    "product_title", "qty",
]

MONTHLY_REPORT_CANONICAL_FIELDS = [
    "order_id", "order_release_id",
    "leaf_sku", "size", "product_title",
    "order_status",
    "packed_on", "delivered_on", "cancelled_on",
    "rto_creation_date", "return_creation_date",
    "final_amount", "total_mrp", "discount", "seller_price",
]

SETTLEMENT_CANONICAL_FIELDS = [
    "order_ref", "leaf_sku",
    "gross_amount", "commission", "shipping_fee", "rto_charge", "gst_on_fees", "fixed_fee", "fees_total", "net_payout",
    "settlement_date", "payment_id",
]

ConfigRole = Literal["order", "dispatch", "monthly_report", "settlement"]


class OrderImportFormatConfigIn(BaseModel):
    platform: Platform
    role: ConfigRole = "order"
    sheet_locator: SheetLocator
    header_locator: HeaderLocator
    skip_rows_after_header: int = 0
    column_map: Dict[str, Optional[str]]
    known_sku_prefixes_to_strip: List[str] = Field(default_factory=list)
    known_sku_prefix_replacements: Dict[str, str] = Field(default_factory=dict)
    is_picklist: bool = False
    active: bool = True
    notes: Optional[str] = ""

    @field_validator("column_map")
    @classmethod
    def _order_column_map_leaf_sku(cls, v):
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        if not v.get("leaf_sku"):
            raise PydanticCustomError(
                "column_map_leaf_sku",
                "column_map.leaf_sku is required — every order/picklist file must expose our internal SKU column"
            )
        return v


class OrderImportFormatConfigUpdate(BaseModel):
    sheet_locator: Optional[SheetLocator] = None
    header_locator: Optional[HeaderLocator] = None
    skip_rows_after_header: Optional[int] = None
    column_map: Optional[Dict[str, Optional[str]]] = None
    known_sku_prefixes_to_strip: Optional[List[str]] = None
    known_sku_prefix_replacements: Optional[Dict[str, str]] = None
    is_picklist: Optional[bool] = None
    active: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("column_map")
    @classmethod
    def _order_column_map_opt(cls, v):
        if v is None: return v
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        if not v.get("leaf_sku"):
            raise PydanticCustomError(
                "column_map_leaf_sku",
                "column_map.leaf_sku is required"
            )
        return v


DEFAULT_ORDER_IMPORT_CONFIGS = [
    {
        "platform": "flipkart",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id":         "Order Id",
            "order_item_id":    "ORDER ITEM ID",
            "shipment_id":      "Shipment ID",
            "order_date":       "Ordered On",
            "leaf_sku":         "SKU",
            "product_title":    "Product",
            "qty":              "Quantity",
            "selling_price":    "Selling Price Per Item",
            "invoice_amount":   "Invoice Amount",
            "order_state":      "Order State",
            "tracking_id":      "Tracking ID",
            "dispatch_by_date": "Dispatch by date",
            "buyer_name":       "Buyer name",
            "city":             "City",
            "state":            "State",
            "pincode":          "PIN Code",
        },
        "known_sku_prefixes_to_strip": ["TH"],
        "known_sku_prefix_replacements": {},
        "is_picklist": False,
        "active": True,
        "notes": "Flipkart order-CSV export.",
    },
    {
        "platform": "myntra",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id":         None,
            "myntra_sku_code":  "myntraSkuCode",
            "leaf_sku":         "sellerSkuCode",
            "product_title":    "productDescription",
            "qty":              "quantity",
            "bin_barcode":      "binBarcode",
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {"FLL": "FL"},
        "is_picklist": True,
        "active": True,
        "notes": "Myntra picklist (OP-xxxxx.csv).",
    },
    {
        "platform": "myntra",
        "role": "dispatch",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id":            "Order id",
            "order_release_id":    "Order_release_id",
            "leaf_sku":            "Seller_sku_code",
            "channel_sku":         "Myntra SKU code",
            "packed_on":           "Packed On",
            "status":              "Status",
            "mrp":                 "MRP",
            "selling_value":       "Selling value",
            "cgst":                "CGST",
            "sgst":                "SGST",
            "igst":                "IGST",
            "tracking_id":         "Tracking_id",
            "destination_city":    "Destination City",
            "destination_state":   "Destination state",
            "destination_pincode": "Destination pincode",
            "store_packet_id":     "Store Packet ID",
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {"FLL": "FL"},
        "is_picklist": False,
        "active": True,
        "notes": "Myntra daily dispatch file (Packed_order_data.csv).",
    },
    {
        "platform": "myntra",
        "role": "monthly_report",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id":             "order id fk",
            "order_release_id":     "order release id",
            "leaf_sku":             "seller sku code",
            "size":                 "size",
            "order_status":         "order status",
            "packed_on":            "packed on",
            "delivered_on":         "delivered on",
            "cancelled_on":         "cancelled on",
            "rto_creation_date":    "rto creation date",
            "return_creation_date": "return creation date",
            "final_amount":         "final amount",
            "total_mrp":            "total mrp",
            "discount":             "discount",
            "seller_price":         "seller price",
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {"FLL": "FL"},
        "is_picklist": False,
        "active": True,
        "notes": "Myntra Monthly_order_report.csv.",
    },
    {
        "platform": "myntra",
        "role": "settlement",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_ref":       "order release id",
            "leaf_sku":        "seller sku code",
            "gross_amount":    "gross amount",
            "commission":      "commission",
            "shipping_fee":    "shipping fee",
            "rto_charge":      "rto charge",
            "net_payout":      "net payout",
            "settlement_date": "settlement date",
            "payment_id":      "payment id",
        },
        "known_sku_prefixes_to_strip": [],
        "known_sku_prefix_replacements": {"FLL": "FL"},
        "is_picklist": False,
        "active": True,
        "notes": "Myntra Settlement Advice CSV.",
    },
    {
        "platform": "flipkart",
        "role": "settlement",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_ref":       "order_id",
            "leaf_sku":        "sku",
            "gross_amount":    "sale_amount",
            "commission":      "commission",
            "shipping_fee":    "shipping_fee",
            "rto_charge":      "reverse_shipping_fee",
            "net_payout":      "bank_settlement_value",
            "settlement_date": "settlement_date",
            "payment_id":      "neft_id",
        },
        "known_sku_prefixes_to_strip": ["TH"],
        "known_sku_prefix_replacements": {},
        "is_picklist": False,
        "active": True,
        "notes": "Flipkart Settlement Report.",
    },
]


async def _seed_order_import_format_configs(db=None) -> int:
    db = db if db is not None else get_db()
    inserted = 0
    try:
        await db.order_import_format_configs.update_many(
            {"role": {"$exists": False}},
            {"$set": {"role": "order"}}
        )
    except Exception as e:
        log.warning(f"Could not backfill role on order_import_format_configs: {e}")

    try:
        idx_info = await db.order_import_format_configs.index_information()
        if "oifc_platform_unique" in idx_info:
            await db.order_import_format_configs.drop_index("oifc_platform_unique")
    except Exception as e:
        log.warning(f"Could not inspect/drop old index: {e}")

    try:
        await db.order_import_format_configs.create_index(
            [("platform", 1), ("role", 1)],
            unique=True,
            name="oifc_platform_role_unique"
        )
    except Exception as e:
        log.warning(f"Could not create order_import_format_configs composite index: {e}")

    for cfg in DEFAULT_ORDER_IMPORT_CONFIGS:
        role = cfg.get("role", "order")
        existing = await db.order_import_format_configs.find_one(
            {"platform": cfg["platform"], "role": role}
        )
        if not existing:
            existing = await db.order_import_format_configs.find_one(
                {"platform": cfg["platform"], "role": {"$exists": False}}
            )

        if existing:
            update_fields = {}
            if "role" not in existing:
                update_fields["role"] = role
            if "known_sku_prefixes_to_strip" not in existing and "known_sku_prefixes_to_strip" in cfg:
                update_fields["known_sku_prefixes_to_strip"] = cfg["known_sku_prefixes_to_strip"]
            if "known_sku_prefix_replacements" not in existing and "known_sku_prefix_replacements" in cfg:
                update_fields["known_sku_prefix_replacements"] = cfg["known_sku_prefix_replacements"]
            if "is_picklist" not in existing and "is_picklist" in cfg:
                update_fields["is_picklist"] = cfg["is_picklist"]
            if update_fields:
                try:
                    await db.order_import_format_configs.update_one(
                        {"_id": existing["_id"]},
                        {"$set": update_fields}
                    )
                except Exception as e:
                    log.warning(f"Could not update order_import_format_config {cfg['platform']}: {e}")
            continue

        doc = dict(cfg)
        doc["role"] = role
        doc["created_at"] = now_iso()
        doc["updated_at"] = now_iso()
        doc["created_by"] = "system"
        try:
            await db.order_import_format_configs.insert_one(doc)
            inserted += 1
        except DuplicateKeyError:
            pass
    return inserted


# ═══════════════════════════════════════════════════════════════════════
# Helpers: File Parsers & Column Matching
# ═══════════════════════════════════════════════════════════════════════

def _norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def strip_known_prefixes(leaf_sku: str, prefixes: List[str]) -> str:
    s = (leaf_sku or "").strip()
    for pfx in prefixes or []:
        pfx_clean = str(pfx or "").strip()
        if not pfx_clean:
            continue
        for delim in ["-", "_", ""]:
            full = f"{pfx_clean}{delim}"
            if s.upper().startswith(full.upper()):
                s = s[len(full):].strip()
                break
    return s


COMMON_COLUMN_ALIAS_GROUPS = [
    {"withdrawl", "withdrawal", "withdrawals", "withdrawalamt", "withdrawalamount", "debit", "debitamount", "dramount", "dr"},
    {"deposit", "deposits", "depositamt", "depositamount", "credit", "creditamount", "cramount", "cr"},
    {"trandate", "transactiondate", "txndate", "date", "txdate", "postingdate"},
    {"valuedate"},
    {"narration", "description", "particulars", "remarks", "transactionremarks", "transactionparticulars"},
    {"balance", "closingbalance", "runningbalance", "netbalance"},
    {"chqno", "chqrefno", "chequeno", "refno", "referenceno", "reference", "utr", "utrno", "chqrefno", "chequereferenceno"},
]


def _resolve_column(target: str, actual_headers: List[str]) -> Optional[str]:
    if not target or not actual_headers:
        return None
    for h in actual_headers:
        if h == target:
            return h
    t_lower = target.strip().lower()
    for h in actual_headers:
        if h.strip().lower() == t_lower:
            return h
    t_norm = _norm_token(target)
    for h in actual_headers:
        if _norm_token(h) == t_norm:
            return h

    # Check alias groups (e.g. withdrawal <-> withdrawl)
    for group in COMMON_COLUMN_ALIAS_GROUPS:
        if t_norm in group:
            for h in actual_headers:
                if _norm_token(h) in group:
                    return h
    return None


def _is_html_content(content: bytes) -> bool:
    """Check if file content is actually HTML (common with Indian bank .xls exports)."""
    try:
        head = content[:2048].decode("utf-8-sig", errors="ignore").strip().lower()
    except Exception:
        try:
            head = content[:2048].decode("latin-1", errors="ignore").strip().lower()
        except Exception:
            return False
    return (
        head.startswith("<!doctype html") or
        head.startswith("<html") or
        head.startswith("<?xml") or
        "<table" in head[:512] or
        "<html" in head[:512]
    )


def _parse_html_table(content: bytes) -> List[List[str]]:
    """
    Parse an HTML file containing a <table> into a list of rows (list of cell strings).
    Many Indian bank portals (UCO, SBI, PNB, etc.) export HTML tables with .xls extension.
    Uses Python's built-in html.parser — no external dependencies needed.
    """
    from html.parser import HTMLParser

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(400, "Unable to decode file content")

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tables: List[List[List[str]]] = []
            self._current_table: Optional[List[List[str]]] = None
            self._current_row: Optional[List[str]] = None
            self._current_cell: Optional[list] = None
            self._in_cell = False
            self._colspan = 1

        def handle_starttag(self, tag, attrs):
            tag_lc = tag.lower()
            if tag_lc == "table":
                self._current_table = []
            elif tag_lc == "tr" and self._current_table is not None:
                self._current_row = []
            elif tag_lc in ("td", "th") and self._current_row is not None:
                self._current_cell = []
                self._in_cell = True
                # Handle colspan
                self._colspan = 1
                for attr_name, attr_val in attrs:
                    if attr_name.lower() == "colspan":
                        try:
                            self._colspan = int(attr_val)
                        except (ValueError, TypeError):
                            self._colspan = 1
            elif tag_lc == "br" and self._in_cell:
                self._current_cell.append(" ")

        def handle_endtag(self, tag):
            tag_lc = tag.lower()
            if tag_lc in ("td", "th") and self._in_cell:
                cell_text = "".join(self._current_cell).strip()
                cell_text = re.sub(r"\s+", " ", cell_text)  # collapse whitespace
                if self._current_row is not None:
                    self._current_row.append(cell_text)
                    # Fill extra cells for colspan > 1
                    for _ in range(self._colspan - 1):
                        self._current_row.append("")
                self._current_cell = None
                self._in_cell = False
                self._colspan = 1
            elif tag_lc == "tr" and self._current_row is not None:
                if self._current_table is not None:
                    self._current_table.append(self._current_row)
                self._current_row = None
            elif tag_lc == "table" and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None

        def handle_data(self, data):
            if self._in_cell and self._current_cell is not None:
                self._current_cell.append(data)

        def handle_entityref(self, name):
            if self._in_cell and self._current_cell is not None:
                char_map = {"nbsp": " ", "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
                self._current_cell.append(char_map.get(name, f"&{name};"))

        def handle_charref(self, name):
            if self._in_cell and self._current_cell is not None:
                try:
                    if name.startswith("x"):
                        self._current_cell.append(chr(int(name[1:], 16)))
                    else:
                        self._current_cell.append(chr(int(name)))
                except (ValueError, OverflowError):
                    self._current_cell.append(f"&#{name};")

    parser = TableParser()
    parser.feed(text)

    if not parser.tables:
        raise HTTPException(400, "No HTML tables found in the uploaded file")

    # Use the largest table (most rows) — bank statements are usually the biggest table
    best_table = max(parser.tables, key=len)
    return best_table


def _detect_tabular_file_format(content: bytes, filename: str = "") -> str:
    """
    Detect whether file is legacy Excel (.xls / OLE2), modern Excel (.xlsx / OOXML zip), CSV,
    or HTML table (common bank portal export disguised as .xls).
    Uses magic bytes inspection first, falling back to file extension or content decoding.
    Raises HTTPException(400, "Unsupported file format — please upload .xls, .xlsx, or .csv") if unsupported.
    """
    if not content:
        raise HTTPException(400, "Uploaded file is empty")

    fname_lc = (filename or "").strip().lower()

    # 1. Magic bytes check (highest priority)
    # Legacy OLE2 compound document signature for .xls: D0 CF 11 E0
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"

    # OOXML / Zip archive signature for .xlsx: PK\x03\x04, PK\x05\x06, PK\x07\x08
    if content.startswith(b"PK\x03\x04") or content.startswith(b"PK\x05\x06") or content.startswith(b"PK\x07\x08"):
        return "xlsx"

    # 2. Check for HTML content disguised as .xls (common with Indian bank portals like UCO, SBI, PNB)
    if _is_html_content(content) and (fname_lc.endswith(".xls") or fname_lc.endswith(".xlsx")):
        return "html_xls"

    # 3. Filename extension checks
    if fname_lc.endswith(".xls"):
        return "xls"
    if fname_lc.endswith(".xlsx") or fname_lc.endswith(".xlsm") or fname_lc.endswith(".xltx"):
        return "xlsx"
    if fname_lc.endswith(".csv") or fname_lc.endswith(".tsv") or fname_lc.endswith(".txt"):
        try:
            content.decode("utf-8-sig")
            return "csv"
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
                return "csv"
            except Exception:
                raise HTTPException(400, "Unsupported file format — please upload .xls, .xlsx, or .csv")

    # 4. HTML sniffing (no extension match but content is HTML with tables)
    if _is_html_content(content):
        return "html_xls"

    # 5. Plain text / CSV sniffing (no null bytes in initial chunk)
    if b"\x00" not in content[:1024]:
        try:
            content.decode("utf-8-sig")
            return "csv"
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
                return "csv"
            except Exception:
                pass

    raise HTTPException(400, "Unsupported file format — please upload .xls, .xlsx, or .csv")


def _parse_xlrd_workbook(content: bytes, sheet_locator: SheetLocator) -> List[List[str]]:
    try:
        import xlrd
    except ImportError:
        raise HTTPException(500, "xlrd is required to parse legacy .xls Excel files")
    try:
        wb = xlrd.open_workbook(file_contents=content, formatting_info=True)
    except Exception:
        try:
            wb = xlrd.open_workbook(file_contents=content)
        except Exception as e:
            raise HTTPException(400, f"Failed to parse .xls file: {str(e)}")

    sheet = None
    if sheet_locator.type == "first_sheet":
        sheet = wb.sheet_by_index(0)
    elif sheet_locator.type == "fixed_name":
        if sheet_locator.name not in wb.sheet_names():
            raise HTTPException(400, f"Sheet '{sheet_locator.name}' not found in workbook")
        sheet = wb.sheet_by_name(sheet_locator.name)
    elif sheet_locator.type == "name_contains":
        sub = (sheet_locator.substring or "").lower()
        for sname in wb.sheet_names():
            if sub in sname.lower():
                sheet = wb.sheet_by_name(sname)
                break
        if not sheet:
            sheet = wb.sheet_by_index(0)
    else:
        sheet = wb.sheet_by_index(0)

    rows_raw = []
    for r in range(sheet.nrows):
        row = []
        for c in range(sheet.ncols):
            ctype = sheet.cell_type(r, c)
            val = sheet.cell_value(r, c)
            if ctype == xlrd.XL_CELL_DATE:
                try:
                    dt = xlrd.xldate_as_datetime(val, wb.datemode)
                    row.append(dt.strftime("%Y-%m-%d %H:%M:%S") if (dt.hour or dt.minute or dt.second) else dt.strftime("%Y-%m-%d"))
                except Exception:
                    row.append(str(val))
            elif ctype == xlrd.XL_CELL_NUMBER:
                if isinstance(val, float) and val.is_integer():
                    row.append(str(int(val)))
                else:
                    row.append(str(val))
            elif ctype == xlrd.XL_CELL_BOOLEAN:
                row.append("TRUE" if val else "FALSE")
            elif ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
                row.append("")
            else:
                row.append(str(val) if val is not None else "")
        rows_raw.append(row)

    for (rlo, rhi, clo, chi) in getattr(sheet, "merged_cells", []):
        top_left_val = rows_raw[rlo][clo] if rlo < len(rows_raw) and clo < len(rows_raw[rlo]) else ""
        if top_left_val:
            for r in range(rlo, min(rhi, len(rows_raw))):
                for c in range(clo, min(chi, len(rows_raw[r]))):
                    if not rows_raw[r][c]:
                        rows_raw[r][c] = top_left_val

    return rows_raw


def _parse_tabular_bytes(
    content: bytes,
    filename: str,
    sheet_locator: SheetLocator,
    header_locator: HeaderLocator,
    skip_rows_after_header: int = 0,
) -> Tuple[List[str], List[Dict[str, str]]]:
    fmt = _detect_tabular_file_format(content, filename)

    if fmt == "html_xls":
        rows_raw = _parse_html_table(content)

    elif fmt == "xls":
        try:
            rows_raw = _parse_xlrd_workbook(content, sheet_locator)
        except HTTPException:
            # If xlrd fails, try HTML fallback (some .xls files are actually HTML)
            if _is_html_content(content):
                rows_raw = _parse_html_table(content)
            else:
                raise

    elif fmt == "xlsx":
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(500, "openpyxl is required to parse Excel files")
        try:
            wb = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
            sheet = None
            if sheet_locator.type == "first_sheet":
                sheet = wb.worksheets[0]
            elif sheet_locator.type == "fixed_name":
                if sheet_locator.name not in wb.sheetnames:
                    raise HTTPException(400, f"Sheet '{sheet_locator.name}' not found in workbook")
                sheet = wb[sheet_locator.name]
            elif sheet_locator.type == "name_contains":
                sub = (sheet_locator.substring or "").lower()
                for sname in wb.sheetnames:
                    if sub in sname.lower():
                        sheet = wb[sname]
                        break
                if not sheet:
                    sheet = wb.worksheets[0]
            else:
                sheet = wb.worksheets[0]

            rows_raw = []
            for r in sheet.iter_rows(values_only=True):
                rows_raw.append([str(c) if c is not None else "" for c in r])
        except Exception as e:
            # If openpyxl fails because file was actually legacy .xls (OLE2 format)
            if "xlrd" in str(e).lower() or content.startswith(b"\xd0\xcf\x11\xe0"):
                try:
                    rows_raw = _parse_xlrd_workbook(content, sheet_locator)
                except Exception:
                    raise HTTPException(400, "Unsupported file format — please upload .xls, .xlsx, or .csv")
            # Try HTML fallback
            elif _is_html_content(content):
                rows_raw = _parse_html_table(content)
            else:
                raise HTTPException(400, f"Failed to parse Excel file: {str(e)}")

    elif fmt == "csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception:
                raise HTTPException(400, "Unsupported file format — please upload .xls, .xlsx, or .csv")
        reader = csv.reader(io.StringIO(text))
        rows_raw = list(reader)
    else:
        raise HTTPException(400, "Unsupported file format — please upload .xls, .xlsx, or .csv")

    if not rows_raw:
        return [], []

    header_row_idx = 0
    if header_locator.type == "fixed_row":
        header_row_idx = max(0, header_locator.row or 0)
    elif header_locator.type == "scan_for_columns":
        raw_kws = header_locator.must_contain_any or []
        if not raw_kws:
            raw_kws = [
                "Tran. Date", "Transaction Date", "Txn Date", "Value Date", "Date",
                "Withdrawl", "Withdrawal", "Withdrawals", "Withdrawal Amt.", "Debit", "Debit Amount", "Dr Amount",
                "Deposit", "Deposits", "Deposit Amt.", "Credit", "Credit Amount", "Cr Amount",
                "Balance", "Closing Balance", "Running Balance",
                "Narration", "Description", "Particulars", "Remarks",
                "Chq. No.", "Chq./Ref.No.", "Cheque No", "Ref No", "Reference No"
            ]
        must_contain = [_norm_token(kw) for kw in raw_kws if kw]
        best_idx = 0
        best_score = 0
        for idx, r in enumerate(rows_raw):
            row_tokens = [_norm_token(c) for c in r if c and str(c).strip()]
            if not row_tokens:
                continue
            matched_kws = set()
            for kw in must_contain:
                for cell in row_tokens:
                    if kw == cell or (len(kw) >= 4 and kw in cell):
                        matched_kws.add(kw)
                        break
            score = len(matched_kws)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_score > 0:
            header_row_idx = best_idx
        else:
            header_row_idx = 0

    if header_row_idx >= len(rows_raw):
        return [], []

    raw_headers = rows_raw[header_row_idx]
    headers = [str(h).strip() for h in raw_headers]

    data_start = header_row_idx + 1 + max(0, skip_rows_after_header)
    parsed_rows = []
    for r in rows_raw[data_start:]:
        if not any(str(c).strip() for c in r):
            continue
        row_dict = {}
        for h_idx, h_name in enumerate(headers):
            if not h_name:
                continue
            val = r[h_idx].strip() if h_idx < len(r) else ""
            row_dict[h_name] = val
        parsed_rows.append(row_dict)

    return headers, parsed_rows


# ═══════════════════════════════════════════════════════════════════════
# Endpoints: Order Import Format Configs
# ═══════════════════════════════════════════════════════════════════════

@online_orders_router.get("/order-import-format-configs")
async def list_order_import_format_configs(
    request: Request,
    active: Optional[bool] = None,
    role: Optional[ConfigRole] = None,
):
    await _get_user(request)
    db = get_db()
    q = {}
    if active is not None:
        q["active"] = active
    if role:
        q["role"] = role
    docs = await db.order_import_format_configs.find(q).sort("platform", 1).to_list(1000)
    return [stringify(d) for d in docs]


@online_orders_router.get("/order-import-format-configs/_meta/canonical-fields")
async def get_order_import_canonical_fields(
    request: Request,
    role: ConfigRole = "order",
):
    await _get_user(request)
    mapping = {
        "order": ORDER_CANONICAL_FIELDS,
        "dispatch": DISPATCH_CANONICAL_FIELDS,
        "monthly_report": MONTHLY_REPORT_CANONICAL_FIELDS,
        "settlement": SETTLEMENT_CANONICAL_FIELDS,
    }
    return {"canonical_fields": mapping.get(role, ORDER_CANONICAL_FIELDS)}


@online_orders_router.get("/order-import-format-configs/{platform}")
async def get_order_import_format_config(
    platform: str,
    request: Request,
    role: ConfigRole = "order",
):
    await _get_user(request)
    db = get_db()
    platform_lc = platform.lower()
    doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": role}
    )
    if not doc and role == "order":
        doc = await db.order_import_format_configs.find_one(
            {"platform": platform_lc, "role": {"$exists": False}}
        )
    if not doc:
        raise HTTPException(404, f"Order import format config for platform '{platform}' with role '{role}' not found")
    return stringify(doc)


@online_orders_router.post("/order-import-format-configs")
async def create_order_import_format_config(payload: OrderImportFormatConfigIn, request: Request):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = payload.platform.lower()
    role = payload.role or "order"
    if await db.order_import_format_configs.find_one({"platform": platform_lc, "role": role}):
        raise HTTPException(409, f"Config for platform '{platform_lc}' with role '{role}' already exists")
    doc = payload.model_dump()
    doc["platform"] = platform_lc
    doc["role"] = role
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    doc["created_by"] = u.get("email", "unknown")
    res = await db.order_import_format_configs.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    await _log_activity(
        "order_import_format.create", "order_import_format_configs",
        f"Created order import format config for platform={platform_lc}, role={role}",
        u["email"], db=db
    )
    return doc


@online_orders_router.patch("/order-import-format-configs/{platform}")
async def update_order_import_format_config(
    platform: str,
    payload: OrderImportFormatConfigUpdate,
    request: Request,
    role: ConfigRole = "order",
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = platform.lower()
    existing = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": role}
    )
    if not existing and role == "order":
        existing = await db.order_import_format_configs.find_one(
            {"platform": platform_lc, "role": {"$exists": False}}
        )
    if not existing:
        raise HTTPException(404, f"Config for platform '{platform_lc}' with role '{role}' not found")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    update["updated_at"] = now_iso()
    await db.order_import_format_configs.update_one({"_id": existing["_id"]}, {"$set": update})
    fresh = await db.order_import_format_configs.find_one({"_id": existing["_id"]})
    await _log_activity(
        "order_import_format.update", "order_import_format_configs",
        f"Updated order import format config for platform={platform_lc}, role={role}",
        u["email"], db=db
    )
    return stringify(fresh)


@online_orders_router.delete("/order-import-format-configs/{platform}")
async def delete_order_import_format_config(
    platform: str,
    request: Request,
    role: ConfigRole = "order",
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = platform.lower()
    res = await db.order_import_format_configs.delete_one({"platform": platform_lc, "role": role})
    if res.deleted_count == 0 and role == "order":
        res = await db.order_import_format_configs.delete_one({"platform": platform_lc, "role": {"$exists": False}})
    if res.deleted_count == 0:
        raise HTTPException(404, f"Config for platform '{platform_lc}' with role '{role}' not found")
    await _log_activity(
        "order_import_format.delete", "order_import_format_configs",
        f"Deleted order import format config for platform={platform_lc}, role={role}",
        u["email"], db=db
    )
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════
# Endpoints: Order Imports & Marketplace Pipelines
# ═══════════════════════════════════════════════════════════════════════

class OnlineOrderImportResult(BaseModel):
    channel: str
    imported: int
    unresolved: int
    errors: List[dict]


@online_orders_router.post("/online-orders/import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_online_orders(
    file: UploadFile = File(...),
    channel: str = "myntra",
    order_date: Optional[str] = None,
    request: Request = None,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()

    channel = channel.strip().lower()
    if channel not in ["myntra", "ajio", "flipkart", "nykaa", "amazon", "website", "unicommerce"]:
        raise HTTPException(400, f"Unknown channel '{channel}'. Must be one of: myntra, ajio, flipkart, nykaa, amazon, website, unicommerce")

    today = (order_date or now_iso()[:10])

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    def norm(row: dict) -> dict:
        return {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items()}

    imported = 0
    unresolved = 0
    errors = []
    fulfilled_from_stock = 0
    picklist_lines_by_order: Dict[str, List[dict]] = {}
    in_flight_covered: Dict[tuple, int] = {}

    from routes.pos import _get_stage_durations, _compute_deadline
    from routes.sku_map import resolve_style
    from routes.wms import _generate_picklist_for_order

    durations = await _get_stage_durations(db=db)
    jobs_to_insert = []
    entered = now_iso()
    deadline = _compute_deadline(entered, durations.get("procurement", 24))

    all_styles = await db.styles.find({}, {"code": 1, "_id": 1}).to_list(10000)
    styles_by_code = {s["code"].strip().upper(): str(s["_id"]) for s in all_styles}

    for row_idx, raw_row in enumerate(reader, start=2):
        r = norm(raw_row)
        order_id = r.get("order_id") or r.get("order_number") or r.get("order_no") or r.get("shipment_id") or ""
        raw_sku = r.get("style_sku") or r.get("sku") or r.get("seller_sku") or r.get("sku_code") or ""
        qty_str = r.get("quantity") or r.get("qty") or "1"
        color = r.get("color") or ""
        size = r.get("size") or ""
        description = r.get("description") or r.get("product_name") or ""
        unit_price = float(r.get("unit_price") or r.get("price") or r.get("mrp") or 0.0)
        delivery_date = r.get("delivery_date") or r.get("expected_delivery") or ""

        if not order_id:
            errors.append({"row": row_idx, "order_id": "", "style_sku": raw_sku, "reason": "Missing order_id"})
            continue
        if not raw_sku:
            errors.append({"row": row_idx, "order_id": order_id, "style_sku": "", "reason": "Missing style_sku"})
            continue
        try:
            quantity = int(qty_str)
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            errors.append({"row": row_idx, "order_id": order_id, "style_sku": raw_sku, "reason": f"Invalid quantity '{qty_str}'"})
            continue

        result = await resolve_style(
            source_type="online_channel",
            source_name=channel,
            external_sku=raw_sku,
            external_color=color or None,
            external_size=size or None,
            db=db,
        )

        if not result["matched"]:
            unresolved += 1
            errors.append({
                "row": row_idx, "order_id": order_id, "style_sku": raw_sku,
                "reason": f"Style SKU '{raw_sku}' not found in Style Master or SKU Mappings for channel '{channel}'",
            })
            continue

        match_status = "mapped" if result["match_via"] in ("sku_map", "marketplace_resolver") else "matched"
        style_doc_id = result.get("style_id") or styles_by_code.get(result["style_code"].upper())
        resolved_color = result.get("color") or color or ""
        resolved_size = str(result.get("size") or size or "")

        covered_qty = 0
        remaining_qty = quantity

        if style_doc_id:
            loc_docs = await db.fg_location_inventory.find({
                "style_id": str(style_doc_id),
                "color": {"$regex": f"^{re.escape(resolved_color)}$", "$options": "i"} if resolved_color else {"$in": ["", None]},
                "size": resolved_size,
                "qty": {"$gt": 0},
            }).to_list(100)

            total_avail = max(0, sum(loc.get("qty", 0) - loc.get("reserved_qty", 0) for loc in loc_docs))
            inflight_key = (str(style_doc_id), resolved_color.lower(), resolved_size)
            prior_claimed = in_flight_covered.get(inflight_key, 0)
            effective_avail = max(0, total_avail - prior_claimed)

            if effective_avail > 0:
                covered_qty = min(quantity, effective_avail)
                remaining_qty = quantity - covered_qty
                in_flight_covered[inflight_key] = prior_claimed + covered_qty

                if order_id not in picklist_lines_by_order:
                    picklist_lines_by_order[order_id] = []
                picklist_lines_by_order[order_id].append({
                    "style_id": str(style_doc_id),
                    "style_code": result["style_code"],
                    "color": resolved_color,
                    "size": resolved_size,
                    "ordered_qty": quantity,
                    "qty": quantity,
                })

        if remaining_qty <= 0:
            imported += 1
            fulfilled_from_stock += covered_qty
            continue

        job = {
            "po_id": None,
            "po_number": order_id,
            "client_name": channel,
            "channel": channel,
            "source_type": "online_channel",
            "order_date": today,
            "style_code": result["style_code"],
            "style_id": result["style_id"],
            "style_match_status": match_status,
            **({"mapped_from_sku": result["mapped_from_sku"], "sku_mapping_id": result["mapping_id"]} if result["match_via"] in ("sku_map", "marketplace_resolver") else {}),
            "description": description,
            "color": result["color"],
            "size": result["size"],
            "quantity": remaining_qty,
            "original_order_qty": quantity,
            "fulfilled_from_stock_qty": covered_qty,
            "unit_price": unit_price,
            "amount": round(unit_price * remaining_qty, 2),
            "completed_qty": 0,
            "rejected_qty": 0,
            "delivery_date": delivery_date,
            "stage": "procurement",
            "stage_entered_at": entered,
            "stage_deadline": deadline,
            "split_from_job_id": None,
            "split_history": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "history": [{"stage": "procurement", "at": now_iso(), "by": u["email"],
                         "notes": f"Auto-created from {channel} CSV import"
                                  + (f" (partial: {covered_qty} pairs shipped from ready stock)" if covered_qty else "")}],
        }
        jobs_to_insert.append(job)
        imported += 1
        fulfilled_from_stock += covered_qty

    if jobs_to_insert:
        await db.production_jobs.insert_many(jobs_to_insert)

    picklists_created = []
    for oid_key, lines in picklist_lines_by_order.items():
        try:
            pl_doc, covered_map, uncovered_map = await _generate_picklist_for_order(
                oid_key, channel, lines, u["email"], db=db)
            if pl_doc.get("_id"):
                picklists_created.append({
                    "picklist_no": pl_doc.get("picklist_no"),
                    "order_id": oid_key,
                    "items": pl_doc.get("total_items", 0),
                    "qty": pl_doc.get("total_qty", 0),
                })
        except Exception as pe:
            log.warning(f"Picklist generation failed for order {oid_key}: {pe}")

    await _log_activity(
        "IMPORT", "online_orders",
        f"{channel.capitalize()} CSV import: {imported} orders, {fulfilled_from_stock} pairs from stock, "
        f"{len(picklists_created)} picklists, {unresolved} unresolved, {len(errors)-unresolved} errors",
        u["email"], db=db
    )
    return {
        "channel": channel,
        "imported": imported,
        "unresolved": unresolved,
        "fulfilled_from_stock": fulfilled_from_stock,
        "picklists_created": picklists_created,
        "errors": errors,
    }


@online_orders_router.get("/online-orders")
async def list_online_orders(
    request: Request,
    channel: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    style_match_status: Optional[str] = None,
):
    await _get_user(request)
    db = get_db()
    query: dict = {"source_type": "online_channel"}
    if channel:
        query["channel"] = channel.lower()
    if style_match_status:
        query["style_match_status"] = style_match_status
    if from_date or to_date:
        date_q: dict = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        query["created_at"] = date_q
    docs = await db.production_jobs.find(query).sort("created_at", -1).to_list(5000)
    return [stringify(j) for j in docs]


# ═══════════════════════════════════════════════════════════════════════
# Endpoints: Configured Order Import, Dispatch, Monthly & Settlements
# ═══════════════════════════════════════════════════════════════════════

def _sanitize_sheet_loc(data: dict) -> dict:
    d = dict(data or {})
    if d.get("type") == "first":
        d["type"] = "first_sheet"
    return d


def _sanitize_header_loc(data: dict) -> dict:
    d = dict(data or {})
    if d.get("type") == "row":
        d["type"] = "fixed_row"
        if "row_1_based" in d:
            d["row"] = max(0, int(d.pop("row_1_based")) - 1)
    return d


@online_orders_router.post("/online-orders/import-configured", dependencies=[Depends(upload_rate_limiter)])
async def import_configured_online_orders(
    file: UploadFile = File(...),
    platform: str = Query(..., description="Platform identifier matching order_import_format_configs"),
    order_date: Optional[str] = None,
    dry_run: bool = False,
    request: Request = None,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = platform.strip().lower()

    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "order", "active": True}
    )
    if not cfg_doc:
        cfg_doc = await db.order_import_format_configs.find_one(
            {"platform": platform_lc, "active": True}
        )
    if not cfg_doc:
        raise HTTPException(400, f"No active order import format config found for platform '{platform_lc}'")

    content = await file.read()
    sheet_loc = SheetLocator(**_sanitize_sheet_loc(cfg_doc.get("sheet_locator", {"type": "first_sheet"})))
    header_loc = HeaderLocator(**_sanitize_header_loc(cfg_doc.get("header_locator", {"type": "fixed_row", "row": 0})))
    skip_rows = int(cfg_doc.get("skip_rows_after_header", 0) or 0)

    headers, rows = _parse_tabular_bytes(
        content=content,
        filename=file.filename or "",
        sheet_locator=sheet_loc,
        header_locator=header_loc,
        skip_rows_after_header=skip_rows,
    )

    if not rows:
        raise HTTPException(400, "No data rows found in uploaded file")

    col_map = cfg_doc.get("column_map") or {}
    resolved_cols = {}
    for canon_field, target_name in col_map.items():
        if target_name:
            actual = _resolve_column(target_name, headers)
            if actual:
                resolved_cols[canon_field] = actual

    leaf_sku_col = resolved_cols.get("leaf_sku")
    if not leaf_sku_col:
        raise HTTPException(400, f"Configured leaf_sku column '{col_map.get('leaf_sku')}' not found in file headers")

    from routes.sku_map import resolve_style, split_leaf_sku
    from routes.pos import _get_stage_durations, _compute_deadline

    prefixes_to_strip = cfg_doc.get("known_sku_prefixes_to_strip", [])
    prefix_replacements = cfg_doc.get("known_sku_prefix_replacements", {})
    is_picklist = bool(cfg_doc.get("is_picklist", False))

    batch_name = os.path.splitext(file.filename or "import")[0]
    today = (order_date or now_iso()[:10])
    durations = await _get_stage_durations(db=db)
    entered = now_iso()
    deadline = _compute_deadline(entered, durations.get("procurement", 24))

    matched_rows = []
    unresolved_rows = []
    canonical_rows = []
    distinct_orders = set()
    derivation_failed = 0
    empty_leaf_sku = 0
    in_flight_fg_claimed = {}
    in_flight_comp_claimed = {}

    header_row_1_based = 1
    if hasattr(header_loc, "row") and header_loc.row is not None:
        header_row_1_based = header_loc.row + 1

    for r_idx, r in enumerate(rows, start=1):
        raw_leaf = r.get(leaf_sku_col, "").strip() if leaf_sku_col else ""
        raw_order_id = r.get(resolved_cols.get("order_id", ""), "") if resolved_cols.get("order_id") else ""
        order_id = raw_order_id.strip()
        if not order_id and is_picklist:
            order_id = batch_name

        if order_id:
            distinct_orders.add(order_id)

        qty_str = r.get(resolved_cols.get("qty", ""), "1") if resolved_cols.get("qty") else "1"
        try:
            qty = int(qty_str)
            if qty <= 0: qty = 1
        except Exception:
            qty = 1

        color_val = r.get(resolved_cols.get("color", ""), "") if resolved_cols.get("color") else ""
        size_val = r.get(resolved_cols.get("size", ""), "") if resolved_cols.get("size") else ""

        if not raw_leaf:
            empty_leaf_sku += 1
            unresolved_rows.append({
                "row_index": r_idx,
                "order_id": order_id or batch_name,
                "raw_sku": "",
                "cleaned_sku": "",
                "color": color_val,
                "size": size_val,
                "quantity": qty,
            })
            canonical_rows.append({
                "source_row_index": r_idx,
                "order_id": None if is_picklist else (raw_order_id.strip() or None),
                "picklist_batch_id": batch_name if is_picklist else None,
                "leaf_sku_raw": "",
                "leaf_sku_replaced_prefix": None,
                "leaf_sku_stripped_prefix": None,
                "leaf_sku": "",
                "group_id": "—",
                "derived_size": "—",
                "size": "",
                "color": "",
                "style_code": "—",
                "style_id": None,
                "qty": qty,
                "matched": False,
                "match_via": None,
                "flags": ["empty_leaf_sku"],
                "exception_reason": "leaf_sku column is empty",
            })
            continue

        # Prefix replacement & stripping
        cleaned_leaf = raw_leaf
        replaced_prefix = None
        for wrong, right in prefix_replacements.items():
            if cleaned_leaf.startswith(wrong):
                cleaned_leaf = right + cleaned_leaf[len(wrong):]
                replaced_prefix = wrong
                break

        stripped_prefix = None
        for pfx in prefixes_to_strip:
            pfx_clean = str(pfx or "").strip()
            if not pfx_clean:
                continue
            for delim in ["-", "_", ""]:
                full = f"{pfx_clean}{delim}"
                if cleaned_leaf.upper().startswith(full.upper()):
                    stripped_prefix = pfx_clean
                    cleaned_leaf = cleaned_leaf[len(full):].strip()
                    break
            if stripped_prefix:
                break

        group_id, size_token, _ = split_leaf_sku(cleaned_leaf)
        if not group_id:
            derivation_failed += 1
        if not size_val and size_token:
            size_val = size_token

        sec_sku = ""
        if resolved_cols.get("myntra_sku_code"):
            sec_sku = r.get(resolved_cols.get("myntra_sku_code", ""), "").strip()
        elif resolved_cols.get("channel_sku"):
            sec_sku = r.get(resolved_cols.get("channel_sku", ""), "").strip()

        result = await resolve_style(
            source_type="online_channel",
            source_name=platform_lc,
            external_sku=cleaned_leaf,
            external_color=color_val or None,
            external_size=size_val or None,
            secondary_sku=sec_sku or None,
            db=db,
        )

        is_row_matched = bool(result.get("matched")) and (result.get("matched_exact") is not False) and (not result.get("unmapped_size")) and (not result.get("unmapped_color"))

        exc_reason = None
        if not is_row_matched:
            if result.get("unmapped_size") or result.get("size_matched_exact") is False:
                exc_reason = f"Unmapped color/size: size '{size_val}' not in size_map for SKU '{cleaned_leaf}'"
            elif result.get("unmapped_color") or result.get("color_matched_exact") is False:
                exc_reason = f"Unmapped color/size: color '{color_val}' not in color_map for SKU '{cleaned_leaf}'"
            else:
                exc_reason = f"SKU '{cleaned_leaf}' not found in Style Master or SKU Mappings"

        covered_qty = 0
        remaining_qty = qty
        fulfillment_status = "produce_shortage"
        components_available = False
        has_bom = False
        component_shortages = []

        if is_row_matched:
            sid_val = result.get("style_id")
            resolved_color = result.get("color", "") or color_val
            resolved_size = result.get("size", "") or size_val

            # Tier 1: Finished Goods Stock Check
            if sid_val and hasattr(db, "fg_location_inventory"):
                sid_str = str(sid_val)
                c_clean = (resolved_color or "").strip()
                s_clean = (resolved_size or "").strip()
                fg_key = (sid_str, c_clean.lower(), s_clean.lower())

                sid_oid = ObjectId(sid_str) if ObjectId.is_valid(sid_str) else sid_str
                q_loc = {
                    "$or": [{"style_id": sid_oid}, {"style_id": sid_str}],
                    "qty": {"$gt": 0},
                }
                if c_clean:
                    q_loc["color"] = {"$regex": f"^{re.escape(c_clean)}$", "$options": "i"}
                if s_clean:
                    q_loc["size"] = {"$regex": f"^{re.escape(s_clean)}$", "$options": "i"}

                loc_docs = await _safe_to_list(db.fg_location_inventory.find(q_loc).sort([("created_at", 1), ("location_code", 1)]))
                total_free_fg = 0
                for loc in loc_docs:
                    loc_code = loc.get("location_code")
                    if loc_code and hasattr(db, "warehouse_locations"):
                        wloc = await _safe_find_one(db.warehouse_locations, {"location_code": loc_code})
                        if wloc and wloc.get("status") == "blocked":
                            continue
                    qty_val = int(loc.get("qty", 0) or 0)
                    res_val = int(loc.get("reserved_qty", 0) or 0)
                    total_free_fg += max(0, qty_val - res_val)

                claimed_fg = in_flight_fg_claimed.get(fg_key, 0)
                avail_fg = max(0, total_free_fg - claimed_fg)
                covered_qty = min(qty, avail_fg)
                remaining_qty = qty - covered_qty
                in_flight_fg_claimed[fg_key] = claimed_fg + covered_qty
            else:
                covered_qty = 0
                remaining_qty = qty

            # Tier 2: BOM and Component Stock Check for uncovered remainder
            if remaining_qty == 0:
                fulfillment_status = "in_stock_picklist"
                components_available = True
                has_bom = True
                component_shortages = []
            else:
                sid_str = str(sid_val)
                sid_oid = ObjectId(sid_str) if ObjectId.is_valid(sid_str) else sid_str
                bom = []
                if sid_val and hasattr(db, "style_component_mapping"):
                    bom = await _safe_to_list(db.style_component_mapping.find({
                        "$or": [{"style_id": sid_oid}, {"style_id": sid_str}],
                        "active": {"$ne": False},
                    }))

                if not bom:
                    has_bom = False
                    components_available = False
                    component_shortages = [{
                        "component_code": "NO_BOM",
                        "component_name": "No BOM Mapped",
                        "available": 0,
                        "required": remaining_qty,
                    }]
                    fulfillment_status = "partial_stock" if covered_qty > 0 else "produce_shortage"
                else:
                    has_bom = True
                    comp_shortages = []
                    needed_res = []
                    all_comp_ok = True

                    for b in bom:
                        comp_id = b.get("component_id")
                        comp = None
                        if comp_id and hasattr(db, "component_master"):
                            comp_oid = ObjectId(comp_id) if ObjectId.is_valid(str(comp_id)) else str(comp_id)
                            comp = await _safe_find_one(db.component_master, {"$or": [{"_id": comp_oid}, {"_id": str(comp_id)}]})
                        if not comp and b.get("component_code") and hasattr(db, "component_master"):
                            comp = await _safe_find_one(db.component_master, {"component_code": b.get("component_code")})

                        need_per_pair = float(b.get("quantity_per_pair", b.get("qty_per_pair", 1)) or 1)
                        total_need = need_per_pair * remaining_qty

                        if not comp:
                            all_comp_ok = False
                            comp_shortages.append({
                                "component_code": b.get("component_code", "UNKNOWN"),
                                "component_name": b.get("component_name", "Unknown Component"),
                                "available": 0,
                                "required": total_need,
                                "shortage": total_need,
                            })
                            continue

                        comp_key = str(comp.get("_id", comp.get("component_code")))
                        c_stock = int(comp.get("current_stock", 0) or 0)
                        r_stock = int(comp.get("reserved_stock", 0) or 0)
                        free_c = max(0, c_stock - r_stock)
                        already_c = in_flight_comp_claimed.get(comp_key, 0)
                        effective_avail = max(0, free_c - already_c)

                        if effective_avail < total_need:
                            all_comp_ok = False
                            comp_shortages.append({
                                "component_code": comp.get("component_code", ""),
                                "component_name": comp.get("component_name", ""),
                                "available": effective_avail,
                                "required": total_need,
                                "shortage": total_need - effective_avail,
                            })
                        else:
                            needed_res.append((comp_key, comp, total_need))

                    component_shortages = comp_shortages
                    if all_comp_ok:
                        components_available = True
                        fulfillment_status = "partial_stock" if covered_qty > 0 else "produce_ready"
                        for comp_key, comp, total_need in needed_res:
                            in_flight_comp_claimed[comp_key] = in_flight_comp_claimed.get(comp_key, 0) + total_need
                    else:
                        components_available = False
                        fulfillment_status = "partial_stock" if covered_qty > 0 else "produce_shortage"

            matched_rows.append({
                "row_index": r_idx,
                "order_id": order_id or batch_name,
                "style_code": result["style_code"],
                "style_id": result["style_id"],
                "color": resolved_color,
                "size": resolved_size,
                "quantity": qty,
                "covered_qty": covered_qty,
                "remaining_qty": remaining_qty,
                "fulfillment_status": fulfillment_status,
                "components_available": components_available,
                "has_bom": has_bom,
                "component_shortages": component_shortages,
                "unit_price": float(r.get(resolved_cols.get("selling_price", ""), 0.0) or 0.0) if resolved_cols.get("selling_price") else 0.0,
            })
        else:
            unresolved_rows.append({
                "row_index": r_idx,
                "order_id": order_id or batch_name,
                "raw_sku": raw_leaf,
                "cleaned_sku": cleaned_leaf,
                "color": color_val,
                "size": size_val,
                "quantity": qty,
            })

        canonical_rows.append({
            "source_row_index": r_idx,
            "order_id": None if is_picklist else (raw_order_id.strip() or None),
            "picklist_batch_id": batch_name if is_picklist else None,
            "leaf_sku_raw": raw_leaf,
            "leaf_sku_replaced_prefix": replaced_prefix,
            "leaf_sku_stripped_prefix": stripped_prefix,
            "leaf_sku": cleaned_leaf,
            "group_id": group_id or "—",
            "derived_size": size_val or "—",
            "size": size_val,
            "color": color_val or result.get("color", ""),
            "style_code": result.get("style_code") or "—",
            "style_id": result.get("style_id"),
            "qty": qty,
            "matched": is_row_matched,
            "match_via": result.get("match_via") or ("sku_map" if is_row_matched else None),
            "covered_qty": covered_qty if is_row_matched else 0,
            "remaining_qty": remaining_qty if is_row_matched else qty,
            "fulfillment_status": fulfillment_status if is_row_matched else None,
            "components_available": components_available if is_row_matched else False,
            "has_bom": has_bom if is_row_matched else False,
            "component_shortages": component_shortages if is_row_matched else [],
            "exception_reason": exc_reason,
        })

    if not dry_run and len(matched_rows) == 0:
        raise HTTPException(status_code=400, detail="Nothing to commit — no rows matched.")

    created_picklists = []
    jobs = []

    if not dry_run:
        # Tier 1: Auto-generate ERP Picklists for covered quantities
        order_lines_by_order = defaultdict(list)
        for m in matched_rows:
            if m.get("covered_qty", 0) > 0:
                order_lines_by_order[m["order_id"]].append({
                    "style_id": m["style_id"],
                    "style_code": m["style_code"],
                    "color": m["color"],
                    "size": m["size"],
                    "quantity": m["covered_qty"],
                })

        for oid, lines in order_lines_by_order.items():
            try:
                from routes.wms import _generate_picklist_for_order
                pl_doc, cov, unc = await _generate_picklist_for_order(
                    order_id=oid,
                    channel=platform_lc,
                    order_lines=lines,
                    user_email=u["email"],
                    db=db,
                )
                if pl_doc and pl_doc.get("picklist_no") and pl_doc.get("items"):
                    created_picklists.append({
                        "picklist_no": pl_doc["picklist_no"],
                        "order_id": oid,
                        "total_qty": pl_doc.get("total_qty", 0),
                        "items_count": len(pl_doc.get("items", [])),
                    })
            except Exception as e:
                log.warning(f"Error generating picklist for order {oid}: {e}")

        # Tier 2: Insert production jobs only for uncovered remaining quantities
        for m in matched_rows:
            rem_qty = m.get("remaining_qty", 0)
            if rem_qty <= 0:
                continue

            stage = "cutting" if m.get("components_available") else "procurement"
            stage_note = "Stock shortage, components available -> cutting" if m.get("components_available") else "Stock & component shortage -> procurement"

            jobs.append({
                "po_id": None,
                "po_number": m["order_id"],
                "client_name": platform_lc,
                "channel": platform_lc,
                "source_type": "online_channel",
                "order_date": today,
                "style_code": m["style_code"],
                "style_id": m["style_id"],
                "style_match_status": "matched",
                "color": m["color"],
                "size": m["size"],
                "quantity": rem_qty,
                "original_ordered_qty": m["quantity"],
                "covered_from_stock_qty": m.get("covered_qty", 0),
                "components_available": m.get("components_available", False),
                "has_bom": m.get("has_bom", False),
                "component_shortages": m.get("component_shortages", []),
                "unit_price": m["unit_price"],
                "amount": round(m["unit_price"] * rem_qty, 2),
                "completed_qty": 0,
                "rejected_qty": 0,
                "stage": stage,
                "stage_entered_at": entered,
                "stage_deadline": deadline,
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "history": [{"stage": stage, "at": now_iso(), "by": u["email"],
                             "notes": f"Configured import from {platform_lc}: {stage_note}"}],
            })

            # If stage is cutting, reserve component stock in component_master
            if stage == "cutting" and hasattr(db, "component_master") and m.get("style_id"):
                try:
                    sid_oid = ObjectId(m["style_id"]) if ObjectId.is_valid(str(m["style_id"])) else str(m["style_id"])
                    bom_items = await _safe_to_list(db.style_component_mapping.find({
                        "$or": [{"style_id": sid_oid}, {"style_id": str(m["style_id"])}],
                        "active": {"$ne": False},
                    }))
                    for b in bom_items:
                        comp_id = b.get("component_id")
                        need_per_pair = float(b.get("quantity_per_pair", b.get("qty_per_pair", 1)) or 1)
                        tot_need = int(round(need_per_pair * rem_qty))
                        if comp_id and tot_need > 0:
                            c_oid = ObjectId(comp_id) if ObjectId.is_valid(str(comp_id)) else str(comp_id)
                            c_up = db.component_master.update_one(
                                {"$or": [{"_id": c_oid}, {"_id": str(comp_id)}]},
                                {"$inc": {"reserved_stock": tot_need}, "$set": {"updated_at": now_iso()}}
                            )
                            if inspect.isawaitable(c_up):
                                await c_up
                except Exception as e:
                    log.warning(f"Failed to reserve components for job {m['style_code']}: {e}")

        if jobs and hasattr(db, "production_jobs"):
            try:
                p_res = db.production_jobs.insert_many(jobs)
                if inspect.isawaitable(p_res):
                    await p_res
            except Exception:
                pass

        if unresolved_rows and hasattr(db, "online_order_exceptions"):
            exc_docs = [{
                "order_id": u["order_id"],
                "raw_sku": u.get("raw_sku", ""),
                "reason": "Unmapped color/size: not found in SKU map",
                "created_at": now_iso(),
            } for u in unresolved_rows]
            try:
                e_res = db.online_order_exceptions.insert_many(exc_docs)
                if inspect.isawaitable(e_res):
                    await e_res
            except Exception:
                pass

    order_style_rows = 0 if is_picklist else len(rows)
    picklist_rows = len(rows) if is_picklist else 0
    pairs_fulfilled_from_stock = sum(m.get("covered_qty", 0) for m in matched_rows)
    pairs_to_manufacture = sum(m.get("remaining_qty", 0) for m in matched_rows)
    ready_to_produce_pairs = sum(m.get("remaining_qty", 0) for m in matched_rows if m.get("components_available"))
    shortage_pairs = sum(m.get("remaining_qty", 0) for m in matched_rows if not m.get("components_available"))

    stats = {
        "total_rows_read": len(rows),
        "matched": len(matched_rows),
        "unmatched": len(unresolved_rows),
        "order_style_rows": order_style_rows,
        "picklist_rows": picklist_rows,
        "distinct_orders": len(distinct_orders),
        "derivation_failed": derivation_failed,
        "empty_leaf_sku": empty_leaf_sku,
        "pairs_fulfilled_from_stock": pairs_fulfilled_from_stock,
        "pairs_to_manufacture": pairs_to_manufacture,
        "ready_to_produce_pairs": ready_to_produce_pairs,
        "shortage_pairs": shortage_pairs,
    }

    batch_id_str = f"IMP_{platform_lc}_{now_iso()[:19].replace('-', '').replace(':', '').replace('T', '_')}"
    return {
        "platform": platform_lc,
        "filename": file.filename or "",
        "is_picklist": is_picklist,
        "picklist_batch_id": batch_name if is_picklist else None,
        "header_row_1_based": header_row_1_based,
        "total_rows": len(rows),
        "matched_count": len(matched_rows),
        "unresolved_count": len(unresolved_rows),
        "dry_run": dry_run,
        "import_batch_id": batch_id_str if not dry_run else None,
        "matched": matched_rows[:100],
        "unresolved": unresolved_rows[:100],
        "rows": canonical_rows,
        "stats": stats,
        "committed": {
            "jobs_created": len(jobs) if not dry_run else 0,
            "picklists_created": len(created_picklists) if not dry_run else 0,
            "picklist_details": created_picklists if not dry_run else [],
            "orders_created": (len(distinct_orders) if not is_picklist else (1 if matched_rows else 0)) if not dry_run else 0,
            "items_created": len(matched_rows) if not dry_run else 0,
            "pairs_fulfilled_from_stock": pairs_fulfilled_from_stock if not dry_run else 0,
            "pairs_to_manufacture": pairs_to_manufacture if not dry_run else 0,
            "exceptions_queued": len(unresolved_rows) if not dry_run else 0,
        },
    }


@online_orders_router.post("/online-orders/dispatch-import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_dispatch_orders(
    file: UploadFile = File(...),
    platform: str = Query(..., description="Platform identifier matching order_import_format_configs"),
    dry_run: bool = False,
    request: Request = None,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = platform.strip().lower()

    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "dispatch", "active": True}
    )
    if not cfg_doc:
        raise HTTPException(400, f"No active dispatch import format config found for platform '{platform_lc}'")

    content = await file.read()
    sheet_loc = SheetLocator(**_sanitize_sheet_loc(cfg_doc.get("sheet_locator", {"type": "first_sheet"})))
    header_loc = HeaderLocator(**_sanitize_header_loc(cfg_doc.get("header_locator", {"type": "fixed_row", "row": 0})))
    skip_rows = int(cfg_doc.get("skip_rows_after_header", 0) or 0)

    headers, rows = _parse_tabular_bytes(
        content=content,
        filename=file.filename or "",
        sheet_locator=sheet_loc,
        header_locator=header_loc,
        skip_rows_after_header=skip_rows,
    )

    if not rows:
        raise HTTPException(400, "No data rows found in dispatch file")

    col_map = cfg_doc.get("column_map") or {}
    resolved_cols = {}
    for canon_field, target_name in col_map.items():
        if target_name:
            actual = _resolve_column(target_name, headers)
            if actual:
                resolved_cols[canon_field] = actual

    leaf_sku_col = resolved_cols.get("leaf_sku")
    if not leaf_sku_col:
        raise HTTPException(400, f"Configured leaf_sku column '{col_map.get('leaf_sku')}' not found in headers")

    from routes.sku_map import resolve_style, split_leaf_sku

    prefixes_to_strip = cfg_doc.get("known_sku_prefixes_to_strip", [])
    prefix_replacements = cfg_doc.get("known_sku_prefix_replacements", {})

    matched_rows = []
    unresolved_rows = []

    for r_idx, r in enumerate(rows, start=1):
        raw_leaf = r.get(leaf_sku_col, "").strip()
        if not raw_leaf:
            continue

        cleaned_leaf = raw_leaf
        for wrong, right in prefix_replacements.items():
            if cleaned_leaf.startswith(wrong):
                cleaned_leaf = right + cleaned_leaf[len(wrong):]
        cleaned_leaf = strip_known_prefixes(cleaned_leaf, prefixes_to_strip)

        group_id, size_token, _ = split_leaf_sku(cleaned_leaf)
        color_val = ""
        size_val = size_token or ""

        sec_sku = ""
        if resolved_cols.get("channel_sku"):
            sec_sku = r.get(resolved_cols.get("channel_sku", ""), "").strip()
        elif resolved_cols.get("myntra_sku_code"):
            sec_sku = r.get(resolved_cols.get("myntra_sku_code", ""), "").strip()

        result = await resolve_style(
            source_type="online_channel",
            source_name=platform_lc,
            external_sku=cleaned_leaf,
            external_color=color_val or None,
            external_size=size_val or None,
            secondary_sku=sec_sku or None,
            db=db,
        )

        order_id = r.get(resolved_cols.get("order_id", ""), "") if resolved_cols.get("order_id") else ""
        order_rel = r.get(resolved_cols.get("order_release_id", ""), "") if resolved_cols.get("order_release_id") else ""

        if result["matched"]:
            matched_rows.append({
                "row_index": r_idx,
                "order_id": order_id,
                "order_release_id": order_rel,
                "style_code": result["style_code"],
                "style_id": result["style_id"],
                "color": result["color"],
                "size": result["size"],
                "packed_on": r.get(resolved_cols.get("packed_on", ""), "") if resolved_cols.get("packed_on") else now_iso()[:10],
            })
        else:
            unresolved_rows.append({
                "row_index": r_idx,
                "order_id": order_id,
                "raw_sku": raw_leaf,
            })

    if not dry_run and len(matched_rows) == 0:
        raise HTTPException(status_code=400, detail="Nothing to commit — no rows matched.")

    if not dry_run:
        # Record movements
        movements = []
        for m in matched_rows:
            movements.append({
                "style_id": m["style_id"],
                "style_code": m["style_code"],
                "color": m["color"],
                "size": m["size"],
                "movement_type": "dispatched",
                "quantity": 1,
                "reference_id": m["order_release_id"] or m["order_id"],
                "platform": platform_lc,
                "created_at": now_iso(),
                "created_by": u["email"],
            })
        if movements:
            await db.fg_stock_movements.insert_many(movements)

    return {
        "platform": platform_lc,
        "total_rows": len(rows),
        "matched_count": len(matched_rows),
        "unresolved_count": len(unresolved_rows),
        "dry_run": dry_run,
    }


def strip_excel_apostrophe(val: Any) -> str:
    s = str(val or "").strip()
    if s.startswith("'") or s.startswith("`"):
        return s[1:].strip()
    return s


def apply_prefix_replacements(sku: str, replacements: Dict[str, str]) -> Tuple[str, Optional[str]]:
    s = (sku or "").strip()
    if not s or not replacements:
        return s, None
    for wrong in sorted(replacements.keys(), key=len, reverse=True):
        if not wrong:
            continue
        right = str(replacements.get(wrong) or "")
        if s.startswith(wrong):
            rest = s[len(wrong):]
            if not rest or rest[0] in "_-":
                return right + rest, wrong
    return s, None


def _has_val(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip()
    if not s:
        return False
    if s.lower() in ("null", "nan", "none", "n/a", "na", "-"):
        return False
    return True


async def _check_internal_dispatch_record(canon: dict, platform: str, db=None) -> bool:
    if db is None:
        db = get_db()
    order_release_id = canon.get("order_release_id")
    order_id = canon.get("order_id")
    leaf_sku = canon.get("leaf_sku") or canon.get("leaf_sku_raw")
    platform_lc = (platform or "").strip().lower()

    item_or_conditions = []
    if order_release_id:
        item_or_conditions.append({"order_release_id": order_release_id})
    if order_id:
        if leaf_sku:
            item_or_conditions.append({
                "order_id": order_id,
                "$or": [{"leaf_sku": leaf_sku}, {"leaf_sku_raw": leaf_sku}]
            })
        else:
            item_or_conditions.append({"order_id": order_id})

    if item_or_conditions:
        item = await db.online_order_items.find_one({
            "platform": platform_lc,
            "$or": item_or_conditions,
            "$and": [
                {
                    "$or": [
                        {"stage": "dispatched"},
                        {"dispatched_at": {"$ne": None}},
                        {"was_packed": True},
                        {"packed_on": {"$ne": None}},
                    ]
                }
            ]
        })
        if item:
            return True
    return False


async def _classify_monthly_row(canon: dict, platform: str = "", db=None) -> dict:
    status = (canon.get("order_status") or "").strip().upper()

    was_packed = _has_val(canon.get("packed_on"))
    has_rto    = _has_val(canon.get("rto_creation_date"))
    has_return = _has_val(canon.get("return_creation_date"))
    cancelled_post_pack = (status == "F" and was_packed)

    was_returned_to_stock = has_rto or has_return or cancelled_post_pack
    is_pending    = status in ("SH", "PK")
    is_net_sold   = was_packed and not was_returned_to_stock and not is_pending

    has_dispatch_discrepancy = False
    discrepancy_reason = None
    never_touched = False

    if not was_packed:
        has_internal_dispatch = await _check_internal_dispatch_record(canon, platform, db=db)
        if has_internal_dispatch:
            never_touched = False
            has_dispatch_discrepancy = True
            discrepancy_reason = "Monthly report lacks packed_on date, but internal system records show unit was dispatched."
            if "flags" not in canon:
                canon["flags"] = []
            canon["flags"].append("dispatch_discrepancy")
            disc_text = "Discrepancy: source file lacks packed_on, but internal records confirm dispatch"
            existing_reason = canon.get("exception_reason")
            canon["exception_reason"] = f"{existing_reason} [{disc_text}]" if existing_reason else disc_text
        else:
            never_touched = True
    else:
        never_touched = False

    if was_returned_to_stock:
        if has_rto:
            reason = "rto"
        elif has_return:
            reason = "customer_return"
        elif cancelled_post_pack:
            reason = "cancelled_after_pack"
        else:
            reason = "unknown"
    else:
        reason = None

    canon["was_packed"]                = was_packed
    canon["was_returned_to_stock"]     = was_returned_to_stock
    canon["is_pending"]                = is_pending
    canon["is_net_sold"]               = is_net_sold
    canon["never_touched_inventory"]   = never_touched
    canon["has_dispatch_discrepancy"]  = has_dispatch_discrepancy
    canon["discrepancy_reason"]        = discrepancy_reason
    canon["return_reason"]             = reason
    return canon


def _return_ref_id(platform: str, order_release_id: Optional[str],
                   order_id: Optional[str], leaf_sku: str) -> str:
    key = order_release_id or order_id or "no-order"
    return f"monthly_return:{platform}:{key}:{leaf_sku}"


async def _get_settlement_return_type(order_release_id: Optional[str],
                                      leaf_sku: str, db=None) -> Optional[str]:
    if db is None:
        db = get_db()
    if not order_release_id:
        return None
    try:
        doc = await db.settlement_reverse.find_one({
            "order_release_id": order_release_id,
            "$or": [{"leaf_sku": leaf_sku}, {"sku_id": leaf_sku}],
        })
    except Exception:
        return None
    if not doc:
        return None
    rt = str(doc.get("return_type") or "").strip().lower()
    if rt in ("damaged", "damage", "unsellable", "not_returnable"):
        return "damaged"
    return None


async def _record_monthly_return(
    *,
    canon: dict,
    platform: str,
    batch_id: str,
    user_email: str,
    db=None,
) -> dict:
    if db is None:
        db = get_db()
    style_id   = canon.get("style_id")
    style_code = canon.get("style_code")
    color      = canon.get("color")
    size       = canon.get("size") or canon.get("derived_size")
    order_id   = canon.get("order_id")
    order_release_id = canon.get("order_release_id")
    leaf_sku   = canon.get("leaf_sku")

    ref_id = _return_ref_id(platform, order_release_id, order_id, leaf_sku)

    prior = await db.fg_stock_movements.find_one({
        "reference_id":  ref_id,
        "movement_type": {"$in": ["return_in", "return_restocked", "return_damaged"]},
    })
    if prior:
        return {"skipped": True, "reason": "prior_movement_exists"}

    settlement_flag = await _get_settlement_return_type(order_release_id, leaf_sku, db=db)
    close_type = "return_damaged" if settlement_flag == "damaged" else "return_restocked"

    from routes.inventory import _apply_movement
    from models.inventory import FgStockMovementIn

    await _apply_movement(
        FgStockMovementIn(
            style_id=style_id, color=color, size=size,
            movement_type="return_in", quantity=1,
            reference_type="online_order",
            reference_id=ref_id,
            notes=f"[{platform}] monthly-report {canon.get('return_reason')} · batch {batch_id}",
        ),
        user_email,
        db=db,
    )
    await _apply_movement(
        FgStockMovementIn(
            style_id=style_id, color=color, size=size,
            movement_type=close_type, quantity=1,
            reference_type="online_order",
            reference_id=ref_id,
            notes=f"[{platform}] monthly-report reconciliation · reason={canon.get('return_reason')}",
        ),
        user_email,
        db=db,
    )
    return {"skipped": False, "close_type": close_type}


def _parse_sku_style_and_size(raw_sku: str) -> Tuple[str, str, str]:
    s = (raw_sku or "").strip()
    if s.startswith("FLL_") or s.startswith("FLL-"):
        s = "FL" + s[3:]
    m = re.match(r"^(.*?)[-_]([A-Za-z]{1,4})[-_]([0-9]{1,2}(?:\.[0-9])?)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    m2 = re.match(r"^(.*?)[-_]([0-9]{1,2}(?:\.[0-9])?)$", s)
    if m2:
        return m2.group(1).strip(), "", m2.group(2).strip()
    return s, "", ""


def _parse_myntra_pnl_workbook(content: bytes) -> Tuple[str, str, Dict[str, Any], List[Dict[str, Any]]]:
    """Parses Myntra Monthly PnL Excel workbook containing PnL_Summary, Glossary, and SKU_Detail."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Could not read uploaded Excel file: {str(e)}")

    sheet_names = wb.sheetnames
    if "SKU_Detail" not in sheet_names:
        raise HTTPException(
            400,
            "Invalid file: Missing 'SKU_Detail' sheet. Please upload the official Myntra Monthly PnL Excel report (PnLReport_xxxxx.xlsx)."
        )

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    seller_id = ""
    pnl_summary: Dict[str, Any] = {
        "report_month_text": "",
        "seller_id": "",
        "gross_sales": 0.0,
        "gross_units": 0,
        "returns_amount": 0.0,
        "returns_units": 0,
        "net_sales": 0.0,
        "net_units": 0,
        "total_expenses": 0.0,
        "forward_expense": 0.0,
        "reverse_expense": 0.0,
        "fwd_commission": 0.0,
        "rev_logistic_charge": 0.0,
        "net_sales_after_expenses": 0.0,
        "product_gst": 0.0,
        "bank_settlement_projected": 0.0,
        "bank_settlement_settled": 0.0,
        "bank_settlement_unsettled": 0.0,
        "earnings_on_platform": 0.0,
        "platform_net_margin_pct": 0.0,
    }

    if "PnL_Summary" in sheet_names:
        ws_sum = wb["PnL_Summary"]
        for r in range(1, ws_sum.max_row + 1):
            k = ws_sum.cell(r, 1).value
            v = ws_sum.cell(r, 2).value
            units = ws_sum.cell(r, 3).value
            if not k:
                continue
            k_str = str(k).strip()
            if "Orders Received During:" in k_str:
                month_str = str(v or "").strip()
                pnl_summary["report_month_text"] = month_str
                m_match = re.search(r"([A-Za-z]+)\s*(\d{4})", month_str)
                if m_match:
                    month_name, year_str = m_match.groups()
                    try:
                        dt = datetime.strptime(f"{month_name} {year_str}", "%B %Y")
                        month = dt.strftime("%Y-%m")
                    except Exception:
                        pass
            elif "Seller ID:" in k_str:
                seller_id = str(v or "").strip()
                pnl_summary["seller_id"] = seller_id
            elif "Gross Sales" in k_str:
                pnl_summary["gross_sales"] = float(v or 0)
                pnl_summary["gross_units"] = int(float(units or 0))
            elif "Returns and Cancellations" in k_str:
                pnl_summary["returns_amount"] = float(v or 0)
                pnl_summary["returns_units"] = int(float(units or 0))
            elif "Estimated Net Sales" in k_str and "After" not in k_str:
                pnl_summary["net_sales"] = float(v or 0)
                pnl_summary["net_units"] = int(float(units or 0))
            elif "Total Expenses" in k_str:
                pnl_summary["total_expenses"] = float(v or 0)
            elif "Forward Expense" in k_str:
                pnl_summary["forward_expense"] = float(v or 0)
            elif "Reverse Expense" in k_str:
                pnl_summary["reverse_expense"] = float(v or 0)
            elif "Commission Fee" in k_str and pnl_summary.get("fwd_commission") == 0.0:
                pnl_summary["fwd_commission"] = float(v or 0)
            elif "Reverse Logistic Charge" in k_str:
                pnl_summary["rev_logistic_charge"] = float(v or 0)
            elif "Estimated Net Sales After Expenses" in k_str:
                pnl_summary["net_sales_after_expenses"] = float(v or 0)
            elif "Product GST" in k_str:
                pnl_summary["product_gst"] = float(v or 0)
            elif "Bank Settlement (Projected)" in k_str:
                pnl_summary["bank_settlement_projected"] = float(v or 0)
            elif "Bank Settlement (Settled)" in k_str:
                pnl_summary["bank_settlement_settled"] = float(v or 0)
            elif "Bank Settlement (Unsettled)" in k_str:
                pnl_summary["bank_settlement_unsettled"] = float(v or 0)
            elif "Earnings on Platform" in k_str:
                pnl_summary["earnings_on_platform"] = float(v or 0)
            elif "Net Margin" in k_str:
                pnl_summary["platform_net_margin_pct"] = round(float(v or 0) * 100, 2)

    ws_sku = wb["SKU_Detail"]
    header = [str(ws_sku.cell(1, c).value or "").strip() for c in range(1, ws_sku.max_column + 1)]
    sku_rows: List[Dict[str, Any]] = []
    for r in range(2, ws_sku.max_row + 1):
        row_dict = {}
        for c in range(1, ws_sku.max_column + 1):
            col_name = header[c - 1]
            if col_name:
                row_dict[col_name] = ws_sku.cell(r, c).value
        sku_rows.append(row_dict)

    return month, seller_id, pnl_summary, sku_rows


def _parse_flipkart_pnl_workbook(content: bytes) -> Tuple[str, str, Dict[str, Any], List[Dict[str, Any]]]:
    """Parses Flipkart Monthly PnL Excel workbook containing Overall Summary, SKU-level P&L, and Orders P&L."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(400, f"Could not read uploaded Excel file: {str(e)}")

    sheet_names = wb.sheetnames
    if "Overall Summary" not in sheet_names and "SKU-level P&L" not in sheet_names:
        raise HTTPException(
            400,
            "Invalid file: Missing 'Overall Summary' or 'SKU-level P&L' sheet. Please upload the official Flipkart Monthly PnL Excel report."
        )

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    seller_id = "Flipkart Seller"

    summary_map = {}
    if "Overall Summary" in sheet_names:
        ws_sum = wb["Overall Summary"]
        for r in range(1, ws_sum.max_row + 1):
            c1 = ws_sum.cell(r, 1).value
            c2 = ws_sum.cell(r, 2).value
            c3 = ws_sum.cell(r, 3).value
            if not c1:
                continue
            c1_str = str(c1).strip()
            summary_map[c1_str] = (c2, c3)
            clean_k = re.sub(r"^[^\w]+", "", c1_str).strip()
            summary_map[clean_k] = (c2, c3)
            if "Orders Recieved During:" in c1_str or "Orders Received During:" in c1_str:
                period_str = str(c2 or "").strip()
                m_dt = re.search(r"(\d{4}-\d{2})", period_str)
                if m_dt:
                    month = m_dt.group(1)

    def _val(key, idx=0, default=0.0):
        t = summary_map.get(key)
        if not t or len(t) <= idx or t[idx] is None:
            return default
        try:
            return float(t[idx])
        except (ValueError, TypeError):
            return default

    gross_sales = _val("Gross Sales", 0)
    gross_units = int(_val("Gross Sales", 1))
    returns_amount = _val("Returns and Cancellations", 0)
    returns_units = int(_val("Returns and Cancellations", 1))
    rto_amount = _val("RTO (Logistics Return)", 0)
    rto_units = int(_val("RTO (Logistics Return)", 1))
    rvp_amount = _val("RVP (Customer Return)", 0)
    rvp_units = int(_val("RVP (Customer Return)", 1))
    cancel_amount = _val("Cancelled", 0)
    cancel_units = int(_val("Cancelled", 1))

    est_net_sales = _val("Estimated Net Sales", 0)
    est_net_units = int(_val("Estimated Net Sales", 1))
    seller_discount = _val("Seller-Funded Discount", 0)
    customer_addons = _val("Customer Add-Ons Amount", 0)
    accounted_net_sales = _val("Accounted Net Sales (Seller Price)", 0)

    total_expenses = _val("Total Expenses", 0)
    fixed_fee = _val("Fixed Fee", 0)
    ads_fee = _val("Ads", 0)
    taxes_gst = _val("Taxes (GST)", 0)
    taxes_tcs = _val("Taxes (TCS)", 0)
    taxes_tds = _val("Taxes (TDS)", 0)
    bank_projected = _val("Bank Settlement (Projected)", 0)
    itc = _val("Input Tax Credits", 0)
    platform_earnings = _val("Earnings on Platform", 0)
    already_paid = _val("Already Paid (In Your Bank Account)", 0)
    pending_pay = _val("Pending (Flipkart to pay you)", 0)

    effective_net_sales = accounted_net_sales if accounted_net_sales else est_net_sales

    pnl_summary: Dict[str, Any] = {
        "report_month_text": f"Orders Received: {month}",
        "seller_id": seller_id,
        "gross_sales": round(gross_sales, 2),
        "gross_units": gross_units,
        "returns_amount": round(returns_amount, 2),
        "returns_units": abs(returns_units),
        "rto_amount": round(rto_amount, 2),
        "rto_units": abs(rto_units),
        "rvp_amount": round(rvp_amount, 2),
        "rvp_units": abs(rvp_units),
        "cancelled_amount": round(cancel_amount, 2),
        "cancelled_units": abs(cancel_units),
        "estimated_net_sales": round(est_net_sales, 2),
        "seller_funded_discount": round(seller_discount, 2),
        "customer_addons_amount": round(customer_addons, 2),
        "net_sales": round(effective_net_sales, 2),
        "net_units": est_net_units if est_net_units else (gross_units - abs(returns_units)),
        "total_expenses": round(total_expenses, 2),
        "fixed_fee": round(fixed_fee, 2),
        "ads_fee": round(ads_fee, 2),
        "taxes_gst": round(taxes_gst, 2),
        "taxes_tcs": round(taxes_tcs, 2),
        "taxes_tds": round(taxes_tds, 2),
        "bank_settlement_projected": round(bank_projected, 2),
        "bank_settlement_settled": round(already_paid, 2),
        "bank_settlement_unsettled": round(pending_pay, 2),
        "input_tax_credits": round(itc, 2),
        "earnings_on_platform": round(platform_earnings, 2),
        "platform_net_margin_pct": round((platform_earnings / effective_net_sales * 100), 2) if effective_net_sales > 0 else 0.0,
    }

    sku_rows: List[Dict[str, Any]] = []
    if "SKU-level P&L" in sheet_names:
        ws_sku = wb["SKU-level P&L"]
        for r in range(3, ws_sku.max_row + 1):
            sku_val = ws_sku.cell(r, 1).value
            if not sku_val:
                continue
            sku_code = str(sku_val).strip()
            gross_u = int(float(ws_sku.cell(r, 3).value or 0))
            ret_u = int(float(ws_sku.cell(r, 4).value or 0))
            rto_u = int(float(ws_sku.cell(r, 5).value or 0))
            rvp_u = int(float(ws_sku.cell(r, 6).value or 0))
            cancel_u = int(float(ws_sku.cell(r, 7).value or 0))
            net_u = int(float(ws_sku.cell(r, 8).value or 0))

            est_sales = float(ws_sku.cell(r, 10).value or 0.0)
            order_item_val = float(ws_sku.cell(r, 11).value or 0.0)
            seller_price = float(ws_sku.cell(r, 13).value or 0.0)

            tot_exp = float(ws_sku.cell(r, 14).value or 0.0)
            comm = float(ws_sku.cell(r, 15).value or 0.0)
            coll = float(ws_sku.cell(r, 16).value or 0.0)
            fixed = float(ws_sku.cell(r, 17).value or 0.0)
            pick_pack = float(ws_sku.cell(r, 18).value or 0.0)
            fwd_ship = float(ws_sku.cell(r, 19).value or 0.0)
            rev_ship = float(ws_sku.cell(r, 21).value or 0.0)
            gst = float(ws_sku.cell(r, 32).value or 0.0)
            tcs = float(ws_sku.cell(r, 33).value or 0.0)
            tds = float(ws_sku.cell(r, 34).value or 0.0)

            bank_proj = float(ws_sku.cell(r, 39).value or 0.0)
            itc_val = float(ws_sku.cell(r, 40).value or 0.0)
            net_earn = float(ws_sku.cell(r, 43).value or 0.0)
            settled_amt = float(ws_sku.cell(r, 47).value or 0.0)
            pending_amt = float(ws_sku.cell(r, 48).value or 0.0)

            sku_rows.append({
                "sku_code": sku_code,
                "GrossSalesUnit": gross_u,
                "ReturnsandCancellationsUnit": ret_u,
                "RTO_Units": rto_u,
                "RVP_Units": rvp_u,
                "Cancelled_Units": cancel_u,
                "EstimatedNetSalesUnit": net_u,
                "GrossSalesAmount": order_item_val or est_sales,
                "EstimatedNetSalesAmount": seller_price or est_sales,
                "TotalExpensesAmount": abs(tot_exp),
                "CommissionFee": abs(comm),
                "CollectionFee": abs(coll),
                "FixedFee": abs(fixed),
                "PickAndPackFee": abs(pick_pack),
                "ForwardShippingFee": abs(fwd_ship),
                "ReverseShippingFee": abs(rev_ship),
                "GST_Amount": abs(gst),
                "TCS_Amount": abs(tcs),
                "TDS_Amount": abs(tds),
                "BankSettlementProjected": bank_proj,
                "InputTaxCredits": itc_val,
                "EarningsOnPlatform": net_earn,
                "AmountSettled": settled_amt,
                "AmountPending": pending_amt,
            })

    return month, seller_id, pnl_summary, sku_rows



async def _fetch_monthly_operational_expenses(
    month: str,
    db,
    existing_ov: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetches operational costs (Rent, Electricity, Salaries, Other Basic) and calculates 50% allocation."""
    if existing_ov and isinstance(existing_ov, dict) and "operational_expenses" in existing_ov:
        saved_op = existing_ov["operational_expenses"]
        if isinstance(saved_op, dict) and saved_op.get("rent") is not None:
            return saved_op

    rent_total = 0.0
    elec_total = 0.0
    salaries_total = 0.0
    other_total = 0.0

    try:
        cur = db.expenses.find({"date": {"$regex": f"^{re.escape(month)}"}})
        if hasattr(cur, "to_list"):
            docs = await cur.to_list(1000)
            if inspect.isawaitable(docs):
                docs = await docs
            for exp in (docs or []):
                cat = (exp.get("category") or "").strip().lower()
                amt = float(exp.get("amount") or 0.0)
                if "rent" in cat:
                    rent_total += amt
                elif "elec" in cat or "power" in cat:
                    elec_total += amt
                elif "salaries" in cat or "wages" in cat or "salary" in cat:
                    salaries_total += amt
                else:
                    other_total += amt
    except Exception as e:
        log.warning(f"Error querying db.expenses for month {month}: {e}")

    try:
        if rent_total == 0.0 or elec_total == 0.0:
            recs_res = db.recurring_expenses.find({"active": True}).to_list(100)
            if inspect.isawaitable(recs_res):
                recs_res = await recs_res
            for r in (recs_res or []):
                cat = (r.get("category") or "").strip().lower()
                amt = float(r.get("amount") or 0.0)
                if rent_total == 0.0 and "rent" in cat:
                    rent_total += amt
                elif elec_total == 0.0 and ("elec" in cat or "power" in cat):
                    elec_total += amt
    except Exception as e:
        log.warning(f"Error checking db.recurring_expenses: {e}")

    if rent_total == 0.0:
        rent_total = 85000.0
    if elec_total == 0.0:
        elec_total = 12500.0
    if salaries_total == 0.0:
        salaries_total = 30000.0
    if other_total == 0.0:
        other_total = 10000.0

    total_op = round(rent_total + elec_total + salaries_total + other_total, 2)
    alloc_pct = 50.0
    allocated_op = round(total_op * (alloc_pct / 100.0), 2)

    return {
        "allocation_pct": alloc_pct,
        "rent": round(rent_total, 2),
        "electricity": round(elec_total, 2),
        "salaries": round(salaries_total, 2),
        "other_basic": round(other_total, 2),
        "total_monthly_operational_cost": total_op,
        "allocated_operational_cost": allocated_op,
    }


async def _build_pnl_reconciliation_overview(
    month: str,
    seller_id: str,
    pnl_summary: Dict[str, Any],
    sku_rows: List[Dict[str, Any]],
    platform: str,
    filename: str,
    db,
) -> Dict[str, Any]:
    """Groups SKUs, maps to Style Master, computes COGS, subtracts 50% operational expenses, and calculates Actual Net Profit."""
    existing_ov = await _safe_find_one(
        getattr(db, "online_monthly_reconciliation_overviews", None),
        {"platform": platform, "month": month}
    )
    saved_costs = {}
    if existing_ov and isinstance(existing_ov, dict) and "styles" in existing_ov:
        for st_item in existing_ov.get("styles", []):
            if st_item.get("style_code") and st_item.get("unit_production_cost") is not None:
                saved_costs[st_item["style_code"]] = float(st_item["unit_production_cost"])

    baseline_snap = await _safe_find_one(getattr(db, "style_cost_snapshots", None), {"total_cost": {"$gt": 0}})
    default_unit_cost = float(baseline_snap["total_cost"]) if (baseline_snap and isinstance(baseline_snap, dict) and "total_cost" in baseline_snap) else 210.0

    all_styles_cur = getattr(db, "styles", None)
    all_styles = []
    if all_styles_cur is not None and hasattr(all_styles_cur, "find"):
        try:
            res = all_styles_cur.find().to_list(1000)
            if inspect.isawaitable(res):
                res = await res
            all_styles = res or []
        except Exception:
            all_styles = []

    style_by_code = {str(s.get("code") or "").strip().lower(): s for s in all_styles if s.get("code")}

    all_sku_maps = []
    sku_map_cur = getattr(db, "sku_map", None)
    if sku_map_cur is not None and hasattr(sku_map_cur, "find"):
        try:
            res_m = sku_map_cur.find().to_list(1000)
            if inspect.isawaitable(res_m):
                res_m = await res_m
            all_sku_maps = res_m or []
        except Exception:
            all_sku_maps = []

    map_by_ext = {}
    for sm in all_sku_maps:
        if sm.get("external_sku"):
            map_by_ext[str(sm["external_sku"]).strip().lower()] = sm

    sku_bifurcation: List[Dict[str, Any]] = []
    style_groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "style_code": "",
        "brand": "",
        "style_name": "",
        "article_type": "Footwear",
        "colors": set(),
        "sizes": defaultdict(int),
        "gross_units": 0,
        "returns_units": 0,
        "net_sold_qty": 0,
        "gross_sales": 0.0,
        "net_sold_seller_price": 0.0,
        "platform_expenses": 0.0,
        "platform_earnings": 0.0,
        "unit_production_cost": default_unit_cost,
        "total_production_cost": 0.0,
        "gross_profit": 0.0,
        "contribution": 0.0,
        "total_orders": 0,
        "packed_qty": 0,
        "returned_qty": 0,
        "rto_qty": 0,
        "cancelled_qty": 0,
        "pending_qty": 0,
        "total_seller_price": 0.0,
    })

    for r in sku_rows:
        sku = str(r.get("sku_code") or "").strip()
        brand = str(r.get("brand_name") or "").strip()
        st_root, col, sz = _parse_sku_style_and_size(sku)

        gross_units = int(float(r.get("GrossSalesUnit") or 0))
        ret_units = int(float(r.get("ReturnsandCancellationsUnit") or 0))
        net_units = int(float(r.get("EstimatedNetSalesUnit") or 0))

        gross_sales = float(r.get("GrossSalesAmount") or 0.0)
        net_sales = float(r.get("EstimatedNetSalesAmount") or 0.0)
        expenses = float(r.get("TotalExpensesAmount") or 0.0)
        earnings = float(r.get("EarningsOnPlatform") or 0.0)
        fwd_exp = float(r.get("ForwardExpense") or 0.0)
        rev_exp = float(r.get("ReverseExpense") or 0.0)
        comm = float(r.get("CommissionFee") or 0.0)
        rev_logistics = float(r.get("ReverseLogisticFee") or 0.0)
        gst = float(r.get("GST_Amount") or 0.0)

        rto_u = int(float(r.get("RTO_Units") or 0))
        rvp_u = int(float(r.get("RVP_Units") or 0))
        canc_u = int(float(r.get("Cancelled_Units") or 0))
        fixed_f = float(r.get("FixedFee") or 0.0)
        settled_amt = float(r.get("AmountSettled") or 0.0)
        pending_amt = float(r.get("AmountPending") or 0.0)

        # Style resolution & cost lookup
        resolved_style = map_by_ext.get(st_root.lower()) or map_by_ext.get(sku.lower())
        u_cost = default_unit_cost
        if st_root in saved_costs:
            u_cost = saved_costs[st_root]
        elif resolved_style and resolved_style.get("style_code"):
            st_doc = style_by_code.get(resolved_style["style_code"].lower())
            if st_doc:
                from routes.styles import compute_style_costing
                b_cost = compute_style_costing(st_doc).get("total_cost", 0)
                if b_cost and float(b_cost) > 0:
                    u_cost = float(b_cost)
        elif st_root.lower() in style_by_code:
            st_doc = style_by_code[st_root.lower()]
            from routes.styles import compute_style_costing
            b_cost = compute_style_costing(st_doc).get("total_cost", 0)
            if b_cost and float(b_cost) > 0:
                u_cost = float(b_cost)

        cogs = round(net_units * u_cost, 2)
        gross_prof = round(net_sales - cogs, 2)
        contrib = round(earnings - cogs, 2)
        margin = round((gross_prof / net_sales * 100), 1) if net_sales > 0 else 0.0

        sku_bifurcation.append({
            "sku_code": sku,
            "style_root": st_root,
            "color": col,
            "size": sz,
            "brand": brand,
            "gross_units": gross_units,
            "returns_units": ret_units,
            "rto_units": rto_u,
            "rvp_units": rvp_u,
            "cancelled_units": canc_u,
            "net_units": net_units,
            "gross_sales": gross_sales,
            "net_sales": net_sales,
            "platform_expenses": expenses,
            "forward_expense": fwd_exp,
            "reverse_expense": rev_exp,
            "commission_fee": comm,
            "reverse_logistic_fee": rev_logistics,
            "fixed_fee": fixed_f,
            "gst_amount": gst,
            "platform_earnings": earnings,
            "settled_amount": settled_amt,
            "pending_amount": pending_amt,
            "unit_production_cost": round(u_cost, 2),
            "total_production_cost": cogs,
            "gross_profit": gross_prof,
            "contribution_after_platform": contrib,
            "margin_pct": margin,
            "is_mapped": bool(resolved_style or st_root.lower() in style_by_code),
        })

        g = style_groups[st_root]
        g["style_code"] = st_root
        g["brand"] = brand or g["brand"]
        g["style_name"] = st_root
        if col:
            g["colors"].add(col)
        if sz:
            g["sizes"][sz] += net_units
        g["gross_units"] += gross_units
        g["returns_units"] += ret_units
        g["rto_qty"] += rto_u
        g["returned_qty"] += (rvp_u if rvp_u > 0 else ret_units)
        g["cancelled_qty"] += canc_u
        g["net_sold_qty"] += net_units
        g["gross_sales"] += gross_sales
        g["net_sold_seller_price"] += net_sales
        g["platform_expenses"] += expenses
        g["platform_earnings"] += earnings
        g["unit_production_cost"] = round(u_cost, 2)
        g["total_production_cost"] += cogs
        g["gross_profit"] += gross_prof
        g["contribution"] += contrib
        g["total_orders"] += gross_units
        g["packed_qty"] += gross_units
        g["total_seller_price"] += gross_sales

    styles_list = []
    tot_sold_units = 0
    tot_sold_rev = 0.0
    tot_prod_cost = 0.0

    for st_code, g in sorted(style_groups.items(), key=lambda kv: kv[1]["net_sold_qty"], reverse=True):
        u_cost = g["unit_production_cost"]
        total_cogs = round(g["total_production_cost"], 2)
        gross_profit = round(g["gross_profit"], 2)
        margin = round((gross_profit / g["net_sold_seller_price"] * 100), 1) if g["net_sold_seller_price"] > 0 else 0.0

        tot_sold_units += g["net_sold_qty"]
        tot_sold_rev += g["net_sold_seller_price"]
        tot_prod_cost += total_cogs

        sorted_sizes = dict(sorted(g["sizes"].items(), key=lambda kv: (float(kv[0]) if kv[0].replace('.', '', 1).isdigit() else kv[0])))

        styles_list.append({
            "style_code":            st_code,
            "brand":                 g["brand"] or "Generic",
            "style_name":            g["style_name"] or st_code,
            "article_type":          g["article_type"] or "Footwear",
            "colors":                sorted(list(g["colors"])),
            "sizes":                 sorted_sizes,
            "total_orders":          g["total_orders"],
            "packed_qty":            g["packed_qty"],
            "returned_qty":          g["returned_qty"],
            "rto_qty":               g["rto_qty"],
            "cancelled_qty":         g["cancelled_qty"],
            "pending_qty":           0,
            "net_sold_qty":          g["net_sold_qty"],
            "total_seller_price":    round(g["total_seller_price"], 2),
            "net_sold_seller_price": round(g["net_sold_seller_price"], 2),
            "unit_production_cost":  round(u_cost, 2),
            "total_production_cost": total_cogs,
            "gross_profit":          gross_profit,
            "platform_earnings":     round(g["platform_earnings"], 2),
            "contribution":          round(g["contribution"], 2),
            "margin_pct":            margin,
        })

    overall_gross_profit = round(tot_sold_rev - tot_prod_cost, 2)
    overall_margin = round((overall_gross_profit / tot_sold_rev * 100), 1) if tot_sold_rev > 0 else 0.0

    op_expenses = await _fetch_monthly_operational_expenses(month, db, existing_ov)
    allocated_op = op_expenses.get("allocated_operational_cost", 0.0)

    total_platform_earnings = float(pnl_summary.get("earnings_on_platform") or sum(s["platform_earnings"] for s in sku_bifurcation))
    actual_net_profit = round(total_platform_earnings - tot_prod_cost - allocated_op, 2)
    actual_net_margin = round((actual_net_profit / tot_sold_rev * 100), 2) if tot_sold_rev > 0 else 0.0

    tot_rto = abs(pnl_summary.get("rto_units") or sum(s.get("rto_units", 0) for s in sku_bifurcation))
    tot_cancelled = abs(pnl_summary.get("cancelled_units") or sum(s.get("cancelled_units", 0) for s in sku_bifurcation))
    tot_returned = abs(pnl_summary.get("rvp_units") or pnl_summary.get("returns_units") or sum(s["returns_units"] for s in sku_bifurcation))

    overview = {
        "platform":                  platform,
        "month":                     month,
        "filename":                  filename,
        "is_pnl_report":             True,
        "seller_id":                 seller_id,
        "pnl_summary":               pnl_summary,
        "operational_expenses":      op_expenses,
        "styles_count":              len(styles_list),
        "total_skus":                len(sku_bifurcation),
        "total_orders":              pnl_summary.get("gross_units") or sum(s["gross_units"] for s in sku_bifurcation),
        "total_packed":              pnl_summary.get("gross_units") or sum(s["gross_units"] for s in sku_bifurcation),
        "total_returned":            tot_returned,
        "total_rto":                 tot_rto,
        "total_cancelled":           tot_cancelled,
        "total_pending":             0,
        "total_net_sold":            tot_sold_units,
        "total_seller_revenue":      round(pnl_summary.get("gross_sales") or sum(s["gross_sales"] for s in sku_bifurcation), 2),
        "net_sold_revenue":          round(tot_sold_rev, 2),
        "platform_expenses":         round(pnl_summary.get("total_expenses") or sum(s["platform_expenses"] for s in sku_bifurcation), 2),
        "platform_earnings":         round(total_platform_earnings, 2),
        "total_cost_of_production":  round(tot_prod_cost, 2),
        "estimated_gross_profit":    overall_gross_profit,
        "overall_margin_pct":        overall_margin,
        "allocated_operational_cost": round(allocated_op, 2),
        "actual_net_profit":         actual_net_profit,
        "actual_net_margin_pct":     actual_net_margin,
        "styles":                    styles_list,
        "sku_bifurcation":           sku_bifurcation,
        "updated_at":                now_iso(),
    }
    return overview


async def _build_monthly_style_overview(
    canonical_rows: List[Dict[str, Any]],
    raw_rows: List[Dict[str, Any]],
    platform: str,
    filename: str,
    db,
) -> Dict[str, Any]:
    dates = [c.get("packed_on") or c.get("delivered_on") or c.get("cancelled_on") for c in canonical_rows]
    valid_dates = [str(d)[:7] for d in dates if d and len(str(d)) >= 7 and str(d)[:4].isdigit()]
    month = max(set(valid_dates), key=valid_dates.count) if valid_dates else datetime.now(timezone.utc).strftime("%Y-%m")

    existing_ov = await _safe_find_one(getattr(db, "online_monthly_reconciliation_overviews", None), {"platform": platform, "month": month})
    saved_costs = {}
    if existing_ov and isinstance(existing_ov, dict) and "styles" in existing_ov:
        for st_item in existing_ov.get("styles", []):
            if st_item.get("style_code") and st_item.get("unit_production_cost") is not None:
                saved_costs[st_item["style_code"]] = float(st_item["unit_production_cost"])

    baseline_snap = await _safe_find_one(getattr(db, "style_cost_snapshots", None), {"total_cost": {"$gt": 0}})
    default_unit_cost = float(baseline_snap["total_cost"]) if (baseline_snap and isinstance(baseline_snap, dict) and "total_cost" in baseline_snap) else 210.0

    grouped: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "style_code": "",
        "brand": "",
        "style_name": "",
        "article_type": "",
        "colors": set(),
        "sizes": defaultdict(int),
        "total_orders": 0,
        "packed_qty": 0,
        "returned_qty": 0,
        "rto_qty": 0,
        "cancelled_qty": 0,
        "pending_qty": 0,
        "net_sold_qty": 0,
        "total_seller_price": 0.0,
        "net_sold_seller_price": 0.0,
        "final_amount_total": 0.0,
    })

    style_cost_cache = {}

    for idx, c in enumerate(canonical_rows):
        raw_r = raw_rows[idx] if idx < len(raw_rows) else {}
        raw_sku = c.get("leaf_sku_raw") or c.get("leaf_sku") or ""
        st_root, col, sz = _parse_sku_style_and_size(raw_sku)

        van = str(raw_r.get("vendor article number") or "").strip()
        style_key = st_root or van or (c.get("style_code") or raw_sku)

        brand = str(raw_r.get("brand") or "").strip()
        sname = str(raw_r.get("style name") or c.get("product_title") or "").strip()
        atype = str(raw_r.get("article type") or "").strip()

        sp = float(c.get("seller_price") or 0.0)
        fa = float(c.get("final_amount") or 0.0)

        g = grouped[style_key]
        g["style_code"] = style_key
        g["brand"] = brand or g["brand"]
        g["style_name"] = sname or g["style_name"]
        g["article_type"] = atype or g["article_type"]
        if col:
            g["colors"].add(col)

        row_size = c.get("size") or sz or c.get("derived_size") or ""
        if row_size:
            g["sizes"][str(row_size)] += 1

        g["total_orders"] += 1
        g["total_seller_price"] += sp
        g["final_amount_total"] += fa

        if c.get("was_packed"):
            g["packed_qty"] += 1

        if c.get("return_reason") == "rto":
            g["rto_qty"] += 1
        elif c.get("return_reason") == "customer_return":
            g["returned_qty"] += 1
        elif c.get("never_touched_inventory") or c.get("return_reason") == "cancelled_after_pack":
            g["cancelled_qty"] += 1
        elif c.get("is_pending"):
            g["pending_qty"] += 1

        if c.get("is_net_sold"):
            g["net_sold_qty"] += 1
            g["net_sold_seller_price"] += sp

    styles_list = []
    tot_sold_units = 0
    tot_sold_rev = 0.0
    tot_prod_cost = 0.0

    for st_code, g in sorted(grouped.items(), key=lambda x: x[1]["total_orders"], reverse=True):
        if st_code in saved_costs:
            u_cost = saved_costs[st_code]
        else:
            if st_code not in style_cost_cache:
                snap = await _safe_find_one(getattr(db, "style_cost_snapshots", None), {"style_code": st_code}, sort=[("effective_date", -1)])
                if snap and isinstance(snap, dict) and float(snap.get("total_cost", 0) or 0) > 0:
                    style_cost_cache[st_code] = float(snap["total_cost"])
                else:
                    st_doc = await _safe_find_one(getattr(db, "styles", None), {
                        "$or": [
                            {"code": {"$regex": f"^{re.escape(st_code)}$", "$options": "i"}},
                            {"article_number": {"$regex": f"^{re.escape(st_code)}$", "$options": "i"}}
                        ]
                    })
                    if st_doc and isinstance(st_doc, dict):
                        from routes.styles import compute_style_costing
                        c_calc = compute_style_costing(st_doc)
                        style_cost_cache[st_code] = float(c_calc.get("total_cost", 0) or default_unit_cost)
                    else:
                        style_cost_cache[st_code] = default_unit_cost
            u_cost = style_cost_cache[st_code]

        total_cogs = round(g["net_sold_qty"] * u_cost, 2)
        gross_profit = round(g["net_sold_seller_price"] - total_cogs, 2)
        margin = round((gross_profit / g["net_sold_seller_price"] * 100), 1) if g["net_sold_seller_price"] > 0 else 0.0

        tot_sold_units += g["net_sold_qty"]
        tot_sold_rev += g["net_sold_seller_price"]
        tot_prod_cost += total_cogs

        sorted_sizes = dict(sorted(g["sizes"].items(), key=lambda kv: (float(kv[0]) if kv[0].replace('.', '', 1).isdigit() else kv[0])))

        styles_list.append({
            "style_code":            st_code,
            "brand":                 g["brand"] or "Generic",
            "style_name":            g["style_name"] or st_code,
            "article_type":          g["article_type"] or "Footwear",
            "colors":                sorted(list(g["colors"])),
            "sizes":                 sorted_sizes,
            "total_orders":          g["total_orders"],
            "packed_qty":            g["packed_qty"],
            "returned_qty":          g["returned_qty"],
            "rto_qty":               g["rto_qty"],
            "cancelled_qty":         g["cancelled_qty"],
            "pending_qty":           g["pending_qty"],
            "net_sold_qty":          g["net_sold_qty"],
            "total_seller_price":    round(g["total_seller_price"], 2),
            "net_sold_seller_price": round(g["net_sold_seller_price"], 2),
            "unit_production_cost":  round(u_cost, 2),
            "total_production_cost": total_cogs,
            "gross_profit":          gross_profit,
            "margin_pct":            margin,
        })

    overall_gross_profit = round(tot_sold_rev - tot_prod_cost, 2)
    overall_margin = round((overall_gross_profit / tot_sold_rev * 100), 1) if tot_sold_rev > 0 else 0.0

    overview = {
        "platform":                  platform,
        "month":                     month,
        "filename":                  filename,
        "styles_count":              len(styles_list),
        "total_orders":              len(canonical_rows),
        "total_packed":              sum(s["packed_qty"] for s in styles_list),
        "total_returned":            sum(s["returned_qty"] for s in styles_list),
        "total_rto":                 sum(s["rto_qty"] for s in styles_list),
        "total_cancelled":           sum(s["cancelled_qty"] for s in styles_list),
        "total_pending":             sum(s["pending_qty"] for s in styles_list),
        "total_net_sold":            tot_sold_units,
        "total_seller_revenue":      round(sum(s["total_seller_price"] for s in styles_list), 2),
        "net_sold_revenue":          round(tot_sold_rev, 2),
        "total_cost_of_production":  round(tot_prod_cost, 2),
        "estimated_gross_profit":    overall_gross_profit,
        "overall_margin_pct":        overall_margin,
        "styles":                    styles_list,
        "updated_at":                now_iso(),
    }
    return overview


@online_orders_router.post("/online-orders/monthly-report-import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_monthly_report(
    file: UploadFile = File(...),
    platform: str = Query("myntra", description="Platform identifier"),
    dry_run: bool = False,
    request: Request = None,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = platform.strip().lower()

    content = await file.read()
    filename = file.filename or ""
    is_excel = filename.lower().endswith(".xlsx") or filename.lower().endswith(".xlsm") or content[:4] == b"PK\x03\x04"

    # Check if this is an official Monthly PnL report (Myntra or Flipkart)
    pnl_platform = None
    if is_excel:
        try:
            import openpyxl
            wb_check = openpyxl.load_workbook(BytesIO(content), read_only=True)
            s_names = wb_check.sheetnames
            if "SKU_Detail" in s_names:
                pnl_platform = "myntra"
            elif "SKU-level P&L" in s_names or ("Overall Summary" in s_names and "Orders P&L" in s_names):
                pnl_platform = "flipkart"
            wb_check.close()
        except Exception:
            pnl_platform = None

    if pnl_platform:
        platform_lc = pnl_platform
        if pnl_platform == "myntra":
            month, seller_id, pnl_summary, sku_rows = _parse_myntra_pnl_workbook(content)
        else:
            month, seller_id, pnl_summary, sku_rows = _parse_flipkart_pnl_workbook(content)

        style_overview = await _build_pnl_reconciliation_overview(
            month=month,
            seller_id=seller_id,
            pnl_summary=pnl_summary,
            sku_rows=sku_rows,
            platform=platform_lc,
            filename=filename,
            db=db,
        )
        import_batch_id = f"MPNL_{platform_lc}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        committed = {
            "styles_reconciled": style_overview["styles_count"],
            "skus_reconciled": len(style_overview["sku_bifurcation"]),
            "items_upserted": 0,
            "orders_upserted": 0,
            "exceptions_queued": 0,
        }
        if not dry_run:
            await _safe_update_one(
                getattr(db, "online_monthly_reconciliation_overviews", None),
                {"platform": platform_lc, "month": style_overview["month"]},
                {"$set": style_overview},
                upsert=True,
            )
            await _log_activity(
                "MONTHLY_PNL_REPORT_IMPORT", "online_orders",
                f"{platform_lc}: {style_overview['styles_count']} styles, "
                f"{len(style_overview['sku_bifurcation'])} SKUs reconciled for month {style_overview['month']} "
                f"(batch {import_batch_id})",
                u.get("email", ""),
                db=db,
            )

        stats = {
            "total_rows": len(style_overview["sku_bifurcation"]),
            "styles_count": style_overview["styles_count"],
            "packed": style_overview.get("total_packed", 0),
            "returned_to_stock": style_overview.get("total_returned", 0),
            "discrepancies": 0,
            "pending": 0,
            "net_sold": style_overview.get("total_net_sold", 0),
            "never_touched_inventory": 0,
            "matched": sum(1 for s in style_overview["sku_bifurcation"] if s.get("is_mapped")),
            "unmatched": sum(1 for s in style_overview["sku_bifurcation"] if not s.get("is_mapped")),
            "empty_leaf_sku": 0,
            "reason_breakdown": {
                "rto": 0,
                "customer_return": style_overview.get("total_returned", 0),
                "cancelled_after_pack": 0,
            },
        }

        return {
            "platform": platform_lc,
            "role": "monthly_report",
            "filename": filename,
            "is_pnl_report": True,
            "month": style_overview["month"],
            "seller_id": seller_id,
            "pnl_summary": pnl_summary,
            "operational_expenses": style_overview.get("operational_expenses"),
            "header_row_1_based": 1,
            "header": [
                "sku_code", "style_root", "color", "size", "gross_units", "returns_units",
                "net_units", "gross_sales", "net_sales", "platform_expenses", "platform_earnings",
                "unit_production_cost", "total_production_cost", "gross_profit",
                "contribution_after_platform", "margin_pct"
            ],
            "dry_run": dry_run,
            "stats": stats,
            "committed": committed if not dry_run else None,
            "import_batch_id": import_batch_id,
            "rows": style_overview["sku_bifurcation"],
            "style_overview": style_overview,
            "sku_bifurcation": style_overview["sku_bifurcation"],
        }

    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "monthly_report", "active": True}
    )
    if not cfg_doc:
        raise HTTPException(400, f"No active monthly report config found for platform '{platform_lc}'")
    sheet_loc = SheetLocator(**_sanitize_sheet_loc(cfg_doc.get("sheet_locator", {"type": "first_sheet"})))
    header_loc = HeaderLocator(**_sanitize_header_loc(cfg_doc.get("header_locator", {"type": "fixed_row", "row": 0})))
    skip_rows = int(cfg_doc.get("skip_rows_after_header", 0) or 0)

    headers, rows = _parse_tabular_bytes(
        content=content,
        filename=file.filename or "",
        sheet_locator=sheet_loc,
        header_locator=header_loc,
        skip_rows_after_header=skip_rows,
    )

    if not rows:
        raise HTTPException(400, "No data rows found in monthly report file")

    col_map = cfg_doc.get("column_map") or {}
    resolved_cols = {}
    for canon_field, target_name in col_map.items():
        if target_name:
            actual = _resolve_column(target_name, headers)
            if actual:
                resolved_cols[canon_field] = actual

    from routes.sku_map import resolve_style, split_leaf_sku

    replacements = cfg_doc.get("known_sku_prefix_replacements") or {}
    prefixes = cfg_doc.get("known_sku_prefixes_to_strip") or []

    style_lookup_cache: Dict[str, Any] = {}
    resolve_cache: Dict[Tuple[str, str, str, str], Any] = {}
    canonical_rows: List[Dict[str, Any]] = []

    for idx, r in enumerate(rows, start=1):
        def _v(canon_key: str):
            col = resolved_cols.get(canon_key)
            return r.get(col) if col else None

        def _str(k: str) -> Optional[str]:
            s = str(_v(k) or "").strip()
            return s if s else None

        def _num(k: str) -> Optional[float]:
            try:
                s = str(_v(k) or "").strip()
                if not s or not _has_val(s):
                    return None
                return float(s.replace(",", "").replace("₹", "").strip())
            except Exception:
                return None

        canon: Dict[str, Any] = {
            "source_row_index": idx,
            "platform":         platform_lc,
            "raw_row":          {k: (str(v) if v is not None else "") for k, v in r.items()},
            "flags":            [],
            "matched":          False,
        }

        canon["order_id"]             = _str("order_id")
        canon["order_release_id"]     = _str("order_release_id")
        canon["size"]                 = _str("size")
        canon["order_status"]         = _str("order_status")
        canon["packed_on"]            = _str("packed_on")
        canon["delivered_on"]         = _str("delivered_on")
        canon["cancelled_on"]         = _str("cancelled_on")
        canon["rto_creation_date"]    = _str("rto_creation_date")
        canon["return_creation_date"] = _str("return_creation_date")
        canon["product_title"]        = _str("product_title")
        canon["final_amount"]         = _num("final_amount")
        canon["total_mrp"]            = _num("total_mrp")
        canon["discount"]             = _num("discount")
        canon["seller_price"]         = _num("seller_price")

        raw_leaf = str(_v("leaf_sku") or "").strip()
        canon["leaf_sku_raw"] = raw_leaf
        if not raw_leaf:
            canon["flags"].append("empty_leaf_sku")
            canon["exception_reason"] = "empty leaf_sku"
            await _classify_monthly_row(canon, platform_lc, db=db)
            canonical_rows.append(canon)
            continue

        leaf = strip_excel_apostrophe(raw_leaf)
        leaf_after_replace, replaced_from = apply_prefix_replacements(leaf, replacements)
        leaf_stripped = strip_known_prefixes(leaf_after_replace, prefixes)
        canon["leaf_sku_replaced_prefix"] = replaced_from
        canon["leaf_sku"] = leaf_stripped

        group_id, size_tok, split_flags = split_leaf_sku(leaf_stripped)
        canon["group_id"] = group_id
        canon["derived_size"] = size_tok
        canon["flags"].extend(split_flags)

        cache_key = (leaf_stripped, group_id or "", str(canon.get("size") or size_tok or ""), str(canon.get("color") or ""))
        if cache_key in resolve_cache:
            resolved = resolve_cache[cache_key]
        else:
            resolved = {"matched": False, "match_via": None}
            for candidate in (leaf_stripped, group_id):
                if not candidate:
                    continue
                res = await resolve_style(
                    source_type="online_channel",
                    source_name=platform_lc,
                    external_sku=candidate,
                    external_color=canon.get("color") or None,
                    external_size=canon.get("size") or size_tok or None,
                    db=db,
                )
                if res.get("matched") and res.get("matched_exact", True):
                    resolved = dict(res)
                    resolved["resolved_from"] = candidate
                    break
                elif res.get("matched") and not res.get("matched_exact", True):
                    resolved = dict(res)
                    resolved["resolved_from"] = candidate
                    resolved["matched"] = False
                    resolved["unmapped_reason"] = f"Unmapped color/size for SKU '{candidate}'"
                    break

            # Fallback: if group_id matches a style in styles collection directly
            if not resolved.get("matched"):
                van = r.get("vendor article number", "").strip() if "vendor article number" in r else ""
                cands_to_check = [c for c in [van, group_id, leaf_stripped] if c]
                for cand in cands_to_check:
                    if cand in style_lookup_cache:
                        st_cand = style_lookup_cache[cand]
                    else:
                        st_cand = await _safe_find_one(getattr(db, "styles", None), {
                            "$or": [
                                {"code": {"$regex": f"^{re.escape(cand)}$", "$options": "i"}},
                                {"name": {"$regex": f"^{re.escape(cand)}$", "$options": "i"}},
                                {"article_number": {"$regex": f"^{re.escape(cand)}$", "$options": "i"}}
                            ]
                        })
                        style_lookup_cache[cand] = st_cand
                    if st_cand:
                        resolved = {
                            "matched": True,
                            "match_via": "style_code_direct",
                            "style_id": str(st_cand["_id"]),
                            "style_code": st_cand.get("code", ""),
                            "color": "",
                            "size": canon.get("size") or size_tok or "",
                        }
                        break
            resolve_cache[cache_key] = resolved

        canon.update({
            "matched":    bool(resolved.get("matched")),
            "match_via":  resolved.get("match_via"),
            "style_id":   resolved.get("style_id"),
            "style_code": resolved.get("style_code"),
            "color":      resolved.get("color") or "",
            "size":       resolved.get("size") or (canon.get("size") or size_tok),
        })
        if not canon["matched"]:
            canon["exception_reason"] = resolved.get("unmapped_reason") or resolved.get("reason") or "no style match in sku_map"

        await _classify_monthly_row(canon, platform_lc, db=db)
        canonical_rows.append(canon)

    def _count(pred) -> int:
        return sum(1 for c in canonical_rows if pred(c))

    stats = {
        "total_rows":              len(canonical_rows),
        "packed":                  _count(lambda c: c.get("was_packed")),
        "never_touched_inventory": _count(lambda c: c.get("never_touched_inventory")),
        "discrepancies":           _count(lambda c: c.get("has_dispatch_discrepancy")),
        "returned_to_stock":       _count(lambda c: c.get("was_returned_to_stock")),
        "pending":                 _count(lambda c: c.get("is_pending")),
        "net_sold":                _count(lambda c: c.get("is_net_sold")),
        "matched":                 _count(lambda c: c.get("matched")),
        "unmatched":               _count(lambda c: not c.get("matched")),
        "empty_leaf_sku":          _count(lambda c: "empty_leaf_sku" in (c.get("flags") or [])),
    }
    breakdown = {
        "rto":                  _count(lambda c: c.get("return_reason") == "rto"),
        "customer_return":      _count(lambda c: c.get("return_reason") == "customer_return"),
        "cancelled_after_pack": _count(lambda c: c.get("return_reason") == "cancelled_after_pack"),
    }
    stats["reason_breakdown"] = breakdown

    # Build monthly style grouping overview (e.g. FL_DB_016 with all sizes grouped and COGS calculated)
    style_overview = await _build_monthly_style_overview(
        canonical_rows=canonical_rows,
        raw_rows=rows,
        platform=platform_lc,
        filename=file.filename or "",
        db=db,
    )

    import_batch_id = f"MREP_{platform_lc}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    committed: Dict[str, int] = {
        "items_upserted":       0,
        "orders_upserted":      0,
        "returns_posted":       0,
        "returns_skipped":      stats.get("returned_to_stock", 0),
        "return_damaged_posted":0,
        "exceptions_queued":    0,
    }

    if not dry_run:
        exceptions: List[Dict[str, Any]] = []
        for canon in canonical_rows:
            src_row = canon.get("source_row_index")
            order_release_id = canon.get("order_release_id")
            order_id         = canon.get("order_id")

            if not canon.get("matched") or "empty_leaf_sku" in (canon.get("flags") or []):
                exceptions.append({
                    "import_batch_id":  import_batch_id,
                    "platform":         platform_lc,
                    "kind":             "monthly_report_import",
                    "source_row_index": src_row,
                    "order_id":         order_id,
                    "order_release_id": order_release_id,
                    "leaf_sku_raw":     canon.get("leaf_sku_raw"),
                    "leaf_sku":         canon.get("leaf_sku"),
                    "reason":           canon.get("exception_reason") or "unresolved",
                    "flags":            canon.get("flags"),
                    "raw_row":          canon.get("raw_row"),
                    "created_at":       now_iso(),
                    "resolved":         False,
                })
                continue

            style_id   = canon["style_id"]
            style_code = canon["style_code"]
            color      = canon["color"]
            size       = canon.get("size") or canon.get("derived_size")

            match_q: Dict[str, Any] = {"platform": platform_lc}
            if order_release_id:
                match_q["order_release_id"] = order_release_id
            elif order_id:
                match_q["order_id"] = order_id
            existing_order = await db.online_orders.find_one(match_q) if len(match_q) > 1 else None
            if existing_order is None:
                new_order = {
                    "platform":            platform_lc,
                    "order_id":            order_id,
                    "order_release_id":    order_release_id,
                    "channel":             platform_lc,
                    "order_status":        canon.get("order_status"),
                    "packed_on":           canon.get("packed_on"),
                    "delivered_on":        canon.get("delivered_on"),
                    "cancelled_on":        canon.get("cancelled_on"),
                    "rto_creation_date":   canon.get("rto_creation_date"),
                    "return_creation_date":canon.get("return_creation_date"),
                    "source":              "monthly_report_import",
                    "monthly_report_batch_id": import_batch_id,
                    "created_at":          now_iso(),
                    "updated_at":          now_iso(),
                }
                res = await db.online_orders.insert_one(new_order)
                online_order_pk = str(res.inserted_id)
                committed["orders_upserted"] += 1
            else:
                online_order_pk = str(existing_order["_id"])
                await db.online_orders.update_one(
                    {"_id": existing_order["_id"]},
                    {"$set": {
                        "order_status":         canon.get("order_status"),
                        "packed_on":            canon.get("packed_on") or existing_order.get("packed_on"),
                        "delivered_on":         canon.get("delivered_on"),
                        "cancelled_on":         canon.get("cancelled_on"),
                        "rto_creation_date":    canon.get("rto_creation_date"),
                        "return_creation_date": canon.get("return_creation_date"),
                        "monthly_report_batch_id": import_batch_id,
                        "updated_at":           now_iso(),
                    }}
                )

            item_q: Dict[str, Any] = {
                "online_order_id": ObjectId(online_order_pk),
                "style_id":        ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else style_id,
                "color":           color,
                "size":            size,
            }
            existing_item = await db.online_order_items.find_one(item_q)

            item_set = {
                "platform":               platform_lc,
                "order_id":               order_id,
                "order_release_id":       order_release_id,
                "style_id":               ObjectId(style_id) if ObjectId.is_valid(str(style_id)) else style_id,
                "style_code":             style_code,
                "color":                  color,
                "size":                   size,
                "leaf_sku":               canon.get("leaf_sku"),
                "leaf_sku_raw":           canon.get("leaf_sku_raw"),
                "was_packed":             canon.get("was_packed"),
                "was_returned_to_stock":  canon.get("was_returned_to_stock"),
                "is_pending":             canon.get("is_pending"),
                "is_net_sold":            canon.get("is_net_sold"),
                "never_touched_inventory":canon.get("never_touched_inventory"),
                "has_dispatch_discrepancy":canon.get("has_dispatch_discrepancy"),
                "discrepancy_reason":     canon.get("discrepancy_reason"),
                "return_reason":          canon.get("return_reason"),
                "order_status":           canon.get("order_status"),
                "packed_on":              canon.get("packed_on"),
                "delivered_on":           canon.get("delivered_on"),
                "cancelled_on":           canon.get("cancelled_on"),
                "rto_creation_date":      canon.get("rto_creation_date"),
                "return_creation_date":   canon.get("return_creation_date"),
                "final_amount":           canon.get("final_amount"),
                "total_mrp":              canon.get("total_mrp"),
                "discount":               canon.get("discount"),
                "seller_price":           canon.get("seller_price"),
                "monthly_report_batch_id":import_batch_id,
                "source":                 (existing_item.get("source") if existing_item else "monthly_report_import"),
                "updated_at":             now_iso(),
            }
            if existing_item:
                await db.online_order_items.update_one(
                    {"_id": existing_item["_id"]},
                    {"$set": item_set}
                )
            else:
                item_set["online_order_id"] = ObjectId(online_order_pk)
                item_set["created_at"]      = now_iso()
                await db.online_order_items.insert_one(item_set)
            committed["items_upserted"] += 1

            if canon.get("has_dispatch_discrepancy"):
                exceptions.append({
                    "import_batch_id":  import_batch_id,
                    "platform":         platform_lc,
                    "kind":             "monthly_report_dispatch_discrepancy",
                    "source_row_index": src_row,
                    "order_id":         order_id,
                    "order_release_id": order_release_id,
                    "style_id":         style_id,
                    "style_code":       style_code,
                    "color":            color,
                    "size":             size,
                    "leaf_sku":         canon.get("leaf_sku"),
                    "reason":           canon.get("discrepancy_reason") or "Dispatch discrepancy",
                    "flags":            canon.get("flags"),
                    "raw_row":          canon.get("raw_row"),
                    "created_at":       now_iso(),
                    "resolved":         False,
                })

            # Note: Inventory restocking is handled daily when physical return/RTO parcels
            # are received and inspected at warehouse gate. Monthly report is strictly for
            # sales/returns reconciliation and profit/COGS overview, so no return movements are posted.

        if exceptions:
            await db.online_order_exceptions.insert_many(exceptions)
            committed["exceptions_queued"] = len(exceptions)

        # Save / upsert the monthly style overview into online_monthly_reconciliation_overviews
        await _safe_update_one(
            getattr(db, "online_monthly_reconciliation_overviews", None),
            {"platform": platform_lc, "month": style_overview["month"]},
            {"$set": style_overview},
            upsert=True,
        )

        await _log_activity(
            "MONTHLY_REPORT_IMPORT", "online_orders",
            f"{platform_lc}: {committed['items_upserted']} items, "
            f"{len(style_overview['styles'])} styles reconciled (month {style_overview['month']}), "
            f"{committed['exceptions_queued']} exceptions "
            f"(batch {import_batch_id})",
            u.get("email", ""),
            db=db,
        )

    return {
        "platform":           platform_lc,
        "role":               "monthly_report",
        "filename":           file.filename or "",
        "header_row_1_based": 1,
        "header":             headers,
        "dry_run":            dry_run,
        "stats":              stats,
        "committed":          committed if not dry_run else None,
        "import_batch_id":    import_batch_id,
        "rows":               canonical_rows,
        "style_overview":     style_overview,
    }


@online_orders_router.post("/online-orders/settlement-import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_settlement(
    file: UploadFile = File(...),
    platform: str = Query(..., description="Platform identifier"),
    dry_run: bool = False,
    request: Request = None,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()
    platform_lc = platform.strip().lower()

    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "settlement", "active": True}
    )
    if not cfg_doc:
        raise HTTPException(400, f"No active settlement import config found for platform '{platform_lc}'")

    content = await file.read()
    sheet_loc = SheetLocator(**_sanitize_sheet_loc(cfg_doc.get("sheet_locator", {"type": "first_sheet"})))
    header_loc = HeaderLocator(**_sanitize_header_loc(cfg_doc.get("header_locator", {"type": "fixed_row", "row": 0})))
    skip_rows = int(cfg_doc.get("skip_rows_after_header", 0) or 0)

    headers, rows = _parse_tabular_bytes(
        content=content,
        filename=file.filename or "",
        sheet_locator=sheet_loc,
        header_locator=header_loc,
        skip_rows_after_header=skip_rows,
    )

    if not rows:
        raise HTTPException(400, "No data rows found in settlement file")

    col_map = cfg_doc.get("column_map") or {}
    resolved_cols = {}
    for canon_field, target_name in col_map.items():
        if target_name:
            actual = _resolve_column(target_name, headers)
            if actual:
                resolved_cols[canon_field] = actual

    from routes.sku_map import resolve_style, split_leaf_sku

    matched_count = 0
    unresolved_count = 0
    records = []

    for r in rows:
        raw_leaf = r.get(resolved_cols.get("leaf_sku", ""), "").strip() if resolved_cols.get("leaf_sku") else ""
        order_ref = r.get(resolved_cols.get("order_ref", ""), "").strip() if resolved_cols.get("order_ref") else ""
        if not raw_leaf and not order_ref:
            continue

        cleaned_leaf = strip_known_prefixes(raw_leaf, cfg_doc.get("known_sku_prefixes_to_strip", []))
        group_id, size_token, _ = split_leaf_sku(cleaned_leaf)

        result = await resolve_style(
            source_type="online_channel",
            source_name=platform_lc,
            external_sku=cleaned_leaf,
            external_color=None,
            external_size=size_token or None,
            db=db,
        )

        gross = float(r.get(resolved_cols.get("gross_amount", ""), 0.0) or 0.0) if resolved_cols.get("gross_amount") else 0.0
        comm = float(r.get(resolved_cols.get("commission", ""), 0.0) or 0.0) if resolved_cols.get("commission") else 0.0
        ship = float(r.get(resolved_cols.get("shipping_fee", ""), 0.0) or 0.0) if resolved_cols.get("shipping_fee") else 0.0
        rto = float(r.get(resolved_cols.get("rto_charge", ""), 0.0) or 0.0) if resolved_cols.get("rto_charge") else 0.0
        net = float(r.get(resolved_cols.get("net_payout", ""), 0.0) or 0.0) if resolved_cols.get("net_payout") else 0.0

        if result["matched"]:
            matched_count += 1
            records.append({
                "platform": platform_lc,
                "order_ref": order_ref,
                "leaf_sku": cleaned_leaf,
                "style_id": result["style_id"],
                "style_code": result["style_code"],
                "color": result["color"],
                "size": result["size"],
                "gross_amount": gross,
                "commission": comm,
                "shipping_fee": ship,
                "rto_charge": rto,
                "net_payout": net,
                "settlement_date": r.get(resolved_cols.get("settlement_date", ""), "") if resolved_cols.get("settlement_date") else now_iso()[:10],
                "payment_id": r.get(resolved_cols.get("payment_id", ""), "") if resolved_cols.get("payment_id") else "",
                "created_at": now_iso(),
            })
        else:
            unresolved_count += 1

    if not dry_run and len(records) == 0:
        raise HTTPException(status_code=400, detail="Nothing to commit — no rows matched.")

    if not dry_run and records:
        await db.online_settlements.insert_many(records)

    return {
        "platform": platform_lc,
        "total_rows": len(rows),
        "matched_count": matched_count,
        "unresolved_count": unresolved_count,
        "dry_run": dry_run,
    }


@online_orders_router.get("/online-orders/settlements")
async def list_settlements(
    request: Request,
    platform: Optional[str] = None,
    order_ref: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    await _get_user(request)
    db = get_db()
    q = {}
    if platform:
        q["platform"] = platform.lower()
    if order_ref:
        q["order_ref"] = {"$regex": re.escape(order_ref), "$options": "i"}
    if from_date or to_date:
        dq = {}
        if from_date: dq["$gte"] = from_date
        if to_date: dq["$lte"] = to_date + "T23:59:59"
        q["settlement_date"] = dq
    docs = await db.online_settlements.find(q).sort("settlement_date", -1).to_list(2000)
    return [stringify(d) for d in docs]


@online_orders_router.get("/online-orders/settlement-summary")
async def settlement_summary(
    request: Request,
    platform: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    await _get_user(request)
    db = get_db()
    q = {}
    if platform:
        q["platform"] = platform.lower()
    if from_date or to_date:
        dq = {}
        if from_date: dq["$gte"] = from_date
        if to_date: dq["$lte"] = to_date + "T23:59:59"
        q["settlement_date"] = dq

    docs = await db.online_settlements.find(q).to_list(10000)
    tot_gross = sum(float(d.get("gross_amount", 0) or 0) for d in docs)
    tot_comm = sum(float(d.get("commission", 0) or 0) for d in docs)
    tot_ship = sum(float(d.get("shipping_fee", 0) or 0) for d in docs)
    tot_rto = sum(float(d.get("rto_charge", 0) or 0) for d in docs)
    tot_net = sum(float(d.get("net_payout", 0) or 0) for d in docs)

    return {
        "count": len(docs),
        "total_gross": round(tot_gross, 2),
        "total_commission": round(tot_comm, 2),
        "total_shipping": round(tot_ship, 2),
        "total_rto": round(tot_rto, 2),
        "total_net_payout": round(tot_net, 2),
    }


class UpdateStyleCostPayload(BaseModel):
    platform: str
    month: str
    style_code: str
    unit_production_cost: float


class UpdateOperationalCostPayload(BaseModel):
    platform: str = "myntra"
    month: str
    allocation_pct: Optional[float] = 50.0
    rent: Optional[float] = None
    electricity: Optional[float] = None
    salaries: Optional[float] = None
    other_basic: Optional[float] = None


@online_orders_router.get("/online-orders/reconciliation-summary")
async def reconciliation_summary(
    request: Request,
    platform: Optional[str] = None,
    month: Optional[str] = None,
):
    await _get_user(request)
    db = get_db()
    platform_lc = platform.lower().strip() if platform else None

    pq = {"channel": platform_lc} if platform_lc else {}
    total_orders = await db.production_jobs.count_documents({**pq, "source_type": "online_channel"})

    sq = {"platform": platform_lc} if platform_lc else {}
    settled_orders = await db.online_settlements.count_documents(sq)

    ov_query: Dict[str, Any] = {}
    if platform_lc:
        ov_query["platform"] = platform_lc
    if month:
        ov_query["month"] = month

    overview_doc = await _safe_find_one(
        getattr(db, "online_monthly_reconciliation_overviews", None),
        ov_query,
        sort=[("month", -1), ("updated_at", -1)],
    )

    available_months: List[str] = []
    if hasattr(db, "online_monthly_reconciliation_overviews"):
        col = db.online_monthly_reconciliation_overviews
        if hasattr(col, "distinct"):
            try:
                m_filter = {"platform": platform_lc} if platform_lc else {}
                distinct_res = col.distinct("month", m_filter)
                if inspect.isawaitable(distinct_res):
                    distinct_res = await distinct_res
                available_months = sorted([str(m) for m in (distinct_res or []) if m], reverse=True)
            except Exception:
                pass

    active_month = month or (overview_doc.get("month") if overview_doc else (available_months[0] if available_months else None))

    res: Dict[str, Any] = {
        "platform": platform or "all",
        "month": active_month,
        "available_months": available_months,
        "total_orders": total_orders,
        "settled_orders": settled_orders,
        "unsettled_orders": max(0, total_orders - settled_orders),
    }

    if overview_doc and isinstance(overview_doc, dict):
        tot_rows = overview_doc.get("total_orders", 0)
        packed = overview_doc.get("total_packed", 0)
        ret_cust = overview_doc.get("total_returned", 0)
        rto = overview_doc.get("total_rto", 0)
        cxl = overview_doc.get("total_cancelled", 0)
        pending = overview_doc.get("total_pending", 0)
        net_sold = overview_doc.get("total_net_sold", 0)

        res.update({
            "total_rows":              tot_rows,
            "packed":                  packed,
            "returned_to_stock":       ret_cust + rto,
            "pending":                 pending,
            "net_sold":                net_sold,
            "never_touched_inventory": cxl,
            "discrepancies":           0,
            "reason_breakdown": {
                "rto":                  rto,
                "customer_return":      ret_cust,
                "cancelled_after_pack": cxl,
            },
            "overview":                stringify(overview_doc),
        })
    else:
        res.update({
            "total_rows":              0,
            "packed":                  0,
            "returned_to_stock":       0,
            "pending":                 0,
            "net_sold":                0,
            "never_touched_inventory": 0,
            "discrepancies":           0,
            "reason_breakdown":        {"rto": 0, "customer_return": 0, "cancelled_after_pack": 0},
            "overview":                None,
        })

    return res


@online_orders_router.put("/online-orders/monthly-reconciliation-overview/cost")
async def update_monthly_style_cost(
    payload: UpdateStyleCostPayload,
    request: Request,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()

    platform_lc = payload.platform.lower().strip()
    month = payload.month.strip()
    style_code = payload.style_code.strip()
    new_unit_cost = max(0.0, float(payload.unit_production_cost))

    doc = await _safe_find_one(getattr(db, "online_monthly_reconciliation_overviews", None), {
        "platform": platform_lc,
        "month": month,
    })
    if not doc or not isinstance(doc, dict):
        raise HTTPException(404, f"Overview for {platform_lc} / {month} not found")

    styles = doc.get("styles", [])
    found = False
    tot_sold_rev = 0.0
    tot_prod_cost = 0.0

    for s in styles:
        if s.get("style_code") == style_code:
            s["unit_production_cost"] = round(new_unit_cost, 2)
            cogs = round(s.get("net_sold_qty", 0) * new_unit_cost, 2)
            s["total_production_cost"] = cogs
            gp = round(float(s.get("net_sold_seller_price", 0) or 0) - cogs, 2)
            s["gross_profit"] = gp
            sold_sp = float(s.get("net_sold_seller_price", 0) or 0)
            s["margin_pct"] = round((gp / sold_sp * 100), 1) if sold_sp > 0 else 0.0
            found = True
        tot_sold_rev += float(s.get("net_sold_seller_price", 0) or 0)
        tot_prod_cost += float(s.get("total_production_cost", 0) or 0)

    if not found:
        raise HTTPException(404, f"Style '{style_code}' not found in overview")

    overall_gp = round(tot_sold_rev - tot_prod_cost, 2)
    overall_margin = round((overall_gp / tot_sold_rev * 100), 1) if tot_sold_rev > 0 else 0.0

    update_data = {
        "styles": styles,
        "total_cost_of_production": round(tot_prod_cost, 2),
        "estimated_gross_profit": overall_gp,
        "overall_margin_pct": overall_margin,
        "updated_at": now_iso(),
    }

    sku_bifurcation = doc.get("sku_bifurcation", [])
    if sku_bifurcation:
        for sk in sku_bifurcation:
            if str(sk.get("style_root") or "").strip().lower() == style_code.lower():
                sk["unit_production_cost"] = round(new_unit_cost, 2)
                sk_cogs = round(float(sk.get("net_units") or 0) * new_unit_cost, 2)
                sk["total_production_cost"] = sk_cogs
                sk["gross_profit"] = round(float(sk.get("net_sales") or 0) - sk_cogs, 2)
                sk["contribution_after_platform"] = round(float(sk.get("platform_earnings") or 0) - sk_cogs, 2)
                net_s = float(sk.get("net_sales") or 0)
                sk["margin_pct"] = round((sk["gross_profit"] / net_s * 100), 1) if net_s > 0 else 0.0
        update_data["sku_bifurcation"] = sku_bifurcation

    op_expenses = doc.get("operational_expenses") or {}
    allocated_op = float(op_expenses.get("allocated_operational_cost") or doc.get("allocated_operational_cost") or 0.0)
    total_plat_earnings = float(doc.get("platform_earnings") or 0.0)
    if not total_plat_earnings and doc.get("pnl_summary"):
        total_plat_earnings = float(doc["pnl_summary"].get("earnings_on_platform") or 0.0)
    actual_net_profit = round(total_plat_earnings - tot_prod_cost - allocated_op, 2)
    actual_net_margin = round((actual_net_profit / tot_sold_rev * 100), 2) if tot_sold_rev > 0 else 0.0

    update_data["actual_net_profit"] = actual_net_profit
    update_data["actual_net_margin_pct"] = actual_net_margin

    await _safe_update_one(
        getattr(db, "online_monthly_reconciliation_overviews", None),
        {"_id": doc["_id"]},
        {"$set": update_data},
    )
    doc.update(update_data)
    return stringify(doc)


@online_orders_router.put("/online-orders/monthly-reconciliation-overview/operational-cost")
async def update_monthly_operational_cost(
    payload: UpdateOperationalCostPayload,
    request: Request,
):
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db()

    platform_lc = payload.platform.lower().strip()
    month = payload.month.strip()

    doc = await _safe_find_one(getattr(db, "online_monthly_reconciliation_overviews", None), {
        "platform": platform_lc,
        "month": month,
    })
    if not doc or not isinstance(doc, dict):
        raise HTTPException(404, f"Overview for {platform_lc} / {month} not found")

    cur_op = doc.get("operational_expenses") or {}
    rent = float(payload.rent if payload.rent is not None else cur_op.get("rent", 85000.0))
    electricity = float(payload.electricity if payload.electricity is not None else cur_op.get("electricity", 12500.0))
    salaries = float(payload.salaries if payload.salaries is not None else cur_op.get("salaries", 30000.0))
    other_basic = float(payload.other_basic if payload.other_basic is not None else cur_op.get("other_basic", 10000.0))
    alloc_pct = float(payload.allocation_pct if payload.allocation_pct is not None else cur_op.get("allocation_pct", 50.0))

    tot_op = round(rent + electricity + salaries + other_basic, 2)
    allocated_op = round(tot_op * (alloc_pct / 100.0), 2)

    new_op = {
        "allocation_pct": alloc_pct,
        "rent": rent,
        "electricity": electricity,
        "salaries": salaries,
        "other_basic": other_basic,
        "total_monthly_operational_cost": tot_op,
        "allocated_operational_cost": allocated_op,
    }

    tot_prod_cost = float(doc.get("total_cost_of_production") or 0.0)
    net_sold_rev = float(doc.get("net_sold_revenue") or 0.0)
    pnl_sum = doc.get("pnl_summary") or {}
    tot_plat_earn = float(doc.get("platform_earnings") or pnl_sum.get("earnings_on_platform") or 0.0)

    actual_net_profit = round(tot_plat_earn - tot_prod_cost - allocated_op, 2)
    actual_net_margin = round((actual_net_profit / net_sold_rev * 100), 2) if net_sold_rev > 0 else 0.0

    update_data = {
        "operational_expenses": new_op,
        "allocated_operational_cost": allocated_op,
        "actual_net_profit": actual_net_profit,
        "actual_net_margin_pct": actual_net_margin,
        "updated_at": now_iso(),
    }
    await _safe_update_one(
        getattr(db, "online_monthly_reconciliation_overviews", None),
        {"_id": doc["_id"]},
        {"$set": update_data},
    )
    doc.update(update_data)
    return stringify(doc)


async def _parse_and_resolve_order_row(
    raw_row: dict,
    cfg: dict,
    platform: str,
    picklist_batch_id: Optional[str] = None,
    db=None,
) -> dict:
    if db is None:
        db = get_db()
    col_map = cfg.get("column_map") or {}
    leaf_col = col_map.get("leaf_sku") or "leaf_sku"
    raw_leaf = (raw_row.get(leaf_col) or "").strip()

    prefixes = cfg.get("known_sku_prefixes_to_strip", [])
    replacements = cfg.get("known_sku_prefix_replacements", {})
    cleaned_leaf = raw_leaf
    for wrong, right in (replacements or {}).items():
        if cleaned_leaf.startswith(wrong):
            cleaned_leaf = right + cleaned_leaf[len(wrong):]
    cleaned_leaf = strip_known_prefixes(cleaned_leaf, prefixes)

    from routes.sku_map import resolve_style, split_leaf_sku
    group_id, size_token, _ = split_leaf_sku(cleaned_leaf)

    size_col = col_map.get("size")
    color_col = col_map.get("color")
    price_col = col_map.get("selling_price")
    order_id_col = col_map.get("order_id")

    size_val = (raw_row.get(size_col) if size_col else "") or size_token or ""
    color_val = (raw_row.get(color_col) if color_col else "") or ""
    order_id = (raw_row.get(order_id_col) if order_id_col else "") or picklist_batch_id or ""

    price_str = (raw_row.get(price_col) if price_col else "0") or "0"
    try:
        selling_price = float(re.sub(r"[^\d.]", "", str(price_str)) or 0.0)
    except Exception:
        selling_price = 0.0

    import server
    resolve_style_fn = getattr(server, "resolve_style", resolve_style)
    res = await resolve_style_fn(
        source_type="online_channel",
        source_name=platform,
        external_sku=cleaned_leaf,
        external_color=color_val or None,
        external_size=size_val or None,
        db=db,
    )

    gst_warning = None
    if res["matched"] and res.get("style_id"):
        try:
            style = await db.styles.find_one({"_id": ObjectId(res["style_id"])})
        except Exception:
            style = await db.styles.find_one({"_id": res["style_id"]})
        if style:
            current_gst = float(style.get("gst_pct", 5.0) or 5.0)
            suggested_gst = 18.0 if selling_price > 2500.0 else 5.0
            if current_gst != suggested_gst:
                gst_warning = f"Selling price ₹{selling_price} suggests {suggested_gst:.0f}% GST, but style is currently set to {current_gst:.0f}%"

    matched = bool(res.get("matched")) and (res.get("matched_exact") is not False) and (not res.get("unmapped_size")) and (not res.get("unmapped_color"))

    exc_reason = None
    if not matched:
        if res.get("unmapped_size") or res.get("size_matched_exact") is False:
            exc_reason = f"Unmapped color/size: size '{size_val}' not in size_map for SKU '{cleaned_leaf}'"
        elif res.get("unmapped_color") or res.get("color_matched_exact") is False:
            exc_reason = f"Unmapped color/size: color '{color_val}' not in color_map for SKU '{cleaned_leaf}'"
        else:
            exc_reason = f"SKU '{cleaned_leaf}' not found in Style Master or SKU Mappings"

    return {
        "raw_leaf_sku": raw_leaf,
        "leaf_sku": cleaned_leaf,
        "order_id": order_id,
        "color": res.get("color") or color_val,
        "size": res.get("size") or size_val,
        "selling_price": selling_price,
        "matched": matched,
        "matched_exact": res.get("matched_exact", res["matched"]),
        "style_id": res.get("style_id"),
        "style_code": res.get("style_code"),
        "match_via": res.get("match_via"),
        "gst_mismatch_warning": gst_warning,
        "exception_reason": exc_reason,
    }


# Backwards compatibility aliases
_seed_order_import_configs = _seed_order_import_format_configs
import_online_orders_configured = import_configured_online_orders
import_dispatch_configured = import_dispatch_orders
import_settlement_report = import_settlement
