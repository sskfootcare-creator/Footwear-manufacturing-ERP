"""SSK Footcare Management System — FastAPI backend."""
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")



import os
import re
import logging
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional, Literal, Dict, Any, Tuple

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, field_validator
from pydantic_core import PydanticCustomError
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

import jwt
from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, validate_password,
    set_auth_cookies, clear_auth_cookies,
    get_current_user_factory, require_roles, seed_admin,
    JWT_ALGORITHM, get_jwt_secret,
)
from routes.auth import (
    auth_router,
    # rate-limit state + helpers re-exported for backward-compat with tests
    _login_failures,
    redis_client,
    check_rate_limit,
    record_login_failure,
    clear_login_failures,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    # auth route functions — imported so tests can call them directly
    login,
    logout,
    refresh_token_route,
    me,
    forgot_password,
    reset_password,
    list_users,
    create_user,
    update_user,
    delete_user,
    # password-reset helpers
    _hash_reset_token,
    _reset_link_base,
    _send_reset_email,
    PASSWORD_RESET_TTL_HOURS,
    ForgotPasswordInput,
    ResetPasswordInput,
)
from collections import defaultdict
from po_extractor import extract_po_from_pdf, extract_po_from_xlsx
from pdf_docs import generate_dispatch_challan_pdf, build_invoice
from packing_list import build_default_packing_list, build_from_template, build_dispatch_packing_list, build_carton_list_xlsx, build_packing_list_pdf, VENDOR, DEFAULT_SIZES
STANDARD_SIZES = DEFAULT_SIZES
from pdf_procurement import build_material_requirement
from pdf_card import build_production_card, build_production_card_dual_a4
from pdf_carton_label import build_carton_labels
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from io import BytesIO
import uuid
import boto3
from models import *
from rate_limiter import upload_rate_limiter, pdf_rate_limiter, bulk_import_rate_limiter

# ---------- DB & app ----------
from routes.plm import plm_router, DEFAULT_PLM_FOLDERS
from routes.settings import settings_router
from routes.workers import workers_router
from routes.vendors import vendors_router
from routes.notifications import notifications_router
from routes.components import (
    components_router,
    _serialize_component,
    _build_size_matrix_pivot,
    _apply_component_movement,
    _record_component_movement,
)
from routes.expenses import expenses_router
from routes.sku_map import (
    sku_map_router,
    resolve_style,
    split_leaf_sku,
    _norm_key,
    _norm_marketplace,
    _update_unmatched_jobs_for_sku_mapping,
    _seed_parser_templates,
    _resolve_marketplace_sku,
    _log_unresolved_sku,
    _parse_sku,
    _get_parser_template,
    SUPPORTED_MARKETPLACES,
    DEFAULT_PARSER_PATTERNS,
)
from routes.online_reconciliation import (
    online_reconciliation_router,
    _compute_online_profitability,
)
from routes.materials import (
    materials_router,
    _sync_material_to_component,
    _get_material_balance,
    _auto_consume_inventory,
    _compute_material_requirement,
    _calculate_material_weighted_avg,
    _compute_material_inventory_summary,
    list_inventory,
    create_movement,
    list_movements,
)
from routes.inventory import (
    inventory_router,
    _seed_fg_inventory_for_lifecycle,
    _get_or_create_fg_row,
    _apply_movement,
    _resolve_style_by_code,
    _MOVEMENT_DELTAS,
    STANDARD_SIZES,
)
from routes.invoice_packing import (
    invoice_packing_router,
    list_invoices,
    get_invoice,
    next_invoice_no,
    _get_max_invoice_seq,
    _extract_credit_days,
    _due_iso,
    _compute_invoice_totals,
    _invoice_iso_date,
    _decorate_invoice,
    _aggregate_payments_for_invoices,
    _aggregate_grn_adjustments,
    _generate_invoice_payload,
    _enrich_cartons_with_mapped_sku,
    _build_packing_payload,
    _packing_options_from_payload,
    _auto_pick_template,
    _generate_packing_bytes,
    _flag_jobs,
    CartonIn,
    EanCodeSimple,
    CartonRowSimple,
    QcPackConfirmIn,
    EanCodeIn,
)
from routes.wms import (
    wms_router,
    _seed_warehouse_locations,
    _allocate_to_locations,
    _deduct_from_locations,
    _deduct_from_specific_location,
    _sync_warehouse_locations,
    _find_style_home_cell,
    _pick_new_cell_for_style,
    _next_picklist_no,
    _generate_picklist_for_order,
    LocationBlockIn,
    ProduceCellIn,
    ProductionCardIn,
    PicklistItemIn,
    PicklistIn,
    PickItemIn,
    PicklistPatchIn,
    WAREHOUSE_ROWS,
    RACKS_PER_ROW,
    RACKS,
    CELLS_PER_RACK,
    CAPACITY,
)
from routes.pos import (
    pos_router,
    validate_po_styles,
    _attach_po_profitability,
    _attach_po_status,
    _sync_po_sku_mappings,
    _flag_jobs,
    _archive_if_complete,
    _build_client_ledger,
    next_grn_no,
    next_payment_no,
    compute_po_profitability,
    compute_style_costing_async,
    list_pos,
    get_po,
    create_po,
    update_po,
    delete_po,
    create_grn,
    delete_grn,
    list_grns,
    get_grn,
    create_payment,
    list_payments,
    delete_payment,
    list_clients,
    client_ledger,
    report_payroll,
    list_jobs,
    update_job,
    list_defects,
    create_defect,
    update_defect,
    delete_defect,
    get_b2b_profitability,
)
from routes.online_orders import (
    online_orders_router,
    _seed_order_import_format_configs,
    ORDER_CANONICAL_FIELDS,
    DISPATCH_CANONICAL_FIELDS,
    MONTHLY_REPORT_CANONICAL_FIELDS,
    SETTLEMENT_CANONICAL_FIELDS,
    OrderImportFormatConfigIn,
    OrderImportFormatConfigUpdate,
    OnlineOrderImportResult,
    list_order_import_format_configs,
    get_order_import_format_config,
    create_order_import_format_config,
    update_order_import_format_config,
    delete_order_import_format_config,
    import_configured_online_orders,
    import_dispatch_orders,
    import_monthly_report,
    import_settlement,
    list_settlements,
    settlement_summary,
    reconciliation_summary,
    import_online_orders,
    list_online_orders,
    _parse_and_resolve_order_row,
    import_online_orders_configured,
)
from routes.styles import (
    styles_router,
    suggest_gst_pct,
    get_gst_config,
    compute_style_costing,
    compute_style_costing_from_jobs,
    compute_style_costing_async,
    compute_po_profitability,
    _default_lifecycle,
    _get_or_create_lifecycle,
    _generate_back_track_number,
    _validate_online_status_transition,
    _seed_color_master,
    resolve_color_code,
    _next_style_code,
    build_catalogue_sku,
    _seed_listing_format_configs,
    list_styles_summary,
    list_styles,
    get_styles_template,
    bulk_upload_preview,
    bulk_upload_styles,
    get_style,
    create_style,
    update_style,
    delete_style,
    get_style_lifecycle,
    add_style_to_online_pipeline,
    remove_style_from_online_pipeline,
    list_styles_not_in_pipeline,
    upsert_style_lifecycle,
    patch_style_online_status,
    list_online_styles,
    get_style_catalogue_codes,
    list_color_master,
    create_color,
    update_color,
    list_listing_format_configs,
    get_listing_format_config,
    create_listing_format_config,
    update_listing_format_config,
    get_canonical_fields,
    catalogue_export,
    catalogue_export_preview,
    costing_preview,
    FOOTWEAR_GST_CONFIG,
    DEFAULT_COLOR_MASTER,
    STYLE_CODE_PREFIX,
    STYLE_CODE_PAD,
    STYLE_CODE_RE,
    CANONICAL_FIELDS,
    EXPORT_SOURCE_TYPES,
    DEFAULT_LISTING_FORMAT_CONFIGS,
    ExportColumn,
    ExportTemplate,
    ListingFormatConfigIn,
    ListingFormatConfigUpdate,
    CatalogueExportRequest,
)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="SSK Footcare ERP")

# Configure CORS dynamically to allow local development, production domains, Vercel deployments, and custom env vars
_frontend_url_env = os.getenv("FRONTEND_URL", "").strip()
_cors_origins_env = os.getenv("CORS_ORIGINS", "").strip()
_raw_origins = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://localhost:5173",
    "https://ssk-footcare-manufacturing-erp.vercel.app",
]
if _frontend_url_env:
    _raw_origins.extend([o.strip() for o in _frontend_url_env.split(",") if o.strip()])
if _cors_origins_env:
    _raw_origins.extend([o.strip() for o in _cors_origins_env.split(",") if o.strip()])

_default_cors_regex = r"^https:\/\/(?:[a-zA-Z0-9_-]+\.)*(?:ssk-footcare-manufacturing-erp|footwear-manufacturing(?:-[a-zA-Z0-9_-]+)?-ssk-footcare)\.vercel\.app$"
_cors_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip() or _default_cors_regex

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(_raw_origins)),
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

api = APIRouter(prefix="/api")

# ---------- Object Storage / Local Uploads ----------
os.makedirs("uploads", exist_ok=True)
# Mounted BOTH paths so:
#   • /api/uploads/... — reachable through the K8s ingress (which sends /api → :8001)
#   • /uploads/...     — kept for local dev / direct-hit and for the resolver helper
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="api_uploads")
app.mount("/uploads",     StaticFiles(directory="uploads"), name="uploads")

S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "")
if S3_BUCKET:
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        endpoint_url=S3_ENDPOINT if S3_ENDPOINT else None,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    )
else:
    s3_client = None

@api.post("/upload/image", dependencies=[Depends(upload_rate_limiter)])
async def upload_image(file: UploadFile = File(...), request: Request = None):
    u = await get_current_user(request)
    require_roles("admin", "manager")(u)

    ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if ext not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
        raise HTTPException(400, "Invalid image format")

    # ── Read up to cap + 1 byte to enforce bounded memory allocation
    MAX_UPLOAD_BYTES = 8 * 1024 * 1024   # 8 MB — server-side limit
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            "Image too large. Max allowed is 8 MB."
        )


    # ── Verify it's really an image (spoofed extension → PIL will raise)
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        img = Image.open(BytesIO(content))
        img.verify()   # header check; must reopen for real decode
        img = Image.open(BytesIO(content))
    except (UnidentifiedImageError, Exception) as e:
        raise HTTPException(400, f"File is not a valid image: {e}")

    # ── Auto-orient by EXIF (phone photos often carry rotation flag)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass   # non-fatal if EXIF missing / corrupt

    # ── Convert to RGB (JPEG can't hold alpha) — flatten PNGs / RGBA over white
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1] if rgba.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    orig_w, orig_h = img.size

    def _thumb(source_img, max_dim: int):
        """Return a copy of source_img scaled so that max(w,h) == max_dim.
        Never upscales — if the source is already smaller, returns a copy as-is."""
        w, h = source_img.size
        if max(w, h) <= max_dim:
            return source_img.copy()
        # Image.thumbnail scales in-place preserving aspect ratio
        c = source_img.copy()
        c.thumbnail((max_dim, max_dim), Image.LANCZOS)
        return c

    variants = [
        ("original.jpg",  _thumb(img, 1600), 85),
        ("display.jpg",   _thumb(img, 600),  82),
        ("thumb.jpg",     _thumb(img, 150),  80),
    ]

    # Encode all three to JPEG (strips EXIF/metadata by default because we
    # don't pass an `exif=` parameter). optimize=True shaves a few % off.
    encoded: Dict[str, bytes] = {}
    for name, variant_img, quality in variants:
        buf = BytesIO()
        variant_img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        encoded[name] = buf.getvalue()

    key = uuid.uuid4().hex

    if s3_client:
        for name, data in encoded.items():
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=f"images/{key}/{name}",
                Body=data,
                ContentType="image/jpeg",
            )

        def _s3_url(name: str) -> str:
            if S3_ENDPOINT:
                return f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/images/{key}/{name}"
            return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/images/{key}/{name}"

        return {
            "url":           _s3_url("original.jpg"),   # kept for back-compat
            "original_url":  _s3_url("original.jpg"),
            "display_url":   _s3_url("display.jpg"),
            "thumbnail_url": _s3_url("thumb.jpg"),
            "width":         orig_w,
            "height":        orig_h,
        }

    # ── Local storage: images/{uuid}/original.jpg etc.
    folder = os.path.join("uploads", "images", key)
    os.makedirs(folder, exist_ok=True)
    for name, data in encoded.items():
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)

    # Persist RELATIVE URLs (no scheme, no host) so the same upload keeps
    # working when the preview hostname rotates — the browser resolves them
    # against whatever origin it's currently viewing the app under. This
    # was the root cause of the "image never appears" bug filed earlier.
    prefix = f"/api/uploads/images/{key}"
    return {
        "url":           f"{prefix}/original.jpg",   # kept for back-compat
        "original_url":  f"{prefix}/original.jpg",
        "display_url":   f"{prefix}/display.jpg",
        "thumbnail_url": f"{prefix}/thumb.jpg",
        "width":         orig_w,
        "height":        orig_h,
    }


def resolve_local_upload_path(url: str) -> Optional[str]:
    """If `url` is a URL previously returned by /api/upload/image AND points
    to this server's local `/uploads/...` tree, return the filesystem path.
    Otherwise (S3 URL, external URL, garbage, empty) return None.

    Used by PDF generators to read local images directly instead of making
    an HTTP round-trip back to themselves (which deadlocks under a single-
    worker uvicorn and doubles latency even when it doesn't).
    """
    if not url or not isinstance(url, str):
        return None
    # Accept BOTH the ingress-friendly "/api/uploads/..." (post-Iteration-21)
    # AND the legacy "/uploads/..." form (older uploads before the ingress
    # fix) — try the newer marker first because it's a longer substring.
    for marker in ("/api/uploads/", "/uploads/"):
        idx = url.find(marker)
        if idx >= 0:
            rel = url[idx + len(marker):].split("?", 1)[0].split("#", 1)[0]
            break
    else:
        return None
    if not rel:
        return None
    # Prevent path-traversal — reject any "../" segment or absolute path
    if ".." in rel.split("/") or rel.startswith("/"):
        return None
    fs_path = os.path.join("uploads", rel)
    return fs_path if os.path.isfile(fs_path) else None


def normalize_image_url(raw: str) -> str:
    """Rewrite common share-link formats (Dropbox / OneDrive / Google Drive)
    to direct-download URLs that a browser <img> tag or PDF renderer can pull
    without an HTML redirect.

    Frontend does the same transform on paste; we mirror it server-side so
    Excel bulk imports (which never touch the paste-handler) work too.
    Returns the input unchanged if no rule matches.
    """
    import base64 as _b64
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    if not raw or not isinstance(raw, str):
        return raw
    val = raw.strip()
    if not val:
        return val
    try:
        parts = urlsplit(val)
    except Exception:
        return val
    host = (parts.hostname or "").lower()

    # ---- DROPBOX ----------------------------------------------------------
    if host.endswith("dropbox.com") and host != "dl.dropboxusercontent.com":
        qs = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "dl"]
        return urlunsplit((parts.scheme, "dl.dropboxusercontent.com", parts.path, urlencode(qs), ""))

    # ---- ONEDRIVE / SHAREPOINT --------------------------------------------
    if "api.onedrive.com/v1.0/shares/u!" in val:
        import re as _re, base64 as _b64
        m = _re.search(r"/shares/u!([^/]+)", val)
        if m:
            b64_str = m.group(1)
            padding = "=" * (-len(b64_str) % 4)
            try:
                decoded = _b64.b64decode(b64_str.replace("_", "/").replace("-", "+") + padding).decode("utf-8")
                if decoded.startswith("http"):
                    val = decoded
                    parts = urlsplit(val)
                    host = (parts.hostname or "").lower()
            except Exception:
                pass

    if host == "1drv.ms" or host.endswith("onedrive.live.com") or host.endswith("sharepoint.com"):
        if "onedrive.live.com" in host:
            if "/embed" in parts.path:
                return urlunsplit((parts.scheme, parts.netloc, parts.path.replace("/embed", "/download"), parts.query, ""))
            qs_dict = dict(parse_qsl(parts.query))
            if "resid" in qs_dict:
                return f"https://onedrive.live.com/download?{parts.query}"
        if host.endswith("sharepoint.com"):
            qs_dict = dict(parse_qsl(parts.query))
            if "download" not in qs_dict:
                qs_dict["download"] = "1"
                return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(qs_dict), ""))
        return val

    # ---- GOOGLE DRIVE -----------------------------------------------------
    if host.endswith("drive.google.com"):
        import re as _re
        m = _re.search(r"/file/d/([^/]+)", parts.path or "")
        gid = m.group(1) if m else dict(parse_qsl(parts.query)).get("id")
        if gid:
            return f"https://drive.google.com/uc?export=view&id={gid}"

    return val


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ssk")

# ---------- AUTH + LOGIN RATE LIMITING ----------
# Rate-limit state and all auth/user endpoints have been extracted to
# routes/auth.py and are imported at the top of this file.
# The names below are re-exported from routes.auth for backward-compat:
#   _login_failures, redis_client, check_rate_limit, record_login_failure,
#   clear_login_failures, login, logout, refresh_token_route, me,
#   forgot_password, reset_password, list_users, create_user, update_user,
#   delete_user, ForgotPasswordInput, ResetPasswordInput


# ---------- Keep Awake Job ----------
async def keep_awake_job():
    interval = 14 * 60
    while True:
        await asyncio.sleep(interval)
        api_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{api_url}/docs")
                log.info(f"Self-ping status: {res.status_code}")
        except Exception as e:
            log.error(f"Error during self-ping: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(keep_awake_job())

# ---------- Helpers ----------
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
    # Recursively stringify any ObjectId values
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, dict):
            doc[key] = stringify(value)
        elif isinstance(value, list):
            doc[key] = [stringify(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in value]
    return doc


async def log_activity(action: str, category: str, details: str, email: str):
    try:
        await db.audit_logs.insert_one({
            "action": action,
            "category": category,
            "details": details,
            "by": email,
            "created_at": now_iso()
        })
    except Exception as e:
        log.warning(f"Failed to write audit log: {e}")


# ---------- System-generated style codes + catalogue SKU builder ----------
# Every NEW style gets an immutable, system-generated code of the form SSK_XXXXX
# via an atomic counter increment on the `counters` collection. This code becomes
# the naming convention used everywhere, including as the base for catalogue SKUs
# handed to marketplaces (Myntra, Ajio, Flipkart, Nykaa, Website).
# (STYLE_CODE_PREFIX, _next_style_code, build_catalogue_sku, DEFAULT_COLOR_MASTER,
#  _seed_color_master, resolve_color_code imported from routes.styles)


# ---------- Pydantic models ----------
Role = Literal["admin", "manager", "production", "sales", "operator"]
# Pydantic models extracted to backend/models package.
# (All models are imported via 'from models import *' at top of file)


# ----- Marketplace SKU Resolver -----
Marketplace = Literal["myntra", "ajio", "flipkart", "nykaa", "amazon", "website", "unicommerce"]


class ParserTemplateIn(BaseModel):
    marketplace: Marketplace
    template:    str  # human-readable description, e.g. "STYLE-COLOR-SIZE"
    pattern:     str  # regex with named groups (?P<style>...)(?P<color>...)(?P<size>...)
    separator:   Optional[str] = None
    active:      bool = True
    example:     Optional[str] = None


class StyleColorMappingIn(BaseModel):
    marketplace:            Marketplace
    marketplace_style_code: str
    marketplace_color_code: str
    erp_style_code:         str
    erp_color_code:         str
    active:                 bool = True


class SkuResolveIn(BaseModel):
    marketplace: Marketplace
    sku:         str


class UnresolvedMapIn(BaseModel):
    queue_id:               Optional[str] = None
    marketplace:            Marketplace
    marketplace_style_code: str
    marketplace_color_code: str
    erp_style_code:         str
    erp_color_code:         str


# Sensible factory defaults (in hours)
DEFAULT_STAGE_HOURS = {
    "procurement": 24, "cutting": 24, "folding": 8, "attachment": 8,
    "stitching": 48, "lasting": 24, "sole_pasting": 12, "finishing": 12,
    "qc_pack": 12, "dispatched": 0,
}


# ---------- Dependencies ----------
get_current_user = None  # set after startup


async def _get_stage_durations() -> Dict[str, float]:
    doc = await db.settings.find_one({"_id": "stage_durations"})
    out = dict(DEFAULT_STAGE_HOURS)
    if doc and isinstance(doc.get("hours"), dict):
        out.update({k: float(v) for k, v in doc["hours"].items() if isinstance(v, (int, float))})
    return out


def _compute_deadline(entered_iso: str, hours: float) -> str:
    try:
        s = entered_iso.replace("Z", "+00:00") if entered_iso.endswith("Z") else entered_iso
        t = datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except Exception:
        t = datetime.now(timezone.utc)
    return (t + timedelta(hours=float(hours or 0))).isoformat()


def _overdue_hours(deadline_iso: str | None) -> float:
    if not deadline_iso:
        return 0.0
    try:
        s = deadline_iso.replace("Z", "+00:00") if deadline_iso.endswith("Z") else deadline_iso
        dl = datetime.fromisoformat(s)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        diff = (datetime.now(timezone.utc) - dl).total_seconds() / 3600
        return round(diff, 1)
    except Exception:
        return 0.0



# ---------- AUTH ----------
# (login, logout, refresh, me, forgot-password, reset-password, users
#  extracted to routes/auth.py and mounted via auth_router)

# ---------- STYLES ----------
# (All style master, BOM, costing, lifecycle, color master, and catalogue export
#  endpoints extracted to routes/styles.py and mounted via styles_router)


# In-memory dashboard stats cache
_dashboard_stats_cache = {"data": None, "expires_at": 0.0}
DASHBOARD_STATS_CACHE_TTL = 300  # 5 minutes


def invalidate_dashboard_stats_cache():
    """Invalidate in-memory dashboard stats cache."""
    _dashboard_stats_cache["data"] = None
    _dashboard_stats_cache["expires_at"] = 0.0


async def _compute_dashboard_stats_live() -> dict:
    total_pos = await db.pos.count_documents({})
    pending_pos = await db.pos.count_documents({"status": "pending"})
    
    jobs = await db.production_jobs.find({}).to_list(10000)
    
    # B2B vs Online WIP/dispatched
    b2b_jobs = [j for j in jobs if j.get("source_type") != "online_channel"]
    online_jobs = [j for j in jobs if j.get("source_type") == "online_channel"]
    
    b2b_wip = sum(j.get("quantity", 0) for j in b2b_jobs if j.get("stage") != "dispatched")
    b2b_dispatched = sum(j.get("quantity", 0) for j in b2b_jobs if j.get("stage") == "dispatched")
    
    online_wip = sum(j.get("quantity", 0) for j in online_jobs if j.get("stage") != "dispatched")
    online_dispatched = sum(j.get("quantity", 0) for j in online_jobs if j.get("stage") == "dispatched")
    
    pairs_in_wip = b2b_wip + online_wip
    dispatched = b2b_dispatched + online_dispatched
    
    # Stage counts
    stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    b2b_stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    online_stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    
    for j in jobs:
        st = j.get("stage")
        qty = j.get("quantity", 0)
        if st in stage_counts:
            stage_counts[st] += qty
        else:
            stage_counts[st] = stage_counts.get(st, 0) + qty
        if j.get("source_type") == "online_channel":
            if st in online_stage_counts:
                online_stage_counts[st] += qty
            else:
                online_stage_counts[st] = online_stage_counts.get(st, 0) + qty
        else:
            if st in b2b_stage_counts:
                b2b_stage_counts[st] += qty
            else:
                b2b_stage_counts[st] = b2b_stage_counts.get(st, 0) + qty
            
    # Revenue split
    b2b_revenue = 0.0
    pos = await db.pos.find({}).to_list(2000)
    for p in pos:
        b2b_revenue += p.get("grand_total", 0) or 0
        
    online_revenue = sum(j.get("amount", 0.0) or 0.0 for j in online_jobs)
    
    recent_pos = [stringify(p) for p in pos[-5:][::-1]]
    recent_online = [stringify(j) for j in online_jobs[-5:][::-1]]
    
    return {
        "total_pos": total_pos,
        "pending_pos": pending_pos,
        "pairs_in_wip": pairs_in_wip,
        "dispatched": dispatched,
        "stage_counts": stage_counts,
        "revenue": round(b2b_revenue + online_revenue, 2),
        "materials_count": await db.materials.count_documents({}),
        "styles_count": await db.styles.count_documents({}),
        
        # Detailed split for Management View
        "b2b": {
            "revenue": round(b2b_revenue, 2),
            "wip": b2b_wip,
            "dispatched": b2b_dispatched,
            "stage_counts": b2b_stage_counts,
            "recent_pos": recent_pos,
            "total_pos": total_pos,
            "pending_pos": pending_pos,
        },
        "online": {
            "revenue": round(online_revenue, 2),
            "wip": online_wip,
            "dispatched": online_dispatched,
            "stage_counts": online_stage_counts,
            "recent_orders": recent_online,
            "total_orders": len(online_jobs),
            "total_qty": sum(j.get("quantity", 0) for j in online_jobs),
        }
    }


# ---------- DASHBOARD ----------
@api.get("/dashboard/stats")
async def dashboard_stats(request: Request, force_refresh: bool = False):
    await get_current_user(request)
    now_ts = datetime.now(timezone.utc).timestamp()

    # 1. Check in-memory cache
    if not force_refresh and _dashboard_stats_cache["data"] is not None and now_ts < _dashboard_stats_cache["expires_at"]:
        return _dashboard_stats_cache["data"]

    # 2. Check db.stats_cache collection
    if not force_refresh:
        cached_doc = await db.stats_cache.find_one({"_id": "dashboard_stats"})
        if cached_doc and cached_doc.get("data"):
            updated_ts = cached_doc.get("updated_at_ts", 0.0)
            if now_ts - updated_ts < DASHBOARD_STATS_CACHE_TTL:
                stats = cached_doc["data"]
                _dashboard_stats_cache["data"] = stats
                _dashboard_stats_cache["expires_at"] = updated_ts + DASHBOARD_STATS_CACHE_TTL
                return stats

    # 3. Live computation fallback
    stats = await _compute_dashboard_stats_live()
    _dashboard_stats_cache["data"] = stats
    _dashboard_stats_cache["expires_at"] = now_ts + DASHBOARD_STATS_CACHE_TTL

    # Persist to db.stats_cache
    try:
        await db.stats_cache.update_one(
            {"_id": "dashboard_stats"},
            {
                "$set": {
                    "data": stats,
                    "updated_at": now_iso(),
                    "updated_at_ts": now_ts,
                    "ttl_seconds": DASHBOARD_STATS_CACHE_TTL,
                }
            },
            upsert=True,
        )
    except Exception as e:
        log.warning(f"Failed to update db.stats_cache: {e}")

    return stats


# ---------- SEED DEMO DATA (admin only) ----------
@api.post("/seed/demo")
async def seed_demo(request: Request):
    u = await get_current_user(request); require_roles("admin")(u)
    # only seed if empty
    if await db.materials.count_documents({}) > 0:
        return {"skipped": True, "reason": "Already seeded"}
    demo_materials = [
        ("CNV-001", "Cotton Canvas - Beige", "upper", "sqft", 28.0),
        ("CNV-002", "Cotton Canvas - Wine", "upper", "sqft", 28.0),
        ("LIN-001", "Cotton Lining White", "lining", "sqft", 14.0),
        ("PVC-001", "PVC Sole Brown 8mm", "sole", "pcs", 65.0),
        ("EVA-001", "EVA Cushion 4mm", "sole", "sqft", 22.0),
        ("ADH-001", "Solution Adhesive", "consumable", "gm", 0.35),
        ("ADH-002", "Hardener", "consumable", "gm", 0.45),
        ("THN-001", "Thinner", "consumable", "ml", 0.12),
        ("PRM-001", "Primer EVA", "consumable", "ml", 0.40),
        ("BCK-001", "Metal Buckle", "accessory", "pcs", 8.0),
        ("PKG-001", "Shoe Box - Standard", "packing", "pcs", 12.0),
    ]
    mat_docs = []
    for code, name, cat, unit, rate in demo_materials:
        mat_docs.append({
            "code": code, "name": name, "category": cat, "unit": unit,
            "rate": rate, "notes": "", "created_at": now_iso(), "updated_at": now_iso(),
        })
    await db.materials.insert_many(mat_docs)
    return {"ok": True, "materials_inserted": len(mat_docs)}


# ---------- ROOT & ROUTERS ----------
@app.get("/")
async def root():
    return {
        "message": "Welcome to SSK Footwear ERP API! 🚀",
        "docs": "Visit /docs for the API documentation."
    }

app.include_router(api)
app.include_router(auth_router)
app.include_router(plm_router)
app.include_router(settings_router)
app.include_router(workers_router)
app.include_router(vendors_router)
app.include_router(notifications_router)
app.include_router(components_router)
app.include_router(expenses_router)
app.include_router(sku_map_router)
app.include_router(online_reconciliation_router)
app.include_router(materials_router)
app.include_router(inventory_router)
app.include_router(invoice_packing_router)
app.include_router(wms_router)
app.include_router(pos_router)
app.include_router(online_orders_router)
app.include_router(styles_router)




@app.on_event("startup")
async def on_startup():
    global get_current_user
    get_current_user = await get_current_user_factory(db)
    await db.users.create_index("email", unique=True)
    
    # Safely create unique index for materials
    try:
        await db.materials.create_index("code", unique=True)
    except Exception as e:
        log.warning(f"Could not create unique index on materials.code directly: {e}. Dropping old index and retrying.")
        try:
            await db.materials.drop_index("code_1")
            await db.materials.create_index("code", unique=True)
        except Exception as drop_err:
            log.error(f"Failed to force unique index on materials.code: {drop_err}")

    # Safely create unique index for styles
    try:
        await db.styles.create_index("code", unique=True)
    except Exception as e:
        log.warning(f"Could not create unique index on styles.code directly: {e}. Dropping old index and retrying.")
        try:
            await db.styles.drop_index("code_1")
            await db.styles.create_index("code", unique=True)
        except Exception as drop_err:
            log.error(f"Failed to force unique index on styles.code: {drop_err}")

    # Safely create unique index for POs
    try:
        await db.pos.create_index("po_number", unique=True)
    except Exception as e:
        log.warning(f"Could not create unique index on pos.po_number directly: {e}. Dropping old index and retrying.")
        try:
            await db.pos.drop_index("po_number_1")
            await db.pos.create_index("po_number", unique=True)
        except Exception as drop_err:
            log.error(f"Failed to force unique index on pos.po_number: {drop_err}")

    # PO, Job, Invoice, and Dispatch query optimization indexes
    try:
        await db.production_jobs.create_index("po_id")
        await db.production_jobs.create_index("style_id")
        await db.production_jobs.create_index("style_code")
        await db.production_jobs.create_index("po_number")
    except Exception as e:
        log.warning(f"Could not create production_jobs indexes: {e}")

    try:
        await db.invoices.create_index("po_id")
        await db.invoices.create_index("po_ids")
        await db.invoices.create_index("po_number")
        await db.invoices.create_index("po_numbers")
    except Exception as e:
        log.warning(f"Could not create invoices indexes: {e}")

    try:
        await db.dispatch_records.create_index("po_id")
        await db.dispatch_records.create_index("po_ids")
        await db.dispatch_records.create_index("po_number")
        await db.dispatch_records.create_index("po_numbers")
    except Exception as e:
        log.warning(f"Could not create dispatch_records indexes: {e}")

    try:
        await db.vendors.create_index("name")
    except Exception as e:
        log.warning(f"Could not create vendors index: {e}")

    # Worker PIN login: phone index for fast lookup
    try:
        await db.workers.create_index("phone", name="workers_phone", sparse=True)
    except Exception as e:
        log.warning(f"Could not create workers.phone index: {e}")

    # Notifications: unread + time index for efficient polling
    try:
        await db.notifications.create_index(
            [("read", 1), ("at", -1)], name="notifications_unread_time"
        )
        await db.notifications.create_index("job_id", name="notifications_job_id")
    except Exception as e:
        log.warning(f"Could not create notifications indexes: {e}")

    # SKU map indexes: unique compound on (source_type, source_name, external_sku) + style lookup
    try:
        await db.sku_map.create_index(
            [("source_type", 1), ("source_name_key", 1), ("external_sku_key", 1)],
            unique=True, name="sku_map_unique_normalized"
        )
        await db.sku_map.create_index("style_id", name="sku_map_style_id")
    except Exception as e:
        log.warning(f"Could not create sku_map indexes: {e}")

    # Style lifecycle: unique per style_id + status index for fast pipeline filtering
    try:
        await db.style_lifecycle.create_index("style_id", unique=True, name="style_lifecycle_unique")
        await db.style_lifecycle.create_index("online_status", name="style_lifecycle_status")
    except Exception as e:
        log.warning(f"Could not create style_lifecycle indexes: {e}")

    # Password reset tokens: TTL index auto-purges expired rows + lookup index on hash.
    try:
        await db.password_resets.create_index("token_hash", unique=True, name="password_reset_token")
        await db.password_resets.create_index("user_id", name="password_reset_user")
        await db.password_resets.create_index("expires_at", expireAfterSeconds=0, name="password_reset_ttl")
    except Exception as e:
        log.warning(f"Could not create password_resets indexes: {e}")

    # Component master: unique (code, color, size). Category & active for fast filter.
    try:
        await db.component_master.create_index(
            [("component_code", 1), ("color", 1), ("size", 1)],
            unique=True, name="component_master_unique"
        )
        await db.component_master.create_index("component_category", name="component_master_category")
        await db.component_master.create_index("active", name="component_master_active")
    except Exception as e:
        log.warning(f"Could not create component_master indexes: {e}")

    # Component stock movements ledger: hot queries are by component + time and by style.
    try:
        await db.component_stock_movements.create_index([("component_id", 1), ("created_at", -1)],
                                                       name="component_moves_by_component")
        await db.component_stock_movements.create_index("movement_type", name="component_moves_type")
        await db.component_stock_movements.create_index("style_id", name="component_moves_style")
        await db.component_stock_movements.create_index("created_at", name="component_moves_created")
    except Exception as e:
        log.warning(f"Could not create component_stock_movements indexes: {e}")

    # Style ⇄ component mapping: one row per (style, component); reverse-index for shared components.
    try:
        await db.style_component_mapping.create_index(
            [("style_id", 1), ("component_id", 1)],
            unique=True, name="style_component_mapping_unique"
        )
        await db.style_component_mapping.create_index("component_id", name="style_component_mapping_component")
    except Exception as e:
        log.warning(f"Could not create style_component_mapping indexes: {e}")

    # fg_inventory unique index
    try:
        await db.fg_inventory.create_index(
            [("style_id", 1), ("color", 1), ("size", 1)],
            unique=True, name="fg_inventory_unique"
        )
    except Exception as e:
        log.warning(f"Could not create fg_inventory unique index: {e}")

    # Phase 2: FG movements & inventory reservations indexes
    try:
        await db.fg_stock_movements.create_index(
            [("style_id", 1), ("created_at", -1)], name="fg_mv_style_ts"
        )
        await db.fg_stock_movements.create_index("movement_type",  name="fg_mv_type")
        await db.fg_stock_movements.create_index("reference_id",   name="fg_mv_ref_id")
        await db.fg_stock_movements.create_index("created_at",     name="fg_mv_ts")
    except Exception as e:
        log.warning(f"Could not create fg_stock_movements indexes: {e}")

    try:
        await db.inventory_reservations.create_index(
            [("online_order_id", 1), ("status", 1)], name="inv_res_order_status"
        )
        await db.inventory_reservations.create_index(
            [("style_id", 1), ("color", 1), ("size", 1), ("status", 1)],
            name="inv_res_sku_status"
        )
    except Exception as e:
        log.warning(f"Could not create inventory_reservations indexes: {e}")

    # WMS: warehouse_locations, fg_location_inventory, picklists
    try:
        await db.warehouse_locations.create_index("location_code", unique=True,
                                                   name="warehouse_locations_unique")
        await db.warehouse_locations.create_index("rack", name="warehouse_locations_rack")
        await db.warehouse_locations.create_index("status", name="warehouse_locations_status")
    except Exception as e:
        log.warning(f"Could not create warehouse_locations indexes: {e}")

    try:
        await db.fg_location_inventory.create_index(
            [("style_id", 1), ("color", 1), ("size", 1), ("location_code", 1)],
            unique=True, name="fg_loc_inv_unique",
        )
        await db.fg_location_inventory.create_index("location_code", name="fg_loc_inv_location")
        await db.fg_location_inventory.create_index(
            [("style_id", 1), ("color", 1), ("size", 1), ("created_at", 1)],
            name="fg_loc_inv_fifo",
        )
    except Exception as e:
        log.warning(f"Could not create fg_location_inventory indexes: {e}")

    try:
        await db.picklists.create_index("picklist_no", unique=True, name="picklists_no_unique")
        await db.picklists.create_index("order_id", name="picklists_order")
        await db.picklists.create_index("status",   name="picklists_status")
        await db.picklists.create_index("channel",  name="picklists_channel")
        await db.picklists.create_index("created_at", name="picklists_created")
        await db.online_orders.create_index(
            [("platform_key", 1), ("order_id_key", 1)], unique=True,
            partialFilterExpression={"order_id_key": {"$exists": True, "$type": "string"}},
            name="online_orders_platform_order_unique",
        )
        await db.online_order_items.create_index(
            [("platform_key", 1), ("order_id_key", 1), ("line_id_key", 1)], unique=True,
            partialFilterExpression={"line_id_key": {"$exists": True, "$type": "string"}},
            name="online_order_items_platform_order_line_unique",
        )
    except Exception as e:
        log.warning(f"Could not create picklists indexes: {e}")

    # Auto-seed 320 warehouse cells (idempotent)
    try:
        inserted = await _seed_warehouse_locations()
        if inserted:
            log.info(f"WMS: seeded {inserted} warehouse cells")
    except Exception as e:
        log.warning(f"WMS auto-seed failed: {e}")

    # Marketplace SKU Resolver: indexes + seed default parser templates
    try:
        await db.sku_parser_templates.create_index("marketplace", unique=True,
                                                    name="sku_parser_marketplace_unique")
    except Exception as e:
        log.warning(f"Could not create sku_parser_templates index: {e}")

    try:
        await db.marketplace_style_color_mapping.create_index(
            [("marketplace_key", 1), ("marketplace_style_code_key", 1), ("marketplace_color_code_key", 1)],
            unique=True, name="mp_scm_unique_normalized",
        )
        await db.marketplace_style_color_mapping.create_index("erp_style_code", name="mp_scm_erp_style")
    except Exception as e:
        log.warning(f"Could not create marketplace_style_color_mapping indexes: {e}")

    try:
        await db.unresolved_sku_queue.create_index(
            [("marketplace", 1), ("marketplace_style_code", 1), ("marketplace_color_code", 1),
             ("raw_sku", 1)], unique=True, name="unresolved_sku_unique",
        )
        await db.unresolved_sku_queue.create_index("status", name="unresolved_sku_status")
    except Exception as e:
        log.warning(f"Could not create unresolved_sku_queue indexes: {e}")

    try:
        seeded = await _seed_parser_templates()
        if seeded:
            log.info(f"Marketplace: seeded {seeded} default parser templates")
    except Exception as e:
        log.warning(f"Parser template seed failed: {e}")

    await seed_admin(db)
    try:
        seeded = await _seed_color_master()
        if seeded:
            log.info(f"Color master: seeded {seeded} default colours")
    except Exception as e:
        log.warning(f"Color master seed failed: {e}")

    try:
        seeded_lfc = await _seed_listing_format_configs()
        if seeded_lfc:
            log.info(f"Listing format registry: seeded {seeded_lfc} platform configs (myntra/ajio/flipkart)")
    except Exception as e:
        log.warning(f"Listing format registry seed failed: {e}")

    try:
        seeded_oifc = await _seed_order_import_configs()
        if seeded_oifc:
            log.info(f"Order import registry: seeded {seeded_oifc} platform configs (flipkart/myntra)")
    except Exception as e:
        log.warning(f"Order import registry seed failed: {e}")
    try:
        profile = await db.settings.find_one({"_id": "company_profile"})
        if profile:
            from pdf_docs import update_company_profile
            update_company_profile(profile)
            log.info("Loaded custom company profile from DB.")
    except Exception as e:
        log.warning(f"Could not load company profile from DB: {e}")
    try:
        await db.online_profitability_daily.create_index(
            [("platform", 1), ("date_from", 1), ("date_to", 1), ("style_id", 1)],
            unique=True, name="profitability_daily_key",
        )
    except Exception as e:
        log.warning(f"Could not create online_profitability_daily index: {e}")

    # ── One-time URL rewrites for image URLs that predate the current shape.
    # (1) legacy "/uploads/..." → "/api/uploads/..." so K8s ingress routes them
    # (2) stale absolute "http(s)://<old-preview-host>/api/uploads/..." → relative "/api/uploads/..."
    # Both idempotent — only touches docs that still carry the older shape.
    try:
        import re as _re
        for coll, fields in (
            ("styles",    ["image_url", "image_display_url", "image_thumbnail_url"]),
            ("materials", ["image_url", "image_display_url", "image_thumbnail_url"]),
        ):
            for fld in fields:
                # (1) legacy /uploads/ → /api/uploads/
                q1 = {fld: {"$regex": r"^https?://[^/]+/uploads/(?!.*api/uploads)"}}
                async for d in db[coll].find(q1, {fld: 1}):
                    v = d.get(fld) or ""
                    if "/api/uploads/" in v: continue
                    await db[coll].update_one(
                        {"_id": d["_id"]},
                        {"$set": {fld: v.replace("/uploads/", "/api/uploads/", 1)}},
                    )

                # (2) absolute /api/uploads/ → relative /api/uploads/
                q2 = {fld: {"$regex": r"^https?://[^/]+/api/uploads/"}}
                cnt = 0
                async for d in db[coll].find(q2, {fld: 1}):
                    v = d.get(fld) or ""
                    new_v = _re.sub(r"^https?://[^/]+", "", v)
                    await db[coll].update_one({"_id": d["_id"]}, {"$set": {fld: new_v}})
                    cnt += 1
                if cnt:
                    log.info(f"Migration: stripped hostname from {cnt} {coll}.{fld} values.")
    except Exception as e:
        log.warning(f"URL-rewrite migration failed (non-fatal): {e}")

    log.info("Startup complete; admin seeded.")

@app.on_event("shutdown")
async def on_shutdown():
    client.close()
