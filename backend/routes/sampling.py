"""Sample Development & Tracking System Routes.

Footwear Product Development (PD) pipeline:
- Isolated sample inspiration photo uploads (kept distinct from Style Master and Material photos)
- Automatic sequential temporary style code generation (SMP-YYYY-XXXX)
- Multi-pillar technical specifications (Upper, Insole/Socks, Sole/Heel)
- State transitions (Draft -> In Sampling -> Sample Ready -> Approved / Rejected -> Transferred to Style Master)
- 1-Click transfer to Style Master importing all specs into BOM lines and Labor operations
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Query
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth import get_current_user_factory, require_roles
from models.sampling import (
    SampleCreateIn,
    SampleUpdateIn,
    SamplePhoto,
    TransferToStyleIn,
    SampleStatus,
)
from services.upload_validator import (
    validate_uploaded_file,
    sanitize_filename,
    ALLOWED_IMAGE_EXTENSIONS,
)
from constants import MAX_IMAGE_UPLOAD_BYTES

sampling_router = APIRouter(prefix="/api/samples", tags=["Sample Development & Tracking"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(val: str) -> ObjectId:
    try:
        return ObjectId(val)
    except Exception:
        raise HTTPException(400, f"Invalid object ID format: '{val}'")


def stringify(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
        elif isinstance(v, dict):
            d[k] = stringify(v)
        elif isinstance(v, list):
            d[k] = [stringify(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in v]
    return d


def get_db(request: Optional[Request] = None):
    if request and hasattr(request, "app"):
        mongodb = getattr(request.app, "mongodb", None)
        if mongodb is not None:
            return mongodb
    import server
    return getattr(server, "db", None)


async def _get_user(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return user
    import server
    if getattr(server, "get_current_user", None) is not None:
        return await server.get_current_user(request)
    fn = await get_current_user_factory(get_db(request))
    return await fn(request)


async def _next_sample_code(db) -> str:
    """Atomically increment the sample code counter for the current year."""
    year = datetime.now(timezone.utc).year
    counter_id = f"sample_code_{year}"
    doc = await db.counters.find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int(doc.get("seq", 1))
    return f"SMP-{year}-{seq:04d}"


# ─────────────────────────────────────────────────────────────────────────────
# 1. SAMPLE LIST & CRUD
# ─────────────────────────────────────────────────────────────────────────────

@sampling_router.get("")
async def list_samples(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: draft, in_sampling, sample_ready, approved, rejected, transferred_to_style"),
    profile: Optional[str] = Query(None, description="Filter by footwear profile: flat, heeled"),
    q: Optional[str] = Query(None, description="Search term for code, name, season, karigar"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    """List sample development records with filtering and pagination."""
    await _get_user(request)
    db = get_db(request)

    query: Dict[str, Any] = {}
    if status and status.strip():
        query["status"] = status.strip()
    if profile and profile.strip():
        query["profile"] = profile.strip()
    if q and q.strip():
        regex = re.compile(re.escape(q.strip()), re.IGNORECASE)
        query["$or"] = [
            {"temp_code": regex},
            {"sample_name": regex},
            {"season": regex},
            {"assigned_karigar_name": regex},
            {"transferred_style_code": regex},
        ]

    total = await db.samples.count_documents(query)
    skip = (page - 1) * limit
    cursor = db.samples.find(query).sort("created_at", -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        items.append(stringify(doc))

    # Compute summary counts by status
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    status_counts = {}
    async for agg in db.samples.aggregate(pipeline):
        status_counts[agg["_id"]] = agg["count"]

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "status_counts": status_counts,
    }


@sampling_router.get("/helpers/materials-and-karigars")
async def get_sampling_helpers(request: Request):
    """Retrieve dropdown options for materials and karigars for sample development."""
    await _get_user(request)
    db = get_db(request)

    materials_cursor = db.materials.find(
        {},
        {"_id": 1, "code": 1, "name": 1, "category": 1, "rate": 1, "unit": 1, "color": 1}
    ).sort("name", 1)

    materials = []
    async for m in materials_cursor:
        materials.append(stringify(m))

    workers_cursor = db.workers.find(
        {"active": {"$ne": False}},
        {"_id": 1, "name": 1, "role": 1, "phone": 1, "skills": 1}
    ).sort("name", 1)

    workers = []
    async for w in workers_cursor:
        workers.append(stringify(w))

    return {
        "materials": materials,
        "workers": workers,
    }


@sampling_router.get("/{sid}")
async def get_sample(sid: str, request: Request):
    """Get single sample development record with all technical specifications."""
    await _get_user(request)
    db = get_db(request)
    doc = await db.samples.find_one({"_id": oid(sid)})
    if not doc:
        raise HTTPException(404, "Sample not found")
    return stringify(doc)


@sampling_router.post("")
async def create_sample(payload: SampleCreateIn, request: Request):
    """Create a new sample with auto-generated temporary style code."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    temp_code = await _next_sample_code(db)
    doc = payload.model_dump()
    doc["temp_code"] = temp_code
    doc["status"] = "draft"
    doc["created_by"] = u.get("email", "")
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    doc["transferred_style_id"] = None
    doc["transferred_style_code"] = None
    doc["transferred_at"] = None

    res = await db.samples.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@sampling_router.patch("/{sid}")
async def update_sample(sid: str, payload: SampleUpdateIn, request: Request):
    """Update sample details, specifications, or status."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        return stringify(sample)

    update_data["updated_at"] = now_iso()
    await db.samples.update_one({"_id": oid(sid)}, {"$set": update_data})
    updated = await db.samples.find_one({"_id": oid(sid)})
    return stringify(updated)


@sampling_router.delete("/{sid}")
async def delete_sample(sid: str, request: Request):
    """Delete or discard a sample that is not in production."""
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    if sample.get("status") == "transferred_to_style":
        raise HTTPException(400, "Cannot delete sample that has already been transferred to Style Master")

    await db.samples.delete_one({"_id": oid(sid)})
    return {"ok": True, "message": f"Sample {sample.get('temp_code')} deleted / discarded successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. SEPARATE INSPIRATION PHOTO UPLOADS (BATCH & MULTIPLE FILES SUPPORT)
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_upload_files(request: Request, files_arg: Any = None, file_arg: Any = None) -> List[Any]:
    """Helper to flexibly extract uploaded files from multipart form or kwargs without 422 list validation errors."""
    all_files = []
    # 1. From direct kwargs (tests / direct function calls)
    if files_arg is not None and not str(type(files_arg)).endswith("params.File'>"):
        if isinstance(files_arg, list):
            for item in files_arg:
                if hasattr(item, "filename") and getattr(item, "filename", None):
                    all_files.append(item)
        elif hasattr(files_arg, "filename") and getattr(files_arg, "filename", None):
            all_files.append(files_arg)
    if file_arg is not None and not str(type(file_arg)).endswith("params.File'>"):
        if hasattr(file_arg, "filename") and getattr(file_arg, "filename", None):
            all_files.append(file_arg)

    # 2. From multipart request form (browser / Axios / curl)
    try:
        form = await request.form()
        for key in ("files", "file", "photos", "photo", "image", "images"):
            for item in form.getlist(key):
                if hasattr(item, "filename") and getattr(item, "filename", None) and item not in all_files:
                    all_files.append(item)
        if not all_files:
            for item in form.values():
                if hasattr(item, "filename") and getattr(item, "filename", None) and item not in all_files:
                    all_files.append(item)
    except Exception:
        pass

    return all_files


@sampling_router.post("/upload-photos")
async def upload_multiple_sample_photos(
    request: Request,
    sample_id: Optional[str] = None,
    files: Optional[Any] = None,
    file: Optional[Any] = None,
):
    """Upload multiple sample inspiration photos in a single batch.
    Isolated storage path under uploads/samples_inspiration/ with category='sample_inspiration'.
    Can be called during sample creation (staging) or attached to an existing sample.
    """
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    all_files = await _extract_upload_files(request, files_arg=files, file_arg=file)
    if not all_files:
        raise HTTPException(400, "No valid image files provided in upload request")

    form = None
    try:
        form = await request.form()
    except Exception:
        pass

    target_sample_id = sample_id or request.query_params.get("sample_id") or (form.get("sample_id") if form else None)
    folder_id = target_sample_id or os.urandom(8).hex()
    sample_dir = os.path.join("uploads", "samples_inspiration", folder_id)
    os.makedirs(sample_dir, exist_ok=True)

    uploaded_photos = []
    last_err = None
    for idx, f_item in enumerate(all_files):
        try:
            content, safe_name = await validate_uploaded_file(
                file=f_item,
                allowed_extensions={"jpg", "jpeg", "png", "webp"},
                max_bytes=MAX_IMAGE_UPLOAD_BYTES,
                category_label="sample_inspiration_photo",
            )
            unique_name = f"{os.urandom(4).hex()}_{safe_name}"
            fpath = os.path.join(sample_dir, unique_name)
            with open(fpath, "wb") as f:
                f.write(content)

            url = f"/api/uploads/samples_inspiration/{folder_id}/{unique_name}"
            photo_id = os.urandom(6).hex()
            photo_entry = {
                "photo_id": photo_id,
                "url": url,
                "thumbnail_url": url,
                "caption": "",
                "is_primary": (idx == 0),
                "uploaded_at": now_iso(),
                "category": "sample_inspiration",
            }
            uploaded_photos.append(photo_entry)

            try:
                await db.image_uploads.insert_one({
                    "_id": photo_id,
                    "key": photo_id,
                    "url": url,
                    "category": "sample_inspiration",
                    "is_sample_inspiration": True,
                    "sample_id": target_sample_id or folder_id,
                    "uploader": u.get("email"),
                    "created_at": now_iso(),
                })
            except Exception:
                pass
        except Exception as e:
            last_err = e

    if not uploaded_photos:
        raise HTTPException(400, f"No valid image files could be uploaded. {last_err or ''}".strip())

    if target_sample_id:
        try:
            sample = await db.samples.find_one({"_id": oid(target_sample_id)})
            if sample:
                has_primary = any(p.get("is_primary") for p in sample.get("inspiration_photos", []))
                if has_primary:
                    for p in uploaded_photos:
                        p["is_primary"] = False
                await db.samples.update_one(
                    {"_id": oid(target_sample_id)},
                    {
                        "$push": {"inspiration_photos": {"$each": uploaded_photos}},
                        "$set": {"updated_at": now_iso()},
                    }
                )
        except Exception:
            pass

    return {
        "ok": True,
        "count": len(uploaded_photos),
        "photos": uploaded_photos,
    }


@sampling_router.post("/{sid}/photos")
async def upload_sample_photos_to_sample(
    sid: str,
    request: Request,
    files: Optional[Any] = None,
    file: Optional[Any] = None,
    caption: Optional[str] = None,
    is_primary: Optional[bool] = None,
):
    """Upload one or more sample inspiration photos to an existing sample."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    all_files = await _extract_upload_files(request, files_arg=files, file_arg=file)
    if not all_files:
        raise HTTPException(400, "No valid image files provided in upload request")

    form = None
    try:
        form = await request.form()
    except Exception:
        pass

    # Extract caption & is_primary from query, form, or direct args
    if caption is None or caption == "":
        caption = request.query_params.get("caption") or (form.get("caption") if form else "") or ""
    if is_primary is None:
        p_val = request.query_params.get("is_primary") or (form.get("is_primary") if form else False)
        is_primary = str(p_val).lower() in ("true", "1", "yes")

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    sample_dir = os.path.join("uploads", "samples_inspiration", sid)
    os.makedirs(sample_dir, exist_ok=True)

    uploaded_photos = []
    existing_photos = sample.get("inspiration_photos", [])
    has_existing_primary = any(p.get("is_primary") for p in existing_photos)

    for idx, f_item in enumerate(all_files):
        try:
            content, safe_name = await validate_uploaded_file(
                file=f_item,
                allowed_extensions={"jpg", "jpeg", "png", "webp"},
                max_bytes=MAX_IMAGE_UPLOAD_BYTES,
                category_label="sample_inspiration_photo",
            )
            unique_name = f"{os.urandom(4).hex()}_{safe_name}"
            fpath = os.path.join(sample_dir, unique_name)
            with open(fpath, "wb") as f:
                f.write(content)

            url = f"/api/uploads/samples_inspiration/{sid}/{unique_name}"
            photo_id = os.urandom(6).hex()
            should_be_primary = (is_primary and idx == 0) or (not has_existing_primary and idx == 0 and len(existing_photos) == 0)

            photo_entry = {
                "photo_id": photo_id,
                "url": url,
                "thumbnail_url": url,
                "caption": caption if idx == 0 else "",
                "is_primary": should_be_primary,
                "uploaded_at": now_iso(),
                "category": "sample_inspiration",
            }
            uploaded_photos.append(photo_entry)

            try:
                await db.image_uploads.insert_one({
                    "_id": photo_id,
                    "key": photo_id,
                    "url": url,
                    "category": "sample_inspiration",
                    "is_sample_inspiration": True,
                    "sample_id": sid,
                    "uploader": u.get("email"),
                    "created_at": now_iso(),
                })
            except Exception:
                pass
        except Exception as e:
            pass

    if not uploaded_photos:
        raise HTTPException(400, "No valid image files could be uploaded")

    # If any new photo is marked primary, demote existing
    if any(p.get("is_primary") for p in uploaded_photos):
        await db.samples.update_one(
            {"_id": oid(sid)},
            {"$set": {"inspiration_photos.$[].is_primary": False}}
        )

    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$push": {"inspiration_photos": {"$each": uploaded_photos}},
            "$set": {"updated_at": now_iso()},
        }
    )

    updated = await db.samples.find_one({"_id": oid(sid)})
    return {
        "ok": True,
        "count": len(uploaded_photos),
        "photo": uploaded_photos[0],
        "photos": uploaded_photos,
        "sample": stringify(updated),
    }


upload_sample_photo = upload_sample_photos_to_sample


@sampling_router.patch("/{sid}/photos/{photo_id}/primary")
async def set_sample_primary_photo(sid: str, photo_id: str, request: Request):
    """Set a specific photo as the primary cover photo for the sample."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    # Demote all, then set matching photo_id to true
    await db.samples.update_one(
        {"_id": oid(sid)},
        {"$set": {"inspiration_photos.$[].is_primary": False}}
    )
    await db.samples.update_one(
        {"_id": oid(sid), "inspiration_photos.photo_id": photo_id},
        {"$set": {"inspiration_photos.$.is_primary": True, "updated_at": now_iso()}}
    )
    updated = await db.samples.find_one({"_id": oid(sid)})
    return {"ok": True, "sample": stringify(updated)}


@sampling_router.patch("/{sid}/photos/{photo_id}/caption")
async def update_sample_photo_caption(
    sid: str,
    photo_id: str,
    request: Request,
    caption: str = Query(...),
):
    """Update caption for a sample photo."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    await db.samples.update_one(
        {"_id": oid(sid), "inspiration_photos.photo_id": photo_id},
        {"$set": {"inspiration_photos.$.caption": caption.strip(), "updated_at": now_iso()}}
    )
    updated = await db.samples.find_one({"_id": oid(sid)})
    return {"ok": True, "sample": stringify(updated)}


@sampling_router.delete("/{sid}/photos/{photo_id}")
async def delete_sample_photo(sid: str, photo_id: str, request: Request):
    """Remove a photo from the sample's inspiration gallery."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$pull": {"inspiration_photos": {"photo_id": photo_id}},
            "$set": {"updated_at": now_iso()},
        }
    )
    updated = await db.samples.find_one({"_id": oid(sid)})
    return {"ok": True, "sample": stringify(updated)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. STATUS TRANSITIONS (Draft -> In Sampling -> Sample Ready -> Approved / Rejected)
# ─────────────────────────────────────────────────────────────────────────────

@sampling_router.post("/{sid}/status")
async def update_sample_status(
    sid: str,
    status: SampleStatus,
    request: Request,
    rejection_reason: Optional[str] = Query(None),
):
    """Advance or reject a sample through the sampling stages."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    update_data: Dict[str, Any] = {
        "status": status,
        "updated_at": now_iso(),
    }
    if status == "rejected":
        update_data["rejection_reason"] = rejection_reason or "Sample rejected during review"

    await db.samples.update_one({"_id": oid(sid)}, {"$set": update_data})
    updated = await db.samples.find_one({"_id": oid(sid)})
    return stringify(updated)


# ─────────────────────────────────────────────────────────────────────────────
# 4. TRANSFER TO STYLE MASTER (Auto-generates BOM Items & Labor Operations)
# ─────────────────────────────────────────────────────────────────────────────

@sampling_router.post("/{sid}/transfer-to-style")
async def transfer_sample_to_style(
    sid: str,
    payload: TransferToStyleIn,
    request: Request,
):
    """Transfer an approved sample into the official Style Master.
    - Official ERP Style Code is assigned.
    - Technical specs are imported:
      - Footwear type (flat/heel)
      - Insole mould & shape
      - Sole mould, shape & ready-to-use flag
      - Primary inspiration photo linked
      - BOM pre-populated with material yields for Upper, Insole, Sole, Heel, Lining, Hardware
      - Labor operations pre-populated for Cutting, Stitching, Edge Coloring, Insole Prep, Sole Prep, Lasting, Pasting
    - Downstream PO planning can immediately compute material requirements & labor slips!
    """
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    if sample.get("status") == "transferred_to_style":
        raise HTTPException(400, f"Sample {sample.get('temp_code')} was already transferred to style '{sample.get('transferred_style_code')}'")

    style_code = payload.style_code.strip().upper()
    existing_style = await db.styles.find_one({"code": style_code})
    if existing_style:
        raise HTTPException(409, f"Style code '{style_code}' already exists in Style Master. Please choose another code.")

    upper_spec = sample.get("upper_spec") or {}
    insole_spec = sample.get("insole_spec") or {}
    sole_spec = sample.get("sole_spec") or {}
    yields = payload.material_yields or {}
    rates = payload.labor_rates or {}

    # 1. Build Pre-Populated BOM Lines
    bom_items: List[Dict[str, Any]] = []

    # 1A. Upper Top Material
    if upper_spec.get("upper_top_material_name") or upper_spec.get("upper_top_material_id"):
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": upper_spec.get("upper_top_material_id") or "",
            "material_name": upper_spec.get("upper_top_material_name") or "Upper Material",
            "material_code": upper_spec.get("upper_top_material_code") or "",
            "unit": "sq ft",
            "rate": 0.0,
            "quantity": float(yields.get("upper_top", 1.2)),
            "yield_per_unit": 1.0,
            "waste_pct": 5.0,
            "section": "Upper",
            "component": "upper",
            "color": upper_spec.get("upper_color_to_develop") or "",
        })

    # 1B. Canvas Backing / Interlining
    if upper_spec.get("canvas_backing"):
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": "",
            "material_name": f"Canvas / Interlining: {upper_spec.get('canvas_backing')}",
            "material_code": "",
            "unit": "meter",
            "rate": 0.0,
            "quantity": float(yields.get("canvas", 0.15)),
            "yield_per_unit": 1.0,
            "waste_pct": 3.0,
            "section": "Upper",
            "component": "upper",
            "color": "",
        })

    # 1C. Lining Material
    if upper_spec.get("lining_material_name") or upper_spec.get("lining_material_id"):
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": upper_spec.get("lining_material_id") or "",
            "material_name": upper_spec.get("lining_material_name") or "Footwear Lining",
            "material_code": upper_spec.get("lining_material_code") or "",
            "unit": "sq ft",
            "rate": 0.0,
            "quantity": float(yields.get("lining", 1.0)),
            "yield_per_unit": 1.0,
            "waste_pct": 4.0,
            "section": "Lining",
            "component": "upper",
            "color": "",
        })

    # 1D. Insole Base Board (Shank or Cellulose)
    base_board_label = "Cellulose Board" if insole_spec.get("base_board") == "cellulose_board" else "Paper Shank Board"
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": "",
        "material_name": f"Insole Base ({base_board_label})",
        "material_code": "",
        "unit": "pair",
        "rate": 0.0,
        "quantity": float(yields.get("base_board", 1.0)),
        "yield_per_unit": 1.0,
        "waste_pct": 0.0,
        "section": "Insole",
        "component": "insole",
        "color": "",
    })

    # 1E. Cushioning Foam
    cushion_type = (insole_spec.get("cushioning_type") or "eva").upper()
    thickness = insole_spec.get("cushioning_thickness_mm") or "3mm"
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": "",
        "material_name": f"Cushioning Foam ({cushion_type} {thickness})",
        "material_code": "",
        "unit": "pair",
        "rate": 0.0,
        "quantity": float(yields.get("cushioning", 1.0)),
        "yield_per_unit": 1.0,
        "waste_pct": 0.0,
        "section": "Insole",
        "component": "insole",
        "color": "",
    })

    # 1F. Insole Covering (Socks)
    socks_label = insole_spec.get("socks_material_name") if insole_spec.get("socks_covering_type") == "custom" else f"Matching Socks ({upper_spec.get('upper_color_to_develop') or 'Upper Match'})"
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": insole_spec.get("socks_material_id") or "",
        "material_name": socks_label or "Socks Covering Material",
        "material_code": insole_spec.get("socks_material_code") or "",
        "unit": "sq ft",
        "rate": 0.0,
        "quantity": float(yields.get("socks_covering", 0.8)),
        "yield_per_unit": 1.0,
        "waste_pct": 4.0,
        "section": "Insole",
        "component": "insole",
        "color": insole_spec.get("socks_color") or upper_spec.get("upper_color_to_develop") or "",
    })

    # 1G. Outsole Material
    sole_mat = sole_spec.get("sole_material") or "TPR"
    mould = sole_spec.get("mould_name") or sole_spec.get("sole_shape") or ""
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": "",
        "material_name": f"Outsole: {sole_mat} ({mould or 'Standard'})",
        "material_code": "",
        "unit": "pair",
        "rate": 0.0,
        "quantity": float(yields.get("sole", 1.0)),
        "yield_per_unit": 1.0,
        "waste_pct": 0.0,
        "section": "Sole",
        "component": "sole",
        "color": "",
    })

    # 1H. Heel (if heeled)
    if sample.get("profile") == "heeled" or (sole_spec.get("heel_type") and sole_spec.get("heel_type") != "none"):
        heel_info = f"Heel: {sole_spec.get('heel_type', '').replace('_', ' ').title()} {sole_spec.get('heel_mould_name', '')} {sole_spec.get('heel_height', '')}"
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": "",
            "material_name": heel_info.strip(),
            "material_code": "",
            "unit": "pair",
            "rate": 0.0,
            "quantity": float(yields.get("heel", 1.0)),
            "yield_per_unit": 1.0,
            "waste_pct": 0.0,
            "section": "Sole",
            "component": "sole",
            "color": "",
        })

    # 1I. Buckle / Hardware (if selected)
    if upper_spec.get("has_buckle") or upper_spec.get("buckle_spec"):
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": "",
            "material_name": f"Hardware Buckle: {upper_spec.get('buckle_spec') or 'Standard Buckle'}",
            "material_code": "",
            "unit": "pair",
            "rate": 0.0,
            "quantity": float(yields.get("buckle", 1.0)),
            "yield_per_unit": 1.0,
            "waste_pct": 0.0,
            "section": "Accessories",
            "component": "upper",
            "color": "",
        })

    # Fill material rates from db.materials where material_id is present
    for bi in bom_items:
        if bi.get("material_id"):
            try:
                m_doc = await db.materials.find_one({"_id": oid(bi["material_id"])})
                if m_doc:
                    bi["rate"] = float(m_doc.get("rate") or 0.0)
                    if not bi.get("unit"):
                        bi["unit"] = m_doc.get("unit") or "pair"
            except Exception:
                pass

    # 2. Build Pre-Populated Labor Operations
    labor_items: List[Dict[str, Any]] = []

    # Cutting
    cutting_op = upper_spec.get("cutting_operation") or "die_cut"
    labor_items.append({
        "name": f"Upper Cutting ({cutting_op.replace('_', ' ').title()})",
        "rate": float(rates.get("cutting", 12.0)),
        "component": "upper",
        "is_outside": False,
        "vendor": None,
        "notes": "Die cutting / folding operation from sampling tech pack",
    })

    # Stitching
    if upper_spec.get("stitching_operation") != "no_stitching":
        labor_items.append({
            "name": "Upper Stitching & Assembly",
            "rate": float(rates.get("stitching", 25.0)),
            "component": "upper",
            "is_outside": False,
            "vendor": None,
            "notes": "Upper sewing & lining attachment",
        })

    # Edge Coloring
    if upper_spec.get("edge_treatment") == "edge_coloring":
        labor_items.append({
            "name": "Upper Edge Coloring & Treatment",
            "rate": float(rates.get("edge_coloring", 8.0)),
            "component": "upper",
            "is_outside": False,
            "vendor": None,
            "notes": "Edge coating / coloring specified in sample pack",
        })

    # Insole Prep
    labor_items.append({
        "name": f"Insole Board & Foam Assembly ({thickness})",
        "rate": float(rates.get("insole_making", 10.0)),
        "component": "bottom",
        "is_outside": False,
        "vendor": None,
        "notes": f"Base board ({base_board_label}) + {cushion_type} foam bonding",
    })

    # Insole Detailing (Embossing / Printing)
    if insole_spec.get("embossing") not in ("none", None) or insole_spec.get("printing") not in ("none", None):
        detail_txt = insole_spec.get("embossing") if insole_spec.get("embossing") != "none" else insole_spec.get("printing")
        labor_items.append({
            "name": f"Socks Detailing ({str(detail_txt).replace('_', ' ').title()})",
            "rate": float(rates.get("embossing", 5.0)),
            "component": "bottom",
            "is_outside": False,
            "vendor": None,
            "notes": insole_spec.get("embossing_details") or insole_spec.get("printing_details") or "",
        })

    # Sole Processing
    sole_ops = []
    if sole_spec.get("velting"): sole_ops.append("Welting")
    if sole_spec.get("grinding"): sole_ops.append("Grinding")
    if sole_spec.get("gripping"): sole_ops.append("Gripping")
    if sole_spec.get("attaching_top_piece"): sole_ops.append("Top Piece")
    if sole_ops or sole_spec.get("sole_type") == "die_cut":
        labor_items.append({
            "name": f"Sole Processing ({', '.join(sole_ops) if sole_ops else 'Die Cut Prep'})",
            "rate": float(rates.get("sole_prep", 15.0)),
            "component": "sole",
            "is_outside": False,
            "vendor": None,
            "notes": "Sole pre-treatment prior to lasting",
        })

    # Heel work
    if sole_spec.get("heel_finish") == "covered":
        labor_items.append({
            "name": "Heel Covering & Preparation",
            "rate": float(rates.get("heel_work", 12.0)),
            "component": "sole",
            "is_outside": False,
            "vendor": None,
            "notes": "Wrapping heel with specified material",
        })

    # Lasting & Pasting
    labor_items.append({
        "name": "Lasting (Upper to Insole/Last)",
        "rate": float(rates.get("lasting", 20.0)),
        "component": "bottom",
        "is_outside": False,
        "vendor": None,
        "notes": "Pulling upper over last and securing to insole",
    })

    labor_items.append({
        "name": "Pasting (Sole Attaching & Pressing)",
        "rate": float(rates.get("pasting", 18.0)),
        "component": "bottom",
        "is_outside": False,
        "vendor": None,
        "notes": "Sole cement and hydraulic press attachment",
    })

    labor_items.append({
        "name": "Finishing, Polishing & Packing",
        "rate": float(rates.get("finishing", 10.0)),
        "component": "other",
        "is_outside": False,
        "vendor": None,
        "notes": "Final inspection, touch-up, boxing",
    })

    # Primary image from sample
    primary_image = ""
    photos = sample.get("inspiration_photos", [])
    for p in photos:
        if p.get("is_primary") and p.get("url"):
            primary_image = p.get("url")
            break
    if not primary_image and photos:
        primary_image = photos[0].get("url", "")

    # Insole mould & sole mould names
    insole_mould = insole_spec.get("insole_style_code_shape") if sample.get("profile") == "heeled" else insole_spec.get("flat_mould_name_shape")
    sole_mould = sole_spec.get("mould_name")

    # Construct the Style Document
    style_doc = {
        "code": style_code,
        "name": payload.name.strip() if payload.name and payload.name.strip() else sample.get("sample_name", "Footwear Style"),
        "category": payload.category or sample.get("category", "Footwear"),
        "footwear_type": "heel" if sample.get("profile") == "heeled" else "flat",
        "image_url": primary_image if payload.use_sample_photo_as_primary else "",
        "image_display_url": primary_image if payload.use_sample_photo_as_primary else "",
        "image_thumbnail_url": primary_image if payload.use_sample_photo_as_primary else "",
        "description": f"Developed from Sample {sample.get('temp_code')}. {sample.get('notes', '')}".strip(),
        "base_size": payload.base_size or "7",
        "insole_mould_name": insole_mould or "",
        "sole_mould_name": sole_mould or "",
        "sole_ready_to_use": True if sole_spec.get("sole_type") == "ready_made" else False,
        "bom": bom_items,
        "labor": labor_items,
        "outside_labour": [],
        "overhead_pct": 5.0,
        "packing_cost": 25.0,
        "margin_pct": payload.margin_pct or 25.0,
        "gst_pct": payload.gst_pct or 5.0,
        "status": "active",
        "origin_sample_id": sid,
        "origin_sample_code": sample.get("temp_code"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    try:
        res = await db.styles.insert_one(style_doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"Style code '{style_code}' already exists in Style Master")

    created_style_id = str(res.inserted_id)

    # Update sample record with transition info
    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$set": {
                "status": "transferred_to_style",
                "transferred_style_id": created_style_id,
                "transferred_style_code": style_code,
                "transferred_at": now_iso(),
                "updated_at": now_iso(),
            }
        }
    )

    # Create digital PLM folder for the new style
    try:
        from models.plm import DEFAULT_PLM_FOLDERS
        await db.style_folders.insert_one({
            "style_id": created_style_id,
            "style_code": style_code,
            "folders": DEFAULT_PLM_FOLDERS,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
    except Exception:
        pass

    style_doc["id"] = created_style_id
    style_doc.pop("_id", None)

    updated_sample = await db.samples.find_one({"_id": oid(sid)})
    return {
        "ok": True,
        "message": f"Sample {sample.get('temp_code')} successfully transferred to Style Master as {style_code}",
        "style": stringify(style_doc),
        "sample": stringify(updated_sample),
    }

