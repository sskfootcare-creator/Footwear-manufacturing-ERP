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
from collections import defaultdict
from po_extractor import extract_po_from_pdf, extract_po_from_xlsx
from pdf_docs import generate_dispatch_challan_pdf, build_invoice
from packing_list import build_default_packing_list, build_from_template, build_dispatch_packing_list, build_carton_list_xlsx
from pdf_procurement import build_material_requirement
from pdf_card import build_production_card
from pdf_carton_label import build_carton_labels
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from io import BytesIO
import uuid
import boto3
from models import *
from rate_limiter import upload_rate_limiter, pdf_rate_limiter, bulk_import_rate_limiter

# ---------- DB & app ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="SSK Footcare ERP")
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

    # ── Read once, enforce size cap BEFORE decoding to keep memory bounded
    MAX_UPLOAD_BYTES = 8 * 1024 * 1024   # 8 MB — server-side limit
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Image too large ({len(content) // (1024*1024)} MB). Max allowed is 8 MB."
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

    # ---- ONEDRIVE (1drv.ms shortlink OR onedrive.live.com share) ----------
    if host == "1drv.ms" or host.endswith("onedrive.live.com"):
        b = _b64.urlsafe_b64encode(val.encode("utf-8")).decode("ascii").rstrip("=")
        return f"https://api.onedrive.com/v1.0/shares/u!{b}/root/content"

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

# ---------- Login rate limiting (in-memory, per-IP) ----------
# Stores timestamps of failed login attempts keyed by IP string.
_login_failures: dict = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5       # max failures before lockout
LOGIN_WINDOW_SECONDS = 900   # 15-minute sliding window

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

STYLE_CODE_PREFIX = "SSK_"
STYLE_CODE_PAD = 5   # SSK_00001, SSK_00002, ...
STYLE_CODE_RE = re.compile(rf"^{re.escape(STYLE_CODE_PREFIX)}\d{{{STYLE_CODE_PAD},}}$")


async def _next_style_code() -> str:
    """Atomically increment the style_code counter and return the next code.

    Uses find_one_and_update with $inc + upsert — the standard Mongo pattern for
    a strictly-increasing counter that is safe under concurrent inserts. Never
    counts existing styles or scans for max — those race.
    """
    doc = await db.counters.find_one_and_update(
        {"_id": "style_code"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int(doc.get("seq", 1))
    return f"{STYLE_CODE_PREFIX}{seq:0{STYLE_CODE_PAD}d}"


def build_catalogue_sku(style_code: str, color_code: str, size: Optional[str] = None) -> str:
    """Canonical catalogue-SKU builder — MUST be used everywhere a catalogue
    SKU needs to be produced so the format never drifts.

    - Style + colour (used as the marketplace "group id" / Style Id):
        f"{style_code}-{color_code}"       → "SSK_00001-TN"
    - Style + colour + size (fully-unique leaf SKU on each marketplace row):
        f"{style_code}-{color_code}-{size}"→ "SSK_00001-TN-38"
    """
    sc = (style_code or "").strip()
    cc = (color_code or "").strip().upper()
    if not sc or not cc:
        return ""
    if size is None or str(size).strip() == "":
        return f"{sc}-{cc}"
    return f"{sc}-{cc}-{str(size).strip()}"


# ---------- Colour master seed vocabulary ----------
# Short uppercase codes (2-3 letters) used by build_catalogue_sku. Chosen to
# avoid collisions across the current colour palette visible in the styles
# catalogue. Admin can add more via POST /api/color-master.
DEFAULT_COLOR_MASTER = [
    ("Tan",         "TN"),
    ("Beige",       "BG"),
    ("Gold",        "GD"),
    ("Silver",      "SL"),
    ("Blue",        "BL"),
    ("Navy",        "NV"),
    ("Brown",       "BR"),
    ("Gunmetal",    "GN"),
    ("Maroon",      "MR"),
    ("Pink",        "PK"),
    ("Black",       "BK"),
    ("White",       "WH"),
    ("Cream",       "CR"),
    ("Deep Peach",  "DP"),
    ("Grey",        "GY"),
    ("Red",         "RD"),
    ("Green",       "GR"),
    ("Yellow",      "YL"),
    ("Orange",      "OR"),
    ("Purple",      "PR"),
    ("Rose Gold",   "RG"),
    ("Copper",      "CP"),
    ("Bronze",      "BZ"),
    ("Nude",        "ND"),
    ("Olive",       "OV"),
]


async def _seed_color_master() -> int:
    """Idempotently seed the color_master collection with the default palette."""
    # Ensure a unique index on color_code so build_catalogue_sku always resolves 1:1
    try:
        await db.color_master.create_index("color_code", unique=True, name="color_master_code_unique")
    except Exception as e:
        log.warning(f"Could not create color_master unique index: {e}")
    # Also index by lowercase name for fast lookup
    try:
        await db.color_master.create_index("color_name_lc", name="color_master_name_lc")
    except Exception as e:
        log.warning(f"Could not create color_master name index: {e}")

    inserted = 0
    for name, code in DEFAULT_COLOR_MASTER:
        existing = await db.color_master.find_one({"color_code": code})
        if existing:
            continue
        # Also skip if the name already exists under a different code
        by_name = await db.color_master.find_one({"color_name_lc": name.lower()})
        if by_name:
            continue
        await db.color_master.insert_one({
            "color_name":    name,
            "color_name_lc": name.lower(),
            "color_code":    code,
            "active":        True,
            "created_at":    now_iso(),
            "updated_at":    now_iso(),
        })
        inserted += 1
    return inserted


async def resolve_color_code(color_name: str) -> Optional[str]:
    """Look up a colour's short code by name (case-insensitive)."""
    if not color_name:
        return None
    doc = await db.color_master.find_one({
        "color_name_lc": color_name.strip().lower(),
        "active": {"$ne": False},
    })
    return doc["color_code"] if doc else None


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
@api.post("/auth/login")
async def login(payload: LoginInput, request: Request, response: Response):
    # --- Rate limiting: reject IPs that have too many recent failures ---
    client_ip = request.headers.get("x-test-rate-limit-client-ip") or (request.client.host if request.client else "unknown")
    now_ts = datetime.now(timezone.utc).timestamp()
    window_start = now_ts - LOGIN_WINDOW_SECONDS
    # Prune old entries
    _login_failures[client_ip] = [
        t for t in _login_failures[client_ip] if t > window_start
    ]
    if len(_login_failures[client_ip]) >= LOGIN_MAX_ATTEMPTS:
        retry_after = int(LOGIN_WINDOW_SECONDS - (now_ts - _login_failures[client_ip][0]))
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {retry_after // 60} minutes.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )

    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("active", True) or not verify_password(payload.password, user["password_hash"]):
        # Record the failure for rate limiting
        _login_failures[client_ip].append(now_ts)
        log.warning("Failed login attempt for email=%s from ip=%s (attempt %d/%d)",
                    email, client_ip, len(_login_failures[client_ip]), LOGIN_MAX_ATTEMPTS)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Success — clear failure counter for this IP
    _login_failures.pop(client_ip, None)
    uid = str(user["_id"])
    access = create_access_token(uid, email, user["role"])
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    return {
        "id": uid, "email": email, "name": user["name"], "role": user["role"],
        "access_token": access, "refresh_token": refresh
    }

@api.post("/auth/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}

@api.post("/auth/refresh")
async def refresh_token_route(request: Request, response: Response):
    """Accept refresh_token from either the httpOnly cookie OR the JSON body.
    The body-based flow is used when cookies can't be transmitted (e.g. when the
    frontend is embedded inside a cross-origin iframe and the ingress forces
    Access-Control-Allow-Origin: '*', which blocks credentialed fetches).
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        try:
            body = await request.json()
            refresh_token = (body or {}).get("refresh_token")
        except Exception:
            refresh_token = None
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = jwt.decode(refresh_token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user or not user.get("active", True):
            raise HTTPException(status_code=401, detail="User not found or inactive")
        
        new_access = create_access_token(str(user["_id"]), user["email"], user["role"])
        set_auth_cookies(response, new_access)
        return {"ok": True, "access_token": new_access}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Expired refresh token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@api.get("/auth/me")
async def me(request: Request):
    user = await get_current_user(request)
    return user


# ---------- PASSWORD RESET ----------
# Two flows:
#   1. `POST /auth/forgot-password { email }` — issues a single-use, 1h token,
#      stored hashed in `password_resets`, and emails a link via Gmail SMTP.
#      Always returns 200 (does not leak whether the email exists).
#   2. `POST /auth/reset-password { token, new_password }` — consumes the token,
#      updates the user's password_hash, marks token used, invalidates other
#      unused tokens for the same user.
# Gmail SMTP is opt-in: needs GMAIL_USER + GMAIL_APP_PASSWORD env vars. Without
# them the endpoint still creates the token but returns an "email not configured"
# hint so the admin can hand-deliver the link if needed.

import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    new_password: str


PASSWORD_RESET_TTL_HOURS = 1


def _hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reset_link_base() -> str:
    """Where the reset link should point. Prefer PUBLIC_APP_URL env, then FRONTEND_URL,
    then fall back to the current request's origin — but we accept nothing lower than
    the FE base URL since Gmail links must be absolute."""
    return (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("FRONTEND_URL")
        or "http://localhost:3000"
    ).rstrip("/")


def _send_reset_email(to_email: str, reset_url: str, user_name: str) -> tuple[bool, str]:
    """Return (ok, hint). ok=False when SMTP isn't configured or send fails —
    admin should surface the hint to the user without leaking secrets."""
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not gmail_user or not gmail_pass:
        return (False, "email_not_configured")

    from_display = os.environ.get("GMAIL_FROM_NAME", "SSK Footcare ERP")
    subject = "Reset your SSK Footcare ERP password"

    text_body = (
        f"Hi {user_name or 'there'},\n\n"
        f"We received a request to reset your SSK Footcare ERP password.\n"
        f"Open the link below to choose a new one — it expires in "
        f"{PASSWORD_RESET_TTL_HOURS} hour(s) and can only be used once.\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— SSK Footcare Manufacturing"
    )
    html_body = f"""\
<!doctype html>
<html><body style="font-family: system-ui, sans-serif; background:#F7F7F5; padding:24px;">
  <div style="max-width:520px; margin:0 auto; background:#fff; border:2px solid #111827; padding:28px;">
    <div style="font-size:11px; letter-spacing:2px; color:#64748B; text-transform:uppercase;">SSK Footcare Manufacturing</div>
    <h1 style="font-size:24px; margin:8px 0 16px;">Reset your password</h1>
    <p>Hi {user_name or 'there'},</p>
    <p>Click the button below to choose a new password. This link expires in
       <strong>{PASSWORD_RESET_TTL_HOURS} hour(s)</strong> and can only be used once.</p>
    <p style="text-align:center; margin:24px 0;">
      <a href="{reset_url}"
         style="background:#0F172A; color:#fff; text-decoration:none; padding:12px 24px;
                font-weight:700; letter-spacing:2px; text-transform:uppercase; font-size:12px;">
        Reset Password
      </a>
    </p>
    <p style="font-size:12px; color:#64748B; word-break:break-all;">Or copy this URL:<br/>{reset_url}</p>
    <hr style="border:none; border-top:1px solid #E2E8F0; margin:20px 0;"/>
    <p style="font-size:11px; color:#94A3B8;">If you didn't request this, you can safely ignore this email.</p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_display} <{gmail_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [to_email], msg.as_string())
        return (True, "sent")
    except smtplib.SMTPAuthenticationError:
        log.exception("Gmail SMTP authentication failed")
        return (False, "smtp_auth_failed")
    except Exception:
        log.exception("Gmail SMTP send failed")
        return (False, "smtp_send_failed")


@api.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordInput, request: Request):
    """Issue a single-use, 1-hour password-reset token and email it.

    Always returns 200 with a generic message — we never leak whether an email
    is registered (prevents user-enumeration).
    """
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})

    generic_ok = {
        "ok": True,
        "message": "If that email matches an account, a reset link has been sent.",
    }

    if not user or not user.get("active", True):
        # Log the attempt but always return generic 200
        log.info("Forgot-password requested for unknown/inactive email: %s", email)
        return generic_ok

    # Generate a strong opaque token; store only its SHA-256 hash
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=PASSWORD_RESET_TTL_HOURS)

    # Invalidate previous unused tokens for this user before issuing a new one
    await db.password_resets.update_many(
        {"user_id": str(user["_id"]), "used_at": None},
        {"$set": {"used_at": now_iso(), "invalidated": True}},
    )

    await db.password_resets.insert_one({
        "user_id":    str(user["_id"]),
        "email":      email,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "used_at":    None,
        "created_at": datetime.now(timezone.utc),
        "created_ip": request.client.host if request.client else "unknown",
    })

    reset_url = f"{_reset_link_base()}/reset-password?token={raw_token}"
    ok, hint = _send_reset_email(email, reset_url, user.get("name", ""))

    # Response for the caller.
    if ok:
        return generic_ok

    # SMTP not configured / failed — surface a discoverable hint to the caller
    # (still 200 so we don't leak account existence). Admin who calls this on
    # their own account can look at the JSON body to see the link.
    resp: dict = dict(generic_ok)
    resp["email_status"] = hint  # "email_not_configured" | "smtp_auth_failed" | "smtp_send_failed"
    if hint == "email_not_configured":
        # In dev, expose the reset link so the admin can hand-deliver it.
        # NEVER exposes the token when SMTP is properly configured.
        resp["dev_reset_url"] = reset_url
    return resp


@api.post("/auth/reset-password")
async def reset_password(payload: ResetPasswordInput):
    """Consume a reset token and set a new password. Invalidates all other
    outstanding tokens for the same user on success."""
    token_hash = _hash_reset_token(payload.token.strip())
    row = await db.password_resets.find_one({"token_hash": token_hash})
    if not row:
        raise HTTPException(400, "Invalid or already-used reset link.")
    if row.get("used_at"):
        raise HTTPException(400, "This reset link has already been used.")
    exp = row.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(400, "This reset link has expired. Please request a new one.")
    validate_password(payload.new_password)

    user = await db.users.find_one({"_id": oid(row["user_id"])})
    if not user or not user.get("active", True):
        raise HTTPException(400, "Account not found or inactive.")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "password_updated_at": now_iso()}},
    )
    # Mark this token used + invalidate every other outstanding token for this user
    await db.password_resets.update_one(
        {"_id": row["_id"]},
        {"$set": {"used_at": now_iso()}},
    )
    await db.password_resets.update_many(
        {"user_id": str(user["_id"]), "used_at": None, "_id": {"$ne": row["_id"]}},
        {"$set": {"used_at": now_iso(), "invalidated": True}},
    )
    return {"ok": True, "message": "Password updated. You can now sign in."}


# ---------- USERS (admin) ----------
@api.get("/users")
async def list_users(request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    docs = await db.users.find({}, {"password_hash": 0}).to_list(500)
    return [stringify(d) for d in docs]

@api.post("/users")
async def create_user(payload: UserCreate, request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    validate_password(payload.password)  # enforce password policy
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already exists")
    doc = {
        "email": email, "name": payload.name, "role": payload.role,
        "password_hash": hash_password(payload.password),
        "active": True, "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    return {
        "id": str(res.inserted_id),
        "email": email,
        "name": payload.name,
        "role": payload.role,
        "active": True,
        "created_at": doc["created_at"],
    }

@api.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "password" in update:
        validate_password(update["password"])  # enforce password policy
        update["password_hash"] = hash_password(update.pop("password"))
    await db.users.update_one({"_id": oid(user_id)}, {"$set": update})
    doc = await db.users.find_one({"_id": oid(user_id)}, {"password_hash": 0})
    return stringify(doc)

@api.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    user = await get_current_user(request)
    require_roles("admin")(user)
    if user["id"] == user_id:
        raise HTTPException(400, "Cannot delete yourself")
    # Soft delete / deactivate instead of hard delete to preserve audit trails (e.g. POs, history)
    await db.users.update_one({"_id": oid(user_id)}, {"$set": {"active": False}})
    return {"ok": True}


# ---------- MATERIALS (rate card) ----------
@api.get("/materials")
async def list_materials(request: Request):
    await get_current_user(request)
    docs = await db.materials.find({}).sort("name", 1).to_list(2000)
    return [stringify(d) for d in docs]

@api.post("/materials")
async def create_material(payload: MaterialIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    code = payload.code.strip()
    if await db.materials.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}):
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    payload.code = code
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    try:
        res = await db.materials.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/materials/{mid}")
async def update_material(mid: str, payload: MaterialIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    code = payload.code.strip()
    if await db.materials.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "_id": {"$ne": oid(mid)}}):
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    payload.code = code
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    try:
        await db.materials.update_one({"_id": oid(mid)}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Material code '{code}' already exists")
    return stringify(await db.materials.find_one({"_id": oid(mid)}))

@api.delete("/materials/{mid}")
async def delete_material(mid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.materials.delete_one({"_id": oid(mid)})
    return {"ok": True}


# ---------- STYLES ----------
def compute_style_costing(style: dict) -> dict:
    materials_cost = 0.0
    for b in style.get("bom", []):
        rate = float(b.get("rate", 0))
        qty = float(b.get("quantity", 0))
        yld = float(b.get("yield_per_unit", 1) or 1)
        waste = float(b.get("waste_pct", 0) or 0)
        # cost per pair = (rate * qty / yield) * (1 + waste%)
        materials_cost += (rate * qty / yld) * (1 + waste / 100)
    labor_cost = sum(float(l.get("rate", 0)) for l in style.get("labor", []))
    base_cost = materials_cost + labor_cost
    overhead_cost = base_cost * (style.get("overhead_pct", 0) / 100)
    packing = style.get("packing_cost", 0)
    total_cost = base_cost + overhead_cost + packing
    margin_amount = total_cost * (style.get("margin_pct", 0) / 100)
    selling_price = total_cost + margin_amount
    gst_amount = selling_price * (style.get("gst_pct", 0) / 100)
    final_price = selling_price + gst_amount
    return {
        "materials_cost": round(materials_cost, 2),
        "labor_cost": round(labor_cost, 2),
        "overhead_cost": round(overhead_cost, 2),
        "packing_cost": round(packing, 2),
        "total_cost": round(total_cost, 2),
        "margin_amount": round(margin_amount, 2),
        "selling_price": round(selling_price, 2),
        "gst_amount": round(gst_amount, 2),
        "final_price": round(final_price, 2),
    }

# ---------- SKU MAP ----------

@api.get("/sku-map")
async def list_sku_map(
    request: Request,
    style_id: Optional[str] = None,
    source_type: Optional[str] = None,
    source_name: Optional[str] = None,
    search: Optional[str] = None,
):
    await get_current_user(request)
    query: dict = {}
    if style_id:
        query["style_id"] = style_id
    if source_type:
        query["source_type"] = source_type
    if source_name:
        query["source_name"] = {"$regex": re.escape(source_name), "$options": "i"}
    if search:
        query["$or"] = [
            {"external_sku": {"$regex": re.escape(search), "$options": "i"}},
            {"external_style_name": {"$regex": re.escape(search), "$options": "i"}},
            {"source_name": {"$regex": re.escape(search), "$options": "i"}},
            {"style_code": {"$regex": re.escape(search), "$options": "i"}},
        ]
    docs = await db.sku_map.find(query).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@api.get("/sku-map/resolve")
async def resolve_sku_endpoint(
    source_type: str,
    source_name: str,
    external_sku: str,
    external_color: Optional[str] = None,
    external_size: Optional[str] = None,
    request: Request = None,
):
    """Resolve (source_type, source_name, external_sku) → internal style + translated color/size.

    Returns the full resolve_style() dict including matched, match_via, color, size.
    Always returns 200; the caller should check `matched` in the response body.
    """
    await get_current_user(request)
    return await resolve_style(
        source_type=source_type,
        source_name=source_name,
        external_sku=external_sku,
        external_color=external_color,
        external_size=external_size,
    )


@api.post("/sku-map")
async def create_sku_map(payload: SkuMapIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # Validate style_id exists
    style = await db.styles.find_one({"_id": oid(payload.style_id)})
    if not style:
        raise HTTPException(404, f"Style '{payload.style_id}' not found")
    doc = payload.model_dump()
    doc["style_code"] = style["code"]          # denormalised for display
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    doc["created_by"] = u["email"]
    try:
        res = await db.sku_map.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"A mapping for source '{payload.source_name}' / SKU '{payload.external_sku}' already exists")
    await log_activity("CREATE", "sku_map", f"Mapped {payload.external_sku} ({payload.source_name}) → {style['code']}", u["email"])
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    # Update previously unmatched production jobs
    await _update_unmatched_jobs_for_sku_mapping(res.inserted_id, doc)
    return doc


@api.put("/sku-map/{mid}")
async def update_sku_map(mid: str, payload: SkuMapUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    existing = await db.sku_map.find_one({"_id": oid(mid)})
    if not existing:
        raise HTTPException(404, "Mapping not found")
    update: dict = {"updated_at": now_iso()}
    if payload.external_style_name is not None:
        update["external_style_name"] = payload.external_style_name
    if payload.color_map is not None:
        update["color_map"] = payload.color_map
    if payload.size_map is not None:
        update["size_map"] = payload.size_map
    await db.sku_map.update_one({"_id": oid(mid)}, {"$set": update})
    await log_activity("UPDATE", "sku_map", f"Updated mapping {mid}", u["email"])
    updated_doc = await db.sku_map.find_one({"_id": oid(mid)})
    if updated_doc:
        await _update_unmatched_jobs_for_sku_mapping(mid, updated_doc)
    return stringify(await db.sku_map.find_one({"_id": oid(mid)}))


@api.delete("/sku-map/{mid}")
async def delete_sku_map(mid: str, request: Request):
    u = await get_current_user(request); require_roles("admin")(u)
    existing = await db.sku_map.find_one({"_id": oid(mid)})
    if not existing:
        raise HTTPException(404, "Mapping not found")
    await db.sku_map.delete_one({"_id": oid(mid)})
    await log_activity("DELETE", "sku_map", f"Deleted mapping {mid} ({existing.get('source_name')} / {existing.get('external_sku')})", u["email"])
    return {"ok": True}


@api.post("/sku-map/bulk", dependencies=[Depends(upload_rate_limiter)])
async def bulk_create_sku_map(
    file: UploadFile = File(...),
    source_type: str = "b2b_client",
    source_name: str = "",
    request: Request = None,
):
    """Bulk-import SKU mappings from a CSV file.

    The CSV must contain at minimum the columns:
      external_sku  — the code the client / platform uses          (required)
      style_code    — our internal styles.code to map it to        (required)

    Optional columns (any absent column is silently skipped):
      external_style_name — human-readable description from that source
      color_from / color_to  — one color translation pair per row
      size_from  / size_to   — one size  translation pair per row

    source_type and source_name can be supplied either as form fields or as
    columns inside the CSV (CSV columns take priority per row).

    Returns a summary: {created, skipped_duplicate, errors: [{row, reason}]}
    """
    import io
    import csv

    u = await get_current_user(request); require_roles("admin", "manager")(u)

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")   # strip BOM if present
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    # Normalise column names: strip whitespace, lower-case
    def norm_row(row: dict) -> dict:
        return {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items()}

    created = 0
    skipped_duplicate = 0
    errors = []

    # Pre-fetch all style codes for fast lookup (code.upper() → ObjectId str)
    all_styles_cursor = await db.styles.find({}, {"code": 1}).to_list(10000)
    style_code_map = {s["code"].strip().upper(): str(s["_id"]) for s in all_styles_cursor}

    for idx, raw_row in enumerate(reader, start=2):   # row 1 = header
        row = norm_row(raw_row)

        # Resolve source_type / source_name: CSV column > form field
        row_src_type = row.get("source_type", "") or source_type
        row_src_name = row.get("source_name", "") or source_name

        ext_sku   = row.get("external_sku", "").strip()
        s_code    = row.get("style_code", "").strip()

        if not ext_sku:
            errors.append({"row": idx, "reason": "external_sku is empty"})
            continue
        if not s_code:
            errors.append({"row": idx, "reason": "style_code is empty"})
            continue
        if not row_src_name:
            errors.append({"row": idx, "reason": "source_name is empty (not in CSV and not provided as form field)"})
            continue

        style_id = style_code_map.get(s_code.upper())
        if not style_id:
            errors.append({"row": idx, "reason": f"style_code '{s_code}' not found in Style Master"})
            continue

        # Build optional color_map / size_map from per-row from/to columns
        color_map: dict = {}
        size_map:  dict = {}
        cf = row.get("color_from", ""); ct = row.get("color_to", "")
        sf = row.get("size_from",  ""); st = row.get("size_to",  "")
        if cf and ct:
            color_map[cf] = ct
        if sf and st:
            size_map[sf] = st

        doc = {
            "style_id":           style_id,
            "style_code":         s_code,
            "source_type":        row_src_type,
            "source_name":        row_src_name,
            "external_sku":       ext_sku,
            "external_style_name": row.get("external_style_name", ""),
            "color_map":          color_map,
            "size_map":           size_map,
            "created_at":         now_iso(),
            "updated_at":         now_iso(),
            "created_by":         u["email"],
        }
        try:
            res = await db.sku_map.insert_one(doc)
            created += 1
            await _update_unmatched_jobs_for_sku_mapping(res.inserted_id, doc)
        except DuplicateKeyError:
            skipped_duplicate += 1

    await log_activity(
        "BULK_CREATE", "sku_map",
        f"Bulk import: {created} created, {skipped_duplicate} duplicates, {len(errors)} errors (source: {source_name or 'per-row'})",
        u["email"],
    )
    return {"created": created, "skipped_duplicate": skipped_duplicate, "errors": errors}


@api.get("/sku-map/unmapped")
async def sku_map_unmapped(request: Request):
    """Return all active production jobs with style_match_status='unmatched',
    grouped by source_type + source_name (derived from the job's client_name, always
    'b2b_client' for PO-originated jobs), mirroring the grouping shape of
    /api/production/unmatched-styles.

    Each group has:
      source_type  — always 'b2b_client' for now
      source_name  — the client name from the originating PO
      job_count    — total unresolved jobs in this group
      external_skus — distinct external SKU codes seen in this group (for quick mapping)
      jobs         — list of individual job summaries
    """
    await get_current_user(request)
    jobs = await db.production_jobs.find({
        "archived":           {"$ne": True},
        "stage":              {"$ne": "dispatched"},
        "style_match_status": "unmatched",
    }).to_list(5000)

    # Group by (source_type, source_name). All PO jobs are b2b_client for now.
    groups: dict[tuple, dict] = {}
    for j in jobs:
        src_type = "b2b_client"
        src_name = j.get("client_name") or "(unknown)"
        key = (src_type, src_name)
        if key not in groups:
            groups[key] = {
                "source_type":  src_type,
                "source_name":  src_name,
                "job_count":    0,
                "external_skus": [],
                "jobs":         [],
            }
        g = groups[key]
        g["job_count"] += 1
        ext_sku = j.get("style_code") or "(blank)"
        if ext_sku not in g["external_skus"]:
            g["external_skus"].append(ext_sku)
        g["jobs"].append({
            "id":                  str(j["_id"]),
            "po_number":           j.get("po_number"),
            "style_code":          j.get("style_code"),
            "color":               j.get("color"),
            "size":                j.get("size"),
            "quantity":            j.get("quantity"),
            "stage":               j.get("stage"),
            "style_match_status":  j.get("style_match_status"),
            "created_at":          j.get("created_at"),
        })

    result = list(groups.values())
    result.sort(key=lambda g: -g["job_count"])
    return result


# ---------- STYLE LIFECYCLE (Online branch) ----------
#
# A separate collection `style_lifecycle`, keyed by style_id, so the B2B style
# doc remains untouched. Every style may or may not have a lifecycle doc — the
# GET endpoint auto-creates a "draft" doc so the pipeline UI always has a row.


def _default_lifecycle(style_id: str, style_code: str) -> dict:
    now = now_iso()
    return {
        "style_id":                style_id,          # str ObjectId
        "style_code":              style_code,        # denormalised for display
        "online_status":           "draft",
        "online_status_history":   [{
            "status":     "draft",
            "changed_at": now,
            "by":         "system",
            "notes":      "Auto-initialised on first read",
        }],
        "sale_channels":           [],
        "mrp":                     None,
        "online_selling_price":    None,
        "platform_commission_pct": {},
        "planned_min_stock":       25,
        "planned_components":      [{"component": c, "planned_qty": 0} for c in PLANNED_COMPONENTS],
        "planned_colors":          [],
        "planned_sizes":           [],
        "sole_mould_name":         "",
        "sole_shape":              "",
        "pattern_number":          "",
        "photoshoot_link":         "",
        "catalogue_link":          "",
        "back_track_number":       "",
        "went_live_at":            None,
        "created_at":              now,
        "updated_at":              now,
    }


async def _get_or_create_lifecycle(style_id: str) -> dict:
    """Look up the lifecycle doc for a style. If missing, insert a default (draft) one."""
    style = await db.styles.find_one({"_id": oid(style_id)})
    if not style:
        raise HTTPException(404, f"Style '{style_id}' not found")
    doc = await db.style_lifecycle.find_one({"style_id": str(style["_id"])})
    if doc:
        return doc
    doc = _default_lifecycle(str(style["_id"]), style["code"])
    try:
        res = await db.style_lifecycle.insert_one(doc)
        doc["_id"] = res.inserted_id
    except DuplicateKeyError:
        doc = await db.style_lifecycle.find_one({"style_id": str(style["_id"])})
    return doc


async def _generate_back_track_number(style_code: str) -> str:
    """Return '{style_code}-{YYYYMMDD}-{seq}' where seq is the next per-(code,date) counter."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"{style_code}-{today}-"
    # Count existing back_track_numbers with this prefix on style_lifecycle
    existing = await db.style_lifecycle.count_documents({
        "back_track_number": {"$regex": f"^{re.escape(prefix)}"}
    })
    return f"{prefix}{existing + 1:03d}"


async def _seed_fg_inventory_for_lifecycle(lifecycle_doc: dict, user_email: str) -> dict:
    """Auto-create fg_inventory rows for every planned (color, size) pair, at
    ready_stock_qty=0 and min_stock_level=planned_min_stock. Idempotent — if a row
    already exists for a (style_id, color, size), only the min_stock_level is updated
    (never overwrites existing quantities).

    Returns a summary: {created, updated, pairs}
    """
    style_id  = lifecycle_doc["style_id"]
    colors    = [c for c in (lifecycle_doc.get("planned_colors") or []) if c and str(c).strip()]
    sizes     = [s for s in (lifecycle_doc.get("planned_sizes")  or []) if s and str(s).strip()]
    min_stock = int(lifecycle_doc.get("planned_min_stock") or 25)

    if not colors or not sizes:
        return {"created": 0, "updated": 0, "pairs": 0,
                "note": "No planned colors/sizes — nothing seeded"}

    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    style_code = style["code"] if style else lifecycle_doc.get("style_code", "")

    created = 0
    updated = 0
    now = now_iso()
    for color in colors:
        for size in sizes:
            row = await db.fg_inventory.find_one({
                "style_id": ObjectId(style_id),
                "color":    color,
                "size":     size,
            })
            if row:
                # Only bump the min_stock_level; never touch quantities
                await db.fg_inventory.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"min_stock_level": min_stock, "updated_at": now}}
                )
                updated += 1
            else:
                try:
                    await db.fg_inventory.insert_one({
                        "style_id":         ObjectId(style_id),
                        "style_code":       style_code,
                        "color":            color,
                        "size":             size,
                        "ready_stock_qty":  0,
                        "reserved_qty":     0,
                        "in_transit_qty":   0,
                        "return_qty":       0,
                        "damaged_qty":      0,
                        "liquidation_qty":  0,
                        "min_stock_level":  min_stock,
                        "updated_at":       now,
                    })
                    created += 1
                except DuplicateKeyError:
                    updated += 1

    await log_activity(
        "SEED", "style_lifecycle",
        f"Seeded FG inventory for {style_code}: {created} created, {updated} updated ({len(colors)}x{len(sizes)} pairs)",
        user_email,
    )
    return {"created": created, "updated": updated, "pairs": len(colors) * len(sizes)}


def _validate_online_status_transition(current: str, to_status: str):
    """Raises 400 if the transition is not allowed. Rules:
       - Side-branches (archived, liquidation_candidate) are reachable from any state.
       - Otherwise: strictly forward along ONLINE_STATUS_SEQUENCE (one step at a time),
         and re-selecting the current status is a no-op (200).
    """
    if to_status not in (ONLINE_STATUS_SEQUENCE + list(ONLINE_STATUS_SIDE_BRANCHES)):
        raise HTTPException(400, f"Unknown online_status '{to_status}'")
    if to_status in ONLINE_STATUS_SIDE_BRANCHES:
        return
    if current == to_status:
        return
    # Both current and target must be in the main sequence to compare positions
    if current in ONLINE_STATUS_SIDE_BRANCHES:
        raise HTTPException(400,
            f"Cannot transition from side-branch '{current}' back into the pipeline. "
            f"Un-archive is not supported.")
    try:
        cur_idx = ONLINE_STATUS_SEQUENCE.index(current)
        new_idx = ONLINE_STATUS_SEQUENCE.index(to_status)
    except ValueError:
        raise HTTPException(400, f"Invalid transition from '{current}' to '{to_status}'")
    if new_idx != cur_idx + 1:
        raise HTTPException(400,
            f"Invalid transition: {current} → {to_status}. "
            f"Only forward, one step at a time (next allowed: "
            f"{ONLINE_STATUS_SEQUENCE[cur_idx + 1] if cur_idx + 1 < len(ONLINE_STATUS_SEQUENCE) else '—'}).")


@api.get("/style-lifecycle/{style_id}")
async def get_style_lifecycle(style_id: str, request: Request):
    """Return the lifecycle doc for a style. Auto-creates a 'draft' doc if none exists yet."""
    await get_current_user(request)
    doc = await _get_or_create_lifecycle(style_id)
    return stringify(doc)


@api.post("/styles/{sid}/pipeline")
async def add_style_to_online_pipeline(sid: str, request: Request):
    """Opt a style INTO the Online Style Pipeline.

    Creates a `draft` lifecycle doc if none exists yet. Idempotent — calling
    twice on the same style is a no-op after the first success. This is the
    only path that puts a style in the pipeline; nothing auto-materialises
    a lifecycle doc anymore.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    try:
        oid = ObjectId(sid)
    except Exception:
        raise HTTPException(400, "Invalid style id")
    style = await db.styles.find_one({"_id": oid})
    if not style:
        raise HTTPException(404, "Style not found")

    existing = await db.style_lifecycle.find_one({"style_id": sid})
    if existing:
        return {"ok": True, "already_in_pipeline": True, "lifecycle": stringify(existing)}

    doc = _default_lifecycle(sid, style["code"])
    res = await db.style_lifecycle.insert_one(doc)
    doc = await db.style_lifecycle.find_one({"_id": res.inserted_id})
    await log_activity(
        "ADD_TO_PIPELINE", "style_lifecycle",
        f"Added style {style['code']} to Online Style Pipeline.",
        u["email"],
    )
    return {"ok": True, "already_in_pipeline": False, "lifecycle": stringify(doc)}


@api.delete("/styles/{sid}/pipeline")
async def remove_style_from_online_pipeline(sid: str, request: Request):
    """Opt a style OUT of the Online Style Pipeline — deletes its lifecycle doc.
    The style itself is untouched (its B2B / catalogue rows are unaffected).
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    lc = await db.style_lifecycle.find_one({"style_id": sid})
    if not lc:
        return {"ok": True, "was_in_pipeline": False}
    style = await db.styles.find_one({"_id": ObjectId(sid)})
    style_code = (style or {}).get("code", sid)
    await db.style_lifecycle.delete_one({"style_id": sid})
    await log_activity(
        "REMOVE_FROM_PIPELINE", "style_lifecycle",
        f"Removed style {style_code} from Online Style Pipeline.",
        u["email"],
    )
    return {"ok": True, "was_in_pipeline": True}


@api.get("/styles/not-in-pipeline")
async def list_styles_not_in_pipeline(request: Request, search: Optional[str] = None):
    """Return every style that does NOT yet have a lifecycle doc — feeds the
    'Add Style to Pipeline' picker on the Online Style Pipeline page.
    """
    await get_current_user(request)
    q: dict = {}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"code": rx}, {"name": rx}]
    styles = await db.styles.find(q).sort("code", 1).to_list(5000)
    ids_in_pipeline = {
        d["style_id"]
        for d in await db.style_lifecycle.find({}, {"style_id": 1}).to_list(20000)
    }
    out = []
    for s in styles:
        sid = str(s["_id"])
        if sid in ids_in_pipeline:
            continue
        out.append({
            "id":                   sid,
            "code":                 s.get("code"),
            "name":                 s.get("name", ""),
            "image_url":            s.get("image_url", ""),
            "image_display_url":    s.get("image_display_url", ""),
            "image_thumbnail_url":  s.get("image_thumbnail_url", ""),
        })
    return out


@api.put("/style-lifecycle/{style_id}")
async def upsert_style_lifecycle(style_id: str, payload: StyleLifecycleUpsert, request: Request):
    """Upsert lifecycle fields (mrp, sale_channels, planned_*, sole info, links, etc.).
    This endpoint does NOT change online_status — use PATCH /styles/{sid}/online-status for that.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    existing = await _get_or_create_lifecycle(style_id)
    update: dict = {"updated_at": now_iso()}
    payload_dict = payload.model_dump(exclude_none=True)

    # planned_components: normalize list of pydantic objs to plain dicts
    if "planned_components" in payload_dict:
        pcs = payload_dict["planned_components"]
        # Enforce the canonical component set — merge any missing components at qty=0
        by_name = {c["component"]: int(c.get("planned_qty") or 0) for c in pcs}
        payload_dict["planned_components"] = [
            {"component": name, "planned_qty": by_name.get(name, 0)}
            for name in PLANNED_COMPONENTS
        ]

    # ── Guard: never allow a direct online_status override via this endpoint ──
    # Status transitions MUST go through PATCH /styles/{sid}/online-status which
    # runs the full _validate_online_status_transition sequence guard. Stripping
    # it here prevents a crafted PUT payload from bypassing that logic.
    payload_dict.pop("online_status", None)

    for k, v in payload_dict.items():
        update[k] = v

    await db.style_lifecycle.update_one({"style_id": str(existing.get("style_id"))}, {"$set": update})
    await log_activity(
        "UPDATE", "style_lifecycle",
        f"Updated lifecycle for {existing.get('style_code')}: {', '.join(payload_dict.keys())}",
        u["email"],
    )
    return stringify(await db.style_lifecycle.find_one({"style_id": str(existing.get("style_id"))}))


@api.patch("/styles/{sid}/online-status")
async def patch_style_online_status(sid: str, payload: OnlineStatusPatchIn, request: Request):
    """Advance a style's online lifecycle status.

    Rules:
      • Forward-only along the main pipeline sequence (one step at a time).
      • 'archived' and 'liquidation_candidate' can be set from ANY state.
      • On the FIRST transition to 'live':
          - generate back_track_number = '{style_code}-{YYYYMMDD}-{seq}'
          - set went_live_at = now
          - auto-seed fg_inventory rows for each planned (color, size) at
            ready_stock_qty=0 and min_stock_level=planned_min_stock.

    Returns the updated lifecycle doc plus a `seed_result` summary when live-seeding fired.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    lifecycle = await _get_or_create_lifecycle(sid)

    current = lifecycle.get("online_status", "draft")
    to_status = payload.to_status
    _validate_online_status_transition(current, to_status)

    now = now_iso()
    history_entry = {
        "status":     to_status,
        "changed_at": now,
        "by":         u["email"],
        "notes":      (payload.notes or "").strip(),
        "from":       current,
    }
    update = {
        "$set":  {"online_status": to_status, "updated_at": now},
        "$push": {"online_status_history": history_entry},
    }

    seed_result = None
    # First-time-live side effects
    if to_status == "live" and current != "live":
        style = await db.styles.find_one({"_id": oid(sid)})
        style_code = style["code"] if style else lifecycle.get("style_code", "")
        # Only generate a new back_track_number if the style doesn't already have one
        if not lifecycle.get("back_track_number"):
            back_track = await _generate_back_track_number(style_code)
            update["$set"]["back_track_number"] = back_track
        # Always set / refresh went_live_at on the transition INTO live
        update["$set"]["went_live_at"] = now

    await db.style_lifecycle.update_one({"style_id": str(lifecycle["style_id"])}, update)
    updated_doc = await db.style_lifecycle.find_one({"style_id": str(lifecycle["style_id"])})

    # Now seed FG inventory (after the doc is updated so seed uses the latest planned_*)
    if to_status == "live" and current != "live":
        seed_result = await _seed_fg_inventory_for_lifecycle(updated_doc, u["email"])

    await log_activity(
        "STATUS", "style_lifecycle",
        f"{updated_doc.get('style_code')}: {current} → {to_status}"
        + (f" [seeded: {seed_result['created']} FG rows]" if seed_result else ""),
        u["email"],
    )
    resp = stringify(updated_doc)
    if seed_result:
        resp["seed_result"] = seed_result
    return resp


@api.get("/styles/online")
async def list_online_styles(
    request: Request,
    online_status:  Optional[str] = None,
    sale_channel:   Optional[str] = None,
    search:         Optional[str] = None,
):
    """Return the online pipeline: every style that has (or should have) a lifecycle doc.
    For any style without an existing lifecycle doc, a default 'draft' doc is materialised
    on the fly so the pipeline is complete.

    Response items include: style_id, style_code, style_name, image_url, online_status,
    online_status_history, sale_channels, mrp, online_selling_price, planned_colors,
    planned_sizes, planned_components, back_track_number, went_live_at, and the list of
    channel SKU mappings for the style (from sku_map) for display.
    """
    await get_current_user(request)

    # Base style filter
    style_query: dict = {}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        style_query["$or"] = [{"code": rx}, {"name": rx}]

    styles = await db.styles.find(style_query).sort("code", 1).to_list(5000)
    style_ids_str = [str(s["_id"]) for s in styles]

    # Fetch ONLY styles that have a persisted lifecycle doc — pipeline is opt-in.
    # A style must be explicitly added via POST /styles/{sid}/pipeline before
    # it shows up here. This was previously auto-materialising `draft` docs
    # for every style, which flooded the pipeline with junk.
    lifecycles = await db.style_lifecycle.find({"style_id": {"$in": style_ids_str}}).to_list(5000)
    lc_by_id = {l["style_id"]: l for l in lifecycles}
    style_ids_in_pipeline = set(lc_by_id.keys())

    # Fetch all sku_map rows for these styles (denormalised into the response for display)
    mappings = await db.sku_map.find({"style_id": {"$in": list(style_ids_in_pipeline)}}).to_list(20000)
    maps_by_style: dict = {}
    for m in mappings:
        maps_by_style.setdefault(m["style_id"], []).append({
            "id":                  str(m["_id"]),
            "source_type":         m.get("source_type"),
            "source_name":         m.get("source_name"),
            "external_sku":        m.get("external_sku"),
            "external_style_name": m.get("external_style_name", ""),
        })

    out = []
    for s in styles:
        sid = str(s["_id"])
        if sid not in style_ids_in_pipeline:
            continue    # not opted-in — hide from pipeline
        lc = lc_by_id[sid]
        # Apply filters on the lifecycle side
        if online_status and lc.get("online_status") != online_status:
            continue
        if sale_channel and sale_channel not in (lc.get("sale_channels") or []):
            continue

        out.append({
            "style_id":               sid,
            "style_code":             s.get("code"),
            "style_name":             s.get("name", ""),
            "image_url":              s.get("image_url", ""),
            "image_display_url":      s.get("image_display_url", ""),
            "image_thumbnail_url":    s.get("image_thumbnail_url", ""),
            "online_status":          lc.get("online_status", "draft"),
            "online_status_history":  lc.get("online_status_history", []),
            "sale_channels":          lc.get("sale_channels", []),
            "mrp":                    lc.get("mrp"),
            "online_selling_price":   lc.get("online_selling_price"),
            "platform_commission_pct": lc.get("platform_commission_pct", {}),
            "planned_min_stock":      lc.get("planned_min_stock", 25),
            "planned_components":     lc.get("planned_components", []),
            "planned_colors":         lc.get("planned_colors", []),
            "planned_sizes":          lc.get("planned_sizes", []),
            "sole_mould_name":        lc.get("sole_mould_name", ""),
            "sole_shape":             lc.get("sole_shape", ""),
            "pattern_number":         lc.get("pattern_number", ""),
            "photoshoot_link":        lc.get("photoshoot_link", ""),
            "catalogue_link":         lc.get("catalogue_link", ""),
            "back_track_number":      lc.get("back_track_number", ""),
            "went_live_at":           lc.get("went_live_at"),
            "channel_skus":           maps_by_style.get(sid, []),
        })

    # Order by pipeline position, then by code
    def sort_key(row):
        st = row["online_status"]
        try:
            idx = ONLINE_STATUS_SEQUENCE.index(st)
        except ValueError:
            idx = 99 if st == "archived" else 98      # archived last, liquidation just before
        return (idx, row["style_code"] or "")
    out.sort(key=sort_key)
    return out


# ---------- COMPONENT INVENTORY (Phase 1) ----------
#
# Global component inventory. A "component" is one row per
# (component_code, color, size) tuple — mirroring the fg_inventory
# color x size matrix shown on Ready Stock. Stock counters are
# maintained ONLY by writing entries into component_stock_movements.
#
#   available_stock = current_stock - reserved_stock
#
# Reservation records go into a separate collection in Phase 2; here
# we just maintain the aggregate reserved_stock counter on the row.

def _serialize_component(doc: dict) -> dict:
    """Attach the derived available_stock field before returning to clients."""
    out = stringify(doc)
    out["available_stock"] = int(out.get("current_stock", 0)) - int(out.get("reserved_stock", 0))
    return out


def _build_size_matrix_pivot(
    rows: List[dict],
    qty_field:      str = "current_stock",
    reserved_field: str = "reserved_stock",
    sizes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, dict]]:
    """Build a {color: {size: {qty, reserved}}} nested pivot from a flat list of rows.

    Guarantees that every color present in `rows` has an entry for each size in
    `sizes` (defaults to STANDARD_SIZES), zero-filled when no row exists for that
    (color, size) pair. Clients can render the matrix without any additional
    grouping logic.

    Args:
        rows:           Flat component_master or fg_inventory row dicts.
        qty_field:      Field to use as the cell's ``qty`` value.
        reserved_field: Field to use as the cell's ``reserved`` value.
        sizes:          Explicit size list; falls back to STANDARD_SIZES.

    Returns:
        Dict keyed by color, then by size string (always present for every
        size in ``sizes``).
    """
    target_sizes = sizes or STANDARD_SIZES
    matrix: Dict[str, Dict[str, dict]] = {}

    for row in rows:
        color = str(row.get("color") or "").strip() or "—"
        size  = str(row.get("size")  or "").strip() or "—"
        if color not in matrix:
            # Seed the full size range at zero so the pivot is always complete
            matrix[color] = {
                sz: {"qty": 0, "reserved": 0} for sz in target_sizes
            }
        matrix[color][size] = {
            "qty":      int(row.get(qty_field,      0) or 0),
            "reserved": int(row.get(reserved_field, 0) or 0),
        }

    return matrix




def _apply_component_movement(mov_type: str, quantity: int,
                              adjustment_dir: Optional[str]) -> Dict[str, int]:
    """Return the {current_delta, reserved_delta} that this movement should
    apply to the component_master row. Signed integers.

    Pure-functional: no I/O, fully testable in isolation.
    """
    q = int(quantity)
    if q <= 0:
        raise HTTPException(400, "quantity must be a positive integer")

    if mov_type == "purchase_in":
        return {"current_delta":  q,  "reserved_delta":  0}
    if mov_type == "return_in":
        return {"current_delta":  q,  "reserved_delta":  0}
    if mov_type == "adjustment":
        if adjustment_dir not in ("increase", "decrease"):
            raise HTTPException(400, "adjustment requires adjustment_dir='increase' or 'decrease'")
        sign = 1 if adjustment_dir == "increase" else -1
        return {"current_delta": sign * q, "reserved_delta": 0}
    if mov_type in ("production_reserve", "online_reserve"):
        return {"current_delta": 0,  "reserved_delta":  q}
    if mov_type == "unreserve":
        return {"current_delta": 0,  "reserved_delta": -q}
    if mov_type in ("production_issue", "online_issue"):
        # Consume the reservation: both current and reserved go down.
        return {"current_delta": -q, "reserved_delta": -q}
    raise HTTPException(400, f"Unsupported movement_type '{mov_type}'")


async def _record_component_movement(component: dict, payload: "ComponentMovementIn",
                                     user_email: str) -> dict:
    """Atomically apply a movement to a component_master row and write a ledger entry.

    Strategy: read current values → compute deltas → write with $inc using an
    optimistic-concurrency guard (match on current_stock + reserved_stock).
    If a concurrent write has already changed the row, modified_count==0 and
    we re-read and retry up to MAX_RETRIES times before raising HTTP 409.

    This eliminates the TOCTOU race condition that existed in the old
    read → compute → $set pattern, where two concurrent movements could both
    read the same stale value and both persist, corrupting stock counts.
    """
    MAX_RETRIES = 3

    for attempt in range(MAX_RETRIES):
        # ── Re-read on every retry to get the latest values ──────────────────
        if attempt > 0:
            component = await db.component_master.find_one({"_id": component["_id"]})
            if not component:
                raise HTTPException(404, "Component row disappeared during movement — abort")

        delta = _apply_component_movement(payload.movement_type, payload.quantity,
                                          payload.adjustment_dir)
        before_current  = int(component.get("current_stock",  0))
        before_reserved = int(component.get("reserved_stock", 0))
        new_current     = before_current  + delta["current_delta"]
        new_reserved    = before_reserved + delta["reserved_delta"]

        # ── Pre-flight validation (based on anticipated post-write values) ────
        if new_current < 0:
            raise HTTPException(400,
                f"Movement would take current_stock negative "
                f"({before_current} → {new_current})")
        if new_reserved < 0:
            raise HTTPException(400,
                f"Movement would take reserved_stock negative "
                f"({before_reserved} → {new_reserved})")
        if new_reserved > new_current:
            raise HTTPException(400,
                f"Movement would over-reserve: reserved_stock ({new_reserved}) "
                f"> current_stock ({new_current})")

        now = now_iso()

        # ── Atomic $inc with concurrency guard ────────────────────────────────
        # The match filter pins current_stock and reserved_stock to exactly the
        # values we read. If a concurrent writer has already modified them,
        # MongoDB won't match the document → modified_count == 0 → retry.
        match_filter = {
            "_id":            component["_id"],
            "current_stock":  before_current,
            "reserved_stock": before_reserved,
        }
        inc_doc: dict = {}
        if delta["current_delta"]  != 0: inc_doc["current_stock"]  = delta["current_delta"]
        if delta["reserved_delta"] != 0: inc_doc["reserved_stock"] = delta["reserved_delta"]

        res = await db.component_master.update_one(
            match_filter,
            {
                "$inc": inc_doc,
                "$set": {"updated_at": now},
            } if inc_doc else {"$set": {"updated_at": now}},
        )

        if res.modified_count == 0:
            if attempt < MAX_RETRIES - 1:
                # Contention detected — brief yield then re-read and retry
                await asyncio.sleep(0.05 * (attempt + 1))
                continue
            raise HTTPException(
                409,
                "Concurrent modification detected on component_master after "
                f"{MAX_RETRIES} retries. Please retry the movement."
            )

        # ── Success: write the audit ledger row ───────────────────────────────
        ledger = {
            "component_id":    component["_id"],
            "component_code":  component.get("component_code", ""),
            "component_name":  component.get("component_name", ""),
            "color":           component.get("color", ""),
            "size":            component.get("size", ""),
            "movement_type":   payload.movement_type,
            "quantity":        int(payload.quantity),
            "current_delta":   delta["current_delta"],
            "reserved_delta":  delta["reserved_delta"],
            "current_before":  before_current,
            "current_after":   new_current,
            "reserved_before": before_reserved,
            "reserved_after":  new_reserved,
            "reference_type":  payload.reference_type or "manual",
            "reference_id":    payload.reference_id or "",
            "style_id":        oid(payload.style_id) if payload.style_id else None,
            "notes":           (payload.notes or "").strip(),
            "created_at":      now,
            "by":              user_email,
        }
        res_l = await db.component_stock_movements.insert_one(ledger)
        ledger["_id"] = res_l.inserted_id

        await log_activity(
            "MOVEMENT", "component",
            f"{component.get('component_code')} "
            f"({component.get('color','') or '—'}/{component.get('size','') or '—'}): "
            f"{payload.movement_type} x {payload.quantity} "
            f"→ stock={new_current}, reserved={new_reserved}",
            user_email,
        )
        return {
            "ledger":    stringify(ledger),
            "component": _serialize_component({
                **component,
                "current_stock":  new_current,
                "reserved_stock": new_reserved,
                "updated_at":     now,
            }),
        }

    # Unreachable — the loop always either returns or raises above.
    raise HTTPException(409, "Component movement failed after retries")


# ── Endpoints ──────────────────────────────────────────────────────

@api.get("/components")
async def list_components(
    request: Request,
    code:       Optional[str] = None,
    category:   Optional[str] = None,
    color:      Optional[str] = None,
    size:       Optional[str] = None,
    active:     Optional[bool] = None,
    low_stock:  Optional[bool] = None,
    search:     Optional[str] = None,
):
    """Return a flat list of component rows. UI groups them by component_code
    (each group renders as a color x size matrix)."""
    await get_current_user(request)
    q: dict = {}
    if code:     q["component_code"] = code
    if category: q["component_category"] = category
    if color:    q["color"] = color
    if size:     q["size"] = size
    if active is not None: q["active"] = active
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"component_code": rx}, {"component_name": rx}, {"vendor": rx}]

    rows = await db.component_master.find(q).sort([("component_code", 1), ("color", 1), ("size", 1)]).to_list(10000)
    result = [_serialize_component(r) for r in rows]
    if low_stock:
        # a row is "low" when available_stock <= minimum_stock (and minimum_stock > 0)
        result = [r for r in result
                  if int(r.get("minimum_stock", 0)) > 0
                  and int(r.get("available_stock", 0)) <= int(r.get("minimum_stock", 0))]
    return result


@api.get("/components/size-matrix/{component_code}")
async def get_component_size_matrix(component_code: str, request: Request):
    """Return a unified color × size matrix sub-document for a single component code.

    Every color that has at least one stock row is included. All STANDARD_SIZES
    (36–41) are guaranteed present in each color column, zero-filled when no
    row exists for that (color, size) pair. This is the canonical representation
    for the matrix UI and for B2B / online BOM allocation screens.

    Response shape:
    {
      "component_code": "...",
      "component_name": "...",
      "standard_sizes": ["36","37","38","39","40","41"],
      "colors":         ["Black", "Tan", ...],
      "matrix": {
        "Black": { "36": {"qty": 12, "reserved": 2}, "37": {...}, ... },
        "Tan":   { "36": {"qty":  0, "reserved": 0}, ... },
      },
      "flat_rows": [ ... ],
    }
    """
    await get_current_user(request)
    rows = await db.component_master.find(
        {"component_code": component_code}
    ).sort([("color", 1), ("size", 1)]).to_list(10000)

    if not rows:
        raise HTTPException(404, f"No components found with code '{component_code}'")

    serialized = [_serialize_component(r) for r in rows]
    matrix = _build_size_matrix_pivot(
        serialized,
        qty_field="current_stock",
        reserved_field="reserved_stock",
    )

    # Collect all distinct sizes that appear in the data, merged with STANDARD_SIZES
    all_sizes = sorted(
        set(STANDARD_SIZES) | {str(r.get("size") or "") for r in serialized if r.get("size")},
        key=lambda x: (int(x) if x.isdigit() else 9999, x),
    )

    sample = rows[0]
    return {
        "component_code":     component_code,
        "component_name":     sample.get("component_name", ""),
        "component_category": sample.get("component_category", ""),
        "unit":               sample.get("unit", "pair"),
        "standard_sizes":     STANDARD_SIZES,
        "all_sizes":          all_sizes,
        "colors":             sorted(matrix.keys()),
        "matrix":             matrix,
        "flat_rows":          serialized,
    }


@api.post("/components")
async def create_component(payload: ComponentIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    now = now_iso()
    doc = {
        **payload.model_dump(),
        "reserved_stock": 0,
        "created_at":     now,
        "updated_at":     now,
        "created_by":     u["email"],
    }
    # Enforce non-negative counters
    if int(doc["current_stock"]) < 0:
        raise HTTPException(400, "current_stock must be >= 0")
    try:
        res = await db.component_master.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409,
            f"A component with code='{payload.component_code}', color='{payload.color or ''}', "
            f"size='{payload.size or ''}' already exists")
    doc["_id"] = res.inserted_id

    # If we're given a non-zero opening stock, write a ledger row so the audit trail is complete
    if int(payload.current_stock) > 0:
        opening = ComponentMovementIn(
            component_id=str(res.inserted_id),
            movement_type="purchase_in",
            quantity=int(payload.current_stock),
            reference_type="opening_balance",
            notes="Opening balance at row creation",
        )
        # We just inserted so read back the row and record the movement in an idempotent way.
        # But the movement helper expects the "before" values; since the row already has
        # current_stock set to opening, temporarily rewind before applying.
        rewound = {**doc, "current_stock": 0, "reserved_stock": 0}
        # Rewind on DB too, so helper's write of new_current computes correctly
        await db.component_master.update_one({"_id": res.inserted_id},
            {"$set": {"current_stock": 0, "reserved_stock": 0}})
        await _record_component_movement(rewound, opening, u["email"])

    fresh = await db.component_master.find_one({"_id": res.inserted_id})
    await log_activity("CREATE", "component",
        f"{payload.component_code} ({payload.color or '—'}/{payload.size or '—'}) created",
        u["email"])
    return _serialize_component(fresh)


@api.put("/components/{cid}")
async def update_component(cid: str, payload: ComponentMasterUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = await db.component_master.find_one({"_id": oid(cid)})
    if not doc:
        raise HTTPException(404, "Component not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        return _serialize_component(doc)
    update["updated_at"] = now_iso()
    await db.component_master.update_one({"_id": doc["_id"]}, {"$set": update})
    await log_activity("UPDATE", "component",
        f"{doc['component_code']} metadata updated: {', '.join(update.keys())}", u["email"])
    return _serialize_component(await db.component_master.find_one({"_id": doc["_id"]}))


@api.delete("/components/{cid}")
async def deactivate_component(cid: str, request: Request):
    """Soft-delete a component master row.

    Refuses if the row has non-zero stock (zero out via adjustment first) or if
    there are active style_component_mapping (BOM) rows referencing this component
    — those would become orphaned and corrupt downstream costing / planning.

    On success:
      • Sets component_master.active = False
      • Sets active=False on all style_component_mapping rows for this component
        (cascade deactivation of the BOM links)
      • Writes an audit log entry
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = await db.component_master.find_one({"_id": oid(cid)})
    if not doc:
        raise HTTPException(404, "Component not found")

    # ── Block 1: refuse if non-zero stock ─────────────────────────────────────
    if int(doc.get("current_stock", 0)) > 0 or int(doc.get("reserved_stock", 0)) > 0:
        raise HTTPException(400,
            "Cannot delete: component has non-zero stock. Zero out via an adjustment movement first.")

    # ── Block 2: refuse if active BOM (style_component_mapping) links exist ───
    # These would become orphaned once the component is deactivated and would
    # produce silent cost errors on any style that references this component.
    active_bom_links = await db.style_component_mapping.find(
        {"component_id": cid, "active": True}
    ).to_list(200)

    if active_bom_links:
        # Collect the style codes for a helpful error message
        style_codes = []
        for link in active_bom_links:
            style_doc = await db.styles.find_one({"_id": ObjectId(link["style_id"])}, {"code": 1})
            style_codes.append((style_doc or {}).get("code", link["style_id"]))
        raise HTTPException(
            409,
            f"Cannot deactivate component '{doc['component_code']}': "
            f"it is referenced in active BOM links for {len(active_bom_links)} style(s): "
            f"{', '.join(style_codes)}. Remove the BOM links first."
        )

    now = now_iso()

    # ── Cascade: deactivate all BOM mapping rows for this component ───────────
    cascade_result = await db.style_component_mapping.update_many(
        {"component_id": cid},
        {"$set": {"active": False, "updated_at": now}},
    )

    # ── Soft-delete the master row ────────────────────────────────────────────
    await db.component_master.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "active":     False,
            "deleted_at": now,
            "updated_at": now,
        }}
    )
    await log_activity(
        "DELETE", "component",
        f"{doc['component_code']} ({doc.get('color','')}/{doc.get('size','')}) deactivated; "
        f"{cascade_result.modified_count} BOM mapping(s) also deactivated.",
        u["email"],
    )
    return {
        "ok":                     True,
        "id":                     cid,
        "bom_links_deactivated":  cascade_result.modified_count,
    }


@api.post("/components/bulk-matrix")
async def create_component_bulk_matrix(payload: ComponentBulkMatrix, request: Request):
    """Create or extend multiple (color, size) rows for one component in one shot.

    Two-mode behaviour so the "Add Stock in Bulk" drawer works whether the
    user is seeding a brand-new component or topping up existing rows:

      • BRAND-NEW (color, size) row → insert the master row and record an
        opening-balance movement for `opening_qty` (if > 0).
      • EXISTING (color, size) row  → the master row is already there, so
        we skip the master insert (correctly) BUT we still record a
        purchase_in movement for the entered quantity when > 0. Silently
        dropping the entered qty was the "size matrix not populating"
        bug — the user's typed values would vanish because the endpoint
        treated every duplicate as a full no-op.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    now = now_iso()
    created, updated, skipped = 0, 0, 0
    results = []
    for row in payload.rows:
        color = str(row.get("color", "") or "").strip()
        size  = str(row.get("size",  "") or "").strip()
        opening = int(row.get("opening_qty") or 0)
        if opening < 0:
            results.append({"color": color, "size": size, "status": "invalid_qty"})
            continue
        # 1. Try to insert the master row (idempotent by (code, color, size))
        try:
            doc = {
                "component_code":     payload.component_code,
                "component_name":     payload.component_name,
                "component_category": payload.component_category,
                "color":              color,
                "size":               size,
                "vendor":             payload.vendor or "",
                "unit":               payload.unit or "pair",
                "current_stock":      0,
                "reserved_stock":     0,
                "reorder_level":      int(payload.reorder_level),
                "minimum_stock":      int(payload.minimum_stock),
                "lead_time_days":     int(payload.lead_time_days),
                "active":             True,
                "created_at":         now,
                "updated_at":         now,
                "created_by":         u["email"],
            }
            res = await db.component_master.insert_one(doc)
            doc["_id"] = res.inserted_id
            if opening > 0:
                await _record_component_movement(
                    doc,
                    ComponentMovementIn(
                        component_id=str(res.inserted_id),
                        movement_type="purchase_in",
                        quantity=opening,
                        reference_type="opening_balance",
                        notes="Opening balance from bulk matrix",
                    ),
                    u["email"],
                )
            created += 1
            results.append({"color": color, "size": size, "status": "created", "qty": opening})
        except DuplicateKeyError:
            # 2. Row already exists — that's expected in "extend" mode.
            # If the user entered a qty, apply it as a purchase_in movement
            # so their input isn't silently dropped.
            if opening > 0:
                existing = await db.component_master.find_one({
                    "component_code": payload.component_code,
                    "color":          color,
                    "size":           size,
                })
                if existing:
                    try:
                        await _record_component_movement(
                            existing,
                            ComponentMovementIn(
                                component_id=str(existing["_id"]),
                                movement_type="purchase_in",
                                quantity=opening,
                                reference_type="bulk_matrix_topup",
                                notes="Stock added via bulk matrix (extend mode)",
                            ),
                            u["email"],
                        )
                        updated += 1
                        results.append({
                            "color": color, "size": size,
                            "status": "stock_added", "qty": opening,
                        })
                    except HTTPException as he:
                        results.append({
                            "color": color, "size": size,
                            "status": "movement_failed",
                            "error":  str(he.detail),
                        })
                else:
                    # Race: DuplicateKeyError from a UNIQUE index that
                    # doesn't correspond to (code,color,size). Unlikely
                    # given the index definition, but keep a safe branch.
                    skipped += 1
                    results.append({"color": color, "size": size, "status": "exists"})
            else:
                # Existing row, no qty entered → truly a no-op.
                skipped += 1
                results.append({"color": color, "size": size, "status": "exists"})
    await log_activity(
        "BULK", "component",
        f"{payload.component_code}: {created} rows created, {updated} rows topped-up, {skipped} skipped",
        u["email"],
    )
    return {
        "created":  created,
        "updated":  updated,   # rows already existed and got a stock top-up movement
        "skipped":  skipped,
        "results":  results,
    }


@api.post("/components/movements")
async def post_component_movement(payload: ComponentMovementIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    comp = await db.component_master.find_one({"_id": oid(payload.component_id)})
    if not comp:
        raise HTTPException(404, "Component not found")
    return await _record_component_movement(comp, payload, u["email"])


@api.get("/components/movements")
async def list_component_movements(
    request: Request,
    component_id:  Optional[str] = None,
    movement_type: Optional[str] = None,
    style_id:      Optional[str] = None,
    reference_type: Optional[str] = None,
    limit: int = 500,
):
    await get_current_user(request)
    q: dict = {}
    if component_id:  q["component_id"] = oid(component_id)
    if movement_type: q["movement_type"] = movement_type
    if style_id:      q["style_id"] = oid(style_id)
    if reference_type: q["reference_type"] = reference_type
    rows = await db.component_stock_movements.find(q).sort("created_at", -1).to_list(min(limit, 2000))
    out = []
    for r in rows:
        s = stringify(r)
        # Also stringify the embedded ObjectId fields we set with helpers
        if isinstance(r.get("style_id"), ObjectId):
            s["style_id"] = str(r["style_id"])
        if isinstance(r.get("component_id"), ObjectId):
            s["component_id"] = str(r["component_id"])
        out.append(s)
    return out


# ---------- Style ⇄ Component BOM mapping ----------

@api.get("/style-component-mapping")
async def list_style_component_mapping(
    request: Request,
    style_id:     Optional[str] = None,
    component_id: Optional[str] = None,
):
    await get_current_user(request)
    q: dict = {}
    if style_id:     q["style_id"] = oid(style_id)
    if component_id: q["component_id"] = oid(component_id)
    rows = await db.style_component_mapping.find(q).to_list(5000)

    # Denormalise the component + style basics for display
    comp_ids  = list({r["component_id"] for r in rows if r.get("component_id")})
    style_ids = list({r["style_id"]     for r in rows if r.get("style_id")})
    comps  = {c["_id"]: c for c in await db.component_master.find({"_id": {"$in": comp_ids}}).to_list(5000)}
    styles = {s["_id"]: s for s in await db.styles.find({"_id": {"$in": style_ids}}).to_list(5000)}

    out = []
    for r in rows:
        s = stringify(r)
        s["style_id"]     = str(r.get("style_id"))     if r.get("style_id") else None
        s["component_id"] = str(r.get("component_id")) if r.get("component_id") else None
        comp  = comps.get(r.get("component_id"))
        style = styles.get(r.get("style_id"))
        if comp:
            s["component_code"]     = comp.get("component_code", "")
            s["component_name"]     = comp.get("component_name", "")
            s["component_category"] = comp.get("component_category", "")
            s["component_color"]    = comp.get("color", "")
            s["component_size"]     = comp.get("size", "")
            s["current_stock"]      = int(comp.get("current_stock", 0))
            s["reserved_stock"]     = int(comp.get("reserved_stock", 0))
            s["available_stock"]    = s["current_stock"] - s["reserved_stock"]
        if style:
            s["style_code"] = style.get("code", "")
            s["style_name"] = style.get("name", "")
        out.append(s)
    # sort: style_code then component category then component_code
    out.sort(key=lambda x: (x.get("style_code",""), x.get("component_category",""), x.get("component_code","")))
    return out


@api.post("/style-component-mapping")
async def create_style_component_mapping(payload: StyleComponentMappingIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    style = await db.styles.find_one({"_id": oid(payload.style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    comp = await db.component_master.find_one({"_id": oid(payload.component_id)})
    if not comp:
        raise HTTPException(404, "Component not found")
    now = now_iso()
    doc = {
        "style_id":           oid(payload.style_id),
        "component_id":       oid(payload.component_id),
        "component_category": comp.get("component_category", ""),   # denormalised for readability
        "quantity_per_pair":  float(payload.quantity_per_pair),
        "wastage_percent":    float(payload.wastage_percent),
        "active":             bool(payload.active),
        "created_at":         now,
        "updated_at":         now,
        "created_by":         u["email"],
    }
    try:
        res = await db.style_component_mapping.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409,
            f"Style '{style['code']}' already has component '{comp['component_code']}' mapped.")
    doc["_id"] = res.inserted_id
    await log_activity("CREATE", "style_component_mapping",
        f"{style['code']} ← {comp['component_code']} @ {payload.quantity_per_pair}/pair", u["email"])
    s = stringify(doc)
    s["style_id"]     = str(doc["style_id"])
    s["component_id"] = str(doc["component_id"])
    return s


@api.put("/style-component-mapping/{mid}")
async def update_style_component_mapping(mid: str, payload: StyleComponentMappingUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = await db.style_component_mapping.find_one({"_id": oid(mid)})
    if not doc:
        raise HTTPException(404, "Mapping not found")
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        return {"ok": True}
    update["updated_at"] = now_iso()
    await db.style_component_mapping.update_one({"_id": doc["_id"]}, {"$set": update})
    await log_activity("UPDATE", "style_component_mapping",
        f"Mapping {mid} updated: {', '.join(update.keys())}", u["email"])
    return {"ok": True}


@api.delete("/style-component-mapping/{mid}")
async def delete_style_component_mapping(mid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = await db.style_component_mapping.find_one({"_id": oid(mid)})
    if not doc:
        raise HTTPException(404, "Mapping not found")
    await db.style_component_mapping.delete_one({"_id": doc["_id"]})
    await log_activity("DELETE", "style_component_mapping",
        f"Mapping {mid} deleted", u["email"])
    return {"ok": True}


# ---------- FINISHED GOODS INVENTORY & RESERVATION ENGINE ----------

@api.get("/fg-inventory")
async def list_fg_inventory(
    request: Request,
    style_id: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: Optional[bool] = None
):
    await get_current_user(request)
    query = {}
    if style_id:
        try:
            query["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if color:
        query["color"] = color
    if size:
        query["size"] = size
    
    if search:
        search_regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"style_code": search_regex},
            {"color": search_regex},
            {"size": search_regex}
        ]
    
    docs = await db.fg_inventory.find(query).to_list(2000)
    out = []
    for d in docs:
        d = stringify(d)
        ready = d.get("ready_stock_qty", 0)
        reserved = d.get("reserved_qty", 0)
        damaged = d.get("damaged_qty", 0)
        liq = d.get("liquidation_qty", 0)
        min_stock = d.get("min_stock_level", 25)
        
        available = ready - reserved - damaged - liq
        d["available_qty"] = available
        # Per Phase-2 spec: low_stock triggers on READY vs MIN, not AVAILABLE vs MIN
        d["is_low_stock"] = ready < min_stock
        
        if low_stock is not None:
            if low_stock and not d["is_low_stock"]:
                continue
            if not low_stock and d["is_low_stock"]:
                continue
        
        out.append(d)
    return out


# ---------- FG Movement Engine (Phase 2) ----------
# Map movement_type → dict of {fg_inventory_field: signed_delta_multiplier}.
# `quantity` from the request is multiplied by these to produce the delta applied to each field.
_MOVEMENT_DELTAS = {
    "production_in":     {"ready_stock_qty":  1},
    "reserved":          {"reserved_qty":     1},
    "unreserved":        {"reserved_qty":    -1},
    "dispatched":        {"ready_stock_qty": -1, "reserved_qty": -1},
    "return_in":         {"return_qty":       1},
    "return_restocked":  {"return_qty":      -1, "ready_stock_qty": 1},
    "return_damaged":    {"return_qty":      -1, "damaged_qty":    1},
    "liquidation_out":   {"ready_stock_qty": -1, "liquidation_qty": 1},
    # "adjustment" is dynamic — applied via payload.adjustment_field
}


async def _get_or_create_fg_row(style_id: str, color: str, size: str):
    """Return the fg_inventory row for (style_id, color, size). Auto-create at zero if absent."""
    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    if not style:
        raise HTTPException(404, f"Style '{style_id}' not found")
    row = await db.fg_inventory.find_one({
        "style_id": ObjectId(style_id),
        "color": color,
        "size":  size,
    })
    if row:
        return row
    doc = {
        "style_id":         ObjectId(style_id),
        "style_code":       style["code"],
        "color":            color,
        "size":             size,
        "ready_stock_qty":  0,
        "reserved_qty":     0,
        "in_transit_qty":   0,
        "return_qty":       0,
        "damaged_qty":      0,
        "liquidation_qty":  0,
        "min_stock_level":  25,
        "updated_at":       now_iso(),
    }
    try:
        res = await db.fg_inventory.insert_one(doc)
        doc["_id"] = res.inserted_id
        return doc
    except DuplicateKeyError:
        return await db.fg_inventory.find_one({
            "style_id": ObjectId(style_id), "color": color, "size": size,
        })


async def _apply_movement(payload: "FgStockMovementIn", user_email: str, skip_location_sync: bool = False):
    """Single write path to fg_inventory. Creates a ledger row and updates the inventory
    row atomically. Blocks any movement that would push a field below zero.

    Also, for movement_type in {"reserved", "unreserved", "dispatched"} it maintains the
    inventory_reservations collection linked via `online_order_id`.
    """
    row = await _get_or_create_fg_row(payload.style_id, payload.color, payload.size)

    # ── Build the delta dict (field → signed change) ────────────────────
    if payload.movement_type == "adjustment":
        if not payload.adjustment_field:
            raise HTTPException(400, "adjustment_field is required for movement_type='adjustment'")
        # For adjustment, `quantity` may be negative (raw delta)
        delta = {payload.adjustment_field: int(payload.quantity)}
    else:
        if payload.quantity <= 0:
            raise HTTPException(400, "quantity must be > 0 for this movement_type")
        multipliers = _MOVEMENT_DELTAS.get(payload.movement_type)
        if multipliers is None:
            raise HTTPException(400, f"Unsupported movement_type '{payload.movement_type}'")
        delta = {f: m * int(payload.quantity) for f, m in multipliers.items()}

    # ── Validate no field goes below zero ───────────────────────────────
    for field, d in delta.items():
        current = int(row.get(field, 0))
        if current + d < 0:
            raise HTTPException(
                400,
                f"Movement would push {field} below zero (current {current}, delta {d}). "
                f"Movement blocked."
            )

    # ── Atomic $inc with concurrency guard (match on current values) ────
    match_filter = {"_id": row["_id"]}
    for field in delta:
        match_filter[field] = int(row.get(field, 0))

    update = {
        "$inc": {field: int(d) for field, d in delta.items()},
        "$set": {"updated_at": now_iso()},
    }
    res = await db.fg_inventory.update_one(match_filter, update)
    if res.modified_count == 0:
        raise HTTPException(
            409,
            "Concurrent modification detected on fg_inventory. Please retry the movement."
        )

    # ── Post the ledger row ─────────────────────────────────────────────
    mv_doc = {
        "style_id":       ObjectId(payload.style_id),
        "style_code":     row.get("style_code", ""),
        "color":          payload.color,
        "size":           payload.size,
        "movement_type":  payload.movement_type,
        "quantity":       int(payload.quantity),
        "reference_type": payload.reference_type,
        "reference_id":   payload.reference_id or "",
        "notes":          payload.notes or "",
        "delta":          {k: int(v) for k, v in delta.items()},
        "created_at":     now_iso(),
        "by":             user_email,
    }
    if payload.movement_type == "adjustment":
        mv_doc["adjustment_field"] = payload.adjustment_field
    mv_res = await db.fg_stock_movements.insert_one(mv_doc)
    mv_doc["_id"] = mv_res.inserted_id

    # ── Maintain inventory_reservations for reserve / unreserve / dispatch ──
    if payload.movement_type == "reserved" and payload.online_order_id:
        await db.inventory_reservations.insert_one({
            "style_id":        ObjectId(payload.style_id),
            "style_code":      row.get("style_code", ""),
            "color":           payload.color,
            "size":            payload.size,
            "qty":             int(payload.quantity),
            "online_order_id": payload.online_order_id,
            "reserved_at":     now_iso(),
            "released_at":     None,
            "status":          "active",
        })
    elif payload.movement_type == "unreserved" and payload.online_order_id:
        await db.inventory_reservations.update_many(
            {
                "online_order_id": payload.online_order_id,
                "style_id":        ObjectId(payload.style_id),
                "color":           payload.color,
                "size":            payload.size,
                "status":          "active",
            },
            {"$set": {"status": "released", "released_at": now_iso()}}
        )
    elif payload.movement_type == "dispatched" and payload.online_order_id:
        await db.inventory_reservations.update_many(
            {
                "online_order_id": payload.online_order_id,
                "style_id":        ObjectId(payload.style_id),
                "color":           payload.color,
                "size":            payload.size,
                "status":          "active",
            },
            {"$set": {"status": "fulfilled", "released_at": now_iso()}}
        )

    updated = await db.fg_inventory.find_one({"_id": row["_id"]})
    updated = stringify(updated)
    u_ready = updated.get("ready_stock_qty", 0)
    u_res   = updated.get("reserved_qty", 0)
    u_dmg   = updated.get("damaged_qty", 0)
    u_liq   = updated.get("liquidation_qty", 0)
    u_min   = updated.get("min_stock_level", 25)
    updated["available_qty"] = u_ready - u_res - u_dmg - u_liq
    updated["is_low_stock"]  = u_ready < u_min

    # ── Warehouse location sync (Phase WMS) ─────────────────────────────
    location_result = None
    if not skip_location_sync:
        try:
            location_result = await _sync_warehouse_locations(payload, user_email)
        except Exception as _wms_err:
            log.warning(f"WMS sync failed for {payload.movement_type}: {_wms_err}")

    # Stringify movement doc for JSON response
    mv_out = stringify(mv_doc)
    return {"inventory": updated, "movement": mv_out, "warehouse": location_result}


@api.post("/fg-inventory/movements")
async def create_fg_movement(request: Request, payload: FgStockMovementIn):
    """Single write path to fg_inventory. Creates a movement ledger row and atomically
    updates the inventory row. Auto-creates the fg_inventory row at zero if none exists.
    Blocks any movement that would push a quantity below zero.
    """
    u = await get_current_user(request)
    require_roles("admin", "manager", "production")(u)
    return await _apply_movement(payload, u["email"])


# ---------- Bulk FG movement flows (matrix entry + CSV import) ----------

async def _resolve_style_by_code(code: str):
    """Resolve a style_code → style ObjectId. Returns None if not found."""
    if not code:
        return None
    doc = await db.styles.find_one({"code": code.strip()})
    return doc


@api.post("/fg-inventory/bulk-movements")
async def bulk_fg_movements(request: Request, payload: dict):
    """Apply many movements in one request. Best-effort: each row is validated and
    applied independently; failures are reported per-row and don't abort the batch.

    Body:
    {
      "movements": [ FgStockMovementIn ... ],
      "dry_run":  false        # optional; if true, only validate (still allocates
                               # nothing) — implemented as a soft check by applying
                               # then aborting? kept simple: just runs live for now.
    }
    """
    u = await get_current_user(request)
    require_roles("admin", "manager", "production")(u)

    movements = (payload or {}).get("movements") or []
    if not isinstance(movements, list) or not movements:
        raise HTTPException(400, "movements must be a non-empty list")
    if len(movements) > 2000:
        raise HTTPException(400, "Batch too large — max 2000 movements per request")

    results = []
    ok_count  = 0
    err_count = 0
    for idx, row in enumerate(movements):
        try:
            mv = FgStockMovementIn(**row)
            out = await _apply_movement(mv, u["email"])
            results.append({
                "index":     idx,
                "style_id":  mv.style_id,
                "color":     mv.color,
                "size":      mv.size,
                "movement":  mv.movement_type,
                "ok":        True,
                "delta":     out["movement"].get("delta"),
            })
            ok_count += 1
        except HTTPException as he:
            results.append({
                "index":    idx,
                "row":      row,
                "ok":       False,
                "error":    str(he.detail),
                "status":   he.status_code,
            })
            err_count += 1
        except Exception as e:
            results.append({
                "index":    idx,
                "row":      row,
                "ok":       False,
                "error":    str(e),
                "status":   500,
            })
            err_count += 1

    return {
        "total":    len(movements),
        "success":  ok_count,
        "failed":   err_count,
        "results":  results,
    }


@api.post("/fg-inventory/import-csv", dependencies=[Depends(upload_rate_limiter)])
async def import_fg_stock_csv(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="If true, only preview — nothing is written."),
):
    """Import many FG stock movements from a CSV file.

    Expected columns (case-insensitive, order-independent):
      style_code (or style_id)   REQUIRED
      color                       REQUIRED
      size                        REQUIRED
      quantity                    REQUIRED (int)
      movement_type               optional, default "production_in"
      reference_type              optional, default "manual"
      reference_id                optional
      notes                       optional
      adjustment_field            required only if movement_type == "adjustment"
      online_order_id             optional (used by reserved/unreserved/dispatched)

    Rows with quantity == 0 are SKIPPED silently.

    On dry_run=true, no writes happen — the response includes validation errors
    and a per-row preview so the frontend can confirm before committing.
    """
    u = await get_current_user(request)
    require_roles("admin", "manager", "production")(u)

    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    import csv as _csv, io as _io
    # Sniff encoding — default to utf-8-sig to strip BOMs
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = _csv.DictReader(_io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV appears to be empty or unreadable")

    # Normalise header names to snake_case_lower for easy lookup
    norm_map = {(h or "").strip().lower().replace(" ", "_"): h for h in reader.fieldnames}

    def col(row, key):
        h = norm_map.get(key)
        return (row.get(h, "") if h else "").strip() if isinstance(row.get(h, ""), str) else row.get(h, "")

    parsed = []
    errors = []
    style_code_cache = {}   # code → style_id str

    for line_no, r in enumerate(reader, start=2):  # header row is line 1
        code = col(r, "style_code")
        sid  = col(r, "style_id")
        color = col(r, "color")
        size  = str(col(r, "size") or "").strip()
        try:
            qty = int(float(str(col(r, "quantity") or "0")))
        except Exception:
            qty = None
        mv_type = (col(r, "movement_type") or "production_in").strip().lower()
        ref_type = (col(r, "reference_type") or "manual").strip().lower()
        ref_id  = col(r, "reference_id") or ""
        notes   = col(r, "notes") or ""
        adj_fld = col(r, "adjustment_field") or None
        oo_id   = col(r, "online_order_id") or None

        # Validate & resolve
        if not (code or sid):
            errors.append({"line": line_no, "error": "Missing style_code / style_id"})
            continue
        if not color:
            errors.append({"line": line_no, "error": "Missing color"})
            continue
        if not size:
            errors.append({"line": line_no, "error": "Missing size"})
            continue
        if qty is None:
            errors.append({"line": line_no, "error": "quantity is not a valid number"})
            continue
        if qty == 0:
            continue  # silently skip

        resolved_sid = sid
        if not resolved_sid:
            if code in style_code_cache:
                resolved_sid = style_code_cache[code]
            else:
                sdoc = await _resolve_style_by_code(code)
                if not sdoc:
                    errors.append({"line": line_no, "error": f"Unknown style_code '{code}'"})
                    continue
                resolved_sid = str(sdoc["_id"])
                style_code_cache[code] = resolved_sid

        row = {
            "style_id":       resolved_sid,
            "color":          color,
            "size":           size,
            "movement_type":  mv_type,
            "quantity":       qty,
            "reference_type": ref_type if ref_type in ("manual","job","online_order","return") else "manual",
            "reference_id":   ref_id,
            "notes":          notes,
        }
        if mv_type == "adjustment":
            if not adj_fld:
                errors.append({"line": line_no, "error": "adjustment_field is required for movement_type='adjustment'"})
                continue
            row["adjustment_field"] = adj_fld
        if oo_id:
            row["online_order_id"] = oo_id
        row["_line"] = line_no
        parsed.append(row)

    if dry_run:
        return {
            "dry_run": True,
            "parsed":  parsed,
            "errors":  errors,
            "summary": {
                "total_rows_seen":  len(parsed) + len(errors),
                "valid":            len(parsed),
                "invalid":          len(errors),
            },
        }

    # Commit: apply each parsed row through the movement engine
    results = []
    ok = 0
    err = 0
    for row in parsed:
        line = row.pop("_line", None)
        try:
            mv = FgStockMovementIn(**row)
            out = await _apply_movement(mv, u["email"])
            results.append({"line": line, "ok": True, "delta": out["movement"].get("delta")})
            ok += 1
        except HTTPException as he:
            results.append({"line": line, "ok": False, "error": str(he.detail)})
            err += 1
        except Exception as e:
            results.append({"line": line, "ok": False, "error": str(e)})
            err += 1

    return {
        "committed": True,
        "summary": {
            "total_rows_seen": len(parsed) + len(errors),
            "attempted":       len(parsed),
            "success":         ok,
            "failed":          err,
            "parse_errors":    len(errors),
        },
        "results":       results,
        "parse_errors":  errors,
    }


@api.get("/fg-inventory/csv-template")
async def download_fg_csv_template(request: Request):
    """Return a ready-to-fill CSV template with headers + one commented example row."""
    await get_current_user(request)
    csv_text = (
        "style_code,color,size,movement_type,quantity,reference_type,reference_id,notes,adjustment_field,online_order_id\n"
        "# Fill one row per (style, color, size). Leave quantity blank / 0 to skip a row.\n"
        "# movement_type defaults to production_in (adds ready stock). Other types:\n"
        "#   reserved, unreserved, dispatched, return_in, return_restocked,\n"
        "#   return_damaged, liquidation_out, adjustment (needs adjustment_field).\n"
        "33-1065-ME,SILVER,36,production_in,10,manual,,First lot from production,,\n"
        "33-1065-ME,SILVER,37,production_in,20,manual,,,,\n"
        "33-1065-ME,GOLD,38,production_in,30,manual,,,,\n"
    )
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fg_stock_template.csv"'},
    )


@api.get("/fg-inventory/movements")
async def list_fg_movements(
    request: Request,
    style_id: Optional[str]      = None,
    movement_type: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str]  = None,
    from_date: Optional[str]     = None,
    to_date: Optional[str]       = None,
    limit: int                    = 500,
):
    """Ledger view of every fg_inventory movement. Ordered newest first."""
    await get_current_user(request)
    query: dict = {}
    if style_id:
        try:
            query["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if movement_type:
        query["movement_type"] = movement_type
    if reference_type:
        query["reference_type"] = reference_type
    if reference_id:
        query["reference_id"] = reference_id
    if from_date or to_date:
        date_q: dict = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        query["created_at"] = date_q
    docs = await db.fg_stock_movements.find(query).sort("created_at", -1).to_list(int(limit))
    return [stringify(d) for d in docs]


@api.get("/fg-inventory/by-style/{style_id}")
async def get_fg_inventory_by_style(request: Request, style_id: str):
    """Full color × size breakdown for a single style, with computed available_qty
    and low-stock flag per row. Non-breaking sibling of /fg-inventory/{id}.
    """
    await get_current_user(request)
    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    rows = await db.fg_inventory.find({"style_id": ObjectId(style_id)}).to_list(500)
    out_rows = []
    colors: set = set()
    sizes:  set = set()
    for r in rows:
        r = stringify(r)
        ready = int(r.get("ready_stock_qty", 0))
        res   = int(r.get("reserved_qty",   0))
        dmg   = int(r.get("damaged_qty",    0))
        liq   = int(r.get("liquidation_qty", 0))
        mn    = int(r.get("min_stock_level", 25))
        r["available_qty"] = ready - res - dmg - liq
        r["is_low_stock"]  = ready < mn
        out_rows.append(r)
        if r.get("color"): colors.add(r["color"])
        if r.get("size"):  sizes.add(r["size"])

    # Reservation drill-down: active reservations for this style
    active = await db.inventory_reservations.find({
        "style_id": ObjectId(style_id),
        "status":   "active",
    }).to_list(500)
    active_reservations = [stringify(a) for a in active]

    # Build a nested size-matrix pivot for quick UI rendering
    size_matrix = _build_size_matrix_pivot(
        out_rows,
        qty_field="ready_stock_qty",
        reserved_field="reserved_qty",
    )

    return {
        "style": {
            "id":    str(style["_id"]),
            "code":  style["code"],
            "name":  style.get("name", ""),
            "image_url":           style.get("image_url", ""),
            "image_display_url":   style.get("image_display_url", ""),
            "image_thumbnail_url": style.get("image_thumbnail_url", ""),
        },
        "rows":                out_rows,
        "colors":              sorted(colors),
        "sizes":               sorted(sizes),
        "standard_sizes":      STANDARD_SIZES,
        "size_matrix":         size_matrix,   # {color: {36: {qty, reserved}, 37: ...}}
        "active_reservations": active_reservations,
    }


@api.put("/fg-inventory/size-matrix")
async def put_fg_inventory_size_matrix(request: Request, payload: dict):
    """Bulk-seed FG ready stock via a color × size matrix in a single call.

    Accepts a matrix body and fans it out to individual production_in movements
    through _apply_movement so every write is atomic and a full ledger trail is
    created automatically.

    Body shape:
    {
      "style_id": "<ObjectId>",
      "color":    "Black",
      "movement_type": "production_in",    # optional, default production_in
      "reference_id":  "LOT-001",          # optional
      "notes":         "First lot",        # optional
      "size_matrix": {
        "36": 10,
        "37": 20,
        "38": 30,
        "39": 20,
        "40": 10,
        "41":  5
      }
    }

    Rows with quantity == 0 are silently skipped. Each successful size write
    returns its delta; failures are reported per-size without aborting the batch.
    """
    u = await get_current_user(request)
    require_roles("admin", "manager", "production")(u)

    style_id     = (payload or {}).get("style_id", "")
    color        = (payload or {}).get("color", "").strip()
    size_matrix  = (payload or {}).get("size_matrix") or {}
    mv_type      = (payload or {}).get("movement_type", "production_in").strip()
    reference_id = (payload or {}).get("reference_id", "")
    notes        = (payload or {}).get("notes", "")

    if not style_id:
        raise HTTPException(400, "style_id is required")
    if not color:
        raise HTTPException(400, "color is required")
    if not size_matrix:
        raise HTTPException(400, "size_matrix must be a non-empty {size: qty} dict")

    results = []
    ok_count  = 0
    err_count = 0

    for size_str, qty_raw in size_matrix.items():
        try:
            qty = int(float(str(qty_raw or 0)))
        except Exception:
            results.append({"size": size_str, "ok": False, "error": "quantity is not a valid number"})
            err_count += 1
            continue

        if qty == 0:
            continue  # silently skip zero-quantity cells

        try:
            mv = FgStockMovementIn(
                style_id       = style_id,
                color          = color,
                size           = str(size_str).strip(),
                movement_type  = mv_type,
                quantity       = qty,
                reference_type = "manual",
                reference_id   = reference_id or "",
                notes          = notes or f"Size-matrix bulk entry for {color}/{size_str}",
            )
            out = await _apply_movement(mv, u["email"])
            results.append({
                "size":  size_str,
                "qty":   qty,
                "ok":    True,
                "delta": out["movement"].get("delta"),
            })
            ok_count += 1
        except HTTPException as he:
            results.append({"size": size_str, "qty": qty, "ok": False, "error": str(he.detail)})
            err_count += 1
        except Exception as e:
            results.append({"size": size_str, "qty": qty, "ok": False, "error": str(e)})
            err_count += 1

    return {
        "style_id": style_id,
        "color":    color,
        "success":  ok_count,
        "failed":   err_count,
        "results":  results,
    }



@api.get("/inventory-reservations")
async def list_inventory_reservations(
    request: Request,
    online_order_id: Optional[str] = None,
    style_id: Optional[str]        = None,
    status: Optional[str]          = None,
):
    """Read-only view of the reservations ledger — which orders are holding which stock."""
    await get_current_user(request)
    query: dict = {}
    if online_order_id:
        query["online_order_id"] = online_order_id
    if style_id:
        try:
            query["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if status:
        query["status"] = status
    docs = await db.inventory_reservations.find(query).sort("reserved_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@api.get("/fg-inventory/{id}")
async def get_fg_inventory_item(request: Request, id: str):
    await get_current_user(request)
    doc = await db.fg_inventory.find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(404, "Inventory record not found")
    doc = stringify(doc)
    ready = doc.get("ready_stock_qty", 0)
    reserved = doc.get("reserved_qty", 0)
    damaged = doc.get("damaged_qty", 0)
    liq = doc.get("liquidation_qty", 0)
    min_stock = doc.get("min_stock_level", 25)
    
    doc["available_qty"] = ready - reserved - damaged - liq
    doc["is_low_stock"] = ready < min_stock
    return doc

@api.post("/fg-inventory")
async def create_fg_inventory(request: Request, payload: FgInventoryIn):
    u = await get_current_user(request)
    require_roles("admin", "manager")(u)
    
    style = await db.styles.find_one({"_id": ObjectId(payload.style_id)})
    if not style:
        raise HTTPException(400, "Style does not exist")
        
    doc = {
        "style_id": ObjectId(payload.style_id),
        "style_code": style["code"],
        "color": payload.color,
        "size": payload.size,
        "ready_stock_qty": payload.ready_stock_qty,
        "reserved_qty": payload.reserved_qty,
        "in_transit_qty": payload.in_transit_qty,
        "return_qty": payload.return_qty,
        "damaged_qty": payload.damaged_qty,
        "liquidation_qty": payload.liquidation_qty,
        "min_stock_level": payload.min_stock_level,
        "updated_at": now_iso()
    }
    try:
        res = await db.fg_inventory.insert_one(doc)
        doc["_id"] = str(res.inserted_id)
        doc["style_id"] = str(doc["style_id"])
        
        ready = doc.get("ready_stock_qty", 0)
        reserved = doc.get("reserved_qty", 0)
        damaged = doc.get("damaged_qty", 0)
        liq = doc.get("liquidation_qty", 0)
        min_stock = doc.get("min_stock_level", 25)
        
        doc["available_qty"] = ready - reserved - damaged - liq
        doc["is_low_stock"] = ready < min_stock
        return doc
    except DuplicateKeyError:
        raise HTTPException(400, "Inventory entry for this style/color/size already exists")

@api.patch("/fg-inventory/{id}")
async def update_fg_inventory(request: Request, id: str, payload: FgInventoryUpdate):
    """Config-only patch: only `min_stock_level` may be updated here. Every stock-qty
    change MUST go through POST /api/fg-inventory/movements so the ledger stays intact.
    """
    u = await get_current_user(request)
    require_roles("admin", "manager")(u)

    payload_data = payload.model_dump(exclude_unset=True)
    stock_fields = {"ready_stock_qty", "reserved_qty", "in_transit_qty",
                    "return_qty", "damaged_qty", "liquidation_qty"}
    illegal = [k for k in payload_data.keys() if k in stock_fields and payload_data[k] is not None]
    if illegal:
        raise HTTPException(
            400,
            f"Direct edits to {illegal} are forbidden. Post a movement via "
            f"POST /api/fg-inventory/movements (movement_type='adjustment', "
            f"adjustment_field='{illegal[0]}') to change stock quantities."
        )

    update_data = {k: v for k, v in payload_data.items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No fields to update")

    update_data["updated_at"] = now_iso()
    res = await db.fg_inventory.update_one(
        {"_id": ObjectId(id)},
        {"$set": update_data}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Inventory record not found")

    doc = await db.fg_inventory.find_one({"_id": ObjectId(id)})
    doc = stringify(doc)
    ready = doc.get("ready_stock_qty", 0)
    reserved = doc.get("reserved_qty", 0)
    damaged = doc.get("damaged_qty", 0)
    liq = doc.get("liquidation_qty", 0)
    min_stock = doc.get("min_stock_level", 25)

    doc["available_qty"] = ready - reserved - damaged - liq
    doc["is_low_stock"] = ready < min_stock
    return doc

@api.post("/fg-inventory/reserve")
async def reserve_stock(request: Request, payload: StockReservation):
    """Legacy convenience wrapper — routes through the movement engine."""
    u = await get_current_user(request)
    mv = FgStockMovementIn(
        style_id       = payload.style_id,
        color          = payload.color,
        size           = payload.size,
        movement_type  = "reserved",
        quantity       = payload.quantity,
        reference_type = "manual",
        reference_id   = "",
        notes          = "Legacy /reserve call",
    )
    result = await _apply_movement(mv, u["email"])
    return {"success": True, "message": f"Reserved {payload.quantity} pairs", **result}

@api.post("/fg-inventory/release")
async def release_stock(request: Request, payload: StockRelease):
    """Legacy convenience wrapper — routes through the movement engine.

    release_type == "ship"   → "dispatched" movement (decrement ready + reserved)
    release_type == "cancel" → "unreserved" movement (decrement reserved only)
    """
    u = await get_current_user(request)
    mv_type = "dispatched" if payload.release_type == "ship" else "unreserved"
    mv = FgStockMovementIn(
        style_id       = payload.style_id,
        color          = payload.color,
        size           = payload.size,
        movement_type  = mv_type,
        quantity       = payload.quantity,
        reference_type = "manual",
        reference_id   = "",
        notes          = f"Legacy /release call ({payload.release_type})",
    )
    result = await _apply_movement(mv, u["email"])
    return {"success": True, "message": f"Released {payload.quantity} pairs via {payload.release_type}", **result}


# ---------- STYLES ----------

@api.get("/styles")
async def list_styles(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    include_deleted: bool  = False,   # set ?include_deleted=true to see soft-deleted styles
):
    await get_current_user(request)
    query: dict = {}
    # ── Exclude soft-deleted styles unless explicitly requested ───────────────
    # Styles soft-deleted via DELETE /styles/{sid} have active=False + deleted_at set.
    # Normal API consumers should never see them; the include_deleted flag is an
    # admin-only audit tool.
    if not include_deleted:
        query["$or"] = [
            {"active": {"$ne": False}},   # never had active set, or active=True
            {"deleted_at": {"$exists": False}},  # old rows without soft-delete fields
        ]
    if status:
        query["status"] = status
    if search:
        search_regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"code": search_regex},
            {"name": search_regex},
            {"description": search_regex}
        ]
    docs = await db.styles.find(query).sort("created_at", -1).to_list(1000)
    # Bulk-fetch pipeline membership so the FE can show "In Online Pipeline" badges
    # and gate the "Send to Online Pipeline" action without an N+1.
    pipeline_ids = {
        d["style_id"]
        for d in await db.style_lifecycle.find({}, {"style_id": 1}).to_list(20000)
    }
    out = []
    for d in docs:
        d = stringify(d)
        d["costing"] = compute_style_costing(d)
        d["in_online_pipeline"] = d["id"] in pipeline_ids
        out.append(d)
    return out

@api.get("/styles/bulk/template")
async def get_styles_template():
    import io
    import pandas as pd
    
    columns = [
        "Style Code", "Name", "Category", "Description", "Base Size",
        "Overhead %", "Packing Cost", "Margin %", "GST %", "Image URL",
        "Labor: Cutting", "Labor: Fitting", "Labor: Pasting", "Labor: Finishing", "Labor: Packing"
    ]
    
    sample_data = [
        {
            "Style Code": "SAMPLE-01", "Name": "Classic Oxford", "Category": "Footwear", "Description": "Men's leather shoe",
            "Base Size": 8, "Overhead %": 10, "Packing Cost": 15, "Margin %": 25, "GST %": 5, "Image URL": "",
            "Labor: Cutting": 12, "Labor: Fitting": 18, "Labor: Pasting": 10, "Labor: Finishing": 8, "Labor: Packing": 5
        }
    ]
    df = pd.DataFrame(sample_data, columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="style_master_template.xlsx"'}
    )

@api.post("/styles/bulk/preview", dependencies=[Depends(upload_rate_limiter)])
async def bulk_upload_preview(file: UploadFile = File(...), request: Request = None):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    import pandas as pd
    import io
    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, "Invalid Excel file")
        
    col_map = {
        "Style Code": "code",
        "Name": "name",
        "Category": "category",
        "Description": "description",
        "Base Size": "base_size",
        "Overhead %": "overhead_pct",
        "Packing Cost": "packing_cost",
        "Margin %": "margin_pct",
        "GST %": "gst_pct",
        "Image URL": "image_url"
    }
    df = df.rename(columns=col_map)
    if "code" not in df.columns or "name" not in df.columns:
        raise HTTPException(400, "Missing required columns (Style Code, Name)")
        
    labor_cols = [c for c in df.columns if str(c).strip().lower().startswith("labor:")]
    
    preview = []
    
    for idx, row in df.iterrows():
        code = str(row.get("code", "")).strip()
        if not code or code == "nan":
            continue
            
        name = str(row.get("name", "")).strip()
        if not name or name == "nan": continue
        
        labor = None
        if labor_cols:
            labor = []
            for lc in labor_cols:
                op_name = lc.split(":", 1)[1].strip()
                val = row.get(lc)
                if pd.notna(val) and str(val).strip() != "":
                    try:
                        rate = float(val)
                        labor.append({"name": op_name, "rate": rate})
                    except:
                        pass
                        
        _raw_url = str(row.get("image_url", "")).strip() if pd.notna(row.get("image_url")) else ""
        _norm_url = normalize_image_url(_raw_url)
        preview.append({
            "code": code,
            "name": name,
            "category": str(row.get("category", "Footwear")).strip() if pd.notna(row.get("category")) else "Footwear",
            "description": str(row.get("description", "")).strip() if pd.notna(row.get("description")) else "",
            "base_size": str(row.get("base_size", "7")).strip() if pd.notna(row.get("base_size")) else "7",
            "overhead_pct": float(row.get("overhead_pct", 0)) if pd.notna(row.get("overhead_pct")) else 0,
            "packing_cost": float(row.get("packing_cost", 0)) if pd.notna(row.get("packing_cost")) else 0,
            "margin_pct": float(row.get("margin_pct", 25)) if pd.notna(row.get("margin_pct")) else 25,
            "gst_pct": float(row.get("gst_pct", 5)) if pd.notna(row.get("gst_pct")) else 5,
            "image_url": _norm_url,
            # Preview mirrors bulk-import: raw URL is echoed into all three
            # variants for the frontend's SafeImage fallback chain.
            "image_display_url":   _norm_url,
            "image_thumbnail_url": _norm_url,
            "labor": labor
        })
                    
    return {"preview": preview}

@api.post("/styles/bulk")
async def bulk_upload_styles(payload: dict, request: Request = None):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    
    styles_list = payload.get("styles", [])
    if not styles_list:
        raise HTTPException(400, "No styles provided")
    
    success = 0
    errors = []
    
    for idx, row in enumerate(styles_list):
        try:
            code = row.get("code", "").strip()
            name = row.get("name", "").strip()
            if not code or not name:
                errors.append(f"Row {idx+1}: Missing code or name")
                continue
                
            doc = {
                "code": code,
                "name": name,
                "category": row.get("category", "Footwear"),
                "description": row.get("description", ""),
                "base_size": row.get("base_size", "7"),
                "overhead_pct": float(row.get("overhead_pct", 0)),
                "packing_cost": float(row.get("packing_cost", 0)),
                "margin_pct": float(row.get("margin_pct", 25)),
                "gst_pct": float(row.get("gst_pct", 5)),
                "image_url": normalize_image_url(row.get("image_url", "")),
                # Bulk / CSV imports carry a single externally-supplied URL —
                # no Pillow re-encode was run on it. Mirror the raw URL into
                # display_url and thumbnail_url so the frontend's fallback
                # chain still finds *something* to render (Phase 3 spec).
                "image_display_url":   normalize_image_url(row.get("image_display_url")   or row.get("image_url", "")),
                "image_thumbnail_url": normalize_image_url(row.get("image_thumbnail_url") or row.get("image_url", "")),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            if row.get("labor") is not None: doc["labor"] = row.get("labor")
            else: doc["labor"] = []
                
            existing = await db.styles.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}})
            
            if existing:
                doc.pop("created_at")
                if row.get("labor") is None:
                    doc["labor"] = existing.get("labor", [])
                
                doc["bom"] = existing.get("bom", [])
                doc["status"] = "active" if len(doc["bom"]) > 0 else "inactive"
                await db.styles.update_one({"_id": existing["_id"]}, {"$set": doc})
            else:
                doc["bom"] = []
                doc["status"] = "inactive"
                await db.styles.insert_one(doc)
            
            success += 1
        except Exception as e:
            errors.append(f"Row {idx+1}: {str(e)}")
            
    return {"ok": True, "success_count": success, "errors": errors}

@api.get("/styles/{sid}")
async def get_style(sid: str, request: Request):
    await get_current_user(request)
    d = await db.styles.find_one({"_id": oid(sid)})
    if not d:
        raise HTTPException(404, "Not found")
    d = stringify(d)
    d["costing"] = compute_style_costing(d)
    return d

@api.post("/styles")
async def create_style(payload: StyleIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # System ALWAYS generates the style code — any user-supplied `code` is
    # ignored to guarantee uniqueness and format consistency (SSK_XXXXX).
    doc = payload.model_dump()
    # Normalize share-link URLs (Dropbox/OneDrive/Drive) so that a browser <img>
    # tag and the PDF renderer can fetch them directly.
    _u = normalize_image_url(doc.get("image_url", "") or "")
    if _u:
        doc["image_url"] = _u
        if not doc.get("image_display_url"):   doc["image_display_url"]   = _u
        if not doc.get("image_thumbnail_url"): doc["image_thumbnail_url"] = _u
    # Retry loop to survive the (astronomically unlikely) case where two
    # concurrent creates receive the same seq before the unique index is hit.
    generated_code = None
    for _ in range(5):
        candidate = await _next_style_code()
        if not await db.styles.find_one({"code": candidate}):
            generated_code = candidate
            break
    if not generated_code:
        raise HTTPException(500, "Failed to generate a unique style code — please retry")
    doc["code"] = generated_code
    doc["status"] = "active" if len(doc.get("bom", [])) > 0 else "inactive"
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    try:
        res = await db.styles.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Style code '{generated_code}' collision — please retry")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    doc["costing"] = compute_style_costing(doc)
    await log_activity("style.create", "styles",
                       f"Created style {generated_code} — {doc.get('name','')}", u["email"])
    return doc

@api.patch("/styles/{sid}")
async def update_style(sid: str, payload: StyleIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    existing = await db.styles.find_one({"_id": oid(sid)})
    if not existing:
        raise HTTPException(404, "Style not found")
    update = payload.model_dump()
    # Normalize share-link URLs (Dropbox/OneDrive/Drive) so that <img> and the
    # PDF renderer can fetch them directly.
    _u = normalize_image_url(update.get("image_url", "") or "")
    if _u:
        update["image_url"] = _u
        if not update.get("image_display_url"):   update["image_display_url"]   = _u
        if not update.get("image_thumbnail_url"): update["image_thumbnail_url"] = _u
    # style.code is IMMUTABLE — silently drop any incoming value so it can
    # never drift from the SSK_XXXXX assigned at creation.
    supplied_code = (update.pop("code", "") or "").strip()
    if supplied_code and supplied_code != existing.get("code", ""):
        raise HTTPException(
            400,
            f"Style code is immutable — attempted to change '{existing.get('code','')}' to '{supplied_code}'"
        )
    update["status"] = "active" if len(update.get("bom", [])) > 0 else "inactive"
    update["updated_at"] = now_iso()
    await db.styles.update_one({"_id": oid(sid)}, {"$set": update})
    d = stringify(await db.styles.find_one({"_id": oid(sid)}))
    d["costing"] = compute_style_costing(d)
    return d

@api.delete("/styles/{sid}")
async def delete_style(sid: str, request: Request):
    """Cascade-aware soft-delete for a Style Master record.

    Safety checks (HTTP 409 blockers — must be resolved before deletion):
      1. Active PO line items referencing this style_code.
      2. Production jobs in states other than 'dispatched' / 'cancelled'.
      3. FG inventory rows with non-zero ready_stock_qty or reserved_qty.

    On success (no blockers):
      • style_lifecycle row              → hard deleted
      • sku_map rows                     → hard deleted (they are SKU translation tables)
      • style_component_mapping rows     → set active=False (cascade deactivation)
      • fg_inventory rows (qty=0 only)   → hard deleted; non-zero rows are flagged active=False
      • styles row                       → soft-deleted: active=False, deleted_at=now
        (the record is kept for audit purposes and PO/invoice history)

    A complete audit trail is written to audit_logs for every cascade action.
    """
    u = await get_current_user(request)
    require_roles("admin", "manager")(u)

    style = await db.styles.find_one({"_id": oid(sid)})
    if not style:
        raise HTTPException(404, "Style not found")

    style_code = style.get("code", sid)
    now = now_iso()
    blockers: list = []

    # ── Blocker 1: active PO line items ───────────────────────────────────────
    po_refs = await db.purchase_orders.find_one({
        "line_items.style_code": style_code,
        "status": {"$nin": ["cancelled", "closed"]},
    })
    if po_refs:
        blockers.append(
            f"Active PO '{po_refs.get('po_number', po_refs['_id'])}' references style {style_code}"
        )

    # ── Blocker 2: active production jobs ─────────────────────────────────────
    active_job = await db.production_jobs.find_one({
        "style_id": ObjectId(sid),
        "stage": {"$nin": ["dispatched", "cancelled"]},
    })
    if active_job:
        blockers.append(
            f"Active production job '{active_job.get('job_number', active_job['_id'])}' "
            f"is still in progress for style {style_code}"
        )

    # ── Blocker 3: non-zero FG inventory ──────────────────────────────────────
    nonzero_inv = await db.fg_inventory.find_one({
        "style_id": ObjectId(sid),
        "$or": [
            {"ready_stock_qty": {"$gt": 0}},
            {"reserved_qty":    {"$gt": 0}},
        ],
    })
    if nonzero_inv:
        blockers.append(
            f"FG inventory has non-zero stock (color={nonzero_inv.get('color')}, "
            f"size={nonzero_inv.get('size')}) for style {style_code}. Zero out stock first."
        )

    if blockers:
        raise HTTPException(
            409,
            {
                "message": f"Cannot delete style '{style_code}' — {len(blockers)} blocker(s) must be resolved first.",
                "blockers": blockers,
            }
        )

    # ── Cascade: clean up all soft-reference collections ──────────────────────
    cascade_summary: dict = {}

    # 1. style_lifecycle — hard delete (it belongs entirely to this style)
    lc_del = await db.style_lifecycle.delete_one({"style_id": sid})
    cascade_summary["lifecycle_deleted"] = lc_del.deleted_count

    # 2. sku_map — hard delete (SKU translations are meaningless without the style)
    sku_del = await db.sku_map.delete_many({"style_id": sid})
    cascade_summary["sku_map_deleted"] = sku_del.deleted_count

    # 3. style_component_mapping (BOM links) — set active=False
    bom_res = await db.style_component_mapping.update_many(
        {"style_id": sid},
        {"$set": {"active": False, "updated_at": now}},
    )
    cascade_summary["bom_links_deactivated"] = bom_res.modified_count

    # 4. fg_inventory — hard-delete zero-qty rows, soft-delete any remainder
    zero_inv_del = await db.fg_inventory.delete_many({
        "style_id": ObjectId(sid),
        "ready_stock_qty": {"$lte": 0},
        "reserved_qty":    {"$lte": 0},
        "in_transit_qty":  {"$lte": 0},
        "return_qty":      {"$lte": 0},
        "damaged_qty":     {"$lte": 0},
        "liquidation_qty": {"$lte": 0},
    })
    nonzero_inv_flag = await db.fg_inventory.update_many(
        {"style_id": ObjectId(sid)},
        {"$set": {"active": False, "updated_at": now}},
    )
    cascade_summary["fg_inventory_zeroed_deleted"] = zero_inv_del.deleted_count
    cascade_summary["fg_inventory_nonzero_flagged"] = nonzero_inv_flag.modified_count

    # 5. Soft-delete the style master itself
    await db.styles.update_one(
        {"_id": oid(sid)},
        {"$set": {
            "active":     False,
            "deleted_at": now,
            "updated_at": now,
        }}
    )

    await log_activity(
        "DELETE", "styles",
        f"Style '{style_code}' soft-deleted. Cascade: {cascade_summary}",
        u["email"],
    )

    return {
        "ok":             True,
        "id":             sid,
        "style_code":     style_code,
        "cascade":        cascade_summary,
    }



# ---------- CATALOGUE CODES ----------
# For a given style, resolve every planned colour and size, and build the
# canonical marketplace SKUs via build_catalogue_sku(). Used by the frontend
# "Catalogue Codes" panel so merchandisers can see exactly what SKUs will go
# into each platform's listing file before Phase F generates the export.
@api.get("/styles/{sid}/catalogue-codes")
async def get_style_catalogue_codes(sid: str, request: Request):
    await get_current_user(request)
    style = await db.styles.find_one({"_id": oid(sid)})
    if not style:
        raise HTTPException(404, "Style not found")
    style_code = style.get("code", "")

    # 1. Prefer planned colours & sizes from style_lifecycle (Phase 5 canonical source)
    lifecycle = await db.style_lifecycle.find_one({"style_id": str(style["_id"])})
    colors: List[str] = []
    sizes: List[str] = []
    if lifecycle:
        colors = [c for c in (lifecycle.get("planned_colors") or []) if c]
        sizes = [str(s) for s in (lifecycle.get("planned_sizes") or []) if s]

    # 2. Fall back to distinct colours & sizes present in fg_inventory
    if not colors or not sizes:
        cursor = db.fg_inventory.find({"style_id": str(style["_id"])})
        cset, sset = set(), set()
        async for r in cursor:
            if r.get("color"): cset.add(r["color"])
            if r.get("size"):  sset.add(str(r["size"]))
        if not colors: colors = sorted(cset)
        if not sizes:
            # Try natural numeric sort where possible
            def _ssort(x):
                try:    return (0, int(x))
                except: return (1, x)
            sizes = sorted(sset, key=_ssort)

    # 3. Resolve each colour → colour_code via color_master. If the colour
    # isn't in the master yet, surface that so the UI can prompt the admin
    # to add it. Never invent codes ad hoc — that defeats the whole point of
    # the canonical builder.
    color_rows = []
    for cname in colors:
        code = await resolve_color_code(cname)
        group_sku = build_catalogue_sku(style_code, code) if code else ""
        color_rows.append({
            "color_name":  cname,
            "color_code":  code or "",
            "mapped":      bool(code),
            "group_sku":   group_sku,   # style + colour (marketplace Style Id)
            "size_skus":   [
                {
                    "size":     sz,
                    "leaf_sku": build_catalogue_sku(style_code, code, sz) if code else "",
                }
                for sz in sizes
            ],
        })

    unmapped_colors = [r["color_name"] for r in color_rows if not r["mapped"]]

    return {
        "style_id":         str(style["_id"]),
        "style_code":       style_code,
        "style_name":       style.get("name", ""),
        "colors":           colors,
        "sizes":            sizes,
        "rows":             color_rows,
        "unmapped_colors":  unmapped_colors,
    }


# ---------- COLOR MASTER ----------
class ColorMasterIn(BaseModel):
    color_name: str
    color_code: str
    active: bool = True

    @field_validator("color_code")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not (2 <= len(v) <= 3) or not v.isalpha():
            raise PydanticCustomError(
                "color_code_format",
                "color_code must be 2-3 uppercase letters (e.g. TN, GN)",
            )
        return v

    @field_validator("color_name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise PydanticCustomError("color_name_empty", "color_name is required")
        return v


class ColorMasterUpdate(BaseModel):
    color_name: Optional[str] = None
    color_code: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("color_code")
    @classmethod
    def _upper_code_opt(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if not (2 <= len(v) <= 3) or not v.isalpha():
            raise PydanticCustomError(
                "color_code_format",
                "color_code must be 2-3 uppercase letters",
            )
        return v


@api.get("/color-master")
async def list_color_master(request: Request, active: Optional[bool] = None, search: Optional[str] = None):
    await get_current_user(request)
    q: Dict[str, Any] = {}
    if active is not None:
        q["active"] = active
    if search:
        rgx = {"$regex": re.escape(search), "$options": "i"}
        q["$or"] = [{"color_name": rgx}, {"color_code": rgx}]
    docs = await db.color_master.find(q).sort("color_name", 1).to_list(1000)
    return [stringify(d) for d in docs]


@api.post("/color-master")
async def create_color(payload: ColorMasterIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # Enforce uniqueness on code (case-insensitive) and name (case-insensitive)
    if await db.color_master.find_one({"color_code": payload.color_code}):
        raise HTTPException(409, f"color_code '{payload.color_code}' already exists")
    if await db.color_master.find_one({"color_name_lc": payload.color_name.lower()}):
        raise HTTPException(409, f"color_name '{payload.color_name}' already exists")
    doc = {
        "color_name":    payload.color_name,
        "color_name_lc": payload.color_name.lower(),
        "color_code":    payload.color_code,
        "active":        payload.active,
        "created_at":    now_iso(),
        "updated_at":    now_iso(),
    }
    try:
        res = await db.color_master.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"color_code '{payload.color_code}' already exists")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    await log_activity("color.create", "color_master",
                       f"Added colour {payload.color_name} ({payload.color_code})", u["email"])
    return doc


@api.put("/color-master/{cid}")
async def update_color(cid: str, payload: ColorMasterUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    existing = await db.color_master.find_one({"_id": oid(cid)})
    if not existing:
        raise HTTPException(404, "Colour not found")
    update: Dict[str, Any] = {}
    if payload.color_name is not None:
        # Uniqueness: another doc with same lc name?
        by_name = await db.color_master.find_one({
            "color_name_lc": payload.color_name.lower(),
            "_id": {"$ne": oid(cid)},
        })
        if by_name:
            raise HTTPException(409, f"color_name '{payload.color_name}' already exists")
        update["color_name"]    = payload.color_name
        update["color_name_lc"] = payload.color_name.lower()
    if payload.color_code is not None:
        by_code = await db.color_master.find_one({
            "color_code": payload.color_code,
            "_id": {"$ne": oid(cid)},
        })
        if by_code:
            raise HTTPException(409, f"color_code '{payload.color_code}' already exists")
        update["color_code"] = payload.color_code
    if payload.active is not None:
        update["active"] = payload.active
    if not update:
        return stringify(existing)
    update["updated_at"] = now_iso()
    await db.color_master.update_one({"_id": oid(cid)}, {"$set": update})
    fresh = await db.color_master.find_one({"_id": oid(cid)})
    await log_activity("color.update", "color_master",
                       f"Updated colour {fresh.get('color_name')} ({fresh.get('color_code')})", u["email"])
    return stringify(fresh)


# ═══════════════════════════════════════════════════════════════════════
# ══ LISTING FORMAT REGISTRY ════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# Config-driven registry of platform listing-file formats. Instead of
# hardcoding parsing logic per platform (Myntra styledashboard sheet name,
# Ajio's dynamic sheet name pattern, Flipkart's description row after the
# header, differing column names for the same canonical field), each
# platform gets ONE config document in `listing_format_configs`. Adding a
# 5th, 6th, 7th platform later never requires touching parsing code — only
# adding a config row through the admin UI.
#
# Canonical fields (any platform's export must be mappable to these):
#   group_id            - style+colour grouping id (Myntra "Style Id",
#                         Ajio "*Style Code"); null when platform has no
#                         native grouping (Flipkart) — Phase C will derive
#                         it from leaf_sku + our SKU map.
#   leaf_sku            - fully-unique per-size code (Myntra "SellerSkuCode",
#                         Ajio "*Item SKU", Flipkart "Seller SKU Id")
#   size                - size column when explicit; null when embedded in
#                         leaf_sku (Myntra, Flipkart)
#   color_primary       - primary colour column (Myntra "Colour", Ajio
#                         "*Primary Color")
#   color_family        - broader colour family (optional; Ajio only)
#   style_description   - product title/description
#   mrp                 - MRP column
#   selling_price       - platform's selling-price column
#   brand               - brand column
#   listing_status      - active/inactive/pending flag column
# ═══════════════════════════════════════════════════════════════════════

Platform = Literal["myntra", "flipkart", "ajio", "nykaa", "website", "other"]

CANONICAL_FIELDS = [
    "group_id", "leaf_sku", "size",
    "color_primary", "color_family",
    "style_description", "mrp", "selling_price",
    "brand", "listing_status",
]


# ── Export template value sources (Phase F) ──────────────────────────
# Each column in an export_template.columns row declares how to fill in
# its per-row cell value. The resolver walks these sources for each
# {colour × size} combination the caller has selected. New source types
# can be added later by extending _resolve_export_source() below.
EXPORT_SOURCE_TYPES = [
    "group_sku",      # build_catalogue_sku(style_code, color_code)
    "leaf_sku",       # build_catalogue_sku(style_code, color_code, size)
    "style_code",     # the SSK_XXXXX itself
    "size",           # the size string
    "color_name",     # the colour name (e.g. "Tan")
    "color_code",     # the 2-3 letter code (e.g. "TN")
    "style",          # a dot-path field on the Style master     ("style", key="name")
    "lifecycle",      # a dot-path field on style_lifecycle       ("lifecycle", key="mrp")
    "constant",       # a fixed value from `value`
    "blank",          # empty — platform will assign (e.g. Myntra Style Id)
]


class ExportColumn(BaseModel):
    """One column in a platform's new-listing upload file."""
    name: str                                 # exact header text the platform requires
    source: Literal[
        "group_sku", "leaf_sku", "style_code", "size",
        "color_name", "color_code",
        "style", "lifecycle", "constant", "blank",
    ]
    # For source="style" or "lifecycle" — which field on that doc to pull.
    # e.g. source="style", key="name" → style.name
    key: Optional[str] = None
    # For source="constant" — the literal value to emit for every row.
    value: Optional[Any] = None
    # For source="blank" only — an optional hint shown in the UI.
    notes: Optional[str] = None
    required: bool = False


class ExportTemplate(BaseModel):
    """Structure of the new-listing upload file for one platform."""
    sheet_name: str = "Sheet1"
    # 0-based row index at which the header row is written. Anything before
    # this is filled with pre_header_rows (list of lists) as literal cells.
    header_row_index: int = 0
    # Filler rows placed BEFORE the header (Ajio ships a couple of
    # blank/metadata rows at the top of its template).
    pre_header_rows: Optional[List[List[Any]]] = None
    # Filler rows placed AFTER the header, BEFORE the first data row
    # (Flipkart's "hint / max chars" row).
    post_header_rows: Optional[List[List[Any]]] = None
    columns: List[ExportColumn]

    @field_validator("columns")
    @classmethod
    def _cols_non_empty(cls, v):
        if not v or len(v) == 0:
            raise PydanticCustomError(
                "export_columns_empty",
                "export_template.columns must contain at least one column"
            )
        # Ensure at least one column is source=leaf_sku — a listing file
        # without a leaf SKU cannot be re-imported later without ambiguity.
        if not any(c.source == "leaf_sku" for c in v):
            raise PydanticCustomError(
                "export_columns_leaf_sku",
                "export_template.columns must include exactly one column with source='leaf_sku'"
            )
        return v


class SheetLocator(BaseModel):
    """How to find the data sheet within an uploaded workbook."""
    type: Literal["fixed_name", "name_contains", "first_sheet"]
    # for type=fixed_name
    name: Optional[str] = None
    # for type=name_contains
    substring: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("substring")
    @classmethod
    def _clean_sub(cls, v):
        return v.strip() if isinstance(v, str) else v


class HeaderLocator(BaseModel):
    """How to find the header row within the data sheet."""
    type: Literal["fixed_row", "scan_for_columns"]
    # for type=fixed_row (0-indexed)
    row: Optional[int] = None
    # for type=scan_for_columns — scan the first ~10 rows for a row that
    # contains AT LEAST ONE of these column names (case-insensitive substring)
    must_contain_any: Optional[List[str]] = None


class ListingFormatConfigIn(BaseModel):
    platform: Platform
    sheet_locator: SheetLocator
    header_locator: HeaderLocator
    skip_rows_after_header: int = 0
    # canonical field -> actual column name in this platform's export
    # (null when the canonical field is not present in that platform's file)
    column_map: Dict[str, Optional[str]]
    has_native_group_id: bool = False
    active: bool = True
    notes: Optional[str] = ""
    # NEW (Phase F): structure of the new-listing upload file. Optional so
    # existing configs don't break; catalogue-export refuses to run for a
    # platform whose export_template is null with a clear error.
    export_template: Optional[ExportTemplate] = None

    @field_validator("column_map")
    @classmethod
    def _validate_column_map(cls, v):
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        # unknown canonical fields are allowed (forward-compat for later platforms)
        # but leaf_sku is REQUIRED — without it there's no per-size row identity
        if not v.get("leaf_sku"):
            raise PydanticCustomError(
                "column_map_leaf_sku",
                "column_map.leaf_sku is required — every platform must expose the per-size unique SKU column"
            )
        return v


class ListingFormatConfigUpdate(BaseModel):
    sheet_locator: Optional[SheetLocator] = None
    header_locator: Optional[HeaderLocator] = None
    skip_rows_after_header: Optional[int] = None
    column_map: Optional[Dict[str, Optional[str]]] = None
    has_native_group_id: Optional[bool] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
    export_template: Optional[ExportTemplate] = None

    @field_validator("column_map")
    @classmethod
    def _validate_column_map_opt(cls, v):
        if v is None:
            return v
        if not isinstance(v, dict):
            raise PydanticCustomError("column_map_type", "column_map must be an object")
        if not v.get("leaf_sku"):
            raise PydanticCustomError(
                "column_map_leaf_sku",
                "column_map.leaf_sku is required"
            )
        return v


DEFAULT_LISTING_FORMAT_CONFIGS = [
    # ── Myntra ────────────────────────────────────────────────────────
    # Data lives on the fixed-name sheet "styledashboard"; header on row 0;
    # no filler row after header. Size is EMBEDDED in SellerSkuCode (e.g.
    # "CC-058-BR-38"), so column_map.size is null — resolver derives it
    # via the SKU parser template.
    {
        "platform": "myntra",
        "sheet_locator": {"type": "fixed_name", "name": "styledashboard"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "group_id":          "Style Id",
            "leaf_sku":          "SellerSkuCode",
            "size":              None,
            "color_primary":     "Colour",
            "color_family":      None,
            "style_description": "Style Name",
            "mrp":               "MRP",
            "selling_price":     "Selling Price",
            "brand":             "Brand",
            "listing_status":    "Listing Status",
        },
        "has_native_group_id": True,
        "active": True,
        "notes": "Myntra Style Dashboard export. Sheet name is fixed. Size is embedded in SellerSkuCode.",
        # Phase F — new-listing upload template. Myntra assigns its numeric
        # Style Id post-ingest, so we leave that column blank. Our own leaf
        # SKU (SSK_XXXXX-COLOR-SIZE) sits in the SellerSkuCode column,
        # which is what Myntra echoes back on every subsequent export.
        "export_template": {
            "sheet_name": "styledashboard",
            "header_row_index": 0,
            "columns": [
                {"name": "Style Id",       "source": "blank",     "notes": "Myntra assigns after ingest"},
                {"name": "SellerSkuCode",  "source": "leaf_sku",  "required": True},
                {"name": "Style Name",     "source": "style",     "key": "name"},
                {"name": "Brand",          "source": "lifecycle", "key": "brand"},
                {"name": "Category",       "source": "style",     "key": "category"},
                {"name": "Colour",         "source": "color_name"},
                {"name": "Size",           "source": "size"},
                {"name": "MRP",            "source": "lifecycle", "key": "mrp"},
                {"name": "Selling Price",  "source": "lifecycle", "key": "online_selling_price"},
                {"name": "Description",    "source": "style",     "key": "description"},
                {"name": "Image URL",      "source": "style",     "key": "image_url"},
                {"name": "Listing Status", "source": "constant",  "value": "Active"},
            ],
        },
    },
    # ── Ajio ──────────────────────────────────────────────────────────
    # Sheet name is dynamic per feed/category (e.g. "Women_Styles_20250701"),
    # so we locate it by substring. Header is on row index 2 (not 0), and
    # different exports may shift this — so scan the first ~10 rows for a
    # row containing "*Style Code" / "*Item SKU". Column names include a
    # leading asterisk in Ajio's template.
    {
        "platform": "ajio",
        "sheet_locator": {"type": "name_contains", "substring": "_Styles_"},
        "header_locator": {"type": "scan_for_columns", "must_contain_any": ["*Style Code", "*Item SKU", "*Size", "*Primary Color"]},
        "skip_rows_after_header": 0,
        "column_map": {
            "group_id":          "*Style Code",
            "leaf_sku":          "*Item SKU",
            "size":              "*Size",
            "color_primary":     "*Primary Color",
            "color_family":      "*Color Family",
            "style_description": "*Product Description",
            "mrp":               "*MRP",
            "selling_price":     "*Selling Price",
            "brand":             "*Brand",
            "listing_status":    "*Listing Status",
        },
        "has_native_group_id": True,
        "active": True,
        "notes": "Ajio catalogue export. Sheet name pattern *_Styles_*. Header row may shift — scanner handles rows 0-10.",
        # Phase F — Ajio's new-listing template. Header is on row index 2,
        # with two filler/metadata rows above. Ajio uses OUR group_sku for
        # *Style Code and OUR leaf_sku for *Item SKU — they don't reassign.
        "export_template": {
            "sheet_name": "SSK_Styles_Export",
            "header_row_index": 2,
            "pre_header_rows": [
                ["SSK Footcare — new listing upload"],
                ["Generated automatically. Do not edit header row."],
            ],
            "columns": [
                {"name": "*Style Code",           "source": "group_sku",  "required": True},
                {"name": "*Style Description",   "source": "style",      "key": "description"},
                {"name": "*Item SKU",            "source": "leaf_sku",   "required": True},
                {"name": "*Brand",               "source": "lifecycle",  "key": "brand"},
                {"name": "*MRP",                 "source": "lifecycle",  "key": "mrp"},
                {"name": "*Size",                "source": "size",       "required": True},
                {"name": "*Primary Color",       "source": "color_name", "required": True},
                {"name": "*Color Family",        "source": "lifecycle",  "key": "color_family"},
                {"name": "*Upper Material",      "source": "lifecycle",  "key": "upper_material"},
                {"name": "*Sole Material",       "source": "lifecycle",  "key": "sole_material"},
                {"name": "*Product Description", "source": "style",      "key": "description"},
                {"name": "*Selling Price",       "source": "lifecycle",  "key": "online_selling_price"},
                {"name": "*Listing Status",      "source": "constant",   "value": "Active"},
            ],
        },
    },
    # ── Flipkart ──────────────────────────────────────────────────────
    # Simple single-sheet format; take first sheet. Header on row 0, then
    # a description row (e.g. "Product Title (max 200 chars)…") immediately
    # after — skip_rows_after_header=1. No native group id column, so
    # has_native_group_id=false → Phase C will derive the group from our
    # SKU map's colour translation.
    {
        "platform": "flipkart",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 1,
        "column_map": {
            "group_id":          None,
            "leaf_sku":          "Seller SKU Id",
            "size":              None,
            "color_primary":     "Color",
            "color_family":      None,
            "style_description": "Product Title",
            "mrp":               "MRP",
            "selling_price":     "Your Selling Price",
            "brand":             "Brand",
            "listing_status":    "Listing Status",
        },
        "has_native_group_id": False,
        "active": True,
        "notes": "Flipkart Listings export. Row 1 (after header) is a description/hint row and must be skipped. No native group id — derive via SKU map.",
        # Phase F — Flipkart's new-listing template. No native group id
        # column, so we emit only the leaf SKU (SSK_XXXXX-COLOR-SIZE) and
        # rely on the SKU map to reassemble the group later. Flipkart's
        # template includes a hint/example row right below the header.
        "export_template": {
            "sheet_name": "Listings",
            "header_row_index": 0,
            "post_header_rows": [
                [
                    "Seller SKU Id (must be unique per size)",
                    "Full product title (max 200 chars)",
                    "Brand name", "MRP (INR)", "Your selling price (INR)",
                    "Colour name", "Size (numeric)", "Product description",
                    "Public image URL", "Active",
                ],
            ],
            "columns": [
                {"name": "Seller SKU Id",     "source": "leaf_sku",   "required": True},
                {"name": "Product Title",    "source": "style",      "key": "name"},
                {"name": "Brand",            "source": "lifecycle",  "key": "brand"},
                {"name": "MRP",              "source": "lifecycle",  "key": "mrp"},
                {"name": "Your Selling Price","source": "lifecycle", "key": "online_selling_price"},
                {"name": "Color",            "source": "color_name"},
                {"name": "Size",             "source": "size"},
                {"name": "Description",      "source": "style",      "key": "description"},
                {"name": "Image URL",        "source": "style",      "key": "image_url"},
                {"name": "Listing Status",   "source": "constant",   "value": "Active"},
            ],
        },
    },
]


async def _seed_listing_format_configs() -> int:
    """Idempotently seed listing_format_configs with Myntra/Ajio/Flipkart.

    Also patches previously-seeded docs that were created BEFORE the
    export_template field existed (Phase F) — so a live deployment picks
    up the new export template on next restart without needing a manual
    Mongo migration or a DELETE-and-reseed dance.
    """
    try:
        await db.listing_format_configs.create_index("platform", unique=True, name="lfc_platform_unique")
    except Exception as e:
        log.warning(f"Could not create listing_format_configs index: {e}")
    inserted = 0
    patched = 0
    for cfg in DEFAULT_LISTING_FORMAT_CONFIGS:
        existing = await db.listing_format_configs.find_one({"platform": cfg["platform"]})
        if existing:
            # If the existing seeded doc is missing export_template, patch it.
            # Do NOT touch admin-edited docs (seeded=False) or configs whose
            # export_template has already been customised.
            if existing.get("seeded", False) and not existing.get("export_template") and cfg.get("export_template"):
                await db.listing_format_configs.update_one(
                    {"platform": cfg["platform"]},
                    {"$set": {
                        "export_template": cfg["export_template"],
                        "updated_at":      now_iso(),
                    }},
                )
                patched += 1
            continue
        doc = dict(cfg)
        doc["created_at"] = now_iso()
        doc["updated_at"] = now_iso()
        doc["seeded"]     = True
        await db.listing_format_configs.insert_one(doc)
        inserted += 1
    if patched:
        log.info(f"Listing format registry: patched {patched} seeded configs with export_template")
    return inserted


# ── Endpoints ────────────────────────────────────────────────────────
@api.get("/listing-format-configs")
async def list_listing_format_configs(request: Request, active: Optional[bool] = None):
    """List all platform listing-format configs.

    Any authenticated user can read (needed by pipelines that resolve columns).
    Only admins can create/update.
    """
    await get_current_user(request)
    q: Dict[str, Any] = {}
    if active is not None:
        q["active"] = active
    docs = await db.listing_format_configs.find(q).sort("platform", 1).to_list(1000)
    return [stringify(d) for d in docs]


@api.get("/listing-format-configs/{platform}")
async def get_listing_format_config(platform: str, request: Request):
    await get_current_user(request)
    doc = await db.listing_format_configs.find_one({"platform": platform.lower()})
    if not doc:
        raise HTTPException(404, f"No listing-format config for platform '{platform}'")
    return stringify(doc)


@api.post("/listing-format-configs")
async def create_listing_format_config(payload: ListingFormatConfigIn, request: Request):
    u = await get_current_user(request); require_roles("admin")(u)
    if await db.listing_format_configs.find_one({"platform": payload.platform}):
        raise HTTPException(409, f"Config for platform '{payload.platform}' already exists — use PUT to update")
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    doc["seeded"]     = False
    try:
        res = await db.listing_format_configs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"Config for platform '{payload.platform}' already exists")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    await log_activity("listing_format.create", "listing_format_configs",
                       f"Added listing format config for {payload.platform}", u["email"])
    return doc


@api.put("/listing-format-configs/{platform}")
async def update_listing_format_config(platform: str, payload: ListingFormatConfigUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin")(u)
    platform_lc = platform.lower()
    existing = await db.listing_format_configs.find_one({"platform": platform_lc})
    if not existing:
        raise HTTPException(404, f"No listing-format config for platform '{platform_lc}'")
    update: Dict[str, Any] = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        return stringify(existing)
    update["updated_at"] = now_iso()
    await db.listing_format_configs.update_one({"platform": platform_lc}, {"$set": update})
    fresh = await db.listing_format_configs.find_one({"platform": platform_lc})
    await log_activity("listing_format.update", "listing_format_configs",
                       f"Updated listing format config for {platform_lc}: {', '.join(update.keys())}", u["email"])
    return stringify(fresh)


@api.get("/listing-format-configs/_meta/canonical-fields")
async def get_canonical_fields(request: Request):
    """Return the list of canonical field names used in column_map — helps the
    admin UI render an editable form without hardcoding the schema client-side."""
    await get_current_user(request)
    return {"canonical_fields": CANONICAL_FIELDS}


# ═══════════════════════════════════════════════════════════════════════
# ══ CATALOGUE EXPORT GENERATOR (Phase F) ═══════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# Build the actual file a merchandiser uploads to a platform's seller
# panel to catalogue a NEW style. This closes the loop:
#   Style created → SSK_XXXXX assigned (Phase A0)
#   → catalogue file generated here with our own SKU naming
#   → uploaded to platform → platform's own export later re-imported
#   → matches on the SSK pattern directly with zero manual reconciliation.
# ═══════════════════════════════════════════════════════════════════════

class CatalogueExportRequest(BaseModel):
    style_id: str
    platform: Platform
    # Colours & sizes the merchandiser wants to catalogue in this file.
    # If omitted or empty, defaults to lifecycle.planned_colors / planned_sizes.
    colors: Optional[List[str]] = None
    sizes:  Optional[List[str]] = None


def _resolve_export_source(
    col: dict,
    *,
    style: dict,
    lifecycle: Optional[dict],
    style_code: str,
    color_name: str,
    color_code: str,
    size: str,
) -> Any:
    """Resolve one export-template column's cell value for one row.

    Kept small and pure — new source types are added by extending this
    switch, no other code path changes.
    """
    src = col.get("source")
    if src == "blank":
        return ""
    if src == "constant":
        return col.get("value", "")
    if src == "group_sku":
        return build_catalogue_sku(style_code, color_code)
    if src == "leaf_sku":
        return build_catalogue_sku(style_code, color_code, size)
    if src == "style_code":
        return style_code
    if src == "size":
        return size
    if src == "color_name":
        return color_name
    if src == "color_code":
        return color_code
    if src == "style":
        key = col.get("key")
        if not key:
            return ""
        return style.get(key, "") if isinstance(style, dict) else ""
    if src == "lifecycle":
        key = col.get("key")
        if not key or not lifecycle:
            return ""
        return lifecycle.get(key, "")
    return ""


async def _upsert_provisional_sku_map(
    *,
    style_id: str,
    platform: str,
    group_sku: str,
    color_name: str,
    sizes_covered: List[str],
    user_email: str,
) -> str:
    """Insert (or refresh) a provisional sku_map row for this
    (style_id, platform, group_sku). Status is
    'pending_platform_confirmation' — flipped to 'confirmed' later either
    manually via the SKU-map UI or automatically when the first
    online_orders import (Phase 4 of the master plan) resolves this exact
    external_sku successfully.

    Returns "created" | "updated" | "unchanged" so the caller can report.
    """
    filter_ = {
        "source_type":  "online_channel",
        "source_name":  platform,
        "external_sku": group_sku,
    }
    existing = await db.sku_map.find_one(filter_)
    color_map = {color_name: color_name}   # identity — colour name matches on both sides
    size_map  = {s: str(s) for s in sizes_covered}
    if existing:
        # Only touch fields we own; never downgrade a confirmed mapping.
        update: Dict[str, Any] = {}
        if existing.get("style_id") != style_id:
            update["style_id"] = style_id
        # Merge maps — additive
        merged_cm = {**(existing.get("color_map") or {}), **color_map}
        merged_sm = {**(existing.get("size_map")  or {}), **size_map}
        if merged_cm != (existing.get("color_map") or {}):
            update["color_map"] = merged_cm
        if merged_sm != (existing.get("size_map") or {}):
            update["size_map"] = merged_sm
        # Only touch status if it's not already confirmed
        if existing.get("status") not in ("confirmed", "auto_confirmed"):
            update["status"] = "pending_platform_confirmation"
        if not update:
            return "unchanged"
        update["updated_at"] = now_iso()
        await db.sku_map.update_one({"_id": existing["_id"]}, {"$set": update})
        return "updated"
    doc = {
        "style_id":            style_id,
        "source_type":         "online_channel",
        "source_name":         platform,
        "external_sku":        group_sku,
        "external_style_name": "",
        "color_map":           color_map,
        "size_map":            size_map,
        "status":              "pending_platform_confirmation",
        "created_via":         "catalogue_export",
        "created_at":          now_iso(),
        "updated_at":          now_iso(),
    }
    try:
        await db.sku_map.insert_one(doc)
        return "created"
    except DuplicateKeyError:
        # Race — another concurrent export inserted first. Treat as updated.
        return "updated"


@api.post("/catalogue-export")
async def catalogue_export(payload: CatalogueExportRequest, request: Request):
    """Generate a new-listing upload .xlsx for one style × platform.

    For each (colour, size) combination:
      - color_code   = color_master lookup for colour name
      - group_sku    = build_catalogue_sku(style_code, color_code)
      - leaf_sku     = build_catalogue_sku(style_code, color_code, size)
    Rows populate the platform's export_template.columns in declared order.
    Also inserts/refreshes provisional sku_map rows for each (colour, group_sku)
    pair (status="pending_platform_confirmation").
    Returns application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)

    # 1. Style + config lookups
    style = await db.styles.find_one({"_id": oid(payload.style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    style_code = style.get("code", "")
    if not style_code:
        raise HTTPException(400, "Style has no style_code — cannot export a catalogue file")

    cfg = await db.listing_format_configs.find_one({"platform": payload.platform})
    if not cfg:
        raise HTTPException(404, f"No listing-format config for platform '{payload.platform}' — create one first")
    export_template = cfg.get("export_template")
    if not export_template:
        raise HTTPException(
            400,
            f"Platform '{payload.platform}' has no export_template configured. "
            "Add one via PUT /api/listing-format-configs/{platform} before generating catalogue files."
        )
    if not cfg.get("active", True):
        raise HTTPException(400, f"Platform '{payload.platform}' config is inactive")

    lifecycle = await db.style_lifecycle.find_one({"style_id": str(style["_id"])})

    # 2. Resolve which colours × sizes to export
    colors = [c for c in (payload.colors or []) if c and c.strip()]
    sizes  = [str(s) for s in (payload.sizes  or []) if s and str(s).strip()]
    if not colors and lifecycle:
        colors = [c for c in (lifecycle.get("planned_colors") or []) if c]
    if not sizes and lifecycle:
        sizes = [str(s) for s in (lifecycle.get("planned_sizes") or []) if s]
    if not colors:
        raise HTTPException(400, "No colours to export. Pass `colors` in the body or set lifecycle.planned_colors.")
    if not sizes:
        raise HTTPException(400, "No sizes to export. Pass `sizes` in the body or set lifecycle.planned_sizes.")

    # 3. Resolve colour_code for each colour. Refuse to export if any is
    # unmapped — silently emitting a blank primary-colour code would poison
    # every downstream marketplace reconciliation.
    color_rows: List[Dict[str, str]] = []
    unmapped: List[str] = []
    for cname in colors:
        cc = await resolve_color_code(cname)
        if not cc:
            unmapped.append(cname)
        else:
            color_rows.append({"color_name": cname, "color_code": cc})
    if unmapped:
        raise HTTPException(
            400,
            f"These colours are not in the color master: {', '.join(unmapped)}. "
            "Add them via POST /api/color-master before exporting."
        )

    # 4. Build the workbook
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = (export_template.get("sheet_name") or "Sheet1")[:31]  # Excel sheet-name limit

    columns: List[dict] = export_template.get("columns") or []
    if not columns:
        raise HTTPException(500, "export_template.columns is empty — refusing to write an empty file")
    header_row_index = int(export_template.get("header_row_index") or 0)   # 0-based
    pre_header_rows  = export_template.get("pre_header_rows")  or []
    post_header_rows = export_template.get("post_header_rows") or []

    # Pre-header filler
    row_cursor = 1   # openpyxl is 1-indexed
    for filler in pre_header_rows:
        for i, cell in enumerate(filler):
            ws.cell(row=row_cursor, column=i + 1, value=cell)
        row_cursor += 1
    # If header_row_index > pre_header_rows length, pad with blank rows
    target_header_row = header_row_index + 1   # convert 0-based → 1-based
    while row_cursor < target_header_row:
        row_cursor += 1

    # Header
    for i, col in enumerate(columns):
        ws.cell(row=row_cursor, column=i + 1, value=col.get("name", ""))
    row_cursor += 1

    # Post-header filler
    for filler in post_header_rows:
        for i, cell in enumerate(filler):
            ws.cell(row=row_cursor, column=i + 1, value=cell)
        row_cursor += 1

    # Data rows — colour × size Cartesian product, colour-major so all rows
    # for one colour sit together (matches how merchandisers eyeball listings).
    rows_written = 0
    sku_map_summary = {"created": 0, "updated": 0, "unchanged": 0}
    style_dict = stringify(style)
    lifecycle_dict = stringify(lifecycle) if lifecycle else None

    for cr in color_rows:
        group_sku = build_catalogue_sku(style_code, cr["color_code"])
        for sz in sizes:
            for i, col in enumerate(columns):
                val = _resolve_export_source(
                    col,
                    style=style_dict,
                    lifecycle=lifecycle_dict,
                    style_code=style_code,
                    color_name=cr["color_name"],
                    color_code=cr["color_code"],
                    size=sz,
                )
                ws.cell(row=row_cursor, column=i + 1, value=val)
            row_cursor += 1
            rows_written += 1

        # Provisional sku_map row per (colour, platform) — one entry per
        # group SKU, not one per size, matching how sku_map is keyed in Phase 1.
        outcome = await _upsert_provisional_sku_map(
            style_id=str(style["_id"]),
            platform=payload.platform,
            group_sku=group_sku,
            color_name=cr["color_name"],
            sizes_covered=sizes,
            user_email=u["email"],
        )
        sku_map_summary[outcome] = sku_map_summary.get(outcome, 0) + 1

    # 5. Return as downloadable stream
    import io  # local, matches project convention (already used elsewhere)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    await log_activity(
        "catalogue.export",
        "catalogue_export",
        f"Generated {payload.platform} listing file for style {style_code} "
        f"({len(color_rows)} colours × {len(sizes)} sizes = {rows_written} rows; "
        f"sku_map: {sku_map_summary})",
        u["email"],
    )

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{style_code}_{payload.platform}_listing_{ts}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Custom headers so the frontend can show a toast without needing
            # to re-fetch or parse the file body.
            "X-Style-Code":         style_code,
            "X-Rows-Written":       str(rows_written),
            "X-Colors":             str(len(color_rows)),
            "X-Sizes":              str(len(sizes)),
            "X-SkuMap-Created":     str(sku_map_summary.get("created", 0)),
            "X-SkuMap-Updated":     str(sku_map_summary.get("updated", 0)),
            "X-SkuMap-Unchanged":   str(sku_map_summary.get("unchanged", 0)),
            "Access-Control-Expose-Headers":
                "Content-Disposition, X-Style-Code, X-Rows-Written, X-Colors, "
                "X-Sizes, X-SkuMap-Created, X-SkuMap-Updated, X-SkuMap-Unchanged",
        },
    )


@api.post("/catalogue-export/preview")
async def catalogue_export_preview(payload: CatalogueExportRequest, request: Request):
    """Non-file preview endpoint — returns the same rows the .xlsx would
    contain, as JSON. Used by the frontend to show a preview table before
    the user hits Download. Does NOT insert sku_map rows."""
    await get_current_user(request)

    style = await db.styles.find_one({"_id": oid(payload.style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    style_code = style.get("code", "")
    cfg = await db.listing_format_configs.find_one({"platform": payload.platform})
    if not cfg:
        raise HTTPException(404, f"No listing-format config for platform '{payload.platform}'")
    export_template = cfg.get("export_template")
    if not export_template:
        raise HTTPException(400, f"Platform '{payload.platform}' has no export_template configured")

    lifecycle = await db.style_lifecycle.find_one({"style_id": str(style["_id"])})
    colors = [c for c in (payload.colors or []) if c and c.strip()]
    sizes  = [str(s) for s in (payload.sizes  or []) if s and str(s).strip()]
    if not colors and lifecycle: colors = [c for c in (lifecycle.get("planned_colors") or []) if c]
    if not sizes  and lifecycle: sizes  = [str(s) for s in (lifecycle.get("planned_sizes")  or []) if s]

    color_rows, unmapped = [], []
    for cname in colors:
        cc = await resolve_color_code(cname)
        (unmapped if not cc else color_rows).append({"color_name": cname, "color_code": cc} if cc else cname)

    style_dict = stringify(style)
    lifecycle_dict = stringify(lifecycle) if lifecycle else None
    columns = export_template.get("columns") or []
    header  = [c.get("name", "") for c in columns]
    rows    = []
    for cr in color_rows:
        for sz in sizes:
            row = []
            for col in columns:
                row.append(_resolve_export_source(
                    col,
                    style=style_dict, lifecycle=lifecycle_dict,
                    style_code=style_code,
                    color_name=cr["color_name"], color_code=cr["color_code"],
                    size=sz,
                ))
            rows.append(row)

    return {
        "style_code":       style_code,
        "platform":         payload.platform,
        "sheet_name":       export_template.get("sheet_name"),
        "header_row_index": export_template.get("header_row_index", 0),
        "header":           header,
        "rows":             rows,
        "row_count":        len(rows),
        "colors":           [cr["color_name"] for cr in color_rows],
        "sizes":            sizes,
        "unmapped_colors":  unmapped,
    }


# ═══════════════════════════════════════════════════════════════════════
# ══ ORDER IMPORT FORMAT REGISTRY (Phase G) ═════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# Config-driven registry for ORDER / PICKLIST imports — mirrors the
# listing_format_configs pattern but with an order-specific column-map
# vocabulary. Adding a 4th/5th platform's order-export or picklist-export
# format requires only a new config row, not new code.
#
# Canonical order fields (any platform's file must map to some subset):
#   order_id, order_item_id, shipment_id, order_date, dispatch_by_date
#   leaf_sku, myntra_sku_code, product_title, qty
#   selling_price, invoice_amount, order_state, tracking_id
#   buyer_name, city, state, pincode, bin_barcode
#
# is_picklist=True platforms (e.g. Myntra picklist) may lack order_id
# entirely — the importer derives a picklist_batch_id from the filename.
# ═══════════════════════════════════════════════════════════════════════

ORDER_CANONICAL_FIELDS = [
    "order_id", "order_item_id", "shipment_id",
    "order_date", "dispatch_by_date",
    "leaf_sku", "myntra_sku_code",
    "product_title", "qty",
    "selling_price", "invoice_amount",
    "order_state", "tracking_id",
    "buyer_name", "city", "state", "pincode",
    "bin_barcode",
]

# Canonical DISPATCH fields — what a "packed today" file from any platform
# should be mapped into. Deliberately overlaps with order fields
# (order_id / leaf_sku) so the same resolve_style() + split_leaf_sku()
# pipeline runs against dispatch rows too.
DISPATCH_CANONICAL_FIELDS = [
    "order_id", "order_release_id",
    "leaf_sku", "channel_sku",          # channel_sku = platform's own SKU code (e.g. Myntra SKU code)
    "packed_on", "status",
    "mrp", "selling_value",
    "cgst", "sgst", "igst",
    "tracking_id",
    "destination_city", "destination_state", "destination_pincode",
    "store_packet_id",
    "product_title", "qty",             # qty defaults to 1 per row for dispatch files
]

# Canonical MONTHLY REPORT fields — full lifecycle per order-line.
# Same core identifiers as dispatch (order_id + order_release_id + leaf_sku)
# plus every date column that lets us classify a row's fate:
# packed_on, delivered_on, cancelled_on, rto_creation_date,
# return_creation_date. Plus revenue-side columns for Phase 4 costing.
MONTHLY_REPORT_CANONICAL_FIELDS = [
    "order_id", "order_release_id",
    "leaf_sku", "size", "product_title",
    "order_status",
    "packed_on", "delivered_on", "cancelled_on",
    "rto_creation_date", "return_creation_date",
    "final_amount", "total_mrp", "discount", "seller_price",
]

# ConfigRole distinguishes ORDER/PICKLIST configs (used by the online-orders
# importer) from DISPATCH configs (used by the daily "what got packed today"
# importer). One platform can have BOTH — e.g. Myntra ships an OP-xxxxx.csv
# picklist AND a Packed_order_data.csv dispatch file — so the collection's
# uniqueness key is (platform, role), not platform alone.
ConfigRole = Literal["order", "dispatch", "monthly_report"]


class OrderImportFormatConfigIn(BaseModel):
    platform: Platform
    # "order" (default, backward-compatible) or "dispatch" — a single
    # platform can have both. Immutable after creation.
    role: ConfigRole = "order"
    sheet_locator: SheetLocator
    header_locator: HeaderLocator
    skip_rows_after_header: int = 0
    # canonical field -> actual column name in this platform's file (null when absent)
    column_map: Dict[str, Optional[str]]
    # Non-numeric/non-code prefixes to strip from leaf_sku BEFORE
    # split_leaf_sku()/resolve_style(). Configurable so new platform
    # prefixes (e.g. "TH" for Flipkart) can be added without a code deploy.
    known_sku_prefixes_to_strip: List[str] = Field(default_factory=list)
    # Typo variants to REPLACE (not strip) — e.g. Myntra sometimes ships
    # "FLL_..." for "FL_..." (doubled-L). Runs BEFORE strip. Keys are the
    # wrong token, values the corrected token. Delimiter preserved.
    known_sku_prefix_replacements: Dict[str, str] = Field(default_factory=dict)
    # True for pure-picklist files that have no order_id at all
    # (e.g. Myntra OP-xxxxx.csv). The importer will derive a
    # picklist_batch_id from the filename in that case.
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
    # ── Flipkart Order CSV ──────────────────────────────────────────────
    # Single-sheet CSV / xlsx. Header row 0. SKU column is our own catalogue
    # code but appears in multiple forms in the same file — split_leaf_sku()
    # + strip_known_prefixes() handle the variants without hardcoding.
    # ORDER ITEM ID values can carry a leading apostrophe (Excel text-safety
    # artefact); the importer strips that.
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
        "notes": "Flipkart order-CSV export. SKU column carries multiple naming variants — split_leaf_sku() + strip_known_prefixes() normalise them. Order Item Id may have a leading apostrophe.",
    },
    # ── Myntra Picklist CSV ────────────────────────────────────────────
    # OP-xxxxx.csv style picklist — NO order id, order date, or shipment id.
    # Filename (minus extension) is used as picklist_batch_id. qty can be
    # >1 per row — do NOT assume 1 unit per row.
    {
        "platform": "myntra",
        "sheet_locator": {"type": "first_sheet"},
        "header_locator": {"type": "fixed_row", "row": 0},
        "skip_rows_after_header": 0,
        "column_map": {
            "order_id":         None,     # picklist has no order id
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
        "notes": "Myntra picklist (OP-xxxxx.csv). No order_id — the filename (minus extension) is stored as picklist_batch_id. sellerSkuCode carries multiple naming variants; the doubled-L typo 'FLL_...' is REPLACED with 'FL_...' via known_sku_prefix_replacements (config-driven, no code change).",
    },
    # ── Myntra Daily Dispatch (Packed_order_data.csv) ───────────────────
    # Single clean-header CSV that Myntra emits daily. This is the record
    # of what got PACKED that day — used to decrement ready_stock_qty and
    # release any prior reservation. Distinct from the picklist above:
    # picklist = "what to pull off the shelf next", dispatch = "what
    # actually got packed and shipped".
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
        "notes": "Myntra daily dispatch file (Packed_order_data.csv). Each row = 1 unit packed. Posts a 'dispatched' fg_stock_movement — implicit-reserve fallback covers first-time dispatches where no prior reservation exists. join key across all Myntra files: order_release_id + Seller_sku_code.",
    },
    # ── Myntra Monthly Order Report ──────────────────────────────────────
    # One row per order-line, full lifecycle. Source-of-truth for
    # returns/RTO/cancellations because the daily dispatch file only
    # records packing, not the reversals. Status alone is NOT enough
    # (176 of 281 "F" rows have a packed_on date meaning inventory WAS
    # consumed before cancellation; 748 of 1953 "C" rows have a
    # return_creation_date meaning customer returned it) — classification
    # must combine status + the date columns.
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
        "notes": "Myntra Monthly_order_report.csv. Row-level classification: was_packed (packed_on!=null), was_returned_to_stock (rto_creation_date OR return_creation_date OR (status=F AND was_packed)), is_pending (status in SH/PK), is_net_sold (packed AND !returned AND !pending). Drives return_restocked movements to correct inventory that the daily dispatch file missed.",
    },
]


async def _seed_order_import_configs() -> int:
    """Idempotently seed order_import_format_configs (Phase G + Dispatch).

    Also performs an in-place UPGRADE on any pre-existing seeded config
    that pre-dates a schema addition — currently:
      - backfills `role` = "order" on any legacy row that has no role
      - migrates the uniqueness index from `platform` alone to
        (`platform`, `role`) so a single platform can now hold both an
        order/picklist config AND a dispatch config
      - adds `known_sku_prefix_replacements` (dict) if missing
      - migrates any "FLL" that was still living in `known_sku_prefixes_to_strip`
        (legacy Myntra seed) into `known_sku_prefix_replacements={FLL: FL}`.
    Non-seeded (user-created) configs are NEVER touched.
    """
    # ── Step 1: backfill role on any legacy docs BEFORE creating the
    # composite unique index (else the create_index would fail on
    # duplicate (platform, null) keys).
    await db.order_import_format_configs.update_many(
        {"role": {"$exists": False}}, {"$set": {"role": "order"}}
    )
    # ── Step 2: drop the old platform-only unique index if it exists.
    try:
        idx_info = await db.order_import_format_configs.index_information()
        if "oifc_platform_unique" in idx_info:
            await db.order_import_format_configs.drop_index("oifc_platform_unique")
            log.info("Order import registry: dropped legacy platform-only unique index")
    except Exception as e:
        log.warning(f"Could not inspect/drop legacy index: {e}")
    # ── Step 3: create the composite (platform, role) unique index.
    try:
        await db.order_import_format_configs.create_index(
            [("platform", 1), ("role", 1)],
            unique=True, name="oifc_platform_role_unique",
        )
    except Exception as e:
        log.warning(f"Could not create order_import_format_configs composite index: {e}")
    # ── Step 4: seed / upgrade the default configs.
    inserted = 0
    for cfg in DEFAULT_ORDER_IMPORT_CONFIGS:
        cfg_role = cfg.get("role") or "order"
        existing = await db.order_import_format_configs.find_one(
            {"platform": cfg["platform"], "role": cfg_role}
        )
        if existing:
            # Upgrade path for seeded configs: reconcile with current default
            # if this row was originally seeded (never touch user-created rows).
            if existing.get("seeded"):
                upd: Dict[str, Any] = {}
                if "known_sku_prefix_replacements" not in existing:
                    upd["known_sku_prefix_replacements"] = cfg.get("known_sku_prefix_replacements") or {}
                # Legacy Myntra order-config: FLL was mis-classified as a strip prefix; move it.
                strip_list = list(existing.get("known_sku_prefixes_to_strip") or [])
                if cfg["platform"] == "myntra" and cfg_role == "order" and "FLL" in strip_list:
                    strip_list = [p for p in strip_list if p != "FLL"]
                    upd["known_sku_prefixes_to_strip"] = strip_list
                    reps = dict(existing.get("known_sku_prefix_replacements") or {})
                    reps.setdefault("FLL", "FL")
                    upd["known_sku_prefix_replacements"] = reps
                    upd["notes"] = cfg.get("notes") or existing.get("notes")
                if upd:
                    upd["updated_at"] = now_iso()
                    await db.order_import_format_configs.update_one(
                        {"platform": cfg["platform"], "role": cfg_role}, {"$set": upd}
                    )
                    log.info(f"Order import registry: upgraded seeded config for {cfg['platform']}/{cfg_role}: {list(upd.keys())}")
            continue
        doc = dict(cfg)
        doc["role"]       = cfg_role
        doc["created_at"] = now_iso()
        doc["updated_at"] = now_iso()
        doc["seeded"]     = True
        await db.order_import_format_configs.insert_one(doc)
        inserted += 1
    return inserted


# ── split_leaf_sku helper ────────────────────────────────────────────
# Splits a leaf SKU like "CC-050-BE-8" or "2504-FAKC-001-GO-37" into
# (group_id, size_token, flags). Used both by the listing-import work
# (Phase C) and by the order-import work (this phase) — SAME logic in
# ONE place so a bug fix here propagates to both. Tricky cases:
#   "2504-FAKC-001-GO-37"       → ("2504-FAKC-001-GO", "37", [])
#   "CC-045-BG-4"               → ("CC-045-BG", "4", [])
#   "FL_DB_015_GO_38"           → ("FL_DB_015_GO", "38", [])
#   "SH_CC-051-GO-4"            → ("SH_CC-051-GO", "4", []) — splits validly;
#                                 downstream resolve_style() flags it as
#                                 unresolved if the group isn't in sku_map.
#   "SIZE-BUCKET"               → ("SIZE-BUCKET", None,
#                                  ["group_id_derivation_failed"])
#   ""                          → ("", None, ["empty_leaf_sku"])

DEFAULT_SIZE_LABELS = ["XS", "S", "M", "L", "XL", "XXL", "Free Size", "FreeSize", "FS"]
NUMERIC_SIZE_RE     = re.compile(r"^\d{1,2}$")


def split_leaf_sku(
    leaf_sku: str,
    size_labels: Optional[List[str]] = None,
) -> Tuple[str, Optional[str], List[str]]:
    """Split leaf_sku into (group_id, size_token, flags).

    Strategy: find the LAST "-" or "_" (whichever is closer to the end),
    treat everything after as the candidate size token. Accept only if
    the token matches ^\\d{1,2}$ OR appears in size_labels (case-insensitive).
    Do NOT force a split when the trailing token doesn't look size-like —
    the row gets flagged and routed to the exception queue instead.
    """
    raw = (leaf_sku or "").strip()
    if not raw:
        return "", None, ["empty_leaf_sku"]

    labels = size_labels or DEFAULT_SIZE_LABELS
    labels_lc = {s.lower() for s in labels}

    # Find the rightmost dash/underscore
    last_dash  = raw.rfind("-")
    last_under = raw.rfind("_")
    cut = max(last_dash, last_under)
    if cut <= 0 or cut == len(raw) - 1:
        return raw, None, ["group_id_derivation_failed"]

    head = raw[:cut]
    tail = raw[cut + 1:]

    is_numeric_size = bool(NUMERIC_SIZE_RE.match(tail))
    is_label_size   = tail.lower() in labels_lc

    if is_numeric_size or is_label_size:
        return head, tail, []

    # Trailing token doesn't look size-like — flag rather than guess.
    return raw, None, ["group_id_derivation_failed"]


def strip_known_prefixes(sku: str, prefixes: List[str]) -> Tuple[str, Optional[str]]:
    """Strip the FIRST matching prefix from sku. Returns (stripped, matched_prefix or None).

    Prefixes are tried longest-first so "FLL" wins over "FL" when both are
    configured. Match is case-sensitive to avoid stripping "th" from a
    genuine SKU segment. Also strips a following delimiter ("_" or "-")
    so "TH_FL_DB_015" → "FL_DB_015", not "_FL_DB_015".
    """
    s = (sku or "").strip()
    if not s or not prefixes:
        return s, None
    for pfx in sorted(prefixes, key=len, reverse=True):
        if not pfx:
            continue
        if s.startswith(pfx):
            # Also eat a following underscore/dash so the remainder is a clean SKU
            rest = s[len(pfx):]
            if rest and rest[0] in "_-":
                rest = rest[1:]
            return rest, pfx
    return s, None


def apply_prefix_replacements(sku: str, replacements: Dict[str, str]) -> Tuple[str, Optional[str]]:
    """Rewrite the FIRST matching *token-boundary* prefix.

    Unlike strip_known_prefixes() which removes a leading prefix (plus a
    following delimiter), this REPLACES a leading token — used for
    "typo variants" of a legitimate SKU token (e.g. Myntra's doubled
    "FLL" for the real "FL"). The delimiter is preserved.

    Example:
        apply_prefix_replacements("FLL_AK_005_SL-7", {"FLL": "FL"})
        → ("FL_AK_005_SL-7", "FLL")

    Config-driven so new platform typo variants can be onboarded
    without touching code.
    """
    s = (sku or "").strip()
    if not s or not replacements:
        return s, None
    # Longest key first so "FLLL" would win over "FLL" if both existed.
    for wrong in sorted(replacements.keys(), key=len, reverse=True):
        if not wrong:
            continue
        right = str(replacements.get(wrong) or "")
        if s.startswith(wrong):
            rest = s[len(wrong):]
            # Only treat this as a token-boundary hit if followed by delimiter
            # or end-of-string — avoids clobbering "FLL" that's actually part
            # of a longer legit token like "FLLAT".
            if not rest or rest[0] in "_-":
                return right + rest, wrong
    return s, None


def strip_excel_apostrophe(s: str) -> str:
    """Strip Excel's leading text-safety apostrophe (e.g. \"'4380193...\")."""
    if not s:
        return s
    return s[1:] if s.startswith("'") else s


# ── Config-driven file reader ────────────────────────────────────────
def _resolve_data_sheet_and_header(wb, cfg: dict) -> Tuple[Any, int, List[str]]:
    """Locate the data sheet and the header row per config. Returns
    (sheet, header_row_1_based, header_values_list)."""
    sheet_locator  = cfg.get("sheet_locator")  or {"type": "first_sheet"}
    header_locator = cfg.get("header_locator") or {"type": "fixed_row", "row": 0}

    # Sheet
    if sheet_locator.get("type") == "fixed_name":
        name = (sheet_locator.get("name") or "").strip()
        if name not in wb.sheetnames:
            raise HTTPException(400, f"Expected sheet '{name}' not found in workbook. Sheets: {wb.sheetnames}")
        ws = wb[name]
    elif sheet_locator.get("type") == "name_contains":
        sub = (sheet_locator.get("substring") or "").strip().lower()
        match = next((n for n in wb.sheetnames if sub in n.lower()), None)
        if not match:
            raise HTTPException(400, f"No sheet name contains '{sub}'. Sheets: {wb.sheetnames}")
        ws = wb[match]
    else:
        ws = wb.worksheets[0]

    # Header
    if header_locator.get("type") == "fixed_row":
        hdr_idx = int(header_locator.get("row") or 0)   # 0-based
        header_row_1 = hdr_idx + 1
        header = [str(c.value).strip() if c.value is not None else ""
                  for c in ws[header_row_1]]
    elif header_locator.get("type") == "scan_for_columns":
        needles = [str(x).strip().lower() for x in (header_locator.get("must_contain_any") or []) if x]
        header_row_1 = None
        for r in range(1, min(ws.max_row, 12) + 1):
            cells = [str(c.value).strip() if c.value is not None else "" for c in ws[r]]
            lc = {c.lower() for c in cells}
            if any(n in lc for n in needles):
                header_row_1 = r
                break
        if header_row_1 is None:
            raise HTTPException(
                400,
                f"Header row not found — no row in first 12 contains any of {header_locator.get('must_contain_any')}"
            )
        header = [str(c.value).strip() if c.value is not None else ""
                  for c in ws[header_row_1]]
    else:
        header_row_1 = 1
        header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]

    return ws, header_row_1, header


def _read_workbook_or_csv(content: bytes, filename: str):
    """Return an openpyxl Workbook-like object from either an .xlsx or .csv upload.

    For CSV we build an in-memory single-sheet workbook so the same
    sheet/header locator logic works uniformly. This is deliberate — the
    config schema shouldn't care whether the physical file is xlsx or csv.
    """
    from openpyxl import Workbook, load_workbook
    import io as _io
    import csv as _csv

    name_lc = (filename or "").lower()
    if name_lc.endswith(".csv"):
        # Decode with UTF-8 BOM tolerance, fall back to latin-1
        try:    text = content.decode("utf-8-sig")
        except UnicodeDecodeError: text = content.decode("latin-1")
        wb = Workbook()
        ws = wb.active
        ws.title = "csv"
        reader = _csv.reader(_io.StringIO(text))
        for row in reader:
            ws.append(row)
        return wb
    else:
        return load_workbook(_io.BytesIO(content), data_only=True, read_only=False)


# ── Endpoints (CRUD) ─────────────────────────────────────────────────
@api.get("/order-import-format-configs")
async def list_order_import_configs(
    request: Request,
    active: Optional[bool] = None,
    role: Optional[str] = None,
):
    await get_current_user(request)
    q: Dict[str, Any] = {}
    if active is not None: q["active"] = active
    if role is not None:   q["role"]   = role
    docs = await db.order_import_format_configs.find(q).sort("platform", 1).to_list(1000)
    return [stringify(d) for d in docs]


@api.get("/order-import-format-configs/_meta/canonical-fields")
async def get_order_canonical_fields(request: Request, role: str = "order"):
    await get_current_user(request)
    if role == "dispatch":
        return {"role": "dispatch", "canonical_fields": DISPATCH_CANONICAL_FIELDS}
    if role == "monthly_report":
        return {"role": "monthly_report", "canonical_fields": MONTHLY_REPORT_CANONICAL_FIELDS}
    return {"role": "order", "canonical_fields": ORDER_CANONICAL_FIELDS}


@api.get("/order-import-format-configs/{platform}")
async def get_order_import_config(platform: str, request: Request, role: str = "order"):
    await get_current_user(request)
    doc = await db.order_import_format_configs.find_one(
        {"platform": platform.lower(), "role": role}
    )
    if not doc:
        raise HTTPException(404, f"No {role}-import config for platform '{platform}'")
    return stringify(doc)


@api.post("/order-import-format-configs")
async def create_order_import_config(payload: OrderImportFormatConfigIn, request: Request):
    u = await get_current_user(request); require_roles("admin")(u)
    if await db.order_import_format_configs.find_one(
        {"platform": payload.platform, "role": payload.role}
    ):
        raise HTTPException(
            409,
            f"Config for platform '{payload.platform}' role '{payload.role}' already exists — use PUT to update"
        )
    doc = payload.model_dump()
    doc["created_at"] = now_iso(); doc["updated_at"] = now_iso(); doc["seeded"] = False
    try:
        res = await db.order_import_format_configs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"Config for platform '{payload.platform}' role '{payload.role}' already exists")
    doc.pop("_id", None); doc["id"] = str(res.inserted_id)
    await log_activity("order_import_format.create", "order_import_format_configs",
                       f"Added {payload.role}-import config for {payload.platform}", u["email"])
    return doc


@api.put("/order-import-format-configs/{platform}")
async def update_order_import_config(
    platform: str,
    payload: OrderImportFormatConfigUpdate,
    request: Request,
    role: str = "order",
):
    u = await get_current_user(request); require_roles("admin")(u)
    platform_lc = platform.lower()
    existing = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": role}
    )
    if not existing:
        raise HTTPException(404, f"No {role}-import config for platform '{platform_lc}'")
    update: Dict[str, Any] = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # role is immutable — reject any attempt to change it
    update.pop("role", None)
    if not update:
        return stringify(existing)
    update["updated_at"] = now_iso()
    await db.order_import_format_configs.update_one(
        {"platform": platform_lc, "role": role}, {"$set": update}
    )
    fresh = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": role}
    )
    await log_activity("order_import_format.update", "order_import_format_configs",
                       f"Updated {role}-import config for {platform_lc}: {', '.join(update.keys())}", u["email"])
    return stringify(fresh)


# ── Canonical row parser + full config-driven order import ───────────
async def _parse_and_resolve_order_row(
    raw_row: dict,
    cfg: dict,
    platform: str,
    picklist_batch_id: Optional[str],
) -> dict:
    """Turn one raw row into a canonical order_import record and try to
    resolve the leaf_sku through sku_map / styles.code."""
    column_map: Dict[str, Optional[str]] = cfg.get("column_map") or {}
    prefixes  = cfg.get("known_sku_prefixes_to_strip") or []
    replacements = cfg.get("known_sku_prefix_replacements") or {}

    def _pick(canonical: str) -> str:
        col = column_map.get(canonical)
        if not col:
            return ""
        v = raw_row.get(col)
        if v is None:
            # Try case-insensitive lookup as a fallback
            col_lc = col.lower()
            for k, val in raw_row.items():
                if str(k).strip().lower() == col_lc:
                    v = val
                    break
        return "" if v is None else str(v).strip()

    canon = {
        "platform":          platform,
        "picklist_batch_id": picklist_batch_id,
    }
    for f in ORDER_CANONICAL_FIELDS:
        canon[f] = _pick(f)

    # Strip Excel apostrophe from id-ish fields
    for key in ("order_id", "order_item_id", "shipment_id", "tracking_id"):
        canon[key] = strip_excel_apostrophe(canon.get(key) or "")

    # Qty
    try:    canon["qty"] = int(float(canon.get("qty") or 0))
    except: canon["qty"] = 0

    leaf_raw = canon.get("leaf_sku") or ""
    canon["leaf_sku_raw"] = leaf_raw

    # Normalise sku: strip apostrophe, apply typo-replacements, then strip prefixes.
    # Order matters: FLL→FL replacement runs BEFORE strip so that a config
    # combining both (rare but possible) still normalises consistently.
    leaf = strip_excel_apostrophe(leaf_raw)
    leaf_after_replace, replaced_from = apply_prefix_replacements(leaf, replacements)
    leaf_stripped, matched_prefix = strip_known_prefixes(leaf_after_replace, prefixes)
    canon["leaf_sku_replaced_prefix"] = replaced_from
    canon["leaf_sku_stripped_prefix"] = matched_prefix
    canon["leaf_sku"] = leaf_stripped

    # split into group + size
    group_id, size_token, flags = split_leaf_sku(leaf_stripped)
    canon["group_id"]     = group_id
    canon["derived_size"] = size_token
    canon["flags"]        = list(flags)   # may contain "group_id_derivation_failed" / "empty_leaf_sku"

    # Resolve via existing pipeline: try full leaf_sku first, then group_id,
    # so we hit both sku_map's group-level rows (created by Phase F catalogue
    # export) and any leaf-level manual mappings.
    resolved = {"matched": False, "match_via": None}
    for candidate in (leaf_stripped, group_id):
        if not candidate:
            continue
        r = await resolve_style(
            source_type="online_channel",
            source_name=platform,
            external_sku=candidate,
        )
        if r.get("matched"):
            resolved = r
            resolved["resolved_from"] = candidate
            break

    canon["style_id"]   = resolved.get("style_id")
    canon["style_code"] = resolved.get("style_code")
    canon["match_via"]  = resolved.get("match_via")
    canon["matched"]    = bool(resolved.get("matched"))
    canon["resolved_from"] = resolved.get("resolved_from")

    # Prefer resolved size from sku_map, else the derived size, else the size
    # column from the file (some platforms have a *Size column even when the
    # SKU also embeds it — order-import configs currently don't map size, so
    # this branch mostly defers to derived_size).
    canon["size"] = resolved.get("size") or size_token or canon.get("size", "") or ""
    canon["color"] = resolved.get("color") or ""

    # Reason for exception queue when not matched
    if not canon["matched"]:
        if canon["flags"]:
            canon["exception_reason"] = "; ".join(canon["flags"])
        else:
            canon["exception_reason"] = f"leaf_sku '{leaf_stripped}' (and derived group '{group_id}') not in sku_map / styles"

    # Preserve original row for audit — cast keys to strings and drop None values
    canon["raw_row"] = {str(k): ("" if v is None else str(v)) for k, v in raw_row.items()}
    return canon


class OrderImportConfiguredRequest(BaseModel):
    # Not used — endpoint takes multipart. Kept for OpenAPI clarity.
    pass


@api.post("/online-orders/import-configured", dependencies=[Depends(upload_rate_limiter)])
async def import_online_orders_configured(
    file: UploadFile = File(...),
    platform: str = "flipkart",
    dry_run: bool = True,
    request: Request = None,
):
    """Config-driven order/picklist import. Uses order_import_format_configs
    to locate the sheet + header + map columns → canonical order_import
    schema. Resolves each row's leaf_sku via sku_map/styles.code (with
    prefix stripping + size-token derivation).

    Query params:
      - platform  : which config to use (e.g. 'flipkart', 'myntra')
      - dry_run   : if true (default), returns the parsed preview WITHOUT
                    persisting to online_orders / online_order_items.
                    Set to false to commit.

    Returns a summary + list of canonical rows.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)

    platform_lc = (platform or "").strip().lower()
    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "order"}
    )
    if not cfg_doc:
        raise HTTPException(
            400,
            f"No order-import config for platform '{platform_lc}'. "
            "Create one via POST /api/order-import-format-configs first."
        )
    if not cfg_doc.get("active", True):
        raise HTTPException(400, f"Order-import config for '{platform_lc}' is inactive.")

    cfg = stringify(cfg_doc)

    # Read file
    content = await file.read()
    filename = file.filename or "upload"
    picklist_batch_id: Optional[str] = None
    if cfg.get("is_picklist"):
        # Derive from filename stem (spec: "OP20625445.csv" → "OP20625445")
        stem = filename.rsplit(".", 1)[0].strip()
        picklist_batch_id = stem or "unnamed_picklist"

    wb = _read_workbook_or_csv(content, filename)
    ws, header_row_1, header = _resolve_data_sheet_and_header(wb, cfg)
    skip = int(cfg.get("skip_rows_after_header") or 0)

    first_data_row_1 = header_row_1 + 1 + skip

    canonical_rows: List[dict] = []
    stats = {
        "total_rows_read":            0,
        "matched":                    0,
        "unmatched":                  0,
        "derivation_failed":          0,
        "empty_leaf_sku":             0,
        "order_style_rows":           0,   # rows with an order_id
        "picklist_rows":              0,   # rows with no order_id (or is_picklist config)
        "distinct_orders":            0,
    }
    order_ids_seen: set = set()

    for r_idx in range(first_data_row_1, ws.max_row + 1):
        row_cells = [ws.cell(row=r_idx, column=c).value for c in range(1, len(header) + 1)]
        # skip totally blank rows
        if all((v is None or (isinstance(v, str) and not v.strip())) for v in row_cells):
            continue
        raw_row = {header[i]: row_cells[i] for i in range(len(header)) if header[i]}
        canon = await _parse_and_resolve_order_row(raw_row, cfg, platform_lc, picklist_batch_id)
        canon["source_row_index"] = r_idx    # 1-based row in the actual sheet
        canonical_rows.append(canon)

        stats["total_rows_read"] += 1
        if canon["matched"]:            stats["matched"]           += 1
        else:                           stats["unmatched"]         += 1
        if "group_id_derivation_failed" in canon["flags"]:
            stats["derivation_failed"] += 1
        if "empty_leaf_sku" in canon["flags"]:
            stats["empty_leaf_sku"]    += 1
        if canon.get("order_id"):
            stats["order_style_rows"] += 1
            order_ids_seen.add(canon["order_id"])
        else:
            stats["picklist_rows"]    += 1

    stats["distinct_orders"] = len(order_ids_seen)

    # ── Commit path ─────────────────────────────────────────────────
    committed = {"orders_created": 0, "items_created": 0, "exceptions_queued": 0}
    import_batch_id = None
    if not dry_run:
        import_batch_id = f"IMP_{platform_lc}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        # Group rows by order_id (or by picklist_batch_id for picklist-mode)
        orders_by_key: Dict[str, dict] = {}
        exceptions: List[dict] = []
        for canon in canonical_rows:
            group_key = canon.get("order_id") or picklist_batch_id or f"orphan_{canon['source_row_index']}"
            if group_key not in orders_by_key:
                orders_by_key[group_key] = {
                    "platform":          platform_lc,
                    "order_id":          canon.get("order_id"),
                    "picklist_batch_id": canon.get("picklist_batch_id"),
                    "order_date":        canon.get("order_date"),
                    "dispatch_by_date":  canon.get("dispatch_by_date"),
                    "buyer_name":        canon.get("buyer_name"),
                    "city":              canon.get("city"),
                    "state":             canon.get("state"),
                    "pincode":           canon.get("pincode"),
                    "items":             [],
                    "import_batch_id":   import_batch_id,
                    "created_at":        now_iso(),
                    "updated_at":        now_iso(),
                    "created_by":        u["email"],
                }
            item_doc = {
                "order_item_id":     canon.get("order_item_id"),
                "shipment_id":       canon.get("shipment_id"),
                "leaf_sku_raw":      canon.get("leaf_sku_raw"),
                "leaf_sku":          canon.get("leaf_sku"),
                "leaf_sku_stripped_prefix": canon.get("leaf_sku_stripped_prefix"),
                "leaf_sku_replaced_prefix": canon.get("leaf_sku_replaced_prefix"),
                "group_id":          canon.get("group_id"),
                "myntra_sku_code":   canon.get("myntra_sku_code"),
                "product_title":     canon.get("product_title"),
                "qty":               canon.get("qty"),
                "selling_price":     canon.get("selling_price"),
                "invoice_amount":    canon.get("invoice_amount"),
                "order_state":       canon.get("order_state"),
                "tracking_id":       canon.get("tracking_id"),
                "bin_barcode":       canon.get("bin_barcode"),
                "style_id":          canon.get("style_id"),
                "style_code":        canon.get("style_code"),
                "size":              canon.get("size"),
                "color":             canon.get("color"),
                "match_via":         canon.get("match_via"),
                "matched":           canon.get("matched"),
                "resolved_from":     canon.get("resolved_from"),
                "flags":             canon.get("flags"),
                "exception_reason":  canon.get("exception_reason"),
                "source_row_index":  canon.get("source_row_index"),
                "raw_row":           canon.get("raw_row"),
            }
            orders_by_key[group_key]["items"].append(item_doc)
            if not canon.get("matched"):
                exceptions.append({
                    "import_batch_id": import_batch_id,
                    "platform":         platform_lc,
                    "order_id":         canon.get("order_id"),
                    "picklist_batch_id":canon.get("picklist_batch_id"),
                    "leaf_sku_raw":     canon.get("leaf_sku_raw"),
                    "leaf_sku":         canon.get("leaf_sku"),
                    "group_id":         canon.get("group_id"),
                    "qty":              canon.get("qty"),
                    "reason":           canon.get("exception_reason"),
                    "flags":            canon.get("flags"),
                    "raw_row":          canon.get("raw_row"),
                    "created_at":       now_iso(),
                    "resolved":         False,
                })

        for group_key, order_doc in orders_by_key.items():
            # Denormalise items into embedded array — small enough per order.
            res = await db.online_orders.insert_one(order_doc)
            committed["orders_created"] += 1
            committed["items_created"]  += len(order_doc["items"])
            # Also insert each item as a top-level row for easy filtering later
            for it in order_doc["items"]:
                it["online_order_id"] = res.inserted_id
                it["platform"]        = platform_lc
                it["import_batch_id"] = import_batch_id
                it["created_at"]      = now_iso()
                await db.online_order_items.insert_one(it)

        if exceptions:
            await db.online_order_exceptions.insert_many(exceptions)
            committed["exceptions_queued"] = len(exceptions)

        await log_activity(
            "IMPORT_CONFIGURED", "online_orders",
            f"{platform_lc}: {committed['orders_created']} orders, "
            f"{committed['items_created']} items, "
            f"{committed['exceptions_queued']} exceptions "
            f"(batch {import_batch_id})",
            u["email"],
        )

    return {
        "platform":          platform_lc,
        "is_picklist":       bool(cfg.get("is_picklist")),
        "picklist_batch_id": picklist_batch_id,
        "filename":          filename,
        "header_row_1_based":header_row_1,
        "header":            header,
        "dry_run":           dry_run,
        "stats":             stats,
        "committed":         committed if not dry_run else None,
        "import_batch_id":   import_batch_id,
        "rows":              canonical_rows,
    }


# ═══════════════════════════════════════════════════════════════════════
# ══ DISPATCH IMPORT (Phase H — daily "what got packed today") ══════════
# ═══════════════════════════════════════════════════════════════════════
# Uses the same order_import_format_configs collection with role="dispatch".
# Each parsed row → 1 unit dispatched → decrement ready_stock_qty and,
# if a prior reservation exists for that (order_release_id, style, color,
# size), release it. If no reservation exists (Myntra's dispatch file is
# often the FIRST record of a unit), an implicit "reserved" movement is
# posted first so the inventory ledger stays honest.
# ═══════════════════════════════════════════════════════════════════════

async def _parse_and_resolve_dispatch_row(
    raw_row: dict,
    cfg: dict,
    platform: str,
    source_row_index: int,
) -> dict:
    """Parse one row of a dispatch file into canonical form + resolve style.

    Mirrors _parse_and_resolve_order_row() but for dispatch canonical
    fields. Reuses the SAME normalisation pipeline (strip_excel_apostrophe
    → apply_prefix_replacements → strip_known_prefixes → split_leaf_sku →
    resolve_style) so there's no second parser to maintain.
    """
    column_map: Dict[str, Optional[str]] = cfg.get("column_map") or {}
    prefixes     = cfg.get("known_sku_prefixes_to_strip") or []
    replacements = cfg.get("known_sku_prefix_replacements") or {}

    def _v(canon_key: str):
        col = column_map.get(canon_key)
        return raw_row.get(col) if col else None

    canon: Dict[str, Any] = {
        "source_row_index": source_row_index,
        "platform":         platform,
        "raw_row":          {k: (str(v) if v is not None else "") for k, v in raw_row.items()},
        "flags":            [],
        "matched":          False,
    }

    # Header identifiers — order_id + order_release_id.
    order_id = str(_v("order_id") or "").strip()
    order_release_id = str(_v("order_release_id") or "").strip()
    canon["order_id"] = order_id or None
    canon["order_release_id"] = order_release_id or None

    # Descriptive channel-side fields
    canon["channel_sku"]         = str(_v("channel_sku") or "").strip() or None
    canon["packed_on"]           = str(_v("packed_on") or "").strip() or None
    canon["status"]              = str(_v("status") or "").strip() or None
    canon["tracking_id"]         = str(_v("tracking_id") or "").strip() or None
    canon["destination_city"]    = str(_v("destination_city") or "").strip() or None
    canon["destination_state"]   = str(_v("destination_state") or "").strip() or None
    canon["destination_pincode"] = str(_v("destination_pincode") or "").strip() or None
    canon["store_packet_id"]     = str(_v("store_packet_id") or "").strip() or None
    canon["product_title"]       = str(_v("product_title") or "").strip() or None

    def _num(x) -> Optional[float]:
        try:
            s = str(x or "").strip()
            if not s: return None
            return float(s)
        except Exception:
            return None
    canon["mrp"]           = _num(_v("mrp"))
    canon["selling_value"] = _num(_v("selling_value"))
    canon["cgst"]          = _num(_v("cgst"))
    canon["sgst"]          = _num(_v("sgst"))
    canon["igst"]          = _num(_v("igst"))

    # qty — dispatch files default to 1 unit per row unless the file
    # explicitly maps a qty column.
    qty_raw = _v("qty")
    try:
        qty = int(float(str(qty_raw or "1").strip() or "1"))
        if qty <= 0: qty = 1
    except Exception:
        qty = 1
    canon["qty"] = qty

    # ── leaf_sku normalisation (identical pipeline to order-import) ──
    leaf_raw = str(_v("leaf_sku") or "").strip()
    canon["leaf_sku_raw"] = leaf_raw
    if not leaf_raw:
        canon["flags"].append("empty_leaf_sku")
        canon["leaf_sku"] = ""
        canon["leaf_sku_replaced_prefix"] = None
        canon["leaf_sku_stripped_prefix"] = None
        canon["exception_reason"] = "leaf_sku column is empty"
        return canon

    leaf = strip_excel_apostrophe(leaf_raw)
    leaf_after_replace, replaced_from = apply_prefix_replacements(leaf, replacements)
    leaf_stripped, matched_prefix = strip_known_prefixes(leaf_after_replace, prefixes)
    canon["leaf_sku_replaced_prefix"] = replaced_from
    canon["leaf_sku_stripped_prefix"] = matched_prefix
    canon["leaf_sku"] = leaf_stripped

    group_id, size_tok, split_flags = split_leaf_sku(leaf_stripped)
    canon["group_id"]     = group_id
    canon["derived_size"] = size_tok
    canon["flags"].extend(split_flags)

    if not group_id or not size_tok:
        canon["exception_reason"] = f"could not split leaf_sku '{leaf_stripped}' into group+size"
        return canon

    # Try both leaf and group candidates via sku_map (same pattern as order-import)
    resolved = {"matched": False, "match_via": None}
    for candidate in (leaf_stripped, group_id):
        if not candidate:
            continue
        r = await resolve_style(
            source_type="online_channel",
            source_name=platform,
            external_sku=candidate,
        )
        if r.get("matched"):
            resolved = r
            break
    canon.update({
        "matched":       bool(resolved.get("matched")),
        "match_via":     resolved.get("match_via"),
        "style_id":      resolved.get("style_id"),
        "style_code":    resolved.get("style_code"),
        "color":         resolved.get("color") or "",
        "size":          resolved.get("size") or size_tok,
    })
    if not canon["matched"]:
        canon["exception_reason"] = resolved.get("reason") or "no style match in sku_map"
    return canon


async def _dispatch_one_unit(
    *,
    style_id: str,
    style_code: str,
    color: str,
    size: str,
    online_order_id: Optional[str],
    reference_id: str,
    notes: str,
    user_email: str,
) -> Dict[str, Any]:
    """Post a 'dispatched' fg_stock_movement for exactly 1 unit.

    If NO active reservation exists for the (online_order_id, style,
    color, size) tuple, an implicit 'reserved' movement is posted first
    so that the subsequent 'dispatched' delta (-1 reserved, -1 ready)
    doesn't push reserved_qty below zero. Keeps the ledger honest for
    first-time Myntra dispatches where the unit was never explicitly
    reserved.
    """
    fg_row = await db.fg_inventory.find_one({
        "style_id": ObjectId(style_id), "color": color, "size": size,
    })
    ready_qty = int((fg_row or {}).get("ready_stock_qty", 0))

    if online_order_id:
        existing_res = await db.inventory_reservations.find_one({
            "online_order_id": online_order_id,
            "style_id":        ObjectId(style_id),
            "color":           color,
            "size":            size,
            "status":          "active",
        })
    else:
        existing_res = None

    outcome = {"implicit_reserve": False, "dispatched": False}

    if not existing_res:
        if ready_qty < 1:
            raise HTTPException(
                400,
                f"Insufficient ready_stock_qty (have {ready_qty}) for "
                f"{style_code} / {color} / {size} — cannot implicit-reserve for dispatch."
            )
        await _apply_movement(
            FgStockMovementIn(
                style_id=style_id, color=color, size=size,
                movement_type="reserved", quantity=1,
                reference_type="online_order" if online_order_id else "manual",
                reference_id=reference_id,
                notes=f"implicit reserve for dispatch — {notes}",
                online_order_id=online_order_id,
            ),
            user_email,
        )
        outcome["implicit_reserve"] = True

    await _apply_movement(
        FgStockMovementIn(
            style_id=style_id, color=color, size=size,
            movement_type="dispatched", quantity=1,
            reference_type="online_order" if online_order_id else "manual",
            reference_id=reference_id, notes=notes,
            online_order_id=online_order_id,
        ),
        user_email,
    )
    outcome["dispatched"] = True
    return outcome


@api.post("/online-orders/dispatch-import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_dispatch_configured(
    request: Request,
    file: UploadFile = File(...),
    platform: str = Query(..., description="e.g. 'myntra'"),
    dry_run: bool = Query(True, description="Preview parse without touching inventory"),
):
    """Config-driven DISPATCH import (Phase H).

    - platform : looked up in order_import_format_configs (role="dispatch")
    - dry_run  : true → parse + resolve + would-succeed check, NO writes
                 false → also post fg_stock_movements + upsert online_orders

    Each row = 1 unit's worth of dispatch → decrement ready_stock_qty
    (and release matching reservation) OR flag as exception if
    inventory is insufficient / SKU unresolved.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)

    platform_lc = (platform or "").strip().lower()
    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "dispatch"}
    )
    if not cfg_doc:
        raise HTTPException(
            400,
            f"No dispatch-import config for platform '{platform_lc}'. "
            "Create one via POST /api/order-import-format-configs with role='dispatch' first."
        )
    if not cfg_doc.get("active", True):
        raise HTTPException(400, f"Dispatch-import config for '{platform_lc}' is inactive.")

    cfg = stringify(cfg_doc)

    content = await file.read()
    filename = file.filename or "upload"

    try:
        wb = _read_workbook_or_csv(content, filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")

    ws, header_row_1, header = _resolve_data_sheet_and_header(wb, cfg)
    skip_after = int(cfg.get("skip_rows_after_header") or 0)
    data_start_row = header_row_1 + 1 + skip_after

    raw_rows: List[Dict[str, Any]] = []
    for r in range(data_start_row, ws.max_row + 1):
        row_cells = ws[r]
        vals = {header[i]: (row_cells[i].value if i < len(row_cells) else None)
                for i in range(len(header)) if header[i]}
        if not any((v not in (None, "", " ")) for v in vals.values()):
            continue
        raw_rows.append(vals)

    canonical_rows: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_rows, start=data_start_row):
        canon = await _parse_and_resolve_dispatch_row(raw, cfg, platform_lc, idx)
        canonical_rows.append(canon)

    stats = {
        "total_rows_read":         len(canonical_rows),
        "matched":                 sum(1 for c in canonical_rows if c.get("matched")),
        "unmatched":               sum(1 for c in canonical_rows if not c.get("matched")),
        "empty_leaf_sku":          sum(1 for c in canonical_rows if "empty_leaf_sku" in (c.get("flags") or [])),
        "distinct_order_releases": len({c.get("order_release_id") for c in canonical_rows if c.get("order_release_id")}),
    }

    import_batch_id = f"DISP_{platform_lc}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    committed: Dict[str, int] = {
        "movements_posted":   0,
        "implicit_reserves":  0,
        "already_dispatched": 0,
        "orders_upserted":    0,
        "items_upserted":     0,
        "exceptions_queued":  0,
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
                    "kind":             "dispatch_import",
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
            size       = canon["size"]
            qty        = int(canon.get("qty") or 1)

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
                    "order_status":        "dispatched",
                    "source":              "dispatch_import",
                    "packed_on":           canon.get("packed_on"),
                    "tracking_id":         canon.get("tracking_id"),
                    "destination_city":    canon.get("destination_city"),
                    "destination_state":   canon.get("destination_state"),
                    "destination_pincode": canon.get("destination_pincode"),
                    "buyer_name":          None,
                    "import_batch_id":     import_batch_id,
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
                        "order_status":  "dispatched",
                        "packed_on":     canon.get("packed_on") or existing_order.get("packed_on"),
                        "tracking_id":   canon.get("tracking_id") or existing_order.get("tracking_id"),
                        "updated_at":    now_iso(),
                    }}
                )

            item_q: Dict[str, Any] = {
                "online_order_id": ObjectId(online_order_pk),
                "style_id":        ObjectId(style_id),
                "color":           color,
                "size":            size,
            }
            existing_item = await db.online_order_items.find_one(item_q)
            if existing_item and (existing_item.get("stage") == "dispatched" or existing_item.get("dispatched_at")):
                committed["already_dispatched"] += 1
                canon["_committed"] = {"already_dispatched": True}
                continue

            posted = 0; implicit = 0
            try:
                for _ in range(qty):
                    outcome = await _dispatch_one_unit(
                        style_id=style_id, style_code=style_code, color=color, size=size,
                        online_order_id=online_order_pk,
                        reference_id=order_release_id or order_id or import_batch_id,
                        notes=f"{platform_lc} dispatch import · row {src_row}"
                              + (f" · tracking {canon.get('tracking_id')}" if canon.get('tracking_id') else ""),
                        user_email=u["email"],
                    )
                    posted += 1
                    if outcome["implicit_reserve"]:
                        implicit += 1
            except HTTPException as he:
                exceptions.append({
                    "import_batch_id":  import_batch_id,
                    "platform":         platform_lc,
                    "kind":             "dispatch_import",
                    "source_row_index": src_row,
                    "order_id":         order_id,
                    "order_release_id": order_release_id,
                    "style_id":         style_id,
                    "style_code":       style_code,
                    "color":            color,
                    "size":             size,
                    "leaf_sku":         canon.get("leaf_sku"),
                    "reason":           f"movement blocked: {he.detail}",
                    "raw_row":          canon.get("raw_row"),
                    "created_at":       now_iso(),
                    "resolved":         False,
                })
                canon["_committed"] = {"error": str(he.detail)}
                continue

            committed["movements_posted"]  += posted
            committed["implicit_reserves"] += implicit

            item_doc = {
                "online_order_id":  ObjectId(online_order_pk),
                "platform":         platform_lc,
                "order_id":         order_id,
                "order_release_id": order_release_id,
                "style_id":         ObjectId(style_id),
                "style_code":       style_code,
                "color":            color,
                "size":             size,
                "leaf_sku":         canon.get("leaf_sku"),
                "leaf_sku_raw":     canon.get("leaf_sku_raw"),
                "channel_sku":      canon.get("channel_sku"),
                "qty":              qty,
                "stage":            "dispatched",
                "packed_on":        canon.get("packed_on"),
                "dispatched_at":    now_iso(),
                "tracking_id":      canon.get("tracking_id"),
                "store_packet_id":  canon.get("store_packet_id"),
                "mrp":              canon.get("mrp"),
                "selling_value":    canon.get("selling_value"),
                "import_batch_id":  import_batch_id,
                "source":           "dispatch_import",
            }
            if existing_item:
                await db.online_order_items.update_one(
                    {"_id": existing_item["_id"]},
                    {"$set": {**item_doc, "updated_at": now_iso()}}
                )
            else:
                item_doc["created_at"] = now_iso()
                await db.online_order_items.insert_one(item_doc)
            committed["items_upserted"] += 1
            canon["_committed"] = {
                "movements_posted":  posted,
                "implicit_reserves": implicit,
                "online_order_id":   online_order_pk,
            }

        if exceptions:
            await db.online_order_exceptions.insert_many(exceptions)
            committed["exceptions_queued"] = len(exceptions)

        await log_activity(
            "DISPATCH_IMPORT", "online_orders",
            f"{platform_lc}: {committed['movements_posted']} units dispatched, "
            f"{committed['implicit_reserves']} implicit reserves, "
            f"{committed['already_dispatched']} already-dispatched skipped, "
            f"{committed['exceptions_queued']} exceptions "
            f"(batch {import_batch_id})",
            u["email"],
        )

        # ── Phase 4 auto-materialise: refresh online_profitability_daily
        # for the packing-date range this dispatch file covered.
        try:
            packed_dates = [c.get("packed_on") for c in canonical_rows if c.get("packed_on")]
            if packed_dates:
                d_from = min(packed_dates)[:10]
                d_to   = max(packed_dates)[:10]
                summary = await _materialise_profitability_range(
                    platform=platform_lc, date_from=d_from, date_to=d_to,
                )
                committed["profitability_rollup"] = summary
        except Exception as e:
            log.warning(f"Auto-materialise profitability failed after dispatch import: {e}")

    return {
        "platform":           platform_lc,
        "role":               "dispatch",
        "filename":           filename,
        "header_row_1_based": header_row_1,
        "header":             header,
        "dry_run":            dry_run,
        "stats":              stats,
        "committed":          committed if not dry_run else None,
        "import_batch_id":    import_batch_id,
        "rows":               canonical_rows,
    }


# ═══════════════════════════════════════════════════════════════════════
# ══ MONTHLY REPORT IMPORT (Phase 2 — inventory reconciliation) ═════════
# ═══════════════════════════════════════════════════════════════════════
# The monthly report is source-of-truth for RETURNS, RTO and CANCELLATIONS
# because the daily dispatch file only records packing, not the reversals.
#
# Classification per row (do NOT simplify to "status == C means sold"):
#   was_packed = packed_on is not null
#   was_returned_to_stock = rto_creation_date IS NOT NULL
#                        OR return_creation_date IS NOT NULL
#                        OR (order_status == "F" AND was_packed)
#   is_pending = order_status in ("SH", "PK")
#   is_net_sold = was_packed AND NOT was_returned_to_stock AND NOT is_pending
#   never_touched_inventory = NOT was_packed
#
# For every was_returned_to_stock row where no prior return movement
# exists (checked by reference_id), we post an implicit "return_in"
# (increment return_qty) then a "return_restocked" (move that unit from
# return_qty back to ready_stock_qty). Phase 3 will override this to
# "return_damaged" when the settlement file's return_type flags damage.
# ═══════════════════════════════════════════════════════════════════════


def _has_val(v: Any) -> bool:
    """True iff v is a non-empty, non-'null' string / non-null value.

    Monthly report exports often carry the literal strings 'null', 'nan',
    'None', '-' for empty date columns. Treat those as absent.
    """
    if v is None: return False
    s = str(v).strip()
    if not s: return False
    if s.lower() in ("null", "nan", "none", "n/a", "na", "-"): return False
    return True


def _classify_monthly_row(canon: dict) -> dict:
    """Apply the EXACT classification logic from the spec.

    Returns the same canon dict with was_packed, was_returned_to_stock,
    is_pending, is_net_sold, never_touched_inventory, return_reason set.
    """
    status = (canon.get("order_status") or "").strip().upper()

    was_packed = _has_val(canon.get("packed_on"))
    has_rto    = _has_val(canon.get("rto_creation_date"))
    has_return = _has_val(canon.get("return_creation_date"))
    cancelled_post_pack = (status == "F" and was_packed)

    was_returned_to_stock = has_rto or has_return or cancelled_post_pack
    is_pending    = status in ("SH", "PK")
    is_net_sold   = was_packed and not was_returned_to_stock and not is_pending
    never_touched = not was_packed

    # Which reversal reason applies? RTO wins over customer_return wins
    # over cancelled_after_pack (RTO is the most severe from an inventory
    # accounting standpoint — the unit was shipped, never delivered, and
    # returned to warehouse without customer touching it).
    if was_returned_to_stock:
        if   has_rto:              reason = "rto"
        elif has_return:           reason = "customer_return"
        elif cancelled_post_pack:  reason = "cancelled_after_pack"
        else:                      reason = "unknown"
    else:
        reason = None

    canon["was_packed"]              = was_packed
    canon["was_returned_to_stock"]   = was_returned_to_stock
    canon["is_pending"]              = is_pending
    canon["is_net_sold"]             = is_net_sold
    canon["never_touched_inventory"] = never_touched
    canon["return_reason"]           = reason
    return canon


async def _parse_and_resolve_monthly_row(
    raw_row: dict,
    cfg: dict,
    platform: str,
    source_row_index: int,
) -> dict:
    """Parse one row of a monthly-report file into canonical form + classify.

    Reuses the identical normalisation pipeline as order-import and
    dispatch-import (strip_excel_apostrophe → apply_prefix_replacements
    → strip_known_prefixes → split_leaf_sku → resolve_style). Then
    applies the classification logic above.
    """
    column_map: Dict[str, Optional[str]] = cfg.get("column_map") or {}
    prefixes     = cfg.get("known_sku_prefixes_to_strip") or []
    replacements = cfg.get("known_sku_prefix_replacements") or {}

    def _v(canon_key: str):
        col = column_map.get(canon_key)
        return raw_row.get(col) if col else None

    def _str(k: str) -> Optional[str]:
        s = str(_v(k) or "").strip()
        return s if s else None

    def _num(k: str) -> Optional[float]:
        try:
            s = str(_v(k) or "").strip()
            if not s or not _has_val(s): return None
            return float(s)
        except Exception:
            return None

    canon: Dict[str, Any] = {
        "source_row_index": source_row_index,
        "platform":         platform,
        "raw_row":          {k: (str(v) if v is not None else "") for k, v in raw_row.items()},
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

    # ── Classify (does NOT depend on leaf_sku resolution) ──
    _classify_monthly_row(canon)

    # ── Then normalise leaf_sku (same as everywhere) ──
    leaf_raw = str(_v("leaf_sku") or "").strip()
    canon["leaf_sku_raw"] = leaf_raw
    if not leaf_raw:
        canon["flags"].append("empty_leaf_sku")
        canon["leaf_sku"] = ""
        canon["leaf_sku_replaced_prefix"] = None
        canon["leaf_sku_stripped_prefix"] = None
        canon["exception_reason"] = "leaf_sku column is empty"
        return canon

    leaf = strip_excel_apostrophe(leaf_raw)
    leaf_after_replace, replaced_from = apply_prefix_replacements(leaf, replacements)
    leaf_stripped, matched_prefix = strip_known_prefixes(leaf_after_replace, prefixes)
    canon["leaf_sku_replaced_prefix"] = replaced_from
    canon["leaf_sku_stripped_prefix"] = matched_prefix
    canon["leaf_sku"] = leaf_stripped

    group_id, size_tok, split_flags = split_leaf_sku(leaf_stripped)
    canon["group_id"]     = group_id
    canon["derived_size"] = size_tok
    canon["flags"].extend(split_flags)

    if not group_id or not size_tok:
        canon["exception_reason"] = f"could not split leaf_sku '{leaf_stripped}' into group+size"
        return canon

    resolved = {"matched": False, "match_via": None}
    for candidate in (leaf_stripped, group_id):
        if not candidate:
            continue
        r = await resolve_style(
            source_type="online_channel",
            source_name=platform,
            external_sku=candidate,
        )
        if r.get("matched"):
            resolved = r
            break
    canon.update({
        "matched":    bool(resolved.get("matched")),
        "match_via":  resolved.get("match_via"),
        "style_id":   resolved.get("style_id"),
        "style_code": resolved.get("style_code"),
        "color":      resolved.get("color") or "",
        "size":       resolved.get("size") or (canon.get("size") or size_tok),
    })
    if not canon["matched"]:
        canon["exception_reason"] = resolved.get("reason") or "no style match in sku_map"
    return canon


def _return_ref_id(platform: str, order_release_id: Optional[str],
                   order_id: Optional[str], leaf_sku: str) -> str:
    """Stable reference_id used to idempotency-check return movements."""
    key = order_release_id or order_id or "no-order"
    return f"monthly_return:{platform}:{key}:{leaf_sku}"


async def _get_settlement_return_type(order_release_id: Optional[str],
                                      leaf_sku: str) -> Optional[str]:
    """Best-effort check into settlement_reverse_settled (Phase 3, may not
    exist yet). Returns 'damaged' if a settlement row for this order/sku
    flags the return as damaged/unsellable — else None.

    Safe to call before Phase 3 is built: if the collection doesn't
    exist, motor simply returns no matches and we default to restock.
    """
    if not order_release_id: return None
    try:
        doc = await db.settlement_reverse.find_one({
            "order_release_id": order_release_id,
            "$or": [{"leaf_sku": leaf_sku}, {"sku_id": leaf_sku}],
        })
    except Exception:
        return None
    if not doc: return None
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
) -> dict:
    """Post return movements for a monthly-report row that came back.

    Idempotent: if a prior return movement exists for the same
    reference_id, skip (returns {"skipped": True}). Otherwise posts
    "return_in" then either "return_restocked" or "return_damaged"
    depending on the settlement file's return_type (Phase 3 hook).
    """
    style_id   = canon["style_id"]
    style_code = canon["style_code"]
    color      = canon["color"]
    size       = canon.get("size") or canon.get("derived_size")
    order_id   = canon.get("order_id")
    order_release_id = canon.get("order_release_id")
    leaf_sku   = canon.get("leaf_sku")

    ref_id = _return_ref_id(platform, order_release_id, order_id, leaf_sku)

    # Idempotency: check if we already posted a return movement for this row
    prior = await db.fg_stock_movements.find_one({
        "reference_id":  ref_id,
        "movement_type": {"$in": ["return_in", "return_restocked", "return_damaged"]},
    })
    if prior:
        return {"skipped": True, "reason": "prior_movement_exists"}

    settlement_flag = await _get_settlement_return_type(order_release_id, leaf_sku)
    close_type = "return_damaged" if settlement_flag == "damaged" else "return_restocked"

    # Post return_in first (implicit — the item physically came back).
    await _apply_movement(
        FgStockMovementIn(
            style_id=style_id, color=color, size=size,
            movement_type="return_in", quantity=1,
            reference_type="online_order",
            reference_id=ref_id,
            notes=f"[{platform}] monthly-report {canon.get('return_reason')} · batch {batch_id}",
        ),
        user_email,
    )
    # Then close it — restocked or damaged.
    await _apply_movement(
        FgStockMovementIn(
            style_id=style_id, color=color, size=size,
            movement_type=close_type, quantity=1,
            reference_type="online_order",
            reference_id=ref_id,
            notes=f"[{platform}] monthly-report reconciliation · reason={canon.get('return_reason')}",
        ),
        user_email,
    )
    return {"skipped": False, "close_type": close_type}


@api.post("/online-orders/monthly-report-import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_monthly_report(
    request: Request,
    file: UploadFile = File(...),
    platform: str = Query(..., description="e.g. 'myntra'"),
    dry_run: bool = Query(True, description="Preview classification without touching inventory"),
):
    """Config-driven MONTHLY REPORT import (Phase 2 — reconciliation).

    Parses the full monthly order-status file, classifies each row
    (was_packed / was_returned_to_stock / is_pending / is_net_sold),
    and for every was_returned_to_stock row posts return_in +
    return_restocked (or return_damaged if Phase 3's settlement file
    marked the return as damaged) — subject to idempotency check.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)

    platform_lc = (platform or "").strip().lower()
    cfg_doc = await db.order_import_format_configs.find_one(
        {"platform": platform_lc, "role": "monthly_report"}
    )
    if not cfg_doc:
        raise HTTPException(
            400,
            f"No monthly-report config for platform '{platform_lc}'. "
            "Create one via POST /api/order-import-format-configs with role='monthly_report' first."
        )
    if not cfg_doc.get("active", True):
        raise HTTPException(400, f"Monthly-report config for '{platform_lc}' is inactive.")

    cfg = stringify(cfg_doc)

    content = await file.read()
    filename = file.filename or "upload"

    try:
        wb = _read_workbook_or_csv(content, filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")

    ws, header_row_1, header = _resolve_data_sheet_and_header(wb, cfg)
    skip_after = int(cfg.get("skip_rows_after_header") or 0)
    data_start_row = header_row_1 + 1 + skip_after

    raw_rows: List[Dict[str, Any]] = []
    for r in range(data_start_row, ws.max_row + 1):
        row_cells = ws[r]
        vals = {header[i]: (row_cells[i].value if i < len(row_cells) else None)
                for i in range(len(header)) if header[i]}
        if not any((v not in (None, "", " ")) for v in vals.values()):
            continue
        raw_rows.append(vals)

    canonical_rows: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_rows, start=data_start_row):
        canon = await _parse_and_resolve_monthly_row(raw, cfg, platform_lc, idx)
        canonical_rows.append(canon)

    # ── Funnel stats + reason breakdown ──
    def _count(pred) -> int:
        return sum(1 for c in canonical_rows if pred(c))
    stats = {
        "total_rows":              len(canonical_rows),
        "packed":                  _count(lambda c: c.get("was_packed")),
        "never_touched_inventory": _count(lambda c: c.get("never_touched_inventory")),
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

    import_batch_id = f"MREP_{platform_lc}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    committed: Dict[str, int] = {
        "items_upserted":       0,
        "orders_upserted":      0,
        "returns_posted":       0,
        "returns_skipped":      0,  # idempotency skips (already-posted)
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

            # ── Upsert online_order ──
            match_q: Dict[str, Any] = {"platform": platform_lc}
            if order_release_id: match_q["order_release_id"] = order_release_id
            elif order_id:       match_q["order_id"]         = order_id
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

            # ── Upsert online_order_item with classification fields ──
            item_q: Dict[str, Any] = {
                "online_order_id": ObjectId(online_order_pk),
                "style_id":        ObjectId(style_id),
                "color":           color,
                "size":            size,
            }
            existing_item = await db.online_order_items.find_one(item_q)

            item_set = {
                "platform":               platform_lc,
                "order_id":               order_id,
                "order_release_id":       order_release_id,
                "style_id":               ObjectId(style_id),
                "style_code":             style_code,
                "color":                  color,
                "size":                   size,
                "leaf_sku":               canon.get("leaf_sku"),
                "leaf_sku_raw":           canon.get("leaf_sku_raw"),
                # ── classification (Phase 4 profit engine reads these) ──
                "was_packed":             canon.get("was_packed"),
                "was_returned_to_stock":  canon.get("was_returned_to_stock"),
                "is_pending":             canon.get("is_pending"),
                "is_net_sold":            canon.get("is_net_sold"),
                "never_touched_inventory":canon.get("never_touched_inventory"),
                "return_reason":          canon.get("return_reason"),
                "order_status":           canon.get("order_status"),
                # ── date columns from monthly file ──
                "packed_on":              canon.get("packed_on"),
                "delivered_on":           canon.get("delivered_on"),
                "cancelled_on":           canon.get("cancelled_on"),
                "rto_creation_date":      canon.get("rto_creation_date"),
                "return_creation_date":   canon.get("return_creation_date"),
                # ── revenue columns for Phase 4 ──
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

            # ── If this row is was_returned_to_stock, post return movements ──
            if canon.get("was_returned_to_stock"):
                try:
                    outcome = await _record_monthly_return(
                        canon=canon, platform=platform_lc,
                        batch_id=import_batch_id, user_email=u["email"],
                    )
                except HTTPException as he:
                    exceptions.append({
                        "import_batch_id":  import_batch_id,
                        "platform":         platform_lc,
                        "kind":             "monthly_report_import",
                        "source_row_index": src_row,
                        "order_id":         order_id,
                        "order_release_id": order_release_id,
                        "style_id":         style_id,
                        "style_code":       style_code,
                        "color":            color,
                        "size":             size,
                        "leaf_sku":         canon.get("leaf_sku"),
                        "reason":           f"return movement blocked: {he.detail}",
                        "raw_row":          canon.get("raw_row"),
                        "created_at":       now_iso(),
                        "resolved":         False,
                    })
                    continue
                if outcome.get("skipped"):
                    committed["returns_skipped"] += 1
                elif outcome.get("close_type") == "return_damaged":
                    committed["return_damaged_posted"] += 1
                else:
                    committed["returns_posted"] += 1

        if exceptions:
            await db.online_order_exceptions.insert_many(exceptions)
            committed["exceptions_queued"] = len(exceptions)

        await log_activity(
            "MONTHLY_REPORT_IMPORT", "online_orders",
            f"{platform_lc}: {committed['items_upserted']} items, "
            f"{committed['returns_posted']} return-restocks, "
            f"{committed['return_damaged_posted']} return-damaged, "
            f"{committed['returns_skipped']} idempotency-skipped, "
            f"{committed['exceptions_queued']} exceptions "
            f"(batch {import_batch_id})",
            u["email"],
        )

        # ── Phase 4 auto-materialise: refresh online_profitability_daily
        # for the date range this monthly file covered. Non-fatal — a
        # failure here must NOT roll back the import.
        try:
            packed_dates = [c.get("packed_on") for c in canonical_rows if c.get("packed_on")]
            if packed_dates:
                d_from = min(packed_dates)[:10]
                d_to   = max(packed_dates)[:10]
                summary = await _materialise_profitability_range(
                    platform=platform_lc, date_from=d_from, date_to=d_to,
                )
                committed["profitability_rollup"] = summary
        except Exception as e:
            log.warning(f"Auto-materialise profitability failed after monthly import: {e}")

    return {
        "platform":           platform_lc,
        "role":               "monthly_report",
        "filename":           filename,
        "header_row_1_based": header_row_1,
        "header":             header,
        "dry_run":            dry_run,
        "stats":              stats,
        "committed":          committed if not dry_run else None,
        "import_batch_id":    import_batch_id,
        "rows":               canonical_rows,
    }


@api.get("/online-orders/reconciliation-summary")
async def reconciliation_summary(
    request: Request,
    platform: Optional[str] = None,
    month: Optional[str] = Query(None, description="YYYY-MM — filters on packed_on prefix"),
):
    """Summary counts of the funnel + reason breakdown for a month.

    Query:
      platform : filter by platform (defaults to all)
      month    : "YYYY-MM" — filters online_order_items where packed_on
                 starts with that prefix. Also matches the same prefix on
                 return_creation_date + rto_creation_date + cancelled_on
                 for row-level activity in that month.

    Returns the same funnel counts as the import endpoint, but calculated
    from the persisted online_order_items rather than the incoming file
    (i.e. this is the read-side "here's the current state of the world").
    """
    await get_current_user(request)

    q: Dict[str, Any] = {}
    if platform: q["platform"] = platform.lower()
    if month:
        q["packed_on"] = {"$regex": f"^{month}"}

    total_rows              = await db.online_order_items.count_documents(q)
    packed                  = await db.online_order_items.count_documents({**q, "was_packed": True})
    never_touched_inventory = await db.online_order_items.count_documents({**q, "never_touched_inventory": True})
    returned_to_stock       = await db.online_order_items.count_documents({**q, "was_returned_to_stock": True})
    pending                 = await db.online_order_items.count_documents({**q, "is_pending": True})
    net_sold                = await db.online_order_items.count_documents({**q, "is_net_sold": True})

    rto_c            = await db.online_order_items.count_documents({**q, "return_reason": "rto"})
    customer_ret_c   = await db.online_order_items.count_documents({**q, "return_reason": "customer_return"})
    cancel_pack_c    = await db.online_order_items.count_documents({**q, "return_reason": "cancelled_after_pack"})

    return {
        "platform": platform,
        "month":    month,
        "total_rows":              total_rows,
        "packed":                  packed,
        "never_touched_inventory": never_touched_inventory,
        "returned_to_stock":       returned_to_stock,
        "pending":                 pending,
        "net_sold":                net_sold,
        "reason_breakdown": {
            "rto":                  rto_c,
            "customer_return":      customer_ret_c,
            "cancelled_after_pack": cancel_pack_c,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# ══ ONLINE PROFITABILITY (Phase 4 — Cost vs Revenue reconciliation) ════
# ═══════════════════════════════════════════════════════════════════════
# The actual profit engine — net cost of goods actually sold against
# what was actually received for them, per period/platform/style.
#
#   Step A — Net units sold: online_order_items where is_net_sold=true
#             (produced by Phase 2 classification).
#   Step B — Net COGS: existing compute_style_costing().total_cost per unit
#             × units_sold, summed across styles. Uses the SAME costing
#             engine as B2B — one source of truth.
#   Step C — Revenue received: sum of Settled_Amount over forward_settled
#             minus reverse_settled (Phase 3 collections).
#   Step D — Revenue pending: same shape but against unsettled sheets.
#   Step E — Platform fees: commission + fixed_fee + logistics_cost +
#             pick_and_pack_fee + tech_enablement + royalty, forward
#             minus reverse.
#   Step F — Cost of returns (logistics): the reverse-side of platform
#             fees, surfaced separately so RTO / return logistics drag
#             is visible even though the inventory itself came back.
#
# Graceful degradation: if Phase 3 settlement collections don't exist
# yet, C/D/E/F return 0 (with `notes.phase_3_available=false` set).
# The moment Phase 3 lands, numbers flow without any code change here.
# ═══════════════════════════════════════════════════════════════════════

# Documented map: canonical fee key → collection column name(s) we sum.
# Kept as a config so Phase 3's actual column names can be finalised
# without touching this endpoint's logic.
_PLATFORM_FEE_FIELDS = [
    "commission_amount_incl_gst_postpaid", "commission_amount_incl_gst_prepaid",
    "fixed_fee_postpaid",                  "fixed_fee_prepaid",
    "logistics_cost_forward_incl_tax_postpaid", "logistics_cost_forward_incl_tax_prepaid",
    "pick_and_pack_fees_postpaid",         "pick_and_pack_fees_prepaid",
    "tech_enablement_charges_postpaid",    "tech_enablement_charges_prepaid",
    "royalty_charges_postpaid",            "royalty_charges_prepaid",
]

# Logistics-only subset (used for Step F — cost of returns logistics).
_LOGISTICS_FEE_FIELDS = [
    "logistics_cost_forward_incl_tax_postpaid", "logistics_cost_forward_incl_tax_prepaid",
    "logistics_cost_reverse_incl_tax_postpaid", "logistics_cost_reverse_incl_tax_prepaid",
]

# Amount columns we treat as "revenue received" on the forward side and
# "revenue clawback" on the reverse side.
_SETTLED_AMOUNT_FIELDS = ["settled_amount_postpaid", "settled_amount_prepaid"]
_PENDING_AMOUNT_FIELDS = [
    "amount_pending_settlement_postpaid",
    "amount_pending_settlement_prepaid",
]

# Customer_Paid_Amount column names to look for when running the sample
# validation "Settled_Amount + Sum(fees) ≈ Customer_Paid_Amount".
_CUSTOMER_PAID_FIELDS = [
    "customer_paid_amount_postpaid",
    "customer_paid_amount_prepaid",
    "customer_paid_amount",
]


async def _collection_exists(name: str) -> bool:
    """True iff a MongoDB collection with this name exists."""
    try:
        names = await db.list_collection_names()
        return name in names
    except Exception:
        return False


async def _sum_settlement_fields(
    coll_name: str,
    fields: List[str],
    match: Dict[str, Any],
) -> float:
    """Sum a list of numeric columns across all matching docs in the
    given settlement collection.  Returns 0.0 if the collection doesn't
    exist yet (Phase 3 not built) or if no rows match.  Missing / non-
    numeric per-doc values are treated as 0.
    """
    if not await _collection_exists(coll_name):
        return 0.0
    coll = db[coll_name]
    # Build $sum expressions coercing missing/null → 0.
    sum_exprs = {
        "total": {"$sum": {
            "$add": [
                {"$ifNull": [f"${f}", 0]}
                for f in fields
            ]
        }}
    } if fields else {"total": {"$sum": 0}}
    try:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": None, **sum_exprs}},
        ]
        agg = await coll.aggregate(pipeline).to_list(1)
        if not agg: return 0.0
        return float(agg[0].get("total") or 0.0)
    except Exception as e:
        log.warning(f"_sum_settlement_fields failed on {coll_name}: {e}")
        return 0.0


def _build_settlement_match(
    platform: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    style_id: Optional[str],
) -> Dict[str, Any]:
    """Match filter used against every settlement collection. Uses
    packing_date/delivery_date range on the settlement rows (Phase 3
    will normalise these), and matches platform when supplied.
    """
    q: Dict[str, Any] = {}
    if platform: q["platform"] = platform.lower()
    if style_id: q["style_id"] = style_id
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from: rng["$gte"] = date_from
        if date_to:   rng["$lte"] = date_to
        # Match the packing/delivery date (Phase 3 will populate these on
        # settlement docs). Row is included if EITHER falls in range so
        # that late-arriving settlements for a June packing still land
        # in the June report.
        q["$or"] = [{"packing_date": rng}, {"delivery_date": rng}]
    return q


@api.get("/reports/online-profitability")
async def online_profitability(
    request: Request,
    platform: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    style_id:  Optional[str] = None,
    materialise: bool = Query(False, description="If true, also upsert into online_profitability_daily"),
):
    """Cost of Production vs Revenue Reconciliation Engine.

    Returns net units sold, total net COGS, revenue settled/pending,
    platform fees, cost of returns logistics, gross profit + margin,
    and a per-style breakdown with return rate.
    """
    await get_current_user(request)
    result = await _compute_online_profitability(
        platform=platform, date_from=date_from, date_to=date_to, style_id=style_id,
    )
    if materialise:
        await _materialise_profitability_snapshot(
            platform=platform, date_from=date_from, date_to=date_to,
            style_id=style_id, result=result,
        )
        result["materialised"] = True
    return result


async def _compute_online_profitability(
    platform:  Optional[str],
    date_from: Optional[str],
    date_to:   Optional[str],
    style_id:  Optional[str],
) -> Dict[str, Any]:
    """Core compute — extracted from the HTTP endpoint so the same logic
    is used by (a) the live GET, (b) the daily rollup materialiser, and
    (c) auto-recompute hooks fired from data-import endpoints."""

    notes: List[str] = []

    # ── Build item-level match (Phase 2 output) ──
    item_match: Dict[str, Any] = {}
    if platform: item_match["platform"] = platform.lower()
    if style_id:
        try: item_match["style_id"] = ObjectId(style_id)
        except Exception: item_match["style_id"] = style_id
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from: rng["$gte"] = date_from
        if date_to:   rng["$lte"] = date_to
        item_match["packed_on"] = rng

    # ── STEP A — Net units sold (grouped by style) ──
    sold_pipeline = [
        {"$match": {**item_match, "is_net_sold": True}},
        {"$group": {
            "_id":         "$style_id",
            "style_code":  {"$first": "$style_code"},
            "color":       {"$first": "$color"},
            "units_sold":  {"$sum": {"$ifNull": ["$qty", 1]}},
            # Item-file revenue is a fallback when settlements aren't yet imported.
            "item_final_amount": {"$sum": {"$ifNull": ["$final_amount", 0]}},
            "order_release_ids": {"$addToSet": "$order_release_id"},
        }},
    ]
    sold_rows = await db.online_order_items.aggregate(sold_pipeline).to_list(5000)

    # ── Returned units (for return_rate_pct in by_style) ──
    ret_pipeline = [
        {"$match": {**item_match, "was_returned_to_stock": True}},
        {"$group": {"_id": "$style_id", "returned_units": {"$sum": {"$ifNull": ["$qty", 1]}}}},
    ]
    ret_rows = await db.online_order_items.aggregate(ret_pipeline).to_list(5000)
    returned_by_style = {str(r["_id"]): r["returned_units"] for r in ret_rows if r.get("_id")}

    # ── STEP B — COGS per style (from the SAME costing engine used by B2B) ──
    style_ids = [r["_id"] for r in sold_rows if r.get("_id")]
    style_cost_map: Dict[str, Dict[str, Any]] = {}
    if style_ids:
        style_docs = await db.styles.find({"_id": {"$in": style_ids}}).to_list(len(style_ids))
        for s in style_docs:
            try:
                c = compute_style_costing(s)
                style_cost_map[str(s["_id"])] = {
                    "style_code": s.get("code") or s.get("style_code"),
                    "unit_cogs":  c.get("total_cost") or 0,
                    "materials_cost": c.get("materials_cost"),
                    "labor_cost":     c.get("labor_cost"),
                    "overhead_cost":  c.get("overhead_cost"),
                    "packing_cost":   c.get("packing_cost"),
                }
            except Exception as e:
                log.warning(f"compute_style_costing failed for style {s.get('_id')}: {e}")
                style_cost_map[str(s["_id"])] = {"style_code": s.get("code"), "unit_cogs": 0}
        missing = [str(sid) for sid in style_ids if str(sid) not in style_cost_map]
        if missing:
            notes.append(f"{len(missing)} style_id(s) referenced by net-sold rows have no styles doc — COGS treated as 0 for these.")

    # ── STEPS C, D, E, F — settlement-derived numbers ──
    settle_match = _build_settlement_match(platform, date_from, date_to, style_id)

    fwd_exists    = await _collection_exists("settlement_forward")
    rev_exists    = await _collection_exists("settlement_reverse")
    fwd_un_exists = await _collection_exists("settlement_unsettled_forward")
    rev_un_exists = await _collection_exists("settlement_unsettled_reverse")
    phase_3_available = (fwd_exists or rev_exists or fwd_un_exists or rev_un_exists)

    if not phase_3_available:
        notes.append(
            "Phase 3 settlement import has not been run yet — revenue_settled, "
            "revenue_pending, platform_fees and cost_of_returns_logistics are "
            "all 0. Import forward_settled / reverse_settled / forward_unsettled "
            "/ reverse_unsettled to populate these figures."
        )

    # STEP C: revenue settled = forward − reverse
    revenue_forward = await _sum_settlement_fields("settlement_forward", _SETTLED_AMOUNT_FIELDS, settle_match)
    revenue_reverse = await _sum_settlement_fields("settlement_reverse", _SETTLED_AMOUNT_FIELDS, settle_match)
    total_revenue_settled = revenue_forward - revenue_reverse

    # STEP D: revenue pending = unsettled forward − unsettled reverse
    pending_forward = await _sum_settlement_fields("settlement_unsettled_forward", _PENDING_AMOUNT_FIELDS, settle_match)
    pending_reverse = await _sum_settlement_fields("settlement_unsettled_reverse", _PENDING_AMOUNT_FIELDS, settle_match)
    total_revenue_pending = pending_forward - pending_reverse

    # STEP E: platform fees = forward − reverse across all fee columns
    fees_forward_settled     = await _sum_settlement_fields("settlement_forward",            _PLATFORM_FEE_FIELDS, settle_match)
    fees_reverse_settled     = await _sum_settlement_fields("settlement_reverse",            _PLATFORM_FEE_FIELDS, settle_match)
    fees_forward_unsettled   = await _sum_settlement_fields("settlement_unsettled_forward",  _PLATFORM_FEE_FIELDS, settle_match)
    fees_reverse_unsettled   = await _sum_settlement_fields("settlement_unsettled_reverse",  _PLATFORM_FEE_FIELDS, settle_match)
    total_platform_fees = (
        fees_forward_settled + fees_forward_unsettled
        - fees_reverse_settled - fees_reverse_unsettled
    )

    # STEP F: cost of returns logistics — the REVERSE-side logistics rows.
    # Reverse rows come with positive amounts (a fee we paid) so we take
    # the raw sum, not forward-minus-reverse.
    cost_of_returns_logistics = (
        await _sum_settlement_fields("settlement_reverse",           _LOGISTICS_FEE_FIELDS, settle_match)
      + await _sum_settlement_fields("settlement_unsettled_reverse", _LOGISTICS_FEE_FIELDS, settle_match)
    )

    # ── Per-style settlement joins ──
    # Try to attribute settled revenue + fees per style by looking up
    # order_release_id → online_order_items.style_id from Phase 2 data.
    per_style_revenue_settled: Dict[str, float] = {}
    per_style_fees:            Dict[str, float] = {}
    if phase_3_available and fwd_exists:
        try:
            per_style_revenue_settled, per_style_fees = \
                await _per_style_settlement_split(settle_match, sold_rows)
        except Exception as e:
            log.warning(f"per-style settlement split failed: {e}")

    # ── Sample validation: Settled_Amount + Sum(fees) vs Customer_Paid_Amount ──
    fees_interpretation: Dict[str, Any] = {"available": False}
    if fwd_exists:
        try:
            fees_interpretation = await _validate_settled_plus_fees(settle_match)
        except Exception as e:
            log.warning(f"validate_settled_plus_fees failed: {e}")

    # ── Assemble per-style breakdown ──
    by_style: List[Dict[str, Any]] = []
    total_units_sold  = 0
    total_net_cogs    = 0.0
    total_item_revenue_fallback = 0.0
    for r in sold_rows:
        sid = r.get("_id")
        sid_str = str(sid) if sid else None
        units_sold = int(r.get("units_sold") or 0)
        returned_units = int(returned_by_style.get(sid_str, 0)) if sid_str else 0
        unit_cogs = float(style_cost_map.get(sid_str, {}).get("unit_cogs", 0)) if sid_str else 0.0
        style_cogs = unit_cogs * units_sold
        item_revenue = float(r.get("item_final_amount") or 0)

        # Denominator = returned + net_sold (as per spec)
        total_touch = returned_units + units_sold
        return_rate = (returned_units / total_touch * 100) if total_touch > 0 else 0.0

        by_style.append({
            "style_id":        sid_str,
            "style_code":      style_cost_map.get(sid_str, {}).get("style_code") or r.get("style_code"),
            "color":           r.get("color"),
            "units_sold":      units_sold,
            "returned_units":  returned_units,
            "unit_cogs":       round(unit_cogs, 2),
            "cogs":            round(style_cogs, 2),
            "item_revenue_fallback": round(item_revenue, 2),   # from final_amount
            "return_rate_pct": round(return_rate, 2),
        })
        total_units_sold += units_sold
        total_net_cogs   += style_cogs
        total_item_revenue_fallback += item_revenue

    # If Phase 3 isn't up, use the item-file's `final_amount` as a
    # best-effort revenue signal so the profit line isn't outright 0.
    revenue_used_for_profit = total_revenue_settled
    revenue_source = "settlement_forward - settlement_reverse"
    if not phase_3_available and total_item_revenue_fallback > 0:
        revenue_used_for_profit = total_item_revenue_fallback
        revenue_source = "online_order_items.final_amount (fallback while Phase 3 not imported)"
        notes.append("Using item-file final_amount as revenue signal since Phase 3 settlements aren't imported yet.")

    # Gross profit computed against whichever revenue signal we have
    gross_profit = revenue_used_for_profit - total_net_cogs
    gross_margin_pct = ((gross_profit / revenue_used_for_profit) * 100) if revenue_used_for_profit else 0.0

    # Per-style profit — use settlement-derived per-style revenue when
    # available, otherwise fall back to item_revenue_fallback.
    for row in by_style:
        sid_str = row.get("style_id") or ""
        if phase_3_available and sid_str in per_style_revenue_settled:
            row_rev = float(per_style_revenue_settled.get(sid_str, 0.0))
            row["revenue_source"] = "settlement_forward"
        else:
            row_rev = float(row.get("item_revenue_fallback") or 0)
            row["revenue_source"] = "item_final_amount"
        row["revenue_settled"] = round(row_rev, 2)
        row["platform_fees"]   = round(float(per_style_fees.get(sid_str, 0.0)), 2)
        row["profit"]          = round(row_rev - row["cogs"], 2)
        row["margin_pct"]      = round(((row["profit"] / row_rev) * 100) if row_rev else 0.0, 2)

    # ── Platform-fees interpretation note (from spec) ──
    if fees_interpretation.get("available"):
        interp_note = (
            f"Sample validation: on {fees_interpretation['sample_size']} forward rows, "
            f"Settled_Amount = ₹{fees_interpretation['settled_sum']:.2f}, "
            f"Sum(fees) = ₹{fees_interpretation['fees_sum']:.2f}, "
            f"Customer_Paid_Amount = ₹{fees_interpretation['customer_paid_sum']:.2f}. "
            f"Interpretation: {fees_interpretation['interpretation']}. "
            f"total_platform_fees is reported {fees_interpretation['treated_as'].upper()}."
        )
        notes.append(interp_note)
    else:
        notes.append(
            "Platform fees interpretation: Myntra typically nets platform fees "
            "OUT of Settled_Amount BEFORE reporting it. So `total_platform_fees` "
            "here is INFORMATIONAL — do NOT subtract it again from "
            "total_revenue_settled. Validate on a sample row that Settled_Amount "
            "+ Sum(fees) ≈ Customer_Paid_Amount before changing this "
            "assumption. Phase 3 will surface both interpretations side-by-side."
        )

    return {
        "period":                    {"from": date_from, "to": date_to},
        "platform":                  platform,
        "style_id":                  style_id,
        "net_units_sold":            total_units_sold,
        "total_net_cogs":            round(total_net_cogs, 2),
        "total_revenue_settled":     round(total_revenue_settled, 2),
        "total_revenue_pending":     round(total_revenue_pending, 2),
        "total_platform_fees":       round(total_platform_fees, 2),
        "cost_of_returns_logistics": round(cost_of_returns_logistics, 2),
        "gross_profit":              round(gross_profit, 2),
        "gross_margin_pct":          round(gross_margin_pct, 2),
        "revenue_source_used":       revenue_source,
        "phase_3_available":         phase_3_available,
        "fees_interpretation":       fees_interpretation,
        "notes":                     notes,
        "by_style":                  by_style,
    }


async def _per_style_settlement_split(
    settle_match: Dict[str, Any],
    sold_rows:    List[Dict[str, Any]],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Attribute settled revenue and platform fees per style, using
    order_release_id as the join key back to online_order_items.style_id.

    Returns (revenue_by_style_id_str, fees_by_style_id_str).
    """
    revenue_by_style: Dict[str, float] = defaultdict(float)
    fees_by_style:    Dict[str, float] = defaultdict(float)

    # 1) Prefer settlement rows that already carry style_id (future Phase 3 shape).
    for coll_name, sign in (("settlement_forward", 1.0), ("settlement_reverse", -1.0)):
        if not await _collection_exists(coll_name):
            continue
        pipeline = [
            {"$match": {**settle_match, "style_id": {"$ne": None}}},
            {"$group": {
                "_id": "$style_id",
                "rev": {"$sum": {"$add": [
                    {"$ifNull": [f"${f}", 0]} for f in _SETTLED_AMOUNT_FIELDS
                ]}},
                "fees": {"$sum": {"$add": [
                    {"$ifNull": [f"${f}", 0]} for f in _PLATFORM_FEE_FIELDS
                ]}},
            }},
        ]
        agg = await db[coll_name].aggregate(pipeline).to_list(5000)
        for row in agg:
            sid_str = str(row["_id"])
            revenue_by_style[sid_str] += sign * float(row.get("rev") or 0)
            fees_by_style[sid_str]    += sign * float(row.get("fees") or 0)

    # 2) For settlement rows WITHOUT style_id, join via order_release_id
    #    → online_order_items to attribute. Uses a $lookup pipeline.
    for coll_name, sign in (("settlement_forward", 1.0), ("settlement_reverse", -1.0)):
        if not await _collection_exists(coll_name):
            continue
        pipeline = [
            {"$match": {**settle_match, "style_id": None, "order_release_id": {"$ne": None}}},
            {"$lookup": {
                "from":         "online_order_items",
                "localField":   "order_release_id",
                "foreignField": "order_release_id",
                "as":           "items",
            }},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.style_id",
                "rev": {"$sum": {"$add": [
                    {"$ifNull": [f"${f}", 0]} for f in _SETTLED_AMOUNT_FIELDS
                ]}},
                "fees": {"$sum": {"$add": [
                    {"$ifNull": [f"${f}", 0]} for f in _PLATFORM_FEE_FIELDS
                ]}},
            }},
        ]
        try:
            agg = await db[coll_name].aggregate(pipeline, allowDiskUse=True).to_list(5000)
        except Exception as e:
            log.warning(f"per-style lookup on {coll_name} failed: {e}")
            agg = []
        for row in agg:
            sid = row.get("_id")
            if not sid: continue
            sid_str = str(sid)
            revenue_by_style[sid_str] += sign * float(row.get("rev") or 0)
            fees_by_style[sid_str]    += sign * float(row.get("fees") or 0)

    return dict(revenue_by_style), dict(fees_by_style)


async def _validate_settled_plus_fees(
    settle_match: Dict[str, Any],
    sample_size: int = 50,
) -> Dict[str, Any]:
    """Fetch a small sample of forward settlement rows and check whether
    Settled_Amount + Sum(fees) ≈ Customer_Paid_Amount.

    Returns:
      {
        available: True,
        sample_size, settled_sum, fees_sum, customer_paid_sum,
        interpretation: "fees_already_netted" | "fees_not_netted" | "inconclusive",
        treated_as: "informational" | "subtracted_again",
      }
    or {available: False, reason: "..."} when the sample can't be built.
    """
    coll = db["settlement_forward"]
    docs = await coll.find(settle_match).limit(sample_size).to_list(sample_size)
    if not docs:
        return {"available": False, "reason": "No forward settlement rows in range."}

    settled_sum       = 0.0
    fees_sum          = 0.0
    customer_paid_sum = 0.0
    cp_hits           = 0
    for d in docs:
        settled_sum += sum(float(d.get(f) or 0) for f in _SETTLED_AMOUNT_FIELDS)
        fees_sum    += sum(float(d.get(f) or 0) for f in _PLATFORM_FEE_FIELDS)
        for f in _CUSTOMER_PAID_FIELDS:
            v = d.get(f)
            if v not in (None, "", 0):
                customer_paid_sum += float(v)
                cp_hits += 1
                break

    if cp_hits == 0 or customer_paid_sum <= 0:
        return {"available": False, "reason": "No Customer_Paid_Amount column populated on sample."}

    total_with_fees = settled_sum + fees_sum
    # ±2% tolerance — Myntra rounds & GST composition varies row to row.
    if abs(total_with_fees - customer_paid_sum) / customer_paid_sum <= 0.02:
        interpretation = "fees_already_netted"
        treated_as     = "informational"
    elif abs(settled_sum - customer_paid_sum) / customer_paid_sum <= 0.02:
        interpretation = "fees_not_netted"
        treated_as     = "subtracted_again"
    else:
        interpretation = "inconclusive"
        treated_as     = "informational"

    return {
        "available":         True,
        "sample_size":       len(docs),
        "settled_sum":       round(settled_sum, 2),
        "fees_sum":          round(fees_sum, 2),
        "customer_paid_sum": round(customer_paid_sum, 2),
        "settled_plus_fees": round(total_with_fees, 2),
        "interpretation":    interpretation,
        "treated_as":        treated_as,
    }


async def _materialise_profitability_snapshot(
    platform:  Optional[str],
    date_from: Optional[str],
    date_to:   Optional[str],
    style_id:  Optional[str],
    result:    Dict[str, Any],
) -> None:
    """Upsert a computed profitability result into online_profitability_daily,
    keyed by (platform, date_from, date_to, style_id)."""
    key = {
        "platform":  platform,
        "date_from": date_from,
        "date_to":   date_to,
        "style_id":  style_id,
    }
    await db.online_profitability_daily.update_one(
        key,
        {"$set": {**key, **result, "computed_at": now_iso()}},
        upsert=True,
    )


async def _materialise_profitability_range(
    platform:  Optional[str],
    date_from: Optional[str],
    date_to:   Optional[str],
) -> Dict[str, Any]:
    """Rebuild the daily rollups for every day in [date_from, date_to] and
    also the whole-range aggregate. Idempotent (upserts). Called from
    data-import endpoints so dashboards read from a hot table.

    Returns a summary: {days_rebuilt, aggregate_computed_at}.
    """
    from datetime import date as _date
    days_rebuilt = 0
    if date_from and date_to:
        try:
            d_from = _date.fromisoformat(date_from)
            d_to   = _date.fromisoformat(date_to)
        except ValueError:
            d_from = d_to = None
        if d_from and d_to and d_from <= d_to:
            d = d_from
            while d <= d_to:
                iso = d.isoformat()
                try:
                    day_result = await _compute_online_profitability(
                        platform=platform, date_from=iso, date_to=iso, style_id=None,
                    )
                    await _materialise_profitability_snapshot(
                        platform=platform, date_from=iso, date_to=iso,
                        style_id=None, result=day_result,
                    )
                    days_rebuilt += 1
                except Exception as e:
                    log.warning(f"Day rollup failed for {iso}/{platform}: {e}")
                d = _date.fromordinal(d.toordinal() + 1)

    # Whole-range aggregate
    agg_result = await _compute_online_profitability(
        platform=platform, date_from=date_from, date_to=date_to, style_id=None,
    )
    await _materialise_profitability_snapshot(
        platform=platform, date_from=date_from, date_to=date_to,
        style_id=None, result=agg_result,
    )
    return {
        "days_rebuilt":          days_rebuilt,
        "aggregate_computed_at": now_iso(),
    }


@api.post("/reports/online-profitability/rebuild")
async def rebuild_online_profitability(
    request:  Request,
    platform: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD (inclusive)"),
):
    """Manually rebuild the online_profitability_daily rollup for a given
    platform + date range. Admin/manager only. Used by ops when they've
    corrected settlement / dispatch / monthly-report data and want the
    cached rollup to reflect the new numbers immediately.
    """
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    summary = await _materialise_profitability_range(
        platform=platform, date_from=date_from, date_to=date_to,
    )
    await log_activity(
        "REBUILD", "online_profitability",
        f"Rebuilt profitability rollup for platform={platform or '(all)'} "
        f"{date_from or '-'}..{date_to or '-'}: {summary['days_rebuilt']} days.",
        u["email"],
    )
    return {"ok": True, "platform": platform, "period": {"from": date_from, "to": date_to}, **summary}



@api.get("/reports/online-profitability-materialised")
async def list_materialised_profitability(
    request: Request,
    platform: Optional[str] = None,
    limit: int = 50,
):
    """List previously-materialised profitability snapshots. Useful for
    dashboards that need fast reads without recomputing.
    """
    await get_current_user(request)
    q: Dict[str, Any] = {}
    if platform: q["platform"] = platform.lower()
    docs = await db.online_profitability_daily.find(q).sort("computed_at", -1).limit(limit).to_list(limit)
    for d in docs: d.pop("_id", None)
    return docs


@api.get("/reports/online-profitability/trend")
async def online_profitability_trend(
    request:   Request,
    platform:  Optional[str] = None,
    date_from: str = Query(..., description="YYYY-MM-DD (inclusive)"),
    date_to:   str = Query(..., description="YYYY-MM-DD (inclusive)"),
    bucket:    Literal["day", "week"] = "day",
    style_id:  Optional[str] = None,
):
    """Per-bucket trend used by the Profitability dashboard's charts.

    Returns for each date bucket:
      { date, units_packed, units_returned, net_units_sold, cogs,
        revenue_settled, revenue_pending, gross_profit,
        fees: { commission, logistics_fwd, logistics_rev, fixed_fee,
                pick_and_pack, tech_enablement, royalty } }

    Uses online_order_items.packed_on for the item-side buckets and
    settlement collections' packing_date / delivery_date for the
    settlement side. Item-file `final_amount` acts as revenue fallback
    when Phase 3 isn't imported yet — same policy as the main endpoint.
    """
    await get_current_user(request)
    from datetime import date as _date, timedelta as _td

    try:
        d_from = _date.fromisoformat(date_from)
        d_to   = _date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(400, "date_from / date_to must be YYYY-MM-DD")
    if d_from > d_to:
        raise HTTPException(400, "date_from must be <= date_to")

    # Build the ordered list of bucket keys and their (start, end) inclusive ranges.
    buckets: List[Dict[str, Any]] = []
    if bucket == "day":
        d = d_from
        while d <= d_to:
            iso = d.isoformat()
            buckets.append({"key": iso, "from": iso, "to": iso})
            d = _date.fromordinal(d.toordinal() + 1)
    else:  # week: ISO week Mon-Sun
        d = d_from
        while d <= d_to:
            wk_start = d - _td(days=d.weekday())
            wk_end   = wk_start + _td(days=6)
            if wk_end > d_to: wk_end = d_to
            if wk_start < d_from: wk_start = d_from
            buckets.append({
                "key":  f"W{wk_start.isocalendar().week:02d} {wk_start.strftime('%b %d')}",
                "from": wk_start.isoformat(),
                "to":   wk_end.isoformat(),
            })
            d = wk_end + _td(days=1)

    # Base item-side match
    base_item: Dict[str, Any] = {}
    if platform: base_item["platform"] = platform.lower()
    if style_id:
        try: base_item["style_id"] = ObjectId(style_id)
        except Exception: base_item["style_id"] = style_id

    fwd_exists = await _collection_exists("settlement_forward")
    rev_exists = await _collection_exists("settlement_reverse")
    fwd_un_exists = await _collection_exists("settlement_unsettled_forward")
    rev_un_exists = await _collection_exists("settlement_unsettled_reverse")

    async def _sum_by(coll: str, fields: List[str], q: Dict[str, Any]) -> float:
        if not await _collection_exists(coll): return 0.0
        return await _sum_settlement_fields(coll, fields, q)

    async def _count_units(match: Dict[str, Any]) -> int:
        pipeline = [
            {"$match": match},
            {"$group": {"_id": None, "n": {"$sum": {"$ifNull": ["$qty", 1]}}}},
        ]
        agg = await db.online_order_items.aggregate(pipeline).to_list(1)
        return int(agg[0]["n"]) if agg else 0

    # Fee-column split we surface separately in the stacked bar
    _FEE_GROUPS = {
        "commission":       ["commission_amount_incl_gst_postpaid", "commission_amount_incl_gst_prepaid"],
        "fixed_fee":        ["fixed_fee_postpaid", "fixed_fee_prepaid"],
        "logistics_fwd":    ["logistics_cost_forward_incl_tax_postpaid", "logistics_cost_forward_incl_tax_prepaid"],
        "logistics_rev":    ["logistics_cost_reverse_incl_tax_postpaid", "logistics_cost_reverse_incl_tax_prepaid"],
        "pick_and_pack":    ["pick_and_pack_fees_postpaid", "pick_and_pack_fees_prepaid"],
        "tech_enablement":  ["tech_enablement_charges_postpaid", "tech_enablement_charges_prepaid"],
        "royalty":          ["royalty_charges_postpaid", "royalty_charges_prepaid"],
    }

    result_rows: List[Dict[str, Any]] = []
    for b in buckets:
        # Item-side (net units + returned + cogs from BOM)
        packed_match = {**base_item, "packed_on": {"$gte": b["from"], "$lte": b["to"]}}
        units_packed   = await _count_units({**packed_match, "was_packed": True})
        units_returned = await _count_units({**packed_match, "was_returned_to_stock": True})
        # net_sold pipeline also groups by style_id to compute cogs
        net_pipeline = [
            {"$match": {**packed_match, "is_net_sold": True}},
            {"$group": {"_id": "$style_id", "n": {"$sum": {"$ifNull": ["$qty", 1]}}, "amt": {"$sum": {"$ifNull": ["$final_amount", 0]}}}},
        ]
        net_rows = await db.online_order_items.aggregate(net_pipeline).to_list(2000)
        net_units_sold = sum(int(r.get("n") or 0) for r in net_rows)
        item_final_amount = sum(float(r.get("amt") or 0) for r in net_rows)

        # COGS via the SAME costing engine
        style_ids = [r["_id"] for r in net_rows if r.get("_id")]
        cogs = 0.0
        if style_ids:
            style_docs = await db.styles.find({"_id": {"$in": style_ids}}).to_list(len(style_ids))
            unit_cost_map = {}
            for s in style_docs:
                try: unit_cost_map[str(s["_id"])] = float(compute_style_costing(s).get("total_cost") or 0)
                except Exception: unit_cost_map[str(s["_id"])] = 0.0
            for r in net_rows:
                sid = str(r.get("_id"))
                cogs += unit_cost_map.get(sid, 0.0) * int(r.get("n") or 0)

        # Settlement-side
        smatch = _build_settlement_match(platform, b["from"], b["to"], style_id)
        rev_fwd = await _sum_by("settlement_forward", _SETTLED_AMOUNT_FIELDS, smatch) if fwd_exists else 0.0
        rev_rev = await _sum_by("settlement_reverse", _SETTLED_AMOUNT_FIELDS, smatch) if rev_exists else 0.0
        pen_fwd = await _sum_by("settlement_unsettled_forward", _PENDING_AMOUNT_FIELDS, smatch) if fwd_un_exists else 0.0
        pen_rev = await _sum_by("settlement_unsettled_reverse", _PENDING_AMOUNT_FIELDS, smatch) if rev_un_exists else 0.0

        fees_out: Dict[str, float] = {}
        for grp, fields in _FEE_GROUPS.items():
            f_fwd = await _sum_by("settlement_forward",           fields, smatch) if fwd_exists else 0.0
            f_rev = await _sum_by("settlement_reverse",           fields, smatch) if rev_exists else 0.0
            f_fu  = await _sum_by("settlement_unsettled_forward", fields, smatch) if fwd_un_exists else 0.0
            f_ru  = await _sum_by("settlement_unsettled_reverse", fields, smatch) if rev_un_exists else 0.0
            # For logistics_rev we WANT reverse-side positive (that's the point).
            if grp == "logistics_rev":
                fees_out[grp] = round(f_rev + f_ru, 2)
            else:
                fees_out[grp] = round(f_fwd + f_fu - f_rev - f_ru, 2)

        revenue_settled = rev_fwd - rev_rev
        # Fallback to item_final_amount if Phase 3 isn't populated
        phase_3_here = (rev_fwd + rev_rev + pen_fwd + pen_rev) > 0
        revenue_effective = revenue_settled if phase_3_here else item_final_amount
        gross_profit = revenue_effective - cogs

        result_rows.append({
            "date":              b["key"],
            "from":              b["from"],
            "to":                b["to"],
            "units_packed":      units_packed,
            "units_returned":    units_returned,
            "net_units_sold":    net_units_sold,
            "cogs":              round(cogs, 2),
            "revenue_settled":   round(revenue_settled, 2),
            "revenue_pending":   round(pen_fwd - pen_rev, 2),
            "revenue_effective": round(revenue_effective, 2),
            "gross_profit":      round(gross_profit, 2),
            "fees":              fees_out,
            "phase_3_here":      phase_3_here,
        })

    return {
        "platform": platform,
        "bucket":   bucket,
        "period":   {"from": date_from, "to": date_to},
        "style_id": style_id,
        "rows":     result_rows,
    }


@api.get("/reports/online-profitability/export")
async def online_profitability_export(
    request:   Request,
    platform:  Optional[str] = None,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    style_id:  Optional[str] = None,
):
    """Download the profitability report as an .xlsx workbook — one
    summary sheet + one per-style sheet. Uses openpyxl (already
    installed for packing lists). Same filter contract as the main
    endpoint; recomputes on the fly (no caching)."""
    await get_current_user(request)
    result = await _compute_online_profitability(
        platform=platform, date_from=date_from, date_to=date_to, style_id=style_id,
    )

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="0F172A")
    label_font  = Font(bold=True)

    ws["A1"] = "Online Profitability Report"
    ws["A1"].font = Font(bold=True, size=16)
    ws.merge_cells("A1:D1")

    meta_rows = [
        ("Platform",   platform or "(all)"),
        ("From",       date_from or "(any)"),
        ("To",         date_to or "(any)"),
        ("Style filter", style_id or "(none)"),
        ("Phase 3 available", "Yes" if result.get("phase_3_available") else "No"),
        ("Revenue source", result.get("revenue_source_used", "")),
        ("Generated at", now_iso()),
    ]
    for i, (k, v) in enumerate(meta_rows, start=3):
        ws.cell(row=i, column=1, value=k).font = label_font
        ws.cell(row=i, column=2, value=v)

    # Headline metrics
    metrics = [
        ("Net Units Sold",             result.get("net_units_sold")),
        ("Total Net COGS (₹)",         result.get("total_net_cogs")),
        ("Revenue Settled (₹)",        result.get("total_revenue_settled")),
        ("Revenue Pending (₹)",        result.get("total_revenue_pending")),
        ("Platform Fees (₹)",          result.get("total_platform_fees")),
        ("Cost of Returns Logistics (₹)", result.get("cost_of_returns_logistics")),
        ("Gross Profit (₹)",           result.get("gross_profit")),
        ("Gross Margin (%)",           result.get("gross_margin_pct")),
    ]
    start_row = 3 + len(meta_rows) + 2
    ws.cell(row=start_row, column=1, value="Metric").font = header_font
    ws.cell(row=start_row, column=1).fill = header_fill
    ws.cell(row=start_row, column=2, value="Value").font = header_font
    ws.cell(row=start_row, column=2).fill = header_fill
    for i, (k, v) in enumerate(metrics, start=start_row + 1):
        ws.cell(row=i, column=1, value=k).font = label_font
        ws.cell(row=i, column=2, value=v)

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 22

    # Per-style breakdown sheet
    ws2 = wb.create_sheet("By Style")
    headers = [
        "Style Code", "Color", "Units Sold", "Returned Units",
        "Unit COGS (₹)", "Total COGS (₹)",
        "Revenue Settled (₹)", "Platform Fees (₹)",
        "Profit (₹)", "Margin (%)", "Return Rate (%)", "Revenue Source",
    ]
    for c, h in enumerate(headers, start=1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    # Sort worst-profit-first
    rows = sorted(result.get("by_style") or [], key=lambda r: r.get("profit", 0))
    for ri, r in enumerate(rows, start=2):
        ws2.cell(row=ri, column=1,  value=r.get("style_code"))
        ws2.cell(row=ri, column=2,  value=r.get("color"))
        ws2.cell(row=ri, column=3,  value=r.get("units_sold"))
        ws2.cell(row=ri, column=4,  value=r.get("returned_units"))
        ws2.cell(row=ri, column=5,  value=r.get("unit_cogs"))
        ws2.cell(row=ri, column=6,  value=r.get("cogs"))
        ws2.cell(row=ri, column=7,  value=r.get("revenue_settled"))
        ws2.cell(row=ri, column=8,  value=r.get("platform_fees"))
        ws2.cell(row=ri, column=9,  value=r.get("profit"))
        ws2.cell(row=ri, column=10, value=r.get("margin_pct"))
        ws2.cell(row=ri, column=11, value=r.get("return_rate_pct"))
        ws2.cell(row=ri, column=12, value=r.get("revenue_source"))
    for c in range(1, 13):
        ws2.column_dimensions[chr(64 + c)].width = 16

    # Notes sheet
    ws3 = wb.create_sheet("Notes")
    ws3.cell(row=1, column=1, value="Interpretation notes").font = Font(bold=True, size=13)
    for i, n in enumerate(result.get("notes") or [], start=3):
        ws3.cell(row=i, column=1, value=n).alignment = Alignment(wrap_text=True, vertical="top")
    ws3.column_dimensions["A"].width = 120

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname_bits = ["profitability"]
    if platform:  fname_bits.append(platform)
    if date_from: fname_bits.append(date_from)
    if date_to:   fname_bits.append(date_to)
    filename = "_".join(fname_bits) + ".xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )





# ---------- COSTING (live preview) ----------
@api.post("/costing/preview")
async def costing_preview(payload: StyleIn, request: Request):
    await get_current_user(request)
    return compute_style_costing(payload.model_dump())


# ---------- PURCHASE ORDERS ----------
@api.get("/pos")
async def list_pos(request: Request):
    await get_current_user(request)
    docs = await db.pos.find({}).sort("created_at", -1).to_list(1000)
    return [stringify(d) for d in docs]

@api.get("/pos/{pid}")
async def get_po(pid: str, request: Request):
    await get_current_user(request)
    d = await db.pos.find_one({"_id": oid(pid)})
    if not d:
        raise HTTPException(404, "Not found")
    return stringify(d)

async def resolve_style(
    source_type: str,
    source_name: str,
    external_sku: str,
    external_color: Optional[str] = None,
    external_size: Optional[str] = None,
) -> dict:
    """Canonical resolver: external SKU → internal style + translated color/size.

    Resolution order:
      1. Exact match in sku_map on (source_type, source_name, external_sku) — all
         comparisons are case-insensitive and trimmed.
         If found: translate color and size through the mapping's color_map / size_map
         (pass values through unchanged when a key is absent from the map).
      2. Fallback: exact case-insensitive match on styles.code — backward compat for
         existing B2B flows that already use the internal code on their POs.
      3. Neither matched: return matched=False so the caller can queue it for manual
         mapping via the /sku-map UI.

    Returns a dict with keys:
      style_id   – str ObjectId or None
      style_code – str internal code or None
      color      – translated internal color string (or original if no mapping)
      size       – translated internal size  string (or original if no mapping)
      matched    – bool  (False when nothing resolved)
      match_via  – "sku_map" | "style_code" | None  (audit trail)
      mapping_id – str ObjectId of the sku_map doc, or None
      mapped_from_sku – the original external_sku that triggered a sku_map hit, or None
    """
    ext_sku    = (external_sku   or "").strip()
    ext_color  = (external_color or "").strip()
    ext_size   = (external_size  or "").strip()
    src_name   = (source_name    or "").strip()
    src_type   = (source_type    or "").strip()

    # ── Pass 1: sku_map lookup ──────────────────────────────────────────────
    mapping = await db.sku_map.find_one({
        "source_type": src_type,
        "source_name": {"$regex": f"^{re.escape(src_name)}$", "$options": "i"},
        "external_sku": {"$regex": f"^{re.escape(ext_sku)}$",  "$options": "i"},
    })

    if mapping:
        style = await db.styles.find_one({"_id": ObjectId(mapping["style_id"])})
        if style:
            color_map: dict = mapping.get("color_map") or {}
            size_map:  dict = mapping.get("size_map")  or {}
            # Translate: try the external value as-is first, then case-insensitive fallback
            def translate(m: dict, val: str) -> str:
                val = (val or "").strip()
                if val and val in m:
                    return m[val]
                if val:
                    val_lower = val.lower()
                    for k, v in m.items():
                        if k.lower() == val_lower:
                            return v
                # Fallback: if input val is empty or unmapped, but map has a single entry,
                # use that single mapped value (e.g. sku_map maps external_sku → single color/size)
                if len(m) == 1:
                    return next(iter(m.values()))
                return val

            return {
                "style_id":       str(style["_id"]),
                "style_code":     style["code"],
                "color":          translate(color_map, ext_color),
                "size":           translate(size_map,  ext_size),
                "matched":        True,
                "match_via":      "sku_map",
                "mapping_id":     str(mapping["_id"]),
                "mapped_from_sku": ext_sku,
            }

    # ── Pass 2: fallback – exact case-insensitive match on styles.code ──────
    style = await db.styles.find_one(
        {"code": {"$regex": f"^{re.escape(ext_sku)}$", "$options": "i"}}
    )
    if style:
        return {
            "style_id":       str(style["_id"]),
            "style_code":     style["code"],
            "color":          ext_color,   # no mapping available, pass through
            "size":           ext_size,
            "matched":        True,
            "match_via":      "style_code",
            "mapping_id":     None,
            "mapped_from_sku": None,
        }

    # ── Pass 3: nothing found ────────────────────────────────────────────────
    return {
        "style_id":       None,
        "style_code":     None,
        "color":          ext_color,
        "size":           ext_size,
        "matched":        False,
        "match_via":      None,
        "mapping_id":     None,
        "mapped_from_sku": None,
    }


async def _update_unmatched_jobs_for_sku_mapping(mapping_id: str, mapping_doc: dict):
    """Scan and resolve all 'unmatched' production jobs that can now be resolved

    by the newly created or updated SKU mapping. Updates style_id, style_code,
    style_match_status, and translates color/size.
    """
    style_id = mapping_doc.get("style_id")
    style_code = mapping_doc.get("style_code")
    source_name = mapping_doc.get("source_name", "").strip()
    external_sku = mapping_doc.get("external_sku", "").strip()

    if not style_id or not style_code or not source_name or not external_sku:
        return

    # Find jobs where client_name matches source_name and style_code matches external_sku
    jobs = await db.production_jobs.find({
        "style_match_status": "unmatched",
        "client_name": {"$regex": f"^{re.escape(source_name)}$", "$options": "i"},
        "style_code": {"$regex": f"^{re.escape(external_sku)}$", "$options": "i"},
    }).to_list(2000)

    if not jobs:
        return

    color_map = mapping_doc.get("color_map") or {}
    size_map = mapping_doc.get("size_map") or {}

    def translate(m: dict, val: str) -> str:
        if not val:
            return val
        if val in m:
            return m[val]
        val_lower = val.lower()
        for k, v in m.items():
            if k.lower() == val_lower:
                return v
        return val

    for j in jobs:
        ext_color = j.get("color") or ""
        ext_size = str(j.get("size") or "")

        translated_color = translate(color_map, ext_color)
        translated_size = translate(size_map, ext_size)

        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {"$set": {
                "style_id": style_id,
                "style_code": style_code,
                "style_match_status": "mapped",
                "mapped_from_sku": external_sku,
                "sku_mapping_id": str(mapping_id),
                "color": translated_color,
                "size": translated_size,
                "updated_at": now_iso(),
            }}
        )


async def validate_po_styles(payload: POIn):
    """Validate and normalise style codes on a PO payload.

    Pass 1 — exact case-insensitive match against styles.code.
    Pass 2 — for any line item still unresolved, try the sku_map cross-reference
             using (client_name, external_sku). If resolved, the line item's
             style_code is replaced with the internal SSK code and any
             color/size translations from the mapping are applied.
    Pass 3 — NO MORE AUTO-CREATE. Codes still unresolved after passes 1+2
             cause an HTTP 422 with a structured `unresolved_line_items` list
             so the frontend can prompt the user to either map the external
             code to an internal SSK style or explicitly create a new one.
             This prevents the flood of "Auto-created Style …" ghosts that
             appeared in Styles/Pipeline every time a PO was uploaded.
    """
    all_styles = await db.styles.find({}, {"code": 1}).to_list(10000)
    existing_codes_upper = {s["code"].strip().upper(): s["code"] for s in all_styles}

    # Pass 1 — exact match
    unresolved = []          # (index, original external code)
    for i, li in enumerate(payload.line_items):
        ext_code = (li.style_code or "").strip()
        if not ext_code:
            raise HTTPException(422, {
                "message": f"Line item #{i+1} has no style_code.",
                "unresolved_line_items": [],
            })
        if ext_code.upper() in existing_codes_upper:
            li.style_code = existing_codes_upper[ext_code.upper()]   # normalise casing
        else:
            unresolved.append((i, ext_code))

    # Pass 2 — resolve_style() sku_map lookup
    still_missing = []       # list of {"index": int, "external_code": str, "color": ..., "size": ...}
    for i, ext_code in unresolved:
        li_obj = payload.line_items[i]
        result = await resolve_style(
            source_type="b2b_client",      # POs are always B2B in this flow
            source_name=payload.client_name,
            external_sku=ext_code,
            external_color=li_obj.color or None,
            external_size=str(li_obj.size) if li_obj.size else None,
        )
        if result["matched"] and result["match_via"] == "sku_map":
            payload.line_items[i].style_code = result["style_code"]
            if result["color"] and result["color"] != (li_obj.color or ""):
                payload.line_items[i].color = result["color"]
            if result["size"] and result["size"] != str(li_obj.size or ""):
                payload.line_items[i].size = result["size"]
            payload.line_items[i].__dict__["_sku_map_meta"] = {
                "mapped_from_sku": result["mapped_from_sku"],
                "mapping_id":      result["mapping_id"],
            }
        elif result["matched"] and result["match_via"] == "style_code":
            payload.line_items[i].style_code = result["style_code"]
        else:
            still_missing.append({
                "line_index":    i,
                "external_code": ext_code,
                "description":   li_obj.description or "",
                "color":         li_obj.color or "",
                "size":          str(li_obj.size or ""),
                "quantity":      li_obj.quantity,
            })

    # Pass 3 — refuse the PO if anything is still unresolved. The FE surfaces
    # this to the user with a mapping/create prompt (see POs.jsx handleSubmit).
    if still_missing:
        raise HTTPException(422, {
            "message": (
                f"{len(still_missing)} line item(s) reference style codes that "
                f"don't exist in our catalogue. Map each external code to an "
                f"existing SSK style (or create the styles first), then re-submit."
            ),
            "unresolved_line_items": still_missing,
            "client_name":           payload.client_name,
        })

@api.post("/pos/validate-styles")
async def validate_po_styles_endpoint(payload: POIn, request: Request):
    """Dry-run of validate_po_styles — returns { ok: true } if every line
    item resolves via (styles.code | sku_map). Returns HTTP 422 with the
    same `unresolved_line_items` shape as POST /pos so the FE can render
    the mapping/create prompt without actually saving a PO.

    The frontend calls this on the "Save PO" flow before hitting POST /pos,
    so we surface the mapping requirement inline instead of only via a
    failed submit.
    """
    await get_current_user(request)
    await validate_po_styles(payload)   # raises 422 on unresolved
    return {"ok": True, "line_count": len(payload.line_items)}


@api.post("/pos")
async def create_po(payload: POIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    await validate_po_styles(payload)
    po_num = payload.po_number.strip()
    if await db.pos.find_one({"po_number": {"$regex": f"^{re.escape(po_num)}$", "$options": "i"}}):
        raise HTTPException(status_code=409, detail=f"Purchase Order with PO number '{po_num}' already exists")
    payload.po_number = po_num
    doc = payload.model_dump()
    doc["status"] = "pending"
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    if not doc.get("total_quantity"):
        doc["total_quantity"] = sum(li["quantity"] for li in doc["line_items"])
    if not doc.get("subtotal"):
        doc["subtotal"] = sum(li["amount"] for li in doc["line_items"])
    try:
        res = await db.pos.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Purchase Order with PO number '{po_num}' already exists")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    # auto-create production jobs (one per line item)
    jobs = []
    durations = await _get_stage_durations()
    entered = now_iso()
    deadline = _compute_deadline(entered, durations.get("procurement", 24))
    
    all_styles = await db.styles.find({}, {"code": 1, "_id": 1}).to_list(10000)
    style_id_map = {s["code"].strip().upper(): str(s["_id"]) for s in all_styles}

    # Build a lookup of sku_map metadata stored on payload line items during validate_po_styles
    sku_meta_by_code = {}
    for li_obj in payload.line_items:
        meta = getattr(li_obj, "__dict__", {}).get("_sku_map_meta")
        if meta:
            sku_meta_by_code[li_obj.style_code.strip().upper()] = meta

    for li in doc["line_items"]:
        style_code_upper = li["style_code"].strip().upper()
        style_id = style_id_map.get(style_code_upper)
        sku_meta = sku_meta_by_code.get(style_code_upper)

        if style_id and sku_meta:
            match_status = "mapped"      # resolved via sku_map cross-reference
        elif style_id:
            match_status = "matched"     # direct exact match against styles.code
        else:
            match_status = "unmatched"   # not found anywhere

        jobs.append({
            "source_type": "b2b_client",
            "po_id": doc["id"],
            "po_number": doc["po_number"],
            "client_name": doc["client_name"],
            "style_code": li["style_code"],
            "style_id": style_id,
            "source_type": "b2b_client",
            "style_match_status": match_status,
            **(({"mapped_from_sku": sku_meta["mapped_from_sku"], "sku_mapping_id": sku_meta["mapping_id"]}) if sku_meta else {}),
            "description": li.get("description", ""),
            "color": li.get("color", ""),
            "size": li.get("size", ""),
            "quantity": li["quantity"],
            "completed_qty": 0,
            "stage": "procurement",
            "rejected_qty": 0,
            "delivery_date": doc.get("delivery_date", ""),
            "stage_entered_at": entered,
            "stage_deadline": deadline,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "history": [{"stage": "procurement", "at": now_iso(), "by": u["email"], "notes": "Job created"}],
        })
    if jobs:
        await db.production_jobs.insert_many(jobs)
    return doc

@api.patch("/pos/{pid}")
async def update_po(pid: str, payload: POIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    await validate_po_styles(payload)
    po_num = payload.po_number.strip()
    if await db.pos.find_one({"po_number": {"$regex": f"^{re.escape(po_num)}$", "$options": "i"}, "_id": {"$ne": oid(pid)}}):
        raise HTTPException(status_code=409, detail=f"Purchase Order with PO number '{po_num}' already exists")
    payload.po_number = po_num
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.pos.update_one({"_id": oid(pid)}, {"$set": update})
    return stringify(await db.pos.find_one({"_id": oid(pid)}))

@api.delete("/pos/{pid}")
async def delete_po(pid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.pos.delete_one({"_id": oid(pid)})
    await db.production_jobs.delete_many({"po_id": pid})
    return {"ok": True}

@api.post("/pos/extract", dependencies=[Depends(upload_rate_limiter)])
async def extract_po(file: UploadFile = File(...), request: Request = None):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds the maximum limit of 10MB.")
    fname = (file.filename or "").lower()
    try:
        if fname.endswith(".pdf"):
            data = await extract_po_from_pdf(content)
        elif fname.endswith(".xlsx") or fname.endswith(".xls"):
            data = await extract_po_from_xlsx(content)
        else:
            raise HTTPException(400, "Only PDF or Excel (xlsx) files are supported")
        return data
    except HTTPException:
        raise
    except Exception as e:
        log.exception("PO extraction failed")
        raise HTTPException(500, f"Extraction failed: {e}")


async def next_invoice_no() -> str:
    """Generate SSK<FY>-XXX format like SSK26-27-004. FY based on Apr-Mar split."""
    today = datetime.now(timezone.utc)
    # Indian FY starts April. If month < 4, FY started prev year.
    yr = today.year
    if today.month < 4:
        fy_start = yr - 1
    else:
        fy_start = yr
    fy_end = fy_start + 1
    fy_label = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}"
    # Atomic counter
    counter = await db.counters.find_one_and_update(
        {"_id": f"invoice_{fy_label}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    seq = counter.get("seq", 1) if counter else 1
    return f"SSK{fy_label}-{seq:03d}"


# ---------- ACCOUNTS-RECEIVABLE HELPERS ----------
def _extract_credit_days(payment_terms_text: str | None) -> int:
    """Pull credit days from a free-text payment-terms field (e.g., 'Net 30',
    '45 days', 'within 60 days from invoice'). Falls back to DEFAULT_CREDIT_DAYS."""
    if not payment_terms_text:
        return DEFAULT_CREDIT_DAYS
    m = re.search(r"(\d{1,3})\s*(?:days|d)?\b", str(payment_terms_text), flags=re.I)
    if m:
        n = int(m.group(1))
        if 0 < n < 365:
            return n
    return DEFAULT_CREDIT_DAYS


def _due_iso(invoice_date_str: str, credit_days: int) -> str:
    """Convert an `invoice_date` (DD/MM/YYYY) + credit_days into YYYY-MM-DD."""
    try:
        if "/" in invoice_date_str:
            base = datetime.strptime(invoice_date_str, "%d/%m/%Y")
        else:
            base = datetime.strptime(invoice_date_str[:10], "%Y-%m-%d")
    except Exception:
        base = datetime.now()
    return (base + timedelta(days=int(credit_days))).date().isoformat()


def _compute_invoice_totals(po: dict, line_items: list[dict]) -> dict:
    """Subtotal + CGST/SGST/IGST + grand_total from line items, using PO rates."""
    subtotal = sum(float(li.get("amount") or 0) for li in line_items)
    qty = sum(int(li.get("quantity") or 0) for li in line_items)
    cgst_rate = float(po.get("cgst_rate") or 0)
    sgst_rate = float(po.get("sgst_rate") or 0)
    igst_rate = float(po.get("igst_rate") or 0)
    cgst_amt = round(subtotal * cgst_rate / 100, 2)
    sgst_amt = round(subtotal * sgst_rate / 100, 2)
    igst_amt = round(subtotal * igst_rate / 100, 2)
    grand = round(subtotal + cgst_amt + sgst_amt + igst_amt, 2)
    return {
        "subtotal": round(subtotal, 2),
        "total_quantity": qty,
        "cgst_amount": cgst_amt, "sgst_amount": sgst_amt, "igst_amount": igst_amt,
        "cgst_rate": cgst_rate, "sgst_rate": sgst_rate, "igst_rate": igst_rate,
        "grand_total": grand,
    }


def _invoice_iso_date(d: str) -> str:
    """Normalise an invoice_date (DD/MM/YYYY) to YYYY-MM-DD for consistent sorting."""
    try:
        if "/" in d:
            return datetime.strptime(d, "%d/%m/%Y").date().isoformat()
        return datetime.strptime(d[:10], "%Y-%m-%d").date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def _decorate_invoice(doc: dict, payments_map: dict | None = None, grns_map: dict | None = None) -> dict:
    """Compute live status + outstanding from saved invoice doc + payments/grns aggregates."""
    inv = stringify(doc)
    iid = inv.get("id")
    paid = float((payments_map or {}).get(iid, 0))
    grn_adj = float((grns_map or {}).get(iid, 0))  # value of short / rejected
    grand = float(inv.get("grand_total") or 0)
    net_after_grn = max(0.0, round(grand - grn_adj, 2))
    outstanding = max(0.0, round(net_after_grn - paid, 2))
    inv["received_amount"] = round(paid, 2)
    inv["grn_adjustment"] = round(grn_adj, 2)
    inv["net_amount"] = net_after_grn
    inv["outstanding"] = outstanding
    today_iso = datetime.now().date().isoformat()
    due = inv.get("due_date") or ""
    if outstanding <= 0.01:
        inv["status"] = "paid"
    elif paid > 0.01:
        inv["status"] = "partial"
    elif due and due < today_iso:
        inv["status"] = "overdue"
    else:
        inv["status"] = "pending"
    if due:
        try:
            days = (datetime.fromisoformat(due) - datetime.now()).days
            inv["days_to_due"] = days
        except Exception:
            inv["days_to_due"] = None
    return inv


async def _aggregate_payments_for_invoices(invoice_ids: list[str]) -> dict[str, float]:
    """Returns invoice_id -> total received (across all payments)."""
    if not invoice_ids:
        return {}
    payments = await db.payments.find({"invoice_ids": {"$in": invoice_ids}}).to_list(5000)
    out: dict[str, float] = {iid: 0.0 for iid in invoice_ids}
    for p in payments:
        # If a payment was allocated across multiple invoices we treat it pro-rata
        allocs = p.get("allocations") or {}
        if allocs:
            for iid, amt in allocs.items():
                if iid in out:
                    out[iid] += float(amt or 0)
        else:
            amt = float(p.get("amount") or 0)
            ids = [i for i in (p.get("invoice_ids") or []) if i in out]
            if ids:
                share = amt / len(ids)
                for iid in ids:
                    out[iid] += share
    return out


async def _aggregate_grn_adjustments(invoice_ids: list[str]) -> dict[str, float]:
    """Returns invoice_id -> rupee value of short/rejected qty across all GRNs."""
    if not invoice_ids:
        return {}
    grns = await db.grns.find({"invoice_id": {"$in": invoice_ids}}).to_list(5000)
    out: dict[str, float] = {iid: 0.0 for iid in invoice_ids}
    # Fetch parent invoices to get unit prices for adjustment
    invoices = await db.invoices.find({"_id": {"$in": [oid(i) for i in invoice_ids]}}).to_list(5000)
    inv_by_id = {str(d["_id"]): d for d in invoices}
    for g in grns:
        inv = inv_by_id.get(g.get("invoice_id"))
        if not inv:
            continue
        # Build a price map: (style, color, size) -> unit_price
        prices = {(li.get("style_code"), li.get("color"), str(li.get("size") or "")):
                  float(li.get("unit_price") or 0) for li in (inv.get("line_items_snapshot") or [])}
        for ln in g.get("line_items", []):
            short = max(0, int(ln.get("dispatched_qty", 0)) - int(ln.get("accepted_qty", 0)))
            key = (ln.get("style_code"), ln.get("color"), str(ln.get("size") or ""))
            unit = prices.get(key) or 0
            out[g["invoice_id"]] += short * unit
    return out


async def next_grn_no() -> str:
    seq = await db.counters.find_one_and_update(
        {"_id": "grn_seq"}, {"$inc": {"v": 1}}, upsert=True, return_document=True,
    )
    n = (seq or {}).get("v", 1)
    return f"GRN-{datetime.now().year}-{n:04d}"


async def next_payment_no() -> str:
    seq = await db.counters.find_one_and_update(
        {"_id": "payment_seq"}, {"$inc": {"v": 1}}, upsert=True, return_document=True,
    )
    n = (seq or {}).get("v", 1)
    return f"RCT-{datetime.now().year}-{n:04d}"


async def next_vendor_po_no() -> str:
    seq = await db.counters.find_one_and_update(
        {"_id": "vendor_po_seq"}, {"$inc": {"v": 1}}, upsert=True, return_document=True,
    )
    n = (seq or {}).get("v", 1)
    return f"PO-VEN-{datetime.now().year}-{n:04d}"


async def _generate_invoice_payload(po: dict, job_ids: list[str] | None) -> tuple[dict, list[dict]]:
    """Returns the (po-augmented, line_items) for invoice generation.

    If job_ids given, filter dispatched jobs and rebuild line items from them — supports merged
    invoice across multiple dispatched cards.
    """
    if not job_ids:
        return po, po.get("line_items", [])

    # Pull dispatched production_jobs by ids, aggregate per (style_code, color, size)
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    # Build map of line items from PO indexed by (style, color, size)
    po_items = po.get("line_items", [])
    idx = {}
    for li in po_items:
        idx[(li.get("style_code"), li.get("color"), str(li.get("size", "")))] = li

    line_items = []
    for j in jobs:
        key = (j.get("style_code"), j.get("color"), str(j.get("size", "")))
        li_src = idx.get(key, {})
        qty = j.get("quantity", 0)
        unit_price = li_src.get("unit_price", 0)
        line_items.append({
            "style_code": j.get("style_code", ""),
            "description": j.get("description") or li_src.get("description", ""),
            "color": j.get("color", ""),
            "size": str(j.get("size", "")),
            "hsn_code": li_src.get("hsn_code", "") or "64029990",
            "quantity": qty,
            "unit_price": unit_price,
            "amount": round(qty * unit_price, 2),
            "mrp": li_src.get("mrp", ""),
        })
    return po, line_items


@api.get("/pos/{pid}/invoice.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def po_invoice(pid: str, request: Request):
    await get_current_user(request)
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "Not found")
    po = stringify(doc)
    # auto-issue invoice number on first download (and persist)
    invoice_no = po.get("invoice_no")
    invoice_date = po.get("invoice_date")
    if not invoice_no:
        invoice_no = await next_invoice_no()
        invoice_date = datetime.now().strftime("%d/%m/%Y")
        await db.pos.update_one({"_id": oid(pid)}, {"$set": {"invoice_no": invoice_no, "invoice_date": invoice_date}})
        po["invoice_no"] = invoice_no
        po["invoice_date"] = invoice_date
    pdf_bytes = build_invoice(po, invoice_no, invoice_date)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_no}.pdf"'},
    )


@api.post("/invoices/job", dependencies=[Depends(pdf_rate_limiter)])
async def invoice_for_jobs(payload: InvoiceGenerate, request: Request):
    """Generate an invoice for a subset of production jobs (dispatched). Supports merging."""
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)
    po, line_items = await _generate_invoice_payload(po, payload.job_ids)
    if not line_items:
        raise HTTPException(400, "No line items for invoice")

    invoice_no = await next_invoice_no()
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    pdf_bytes = build_invoice(
        po, invoice_no, invoice_date,
        transport_mode=payload.transport_mode or "",
        vehicle_no=payload.vehicle_no or "",
        supply_date=payload.supply_date or "",
        line_items=line_items,
    )
    # Compute totals + due date for AR tracking
    totals = _compute_invoice_totals(po, line_items)
    credit_days = _extract_credit_days(po.get("payment_terms", ""))
    invoice_iso = _invoice_iso_date(invoice_date)
    due_date = _due_iso(invoice_date, credit_days)
    import base64 as _b64
    # Store invoice record (includes file bytes for re-download)
    inv_doc = {
        "invoice_no": invoice_no, "invoice_date": invoice_date,
        "invoice_iso_date": invoice_iso,
        "due_date": due_date, "payment_terms_days": credit_days,
        "po_id": payload.po_id, "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")],
        "client_name": po.get("client_name"),
        "job_ids": payload.job_ids or [],
        "line_items_snapshot": line_items,
        **totals,
        "transport_mode": payload.transport_mode, "vehicle_no": payload.vehicle_no,
        "supply_date": payload.supply_date,
        "by": u["email"], "created_at": now_iso(),
        "file_b64": _b64.b64encode(pdf_bytes).decode("ascii"),
        "merged": False,
    }
    res = await db.invoices.insert_one(inv_doc)
    # Map packed cartons to dispatch
    cartons = await db.packing_cartons.find({"job_id": {"$in": payload.job_ids or []}, "status": "packed"}).to_list(10000)
    for idx, carton in enumerate(cartons):
        await db.packing_cartons.update_one(
            {"_id": carton["_id"]},
            {"$set": {
                "status": "dispatched",
                "invoice_id": str(res.inserted_id),
                "box_number": idx + 1
            }}
        )
    # Flag jobs as invoiced; auto-archive if packing list already generated.
    await _flag_jobs(payload.job_ids or [], "invoice_generated_at")
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice_no}.pdf"',
            "X-Invoice-Id": str(res.inserted_id),
        },
    )

@api.delete("/invoices/{id}")
async def delete_invoice(id: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    inv = await db.invoices.find_one({"_id": oid(id)})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    
    # Revert jobs
    job_ids = inv.get("job_ids", [])
    if job_ids:
        obj_ids = [oid(j) for j in job_ids]
        await db.production_jobs.update_many(
            {"_id": {"$in": obj_ids}},
            {"$set": {"stage": "qc_pack"}, "$unset": {"invoice_generated_at": ""}}
        )
        for o_id in obj_ids:
            await db.production_jobs.update_one(
                {"_id": o_id},
                {"$push": {"history": {
                    "stage": "qc_pack", "at": now_iso(), "by": u["email"],
                    "notes": f"Invoice {inv.get('invoice_no')} deleted; stage reverted to QC & Pack",
                    "qc_pass": None, "rejected_qty": 0
                }}}
            )
    
    # Revert cartons
    await db.packing_cartons.update_many(
        {"invoice_id": id},
        {"$set": {
            "status": "packed",
            "invoice_id": None,
            "box_number": None
        }}
    )
    
    # Delete payments for this invoice
    await db.payments.delete_many({"invoice_id": id})
    
    # Delete the invoice
    await db.invoices.delete_one({"_id": oid(id)})
    return {"ok": True}


@api.post("/invoices/merged", dependencies=[Depends(pdf_rate_limiter)])
async def merged_invoice(payload: dict, request: Request):
    """Generate a single merged invoice across multiple POs/jobs.
    payload: { entries: [{po_id, job_ids:[...]}] , transport_mode, vehicle_no, supply_date }
    All entries must share the same client (uses first PO's client).
    """
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    entries = payload.get("entries", [])
    if not entries:
        raise HTTPException(400, "No entries")

    # use first PO as the parent (for client/billing/etc.)
    first_po = await db.pos.find_one({"_id": oid(entries[0]["po_id"])})
    if not first_po:
        raise HTTPException(404, "First PO not found")
    parent = stringify(first_po)

    all_items = []
    po_numbers = []
    job_ids_all = []
    for e in entries:
        po_doc = await db.pos.find_one({"_id": oid(e["po_id"])})
        if not po_doc:
            continue
        po_x = stringify(po_doc)
        po_numbers.append(po_x.get("po_number", ""))
        _, lis = await _generate_invoice_payload(po_x, e.get("job_ids"))
        all_items.extend(lis)
        job_ids_all.extend(e.get("job_ids") or [])

    if len(set([p for p in po_numbers if p])) > 1:
        raise HTTPException(400, "Cannot merge invoices across different POs")

    if not all_items:
        raise HTTPException(400, "No line items found across entries")

    invoice_no = await next_invoice_no()
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    # show comma-joined PO numbers in the parent for the meta block
    parent["po_number"] = ", ".join([p for p in po_numbers if p])
    pdf_bytes = build_invoice(
        parent, invoice_no, invoice_date,
        transport_mode=payload.get("transport_mode", ""),
        vehicle_no=payload.get("vehicle_no", ""),
        supply_date=payload.get("supply_date", ""),
        line_items=all_items,
    )
    import base64 as _b64m
    credit_days_m = _extract_credit_days(parent.get("payment_terms", ""))
    inv_doc_m = {
        "invoice_no": invoice_no, "invoice_date": invoice_date,
        "invoice_iso_date": _invoice_iso_date(invoice_date),
        "due_date": _due_iso(invoice_date, credit_days_m),
        "payment_terms_days": credit_days_m,
        "merged": True, "po_numbers": po_numbers, "job_ids": job_ids_all,
        "po_id": str(first_po.get("_id")),
        "po_number": " + ".join(po_numbers),
        "client_name": parent.get("client_name"),
        "line_items_snapshot": all_items,
        **_compute_invoice_totals(parent, all_items),
        "by": u["email"], "created_at": now_iso(),
        "file_b64": _b64m.b64encode(pdf_bytes).decode("ascii"),
    }
    res_m = await db.invoices.insert_one(inv_doc_m)
    # Map packed cartons to dispatch
    cartons_m = await db.packing_cartons.find({"job_id": {"$in": job_ids_all}, "status": "packed"}).to_list(10000)
    for idx, carton in enumerate(cartons_m):
        await db.packing_cartons.update_one(
            {"_id": carton["_id"]},
            {"$set": {
                "status": "dispatched",
                "invoice_id": str(res_m.inserted_id),
                "box_number": idx + 1
            }}
        )
    await _flag_jobs(job_ids_all, "invoice_generated_at")
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice_no}.pdf"',
            "X-Invoice-Id": str(res_m.inserted_id),
        },
    )


@api.get("/pos/{pid}/challan.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def po_challan(pid: str, request: Request, dispatch_qty: Optional[int] = None,
                     transporter: str = "", vehicle: str = ""):
    await get_current_user(request)
    doc = await db.pos.find_one({"_id": oid(pid)})
    if not doc:
        raise HTTPException(404, "Not found")
    po = stringify(doc)
    pdf_bytes = generate_dispatch_challan_pdf(po, dispatch_qty=dispatch_qty,
                                              transporter=transporter, vehicle=vehicle)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="challan-{po.get("po_number","po")}.pdf"'},
    )


# ---------- INVOICE ARCHIVE & ACCOUNTS RECEIVABLE ----------
@api.get("/invoices")
async def list_invoices(request: Request, client: Optional[str] = None,
                        status: Optional[str] = None, include_legacy: bool = False,
                        limit: int = 500):
    """Return all generated invoices, decorated with live status + outstanding."""
    await get_current_user(request)
    q: dict = {}
    if not include_legacy:
        q["legacy"] = {"$ne": True}
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    docs = await db.invoices.find(q, {"file_b64": 0}).sort("created_at", -1).to_list(limit)
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids)
    grn_map = await _aggregate_grn_adjustments(inv_ids)
    rows = [_decorate_invoice(d, pay_map, grn_map) for d in docs]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows


@api.get("/invoices/overdue")
async def overdue_invoices(request: Request):
    await get_current_user(request)
    docs = await db.invoices.find({}, {"file_b64": 0}).sort("due_date", 1).to_list(500)
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids)
    grn_map = await _aggregate_grn_adjustments(inv_ids)
    rows = [_decorate_invoice(d, pay_map, grn_map) for d in docs]
    return [r for r in rows if r["status"] == "overdue"]


@api.get("/invoices/{iid}")
async def get_invoice(iid: str, request: Request):
    await get_current_user(request)
    doc = await db.invoices.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Invoice not found")
    pay_map = await _aggregate_payments_for_invoices([iid])
    grn_map = await _aggregate_grn_adjustments([iid])
    inv = _decorate_invoice(doc, pay_map, grn_map)
    inv.pop("file_b64", None)
    # Attach related payments + GRNs
    payments = await db.payments.find({"invoice_ids": iid}).sort("payment_date", -1).to_list(200)
    grns = await db.grns.find({"invoice_id": iid}).sort("grn_date", -1).to_list(200)
    inv["payments"] = [stringify(p) for p in payments]
    inv["grns"] = [stringify(g) for g in grns]
    return inv


@api.get("/invoices/{iid}/file", dependencies=[Depends(pdf_rate_limiter)])
async def download_invoice_file(iid: str, request: Request):
    await get_current_user(request)
    doc = await db.invoices.find_one({"_id": oid(iid)})
    if not doc:
        raise HTTPException(404, "Invoice not found")
    import base64 as _b
    raw = _b.b64decode(doc.get("file_b64", "") or b"")
    if not raw:
        raise HTTPException(404, "No PDF stored for this invoice (predates persistence). Regenerate from the PO.")
    fname = f"{doc.get('invoice_no', 'invoice')}.pdf"
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


# ---------- GOODS RECEIPT NOTES (GRN) ----------
@api.post("/grns")
async def create_grn(payload: GRNIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    inv = await db.invoices.find_one({"_id": oid(payload.invoice_id)})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    grn_no = await next_grn_no()
    lines = []
    total_disp = total_recv = total_acc = total_rej = 0
    for li in payload.line_items:
        disp = int(li.dispatched_qty or 0)
        recv = int(li.received_qty if li.received_qty is not None else disp)
        rej = int(li.rejected_qty or 0)
        acc = int(li.accepted_qty if li.accepted_qty is not None else (recv - rej))
        lines.append({
            "style_code": li.style_code, "description": li.description,
            "color": li.color, "size": li.size,
            "dispatched_qty": disp, "received_qty": recv,
            "accepted_qty": acc, "rejected_qty": rej,
            "rejection_reason": li.rejection_reason,
        })
        total_disp += disp; total_recv += recv; total_acc += acc; total_rej += rej
    doc = {
        "grn_no": grn_no, "grn_date": payload.grn_date,
        "received_date": payload.received_date or payload.grn_date,
        "invoice_id": payload.invoice_id, "invoice_no": inv.get("invoice_no"),
        "po_id": inv.get("po_id"), "po_number": inv.get("po_number"),
        "client_name": inv.get("client_name"),
        "client_reference": payload.client_reference,
        "notes": payload.notes,
        "line_items": lines,
        "total_dispatched": total_disp, "total_received": total_recv,
        "total_accepted": total_acc, "total_rejected": total_rej,
        "by": u["email"], "created_at": now_iso(),
    }
    res = await db.grns.insert_one(doc)
    doc["_id"] = res.inserted_id
    return stringify(doc)


@api.get("/grns")
async def list_grns(request: Request, invoice_id: Optional[str] = None,
                    client: Optional[str] = None, limit: int = 300):
    await get_current_user(request)
    q: dict = {}
    if invoice_id:
        q["invoice_id"] = invoice_id
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    docs = await db.grns.find(q).sort("grn_date", -1).to_list(limit)
    return [stringify(d) for d in docs]


@api.get("/grns/{gid}")
async def get_grn(gid: str, request: Request):
    await get_current_user(request)
    doc = await db.grns.find_one({"_id": oid(gid)})
    if not doc:
        raise HTTPException(404, "GRN not found")
    return stringify(doc)


@api.delete("/grns/{gid}")
async def delete_grn(gid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    r = await db.grns.delete_one({"_id": oid(gid)})
    if not r.deleted_count:
        raise HTTPException(404, "GRN not found")
    return {"ok": True}


# ---------- PAYMENTS ----------
@api.post("/payments")
async def create_payment(payload: PaymentIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if not payload.invoice_ids:
        raise HTTPException(400, "At least one invoice required")
    invoices = await db.invoices.find({"_id": {"$in": [oid(i) for i in payload.invoice_ids]}}).to_list(50)
    if not invoices:
        raise HTTPException(404, "No invoices found")
    # FIFO allocation by due_date (oldest first)
    invoices.sort(key=lambda d: (d.get("due_date") or "", d.get("invoice_date") or ""))
    inv_ids_str = [str(d["_id"]) for d in invoices]
    existing_paid = await _aggregate_payments_for_invoices(inv_ids_str)
    existing_grn = await _aggregate_grn_adjustments(inv_ids_str)
    remaining = float(payload.amount)
    allocations: dict[str, float] = {}
    for d in invoices:
        iid = str(d["_id"])
        net = max(0.0, float(d.get("grand_total") or 0) - existing_grn.get(iid, 0))
        outstanding = max(0.0, net - existing_paid.get(iid, 0))
        if outstanding <= 0:
            continue
        take = round(min(outstanding, remaining), 2)
        if take > 0:
            allocations[iid] = take
            remaining = round(remaining - take, 2)
        if remaining <= 0:
            break
    if not allocations:
        raise HTTPException(400, "Selected invoices are already fully paid")
    payment_no = await next_payment_no()
    doc = {
        "payment_no": payment_no,
        "payment_date": payload.payment_date,
        "amount": round(float(payload.amount), 2),
        "advance_amount": round(remaining, 2) if remaining > 0 else 0,  # over-paid surplus
        "mode": payload.mode, "reference": payload.reference, "bank": payload.bank,
        "notes": payload.notes,
        "invoice_ids": list(allocations.keys()),
        "allocations": allocations,
        "client_name": invoices[0].get("client_name"),
        "by": u["email"], "created_at": now_iso(),
    }
    res = await db.payments.insert_one(doc)
    doc["_id"] = res.inserted_id
    return stringify(doc)


@api.get("/payments")
async def list_payments(request: Request, invoice_id: Optional[str] = None,
                        client: Optional[str] = None, limit: int = 500):
    await get_current_user(request)
    q: dict = {}
    if invoice_id:
        q["invoice_ids"] = invoice_id
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    docs = await db.payments.find(q).sort("payment_date", -1).to_list(limit)
    return [stringify(d) for d in docs]


@api.delete("/payments/{pid}")
async def delete_payment(pid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    r = await db.payments.delete_one({"_id": oid(pid)})
    if not r.deleted_count:
        raise HTTPException(404, "Payment not found")
    return {"ok": True}




# ---------- VENDORS (Accounts Payable Master) ----------

@api.get("/vendors")
async def list_vendors(request: Request, include_inactive: bool = False, limit: int = 500):
    """Return all vendor master records. Default hides inactive vendors."""
    await get_current_user(request)
    q: dict = {} if include_inactive else {"active": {"$ne": False}}
    docs = await db.vendors.find(q).sort("name", 1).to_list(limit)
    return [stringify(d) for d in docs]


@api.post("/vendors", status_code=201)
async def create_vendor(payload: VendorIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = {
        **payload.model_dump(),
        "by": u["email"], "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        res = await db.vendors.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"A vendor named '{payload.name}' already exists.")
    doc["_id"] = res.inserted_id
    await log_activity("create_vendor", "vendors", f"Created vendor '{payload.name}'", u["email"])
    return stringify(doc)


@api.get("/vendors/{vid}")
async def get_vendor(vid: str, request: Request):
    await get_current_user(request)
    doc = await db.vendors.find_one({"_id": oid(vid)})
    if not doc:
        raise HTTPException(404, "Vendor not found")
    return stringify(doc)


@api.patch("/vendors/{vid}")
async def update_vendor(vid: str, payload: VendorUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    updates["updated_at"] = now_iso()
    r = await db.vendors.update_one({"_id": oid(vid)}, {"$set": updates})
    if not r.matched_count:
        raise HTTPException(404, "Vendor not found")
    doc = await db.vendors.find_one({"_id": oid(vid)})
    await log_activity("update_vendor", "vendors", f"Updated vendor id={vid}", u["email"])
    return stringify(doc)


@api.delete("/vendors/{vid}")
async def deactivate_vendor(vid: str, request: Request):
    """Soft-delete: sets active=False to preserve AP history."""
    u = await get_current_user(request); require_roles("admin")(u)
    doc = await db.vendors.find_one({"_id": oid(vid)})
    if not doc:
        raise HTTPException(404, "Vendor not found")
    await db.vendors.update_one({"_id": oid(vid)}, {"$set": {"active": False, "updated_at": now_iso()}})
    await log_activity("deactivate_vendor", "vendors", f"Deactivated vendor '{doc.get('name')}'", u["email"])
    return {"ok": True}


# ---------- VENDOR PURCHASE ORDERS (to vendors) ----------

@api.get("/vendor-pos")
async def list_vendor_pos(request: Request, vendor_id: Optional[str] = None, status: Optional[str] = None, limit: int = 500):
    await get_current_user(request)
    q: dict = {}
    if vendor_id:
        q["vendor_id"] = vendor_id
    if status:
        q["status"] = status
    docs = await db.vendor_purchase_orders.find(q).sort("created_at", -1).to_list(limit)
    
    # Decorate with vendor name
    vendors = await db.vendors.find({}).to_list(2000)
    vendor_map = {str(v["_id"]): v.get("name", "") for v in vendors}
    
    out = []
    for d in docs:
        d = stringify(d)
        d["vendor_name"] = vendor_map.get(d.get("vendor_id", ""), "Unknown Vendor")
        for li in d.get("line_items", []):
            if "received_quantity" not in li:
                li["received_quantity"] = 0.0
        out.append(d)
    return out


@api.post("/vendor-pos", status_code=201)
async def create_vendor_po(payload: VendorPOIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # Validate vendor exists
    vendor = await db.vendors.find_one({"_id": oid(payload.vendor_id)})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
        
    po_no = await next_vendor_po_no()
    doc = {
        **payload.model_dump(),
        "po_number": po_no,
        "by": u["email"],
        "processed_receipt_ids": [],
        "created_at": now_iso(),
        "updated_at": now_iso()
    }
    res = await db.vendor_purchase_orders.insert_one(doc)
    doc["_id"] = res.inserted_id
    await log_activity("create_vendor_po", "vendor_pos", f"Created Vendor PO '{po_no}'", u["email"])
    return stringify(doc)


@api.get("/vendor-pos/{id}")
async def get_vendor_po(id: str, request: Request):
    await get_current_user(request)
    doc = await db.vendor_purchase_orders.find_one({"_id": oid(id)})
    if not doc:
        raise HTTPException(404, "Vendor Purchase Order not found")
    vendor = await db.vendors.find_one({"_id": oid(doc.get("vendor_id"))})
    out = stringify(doc)
    out["vendor_name"] = vendor.get("name", "Unknown Vendor") if vendor else "Unknown Vendor"
    for li in out.get("line_items", []):
        if "received_quantity" not in li:
            li["received_quantity"] = 0.0
    return out


@api.patch("/vendor-pos/{id}")
async def update_vendor_po(id: str, payload: VendorPOUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    
    if "vendor_id" in updates:
        vendor = await db.vendors.find_one({"_id": oid(updates["vendor_id"])})
        if not vendor:
            raise HTTPException(404, "Vendor not found")

    updates["updated_at"] = now_iso()
    r = await db.vendor_purchase_orders.update_one({"_id": oid(id)}, {"$set": updates})
    if not r.matched_count:
        raise HTTPException(404, "Vendor Purchase Order not found")
        
    doc = await db.vendor_purchase_orders.find_one({"_id": oid(id)})
    await log_activity("update_vendor_po", "vendor_pos", f"Updated Vendor PO id={id}", u["email"])
    return stringify(doc)


@api.post("/vendor-pos/{id}/receive")
async def receive_vendor_po(id: str, payload: VendorPOReceiveIn, request: Request):
    u = await get_current_user(request)
    require_roles("admin", "manager")(u)
    
    po = await db.vendor_purchase_orders.find_one({"_id": oid(id)})
    if not po:
        raise HTTPException(404, "Vendor Purchase Order not found")
        
    receipt_id = payload.receipt_id
    processed = po.get("processed_receipt_ids") or []
    if receipt_id in processed:
        # Idempotent retry: already processed
        return stringify(po)
        
    vendor = await db.vendors.find_one({"_id": oid(po.get("vendor_id"))})
    vendor_name = vendor.get("name", "Unknown Vendor") if vendor else "Unknown Vendor"
    
    line_items = po.get("line_items") or []
    for li in line_items:
        if "received_quantity" not in li:
            li["received_quantity"] = 0.0
            
    li_map = {li["material_id"]: li for li in line_items}
    
    movements = []
    material_ids = [item.material_id for item in payload.items]
    materials_list = await db.materials.find({"_id": {"$in": [oid(mid) for mid in material_ids]}}).to_list(100)
    materials_map = {str(m["_id"]): m for m in materials_list}
    
    for item in payload.items:
        if item.material_id not in li_map:
            raise HTTPException(400, f"Material {item.material_id} is not in PO line items")
        if item.quantity <= 0:
            continue
            
        li = li_map[item.material_id]
        li["received_quantity"] = round(li["received_quantity"] + item.quantity, 4)
        
        mat = materials_map.get(item.material_id)
        if not mat:
            raise HTTPException(404, f"Material {item.material_id} not found in DB")
            
        movements.append({
            "material_id": item.material_id,
            "material_code": mat.get("code"),
            "material_name": mat.get("name"),
            "unit": mat.get("unit"),
            "type": "in",
            "quantity": item.quantity,
            "rate": li.get("rate") or mat.get("rate") or 0.0,
            "party": vendor_name,
            "vendor_po_id": str(po["_id"]),
            "receipt_id": receipt_id,
            "notes": f"Received against PO {po.get('po_number')}",
            "by": u["email"],
            "date": datetime.now(timezone.utc).date().isoformat(),
            "created_at": now_iso(),
            "auto": True
        })
        
    if movements:
        # Determine status
        all_received = True
        any_received = False
        for li in line_items:
            req_qty = li.get("quantity", 0)
            rec_qty = li.get("received_quantity", 0)
            if rec_qty < req_qty:
                all_received = False
            if rec_qty > 0:
                any_received = True
                
        new_status = po.get("status", "draft")
        if all_received:
            new_status = "received"
        elif any_received:
            new_status = "partially_received"
            
        processed.append(receipt_id)
        
        await db.vendor_purchase_orders.update_one(
            {"_id": po["_id"]},
            {"$set": {
                "line_items": line_items,
                "status": new_status,
                "processed_receipt_ids": processed,
                "updated_at": now_iso()
            }}
        )
        await db.inventory_movements.insert_many(movements)
        po = await db.vendor_purchase_orders.find_one({"_id": po["_id"]})
        
    await log_activity("receive_vendor_po", "vendor_pos", f"Received materials for PO {po.get('po_number')} (receipt: {receipt_id})", u["email"])
    return stringify(po)


@api.delete("/vendor-pos/{id}")
async def delete_vendor_po(id: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    r = await db.vendor_purchase_orders.delete_one({"_id": oid(id)})
    if not r.deleted_count:
        raise HTTPException(404, "Vendor Purchase Order not found")
    await log_activity("delete_vendor_po", "vendor_pos", f"Deleted Vendor PO id={id}", u["email"])
    return {"ok": True}


# ---------- CLIENTS / TALLY-STYLE LEDGER ----------

@api.get("/clients")
async def list_clients(request: Request):
    """Return unique clients seen on invoices + their aggregate AR snapshot."""
    await get_current_user(request)
    docs = await db.invoices.find({}, {"file_b64": 0}).to_list(5000)
    if not docs:
        return []
    inv_ids = [str(d["_id"]) for d in docs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids)
    grn_map = await _aggregate_grn_adjustments(inv_ids)
    decorated = [_decorate_invoice(d, pay_map, grn_map) for d in docs]
    summary: dict[str, dict] = {}
    for r in decorated:
        client = r.get("client_name") or "—"
        slot = summary.setdefault(client, {
            "client_name": client, "invoice_count": 0,
            "total_invoiced": 0.0, "total_received": 0.0,
            "outstanding": 0.0, "overdue_count": 0, "overdue_amount": 0.0,
        })
        slot["invoice_count"] += 1
        slot["total_invoiced"] += float(r.get("net_amount") or 0)
        slot["total_received"] += float(r.get("received_amount") or 0)
        slot["outstanding"] += float(r.get("outstanding") or 0)
        if r.get("status") == "overdue":
            slot["overdue_count"] += 1
            slot["overdue_amount"] += float(r.get("outstanding") or 0)
    out = list(summary.values())
    for s in out:
        for k in ("total_invoiced", "total_received", "outstanding", "overdue_amount"):
            s[k] = round(s[k], 2)
    out.sort(key=lambda s: -s["outstanding"])
    return out


@api.get("/clients/{client_name}/ledger")
async def client_ledger(client_name: str, request: Request):
    """Tally-style ledger for a single client.

    Entries (chronological):
      - Invoice  -> debit  (increases receivable)
      - GRN short/rejected -> credit (reduces receivable)
      - Payment  -> credit (reduces receivable)
    Returns ledger lines + a running balance.
    """
    await get_current_user(request)
    invs = await db.invoices.find({"client_name": client_name}, {"file_b64": 0}).to_list(2000)
    grns = await db.grns.find({"client_name": client_name}).to_list(2000)
    pays = await db.payments.find({"client_name": client_name}).to_list(2000)

    # Build price index per invoice for GRN value adjustments
    price_idx: dict[str, dict] = {}
    for inv in invs:
        iid = str(inv["_id"])
        prices = {(li.get("style_code"), li.get("color"), str(li.get("size") or "")):
                  float(li.get("unit_price") or 0) for li in (inv.get("line_items_snapshot") or [])}
        price_idx[iid] = prices

    entries = []
    for inv in invs:
        d = inv.get("invoice_iso_date") or _invoice_iso_date(inv.get("invoice_date", ""))
        entries.append({
            "date": d,
            "vch_type": "Invoice",
            "vch_no": inv.get("invoice_no"),
            "particulars": f"Inv {inv.get('invoice_no')} · {(inv.get('po_numbers') or [inv.get('po_number')])[0] or ''}",
            "debit": float(inv.get("grand_total") or 0),
            "credit": 0.0,
            "ref_id": str(inv["_id"]),
            "due_date": inv.get("due_date"),
        })
    for g in grns:
        prices = price_idx.get(g.get("invoice_id", ""), {})
        short_value = 0.0
        for ln in g.get("line_items", []):
            short = max(0, int(ln.get("dispatched_qty", 0)) - int(ln.get("accepted_qty", 0)))
            unit = prices.get((ln.get("style_code"), ln.get("color"), str(ln.get("size") or ""))) or 0
            short_value += short * unit
        if short_value > 0:
            entries.append({
                "date": g.get("grn_date") or g.get("received_date") or "",
                "vch_type": "GR Adj",
                "vch_no": g.get("grn_no"),
                "particulars": f"GRN {g.get('grn_no')} · short/rejected {g.get('total_dispatched',0) - g.get('total_accepted',0)} pcs",
                "debit": 0.0,
                "credit": round(short_value, 2),
                "ref_id": str(g["_id"]),
            })
    for p in pays:
        entries.append({
            "date": p.get("payment_date") or "",
            "vch_type": "Payment",
            "vch_no": p.get("payment_no"),
            "particulars": f"{p.get('mode')} · {p.get('reference', '')}".strip(" ·"),
            "debit": 0.0,
            "credit": float(p.get("amount") or 0),
            "ref_id": str(p["_id"]),
            "mode": p.get("mode"),
            "reference": p.get("reference"),
        })

    entries.sort(key=lambda e: (e["date"] or "", e["vch_type"]))
    bal = 0.0
    for e in entries:
        bal += float(e["debit"]) - float(e["credit"])
        e["debit"] = round(float(e["debit"]), 2)
        e["credit"] = round(float(e["credit"]), 2)
        e["balance"] = round(bal, 2)
        e["balance_type"] = "Dr" if bal >= 0 else "Cr"

    # Aging buckets — based on still-open invoices
    inv_ids = [str(d["_id"]) for d in invs]
    pay_map = await _aggregate_payments_for_invoices(inv_ids)
    grn_map = await _aggregate_grn_adjustments(inv_ids)
    decorated = [_decorate_invoice(d, pay_map, grn_map) for d in invs]
    today = datetime.now().date()
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    bucket_count = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for r in decorated:
        outstanding = float(r.get("outstanding") or 0)
        if outstanding <= 0 or not r.get("due_date"):
            continue
        try:
            due = datetime.fromisoformat(r["due_date"]).date()
        except Exception:
            continue
        days_overdue = (today - due).days
        if days_overdue <= 30:
            k = "0-30"
        elif days_overdue <= 60:
            k = "31-60"
        elif days_overdue <= 90:
            k = "61-90"
        else:
            k = "90+"
        buckets[k] += outstanding
        bucket_count[k] += 1

    total_invoiced = sum(float(r.get("net_amount") or 0) for r in decorated)
    total_received = sum(float(r.get("received_amount") or 0) for r in decorated)

    return {
        "client_name": client_name,
        "entries": entries,
        "closing_balance": round(bal, 2),
        "closing_balance_type": "Dr" if bal >= 0 else "Cr",
        "totals": {
            "invoiced": round(total_invoiced, 2),
            "received": round(total_received, 2),
            "outstanding": round(bal, 2),
        },
        "aging": [
            {"bucket": k, "amount": round(v, 2), "count": bucket_count[k]}
            for k, v in buckets.items()
        ],
        "invoices": decorated,
    }


# ---------- PACKING LIST ----------
async def _build_packing_payload(po: dict, job_ids: list[str] | None) -> dict:
    """Build a PO-like dict suitable for the packing list generator. If job_ids
    are supplied, line_items are rebuilt from those dispatched jobs (lets the
    user generate a packing list for a single colour/size group, etc.)."""
    po_aug, items = await _generate_invoice_payload(po, job_ids)
    out = dict(po_aug)
    out["line_items"] = items
    out["total_quantity"] = sum((li.get("quantity") or 0) for li in items)
    return out


def _packing_options_from_payload(p) -> dict:
    """Pull all manual / shipping fields from the request payload."""
    return {
        "carton_dim": p.carton_dim,
        "pcs_per_box": p.pcs_per_box,
        "net_wt_per_carton": p.net_wt_per_carton,
        "gross_wt_per_carton": p.gross_wt_per_carton,
        "dispatch_date": p.dispatch_date or "",
        "transporter": p.transporter or "",
        "vehicle_no": p.vehicle_no or "",
        "driver_name": p.driver_name or "",
        "driver_phone": p.driver_phone or "",
        "site_code": p.site_code or "",
        "destination": p.destination or "",
        "port": p.port or "",
        "notes": p.notes or "",
    }



async def _auto_pick_template(client_name: str) -> Optional[str]:
    """Return template_id whose alias matches client_name; case-insensitive
    substring match. Returns None if no template configured."""
    if not client_name:
        return None
    docs = await db.packing_templates.find({}).to_list(200)
    cn = client_name.upper()
    best = None
    for d in docs:
        aliases = [a.upper().strip() for a in (d.get("aliases") or []) if a and a.strip()]
        if not aliases:
            # Also try exact client_name match on stored field
            if d.get("client_name", "").strip().upper() == cn:
                return str(d["_id"])
            continue
        if any(a in cn or cn in a for a in aliases):
            best = str(d["_id"])
            break
    return best


async def _generate_packing_bytes(payload_po: dict, options: dict, template_id: Optional[str], cartons: Optional[list] = None, invoice_no: str = "") -> bytes:
    """Resolve template (explicit or auto) and produce the xlsx bytes."""
    tpl_id = template_id
    if not tpl_id:
        tpl_id = await _auto_pick_template(payload_po.get("client_name", ""))
    if tpl_id:
        tdoc = await db.packing_templates.find_one({"_id": oid(tpl_id)})
        if not tdoc:
            raise HTTPException(404, "Packing template not found")
        import base64 as b64
        tpl_bytes = b64.b64decode(tdoc["file_b64"])
        return build_from_template(tpl_bytes, payload_po, options, cartons=cartons)
    if cartons is not None:
        return build_dispatch_packing_list(cartons, payload_po, invoice_no, options)
    return build_default_packing_list(payload_po, options)


# ═══ EAN CODES & CARTON PACKING ═══

@api.get("/packing/ean-codes")
async def get_ean_codes(style_id: str, request: Request, color: str | None = None):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    q = {"style_id": style_id}
    if color:
        q["color"] = color
    codes = await db.sku_ean_codes.find(q).to_list(1000)
    print("DEBUG CODES TYPE:", type(codes), codes)
    return [stringify(c) for c in codes]

class EanCodeIn(BaseModel):
    style_id: str
    color: str
    size: str
    ean_code: str

@api.post("/packing/ean-codes")
async def create_ean_code(payload: EanCodeIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    q = {"style_id": payload.style_id, "color": payload.color, "size": payload.size}
    existing = await db.sku_ean_codes.find_one(q)
    if existing:
        await db.sku_ean_codes.update_one(q, {"$set": {"ean_code": payload.ean_code, "updated_at": now_iso()}})
        return {"ok": True, "id": str(existing["_id"])}
    else:
        doc = {**q, "ean_code": payload.ean_code, "created_at": now_iso()}
        res = await db.sku_ean_codes.insert_one(doc)
        return {"ok": True, "id": str(res.inserted_id)}

@api.get("/packing/cartons")
async def get_cartons(request: Request, job_id: Optional[str] = None, job_ids: Optional[str] = None):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    q = {}
    if job_ids:
        q["job_id"] = {"$in": job_ids.split(",")}
    elif job_id:
        q["job_id"] = job_id
    cartons = await db.packing_cartons.find(q).to_list(1000)
    return [stringify(c) for c in cartons]


@api.get("/production/jobs/carton-labels", dependencies=[Depends(pdf_rate_limiter)])
async def get_direct_carton_labels(job_ids: str, request: Request):
    """Generate carton labels directly for the given job IDs, even if no dispatch record exists."""
    await get_current_user(request)
    jids = job_ids.split(",")
    # Find packing cartons
    carton_docs = await db.packing_cartons.find({"job_id": {"$in": jids}}).sort([("size", 1), ("_id", 1)]).to_list(1000)
    if not carton_docs:
        raise HTTPException(400, "No cartons packed for these jobs")

    job_docs = await db.production_jobs.find({"_id": {"$in": [oid(jid) for jid in jids]}}).to_list(1000)
    po_numbers = {job.get("po_number") for job in job_docs if job and job.get("po_number")}
    if len(po_numbers) > 1:
        raise HTTPException(400, "Cannot merge carton labels for multiple PO numbers")

    cartons = [stringify(c) for c in carton_docs]
    total_cartons = len(cartons)
    # Assign continuous box numbers across merged cartons
    for idx, c in enumerate(cartons):
        c["box_number"] = idx + 1
        c["total_cartons"] = total_cartons

    # Load first job to find PO and invoice info
    job = await db.production_jobs.find_one({"_id": oid(jids[0])})
    po_number = job.get("po_number", "DRAFT") if job else "DRAFT"

    # Try to find invoice number from cartons
    invoice_no = "DRAFT"
    invoice_id = next((c.get("invoice_id") for c in cartons if c.get("invoice_id")), None)
    if invoice_id:
        invoice = await db.invoices.find_one({"_id": oid(invoice_id)})
        if invoice:
            invoice_no = invoice.get("invoice_no", "DRAFT")

    pdf_bytes = build_carton_labels(cartons, po_number, invoice_no)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CartonLabels-{invoice_no}.pdf"'},
    )


@api.get("/production/jobs/carton-list", dependencies=[Depends(pdf_rate_limiter)])
async def get_direct_carton_list(job_ids: str, request: Request):
    """Generate carton list directly for the given job IDs, even if no dispatch record exists."""
    await get_current_user(request)
    jids = job_ids.split(",")
    carton_docs = await db.packing_cartons.find({"job_id": {"$in": jids}}).sort([("size", 1), ("_id", 1)]).to_list(1000)
    if not carton_docs:
        raise HTTPException(400, "No cartons packed for these jobs")

    job_docs = await db.production_jobs.find({"_id": {"$in": [oid(jid) for jid in jids]}}).to_list(1000)
    po_numbers = {job.get("po_number") for job in job_docs if job and job.get("po_number")}
    if len(po_numbers) > 1:
        raise HTTPException(400, "Cannot merge carton lists for multiple PO numbers")

    cartons = [stringify(c) for c in carton_docs]
    total_cartons = len(cartons)
    for idx, c in enumerate(cartons):
        c["box_number"] = idx + 1
        c["total_cartons"] = total_cartons

    job = await db.production_jobs.find_one({"_id": oid(jids[0])})
    po_doc = await db.pos.find_one({"_id": oid(job["po_id"])}) if (job and job.get("po_id")) else None
    po = stringify(po_doc) if po_doc else {"po_number": "DRAFT"}

    invoice_no = "DRAFT"
    invoice_id = next((c.get("invoice_id") for c in cartons if c.get("invoice_id")), None)
    if invoice_id:
        invoice = await db.invoices.find_one({"_id": oid(invoice_id)})
        if invoice:
            invoice_no = invoice.get("invoice_no", "DRAFT")

    pl_options = {
        "carton_dim": "60x50x30 CMS",
        "net_wt_per_carton": "",
        "gross_wt_per_carton": "",
        "dispatch_date": "",
        "transporter": "",
        "vehicle_no": "",
        "driver_name": "",
        "driver_phone": "",
        "site_code": "",
        "destination": "",
        "port": "",
        "notes": "",
    }
    excel_bytes = build_carton_list_xlsx(cartons, po, invoice_no, pl_options)
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="CartonList-{invoice_no}.xlsx"'},
    )


class CartonIn(BaseModel):
    job_id: str
    size: str
    qty: int

@api.post("/packing/cartons")
async def pack_carton(payload: CartonIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(payload.job_id)})
    if not job:
        raise HTTPException(404, "Job not found")
    
    # Resolve EAN code if exists
    ean_doc = await db.sku_ean_codes.find_one({
        "style_id": job["style_id"],
        "color": job.get("color"),
        "size": payload.size
    })
    ean_code = ean_doc["ean_code"] if ean_doc else ""
    
    doc = {
        "job_id": payload.job_id,
        "po_id": job.get("po_id"),
        "style_id": job.get("style_id"),
        "style_code": job.get("style_code"),
        "color": job.get("color"),
        "size": payload.size,
        "ean_code": ean_code,
        "qty": payload.qty,
        "box_number": None,
        "invoice_id": None,
        "packed_at": now_iso(),
        "packed_by": u["email"],
        "status": "packed"
    }
    res = await db.packing_cartons.insert_one(doc)
    return {"ok": True, "id": str(res.inserted_id)}

@api.delete("/packing/cartons/{cid}")
async def delete_carton(cid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    await db.packing_cartons.delete_one({"_id": oid(cid)})
    return {"ok": True}


class EanCodeSimple(BaseModel):
    size: str
    ean_code: str

class CartonRowSimple(BaseModel):
    size: str
    qty: int

class QcPackConfirmIn(BaseModel):
    job_ids: list[str]
    eans: list[EanCodeSimple]
    cartons: list[CartonRowSimple]

@api.post("/packing/confirm-qc-pack")
async def confirm_qc_pack(payload: QcPackConfirmIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    if not payload.job_ids:
        raise HTTPException(400, "No job IDs provided")
        
    job_objs = []
    for jid in payload.job_ids:
        job = await db.production_jobs.find_one({"_id": oid(jid)})
        if not job:
            raise HTTPException(404, f"Job {jid} not found")
        job_objs.append(job)
        
    style_id = job_objs[0].get("style_id")
    style_code = job_objs[0].get("style_code")
    po_id = job_objs[0].get("po_id")
    color = job_objs[0].get("color")
    
    for job in job_objs:
        if job.get("style_id") != style_id or job.get("color") != color:
            raise HTTPException(400, "All jobs must share the same style and color")

    for item in payload.eans:
        if not item.ean_code.strip():
            continue
        q = {"style_id": str(style_id), "color": color, "size": item.size}
        existing = await db.sku_ean_codes.find_one(q)
        if existing:
            await db.sku_ean_codes.update_one(q, {"$set": {"ean_code": item.ean_code.strip(), "updated_at": now_iso()}})
        else:
            doc = {**q, "ean_code": item.ean_code.strip(), "created_at": now_iso()}
            await db.sku_ean_codes.insert_one(doc)

    await db.packing_cartons.delete_many({"job_id": {"$in": payload.job_ids}})

    carton_docs = []
    ean_map = {}
    async for e in db.sku_ean_codes.find({"style_id": str(style_id), "color": color}):
        ean_map[e["size"]] = e["ean_code"]

    job_by_size = {job.get("size"): str(job["_id"]) for job in job_objs}

    for c in payload.cartons:
        size = c.size
        qty = c.qty
        job_id = job_by_size.get(size)
        if not job_id:
            raise HTTPException(400, f"Size {size} not found in color group jobs")
        ean_code = ean_map.get(size, "")
        
        carton_docs.append({
            "job_id": job_id,
            "po_id": str(po_id),
            "style_id": str(style_id),
            "style_code": style_code,
            "color": color,
            "size": size,
            "ean_code": ean_code,
            "qty": qty,
            "box_number": None,
            "invoice_id": None,
            "packed_at": now_iso(),
            "packed_by": u["email"],
            "status": "packed"
        })

    if carton_docs:
        await db.packing_cartons.insert_many(carton_docs)

    durations = await _get_stage_durations()
    entered = now_iso()
    hours = float(durations.get("qc_pack", 12))
    deadline = _compute_deadline(entered, hours)
    
    for job in job_objs:
        stage_changing = job.get("stage") != "qc_pack"
        update = {
            "stage": "qc_pack",
            "stage_entered_at": entered,
            "stage_deadline": deadline,
            "updated_at": now_iso()
        }
        if stage_changing:
            history_entry = {
                "stage": "qc_pack", "at": entered, "by": u["email"],
                "notes": "QC & Pack Carton packing confirmed",
                "qc_pass": None, "rejected_qty": 0
            }
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": update, "$push": {"history": history_entry}}
            )
        else:
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": update}
            )

    return {"ok": True, "count": len(carton_docs)}


# ═══ UNIFIED DISPATCH ═══

@api.post("/dispatch", dependencies=[Depends(pdf_rate_limiter)])
async def create_dispatch(payload: DispatchCreate, request: Request):
    """
    Unified dispatch action for one or more qc_pack jobs.

    Steps:
      1. Load packed cartons for the given jobs.
      2. Assign box_number 1..N (sorted by size then _id) — reset per invoice.
      3. Build line items from actual packed quantities (not PO qty).
      4. Generate invoice PDF, packing list XLSX, and carton labels PDF.
      5. Bundle all three into a ZIP.
      6. Persist dispatch_record with full file snapshots.
      7. Update carton status → dispatched, advance job stages → dispatched.
      8. Return ZIP stream with X-Dispatch-Record-Id header.
    """
    import base64 as _b64
    import zipfile

    u = await get_current_user(request)
    require_roles("admin", "manager", "sales")(u)

    if not payload.job_ids:
        raise HTTPException(400, "job_ids required")

    # ── 1. Load PO ───────────────────────────────────────────────────────────
    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)

    # ── 2. Load packed cartons ───────────────────────────────────────────────
    carton_docs = await db.packing_cartons.find(
        {"job_id": {"$in": payload.job_ids}, "status": "packed"}
    ).sort([("size", 1), ("_id", 1)]).to_list(50000)

    if not carton_docs:
        raise HTTPException(400, "No packed cartons found for these jobs — run QC Pack first")

    cartons = [stringify(c) for c in carton_docs]

    # ── 3. Assign box_number 1..N (in-memory; persist after files generated) ─
    for idx, c in enumerate(cartons):
        c["box_number"] = idx + 1

    # ── 4. Build line items from actual packed qty (SUM per style/color/size) ─
    po_items = po.get("line_items", [])
    po_price_idx = {}
    for li in po_items:
        key = (li.get("style_code"), li.get("color"), str(li.get("size", "")))
        po_price_idx[key] = li

    qty_agg: dict = {}   # (style_code, color, size) → aggregated dict
    for c in cartons:
        key = (c.get("style_code", ""), c.get("color", ""), str(c.get("size", "")))
        if key not in qty_agg:
            li_src = po_price_idx.get(key, {})
            qty_agg[key] = {
                "style_code": c.get("style_code", ""),
                "color": c.get("color", ""),
                "size": str(c.get("size", "")),
                "ean_code": c.get("ean_code", ""),
                "qty": 0,
                "unit_price": li_src.get("unit_price", 0),
                "description": li_src.get("description", ""),
                "hsn_code": li_src.get("hsn_code", "") or "64029990",
                "mrp": li_src.get("mrp", ""),
            }
        qty_agg[key]["qty"] += (c.get("qty") or 0)

    line_items = [
        {
            "style_code": v["style_code"],
            "description": v["description"],
            "color": v["color"],
            "size": v["size"],
            "hsn_code": v["hsn_code"],
            "quantity": v["qty"],
            "unit_price": v["unit_price"],
            "amount": round(v["qty"] * v["unit_price"], 2),
            "mrp": v["mrp"],
        }
        for v in qty_agg.values()
        if v["qty"] > 0
    ]

    if not line_items:
        raise HTTPException(400, "No packed quantities found — carton rows may have 0 qty")

    # ── 5. Invoice PDF ───────────────────────────────────────────────────────
    invoice_no = await next_invoice_no()
    invoice_date = datetime.now().strftime("%d/%m/%Y")
    invoice_pdf = build_invoice(
        po, invoice_no, invoice_date,
        transport_mode=payload.transport_mode or "",
        vehicle_no=payload.vehicle_no or "",
        supply_date=payload.supply_date or "",
        line_items=line_items,
    )

    # ── 6. Packing list XLSX (fed with actual carton data) ───────────────────
    # Build a packing-list-compatible payload_po: inject real line_items + totals
    total_qty = sum(li["quantity"] for li in line_items)
    total_cartons = len(cartons)
    payload_po = dict(po)
    payload_po["line_items"] = line_items
    payload_po["total_quantity"] = total_qty
    payload_po["total_cartons"] = total_cartons
    payload_po["po_number"] = po.get("po_number", "")

    # Inject shipping metadata so the template can render it
    pl_options = {
        "carton_dim": payload.carton_dim or "60x50x30 CMS",
        "pcs_per_box": None,           # actual rows are in line_items
        "net_wt_per_carton": payload.net_wt_per_carton or "",
        "gross_wt_per_carton": payload.gross_wt_per_carton or "",
        "dispatch_date": payload.dispatch_date or "",
        "transporter": payload.transporter or "",
        "vehicle_no": payload.vehicle_no or "",
        "driver_name": payload.driver_name or "",
        "driver_phone": payload.driver_phone or "",
        "site_code": payload.site_code or "",
        "destination": payload.destination or "",
        "port": payload.port or "",
        "notes": payload.notes or "",
    }
    packing_xlsx = await _generate_packing_bytes(payload_po, pl_options, payload.template_id, cartons=cartons, invoice_no=invoice_no)

    total_cartons = len(cartons)
    for c in cartons:
        c["total_cartons"] = total_cartons

    # ── 7. Carton Labels PDF ─────────────────────────────────────────────────
    labels_pdf = build_carton_labels(cartons, po.get("po_number", ""), invoice_no)

    # ── 7a. Carton List Excel ────────────────────────────────────────────────
    carton_list_xlsx = build_carton_list_xlsx(cartons, po, invoice_no, pl_options)

    # ── 8. Store invoice record ──────────────────────────────────────────────
    totals = _compute_invoice_totals(po, line_items)
    credit_days = _extract_credit_days(po.get("payment_terms", ""))
    inv_doc = {
        "invoice_no": invoice_no,
        "invoice_date": invoice_date,
        "invoice_iso_date": _invoice_iso_date(invoice_date),
        "due_date": _due_iso(invoice_date, credit_days),
        "payment_terms_days": credit_days,
        "po_id": payload.po_id,
        "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")],
        "client_name": po.get("client_name"),
        "job_ids": payload.job_ids,
        "line_items_snapshot": line_items,
        **totals,
        "transport_mode": payload.transport_mode,
        "vehicle_no": payload.vehicle_no,
        "supply_date": payload.supply_date,
        "by": u["email"],
        "created_at": now_iso(),
        "file_b64": _b64.b64encode(invoice_pdf).decode("ascii"),
        "merged": False,
    }
    inv_res = await db.invoices.insert_one(inv_doc)
    invoice_id = str(inv_res.inserted_id)

    # ── 9. Persist carton updates ─────────────────────────────────────────────
    for c in cartons:
        await db.packing_cartons.update_one(
            {"_id": oid(c["id"])},
            {"$set": {
                "status": "dispatched",
                "invoice_id": invoice_id,
                "box_number": c["box_number"],
            }},
        )

    # ── 10. Persist dispatch_record ───────────────────────────────────────────
    snapshot = [
        {
            "box_number": c["box_number"],
            "ean_code": c.get("ean_code"),
            "qty": c.get("qty"),
            "size": c.get("size"),
            "color": c.get("color"),
            "style_code": c.get("style_code"),
            "style_id": c.get("style_id"),
            "job_id": c.get("job_id"),
        }
        for c in cartons
    ]
    dispatch_doc = {
        "invoice_id": invoice_id,
        "invoice_no": invoice_no,
        "dispatched_at": now_iso(),
        "dispatched_by": u["email"],
        "client_name": po.get("client_name"),
        "po_ids": [payload.po_id],
        "po_numbers": [po.get("po_number", "")],
        "job_ids": payload.job_ids,
        "packing_cartons_snapshot": snapshot,
        "total_cartons": total_cartons,
        "total_qty": total_qty,
        "invoice_file_b64": _b64.b64encode(invoice_pdf).decode("ascii"),
        "packing_list_file_b64": _b64.b64encode(packing_xlsx).decode("ascii"),
        "carton_labels_file_b64": _b64.b64encode(labels_pdf).decode("ascii"),
        "carton_list_file_b64": _b64.b64encode(carton_list_xlsx).decode("ascii"),
    }
    dr_res = await db.dispatch_records.insert_one(dispatch_doc)
    dispatch_record_id = str(dr_res.inserted_id)

    # ── 11. Advance job stages ────────────────────────────────────────────────
    await _flag_jobs(payload.job_ids, "invoice_generated_at")

    # ── 12. ZIP all documents ─────────────────────────────────────────────────
    date_tag = datetime.now().strftime("%Y%m%d-%H%M")
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"Invoice-{invoice_no}.pdf", invoice_pdf)
        zf.writestr(f"PackingList-{invoice_no}-{date_tag}.xlsx", packing_xlsx)
        zf.writestr(f"CartonLabels-{invoice_no}.pdf", labels_pdf)
        zf.writestr(f"CartonList-{invoice_no}-{date_tag}.xlsx", carton_list_xlsx)
    zip_buf.seek(0)

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="Dispatch-{invoice_no}-{date_tag}.zip"',
            "X-Dispatch-Record-Id": dispatch_record_id,
            "X-Invoice-No": invoice_no,
        },
    )


# ═══ DISPATCH RECORDS ═══

@api.get("/dispatch-records")
async def list_dispatch_records(
    request: Request,
    client: Optional[str] = None,
    po_number: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 200,
):
    """List all dispatch records (file bytes excluded for size)."""
    await get_current_user(request)
    q: dict = {}
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    if po_number:
        q["po_numbers"] = {"$elemMatch": {"$regex": re.escape(po_number), "$options": "i"}}
    if job_id:
        q["job_ids"] = job_id
    proj = {
        "invoice_file_b64": 0,
        "packing_list_file_b64": 0,
        "carton_labels_file_b64": 0,
        "carton_list_file_b64": 0,
    }
    docs = await db.dispatch_records.find(q, proj).sort("dispatched_at", -1).to_list(limit)
    return [stringify(d) for d in docs]


@api.get("/dispatch-records/{dr_id}")
async def get_dispatch_record(dr_id: str, request: Request):
    """Full dispatch record detail — includes snapshot but excludes file bytes (use /file routes)."""
    await get_current_user(request)
    doc = await db.dispatch_records.find_one(
        {"_id": oid(dr_id)},
        {"invoice_file_b64": 0, "packing_list_file_b64": 0, "carton_labels_file_b64": 0, "carton_list_file_b64": 0},
    )
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    return stringify(doc)


@api.get("/dispatch-records/{dr_id}/invoice", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_invoice(dr_id: str, request: Request):
    """Re-download the invoice PDF exactly as generated at dispatch time."""
    await get_current_user(request)
    import base64 as _b64
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"invoice_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = _b64.b64decode(doc.get("invoice_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Invoice file not stored for this record")
    inv_no = doc.get("invoice_no", "invoice")
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Invoice-{inv_no}.pdf"'},
    )


@api.get("/dispatch-records/{dr_id}/packing-list", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_packing_list(dr_id: str, request: Request):
    """Re-download the packing list XLSX as generated at dispatch time."""
    await get_current_user(request)
    import base64 as _b64
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"packing_list_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = _b64.b64decode(doc.get("packing_list_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Packing list file not stored for this record")
    inv_no = doc.get("invoice_no", "dispatch")
    return StreamingResponse(
        BytesIO(raw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="PackingList-{inv_no}.xlsx"'},
    )


@api.get("/dispatch-records/{dr_id}/carton-labels", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_carton_labels(dr_id: str, request: Request):
    """Re-download the carton labels PDF as generated at dispatch time."""
    await get_current_user(request)
    import base64 as _b64
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"carton_labels_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = _b64.b64decode(doc.get("carton_labels_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Carton labels file not stored for this record")
    inv_no = doc.get("invoice_no", "dispatch")
    return StreamingResponse(
        BytesIO(raw), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CartonLabels-{inv_no}.pdf"'},
    )


@api.get("/dispatch-records/{dr_id}/carton-list", dependencies=[Depends(pdf_rate_limiter)])
async def download_dispatch_carton_list(dr_id: str, request: Request):
    """Re-download the carton list XLSX as generated at dispatch time."""
    await get_current_user(request)
    import base64 as _b64
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)}, {"carton_list_file_b64": 1, "invoice_no": 1})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    raw = _b64.b64decode(doc.get("carton_list_file_b64") or "")
    if not raw:
        raise HTTPException(404, "Carton list file not stored for this record")
    inv_no = doc.get("invoice_no", "dispatch")
    return StreamingResponse(
        BytesIO(raw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="CartonList-{inv_no}.xlsx"'},
    )


@api.post("/dispatch-records/{dr_id}/reprint", dependencies=[Depends(pdf_rate_limiter)])
async def reprint_dispatch_zip(dr_id: str, request: Request):
    """Re-download all dispatch documents as a ZIP (for reprinting)."""
    await get_current_user(request)
    import base64 as _b64
    import zipfile
    doc = await db.dispatch_records.find_one({"_id": oid(dr_id)})
    if not doc:
        raise HTTPException(404, "Dispatch record not found")
    inv_no = doc.get("invoice_no", "dispatch")
    invoice_pdf = _b64.b64decode(doc.get("invoice_file_b64") or "")
    packing_xlsx = _b64.b64decode(doc.get("packing_list_file_b64") or "")
    labels_pdf = _b64.b64decode(doc.get("carton_labels_file_b64") or "")
    carton_list_xlsx = _b64.b64decode(doc.get("carton_list_file_b64") or "")
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if invoice_pdf:
            zf.writestr(f"Invoice-{inv_no}.pdf", invoice_pdf)
        if packing_xlsx:
            zf.writestr(f"PackingList-{inv_no}.xlsx", packing_xlsx)
        if labels_pdf:
            zf.writestr(f"CartonLabels-{inv_no}.pdf", labels_pdf)
        if carton_list_xlsx:
            zf.writestr(f"CartonList-{inv_no}.xlsx", carton_list_xlsx)
    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Reprint-{inv_no}.zip"'},
    )


@api.post("/packing-lists/job", dependencies=[Depends(pdf_rate_limiter)])
async def generate_packing_list(payload: PackingListGenerate, request: Request):
    """Generate a packing-list xlsx for a single PO (optionally filtered by jobs).
    Stores the bytes so the user can re-download from Archive later."""
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    po_doc = await db.pos.find_one({"_id": oid(payload.po_id)})
    if not po_doc:
        raise HTTPException(404, "PO not found")
    po = stringify(po_doc)
    payload_po = await _build_packing_payload(po, payload.job_ids)
    options = _packing_options_from_payload(payload)
    cartons = await db.packing_cartons.find({"job_id": {"$in": [oid(j) for j in payload.job_ids or []]}}).sort([("box_number", 1), ("_id", 1)]).to_list(1000)
    cartons = [stringify(c) for c in cartons] if cartons else None
    xlsx_bytes = await _generate_packing_bytes(payload_po, options, payload.template_id, cartons=cartons)

    import base64 as b64
    rec = {
        "po_id": payload.po_id, "po_number": po.get("po_number"),
        "po_numbers": [po.get("po_number")],
        "client_name": po.get("client_name"),
        "job_ids": payload.job_ids or [],
        "template_id": payload.template_id,
        "options": options, "by": u["email"], "created_at": now_iso(),
        "file_b64": b64.b64encode(xlsx_bytes).decode("ascii"),
        "merged": False,
    }
    res = await db.packing_lists.insert_one(rec)
    await _flag_jobs(payload.job_ids or [], "packing_generated_at")

    fname = f"PackingList-{po.get('po_number','po')}-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Packing-List-Id": str(res.inserted_id),
        },
    )


@api.post("/packing-lists/merged", dependencies=[Depends(pdf_rate_limiter)])
async def generate_merged_packing_list(payload: MergedPackingListGenerate, request: Request):
    """Generate ONE packing list covering jobs from multiple POs of the same
    client (mirrors merged-invoice flow)."""
    u = await get_current_user(request); require_roles("admin", "manager", "sales")(u)
    if not payload.job_ids:
        raise HTTPException(400, "Provide job_ids to merge")
    jobs = await db.production_jobs.find({"_id": {"$in": [oid(j) for j in payload.job_ids]}}).to_list(2000)
    if not jobs:
        raise HTTPException(404, "No jobs found")
    po_ids = list({j.get("po_id") for j in jobs if j.get("po_id")})
    po_docs = await db.pos.find({"_id": {"$in": [oid(p) for p in po_ids]}}).to_list(200)
    if not po_docs:
        raise HTTPException(404, "No POs found for these jobs")
    po_docs = [stringify(p) for p in po_docs]

    # All merged jobs must belong to the same PO.
    po_numbers = [p.get("po_number", "") for p in po_docs]
    if len(set([p for p in po_numbers if p])) > 1:
        raise HTTPException(400, "Cannot merge packing lists across different POs")
    parent = po_docs[0]

    # Build aggregated line items
    job_ids_str = [str(j["_id"]) for j in jobs]
    all_items: list[dict] = []
    for p in po_docs:
        _, items = await _generate_invoice_payload(p, job_ids_str)
        if payload.sectioned:
            # Annotate items so the section header can be inserted in the template
            for it in items:
                it["_po_number"] = p.get("po_number", "")
        all_items.extend(items)

    payload_po = dict(parent)
    payload_po["line_items"] = all_items
    payload_po["total_quantity"] = sum((li.get("quantity") or 0) for li in all_items)
    payload_po["po_number"] = " + ".join(po_numbers)

    options = _packing_options_from_payload(payload)
    cartons = await db.packing_cartons.find({"job_id": {"$in": [oid(j) for j in job_ids_str]}}).sort([("box_number", 1), ("_id", 1)]).to_list(1000)
    cartons = [stringify(c) for c in cartons] if cartons else None
    xlsx_bytes = await _generate_packing_bytes(payload_po, options, payload.template_id, cartons=cartons)

    import base64 as b64
    rec = {
        "merged": True, "po_numbers": po_numbers, "client_name": parent.get("client_name"),
        "job_ids": job_ids_str, "template_id": payload.template_id,
        "options": options, "by": u["email"], "created_at": now_iso(),
        "file_b64": b64.b64encode(xlsx_bytes).decode("ascii"),
    }
    res = await db.packing_lists.insert_one(rec)
    await _flag_jobs(job_ids_str, "packing_generated_at")

    fname = f"PackingList-MERGED-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Packing-List-Id": str(res.inserted_id),
        },
    )


@api.get("/packing-lists")
async def list_packing_lists(request: Request, po_id: Optional[str] = None,
                             client: Optional[str] = None, limit: int = 200):
    """List saved packing lists. Optional filters: by po_id or client_name."""
    await get_current_user(request)
    q: dict = {}
    if po_id:
        q["po_id"] = po_id
    if client:
        q["client_name"] = {"$regex": re.escape(client), "$options": "i"}
    docs = await db.packing_lists.find(q, {"file_b64": 0}).sort("created_at", -1).to_list(limit)
    return [stringify(d) for d in docs]


@api.get("/packing-lists/{plid}/file", dependencies=[Depends(pdf_rate_limiter)])
async def download_packing_list(plid: str, request: Request):
    await get_current_user(request)
    doc = await db.packing_lists.find_one({"_id": oid(plid)})
    if not doc:
        raise HTTPException(404, "Packing list not found")
    import base64 as b64
    raw = b64.b64decode(doc.get("file_b64", "") or b"")
    if not raw:
        raise HTTPException(404, "File not stored for this entry")
    label = "MERGED" if doc.get("merged") else doc.get("po_number", "po")
    fname = f"PackingList-{label}-{doc.get('created_at','')[:10]}.xlsx"
    return StreamingResponse(
        BytesIO(raw),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@api.get("/packing-templates")
async def list_packing_templates(request: Request):
    await get_current_user(request)
    docs = await db.packing_templates.find({}, {"file_b64": 0}).to_list(200)
    return [stringify(d) for d in docs]


@api.post("/packing-templates")
async def create_packing_template(payload: PackingTemplateIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # Lightweight sanity check the file is a valid xlsx
    import base64 as b64
    try:
        raw = b64.b64decode(payload.file_b64.split(",", 1)[-1] if "," in payload.file_b64 else payload.file_b64)
        # try loading
        import io as _io
        import openpyxl as _ox
        _ox.load_workbook(_io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(400, f"Invalid xlsx file: {e}")

    doc = {
        "client_name": payload.client_name.strip(),
        "name": payload.name.strip(),
        "aliases": [a.strip() for a in (payload.aliases or []) if a and a.strip()],
        "file_b64": payload.file_b64,
        "by": u["email"],
        "created_at": now_iso(),
    }
    res = await db.packing_templates.insert_one(doc)
    doc["_id"] = res.inserted_id
    safe = stringify(doc)
    safe.pop("file_b64", None)
    await log_activity("create_packing_template", "settings", f"Created packing template: {payload.name}", u["email"])
    return safe


@api.delete("/packing-templates/{tid}")
async def delete_packing_template(tid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    t = await db.packing_templates.find_one({"_id": oid(tid)})
    if not t:
        raise HTTPException(404, "Template not found")
    await db.packing_templates.delete_one({"_id": oid(tid)})
    await log_activity("delete_packing_template", "settings", f"Deleted packing template: {t.get('name')}", u["email"])
    return {"ok": True}


# ---------- REPORTS ----------
@api.get("/reports/cost-variance")
async def report_cost_variance(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    await get_current_user(request)
    styles = await db.styles.find({}).to_list(1000)
    style_costs = {}
    for s in styles:
        s_obj = stringify(s)
        c = compute_style_costing(s_obj)
        style_costs[s["code"]] = {"name": s["name"], "computed_cost": c["total_cost"], "selling_price": c["selling_price"]}
        
    po_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date
        po_query["po_date"] = date_q
        
    pos = await db.pos.find(po_query).to_list(1000)
    rows = []
    for p in pos:
        for li in p.get("line_items", []):
            code = li.get("style_code", "")
            sc = style_costs.get(code, {})
            cost = sc.get("computed_cost", 0)
            sell = li.get("unit_price", 0)
            variance = sell - cost
            margin_pct = (variance / cost * 100) if cost else 0
            rows.append({
                "po_number": p.get("po_number"), "client": p.get("client_name"),
                "style_code": code, "style_name": sc.get("name", "—"),
                "computed_cost": round(cost, 2), "po_unit_price": round(sell, 2),
                "variance": round(variance, 2), "margin_pct": round(margin_pct, 2),
                "quantity": li.get("quantity", 0),
                "total_variance": round(variance * li.get("quantity", 0), 2),
            })
    rows.sort(key=lambda r: r["margin_pct"])
    return rows


@api.get("/reports/stage-cycle-time")
async def report_stage_cycle_time(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    await get_current_user(request)
    
    job_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        job_query["created_at"] = date_q
        
    jobs = await db.production_jobs.find(job_query).to_list(5000)
    from collections import defaultdict
    durations = defaultdict(list)
    for j in jobs:
        hist = sorted(j.get("history", []), key=lambda h: h.get("at", ""))
        for i in range(1, len(hist)):
            prev, cur = hist[i - 1], hist[i]
            try:
                t_prev = datetime.fromisoformat(prev["at"])
                t_cur = datetime.fromisoformat(cur["at"])
                hours = (t_cur - t_prev).total_seconds() / 3600
                if hours >= 0:
                    durations[(prev["stage"], cur["stage"])].append(hours)
            except Exception:
                continue
    out = []
    for (frm, to), vals in durations.items():
        out.append({
            "from_stage": frm, "to_stage": to, "samples": len(vals),
            "avg_hours": round(sum(vals) / len(vals), 2),
            "min_hours": round(min(vals), 2), "max_hours": round(max(vals), 2),
        })
    out.sort(key=lambda r: r["avg_hours"], reverse=True)
    return out


@api.get("/reports/defect-rate")
async def report_defect_rate(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    await get_current_user(request)
    
    defect_query = {}
    job_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        defect_query["created_at"] = date_q
        job_query["created_at"] = date_q
        
    defects = await db.defects.find(defect_query).to_list(2000)
    jobs = await db.production_jobs.find(job_query).to_list(5000)
    from collections import defaultdict
    stage_qty = defaultdict(int)
    for j in jobs:
        for h in j.get("history", []):
            stage_qty[h.get("stage", "")] += j.get("quantity", 0)
    by_stage = defaultdict(lambda: {"defective": 0, "rework": 0, "rejected": 0, "cost": 0.0, "incidents": 0})
    by_type = defaultdict(lambda: {"defective": 0, "cost": 0.0, "incidents": 0})
    total_defective = 0
    total_cost = 0.0
    for d in defects:
        s = d.get("stage", "unknown")
        by_stage[s]["defective"] += d.get("defective_qty", 0)
        by_stage[s]["rework"] += d.get("rework_qty", 0)
        by_stage[s]["rejected"] += d.get("final_rejection_qty", 0)
        by_stage[s]["cost"] += d.get("cost", 0) or 0
        by_stage[s]["incidents"] += 1
        t = d.get("defect_type", "unknown")
        by_type[t]["defective"] += d.get("defective_qty", 0)
        by_type[t]["cost"] += d.get("cost", 0) or 0
        by_type[t]["incidents"] += 1
        total_defective += d.get("defective_qty", 0)
        total_cost += d.get("cost", 0) or 0
    stages_out = []
    for stage, v in by_stage.items():
        produced = stage_qty.get(stage, 0)
        rate = (v["defective"] / produced * 100) if produced else 0
        stages_out.append({
            "stage": stage, "produced_qty": produced,
            "defective_qty": v["defective"], "rework_qty": v["rework"],
            "rejected_qty": v["rejected"], "cost": round(v["cost"], 2),
            "incidents": v["incidents"], "defect_rate_pct": round(rate, 2),
        })
    stages_out.sort(key=lambda r: r["defect_rate_pct"], reverse=True)
    types_out = [{"type": k, **v, "cost": round(v["cost"], 2)} for k, v in by_type.items()]
    types_out.sort(key=lambda r: r["defective"], reverse=True)
    return {
        "by_stage": stages_out, "by_type": types_out,
        "totals": {"total_defective": total_defective, "total_cost": round(total_cost, 2), "total_incidents": len(defects)},
    }


# ---------- SETTINGS (stage durations / ETAs) ----------
@api.get("/settings/stage-durations")
async def get_stage_durations(request: Request):
    await get_current_user(request)
    return {"hours": await _get_stage_durations(), "defaults": DEFAULT_STAGE_HOURS}


@api.put("/settings/stage-durations")
async def put_stage_durations(payload: StageDurationsIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    cleaned = {k: float(v) for k, v in payload.hours.items() if isinstance(v, (int, float)) and float(v) >= 0}
    await db.settings.update_one(
        {"_id": "stage_durations"},
        {"$set": {"hours": cleaned, "updated_at": now_iso(), "updated_by": u["email"]}},
        upsert=True,
    )
    await log_activity("update_stage_durations", "settings", "Updated stage ETAs/deadlines", u["email"])
    return {"ok": True, "hours": await _get_stage_durations()}

@api.get("/settings/company")
async def get_company_profile(request: Request):
    await get_current_user(request)
    profile = await db.settings.find_one({"_id": "company_profile"})
    if not profile:
        from pdf_docs import COMPANY
        return COMPANY
    profile.pop("_id", None)
    return profile

@api.put("/settings/company")
async def put_company_profile(payload: dict, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.settings.update_one(
        {"_id": "company_profile"},
        {"$set": payload},
        upsert=True
    )
    from pdf_docs import update_company_profile
    update_company_profile(payload)
    await log_activity("update_company_profile", "settings", "Updated company profile details", u["email"])
    return {"ok": True}

@api.get("/settings/audit-logs")
async def get_audit_logs(request: Request):
    await get_current_user(request)
    logs = await db.audit_logs.find({}).sort("created_at", -1).to_list(100)
    return [stringify(l) for l in logs]

@api.get("/settings/export-backup")
async def get_export_backup(request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    backup_data = {}
    collections = [
        "users", "materials", "styles", "pos", "production_jobs", 
        "workers", "defects", "packing_templates", "invoices", 
        "grns", "payments", "settings", "inventory_movements", "audit_logs"
    ]
    for col_name in collections:
        docs = await db[col_name].find({}).to_list(10000)
        backup_data[col_name] = [stringify(d) for d in docs]
    await log_activity("database_backup", "settings", f"Full database backup downloaded by {u['email']}", u["email"])
    return backup_data


# ---------- OVERDUE / DEADLINE ALERTS ----------
@api.get("/dashboard/overdue")
async def overdue_jobs(request: Request):
    """Returns active jobs whose stage_deadline has passed (excluding dispatched)."""
    await get_current_user(request)
    jobs = await db.production_jobs.find({"stage": {"$ne": "dispatched"}}).to_list(5000)
    out = []
    durations = await _get_stage_durations()
    for j in jobs:
        # Backfill deadline if missing (for jobs created before this feature)
        dl = j.get("stage_deadline")
        if not dl:
            entered = j.get("stage_entered_at") or j.get("updated_at") or j.get("created_at")
            if entered:
                dl = _compute_deadline(entered, durations.get(j.get("stage", "procurement"), 24))
        hrs_over = _overdue_hours(dl)
        if hrs_over > 0:
            s = stringify(j)
            s["stage_deadline"] = dl
            s["overdue_hours"] = hrs_over
            out.append(s)
    out.sort(key=lambda r: -r["overdue_hours"])
    return out


@api.get("/production/unmatched-styles")
async def unmatched_styles(request: Request):
    """Return active (non-dispatched, non-archived) production jobs whose style
    could not be resolved at creation time (style_match_status='unmatched') OR
    whose inventory_consume_error contains a style-not-found message.
    Results are grouped by style_code so the operator sees at a glance which
    style codes need fixing in the Style Master.
    """
    await get_current_user(request)
    jobs = await db.production_jobs.find({
        "archived": {"$ne": True},
        "stage": {"$ne": "dispatched"},
        "$or": [
            {"style_match_status": "unmatched"},
            {"inventory_consume_error": {"$regex": "style", "$options": "i"}},
        ],
    }).to_list(2000)

    # Group by style_code
    groups: dict[str, dict] = {}
    for j in jobs:
        code = j.get("style_code") or "(blank)"
        if code not in groups:
            groups[code] = {"style_code": code, "job_count": 0, "jobs": []}
        groups[code]["job_count"] += 1
        groups[code]["jobs"].append({
            "id": str(j["_id"]),
            "po_number": j.get("po_number"),
            "color": j.get("color"),
            "size": j.get("size"),
            "quantity": j.get("quantity"),
            "stage": j.get("stage"),
            "style_match_status": j.get("style_match_status"),
            "inventory_consume_error": j.get("inventory_consume_error"),
            "created_at": j.get("created_at"),
        })

    result = list(groups.values())
    result.sort(key=lambda g: -g["job_count"])
    return result


# ---------- VISUAL REPORTS ----------
@api.get("/reports/monthly-production")
async def report_monthly_production(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Pairs produced (dispatched) and started (procurement created) per month for last 12 months."""
    await get_current_user(request)
    
    job_query = {}
    if from_date or to_date:
        date_q = {}
        if from_date:
            date_q["$gte"] = from_date
        if to_date:
            date_q["$lte"] = to_date + "T23:59:59.999Z"
        job_query["created_at"] = date_q
        
    jobs = await db.production_jobs.find(job_query).to_list(10000)
    from collections import defaultdict
    monthly = defaultdict(lambda: {"started": 0, "dispatched": 0})
    for j in jobs:
        created = (j.get("created_at") or "")[:7]
        if created:
            monthly[created]["started"] += j.get("quantity", 0) or 0
        if j.get("stage") == "dispatched":
            disp_at = (j.get("updated_at") or "")[:7]
            if disp_at:
                monthly[disp_at]["dispatched"] += j.get("quantity", 0) or 0
    rows = [{"month": m, **v} for m, v in sorted(monthly.items())]
    if from_date or to_date:
        return rows
    return rows[-12:]


@api.get("/reports/karigar-output")
async def report_karigar_output(request: Request,
                                from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Per-karigar pairs and earnings for the given period (defaults to current month)."""
    if not from_date:
        from_date = datetime.now(timezone.utc).strftime("%Y-%m-01")
    if not to_date:
        to_date = datetime.now(timezone.utc).date().isoformat()
    # delegate to /reports/payroll for the same computation
    payroll = await report_payroll(request, from_date=from_date, to_date=to_date)
    rows = [{
        "worker_id": r["worker_id"], "name": r["name"], "skill": r["skill"],
        "pairs": r["total_pairs"], "earnings": r["total_earning"], "bonus": r.get("total_bonus", 0),
    } for r in payroll["rows"]]
    rows.sort(key=lambda r: -r["pairs"])
    return rows


# ---------- ONLINE ORDERS ----------

class OnlineOrderImportResult(BaseModel):
    channel: str
    imported: int
    unresolved: int
    errors: List[dict]

@api.post("/online-orders/import", dependencies=[Depends(bulk_import_rate_limiter)])
async def import_online_orders(
    file: UploadFile = File(...),
    channel: str = "myntra",          # form field: myntra|flipkart|nykaa|website
    order_date: Optional[str] = None, # ISO date string, defaults to today
    request: Request = None,
):
    """Import online marketplace orders from a CSV and create production jobs.

    CSV required columns:
      order_id   — marketplace order / shipment ID     (required, used as po_number)
      style_sku  — the platform's SKU code             (required)
      quantity   — integer                             (required)

    Optional columns:
      color, size, description, unit_price, delivery_date

    Resolution uses resolve_style(source_type="online_channel", source_name=channel).
    Unresolved rows are NOT auto-created as placeholder styles — they are returned
    in the errors list for manual mapping via /sku-map.

    Returns: { channel, imported, unresolved, errors: [{row, order_id, style_sku, reason}] }
    """
    import io
    import csv as csv_mod

    u = await get_current_user(request); require_roles("admin", "manager")(u)

    channel = channel.strip().lower()
    if channel not in ["myntra", "ajio", "flipkart", "nykaa", "amazon", "website", "unicommerce"]:
        raise HTTPException(400, f"Unknown channel '{channel}'. Must be one of: myntra, ajio, flipkart, nykaa, amazon, website, unicommerce")

    today = (order_date or now_iso()[:10])

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv_mod.DictReader(io.StringIO(text))

    def norm(row: dict) -> dict:
        return {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items()}

    imported = 0
    unresolved = 0
    errors = []
    fulfilled_from_stock = 0
    picklist_lines_by_order: Dict[str, List[dict]] = {}
    # Track already-covered qty per SKU during this import batch, so order N doesn't
    # over-claim stock that order N-1 has already been assigned in the same batch.
    in_flight_covered: Dict[tuple, int] = {}

    durations = await _get_stage_durations()

    jobs_to_insert = []
    for idx, raw_row in enumerate(reader, start=2):
        row = norm(raw_row)

        order_id   = row.get("order_id",  "").strip()
        style_sku  = row.get("style_sku", "").strip()
        qty_str    = row.get("quantity",  "0").strip()

        if not order_id:
            errors.append({"row": idx, "order_id": None, "style_sku": style_sku, "reason": "order_id is empty"})
            continue
        if not style_sku:
            errors.append({"row": idx, "order_id": order_id, "style_sku": None, "reason": "style_sku is empty"})
            continue
        try:
            quantity = int(float(qty_str))
            if quantity <= 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append({"row": idx, "order_id": order_id, "style_sku": style_sku, "reason": f"Invalid quantity '{qty_str}'"})
            continue

        ext_color  = row.get("color", "")
        ext_size   = row.get("size",  "")
        unit_price = 0.0
        try:
            unit_price = float(row.get("unit_price", 0) or 0)
        except (ValueError, TypeError):
            pass
        delivery_date = row.get("delivery_date", "")
        description   = row.get("description", "")

        # ── Marketplace SKU Resolver (Phase 1) ──────────────────────────────
        # Try to parse+resolve using the marketplace resolver first. This handles the
        # case where the marketplace SKU embeds style+color+size (e.g. "CC-058-BR-38").
        # If it fails, fall back to the legacy sku_map/style_code resolver below.
        mp_result = await _resolve_marketplace_sku(channel, style_sku)
        result = None
        if mp_result.get("resolved"):
            # Marketplace resolver hit — override the ext_color/ext_size with parsed values
            result = {
                "style_id":        mp_result["erp_style_id"],
                "style_code":      mp_result["erp_style_code"],
                "color":           mp_result["erp_color_code"],
                "size":            mp_result["parsed_size"] or ext_size,
                "matched":         True,
                "match_via":       "marketplace_resolver",
                "mapping_id":      mp_result["mapping_id"],
                "mapped_from_sku": style_sku,
            }

        if result is None:
            # ── Legacy fallback: sku_map or exact styles.code match ─────────────
            legacy = await resolve_style(
                source_type="online_channel",
                source_name=channel,
                external_sku=style_sku,
                external_color=ext_color or mp_result.get("parsed_color") or None,
                external_size=ext_size  or mp_result.get("parsed_size")  or None,
            )
            if legacy["matched"]:
                result = legacy

        if not result:
            # Neither resolver nor legacy could match — log to unresolved queue
            unresolved += 1
            try:
                await _log_unresolved_sku(channel, style_sku, mp_result,
                                           source="online_orders_import", order_id=order_id)
            except Exception:
                pass
            errors.append({
                "row":       idx,
                "order_id":  order_id,
                "style_sku": style_sku,
                "reason":    f"Unresolved SKU on channel '{channel}'. "
                             + (f"Parsed as style={mp_result.get('parsed_style')}/color={mp_result.get('parsed_color')}/size={mp_result.get('parsed_size')} but no ERP mapping. " if mp_result.get('parsed_ok') else f"SKU parse failed. ")
                             + f"Map it via SKU Resolver → Unresolved Queue.",
                "parsed":    {
                    "style": mp_result.get("parsed_style"),
                    "color": mp_result.get("parsed_color"),
                    "size":  mp_result.get("parsed_size"),
                },
            })
            continue

        entered  = now_iso()
        deadline = _compute_deadline(entered, durations.get("procurement", 24))

        match_status = result["match_via"]   # "sku_map" | "style_code" | "marketplace_resolver"
        if match_status == "sku_map":
            match_status = "mapped"
        elif match_status == "marketplace_resolver":
            match_status = "resolved"
        else:
            match_status = "matched"

        # ── Check FG stock coverage from fg_location_inventory (WMS) ─────────
        try:
            style_oid = ObjectId(result["style_id"])
            color_val = (result.get("color") or "").strip()
            size_val  = (result.get("size")  or "").strip()
            covered_available = 0

            q_loc = {
                "$or": [{"style_id": style_oid}, {"style_id": str(result["style_id"])}],
                "qty": {"$gt": 0},
            }
            if color_val:
                q_loc["color"] = {"$regex": f"^{re.escape(color_val)}$", "$options": "i"}
            if size_val:
                q_loc["size"]  = {"$regex": f"^{re.escape(size_val)}$",  "$options": "i"}

            async for loc in db.fg_location_inventory.find(q_loc):
                qty_val = int(loc.get("qty", 0) or 0)
                res_val = int(loc.get("reserved_qty", 0) or 0)
                covered_available += max(0, qty_val - res_val)

            sku_key = (result["style_id"], result["color"], result["size"])
            already_in_batch = in_flight_covered.get(sku_key, 0)
            free_available = max(0, covered_available - already_in_batch)
        except Exception as _cov_err:
            log.warning(f"WMS stock coverage check failed: {_cov_err}")
            free_available = 0
            sku_key = (result["style_id"], result["color"], result["size"])

        covered_qty   = min(int(quantity), int(free_available))
        remaining_qty = int(quantity) - covered_qty
        if covered_qty > 0:
            in_flight_covered[sku_key] = in_flight_covered.get(sku_key, 0) + covered_qty

        if covered_qty > 0:
            # Buffer for picklist generation (per order_id) after loop finishes
            picklist_lines_by_order.setdefault(order_id, []).append({
                "style_id":   result["style_id"],
                "style_code": result["style_code"],
                "color":      result["color"],
                "size":       result["size"],
                "quantity":   covered_qty,
            })

        # If part or full remaining, still create production job for the remainder
        if remaining_qty <= 0:
            imported += 1
            fulfilled_from_stock += covered_qty
            continue

        job = {
            # Link to source — use order_id as po_number, channel as client_name
            "po_id":              None,          # no PO doc; this is a direct channel order
            "po_number":          order_id,
            "client_name":        channel,
            "channel":            channel,
            "source_type":        "online_channel",
            "order_date":         today,

            # Style resolution
            "style_code":         result["style_code"],
            "style_id":           result["style_id"],
            "style_match_status": match_status,
            **({"mapped_from_sku": result["mapped_from_sku"], "sku_mapping_id": result["mapping_id"]} if result["match_via"] in ("sku_map", "marketplace_resolver") else {}),

            # Line details
            "description":        description,
            "color":              result["color"],
            "size":               result["size"],
            "quantity":           remaining_qty,   # only what's NOT already covered from ready stock
            "original_order_qty": quantity,
            "fulfilled_from_stock_qty": covered_qty,
            "unit_price":         unit_price,
            "amount":             round(unit_price * remaining_qty, 2),
            "completed_qty":      0,
            "rejected_qty":       0,
            "delivery_date":      delivery_date,

            # Production pipeline
            "stage":              "procurement",
            "stage_entered_at":   entered,
            "stage_deadline":     deadline,
            "created_at":         now_iso(),
            "updated_at":         now_iso(),
            "history": [{"stage": "procurement", "at": now_iso(), "by": u["email"],
                         "notes": f"Auto-created from {channel} CSV import"
                                  + (f" (partial: {covered_qty} pairs shipped from ready stock)" if covered_qty else "")}],
        }
        jobs_to_insert.append(job)
        imported += 1
        fulfilled_from_stock += covered_qty

    if jobs_to_insert:
        await db.production_jobs.insert_many(jobs_to_insert)

    # ── Auto-generate picklists per order_id (WMS integration) ───────────────
    picklists_created = []
    for oid_key, lines in picklist_lines_by_order.items():
        try:
            pl_doc, covered_map, uncovered_map = await _generate_picklist_for_order(
                oid_key, channel, lines, u["email"])
            if pl_doc.get("_id"):
                picklists_created.append({
                    "picklist_no": pl_doc.get("picklist_no"),
                    "order_id":    oid_key,
                    "items":       pl_doc.get("total_items", 0),
                    "qty":         pl_doc.get("total_qty", 0),
                })
        except Exception as pe:
            log.warning(f"Picklist generation failed for order {oid_key}: {pe}")

    await log_activity(
        "IMPORT", "online_orders",
        f"{channel.capitalize()} CSV import: {imported} orders, {fulfilled_from_stock} pairs from stock, "
        f"{len(picklists_created)} picklists, {unresolved} unresolved, {len(errors)-unresolved} errors",
        u["email"],
    )
    return {
        "channel":               channel,
        "imported":              imported,
        "unresolved":            unresolved,
        "fulfilled_from_stock":  fulfilled_from_stock,
        "picklists_created":     picklists_created,
        "errors":                errors,
    }


@api.get("/online-orders")
async def list_online_orders(
    request: Request,
    channel: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    style_match_status: Optional[str] = None,
):
    """List production jobs that originated from online channel CSV imports.
    Filterable by channel, date range, and style_match_status.
    """
    await get_current_user(request)
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


# ---------- PRODUCTION ----------
@api.get("/production/jobs")
async def list_jobs(request: Request, include_archived: bool = False, source_type: Optional[str] = "b2b_client"):
    """List production jobs. Default `source_type=b2b_client` — Online orders
    are handled entirely inside Online Commerce (Ready Stock + Pending List)
    and shouldn't appear on the B2B Kanban since they never produce an invoice.
    Pass `source_type=all` to see everything, or `source_type=online_channel`
    for online-only.
    """
    await get_current_user(request)
    q: dict = {}
    if not include_archived:
        q = {"archived": {"$ne": True}}
    if source_type and source_type != "all":
        if source_type == "b2b_client":
            q["source_type"] = {"$in": ["b2b_client", None]}
        else:
            q["source_type"] = source_type
    docs = await db.production_jobs.find(q).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


@api.get("/production/archive")
async def list_archive(request: Request):
    """Return groups (po, style, color) that have been invoiced AND packed and are archived."""
    await get_current_user(request)
    docs = await db.production_jobs.find({"archived": True}).sort("archived_at", -1).to_list(2000)
    return [stringify(d) for d in docs]


def _archive_if_complete(job_update: dict) -> None:
    """Mutate `job_update` in-place: if it now has both invoice_generated_at and
    packing_generated_at, mark archived=True."""
    if job_update.get("invoice_generated_at") and job_update.get("packing_generated_at"):
        job_update["archived"] = True
        job_update["archived_at"] = now_iso()


async def _flag_jobs(job_ids: list, field: str) -> None:
    """Mark a batch of jobs with a timestamped field. If the other flag is also
    present, additionally mark archived=True/archived_at."""
    if not job_ids:
        return
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    now = now_iso()
    # Bulk update – set the timestamp
    update_fields = {field: now}
    if field == "invoice_generated_at":
        update_fields["stage"] = "dispatched"
        update_fields["stage_entered_at"] = now
        update_fields["stage_deadline"] = None

    await db.production_jobs.update_many(
        {"_id": {"$in": obj_ids}},
        {"$set": update_fields},
    )
    
    if field == "invoice_generated_at":
        for o_id in obj_ids:
            await db.production_jobs.update_one(
                {"_id": o_id},
                {"$push": {"history": {
                    "stage": "dispatched", "at": now, "by": "system",
                    "notes": "Invoice generated and job dispatched",
                    "qc_pass": None, "rejected_qty": 0
                }}}
            )

    # Then for each job, check if both flags are now set → archive
    docs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    archive_ids = [d["_id"] for d in docs if d.get("invoice_generated_at") and d.get("packing_generated_at")]
    if archive_ids:
        await db.production_jobs.update_many(
            {"_id": {"$in": archive_ids}},
            {"$set": {"archived": True, "archived_at": now}},
        )


@api.patch("/production/jobs/{jid}")
async def update_job(jid: str, payload: ProductionStageUpdate, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    
    update = {"updated_at": now_iso()}
    # If stage actually changed, reset the per-stage clock and deadline
    if job.get("stage") != payload.stage:
        try:
            curr_idx = PRODUCTION_STAGES.index(job.get("stage", "procurement"))
            target_idx = PRODUCTION_STAGES.index(payload.stage)
        except ValueError:
            curr_idx = 0
            target_idx = 0
            
        # Check if they are skipping stages or moving backward by more than 1 stage
        is_production_only = "production" in u.get("roles", []) and not any(r in u.get("roles", []) for r in ["admin", "manager"])
        if is_production_only and abs(target_idx - curr_idx) > 1 and not getattr(payload, "confirm_skip", False):
            raise HTTPException(
                status_code=400,
                detail="Skipping stages requires explicit confirmation. Please confirm stage skip."
            )
            
        durations = await _get_stage_durations()
        entered = now_iso()
        hours = float(durations.get(payload.stage, 24))
        update["stage"] = payload.stage
        update["stage_entered_at"] = entered
        update["stage_deadline"] = _compute_deadline(entered, hours) if payload.stage != "dispatched" else None
        
    if payload.completed_qty is not None:
        update["completed_qty"] = payload.completed_qty
    if payload.rejected_qty is not None:
        update["rejected_qty"] = payload.rejected_qty
    if payload.qc_pass is not None:
        update["qc_pass"] = payload.qc_pass
    history_entry = {
        "stage": payload.stage, "at": now_iso(), "by": u["email"],
        "notes": payload.notes or "",
        "qc_pass": payload.qc_pass, "rejected_qty": payload.rejected_qty,
    }
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": update, "$push": {"history": history_entry}},
    )
    # auto-consume inventory when moving OUT of procurement (first time only)
    if job.get("stage") == "procurement" and payload.stage != "procurement":
        try:
            await _auto_consume_inventory(await db.production_jobs.find_one({"_id": oid(jid)}), u["email"])
        except Exception as e:
            err_msg = str(e)
            await db.production_jobs.update_one(
                {"_id": oid(jid)},
                {"$set": {"inventory_consume_error": err_msg}}
            )
            log.warning(f"Auto-consume inventory failed for job {jid}: {e}")
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@api.patch("/production/jobs/{jid}/components")
async def update_job_components(jid: str, payload: ComponentUpdate, request: Request):
    """Toggle Upper / Bottom / Sole completion per production job."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    comps = job.get("components") or {"upper_done": False, "bottom_done": False, "sole_done": False}
    for k in ("upper_done", "bottom_done", "sole_done"):
        v = getattr(payload, k)
        if v is not None:
            comps[k] = bool(v)
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": {"components": comps, "updated_at": now_iso()},
         "$push": {"history": {"event": "component_update", "components": comps,
                               "at": now_iso(), "by": u["email"], "notes": payload.notes or ""}}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@api.patch("/production/jobs/{jid}/assignment")
async def update_job_assignment(jid: str, payload: AssignmentUpdate, request: Request):
    """Assign / reassign a karigar to a particular role on a job with a job-specific rate."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    assignments = job.get("assignments") or {}
    if payload.worker_id:
        worker = await db.workers.find_one({"_id": oid(payload.worker_id)})
        if not worker:
            raise HTTPException(404, "Worker not found")
        rate = payload.rate_per_pair if payload.rate_per_pair is not None else worker.get("rate_per_pair", 0)
        assignments[payload.role] = {
            "worker_id": payload.worker_id,
            "worker_name": worker.get("name", ""),
            "rate_per_pair": float(rate or 0),
        }
    else:
        assignments.pop(payload.role, None)
    await db.production_jobs.update_one(
        {"_id": oid(jid)},
        {"$set": {"assignments": assignments, "updated_at": now_iso()},
         "$push": {"history": {"event": "assignment_update", "role": payload.role,
                               "worker_id": payload.worker_id,
                               "worker_name": assignments.get(payload.role, {}).get("worker_name", ""),
                               "rate_per_pair": assignments.get(payload.role, {}).get("rate_per_pair"),
                               "at": now_iso(), "by": u["email"]}}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


@api.patch("/production/jobs/{jid}/quantity")
async def update_job_quantity(jid: str, payload: QuantityUpdate, request: Request):
    """Increase, reduce or correct the quantity on a job at any stage."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    job = await db.production_jobs.find_one({"_id": oid(jid)})
    if not job:
        raise HTTPException(404, "Not found")
    update = {"updated_at": now_iso()}
    old_qty = job.get("quantity", 0)
    if payload.quantity is not None:
        update["quantity"] = int(payload.quantity)
    if payload.completed_qty is not None:
        update["completed_qty"] = int(payload.completed_qty)
    if payload.rejected_qty is not None:
        update["rejected_qty"] = int(payload.rejected_qty)
    history_entry = {
        "event": "quantity_update", "old_quantity": old_qty,
        "new_quantity": update.get("quantity", old_qty),
        "completed_qty": update.get("completed_qty"),
        "rejected_qty": update.get("rejected_qty"),
        "reason": payload.reason or "",
        "at": now_iso(), "by": u["email"],
    }
    await db.production_jobs.update_one(
        {"_id": oid(jid)}, {"$set": update, "$push": {"history": history_entry}}
    )
    return stringify(await db.production_jobs.find_one({"_id": oid(jid)}))


# ---------- WORKERS / KARIGARS ----------
@api.get("/workers")
async def list_workers(request: Request):
    await get_current_user(request)
    docs = await db.workers.find({}).sort("name", 1).to_list(500)
    return [stringify(d) for d in docs]

@api.post("/workers")
async def create_worker(payload: WorkerIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.workers.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/workers/{wid}")
async def update_worker(wid: str, payload: WorkerIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    await db.workers.update_one({"_id": oid(wid)}, {"$set": update})
    return stringify(await db.workers.find_one({"_id": oid(wid)}))

@api.delete("/workers/{wid}")
async def delete_worker(wid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.workers.update_one({"_id": oid(wid)}, {"$set": {"active": False, "updated_at": now_iso()}})
    return {"ok": True}


# ---------- PROCUREMENT MATERIAL REQUIREMENT ----------
async def _compute_material_requirement(job_ids: list[str]) -> dict:
    """Aggregate material requirements across jobs based on their style BOM and yield."""
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    # Pre-load styles for these jobs (by style_code)
    style_codes = list({j.get("style_code") for j in jobs})
    styles = await db.styles.find({"code": {"$in": style_codes}}).to_list(500)
    style_map = {s["code"]: stringify(s) for s in styles}

    # Pre-load all materials (for fresh rate + category info)
    materials = await db.materials.find({}).to_list(2000)
    mat_map = {str(m["_id"]): stringify(m) for m in materials}

    # Aggregate
    requirements = {}  # key = material_id or material_code; value = {code,name,category,unit,rate,total_qty}
    jobs_summary = []
    for j in jobs:
        st = style_map.get(j.get("style_code"))
        pairs = j.get("quantity", 0)
        jobs_summary.append({
            "po_number": j.get("po_number"),
            "style_code": j.get("style_code"),
            "color": j.get("color"),
            "total_pairs": pairs,
            "sizes_text": f"Size {j.get('size','')}",
        })
        if not st or not pairs:
            continue
        for b in st.get("bom", []):
            mid = b.get("material_id") or b.get("material_code")
            code = b.get("material_code") or ""
            name = b.get("material_name") or ""
            unit = b.get("unit") or ""
            rate = float(b.get("rate", 0))
            yld = float(b.get("yield_per_unit", 1) or 1)
            qty = float(b.get("quantity", 0))
            waste = float(b.get("waste_pct", 0) or 0)
            # per pair material in unit terms = qty / yield * (1 + waste%)
            per_pair = (qty / yld) * (1 + waste / 100)
            total_qty = per_pair * pairs
            key = code or mid
            if key not in requirements:
                cat = mat_map.get(str(mid), {}).get("category", b.get("section", "other"))
                requirements[key] = {
                    "code": code, "name": name, "category": cat, "unit": unit,
                    "rate": rate, "total_qty_required": 0.0, "total_cost": 0.0,
                }
            requirements[key]["total_qty_required"] += total_qty
            requirements[key]["total_cost"] += total_qty * rate

    # Round
    material_lines = []
    for v in requirements.values():
        v["total_qty_required"] = round(v["total_qty_required"], 2)
        v["total_cost"] = round(v["total_cost"], 2)
        material_lines.append(v)
    material_lines.sort(key=lambda m: (m["category"], m["code"]))

    # Merge jobs_summary for same (style+color) so summary is one row per card
    merged = {}
    for js in jobs_summary:
        key = (js["po_number"], js["style_code"], js["color"])
        if key not in merged:
            merged[key] = {**js, "sizes_text": "", "_sizes": set()}
        merged[key]["total_pairs"] += 0 if merged[key] is js else js["total_pairs"]
        # nb already counted? Let's just keep simple and aggregate
    # Simpler: aggregate inline
    summary_agg = {}
    for js in jobs_summary:
        key = (js["po_number"], js["style_code"], js["color"])
        if key not in summary_agg:
            summary_agg[key] = {"po_number": js["po_number"], "style_code": js["style_code"],
                                "color": js["color"], "total_pairs": 0, "_sizes": []}
        summary_agg[key]["total_pairs"] += js["total_pairs"]
        sz = js["sizes_text"].replace("Size ", "")
        if sz and sz not in summary_agg[key]["_sizes"]:
            summary_agg[key]["_sizes"].append(sz)
    summary_out = []
    for v in summary_agg.values():
        summary_out.append({
            "po_number": v["po_number"], "style_code": v["style_code"], "color": v["color"],
            "total_pairs": v["total_pairs"],
            "sizes_text": ", ".join(sorted(v["_sizes"], key=lambda x: (float(x) if x.replace('.', '', 1).isdigit() else 999))),
        })
    return {"jobs": summary_out, "materials": material_lines}


@api.post("/procurement/requirement")
async def procurement_requirement(payload: dict, request: Request):
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    return await _compute_material_requirement(job_ids)


@api.post("/procurement/requirement.pdf")
async def procurement_requirement_pdf(payload: dict, request: Request):
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    scope_label = payload.get("scope_label") or f"{len(job_ids)} production card(s)"
    notes = payload.get("notes", "")
    data = await _compute_material_requirement(job_ids)
    pdf_bytes = build_material_requirement(scope_label, data["jobs"], data["materials"], notes)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="material-requirement-{datetime.now().strftime("%Y%m%d-%H%M")}.pdf"'},
    )


# ---------- BULK ASSIGN ----------
@api.post("/production/bulk-assign")
async def bulk_assign(payload: BulkAssign, request: Request):
    """Assign one karigar to multiple jobs at once for a specific role."""
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    if not payload.job_ids:
        raise HTTPException(400, "job_ids required")
    worker_name = ""
    rate = float(payload.rate_per_pair or 0)
    if payload.worker_id:
        w = await db.workers.find_one({"_id": oid(payload.worker_id)})
        if not w:
            raise HTTPException(404, "Worker not found")
        worker_name = w.get("name", "")
        if payload.rate_per_pair is None:
            rate = float(w.get("rate_per_pair", 0) or 0)

    obj_ids = []
    for jid in payload.job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(2000)
    affected = 0
    for j in jobs:
        assignments = j.get("assignments") or {}
        if payload.worker_id:
            assignments[payload.role] = {
                "worker_id": payload.worker_id, "worker_name": worker_name,
                "rate_per_pair": rate,
            }
        else:
            assignments.pop(payload.role, None)
        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {"$set": {"assignments": assignments, "updated_at": now_iso()},
             "$push": {"history": {"event": "bulk_assignment", "role": payload.role,
                                   "worker_id": payload.worker_id, "worker_name": worker_name,
                                   "rate_per_pair": rate,
                                   "at": now_iso(), "by": u["email"]}}}
        )
        affected += 1
    return {"affected": affected, "role": payload.role, "worker_id": payload.worker_id, "worker_name": worker_name, "rate_per_pair": rate}


# ---------- INVENTORY ----------
@api.get("/inventory")
async def list_inventory(request: Request):
    """List all materials with computed stock balance."""
    await get_current_user(request)
    materials = await db.materials.find({}).to_list(2000)
    movements = await db.inventory_movements.find({}).to_list(20000)

    # aggregate per material
    bal = {}
    last_in = {}
    for m in movements:
        mid = m.get("material_id")
        if mid not in bal:
            bal[mid] = {"in": 0, "out": 0, "adj": 0, "last_rate": 0, "last_date": ""}
        if m["type"] == "in":
            bal[mid]["in"] += m.get("quantity", 0)
            bal[mid]["last_rate"] = m.get("rate") or bal[mid]["last_rate"]
            bal[mid]["last_date"] = m.get("date") or m.get("created_at", "")
            last_in[mid] = m
        elif m["type"] == "out":
            bal[mid]["out"] += m.get("quantity", 0)
        else:
            bal[mid]["adj"] += m.get("quantity", 0)

    out = []
    for mat in materials:
        mat_id = str(mat["_id"])
        b = bal.get(mat_id, {"in": 0, "out": 0, "adj": 0, "last_rate": 0, "last_date": ""})
        stock = b["in"] - b["out"] + b["adj"]
        out.append({
            "material_id": mat_id,
            "code": mat.get("code"),
            "name": mat.get("name"),
            "category": mat.get("category"),
            "unit": mat.get("unit"),
            "current_rate": mat.get("rate"),
            "last_purchase_rate": b["last_rate"],
            "last_purchase_date": b["last_date"],
            "stock_in": round(b["in"], 2),
            "stock_out": round(b["out"], 2),
            "adjustments": round(b["adj"], 2),
            "balance": round(stock, 2),
            "value": round(stock * (b["last_rate"] or mat.get("rate", 0)), 2),
        })
    out.sort(key=lambda r: (r["category"] or "", r["name"] or ""))
    return out


@api.get("/inventory/movements")
async def list_movements(request: Request, material_id: Optional[str] = None, limit: int = 200):
    await get_current_user(request)
    q = {}
    if material_id:
        q["material_id"] = material_id
    docs = await db.inventory_movements.find(q).sort("created_at", -1).to_list(limit)
    return [stringify(d) for d in docs]


@api.post("/inventory/movements")
async def create_movement(payload: InventoryMovement, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    # validate material exists
    try:
        mat = await db.materials.find_one({"_id": oid(payload.material_id)})
    except HTTPException:
        mat = None
    if not mat:
        raise HTTPException(404, "Material not found")
        
    # Block deductions that exceed current stock balance
    deduction_qty = 0.0
    if payload.type == "out":
        deduction_qty = payload.quantity
    elif payload.type == "adjustment" and payload.quantity < 0:
        deduction_qty = -payload.quantity
        
    if deduction_qty > 0:
        current_bal = await _get_material_balance(payload.material_id)
        if current_bal - deduction_qty < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Deduction of {deduction_qty} {mat.get('unit', '')} exceeds current stock balance ({current_bal} {mat.get('unit', '')})."
            )
            
    doc = payload.model_dump()
    doc["material_code"] = mat.get("code")
    doc["material_name"] = mat.get("name")
    doc["unit"] = mat.get("unit")
    doc["created_at"] = now_iso()
    doc["by"] = u["email"]
    if not doc.get("date"):
        doc["date"] = datetime.now(timezone.utc).date().isoformat()
    res = await db.inventory_movements.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc


@api.delete("/inventory/movements/{mid}")
async def delete_movement(mid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.inventory_movements.delete_one({"_id": oid(mid)})
    return {"ok": True}


@api.post("/inventory/shortage")
async def inventory_shortage(payload: dict, request: Request):
    """Given job_ids, compute material requirement and compare with current stock to expose shortage."""
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    req = await _compute_material_requirement(job_ids)
    # current stock map
    bal_list = await list_inventory(request)
    bal_map = {(b["code"], b["name"]): b for b in bal_list}
    
    materials = await db.materials.find({}).to_list(2000)
    mat_details = {(m.get("code"), m.get("name")): m for m in materials}
    
    vendors = await db.vendors.find({}).to_list(2000)
    vendor_map = {str(v["_id"]): v for v in vendors}

    rows = []
    for m in req["materials"]:
        key = (m["code"], m["name"])
        b = bal_map.get(key, {"balance": 0, "unit": m["unit"]})
        shortage = max(0, m["total_qty_required"] - b.get("balance", 0))
        
        # Get material metadata
        mat_doc = mat_details.get(key) or {}
        pref_v_id = mat_doc.get("preferred_vendor_id") or ""
        pref_v_name = ""
        if pref_v_id:
            try:
                v_doc = vendor_map.get(pref_v_id)
                if v_doc:
                    pref_v_name = v_doc.get("name")
            except Exception:
                pass

        rows.append({
            "code": m["code"], "name": m["name"], "unit": m["unit"],
            "required": m["total_qty_required"],
            "in_stock": b.get("balance", 0),
            "shortage": round(shortage, 2),
            "purchase_cost_estimated": round(shortage * m["rate"], 2),
            "material_id": str(mat_doc.get("_id")) if mat_doc else "",
            "reorder_level": mat_doc.get("reorder_level", 0),
            "preferred_vendor_id": pref_v_id,
            "preferred_vendor_name": pref_v_name,
            "rate": m["rate"],
        })
    return {"jobs": req["jobs"], "shortage": rows}


# ---------- ADVANCES (worker money taken in advance, deducted from earnings) ----------
@api.get("/advances")
async def list_advances(request: Request, worker_id: Optional[str] = None):
    await get_current_user(request)
    q = {}
    if worker_id:
        q["worker_id"] = worker_id
    docs = await db.advances.find(q).sort("date", -1).to_list(2000)
    return [stringify(d) for d in docs]

@api.post("/advances")
async def create_advance(payload: AdvanceIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    worker = await db.workers.find_one({"_id": oid(payload.worker_id)})
    if not worker:
        raise HTTPException(404, "Worker not found")
    doc = payload.model_dump()
    doc["worker_name"] = worker.get("name", "")
    doc["date"] = doc.get("date") or datetime.now(timezone.utc).date().isoformat()
    doc["settled"] = False
    doc["by"] = u["email"]
    doc["created_at"] = now_iso()
    res = await db.advances.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc


@api.get("/workers/{wid}/ledger")
async def worker_ledger(wid: str, request: Request,
                        from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Per-worker chronological ledger of earnings (credit) and payments/advances (debit)
    with running balance. Earnings are computed live from completed jobs.
    Bonuses are computed if worker.target_cycle_days > 0 and worker.bonus_pct > 0.
    """
    await get_current_user(request)
    w = await db.workers.find_one({"_id": oid(wid)})
    if not w:
        raise HTTPException(404, "Worker not found")
    worker = stringify(w)

    bonus_pct = float(worker.get("bonus_pct", 0) or 0)
    target_cycle_days = float(worker.get("target_cycle_days", 0) or 0)

    # Earnings from completed jobs (and bonuses where eligible)
    job_q = {}
    if from_date:
        job_q["updated_at"] = {"$gte": from_date}
    if to_date:
        job_q.setdefault("updated_at", {})
        job_q["updated_at"]["$lte"] = to_date + "T23:59:59Z"
    jobs = await db.production_jobs.find(job_q).to_list(5000)

    entries = []
    for j in jobs:
        assigns = j.get("assignments") or {}
        comp = j.get("completed_qty", 0)
        if not comp and j.get("stage") == "dispatched":
            comp = j.get("quantity", 0)
        if not comp:
            continue
        for role, a in assigns.items():
            if a.get("worker_id") != wid:
                continue
            rate = float(a.get("rate_per_pair") if a.get("rate_per_pair") is not None
                         else worker.get("rate_per_pair", 0) or 0)
            earning = round(rate * comp, 2)
            # Date: use job.updated_at or last history entry
            entry_date = (j.get("updated_at") or j.get("created_at") or "")[:10]
            entries.append({
                "date": entry_date,
                "txn_type": "earning",
                "amount": earning,  # positive = credit
                "description": f"{j.get('po_number','')} · {j.get('style_code','')} · {j.get('color','')} · Sz {j.get('size','')} · {role.upper()} ({comp} prs × ₹{rate}/pr)",
                "ref": j.get("po_number"),
            })

            # Bonus: if target_cycle_days set, compare assignment->dispatched duration
            if bonus_pct > 0 and target_cycle_days > 0:
                hist = j.get("history") or []
                assign_at = None
                done_at = None
                for h in hist:
                    if h.get("event") in ("assignment_update", "bulk_assignment") and h.get("role") == role and h.get("worker_id") == wid:
                        assign_at = h.get("at")
                    if h.get("stage") == "dispatched":
                        done_at = h.get("at")
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

    # Advances / payments
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
        # advance + payment are DEBITS (reduce worker balance), bonus is CREDIT, adjustment can be either (use sign)
        if ttype in ("advance", "payment"):
            signed = -amt
        elif ttype == "bonus":
            signed = amt
        else:  # adjustment - use sign as-is
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

    # Sort by date, then earnings before payments on same date
    entries.sort(key=lambda e: (e["date"] or "", 0 if e["txn_type"] in ("earning", "bonus") else 1))

    # Running balance
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

@api.patch("/advances/{aid}")
async def update_advance(aid: str, payload: dict, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
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

@api.delete("/advances/{aid}")
async def delete_advance(aid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.advances.delete_one({"_id": oid(aid)})
    return {"ok": True}


# ---------- REPORTS – PAYROLL ----------
@api.get("/reports/payroll")
async def report_payroll(request: Request, from_date: Optional[str] = None, to_date: Optional[str] = None):
    """Per-karigar earnings using JOB-SPECIFIC rate (set during assignment).
    Falls back to worker.rate_per_pair if no job-specific rate captured.
    Subtracts unsettled advances within the period from total earnings → net payable.
    """
    await get_current_user(request)
    workers = await db.workers.find({}).to_list(500)
    worker_map = {str(w["_id"]): w for w in workers}

    q = {}
    if from_date:
        q["updated_at"] = {"$gte": from_date}
    if to_date:
        q.setdefault("updated_at", {})
        q["updated_at"]["$lte"] = to_date + "T23:59:59Z"
    jobs = await db.production_jobs.find(q).to_list(5000)

    earnings = {}
    for j in jobs:
        comp = j.get("completed_qty", 0)
        if not comp and j.get("stage") == "dispatched":
            comp = j.get("quantity", 0)
        if not comp:
            continue
        assigns = j.get("assignments") or {}
        for role, a in assigns.items():
            wid = a.get("worker_id")
            if not wid:
                continue
            w = worker_map.get(wid)
            if not w:
                continue
            rate = float(a.get("rate_per_pair") if a.get("rate_per_pair") is not None
                         else w.get("rate_per_pair", 0) or 0)
            earn = rate * comp
            if wid not in earnings:
                earnings[wid] = {
                    "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
                    "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
                    "bonus_pct": float(w.get("bonus_pct", 0) or 0),
                    "target_cycle_days": float(w.get("target_cycle_days", 0) or 0),
                    "total_pairs": 0, "total_earning": 0.0,
                    "total_bonus": 0.0,
                    "advances_taken": 0.0, "advances_open": 0.0,
                    "payments_paid": 0.0,
                    "net_payable": 0.0,
                    "by_role": {}, "jobs": [],
                }
            earnings[wid]["total_pairs"] += comp
            earnings[wid]["total_earning"] += earn
            earnings[wid]["by_role"][role] = earnings[wid]["by_role"].get(role, 0) + comp

            # Productivity bonus
            bonus_amt = 0
            bp = float(w.get("bonus_pct", 0) or 0)
            td = float(w.get("target_cycle_days", 0) or 0)
            if bp > 0 and td > 0:
                hist = j.get("history") or []
                assign_at = None
                done_at = None
                for h in hist:
                    if h.get("event") in ("assignment_update", "bulk_assignment") and h.get("role") == role and h.get("worker_id") == wid:
                        assign_at = h.get("at")
                    if h.get("stage") == "dispatched":
                        done_at = h.get("at")
                if assign_at and done_at:
                    try:
                        delta_days = (datetime.fromisoformat(done_at) - datetime.fromisoformat(assign_at)).total_seconds() / 86400
                        if 0 <= delta_days <= td:
                            bonus_amt = round(earn * bp / 100, 2)
                            earnings[wid]["total_bonus"] += bonus_amt
                    except Exception:
                        pass

            earnings[wid]["jobs"].append({
                "po_number": j.get("po_number"), "style_code": j.get("style_code"),
                "color": j.get("color"), "size": j.get("size"),
                "role": role, "pairs": comp, "rate": rate,
                "earning": round(earn, 2), "bonus": bonus_amt,
            })

    # Aggregate advances per worker (filter by period if dates given)
    adv_q = {}
    if from_date:
        adv_q["date"] = {"$gte": from_date}
    if to_date:
        adv_q.setdefault("date", {})
        adv_q["date"]["$lte"] = to_date
    advances = await db.advances.find(adv_q).to_list(5000)
    adv_by_worker = {}
    for a in advances:
        wid = a.get("worker_id")
        if not wid:
            continue
        adv_by_worker.setdefault(wid, []).append(a)

    for wid, e in earnings.items():
        for a in adv_by_worker.get(wid, []):
            amt = float(a.get("amount", 0) or 0)
            ttype = a.get("txn_type") or "advance"
            if ttype == "advance":
                e["advances_taken"] += amt
                if not a.get("settled"):
                    e["advances_open"] += amt
            elif ttype == "payment":
                e["payments_paid"] += amt
            elif ttype == "bonus":
                e["total_bonus"] += amt
            # adjustment is ignored in summary (use ledger to view)
        gross = e["total_earning"] + e["total_bonus"]
        e["net_payable"] = round(gross - e["advances_open"] - e["payments_paid"], 2)
        e["total_earning"] = round(e["total_earning"], 2)
        e["total_bonus"] = round(e["total_bonus"], 2)
        e["advances_taken"] = round(e["advances_taken"], 2)
        e["advances_open"] = round(e["advances_open"], 2)
        e["payments_paid"] = round(e["payments_paid"], 2)

    # Also include workers with no earnings but with advances in period
    for wid, advs in adv_by_worker.items():
        if wid in earnings:
            continue
        w = worker_map.get(wid)
        if not w:
            continue
        taken = sum(float(a.get("amount", 0) or 0) for a in advs if (a.get("txn_type") or "advance") == "advance")
        open_amt = sum(float(a.get("amount", 0) or 0) for a in advs if (a.get("txn_type") or "advance") == "advance" and not a.get("settled"))
        paid = sum(float(a.get("amount", 0) or 0) for a in advs if a.get("txn_type") == "payment")
        bon = sum(float(a.get("amount", 0) or 0) for a in advs if a.get("txn_type") == "bonus")
        earnings[wid] = {
            "worker_id": wid, "name": w.get("name", ""), "skill": w.get("skill", ""),
            "phone": w.get("phone", ""), "default_rate": float(w.get("rate_per_pair", 0) or 0),
            "bonus_pct": float(w.get("bonus_pct", 0) or 0),
            "target_cycle_days": float(w.get("target_cycle_days", 0) or 0),
            "total_pairs": 0, "total_earning": 0.0, "total_bonus": round(bon, 2),
            "advances_taken": round(taken, 2), "advances_open": round(open_amt, 2),
            "payments_paid": round(paid, 2),
            "net_payable": round(bon - open_amt - paid, 2),
            "by_role": {}, "jobs": [],
        }

    rows = list(earnings.values())
    rows.sort(key=lambda r: r["net_payable"], reverse=True)
    grand = round(sum(r["total_earning"] for r in rows), 2)
    grand_bonus = round(sum(r["total_bonus"] for r in rows), 2)
    grand_advances = round(sum(r["advances_open"] for r in rows), 2)
    grand_payments = round(sum(r["payments_paid"] for r in rows), 2)
    return {
        "rows": rows,
        "grand_total": grand,
        "grand_bonus": grand_bonus,
        "grand_advances_open": grand_advances,
        "grand_payments": grand_payments,
        "grand_net_payable": round(grand + grand_bonus - grand_advances - grand_payments, 2),
        "worker_count": len(rows),
        "from_date": from_date, "to_date": to_date,
    }


@api.get("/reports/payroll.pdf")
async def report_payroll_pdf(request: Request,
                             from_date: Optional[str] = None,
                             to_date: Optional[str] = None):
    """Payroll summary PDF (all karigars in the period)."""
    await get_current_user(request)
    data = await report_payroll(request, from_date, to_date)
    from pdf_payroll import build_payroll_summary
    pdf_bytes = build_payroll_summary(data)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="payroll-{from_date or ""}-{to_date or ""}.pdf"'},
    )


@api.get("/reports/payroll/{worker_id}.pdf")
async def report_wage_slip_pdf(worker_id: str, request: Request,
                               from_date: Optional[str] = None,
                               to_date: Optional[str] = None):
    """Per-karigar wage slip PDF."""
    await get_current_user(request)
    data = await report_payroll(request, from_date, to_date)
    row = next((r for r in data["rows"] if r["worker_id"] == worker_id), None)
    if not row:
        raise HTTPException(404, "No payroll data for this karigar in the period")
    advances = await db.advances.find({"worker_id": worker_id}).sort("date", -1).to_list(500)
    advances_list = [stringify(a) for a in advances]
    from pdf_payroll import build_wage_slip
    pdf_bytes = build_wage_slip(row, advances_list, data["from_date"], data["to_date"])
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="wage-slip-{row["name"].replace(" ", "_")}.pdf"'},
    )


# ---------- AUTO INVENTORY CONSUMPTION (on stage transition) ----------
async def _get_material_balance(material_id: str) -> float:
    movements = await db.inventory_movements.find({"material_id": material_id}).to_list(10000)
    stock = 0.0
    for m in movements:
        qty = float(m.get("quantity", 0) or 0)
        mtype = m.get("type")
        if mtype == "in":
            stock += qty
        elif mtype == "out":
            stock -= qty
        else: # adjustment
            stock += qty
    return stock


# ---------- AUTO INVENTORY CONSUMPTION (on stage transition) ----------
async def _auto_consume_inventory(job: dict, by_email: str):
    """When a job advances from procurement → cutting, auto-create stock-out movements
    for each BOM material based on job's quantity × yield-adjusted consumption.
    Idempotent: marks job.inventory_consumed=True so we don't double-deduct.
    """
    if job.get("inventory_consumed"):
        return False
    # Lookup style: store style_id on job and try that first, fall back to code matching
    style = None
    if job.get("style_id"):
        style = await db.styles.find_one({"_id": oid(job["style_id"])})
    if not style:
        style = await db.styles.find_one({"code": job.get("style_code")})
    if not style:
        await db.production_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {"inventory_consume_error": f"Style '{job.get('style_code')}' not found in Style Master"}}
        )
        return False
    style_d = stringify(style)
    pairs = job.get("quantity", 0)
    if not pairs or not style_d.get("bom"):
        return False
    # Build material id lookup by code
    mat_codes = [b.get("material_code") for b in style_d["bom"]]
    materials = await db.materials.find({"code": {"$in": mat_codes}}).to_list(500)
    by_code = {m["code"]: m for m in materials}

    movements = []
    temp_balances = {}
    for b in style_d["bom"]:
        rate = float(b.get("rate", 0))
        qty = float(b.get("quantity", 0))
        yld = float(b.get("yield_per_unit", 1) or 1)
        waste = float(b.get("waste_pct", 0) or 0)
        consume = pairs * (qty / yld) * (1 + waste / 100)
        if consume <= 0:
            continue
        mat = by_code.get(b.get("material_code"))
        if not mat:
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"inventory_consume_error": f"Material '{b.get('material_code')}' not found"}}
            )
            return False
        mat_id = str(mat["_id"])
        if mat_id not in temp_balances:
            temp_balances[mat_id] = await _get_material_balance(mat_id)
        if temp_balances[mat_id] - consume < 0:
            await db.production_jobs.update_one(
                {"_id": job["_id"]},
                {"$set": {"inventory_consume_error": f"Insufficient stock for '{mat.get('name')}'"}}
            )
            return False
        temp_balances[mat_id] -= consume

        movements.append({
            "material_id": mat_id,
            "material_code": mat.get("code"),
            "material_name": mat.get("name"),
            "unit": mat.get("unit"),
            "type": "out",
            "quantity": round(consume, 4),
            "rate": rate,
            "party": f"Job {job.get('po_number','')} · {job.get('style_code','')} · {job.get('color','')} · Sz {job.get('size','')}",
            "job_id": str(job["_id"]),
            "notes": "Auto-consumed when stage moved past Procurement",
            "date": datetime.now(timezone.utc).date().isoformat(),
            "by": by_email,
            "created_at": now_iso(),
            "auto": True,
        })
    if movements:
        await db.inventory_movements.insert_many(movements)
        await db.production_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {"inventory_consumed": True, "inventory_consumed_at": now_iso(), "inventory_consume_error": None}}
        )
        return True
    return False


@api.get("/inventory/alerts")
async def inventory_alerts(request: Request):
    """List materials whose balance <= reorder_level."""
    await get_current_user(request)
    inv_rows = await list_inventory(request)
    alerts = []
    materials = await db.materials.find({}).to_list(2000)
    rl = {str(m["_id"]): float(m.get("reorder_level", 0) or 0) for m in materials}
    for r in inv_rows:
        threshold = rl.get(r["material_id"], 0)
        if threshold > 0 and r["balance"] <= threshold:
            alerts.append({**r, "reorder_level": threshold, "shortfall": round(threshold - r["balance"], 2)})
    alerts.sort(key=lambda x: x["balance"])
    return alerts





@api.post("/production/card.pdf", dependencies=[Depends(pdf_rate_limiter)])
async def production_card_pdf(payload: dict, request: Request):
    """Generate a printable production card PDF for a (style+color+po) group.
    Accepts {job_ids:[...]} of all jobs belonging to the same style+color+PO.
    """
    await get_current_user(request)
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(400, "job_ids required")
    obj_ids = []
    for jid in job_ids:
        try:
            obj_ids.append(oid(jid))
        except HTTPException:
            continue
    jobs = await db.production_jobs.find({"_id": {"$in": obj_ids}}).to_list(500)
    if not jobs:
        raise HTTPException(404, "Jobs not found")
    j0 = jobs[0]
    # aggregate
    sizes = []
    seen = set()
    for j in sorted(jobs, key=lambda x: (float(x.get("size", 999)) if str(x.get("size", "")).replace('.', '', 1).isdigit() else 999)):
        sz = str(j.get("size", "—"))
        if sz in seen:
            continue
        seen.add(sz)
        sizes.append({"size": sz, "quantity": j.get("quantity", 0)})
    total_qty = sum(j.get("quantity", 0) for j in jobs)
    # components: aggregate (all=true)
    comp = {
        "upper_done": all((j.get("components") or {}).get("upper_done") for j in jobs),
        "bottom_done": all((j.get("components") or {}).get("bottom_done") for j in jobs),
        "sole_done": all((j.get("components") or {}).get("sole_done") for j in jobs),
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
    pdf_bytes = build_production_card(group, style_d)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="card-{group["po_number"]}-{group["style_code"]}-{group["color"]}.pdf"'},
    )


# ---------- DEFECTS ----------
@api.get("/defects")
async def list_defects(request: Request):
    await get_current_user(request)
    docs = await db.defects.find({}).sort("created_at", -1).to_list(2000)
    return [stringify(d) for d in docs]

@api.post("/defects")
async def create_defect(payload: DefectIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    doc = payload.model_dump()
    doc["reported_by"] = u["email"]
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    res = await db.defects.insert_one(doc)
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    return doc

@api.patch("/defects/{did}")
async def update_defect(did: str, payload: DefectIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    update = payload.model_dump()
    update["updated_at"] = now_iso()
    if update["status"] == "closed":
        update["closed_at"] = now_iso()
    await db.defects.update_one({"_id": oid(did)}, {"$set": update})
    return stringify(await db.defects.find_one({"_id": oid(did)}))

@api.delete("/defects/{did}")
async def delete_defect(did: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.defects.delete_one({"_id": oid(did)})
    return {"ok": True}


# ---------- DASHBOARD ----------
@api.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    await get_current_user(request)
    total_pos = await db.pos.count_documents({})
    pending_pos = await db.pos.count_documents({"status": "pending"})
    
    jobs = await db.production_jobs.find({}).to_list(10000)
    
    # B2B vs Online WIP/dispatched
    b2b_jobs = [j for j in jobs if j.get("source_type") != "online_channel"]
    online_jobs = [j for j in jobs if j.get("source_type") == "online_channel"]
    
    b2b_wip = sum(j["quantity"] for j in b2b_jobs if j["stage"] != "dispatched")
    b2b_dispatched = sum(j["quantity"] for j in b2b_jobs if j["stage"] == "dispatched")
    
    online_wip = sum(j["quantity"] for j in online_jobs if j["stage"] != "dispatched")
    online_dispatched = sum(j["quantity"] for j in online_jobs if j["stage"] == "dispatched")
    
    pairs_in_wip = b2b_wip + online_wip
    dispatched = b2b_dispatched + online_dispatched
    
    # Stage counts
    stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    b2b_stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    online_stage_counts = {s: 0 for s in PRODUCTION_STAGES}
    
    for j in jobs:
        stage_counts[j["stage"]] = stage_counts.get(j["stage"], 0) + j["quantity"]
        if j.get("source_type") == "online_channel":
            online_stage_counts[j["stage"]] = online_stage_counts.get(j["stage"], 0) + j["quantity"]
        else:
            b2b_stage_counts[j["stage"]] = b2b_stage_counts.get(j["stage"], 0) + j["quantity"]
            
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
            "total_qty": sum(j["quantity"] for j in online_jobs),
        }
    }


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


# ---------- App wiring ----------
# ═══════════════════════════════════════════════════════════════════════
# ══ WAREHOUSE MANAGEMENT SYSTEM (WMS) — Online Commerce Layer ══════════
# ═══════════════════════════════════════════════════════════════════════
# Structure: 4 rack blocks (A/B/C/D) × 10 rows × 8 columns = 320 cells.
# Each cell capacity = 30 pairs. Location code format: A-01-01 .. D-10-08.
#
# Collections:
#   • warehouse_locations       — 320 cells, capacity/occupied/available
#   • fg_location_inventory     — style×color×size×location → qty
#   • picklists                 — order fulfillment slips with location details
#
# Hook points (do NOT touch B2B production):
#   • _sync_warehouse_locations() is called from _apply_movement()
#   • /online-orders/import auto-generates picklists for covered qty
# ═══════════════════════════════════════════════════════════════════════

WAREHOUSE_ROWS = 10
RACKS_PER_ROW  = 3
RACKS          = [1, 2, 3]
CELLS_PER_RACK = 8
CAPACITY       = 40                  # pairs per cell
ROW_PAIRS      = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]


def _make_location_code(row: int, rack: int, cell: int) -> str:
    # New naming: f"R{row:02d}-RK{rack}-C{cell:02d}"  (e.g. "R01-RK1-C01" … "R10-RK3-C08")
    return f"R{row:02d}-RK{rack}-C{cell:02d}"


async def _seed_warehouse_locations():
    """Idempotent — inserts any missing cells into warehouse_locations.

    All cells use zone='main'. No return holding zone.
    """
    to_upsert = []
    for r in range(1, WAREHOUSE_ROWS + 1):
        for rack in range(1, RACKS_PER_ROW + 1):
            for c in range(1, CELLS_PER_RACK + 1):
                code = _make_location_code(r, rack, c)
                zone = "main"
                pair_group = (r - 1) // 2 + 1
                aisle_before = (r % 2 == 1 and r != 1)
                to_upsert.append({
                    "location_code":   code,
                    "rack":            rack,
                    "row":             r,
                    "cell":            c,
                    "zone":            zone,
                    "pair_group":      pair_group,
                    "aisle_before":    aisle_before,
                    "capacity_pairs":  CAPACITY,
                    "occupied_pairs":  0,
                    "available_pairs": CAPACITY,
                    "status":          "empty",  # empty | partial | full | blocked
                    "block_reason":    None,
                    "created_at":      now_iso(),
                    "updated_at":      now_iso(),
                })
    inserted = 0
    for doc in to_upsert:
        doc_on_insert = {k: v for k, v in doc.items() if k not in ("pair_group", "aisle_before", "zone")}
        res = await db.warehouse_locations.update_one(
            {"location_code": doc["location_code"]},
            {"$setOnInsert": doc_on_insert,
             "$set": {
                 "pair_group":   doc["pair_group"],
                 "aisle_before": doc["aisle_before"],
                 "zone":         doc["zone"],
             }},
            upsert=True,
        )
        if res.upserted_id:
            inserted += 1
    # Backfill zone for any pre-existing cells that lack it (kept for legacy
    # deployments; new-layout cells always have zone set on insert).
    await db.warehouse_locations.update_many(
        {"zone": {"$exists": False}},
        [{"$set": {"zone": "main"}}]
    )
    return inserted


def _recompute_status(occupied: int, capacity: int) -> str:
    if occupied <= 0:
        return "empty"
    if occupied >= capacity:
        return "full"
    return "partial"


async def _allocate_to_locations(style_id, style_code, color, size, qty, user_email,
                                  reference_type="", reference_id="", zone="main",
                                  prefer_existing_sku_cells=False):
    """Sequentially fill cells (by location_code ASC) until qty placed.
    prefer_existing_sku_cells: when True, first fill existing cells that already hold
       this SKU (with room to spare) before opening a fresh empty cell.
    """
    remaining = int(qty)
    placements = []
    guard = 0

    # Phase A — same-SKU consolidation (only when prefer_existing_sku_cells is True)
    if prefer_existing_sku_cells and remaining > 0:
        existing_cur = db.fg_location_inventory.find({
            "style_id": ObjectId(style_id), "color": color, "size": size,
        }).sort([("created_at", 1), ("location_code", 1)])
        async for inv in existing_cur:
            if remaining <= 0:
                break
            code = inv.get("location_code")
            # Only consolidate onto main-zone, non-blocked cells with room
            wloc = await db.warehouse_locations.find_one({
                "location_code": code, "zone": zone,
                "status": {"$ne": "blocked"}, "available_pairs": {"$gt": 0},
            })
            if not wloc:
                continue
            place_qty = min(remaining, int(wloc["available_pairs"]))
            new_occupied  = int(wloc["occupied_pairs"]) + place_qty
            new_available = int(wloc["available_pairs"]) - place_qty
            new_status    = _recompute_status(new_occupied, int(wloc["capacity_pairs"]))
            res = await db.warehouse_locations.update_one(
                {"_id": wloc["_id"], "available_pairs": wloc["available_pairs"]},
                {"$set": {"occupied_pairs": new_occupied, "available_pairs": new_available,
                          "status": new_status, "updated_at": now_iso()}},
            )
            if res.modified_count == 0:
                continue
            await db.fg_location_inventory.update_one(
                {"_id": inv["_id"]},
                {"$inc": {"qty": place_qty},
                 "$set": {"style_code": style_code, "updated_at": now_iso()}},
            )
            placements.append({"location_code": code, "qty": place_qty,
                                "rack": wloc["rack"], "row": wloc["row"], "cell": wloc["cell"],
                                "zone": zone, "consolidated": True})
            remaining -= place_qty

    # Phase B — sequential fill from first empty/partial cell in zone
    while remaining > 0 and guard < 500:
        guard += 1
        loc = await db.warehouse_locations.find_one(
            {"available_pairs": {"$gt": 0}, "status": {"$ne": "blocked"}, "zone": zone},
            sort=[("location_code", 1)],
        )
        if not loc:
            log.warning(f"WMS: {zone} zone full — {remaining} pairs unplaced for {style_code}/{color}/{size}")
            break
        place_qty = min(remaining, int(loc["available_pairs"]))
        new_occupied  = int(loc["occupied_pairs"]) + place_qty
        new_available = int(loc["available_pairs"]) - place_qty
        new_status    = _recompute_status(new_occupied, int(loc["capacity_pairs"]))
        # Optimistic lock on available_pairs
        res = await db.warehouse_locations.update_one(
            {"_id": loc["_id"], "available_pairs": loc["available_pairs"]},
            {"$set": {
                "occupied_pairs":  new_occupied,
                "available_pairs": new_available,
                "status":          new_status,
                "updated_at":      now_iso(),
            }},
        )
        if res.modified_count == 0:
            continue
        # Upsert fg_location_inventory
        await db.fg_location_inventory.update_one(
            {"style_id": ObjectId(style_id), "color": color, "size": size,
             "location_code": loc["location_code"]},
            {"$inc": {"qty": place_qty},
             "$set": {"style_code": style_code, "updated_at": now_iso()},
             "$setOnInsert": {"created_at": now_iso()}},
            upsert=True,
        )
        placements.append({"location_code": loc["location_code"], "qty": place_qty,
                            "rack": loc["rack"], "row": loc["row"], "cell": loc["cell"],
                            "zone": zone})
        remaining -= place_qty
    return {"placed_qty": int(qty) - remaining, "unplaced_qty": remaining, "placements": placements}


async def _deduct_from_locations(style_id, color, size, qty, user_email,
                                  reference_type="", reference_id="", zone=None):
    """FIFO deduction: oldest fg_location_inventory doc first (by created_at, then location_code).
    Optionally restrict to a specific zone."""
    remaining = int(qty)
    removals = []
    guard = 0
    # Precompute the set of location_codes in target zone if a filter is requested
    allowed_codes = None
    if zone:
        allowed_codes = set()
        async for w in db.warehouse_locations.find({"zone": zone}, {"location_code": 1}):
            allowed_codes.add(w["location_code"])
    while remaining > 0 and guard < 500:
        guard += 1
        q = {"style_id": ObjectId(style_id), "color": color, "size": size, "qty": {"$gt": 0}}
        if allowed_codes is not None:
            q["location_code"] = {"$in": list(allowed_codes)}
        loc_inv = await db.fg_location_inventory.find_one(
            q, sort=[("created_at", 1), ("location_code", 1)],
        )
        if not loc_inv:
            break
        take = min(remaining, int(loc_inv["qty"]))
        new_qty = int(loc_inv["qty"]) - take
        if new_qty <= 0:
            await db.fg_location_inventory.delete_one({"_id": loc_inv["_id"]})
        else:
            await db.fg_location_inventory.update_one(
                {"_id": loc_inv["_id"]},
                {"$set": {"qty": new_qty, "updated_at": now_iso()}},
            )
        # Update warehouse_locations counters
        wloc = await db.warehouse_locations.find_one({"location_code": loc_inv["location_code"]})
        if wloc:
            new_occupied  = max(0, int(wloc["occupied_pairs"]) - take)
            new_available = min(int(wloc["capacity_pairs"]),
                                int(wloc["available_pairs"]) + take)
            new_status    = _recompute_status(new_occupied, int(wloc["capacity_pairs"])) \
                              if wloc.get("status") != "blocked" else "blocked"
            await db.warehouse_locations.update_one(
                {"_id": wloc["_id"]},
                {"$set": {"occupied_pairs": new_occupied,
                          "available_pairs": new_available,
                          "status": new_status,
                          "updated_at": now_iso()}},
            )
        removals.append({"location_code": loc_inv["location_code"], "qty": take})
        remaining -= take
    return {"deducted_qty": int(qty) - remaining, "shortfall": remaining, "removals": removals}


async def _deduct_from_specific_location(style_id, color, size, qty, location_code):
    """Deduct qty from a specific location. Used by picklist confirm.
    Decrements both physical qty AND reserved_qty (picklist reservation is being fulfilled).
    """
    loc_inv = await db.fg_location_inventory.find_one({
        "style_id": ObjectId(style_id), "color": color, "size": size,
        "location_code": location_code,
    })
    if not loc_inv:
        raise HTTPException(400, f"No stock of {color}/{size} at {location_code}")
    if int(loc_inv.get("qty", 0)) < int(qty):
        raise HTTPException(400, f"Only {loc_inv['qty']} pairs at {location_code}, need {qty}")
    new_qty = int(loc_inv["qty"]) - int(qty)
    new_res = max(0, int(loc_inv.get("reserved_qty", 0)) - int(qty))
    if new_qty <= 0:
        await db.fg_location_inventory.delete_one({"_id": loc_inv["_id"]})
    else:
        await db.fg_location_inventory.update_one(
            {"_id": loc_inv["_id"]},
            {"$set": {"qty": new_qty, "reserved_qty": new_res, "updated_at": now_iso()}},
        )
    wloc = await db.warehouse_locations.find_one({"location_code": location_code})
    if wloc:
        new_occ = max(0, int(wloc["occupied_pairs"]) - int(qty))
        new_av  = min(int(wloc["capacity_pairs"]), int(wloc["available_pairs"]) + int(qty))
        new_st  = _recompute_status(new_occ, int(wloc["capacity_pairs"])) \
                    if wloc.get("status") != "blocked" else "blocked"
        await db.warehouse_locations.update_one(
            {"_id": wloc["_id"]},
            {"$set": {"occupied_pairs": new_occ, "available_pairs": new_av,
                      "status": new_st, "updated_at": now_iso()}},
        )
    return True


async def _sync_warehouse_locations(payload, user_email):
    """Central hook. Called from _apply_movement(). Maps FG movements → warehouse actions."""
    mt = payload.movement_type
    qty = int(payload.quantity)
    style_id, color, size = payload.style_id, payload.color, payload.size
    style = await db.styles.find_one({"_id": ObjectId(style_id)})
    style_code = style.get("code", "") if style else ""
    ref = payload.reference_type
    ref_id = payload.reference_id or ""

    if mt in ("production_in",):
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main")
    elif mt == "return_restocked":
        # Returns go into main zone, preferring cells that already hold this SKU.
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main",
                                                 prefer_existing_sku_cells=True)
    elif mt == "return_in":
        # Fresh return — put directly in main zone since no cells are reserved for returns
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main")
    elif mt in ("dispatched", "liquidation_out", "return_damaged"):
        if qty > 0:
            return await _deduct_from_locations(style_id, color, size, qty,
                                                 user_email, ref, ref_id)
    elif mt == "adjustment" and payload.adjustment_field == "ready_stock_qty":
        if qty > 0:
            return await _allocate_to_locations(style_id, style_code, color, size, qty,
                                                 user_email, ref, ref_id, zone="main")
        elif qty < 0:
            return await _deduct_from_locations(style_id, color, size, abs(qty),
                                                 user_email, ref, ref_id)
    return None


# ───────────── Warehouse Endpoints ─────────────

@api.get("/warehouse/locations")
async def wms_list_locations(
    request: Request,
    rack: Optional[str] = None,
    status: Optional[str] = None,
    zone: Optional[str] = None,
    search: Optional[str] = None,
):
    """List all warehouse cells with capacity/occupied stats. Filterable."""
    await get_current_user(request)
    q = {}
    if rack:
        try:
            q["rack"] = int(rack)
        except ValueError:
            q["rack"] = rack.upper()
    if status: q["status"] = status
    if zone:   q["zone"] = zone
    if search: q["location_code"] = {"$regex": search, "$options": "i"}
    docs = await db.warehouse_locations.find(q).sort("location_code", 1).to_list(500)
    return [stringify(d) for d in docs]


class LocationBlockIn(BaseModel):
    blocked: bool
    reason: Optional[str] = None


@api.patch("/warehouse/locations/{code}/block")
async def wms_block_location(request: Request, code: str, payload: LocationBlockIn):
    """Block or unblock a cell for repairs / maintenance / damage."""
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    code = code.upper().strip()
    loc = await db.warehouse_locations.find_one({"location_code": code})
    if not loc:
        raise HTTPException(404, "Location not found")
    if payload.blocked:
        new_status = "blocked"
        upd = {"status": new_status, "block_reason": payload.reason or "manually blocked",
               "blocked_at": now_iso(), "blocked_by": u["email"], "updated_at": now_iso()}
    else:
        new_status = _recompute_status(int(loc["occupied_pairs"]), int(loc["capacity_pairs"]))
        upd = {"status": new_status, "block_reason": None,
               "blocked_at": None, "blocked_by": None, "updated_at": now_iso()}
    await db.warehouse_locations.update_one({"_id": loc["_id"]}, {"$set": upd})
    await log_activity("UPDATE", "warehouse_locations",
                        f"{'Blocked' if payload.blocked else 'Unblocked'} {code}: {payload.reason or '-'}", u["email"])
    return stringify(await db.warehouse_locations.find_one({"_id": loc["_id"]}))


@api.get("/warehouse/locations/{code}")
async def wms_get_location(request: Request, code: str):
    """Get one cell + list all SKUs stored in it."""
    await get_current_user(request)
    loc = await db.warehouse_locations.find_one({"location_code": code.upper()})
    if not loc:
        raise HTTPException(404, "Location not found")
    contents = await db.fg_location_inventory.find({"location_code": code.upper()}).to_list(500)
    return {"location": stringify(loc), "contents": [stringify(c) for c in contents]}


@api.post("/warehouse/seed-locations")
async def wms_seed(request: Request):
    """Idempotently seed all cells for the current layout. Safe to call any time."""
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    inserted = await _seed_warehouse_locations()
    total = await db.warehouse_locations.count_documents({})
    return {"inserted": inserted, "total": total}


@api.post("/warehouse/rebuild-layout")
async def wms_rebuild_layout(request: Request):
    """DESTRUCTIVE: drop `warehouse_locations` and reseed with the current
    layout (10 lines × 3 racks × 8 cells @ 40 pairs = 240 cells / 9,600 pairs).

    Existing `fg_location_inventory` rows are auto-migrated: each row is
    relocated to the first available cell of the new layout, preferring cells
    already holding the same (style, color) so per-style stock stays clustered
    together (matches the user's "re-racking must reuse allotted rack" rule).

    Returns a migration report.
    """
    u = await get_current_user(request); require_roles("admin")(u)

    dropped = await db.warehouse_locations.count_documents({})
    await db.warehouse_locations.delete_many({})
    inserted = await _seed_warehouse_locations()

    # Migrate fg_location_inventory to the new layout ------------------------
    now = now_iso()
    moved   = 0
    skipped = 0
    # style_id → assigned location_code (so the same style keeps landing in the
    # same rack cell until it fills up, then the next one over).
    style_home: dict = {}
    # location_code → running qty already assigned in this migration pass
    fill: dict = {}

    async def _next_cell_for(style_id: str, qty_needed: int) -> Optional[str]:
        """Find a cell that (a) is already this style's "home" if not yet full,
        else (b) the first empty cell, honouring capacity."""
        home = style_home.get(style_id)
        if home and fill.get(home, 0) + qty_needed <= CAPACITY:
            return home
        # Otherwise pick the next empty (or partially-filled) main cell
        async for w in db.warehouse_locations.find({"zone": "main"}).sort([("row", 1), ("rack", 1), ("cell", 1)]):
            code = w["location_code"]
            if fill.get(code, 0) + qty_needed <= CAPACITY:
                style_home[style_id] = code
                return code
        return None

    cur = db.fg_location_inventory.find({}).sort([("style_id", 1), ("color", 1), ("size", 1)])
    async for inv in cur:
        qty = int(inv.get("qty", 0))
        if qty <= 0:
            await db.fg_location_inventory.delete_one({"_id": inv["_id"]})
            continue
        sid = str(inv.get("style_id"))
        new_code = await _next_cell_for(sid, qty)
        if not new_code:
            skipped += 1
            continue
        # Fetch cell to enrich rack/row/col (used by picklist reports)
        cell = await db.warehouse_locations.find_one({"location_code": new_code})
        await db.fg_location_inventory.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "location_code": new_code,
                "rack":          cell.get("rack"),
                "row":           cell.get("row"),
                "cell":          cell.get("cell"),
                "updated_at":    now,
            }},
        )
        fill[new_code] = fill.get(new_code, 0) + qty
        moved += 1

    # Re-sync warehouse_locations counters based on new fg_location_inventory
    for code, occ in fill.items():
        await db.warehouse_locations.update_one(
            {"location_code": code},
            {"$set": {
                "occupied_pairs":  occ,
                "available_pairs": max(0, CAPACITY - occ),
                "status":          _recompute_status(occ, CAPACITY),
                "updated_at":      now,
            }},
        )
    return {
        "dropped_cells":  dropped,
        "inserted_cells": inserted,
        "capacity_per_cell": CAPACITY,
        "total_capacity_pairs": CAPACITY * inserted,
        "fg_locations_migrated": moved,
        "fg_locations_skipped_no_room": skipped,
        "style_home_assignments": len(style_home),
    }


@api.get("/warehouse/fg-locations")
async def wms_fg_location_inventory(
    request: Request,
    style_id: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    location_code: Optional[str] = None,
):
    """List fg_location_inventory rows. Filterable."""
    await get_current_user(request)
    q = {}
    if style_id:
        try:
            q["style_id"] = ObjectId(style_id)
        except Exception:
            pass
    if color: q["color"] = color
    if size:  q["size"] = size
    if location_code: q["location_code"] = location_code.upper()
    docs = await db.fg_location_inventory.find(q).sort("location_code", 1).to_list(2000)
    return [stringify(d) for d in docs]


@api.get("/warehouse/dashboard")
async def wms_dashboard(request: Request):
    """Aggregate stats for the warehouse dashboard."""
    await get_current_user(request)
    locs = await db.warehouse_locations.find({}).to_list(1000)
    total_cells      = len(locs)
    total_capacity   = sum(int(l.get("capacity_pairs", 0))  for l in locs)
    total_occupied   = sum(int(l.get("occupied_pairs", 0))  for l in locs)
    total_available  = sum(int(l.get("available_pairs", 0)) for l in locs)
    empty_cells      = sum(1 for l in locs if l.get("status") == "empty")
    partial_cells    = sum(1 for l in locs if l.get("status") == "partial")
    full_cells       = sum(1 for l in locs if l.get("status") == "full")
    blocked_cells    = sum(1 for l in locs if l.get("status") == "blocked")

    # Per-rack breakdown
    by_rack = {}
    for r in RACKS:
        rlocs = [l for l in locs if l.get("rack") == r]
        by_rack[r] = {
            "total_cells":     len(rlocs),
            "occupied_pairs":  sum(int(l.get("occupied_pairs", 0)) for l in rlocs),
            "available_pairs": sum(int(l.get("available_pairs", 0)) for l in rlocs),
            "capacity_pairs":  sum(int(l.get("capacity_pairs", 0)) for l in rlocs),
            "empty_cells":     sum(1 for l in rlocs if l.get("status") == "empty"),
            "partial_cells":   sum(1 for l in rlocs if l.get("status") == "partial"),
            "full_cells":      sum(1 for l in rlocs if l.get("status") == "full"),
        }

    # Active picklists
    active_picklists   = await db.picklists.count_documents({"status": {"$in": ["pending", "in_progress"]}})
    pending_picklists  = await db.picklists.count_documents({"status": "pending"})
    completed_today    = await db.picklists.count_documents({
        "status": "completed",
        "completed_at": {"$gte": now_iso()[:10] + "T00:00:00Z"},
    })

    # Distinct SKUs stored
    distinct_skus = len(await db.fg_location_inventory.distinct("style_id"))

    utilization_pct = round((total_occupied / total_capacity * 100), 2) if total_capacity else 0

    # Zone breakdown (single main zone)
    by_zone = {
        "main": {
            "cells":           len(locs),
            "capacity_pairs":  total_capacity,
            "occupied_pairs":  total_occupied,
            "available_pairs": total_available,
        },
    }

    return {
        "total_cells":       total_cells,
        "total_capacity":    total_capacity,
        "total_occupied":    total_occupied,
        "total_available":   total_available,
        "utilization_pct":   utilization_pct,
        "empty_cells":       empty_cells,
        "partial_cells":     partial_cells,
        "full_cells":        full_cells,
        "blocked_cells":     blocked_cells,
        "distinct_skus":     distinct_skus,
        "active_picklists":  active_picklists,
        "pending_picklists": pending_picklists,
        "completed_today":   completed_today,
        "by_rack":           by_rack,
        "by_zone":           by_zone,
    }


# ───────────── Picklist Endpoints ─────────────

async def _next_picklist_no() -> str:
    """PL-YYYYMMDD-NNN sequential."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"PL-{today}-"
    last = await db.picklists.find({"picklist_no": {"$regex": f"^{prefix}"}}) \
                             .sort("picklist_no", -1).limit(1).to_list(1)
    seq = 1
    if last:
        try:
            seq = int(last[0]["picklist_no"].split("-")[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:03d}"


async def _generate_picklist_for_order(order_id: str, channel: str, order_lines: List[dict],
                                        user_email: str):
    """Build a picklist for an online order using FIFO allocation. Only covers what's
    available in fg_location_inventory (net of location-level reservations). Returns
    (picklist_doc, covered_map, uncovered_map).

    order_lines: [{style_id, style_code, color, size, quantity}]
    """
    items = []
    covered = {}     # (style_id,color,size) → qty covered
    uncovered = {}   # (style_id,color,size) → qty short
    reservations_to_book = []
    loc_reservations_to_book = []  # (fg_location_inventory _id, qty) pairs

    for line in order_lines:
        style_id   = line.get("style_id")
        style_code = line.get("style_code", "")
        color      = line.get("color", "")
        size       = line.get("size", "")
        need       = int(line.get("quantity", 0))
        if not style_id or need <= 0:
            continue
        # FIFO allocate — find candidate locations
        remaining = need
        picked = []
        q_loc = {
            "$or": [{"style_id": ObjectId(style_id)}, {"style_id": str(style_id)}],
            "qty": {"$gt": 0},
        }
        color_val = (color or "").strip()
        size_val  = (size  or "").strip()
        if color_val:
            q_loc["color"] = {"$regex": f"^{re.escape(color_val)}$", "$options": "i"}
        if size_val:
            q_loc["size"]  = {"$regex": f"^{re.escape(size_val)}$",  "$options": "i"}

        cur = db.fg_location_inventory.find(q_loc).sort([("created_at", 1), ("location_code", 1)])
        async for loc in cur:
            if remaining <= 0:
                break
            qty_val = int(loc.get("qty", 0) or 0)
            res_val = int(loc.get("reserved_qty", 0) or 0)
            free_here = qty_val - res_val
            if free_here <= 0:
                continue
            take = min(remaining, free_here)
            picked.append({
                "loc_inv_id":    loc["_id"],
                "location_code": loc["location_code"], "qty": take,
                "style_id":      str(loc["style_id"]), "style_code": style_code,
                "color":         color, "size": size,
            })
            remaining -= take

        # Enrich each pick with rack/row/col via warehouse_locations
        codes = list({p["location_code"] for p in picked})
        wloc_map = {}
        if codes:
            async for w in db.warehouse_locations.find({"location_code": {"$in": codes}}):
                wloc_map[w["location_code"]] = w
        for p in picked:
            w = wloc_map.get(p["location_code"], {})
            item = {
                "style_id":      p["style_id"], "style_code": p["style_code"],
                "color":         p["color"],    "size":       p["size"],
                "location_code": p["location_code"], "qty":    p["qty"],
                "rack":          w.get("rack"), "row":        w.get("row"),
                "cell":          w.get("cell"),
                "picked":        False, "picked_at": None,
            }
            items.append(item)
            loc_reservations_to_book.append((p["loc_inv_id"], p["qty"]))

        covered_qty = need - remaining
        if covered_qty > 0:
            covered[(style_id, color, size)] = covered_qty
            reservations_to_book.append({
                "style_id": style_id, "color": color, "size": size,
                "qty": covered_qty, "style_code": style_code,
            })
        if remaining > 0:
            uncovered[(style_id, color, size)] = remaining

    picklist_no = await _next_picklist_no()
    doc = {
        "picklist_no": picklist_no,
        "order_id":    order_id,
        "channel":     channel,
        "status":      "pending",
        "picker":      None,
        "items":       items,
        "total_items": len(items),
        "total_qty":   sum(i["qty"] for i in items),
        "created_at":  now_iso(),
        "updated_at":  now_iso(),
        "created_by":  user_email,
        "completed_at": None,
    }
    if items:
        # Book location-level reservations (prevents overlap with future picklists)
        for loc_inv_id, take in loc_reservations_to_book:
            try:
                await db.fg_location_inventory.update_one(
                    {"_id": loc_inv_id},
                    {"$inc": {"reserved_qty": int(take)}, "$set": {"updated_at": now_iso()}},
                )
            except Exception as e:
                log.warning(f"Location reservation increment failed: {e}")
        # Book SKU-level reservations for the covered portion
        for r in reservations_to_book:
            try:
                mv = FgStockMovementIn(
                    style_id=r["style_id"], color=r["color"], size=r["size"],
                    movement_type="reserved", quantity=int(r["qty"]),
                    reference_type="online_order", reference_id=order_id,
                    online_order_id=order_id, notes=f"Auto-reserved for picklist {picklist_no}",
                )
                await _apply_movement(mv, user_email, skip_location_sync=True)
            except Exception as e:
                log.warning(f"Reservation booking failed for {r}: {e}")
        res = await db.picklists.insert_one(doc)
        doc["_id"] = res.inserted_id
    return doc, covered, uncovered


@api.get("/picklists")
async def list_picklists(
    request: Request,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    order_id: Optional[str] = None,
    picker: Optional[str] = None,
):
    await get_current_user(request)
    q = {}
    if status:   q["status"] = status
    if channel:  q["channel"] = channel.lower()
    if order_id: q["order_id"] = order_id
    if picker:   q["picker"] = picker
    docs = await db.picklists.find(q).sort("created_at", -1).to_list(500)
    return [stringify(d) for d in docs]


@api.get("/picklists/{pid}")
async def get_picklist(request: Request, pid: str):
    await get_current_user(request)
    try:
        doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(404, "Picklist not found")
    # Enrich items with style image + client-facing details for print/UX.
    style_ids = list({ObjectId(i["style_id"]) for i in doc.get("items", []) if i.get("style_id")})
    style_map: dict = {}
    if style_ids:
        async for s in db.styles.find({"_id": {"$in": style_ids}}):
            style_map[str(s["_id"])] = {
                "image_url":              s.get("image_url", ""),
                "image_display_url":      s.get("image_display_url", ""),
                "image_thumbnail_url":    s.get("image_thumbnail_url", ""),
                "style_name":             s.get("name", ""),
            }
    for it in doc.get("items", []):
        info = style_map.get(str(it.get("style_id")), {})
        it["image_url"]           = info.get("image_url", "")
        it["image_display_url"]   = info.get("image_display_url", "")
        it["image_thumbnail_url"] = info.get("image_thumbnail_url", "")
        it["style_name"]          = info.get("style_name", "")
    return stringify(doc)


@api.post("/picklists")
async def create_picklist(request: Request, payload: PicklistIn):
    """Manually create a picklist. Auto-generation happens on /online-orders/import."""
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    lines = [{
        "style_id": i.style_id, "style_code": i.style_code,
        "color": i.color, "size": i.size, "quantity": i.qty,
    } for i in payload.items]
    doc, covered, uncovered = await _generate_picklist_for_order(
        payload.order_id, payload.channel, lines, u["email"])
    return {"picklist": stringify(doc),
            "covered": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in covered.items()},
            "uncovered": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in uncovered.items()}}


@api.patch("/picklists/{pid}")
async def patch_picklist(request: Request, pid: str, payload: PicklistPatchIn):
    u = await get_current_user(request); require_roles("admin", "manager", "production", "operator")(u)
    upd = {"updated_at": now_iso()}
    if payload.picker is not None: upd["picker"] = payload.picker
    if payload.status is not None: upd["status"] = payload.status
    try:
        res = await db.picklists.update_one({"_id": ObjectId(pid)}, {"$set": upd})
    except Exception:
        raise HTTPException(404, "Picklist not found")
    if not res.matched_count:
        raise HTTPException(404, "Picklist not found")
    doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    return stringify(doc)


@api.post("/picklists/{pid}/pick-item")
async def pick_item(request: Request, pid: str, payload: PickItemIn):
    """Confirm a pick: verify scan matches, deduct from that specific location."""
    u = await get_current_user(request); require_roles("admin", "manager", "production", "operator")(u)
    try:
        doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(404, "Picklist not found")
    if payload.item_index < 0 or payload.item_index >= len(doc.get("items", [])):
        raise HTTPException(400, "Invalid item_index")
    item = doc["items"][payload.item_index]
    if item.get("picked"):
        raise HTTPException(400, "Item already picked")
    if payload.scanned_location.upper().strip() != item["location_code"].upper():
        raise HTTPException(400,
            f"Scan mismatch — expected {item['location_code']}, got {payload.scanned_location}")

    # Deduct qty from that exact location
    await _deduct_from_specific_location(
        item["style_id"], item["color"], item["size"],
        int(item["qty"]), item["location_code"],
    )

    # Post the 'dispatched' ledger row (skip location sync — we already did it)
    try:
        mv = FgStockMovementIn(
            style_id=item["style_id"], color=item["color"], size=item["size"],
            movement_type="dispatched", quantity=int(item["qty"]),
            reference_type="online_order", reference_id=doc["order_id"],
            online_order_id=doc["order_id"], notes=f"Picklist {doc['picklist_no']} item {payload.item_index}",
        )
        await _apply_movement(mv, u["email"], skip_location_sync=True)
    except Exception as e:
        log.warning(f"Dispatched ledger failed: {e}")

    # Mark this item picked
    now = now_iso()
    doc["items"][payload.item_index]["picked"] = True
    doc["items"][payload.item_index]["picked_at"] = now
    doc["items"][payload.item_index]["picked_by"] = u["email"]

    all_picked = all(bool(i.get("picked")) for i in doc["items"])
    new_status = "completed" if all_picked else "in_progress"
    upd = {"items": doc["items"], "status": new_status, "updated_at": now}
    if all_picked:
        upd["completed_at"] = now
    await db.picklists.update_one({"_id": ObjectId(pid)}, {"$set": upd})
    updated = await db.picklists.find_one({"_id": ObjectId(pid)})
    return stringify(updated)


@api.delete("/picklists/{pid}")
async def delete_picklist(request: Request, pid: str):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    try:
        doc = await db.picklists.find_one({"_id": ObjectId(pid)})
    except Exception:
        doc = None
    if not doc:
        raise HTTPException(404, "Picklist not found")
    if doc.get("status") == "completed":
        raise HTTPException(400, "Cannot delete a completed picklist. Use returns flow instead.")
    # Release location-level reservations on all unpicked items
    for it in doc.get("items", []):
        if it.get("picked"):
            continue
        try:
            await db.fg_location_inventory.update_one(
                {"style_id": ObjectId(it["style_id"]), "color": it["color"],
                 "size": it["size"], "location_code": it["location_code"]},
                {"$inc": {"reserved_qty": -int(it["qty"])}, "$set": {"updated_at": now_iso()}},
            )
        except Exception:
            pass
    # Release any active reservations tied to this order
    if doc.get("order_id"):
        await db.inventory_reservations.update_many(
            {"online_order_id": doc["order_id"], "status": "active"},
            {"$set": {"status": "released", "released_at": now_iso()}},
        )
        # Also unreserve the qty in fg_inventory (best-effort per-item)
        for it in doc.get("items", []):
            if it.get("picked"):
                continue
            try:
                mv = FgStockMovementIn(
                    style_id=it["style_id"], color=it["color"], size=it["size"],
                    movement_type="unreserved", quantity=int(it["qty"]),
                    reference_type="online_order", reference_id=doc["order_id"],
                    online_order_id=doc["order_id"],
                    notes=f"Picklist {doc['picklist_no']} cancelled",
                )
                await _apply_movement(mv, u["email"], skip_location_sync=True)
            except Exception:
                pass
    await db.picklists.delete_one({"_id": ObjectId(pid)})
    return {"ok": True}


# ───────────── Warehouse Reports ─────────────

@api.get("/warehouse/reports/capacity")
async def report_capacity(request: Request):
    """Total capacity, used, available; per-rack breakdown."""
    await get_current_user(request)
    locs = await db.warehouse_locations.find({}).to_list(1000)
    total_capacity  = sum(int(l.get("capacity_pairs", 0))  for l in locs)
    total_occupied  = sum(int(l.get("occupied_pairs", 0))  for l in locs)
    total_available = sum(int(l.get("available_pairs", 0)) for l in locs)
    by_rack = []
    for r in RACKS:
        rlocs = [l for l in locs if l.get("rack") == r]
        cap = sum(int(l.get("capacity_pairs", 0)) for l in rlocs)
        occ = sum(int(l.get("occupied_pairs", 0)) for l in rlocs)
        by_rack.append({
            "rack": r,
            "cells": len(rlocs),
            "capacity_pairs":  cap,
            "occupied_pairs":  occ,
            "available_pairs": cap - occ,
            "utilization_pct": round((occ / cap * 100), 2) if cap else 0,
        })
    return {
        "total_cells":     len(locs),
        "total_capacity":  total_capacity,
        "total_occupied":  total_occupied,
        "total_available": total_available,
        "utilization_pct": round((total_occupied / total_capacity * 100), 2) if total_capacity else 0,
        "by_rack":         by_rack,
    }


@api.get("/warehouse/reports/location-utilization")
async def report_location_utilization(request: Request):
    """Per-cell utilization + top 20 fullest and 20 emptiest."""
    await get_current_user(request)
    locs = await db.warehouse_locations.find({}).to_list(1000)
    rows = []
    for l in locs:
        cap = int(l.get("capacity_pairs", 0) or 0)
        occ = int(l.get("occupied_pairs", 0) or 0)
        rows.append({
            "location_code":   l["location_code"],
            "rack":            l.get("rack"),
            "row":             l.get("row"),
            "cell":            l.get("cell"),
            "capacity_pairs":  cap,
            "occupied_pairs":  occ,
            "available_pairs": cap - occ,
            "utilization_pct": round((occ / cap * 100), 2) if cap else 0,
            "status":          l.get("status"),
        })
    rows.sort(key=lambda r: r["location_code"])
    fullest = sorted(rows, key=lambda r: -r["utilization_pct"])[:20]
    emptiest = sorted([r for r in rows if r["utilization_pct"] < 100], key=lambda r: r["utilization_pct"])[:20]
    return {"rows": rows, "fullest": fullest, "emptiest": emptiest}


@api.get("/warehouse/reports/picking-efficiency")
async def report_picking_efficiency(request: Request, days: int = 30):
    """Picker efficiency: picks/hour, avg completion time, orders picked."""
    await get_current_user(request)
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    picklists = await db.picklists.find({
        "status": "completed",
        "completed_at": {"$gte": since},
    }).to_list(2000)
    # Per-picker stats
    per_picker = {}
    grand = {"picklists": 0, "items": 0, "qty": 0, "avg_minutes": 0}
    total_minutes = 0.0
    total_pl = 0
    for pl in picklists:
        picker = pl.get("picker") or pl.get("created_by") or "unknown"
        try:
            started = pl.get("created_at", "").replace("Z", "+00:00")
            ended = pl.get("completed_at", "").replace("Z", "+00:00")
            t1 = datetime.fromisoformat(started)
            t2 = datetime.fromisoformat(ended)
            minutes = max(0.0, (t2 - t1).total_seconds() / 60.0)
        except Exception:
            minutes = 0.0
        items_count = len(pl.get("items", []))
        qty_count = sum(int(i.get("qty", 0)) for i in pl.get("items", []))
        row = per_picker.setdefault(picker, {"picker": picker, "picklists": 0,
                                              "items": 0, "qty": 0, "total_minutes": 0.0})
        row["picklists"] += 1
        row["items"]     += items_count
        row["qty"]       += qty_count
        row["total_minutes"] += minutes
        total_minutes += minutes
        total_pl += 1
        grand["picklists"] += 1
        grand["items"]     += items_count
        grand["qty"]       += qty_count

    for row in per_picker.values():
        row["avg_minutes_per_picklist"] = round(row["total_minutes"] / max(row["picklists"], 1), 2)
        row["items_per_hour"] = round((row["items"] / row["total_minutes"] * 60), 2) if row["total_minutes"] else 0
        row["total_minutes"] = round(row["total_minutes"], 2)
    grand["avg_minutes_per_picklist"] = round(total_minutes / max(total_pl, 1), 2)
    grand["items_per_hour"] = round((grand["items"] / total_minutes * 60), 2) if total_minutes else 0
    return {"days": int(days), "grand_total": grand,
            "per_picker": sorted(per_picker.values(), key=lambda r: -r["picklists"])}


# ───────────── Pending Product List (production role) ─────────────

@api.get("/production/pending-list")
async def pending_product_list(request: Request):
    """Online-channel production jobs not yet dispatched, with component-availability
    flag. This is the printable/mobile Pending Product List for the production role."""
    await get_current_user(request)

    jobs = await db.production_jobs.find({
        "source_type": "online_channel",
        "stage": {"$ne": "dispatched"},
    }).sort("created_at", 1).to_list(2000)

    # Preload BOM & component stock for each unique style_id
    style_ids = list({str(j.get("style_id")) for j in jobs if j.get("style_id")})
    comp_stock_by_style = {}  # style_id → {"components_available": bool, "shortages": [...]}
    for sid in style_ids:
        try:
            oid = ObjectId(sid)
        except Exception:
            comp_stock_by_style[sid] = {"components_available": False, "shortages": []}
            continue
        bom = await db.style_component_mapping.find({
            "style_id": oid, "active": {"$ne": False},
        }).to_list(200)
        if not bom:
            comp_stock_by_style[sid] = {"components_available": True, "shortages": [],
                                         "note": "No BOM mapped"}
            continue
        shortages = []
        ok = True
        for b in bom:
            comp = await db.component_master.find_one({"_id": ObjectId(b["component_id"])})
            if not comp:
                continue
            cur = int(comp.get("current_stock", 0)) - int(comp.get("reserved_stock", 0))
            need_per_pair = float(b.get("qty_per_pair", 1) or 1)
            if cur <= 0:
                ok = False
                shortages.append({
                    "component_code": comp.get("component_code"),
                    "component_name": comp.get("component_name"),
                    "available":      cur,
                    "per_pair":       need_per_pair,
                })
        comp_stock_by_style[sid] = {"components_available": ok, "shortages": shortages}

    out = []
    # Preload style images / names for pending jobs so the frontend can render
    # the picklist-style print card without extra network calls.
    style_lookup: dict = {}
    if style_ids:
        style_object_ids = []
        for sid in style_ids:
            try:
                style_object_ids.append(ObjectId(sid))
            except Exception:
                continue
        if style_object_ids:
            async for s in db.styles.find({"_id": {"$in": style_object_ids}}):
                style_lookup[str(s["_id"])] = {
                    "image_url":              s.get("image_url", ""),
                    "image_display_url":      s.get("image_display_url", ""),
                    "image_thumbnail_url":    s.get("image_thumbnail_url", ""),
                    "style_name":             s.get("name", ""),
                }
    for j in jobs:
        jd = stringify(j)
        sid = jd.get("style_id")
        info = comp_stock_by_style.get(sid, {"components_available": False, "shortages": []})
        jd["components_available"] = bool(info.get("components_available"))
        jd["component_shortages"]  = info.get("shortages", [])
        s_meta = style_lookup.get(sid, {})
        jd["image_url"]           = s_meta.get("image_url", "")
        jd["image_display_url"]   = s_meta.get("image_display_url", "")
        jd["image_thumbnail_url"] = s_meta.get("image_thumbnail_url", "")
        jd["style_name"]          = s_meta.get("style_name", "")
        out.append(jd)
    out.sort(key=lambda x: (not x.get("components_available"), x.get("created_at", "")))
    return out


# ---------- Pending List Snapshots ----------

@api.post("/production/pending-list/snapshot")
async def create_pending_list_snapshot(request: Request, payload: Optional[dict] = None):
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    filter_used = (payload or {}).get("filter_used", "all")
    
    # Call the existing logic internally
    jobs = await pending_product_list(request)
    
    # Compute totals
    pending = len(jobs)
    ready = sum(1 for j in jobs if j.get("components_available"))
    shortage = sum(1 for j in jobs if not j.get("components_available"))
    total_pairs = sum(int(j.get("quantity", 0)) for j in jobs)
    
    doc = {
        "saved_at": now_iso(),
        "saved_by": u["email"],
        "filter_used": filter_used,
        "totals": {
            "pending": pending,
            "ready": ready,
            "shortage": shortage,
            "total_pairs": total_pairs
        },
        "jobs": jobs
    }
    
    res = await db.pending_list_snapshots.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@api.get("/production/pending-list/snapshots")
async def list_pending_list_snapshots(request: Request):
    await get_current_user(request)
    docs = await db.pending_list_snapshots.find({}, {"jobs": 0}).sort("saved_at", -1).to_list(1000)
    return [stringify(d) for d in docs]


@api.get("/production/pending-list/snapshots/{id}")
async def get_pending_list_snapshot(id: str, request: Request):
    await get_current_user(request)
    doc = await db.pending_list_snapshots.find_one({"_id": oid(id)})
    if not doc:
        raise HTTPException(404, "Snapshot not found")
    return stringify(doc)


# ─────────────────────────────────────────────────────────────────────────
# Produce a pending cell (Online / B2B) → deduct components, add excess to
# stock in the style's already-allotted rack, record short-production reason.
# ─────────────────────────────────────────────────────────────────────────

class ProduceCellIn(BaseModel):
    style_id:      str
    color:         str
    size:          str
    produced_qty:  int
    reason:        Optional[str] = ""       # required when produced_qty < pending
    use_components: bool          = True     # False = "raw material mode", no component_stock deduct
    channel_filter: Optional[str] = None     # if set, only pending jobs from this source get consumed
    dispatch_stage: Optional[str] = "dispatched"
    force_negative_stock: bool    = False    # explicit override to allow deducting past zero


async def _find_style_home_cell(style_id: str) -> Optional[str]:
    """Return the location_code where this style is currently stocked. If
    multiple, return the one with the most existing qty (largest cluster) —
    that becomes the "allotted rack" for further re-racking / excess.
    """
    try:
        oid_v = ObjectId(style_id)
    except Exception:
        return None
    pipeline = [
        {"$match": {"style_id": oid_v, "qty": {"$gt": 0}}},
        {"$group": {"_id": "$location_code", "total": {"$sum": "$qty"}}},
        {"$sort": {"total": -1}},
        {"$limit": 1},
    ]
    docs = await db.fg_location_inventory.aggregate(pipeline).to_list(1)
    return docs[0]["_id"] if docs else None


async def _pick_new_cell_for_style(style_id: str) -> Optional[str]:
    """When a style has never been stocked, pick the first empty main cell."""
    home = await _find_style_home_cell(style_id)
    if home:
        return home
    async for w in db.warehouse_locations.find(
        {"zone": "main", "status": "empty"}
    ).sort([("row", 1), ("rack", 1), ("cell", 1)]).limit(1):
        return w["location_code"]
    return None


@api.post("/production/produce-cell")
async def produce_cell(request: Request, payload: ProduceCellIn):
    """Complete production for a specific (style, color, size) cell of the
    pending list. Handles four cases:

    1) `produced == pending` → mark all matching pending jobs as dispatched.
    2) `produced <  pending` → mark that portion dispatched, keep the shortfall
       on the pending list, and log a `short_production` record with reason.
    3) `produced >  pending` → dispatch all matching jobs, add the excess to
       fg_stock + fg_location_inventory in the style's currently-allotted rack
       (or the first empty cell if the style has no cluster yet). This is the
       "re-racking rule": already-allotted cells absorb further stock until
       they're full, then spill over.
    4) `use_components=True` AND a BOM exists for the style → deduct
       `component_master.current_stock` for each component in proportion to
       produced_qty and record the deduction in history.

    Returns a summary payload the frontend can toast.
    """
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)

    if payload.produced_qty <= 0:
        raise HTTPException(400, "produced_qty must be > 0")

    # Fetch pending jobs matching (style, color, size). FIFO by created_at.
    q: dict = {
        "style_id": ObjectId(payload.style_id),
        "color":    payload.color,
        "size":     payload.size,
        "stage":    {"$ne": "dispatched"},
    }
    if payload.channel_filter == "online_channel":
        q["source_type"] = "online_channel"
    elif payload.channel_filter == "b2b_client":
        q["source_type"] = {"$in": ["b2b_client", None]}

    jobs = await db.production_jobs.find(q).sort("created_at", 1).to_list(500)
    pending_total = sum(int(j.get("quantity", 0)) - int(j.get("completed_qty", 0) or 0) for j in jobs)

    style = await db.styles.find_one({"_id": ObjectId(payload.style_id)})
    if not style:
        raise HTTPException(404, "Style not found")
    style_code = style.get("code", "")

    produced = int(payload.produced_qty)
    is_short = produced < pending_total
    is_over  = produced > pending_total
    if is_short and not (payload.reason or "").strip():
        raise HTTPException(422, "Short production must include a reason.")

    # BOM check + component deduction ---------------------------------------
    bom_used: list[dict] = []
    if payload.use_components:
        bom = await db.style_component_mapping.find({
            "style_id": ObjectId(payload.style_id), "active": {"$ne": False},
        }).to_list(200)
        if not bom:
            raise HTTPException(
                412,
                {"code": "no_production_card",
                 "message": "No production card (BOM) mapped for this style. "
                            "Create one before consuming components — or set use_components=false to skip.",
                 "style_id": payload.style_id, "style_code": style_code},
            )
        # ---- Pre-flight feasibility check -----------------------------------
        # Compute how much each component this batch would deduct BEFORE we
        # touch component_master, so we can either:
        #   (a) block the run with a `component_shortage` error, or
        #   (b) proceed anyway if the operator explicitly opted in
        #       (`force_negative_stock=True`).
        shortages: list[dict] = []
        deductions: list[tuple[dict, int]] = []
        for b in bom:
            per   = float(b.get("quantity_per_pair", 1) or 1)
            waste = float(b.get("wastage_percent", 0) or 0) / 100.0
            deduct = int(round(produced * per * (1 + waste)))
            if deduct <= 0:
                continue
            comp = await db.component_master.find_one({"_id": ObjectId(b["component_id"])})
            if not comp:
                continue
            current = int(comp.get("current_stock", 0))
            if deduct > current:
                shortages.append({
                    "component_id":   str(comp["_id"]),
                    "component_code": comp.get("component_code"),
                    "component_name": comp.get("component_name"),
                    "needed":         deduct,
                    "available":      current,
                    "shortfall":      deduct - current,
                })
            deductions.append((comp, deduct))
        if shortages and not payload.force_negative_stock:
            raise HTTPException(
                409,
                {"code": "component_shortage",
                 "message": f"{len(shortages)} component(s) would go below zero. Re-submit with force_negative_stock=true to proceed anyway.",
                 "style_code": style_code,
                 "produced":   produced,
                 "shortages":  shortages},
            )
        # Apply the deductions (we already have `comp` fetched above, no double round-trip)
        for comp, deduct in deductions:
            new_stock = int(comp.get("current_stock", 0)) - deduct
            await db.component_master.update_one(
                {"_id": comp["_id"]},
                {"$set": {"current_stock": new_stock, "updated_at": now_iso()},
                 "$push": {"history": {"event": "produce_cell", "at": now_iso(),
                                       "by": u["email"], "style_code": style_code,
                                       "color": payload.color, "size": payload.size,
                                       "pairs": produced, "deducted": deduct,
                                       "new_stock": new_stock}}},
            )
            bom_used.append({
                "component_id":   str(comp["_id"]),
                "component_code": comp.get("component_code"),
                "component_name": comp.get("component_name"),
                "deducted":       deduct,
                "new_stock":      new_stock,
            })

    # Dispatch/complete the pending jobs (or the covered portion) -----------
    remaining_to_cover = min(produced, pending_total)
    covered_job_ids: list[str] = []
    for j in jobs:
        if remaining_to_cover <= 0:
            break
        job_pending = int(j.get("quantity", 0)) - int(j.get("completed_qty", 0) or 0)
        take = min(job_pending, remaining_to_cover)
        new_completed = int(j.get("completed_qty", 0) or 0) + take
        new_stage = payload.dispatch_stage if new_completed >= int(j.get("quantity", 0)) else "packing"
        await db.production_jobs.update_one(
            {"_id": j["_id"]},
            {"$set": {"completed_qty": new_completed, "stage": new_stage, "updated_at": now_iso()},
             "$push": {"history": {"event": "produced", "at": now_iso(), "by": u["email"],
                                   "produced_qty": take, "new_completed": new_completed,
                                   "reason": payload.reason or ""}}},
        )
        covered_job_ids.append(str(j["_id"]))
        remaining_to_cover -= take

    # Short-production log
    shortfall = pending_total - produced if is_short else 0
    if is_short:
        await db.short_production_log.insert_one({
            "style_id":    payload.style_id,
            "style_code":  style_code,
            "color":       payload.color,
            "size":        payload.size,
            "pending_qty": pending_total,
            "produced_qty": produced,
            "shortfall":   shortfall,
            "reason":      payload.reason or "",
            "logged_by":   u["email"],
            "created_at":  now_iso(),
        })

    # Over-production → excess to fg_stock + fg_location_inventory ---------
    excess = produced - pending_total if is_over else 0
    excess_placed_at: Optional[str] = None
    if excess > 0:
        home = await _pick_new_cell_for_style(payload.style_id) or "01-A-01"
        excess_placed_at = home
        # Book raw fg_stock (via _apply_movement so historical trail is consistent)
        try:
            mv = FgStockMovementIn(
                style_id=payload.style_id, color=payload.color, size=payload.size,
                movement_type="production_in", quantity=int(excess),
                reference_type="produce_cell_excess", reference_id="",
                notes=f"Excess of {excess} pairs over pending {pending_total} for {style_code}",
            )
            await _apply_movement(mv, u["email"], skip_location_sync=True)
        except Exception:
            log.exception("Excess fg_stock movement failed")
        # Push into the style's home cell (partial fill if needed)
        cell = await db.warehouse_locations.find_one({"location_code": home})
        capacity = int(cell.get("capacity_pairs", CAPACITY)) if cell else CAPACITY
        room = capacity - int(cell.get("occupied_pairs", 0)) if cell else capacity
        put_here = min(excess, room)
        if put_here > 0:
            await db.fg_location_inventory.update_one(
                {"style_id": ObjectId(payload.style_id), "color": payload.color,
                 "size": payload.size, "location_code": home},
                {"$inc": {"qty": put_here},
                 "$setOnInsert": {"style_code": style_code, "created_at": now_iso(),
                                  "rack": cell.get("rack") if cell else None,
                                  "row":  cell.get("row")  if cell else None,
                                  "cell": cell.get("cell") if cell else None},
                 "$set": {"updated_at": now_iso()}},
                upsert=True,
            )
            new_occ = int(cell.get("occupied_pairs", 0)) + put_here if cell else put_here
            await db.warehouse_locations.update_one(
                {"location_code": home},
                {"$set": {"occupied_pairs":  new_occ,
                          "available_pairs": max(0, capacity - new_occ),
                          "status":          _recompute_status(new_occ, capacity),
                          "updated_at":      now_iso()}},
            )

    return {
        "ok":                  True,
        "style_code":          style_code,
        "color":               payload.color,
        "size":                payload.size,
        "pending_before":      pending_total,
        "produced":            produced,
        "shortfall":           shortfall,
        "excess":              excess,
        "excess_placed_at":    excess_placed_at,
        "jobs_updated":        len(covered_job_ids),
        "bom_components_used": bom_used,
    }


class ProductionCardIn(BaseModel):
    style_id:   str
    components: List[dict]  # [{component_id, quantity_per_pair, wastage_percent?}]


@api.post("/production/production-card")
async def create_production_card(request: Request, payload: ProductionCardIn):
    """Bulk-upsert a style's BOM (production card). Replaces the previous
    active mapping — deactivates old entries and inserts fresh ones. Called by
    the "Create production card" prompt on the pending-list produce drawer
    when a style has no BOM yet.
    """
    u = await get_current_user(request); require_roles("admin", "manager", "production")(u)
    sid_oid = ObjectId(payload.style_id)
    # Deactivate previous mappings for this style
    await db.style_component_mapping.update_many(
        {"style_id": sid_oid, "active": {"$ne": False}},
        {"$set": {"active": False, "updated_at": now_iso()}},
    )
    inserted = []
    for c in payload.components:
        comp_id = c.get("component_id")
        if not comp_id:
            continue
        doc = {
            "style_id":          sid_oid,
            "component_id":      ObjectId(comp_id),
            "quantity_per_pair": float(c.get("quantity_per_pair", 1) or 1),
            "wastage_percent":   float(c.get("wastage_percent", 0) or 0),
            "active":            True,
            "created_at":        now_iso(),
            "updated_at":        now_iso(),
            "created_by":        u["email"],
        }
        r = await db.style_component_mapping.insert_one(doc)
        inserted.append(str(r.inserted_id))
    return {"style_id": payload.style_id, "mapping_ids": inserted, "count": len(inserted)}


@api.get("/production/short-log")
async def list_short_production(request: Request, style_code: Optional[str] = None):
    """Historical short-production log — total pending list of unfulfilled qty."""
    await get_current_user(request)
    q: dict = {}
    if style_code:
        q["style_code"] = style_code
    rows = await db.short_production_log.find(q).sort("created_at", -1).to_list(1000)
    return [stringify(r) for r in rows]


@api.get("/production/style-variants/{sid}")
async def style_variants(sid: str, request: Request):
    """Return every (color, size) pair we've ever seen for this style — used by
    the ad-hoc production matrix to pre-fill rows/cols."""
    await get_current_user(request)
    try:
        sid_oid = ObjectId(sid)
    except Exception:
        raise HTTPException(400, "Invalid style_id")

    colors, sizes = set(), set()
    async for r in db.fg_location_inventory.find({"style_id": sid_oid}, {"color": 1, "size": 1}):
        if r.get("color"): colors.add(str(r["color"]))
        if r.get("size"):  sizes.add(str(r["size"]))
    async for r in db.production_jobs.find({"style_id": sid_oid}, {"color": 1, "size": 1}):
        if r.get("color"): colors.add(str(r["color"]))
        if r.get("size"):  sizes.add(str(r["size"]))
    lc = await db.style_lifecycle.find_one({"style_id": sid})
    if lc:
        for c in (lc.get("planned_colors") or []):
            if c: colors.add(str(c))
        for s in (lc.get("planned_sizes")  or []):
            if s: sizes.add(str(s))

    def _sortsz(s):
        try: return (0, float(s))
        except (ValueError, TypeError):
            return (1, s)

    return {
        "colors": sorted(colors),
        "sizes":  sorted(sizes, key=_sortsz),
    }


@api.get("/production/bom-feasibility/{sid}")
async def bom_feasibility(sid: str, request: Request, pairs: int = 1):
    """Preview whether a run of `pairs` pairs of style `sid` can be produced
    with the current component_master stock (using the style's active BOM).
    Returns: {feasible: bool, components: [{code, name, needed, available, shortfall}], missing_bom: bool}.
    """
    await get_current_user(request)
    if pairs <= 0:
        return {"feasible": True, "components": [], "missing_bom": False, "pairs": 0}
    try:
        oid_v = ObjectId(sid)
    except Exception:
        raise HTTPException(400, "Invalid style_id")
    bom = await db.style_component_mapping.find({
        "style_id": oid_v, "active": {"$ne": False},
    }).to_list(200)
    if not bom:
        return {"feasible": False, "components": [], "missing_bom": True, "pairs": pairs}

    comps = []
    feasible = True
    for b in bom:
        per   = float(b.get("quantity_per_pair", 1) or 1)
        waste = float(b.get("wastage_percent", 0) or 0) / 100.0
        needed = int(round(pairs * per * (1 + waste)))
        cm = await db.component_master.find_one({"_id": ObjectId(b["component_id"])})
        if not cm:
            continue
        available = int(cm.get("current_stock", 0))
        short = max(0, needed - available)
        if short > 0:
            feasible = False
        comps.append({
            "component_id":   str(cm["_id"]),
            "component_code": cm.get("component_code"),
            "component_name": cm.get("component_name"),
            "needed":         needed,
            "available":      available,
            "shortfall":      short,
        })
    return {"feasible": feasible, "components": comps, "missing_bom": False, "pairs": pairs}


# ═══════════════════════════════════════════════════════════════════════
# ══ MARKETPLACE SKU RESOLVER ENGINE ════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# Goal: The ERP stores Style + Color matrix + Size matrix only (NO exploded
# per-size SKUs). Marketplaces embed style+color+size in a single string
# like "CC-058-BR-38" or "FL_AK_002_GO-4". We parse them with a per-market
# regex template, then resolve marketplace style/color codes to ERP style/
# color codes via a mapping table. Size is taken verbatim from the parsed SKU.
# ═══════════════════════════════════════════════════════════════════════

SUPPORTED_MARKETPLACES = ["myntra", "ajio", "flipkart", "nykaa", "amazon", "website", "unicommerce"]

# Default regex patterns — greedy style + last two segments are color and size.
# Users can override via /api/marketplace/parser-templates.
DEFAULT_PARSER_PATTERNS = {
    # Myntra: CC-058-BR-38 → style=CC-058, color=BR, size=38
    "myntra":      r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
    # Ajio: similar
    "ajio":        r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
    # Flipkart: FL_AK_002_GO-4 → style=FL_AK_002, color=GO, size=4
    "flipkart":    r"^(?P<style>.+?)[_-](?P<color>[A-Za-z]{1,4})[_-](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
    # Nykaa
    "nykaa":       r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
    # Amazon (ASIN-style is opaque; assume merchant SKU pattern with style-color-size)
    "amazon":      r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
    # Own website
    "website":     r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
    # Unicommerce middleware
    "unicommerce": r"^(?P<style>.+?)[-_](?P<color>[A-Za-z]{1,4})[-_](?P<size>[0-9]{1,4}(?:\.[0-9]{1,2})?)$",
}


async def _seed_parser_templates():
    """Idempotently seed default parser templates for all supported marketplaces."""
    inserted = 0
    for mp in SUPPORTED_MARKETPLACES:
        exists = await db.sku_parser_templates.find_one({"marketplace": mp})
        if not exists:
            await db.sku_parser_templates.insert_one({
                "marketplace":  mp,
                "template":     "STYLE-COLOR-SIZE",
                "pattern":      DEFAULT_PARSER_PATTERNS[mp],
                "separator":    "-" if mp not in ("flipkart",) else "_",
                "active":       True,
                "example":      {"myntra": "CC-058-BR-38", "flipkart": "FL_AK_002_GO-4"}.get(mp, "STYLE-COLOR-SIZE"),
                "created_at":   now_iso(),
                "updated_at":   now_iso(),
            })
            inserted += 1
    return inserted


async def _get_parser_template(marketplace: str):
    """Return the active parser template for a marketplace, or a fallback default."""
    tmpl = await db.sku_parser_templates.find_one({"marketplace": marketplace, "active": True})
    if tmpl:
        return tmpl
    return {
        "marketplace": marketplace,
        "pattern":     DEFAULT_PARSER_PATTERNS.get(marketplace, DEFAULT_PARSER_PATTERNS["myntra"]),
        "template":    "STYLE-COLOR-SIZE (default)",
    }


def _parse_sku(sku: str, pattern: str):
    """Parse a raw marketplace SKU using a regex with named groups.
    Returns {ok, style, color, size, error}."""
    if not sku:
        return {"ok": False, "error": "empty sku"}
    try:
        m = re.match(pattern, sku.strip())
    except re.error as e:
        return {"ok": False, "error": f"bad regex: {e}"}
    if not m:
        return {"ok": False, "error": f"pattern did not match: {pattern}"}
    d = m.groupdict()
    style = (d.get("style") or "").strip()
    color = (d.get("color") or "").strip()
    size  = (d.get("size")  or "").strip()
    if not (style and color and size):
        return {"ok": False, "error": "missing style/color/size group"}
    return {"ok": True, "style": style, "color": color, "size": size}


async def _resolve_marketplace_sku(marketplace: str, sku: str):
    """Full resolver: parse marketplace SKU → resolve to ERP style+color → verify size.
    Does NOT modify data. Used by /parse-sku, /online-orders/import and the SKU Resolver
    screen. Returns a rich dict with all intermediate values for audit/UI."""
    tmpl = await _get_parser_template(marketplace)
    parsed = _parse_sku(sku, tmpl["pattern"])
    out = {
        "marketplace":     marketplace,
        "raw_sku":         sku,
        "template":        tmpl.get("template"),
        "pattern":         tmpl.get("pattern"),
        "parsed_ok":       parsed["ok"],
        "parsed_style":    parsed.get("style"),
        "parsed_color":    parsed.get("color"),
        "parsed_size":     parsed.get("size"),
        "parse_error":     parsed.get("error"),
        "erp_style_id":    None,
        "erp_style_code":  None,
        "erp_color_code":  None,
        "erp_size":        parsed.get("size"),
        "mapping_id":      None,
        "resolved":        False,
        "resolution_status": "parse_failed" if not parsed["ok"] else "unmapped",
    }
    if not parsed["ok"]:
        return out

    # Lookup marketplace_style_color_mapping (case-insensitive)
    mapping = await db.marketplace_style_color_mapping.find_one({
        "marketplace":            marketplace,
        "marketplace_style_code": {"$regex": f"^{re.escape(parsed['style'])}$", "$options": "i"},
        "marketplace_color_code": {"$regex": f"^{re.escape(parsed['color'])}$", "$options": "i"},
        "active":                 {"$ne": False},
    })
    if not mapping:
        out["resolution_status"] = "unmapped"
        return out

    # Lookup ERP style by code
    style = await db.styles.find_one({
        "code": {"$regex": f"^{re.escape(mapping['erp_style_code'])}$", "$options": "i"},
    })
    if not style:
        out["resolution_status"] = "erp_style_missing"
        out["erp_style_code"] = mapping["erp_style_code"]
        out["erp_color_code"] = mapping["erp_color_code"]
        return out

    out["erp_style_id"]   = str(style["_id"])
    out["erp_style_code"] = style["code"]
    out["erp_color_code"] = mapping["erp_color_code"]
    out["mapping_id"]     = str(mapping["_id"])
    out["resolved"]       = True
    out["resolution_status"] = "resolved"
    return out


async def _log_unresolved_sku(marketplace: str, raw_sku: str, resolution: dict,
                               source: str = "import", order_id: Optional[str] = None):
    """Add or upsert an entry to the unresolved SKU queue for later manual mapping."""
    key = {
        "marketplace":            marketplace,
        "raw_sku":                raw_sku,
        "marketplace_style_code": resolution.get("parsed_style"),
        "marketplace_color_code": resolution.get("parsed_color"),
    }
    now = now_iso()
    upd = {
        "$set": {
            **key,
            "parsed_size":         resolution.get("parsed_size"),
            "resolution_status":   resolution.get("resolution_status"),
            "parse_error":         resolution.get("parse_error"),
            "last_source":         source,
            "last_seen_at":        now,
        },
        "$setOnInsert": {"created_at": now, "occurrences": 0, "status": "open"},
        "$inc":         {"occurrences": 1},
    }
    if order_id:
        upd["$addToSet"] = {"seen_order_ids": order_id}
    await db.unresolved_sku_queue.update_one(key, upd, upsert=True)


# ───────────── Parser Templates endpoints ─────────────

@api.get("/marketplace/parser-templates")
async def list_parser_templates(request: Request):
    await get_current_user(request)
    docs = await db.sku_parser_templates.find({}).sort("marketplace", 1).to_list(50)
    return [stringify(d) for d in docs]


@api.post("/marketplace/parser-templates")
async def upsert_parser_template(request: Request, payload: ParserTemplateIn):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # Validate regex compiles and produces the three named groups
    try:
        cp = re.compile(payload.pattern)
    except re.error as e:
        raise HTTPException(400, f"Invalid regex: {e}")
    if not all(g in cp.groupindex for g in ("style", "color", "size")):
        raise HTTPException(400, "Pattern must contain named groups (?P<style>), (?P<color>), (?P<size>)")
    now = now_iso()
    doc = {
        "marketplace": payload.marketplace,
        "template":    payload.template,
        "pattern":     payload.pattern,
        "separator":   payload.separator,
        "active":      payload.active,
        "example":     payload.example,
        "updated_at":  now,
    }
    await db.sku_parser_templates.update_one(
        {"marketplace": payload.marketplace},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    ret = await db.sku_parser_templates.find_one({"marketplace": payload.marketplace})
    await log_activity("UPDATE", "sku_parser_templates", f"Set parser for {payload.marketplace}", u["email"])
    return stringify(ret)


@api.delete("/marketplace/parser-templates/{tid}")
async def delete_parser_template(request: Request, tid: str):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    try:
        await db.sku_parser_templates.delete_one({"_id": ObjectId(tid)})
    except Exception:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


# ───────────── Style-Color Mapping endpoints ─────────────

@api.get("/marketplace/style-color-mapping")
async def list_marketplace_mappings(
    request: Request,
    marketplace: Optional[str] = None,
    search:      Optional[str] = None,
    active:      Optional[bool] = None,
):
    await get_current_user(request)
    q = {}
    if marketplace: q["marketplace"] = marketplace
    if active is not None: q["active"] = active
    if search:
        q["$or"] = [
            {"marketplace_style_code": {"$regex": search, "$options": "i"}},
            {"marketplace_color_code": {"$regex": search, "$options": "i"}},
            {"erp_style_code":         {"$regex": search, "$options": "i"}},
            {"erp_color_code":         {"$regex": search, "$options": "i"}},
        ]
    docs = await db.marketplace_style_color_mapping.find(q).sort("marketplace", 1).to_list(2000)
    return [stringify(d) for d in docs]


@api.post("/marketplace/style-color-mapping")
async def upsert_marketplace_mapping(request: Request, payload: StyleColorMappingIn):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    # Validate ERP style exists
    style = await db.styles.find_one({
        "code": {"$regex": f"^{re.escape(payload.erp_style_code)}$", "$options": "i"},
    })
    if not style:
        raise HTTPException(400, f"ERP style '{payload.erp_style_code}' not found. Create it first.")

    key = {
        "marketplace":            payload.marketplace,
        "marketplace_style_code": payload.marketplace_style_code,
        "marketplace_color_code": payload.marketplace_color_code,
    }
    now = now_iso()
    doc = {
        **key,
        "erp_style_code": style["code"],
        "erp_style_id":   str(style["_id"]),
        "erp_color_code": payload.erp_color_code,
        "active":         payload.active,
        "updated_at":     now,
        "updated_by":     u["email"],
    }
    await db.marketplace_style_color_mapping.update_one(
        key, {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True,
    )
    ret = await db.marketplace_style_color_mapping.find_one(key)
    await log_activity("UPDATE", "marketplace_style_color_mapping",
                        f"{payload.marketplace}: {payload.marketplace_style_code}/{payload.marketplace_color_code} → {style['code']}/{payload.erp_color_code}",
                        u["email"])
    return stringify(ret)


@api.delete("/marketplace/style-color-mapping/{mid}")
async def delete_marketplace_mapping(request: Request, mid: str):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    try:
        res = await db.marketplace_style_color_mapping.delete_one({"_id": ObjectId(mid)})
    except Exception:
        raise HTTPException(404, "Mapping not found")
    if not res.deleted_count:
        raise HTTPException(404, "Mapping not found")
    return {"ok": True}


# ───────────── Parse / Resolve endpoints ─────────────

@api.post("/marketplace/parse-sku")
async def parse_sku_endpoint(request: Request, payload: SkuResolveIn):
    """One-shot SKU resolver — used by the SKU Resolver screen for manual testing."""
    await get_current_user(request)
    result = await _resolve_marketplace_sku(payload.marketplace, payload.sku)
    return result


@api.post("/marketplace/parse-batch")
async def parse_sku_batch(request: Request, payload: dict):
    """Batch resolve — payload: {marketplace, skus: [str]}"""
    await get_current_user(request)
    marketplace = payload.get("marketplace")
    skus = payload.get("skus") or []
    if not marketplace or not isinstance(skus, list):
        raise HTTPException(400, "Provide {marketplace, skus: [str]}")
    out = []
    for sku in skus[:1000]:
        out.append(await _resolve_marketplace_sku(marketplace, sku))
    return {"count": len(out), "results": out}


# ───────────── Unresolved SKU Queue ─────────────

@api.get("/marketplace/unresolved")
async def list_unresolved(
    request: Request,
    marketplace: Optional[str] = None,
    status: Optional[str] = None,
):
    await get_current_user(request)
    q = {}
    if marketplace: q["marketplace"] = marketplace
    q["status"] = status or "open"
    docs = await db.unresolved_sku_queue.find(q).sort([("occurrences", -1), ("last_seen_at", -1)]).to_list(1000)
    return [stringify(d) for d in docs]


@api.post("/marketplace/unresolved/map")
async def map_and_replay_unresolved(request: Request, payload: UnresolvedMapIn):
    """Add a mapping and mark all matching unresolved queue entries as resolved.
    System 'remembers' by inserting into marketplace_style_color_mapping and
    flipping every open queue row that matches the marketplace_style/color keys."""
    u = await get_current_user(request); require_roles("admin", "manager")(u)

    # Insert (or upsert) the mapping
    style = await db.styles.find_one({
        "code": {"$regex": f"^{re.escape(payload.erp_style_code)}$", "$options": "i"},
    })
    if not style:
        raise HTTPException(400, f"ERP style '{payload.erp_style_code}' not found. Create it first.")

    key = {
        "marketplace":            payload.marketplace,
        "marketplace_style_code": payload.marketplace_style_code,
        "marketplace_color_code": payload.marketplace_color_code,
    }
    now = now_iso()
    await db.marketplace_style_color_mapping.update_one(
        key,
        {"$set": {
            **key,
            "erp_style_code": style["code"],
            "erp_style_id":   str(style["_id"]),
            "erp_color_code": payload.erp_color_code,
            "active":         True,
            "updated_at":     now,
            "updated_by":     u["email"],
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    # Close all queue rows matching this mapping
    close_res = await db.unresolved_sku_queue.update_many(
        {**key, "status": "open"},
        {"$set": {"status": "mapped", "mapped_at": now, "mapped_by": u["email"]}},
    )

    await log_activity("UPDATE", "unresolved_sku_queue",
                        f"Mapped {payload.marketplace}:{payload.marketplace_style_code}/{payload.marketplace_color_code} → {style['code']}/{payload.erp_color_code} (closed {close_res.modified_count} queue rows)",
                        u["email"])
    return {
        "ok":            True,
        "mapping_key":   key,
        "closed_queue_rows": close_res.modified_count,
    }


@api.delete("/marketplace/unresolved/{qid}")
async def dismiss_unresolved(request: Request, qid: str):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    try:
        res = await db.unresolved_sku_queue.update_one(
            {"_id": ObjectId(qid)},
            {"$set": {"status": "dismissed", "dismissed_at": now_iso(), "dismissed_by": u["email"]}},
        )
    except Exception:
        raise HTTPException(404, "Queue item not found")
    if not res.matched_count:
        raise HTTPException(404, "Queue item not found")
    return {"ok": True}


@app.get("/")
async def root():
    return {
        "message": "Welcome to SSK Footwear ERP API! 🚀",
        "docs": "Visit /docs for the API documentation."
    }

app.include_router(api)


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=list(set([
        "http://localhost:3000",
        "https://localhost:3000",
        os.getenv("FRONTEND_URL", "http://localhost:3000")
    ])),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

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
    await db.production_jobs.create_index("po_id")
    await db.vendors.create_index("name")

    # SKU map indexes: unique compound on (source_type, source_name, external_sku) + style lookup
    try:
        await db.sku_map.create_index(
            [("source_type", 1), ("source_name", 1), ("external_sku", 1)],
            unique=True, name="sku_map_unique"
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
            [("marketplace", 1), ("marketplace_style_code", 1), ("marketplace_color_code", 1)],
            unique=True, name="mp_scm_unique",
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
