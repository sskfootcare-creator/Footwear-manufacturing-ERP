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
from typing import List, Optional, Literal, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, field_validator
from pydantic_core import PydanticCustomError
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

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
from packing_list import build_default_packing_list, build_from_template
from pdf_procurement import build_material_requirement
from pdf_card import build_production_card
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from io import BytesIO
import uuid
import boto3

# ---------- DB & app ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="SSK Footcare ERP")
api = APIRouter(prefix="/api")

# ---------- Object Storage / Local Uploads ----------
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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

@api.post("/upload/image")
async def upload_image(file: UploadFile = File(...), request: Request = None):
    u = await get_current_user(request)
    require_roles("admin", "manager")(u)
    
    ext = file.filename.split('.')[-1].lower() if '.' in file.filename else 'png'
    if ext not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
        raise HTTPException(400, "Invalid image format")
        
    filename = f"{uuid.uuid4().hex}.{ext}"
    content = await file.read()
    
    if s3_client:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"images/{filename}",
            Body=content,
            ContentType=file.content_type
        )
        if S3_ENDPOINT:
            url = f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/images/{filename}"
        else:
            url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/images/{filename}"
        return {"url": url}
    else:
        filepath = os.path.join("uploads", filename)
        with open(filepath, "wb") as f:
            f.write(content)
        base = str(request.base_url).rstrip('/')
        return {"url": f"{base}/uploads/{filename}"}


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


# ---------- Pydantic models ----------
Role = Literal["admin", "manager", "production", "sales"]

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "production"

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if v is not None and len(v) < 8:
            raise PydanticCustomError(
                "string_too_short",
                "Password must be at least 8 characters long."
            )
        return v

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Role] = None
    active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 8:
            raise PydanticCustomError(
                "string_too_short",
                "Password must be at least 8 characters long."
            )
        return v

class MaterialIn(BaseModel):
    code: str
    name: str
    category: Literal["upper", "sole", "lining", "accessory", "consumable", "packing", "other"]
    unit: str
    rate: float
    reorder_level: float = 0
    notes: Optional[str] = ""
    preferred_vendor_id: Optional[str] = ""

class BomItem(BaseModel):
    material_id: str
    material_name: str
    material_code: str
    unit: str
    rate: float
    quantity: float
    yield_per_unit: float = 1  # pairs produced per 1 unit of material (e.g., 10 uppers per meter)
    waste_pct: float = 0
    section: str = "Other"
    component: Optional[str] = None  # "upper" | "bottom" | "sole" (auto-classified or manual)

class LaborItem(BaseModel):
    name: str
    rate: float  # per pair

class StyleIn(BaseModel):
    code: str
    name: str
    category: Optional[str] = "Footwear"
    image_url: Optional[str] = ""
    description: Optional[str] = ""
    base_size: Optional[str] = "7"
    bom: List[BomItem] = []
    labor: List[LaborItem] = []
    overhead_pct: float = 0
    packing_cost: float = 0
    margin_pct: float = 25
    gst_pct: float = 5
    status: Optional[str] = "inactive"

class POLineItem(BaseModel):
    style_code: str
    description: Optional[str] = ""
    color: Optional[str] = ""
    size: Optional[str] = ""
    hsn_code: Optional[str] = ""
    quantity: int
    unit_price: float
    amount: float

class POIn(BaseModel):
    po_number: str
    po_date: str  # ISO
    client_name: str
    client_address: Optional[str] = ""
    billing_address: Optional[str] = ""
    shipping_address: Optional[str] = ""
    client_gstin: Optional[str] = ""
    client_state: Optional[str] = ""
    client_state_code: Optional[str] = ""
    delivery_date: Optional[str] = ""
    payment_terms: Optional[str] = ""
    currency: str = "INR"
    line_items: List[POLineItem]
    subtotal: float = 0
    cgst_rate: float = 0
    cgst_amount: float = 0
    sgst_rate: float = 0
    sgst_amount: float = 0
    igst_rate: float = 0
    igst_amount: float = 0
    grand_total: float = 0
    total_quantity: int = 0
    notes: Optional[str] = ""

PRODUCTION_STAGES = [
    "procurement", "cutting", "folding", "attachment",
    "stitching", "lasting", "sole_pasting", "finishing", "dispatched",
]

class ProductionStageUpdate(BaseModel):
    stage: Literal["procurement", "cutting", "folding", "attachment",
                   "stitching", "lasting", "sole_pasting", "finishing", "dispatched"]
    completed_qty: Optional[int] = None
    rejected_qty: Optional[int] = None
    qc_pass: Optional[bool] = None
    notes: Optional[str] = ""
    confirm_skip: bool = False

class ComponentUpdate(BaseModel):
    upper_done: Optional[bool] = None
    bottom_done: Optional[bool] = None
    sole_done: Optional[bool] = None
    notes: Optional[str] = ""

class WorkerIn(BaseModel):
    name: str
    phone: Optional[str] = ""
    skill: str = "general"
    rate_per_pair: float = 0
    active: bool = True
    notes: Optional[str] = ""
    bonus_pct: float = 0
    target_cycle_days: float = 0

class AssignmentUpdate(BaseModel):
    role: str  # cutting | upper | bottom | sole | stitching | lasting | sole_pasting | finishing
    worker_id: Optional[str] = None  # null = unassign
    worker_name: Optional[str] = None  # denormalised for quick display
    rate_per_pair: Optional[float] = None  # negotiated rate for THIS style/job (overrides worker default)

class BulkAssign(BaseModel):
    job_ids: List[str]
    role: str
    worker_id: Optional[str] = None
    rate_per_pair: Optional[float] = None

class AdvanceIn(BaseModel):
    worker_id: str
    amount: float
    date: Optional[str] = ""
    notes: Optional[str] = ""
    txn_type: Literal["advance", "payment", "bonus", "adjustment"] = "advance"
    # advance = loan upfront, payment = wage paid out, bonus = bonus credit (positive), adjustment = manual correction

class WorkerIn(BaseModel):
    name: str
    phone: Optional[str] = ""
    skill: str = "general"
    rate_per_pair: float = 0
    active: bool = True
    notes: Optional[str] = ""
    # Productivity bonus config
    bonus_pct: float = 0  # e.g., 10 = 10% bonus on qualifying jobs
    target_cycle_days: float = 0  # threshold in days; 0 = bonus disabled



class QuantityUpdate(BaseModel):
    quantity: Optional[int] = None
    completed_qty: Optional[int] = None
    rejected_qty: Optional[int] = None
    reason: Optional[str] = ""

class InventoryMovement(BaseModel):
    material_id: str
    type: Literal["in", "out", "adjustment"]  # in = stock-in (purchase), out = consumption, adjustment = correction
    quantity: float
    rate: Optional[float] = None  # unit rate at this movement (purchase price)
    party: Optional[str] = ""  # supplier name for IN, job/po reference for OUT
    job_id: Optional[str] = None  # if linked to a production job
    notes: Optional[str] = ""
    date: Optional[str] = ""  # ISO date

class InvoiceGenerate(BaseModel):
    po_id: str
    job_ids: Optional[List[str]] = None  # if None, full PO; otherwise dispatched-only items
    transport_mode: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    supply_date: Optional[str] = ""


class PackingListGenerate(BaseModel):
    po_id: str
    job_ids: Optional[List[str]] = None
    template_id: Optional[str] = None  # use a saved per-client template
    carton_dim: Optional[str] = "60x50x30 CMS"
    pcs_per_box: Optional[int] = 20
    net_wt_per_carton: Optional[float] = 10.8
    gross_wt_per_carton: Optional[float] = 12.0
    # Manual / extra metadata captured at generation time
    dispatch_date: Optional[str] = ""
    transporter: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    driver_name: Optional[str] = ""
    driver_phone: Optional[str] = ""
    site_code: Optional[str] = ""
    destination: Optional[str] = ""
    port: Optional[str] = ""
    notes: Optional[str] = ""


class MergedPackingListGenerate(BaseModel):
    job_ids: List[str]  # jobs across one or more POs (must share the same client for merging)
    template_id: Optional[str] = None
    carton_dim: Optional[str] = "60x50x30 CMS"
    pcs_per_box: Optional[int] = 20
    net_wt_per_carton: Optional[float] = 10.8
    gross_wt_per_carton: Optional[float] = 12.0
    sectioned: Optional[bool] = False  # if True, emit one section per PO with headers
    dispatch_date: Optional[str] = ""
    transporter: Optional[str] = ""
    vehicle_no: Optional[str] = ""
    driver_name: Optional[str] = ""
    driver_phone: Optional[str] = ""
    site_code: Optional[str] = ""
    destination: Optional[str] = ""
    port: Optional[str] = ""
    notes: Optional[str] = ""


class PackingTemplateIn(BaseModel):
    client_name: str
    name: str   # human-friendly label
    aliases: Optional[List[str]] = None  # client-name keywords this template auto-matches
    file_b64: str  # base64-encoded xlsx file contents


# ----- Accounts Receivable / Ledger models -----
DEFAULT_CREDIT_DAYS = 45
PAYMENT_MODES = ["Bank Transfer", "RTGS", "NEFT", "Cheque", "UPI", "Cash", "Adjustment"]


class GRNLineItem(BaseModel):
    style_code: str = ""
    description: str = ""
    color: str = ""
    size: str = ""
    dispatched_qty: int = 0
    received_qty: int = 0
    accepted_qty: int = 0
    rejected_qty: int = 0
    rejection_reason: str = ""


class GRNIn(BaseModel):
    invoice_id: str
    grn_date: str  # YYYY-MM-DD
    received_date: Optional[str] = ""
    client_reference: Optional[str] = ""  # client's GRN ref / email subject
    notes: Optional[str] = ""
    line_items: List[GRNLineItem]


class PaymentIn(BaseModel):
    invoice_ids: List[str]  # can pay multiple invoices in one go
    amount: float
    payment_date: str  # YYYY-MM-DD
    mode: Literal["Bank Transfer", "RTGS", "NEFT", "Cheque", "UPI", "Cash", "Adjustment"]
    reference: Optional[str] = ""  # UTR / Cheque no / Txn id
    bank: Optional[str] = ""
    notes: Optional[str] = ""

# ----- Accounts Payable / Vendor models -----
class VendorIn(BaseModel):
    name: str
    gstin: Optional[str] = ""
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""
    payment_terms_days: int = 30
    active: bool = True
    notes: Optional[str] = ""


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms_days: Optional[int] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


# ----- Accounts Payable / Vendor Purchase Order models -----
class VendorPOLineItem(BaseModel):
    material_id: str
    quantity: float
    rate: float
    amount: float
    received_quantity: float = 0.0


class VendorPOIn(BaseModel):
    vendor_id: str
    line_items: List[VendorPOLineItem]
    status: Literal["draft", "sent", "partially_received", "received", "cancelled"] = "draft"
    expected_delivery_date: Optional[str] = ""
    notes: Optional[str] = ""


class VendorPOUpdate(BaseModel):
    vendor_id: Optional[str] = None
    line_items: Optional[List[VendorPOLineItem]] = None
    status: Optional[Literal["draft", "sent", "partially_received", "received", "cancelled"]] = None
    expected_delivery_date: Optional[str] = None
    notes: Optional[str] = None


class VendorPOReceiveItem(BaseModel):
    material_id: str
    quantity: float


class VendorPOReceiveIn(BaseModel):
    receipt_id: str
    items: List[VendorPOReceiveItem]


class DefectIn(BaseModel):
    po_number: str
    article: Optional[str] = ""
    stage: str
    defect_type: str
    description: str
    defective_qty: int
    root_cause: Optional[str] = ""
    responsible_dept: Optional[str] = ""
    corrective_action: Optional[str] = ""
    rework_qty: int = 0
    rework_completed: bool = False
    final_rejection_qty: int = 0
    cost: float = 0
    status: Literal["open", "in_progress", "closed"] = "open"


class StageDurationsIn(BaseModel):
    """Default ETA hours per production stage. Used to compute deadlines & overdue alerts."""
    hours: Dict[str, float]


# ---------- SKU Map models ----------
SourceType = Literal["b2b_client", "online_channel"]
OnlineChannel = Literal["myntra", "flipkart", "nykaa", "website"]

class SkuMapIn(BaseModel):
    style_id: str                                   # ObjectId string ref to db.styles
    source_type: SourceType
    source_name: str                                # client_name (b2b) or channel slug (online)
    external_sku: str
    external_style_name: Optional[str] = ""
    color_map: Optional[Dict[str, str]] = {}        # e.g. {"Tan": "TAN01"}
    size_map:  Optional[Dict[str, str]] = {}        # e.g. {"8 UK": "8"}

class SkuMapUpdate(BaseModel):
    external_style_name: Optional[str] = None
    color_map: Optional[Dict[str, str]] = None
    size_map:  Optional[Dict[str, str]] = None


class FgInventoryIn(BaseModel):
    style_id: str
    color: str
    size: str
    ready_stock_qty: Optional[int] = 0
    reserved_qty: Optional[int] = 0
    in_transit_qty: Optional[int] = 0
    return_qty: Optional[int] = 0
    damaged_qty: Optional[int] = 0
    liquidation_qty: Optional[int] = 0
    min_stock_level: Optional[int] = 25

class FgInventoryUpdate(BaseModel):
    ready_stock_qty: Optional[int] = None
    reserved_qty: Optional[int] = None
    in_transit_qty: Optional[int] = None
    return_qty: Optional[int] = None
    damaged_qty: Optional[int] = None
    liquidation_qty: Optional[int] = None
    min_stock_level: Optional[int] = None

class StockReservation(BaseModel):
    style_id: str
    color: str
    size: str
    quantity: int

class StockRelease(BaseModel):
    style_id: str
    color: str
    size: str
    quantity: int
    release_type: Literal["ship", "cancel"]


# ----- Phase 2 : FG Stock Movements ledger -----
MovementType = Literal[
    "production_in", "reserved", "unreserved", "dispatched",
    "return_in", "return_restocked", "return_damaged",
    "liquidation_out", "adjustment"
]

ReferenceType = Literal["job", "online_order", "return", "manual"]

# Field to adjust when movement_type == "adjustment" (positive or negative delta)
AdjustmentField = Literal[
    "ready_stock_qty", "reserved_qty", "in_transit_qty",
    "return_qty", "damaged_qty", "liquidation_qty"
]


class FgStockMovementIn(BaseModel):
    style_id: str
    color: str
    size: str
    movement_type: MovementType
    quantity: int  # always POSITIVE; sign is derived from movement_type. For "adjustment" a negative value is allowed.
    reference_type: ReferenceType = "manual"
    reference_id: Optional[str] = ""
    notes: Optional[str] = ""
    # For movement_type == "adjustment"
    adjustment_field: Optional[AdjustmentField] = None
    # For movement_type == "reserved" / "unreserved" : online_order line item id used to log inventory_reservations
    online_order_id: Optional[str] = None


class InventoryReservationIn(BaseModel):
    style_id: str
    color: str
    size: str
    qty: int
    online_order_id: str


# Sensible factory defaults (in hours)
DEFAULT_STAGE_HOURS = {
    "procurement": 24, "cutting": 24, "folding": 8, "attachment": 8,
    "stitching": 48, "lasting": 24, "sole_pasting": 12, "finishing": 12,
    "dispatched": 0,
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
    client_ip = request.client.host if request.client else "unknown"
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
    refresh_token = request.cookies.get("refresh_token")
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


@api.post("/sku-map/bulk")
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


async def _apply_movement(payload: "FgStockMovementIn", user_email: str):
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

    # Stringify movement doc for JSON response
    mv_out = stringify(mv_doc)
    return {"inventory": updated, "movement": mv_out}


@api.post("/fg-inventory/movements")
async def create_fg_movement(request: Request, payload: FgStockMovementIn):
    """Single write path to fg_inventory. Creates a movement ledger row and atomically
    updates the inventory row. Auto-creates the fg_inventory row at zero if none exists.
    Blocks any movement that would push a quantity below zero.
    """
    u = await get_current_user(request)
    require_roles("admin", "manager", "production")(u)
    return await _apply_movement(payload, u["email"])


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

    return {
        "style": {
            "id":    str(style["_id"]),
            "code":  style["code"],
            "name":  style.get("name", ""),
            "image_url": style.get("image_url", ""),
        },
        "rows":               out_rows,
        "colors":             sorted(colors),
        "sizes":              sorted(sizes),
        "active_reservations": active_reservations,
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
async def list_styles(request: Request, status: Optional[str] = None, search: Optional[str] = None):
    await get_current_user(request)
    query = {}
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
    out = []
    for d in docs:
        d = stringify(d)
        d["costing"] = compute_style_costing(d)
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

@api.post("/styles/bulk/preview")
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
            "image_url": str(row.get("image_url", "")).strip() if pd.notna(row.get("image_url")) else "",
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
                "image_url": row.get("image_url", ""),
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
    code = payload.code.strip()
    if await db.styles.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}):
        raise HTTPException(status_code=409, detail=f"Style code '{code}' already exists")
    payload.code = code
    doc = payload.model_dump()
    doc["status"] = "active" if len(doc.get("bom", [])) > 0 else "inactive"
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    try:
        res = await db.styles.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Style code '{code}' already exists")
    doc.pop("_id", None)
    doc["id"] = str(res.inserted_id)
    doc["costing"] = compute_style_costing(doc)
    return doc

@api.patch("/styles/{sid}")
async def update_style(sid: str, payload: StyleIn, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    code = payload.code.strip()
    if await db.styles.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "_id": {"$ne": oid(sid)}}):
        raise HTTPException(status_code=409, detail=f"Style code '{code}' already exists")
    payload.code = code
    update = payload.model_dump()
    update["status"] = "active" if len(update.get("bom", [])) > 0 else "inactive"
    update["updated_at"] = now_iso()
    try:
        await db.styles.update_one({"_id": oid(sid)}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Style code '{code}' already exists")
    d = stringify(await db.styles.find_one({"_id": oid(sid)}))
    d["costing"] = compute_style_costing(d)
    return d

@api.delete("/styles/{sid}")
async def delete_style(sid: str, request: Request):
    u = await get_current_user(request); require_roles("admin", "manager")(u)
    await db.styles.delete_one({"_id": oid(sid)})
    return {"ok": True}


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
                if not val:
                    return val
                if val in m:
                    return m[val]
                val_lower = val.lower()
                for k, v in m.items():
                    if k.lower() == val_lower:
                        return v
                return val   # pass through unchanged when key not in map

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

    Pass 1 — exact case-insensitive match against styles.code (unchanged behaviour).
    Pass 2 — for any line item still unresolved, try the sku_map cross-reference using
             (client_name, external_sku). If resolved, the line item's style_code is
             replaced with the internal code; no auto-create placeholder is created.
    Pass 3 — codes that are still unresolved after both passes are auto-created as
             placeholder inactive styles (original behaviour, preserved for backward compat).
    """
    all_styles = await db.styles.find({}, {"code": 1}).to_list(10000)
    existing_codes_upper = {s["code"].strip().upper(): s["code"] for s in all_styles}

    # Pass 1 — exact match
    unresolved = []          # (index, original external code)
    for i, li in enumerate(payload.line_items):
        ext_code = li.style_code.strip()
        if ext_code.upper() in existing_codes_upper:
            li.style_code = existing_codes_upper[ext_code.upper()]   # normalise casing
        else:
            unresolved.append((i, ext_code))

    # Pass 2 — resolve_style() sku_map lookup
    still_missing = []
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
            # translate color/size in-place if the mapping provided translations
            if result["color"] and result["color"] != (li_obj.color or ""):
                payload.line_items[i].color = result["color"]
            if result["size"] and result["size"] != str(li_obj.size or ""):
                payload.line_items[i].size = result["size"]
            # stash resolution metadata for create_po() to pick up
            payload.line_items[i].__dict__["_sku_map_meta"] = {
                "mapped_from_sku": result["mapped_from_sku"],
                "mapping_id":      result["mapping_id"],
            }
        elif result["matched"] and result["match_via"] == "style_code":
            # resolve_style fell back to a direct styles.code match — treat as matched,
            # no auto-create needed, but also no sku_map metadata.
            payload.line_items[i].style_code = result["style_code"]
        else:
            still_missing.append(ext_code)

    # Pass 3 — auto-create placeholder styles for anything still unresolved
    if still_missing:
        new_styles = []
        now = now_iso()
        for code in set(still_missing):
            new_styles.append({
                "code": code,
                "name": f"Auto-created Style {code}",
                "category": "Footwear",
                "image_url": "",
                "description": "Auto-created from PO upload",
                "base_size": "7",
                "bom": [],
                "labor": [
                    {"name": "Cutting", "rate": 6},
                    {"name": "Fitting", "rate": 12},
                    {"name": "Pasting", "rate": 8},
                    {"name": "Finishing", "rate": 6},
                    {"name": "Packing", "rate": 3}
                ],
                "overhead_pct": 8,
                "packing_cost": 12,
                "margin_pct": 25,
                "gst_pct": 5,
                "status": "inactive",
                "created_at": now,
                "updated_at": now
            })
        if new_styles:
            await db.styles.insert_many(new_styles)

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
            "po_id": doc["id"],
            "po_number": doc["po_number"],
            "client_name": doc["client_name"],
            "style_code": li["style_code"],
            "style_id": style_id,
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

@api.post("/pos/extract")
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


@api.get("/pos/{pid}/invoice.pdf")
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


@api.post("/invoices/job")
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
        await db.jobs.update_many(
            {"_id": {"$in": [oid(j) for j in job_ids]}},
            {"$unset": {"invoice_generated_at": ""}}
        )
    
    # Delete payments for this invoice
    await db.payments.delete_many({"invoice_id": id})
    
    # Delete the invoice
    await db.invoices.delete_one({"_id": oid(id)})
    return {"ok": True}


@api.post("/invoices/merged")
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
    await _flag_jobs(job_ids_all, "invoice_generated_at")
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice_no}.pdf"',
            "X-Invoice-Id": str(res_m.inserted_id),
        },
    )


@api.get("/pos/{pid}/challan.pdf")
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


@api.get("/invoices/{iid}/file")
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


async def _generate_packing_bytes(payload_po: dict, options: dict, template_id: Optional[str]) -> bytes:
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
        return build_from_template(tpl_bytes, payload_po, options)
    return build_default_packing_list(payload_po, options)


@api.post("/packing-lists/job")
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
    xlsx_bytes = await _generate_packing_bytes(payload_po, options, payload.template_id)

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


@api.post("/packing-lists/merged")
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

    # All POs must share the same client for a coherent packing list.
    clients = {p.get("client_name", "").strip() for p in po_docs}
    if len(clients) > 1:
        raise HTTPException(400, f"Cannot merge POs of different clients: {clients}")
    parent = po_docs[0]
    po_numbers = [p.get("po_number", "") for p in po_docs]

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
    xlsx_bytes = await _generate_packing_bytes(payload_po, options, payload.template_id)

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


@api.get("/packing-lists/{plid}/file")
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

@api.post("/online-orders/import")
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
    if channel not in ["myntra", "flipkart", "nykaa", "website"]:
        raise HTTPException(400, f"Unknown channel '{channel}'. Must be: myntra, flipkart, nykaa, website")

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

        # ── resolve_style: online_channel pass ──────────────────────────────
        result = await resolve_style(
            source_type="online_channel",
            source_name=channel,
            external_sku=style_sku,
            external_color=ext_color or None,
            external_size=ext_size  or None,
        )

        if not result["matched"]:
            unresolved += 1
            errors.append({
                "row":       idx,
                "order_id":  order_id,
                "style_sku": style_sku,
                "reason":    f"No sku_map entry and no styles.code match for '{style_sku}' on channel '{channel}'. "
                             f"Add a mapping at /sku-map before re-importing.",
            })
            continue

        entered  = now_iso()
        deadline = _compute_deadline(entered, durations.get("procurement", 24))

        match_status = result["match_via"]   # "sku_map" or "style_code"
        if match_status == "sku_map":
            match_status = "mapped"
        else:
            match_status = "matched"

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
            **({"mapped_from_sku": result["mapped_from_sku"], "sku_mapping_id": result["mapping_id"]} if result["match_via"] == "sku_map" else {}),

            # Line details
            "description":        description,
            "color":              result["color"],
            "size":               result["size"],
            "quantity":           quantity,
            "unit_price":         unit_price,
            "amount":             round(unit_price * quantity, 2),
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
                         "notes": f"Auto-created from {channel} CSV import"}],
        }
        jobs_to_insert.append(job)
        imported += 1

    if jobs_to_insert:
        await db.production_jobs.insert_many(jobs_to_insert)

    await log_activity(
        "IMPORT", "online_orders",
        f"{channel.capitalize()} CSV import: {imported} jobs created, {unresolved} unresolved, {len(errors)-unresolved} errors",
        u["email"],
    )
    return {
        "channel":    channel,
        "imported":   imported,
        "unresolved": unresolved,
        "errors":     errors,
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
async def list_jobs(request: Request, include_archived: bool = False):
    await get_current_user(request)
    q: dict = {}
    if not include_archived:
        # Hide jobs that have both invoice + packing list generated
        q = {"archived": {"$ne": True}}
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
    await db.production_jobs.update_many(
        {"_id": {"$in": obj_ids}},
        {"$set": {field: now}},
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





@api.post("/production/card.pdf")
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

    await seed_admin(db)
    try:
        profile = await db.settings.find_one({"_id": "company_profile"})
        if profile:
            from pdf_docs import update_company_profile
            update_company_profile(profile)
            log.info("Loaded custom company profile from DB.")
    except Exception as e:
        log.warning(f"Could not load company profile from DB: {e}")
    log.info("Startup complete; admin seeded.")

@app.on_event("shutdown")
async def on_shutdown():
    client.close()
