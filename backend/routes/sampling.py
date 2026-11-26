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
import logging
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
    PatternPiece,
    StandardStripItem,
    StandardPresetComponent,
    SampleYieldCalculation,
    CalculateYieldIn,
    ImportPatternIn,
    SaveToLibraryIn,
)
from services.pattern_scanner_service import (
    extract_patterns_from_image_bytes,
    extract_piece_images_from_bytes,
    is_opencv_available,
)
from services.yield_nesting_service import simulate_nesting
from services.upload_validator import (
    validate_uploaded_file,
    sanitize_filename,
    ALLOWED_IMAGE_EXTENSIONS,
)
from services.imagekit_service import (
    is_imagekit_configured,
    upload_to_imagekit_async,
    delete_from_imagekit_async,
)
from constants import MAX_IMAGE_UPLOAD_BYTES

logger = logging.getLogger("sampling")
sampling_router = APIRouter(prefix="/api/samples", tags=["Sample Development & Tracking"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


STATUS_TIMELINE_LABELS = {
    "draft": "Sample Spec Created (Draft)",
    "in_sampling": "Moved to Sampling Floor",
    "sample_ready": "Sample Ready for Review",
    "approved": "Approved for Production",
    "rejected": "Rejected / Archived",
    "transferred_to_style": "Transferred to Style Master",
}


def _make_timeline_event(status: str, label: Optional[str] = None, actor: str = "", notes: str = "") -> Dict[str, Any]:
    return {
        "status": status,
        "label": label or STATUS_TIMELINE_LABELS.get(status, status.replace("_", " ").title()),
        "timestamp": now_iso(),
        "actor": actor,
        "notes": notes,
    }


async def _fetch_materials_info(db, material_ids: List[Optional[str]]) -> Dict[str, Dict[str, Any]]:
    """Fetch Material Master documents by ID for yield/BOM calculations."""
    clean_ids = []
    for mid in material_ids:
        if mid and isinstance(mid, str) and len(mid.strip()) == 24:
            try:
                clean_ids.append(ObjectId(mid.strip()))
            except Exception:
                pass
    if not clean_ids:
        return {}
    docs = await db.materials.find({"_id": {"$in": clean_ids}}).to_list(None)
    result: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        sid = str(d["_id"])
        d_copy = dict(d)
        d_copy["id"] = sid
        result[sid] = d_copy
    return result


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
        st = status.strip()
        if st == "active":
            query["status"] = {"$nin": ["transferred_to_style", "rejected"]}
        elif st == "archived":
            query["status"] = {"$in": ["transferred_to_style", "rejected"]}
        else:
            query["status"] = st
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


@sampling_router.get("/pattern-library")
async def list_pattern_library(request: Request, q: Optional[str] = None):
    """Fetch all reusable digitized patterns saved across styles and samples for cross-style re-use."""
    u = await _get_user(request)
    db = get_db(request)

    query = {}
    if q and q.strip():
        search_regex = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [
            {"pattern_name": search_regex},
            {"pattern_code": search_regex},
            {"style_code": search_regex},
            {"sample_code": search_regex},
        ]

    patterns = await db.plm_patterns.find(query).sort("updated_at", -1).to_list(100)
    return [stringify(p) for p in patterns]


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
    doc["timeline"] = [_make_timeline_event("draft", "Sample Spec Created", u.get("email", ""))]

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


async def _process_and_upload_photo(
    content: bytes,
    safe_name: str,
    folder_id: str,
    photo_id: str,
    is_primary: bool,
    caption: str = "",
) -> Dict[str, Any]:
    """Upload photo to ImageKit when configured, or fallback to local disk."""
    clean_name = safe_name.replace(" ", "_")
    clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", clean_name)
    clean_name = re.sub(r"_+", "_", clean_name)

    if is_imagekit_configured():
        try:
            ik_res = await upload_to_imagekit_async(
                file_data=content,
                file_name=f"{photo_id}_{clean_name}",
                folder="/ssk-erp/samples_inspiration",
                tags=["ssk-erp", "samples_inspiration"],
                use_unique_file_name=True,
            )
            url = ik_res.get("url")
            thumbnail_url = ik_res.get("thumbnail_url") or ik_res.get("thumbnailUrl") or url
            display_url = ik_res.get("display_url") or url
            file_id = ik_res.get("fileId")
            return {
                "photo_id": photo_id,
                "url": url,
                "thumbnail_url": thumbnail_url,
                "display_url": display_url,
                "file_id": file_id,
                "storage": "imagekit",
                "caption": caption,
                "is_primary": is_primary,
                "uploaded_at": now_iso(),
                "category": "sample_inspiration",
            }
        except Exception as ik_err:
            logger.warning(f"ImageKit upload failed ({ik_err}); falling back to local storage")

    # Local disk fallback
    sample_dir = os.path.join("uploads", "samples_inspiration", folder_id)
    os.makedirs(sample_dir, exist_ok=True)
    unique_name = f"{os.urandom(4).hex()}_{clean_name}"
    fpath = os.path.join(sample_dir, unique_name)
    with open(fpath, "wb") as f:
        f.write(content)

    url = f"/api/uploads/samples_inspiration/{folder_id}/{unique_name}"
    return {
        "photo_id": photo_id,
        "url": url,
        "thumbnail_url": url,
        "display_url": url,
        "file_id": None,
        "storage": "local",
        "caption": caption,
        "is_primary": is_primary,
        "uploaded_at": now_iso(),
        "category": "sample_inspiration",
    }


@sampling_router.post("/upload-photos")
async def upload_multiple_sample_photos(
    request: Request,
    sample_id: Optional[str] = None,
    files: Optional[Any] = None,
    file: Optional[Any] = None,
):
    """Upload multiple sample inspiration photos in a single batch.
    Stores to ImageKit.io when configured (with local fallback).
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
            photo_id = os.urandom(6).hex()
            photo_entry = await _process_and_upload_photo(
                content=content,
                safe_name=safe_name,
                folder_id=folder_id,
                photo_id=photo_id,
                is_primary=(idx == 0),
                caption="",
            )
            uploaded_photos.append(photo_entry)

            try:
                await db.image_uploads.insert_one({
                    "_id": photo_id,
                    "key": photo_id,
                    "url": photo_entry.get("url"),
                    "thumbnail_url": photo_entry.get("thumbnail_url"),
                    "display_url": photo_entry.get("display_url"),
                    "imagekit_file_id": photo_entry.get("file_id"),
                    "storage": photo_entry.get("storage", "local"),
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
    """Upload one or more sample inspiration photos to an existing sample (saved to ImageKit with local fallback)."""
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
            photo_id = os.urandom(6).hex()
            should_be_primary = (is_primary and idx == 0) or (not has_existing_primary and idx == 0 and len(existing_photos) == 0)

            photo_entry = await _process_and_upload_photo(
                content=content,
                safe_name=safe_name,
                folder_id=sid,
                photo_id=photo_id,
                is_primary=should_be_primary,
                caption=caption if idx == 0 else "",
            )
            uploaded_photos.append(photo_entry)

            try:
                await db.image_uploads.insert_one({
                    "_id": photo_id,
                    "key": photo_id,
                    "url": photo_entry.get("url"),
                    "thumbnail_url": photo_entry.get("thumbnail_url"),
                    "display_url": photo_entry.get("display_url"),
                    "imagekit_file_id": photo_entry.get("file_id"),
                    "storage": photo_entry.get("storage", "local"),
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
    """Remove a photo from the sample's inspiration gallery (and delete from ImageKit if applicable)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    target_photo = next((p for p in sample.get("inspiration_photos", []) if p.get("photo_id") == photo_id), None)
    if target_photo and target_photo.get("file_id") and target_photo.get("storage") == "imagekit":
        try:
            await delete_from_imagekit_async(target_photo["file_id"])
        except Exception as e:
            logger.warning(f"Failed to delete ImageKit photo {target_photo['file_id']}: {e}")

    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$pull": {"inspiration_photos": {"photo_id": photo_id}},
            "$set": {"updated_at": now_iso()},
        }
    )
    if db is not None and hasattr(db, "image_uploads"):
        try:
            await db.image_uploads.update_one(
                {"_id": photo_id},
                {"$set": {"status": "deleted", "deleted_at": now_iso()}}
            )
        except Exception:
            pass

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

    timeline_ev = _make_timeline_event(
        status=status,
        actor=u.get("email", ""),
        notes=rejection_reason or "",
    )
    await db.samples.update_one(
        {"_id": oid(sid)},
        {"$set": update_data, "$push": {"timeline": timeline_ev}},
    )
    updated = await db.samples.find_one({"_id": oid(sid)})
    return stringify(updated)


@sampling_router.post("/{sid}/actual-photo")
async def upload_actual_developed_photo(
    sid: str,
    request: Request,
    file: UploadFile = File(...),
):
    """Upload the actual developed & approved sample photo (stored separately from inspiration photos)."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    content, safe_name = await validate_uploaded_file(
        file=file,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        max_bytes=MAX_IMAGE_UPLOAD_BYTES,
        category_label="actual_sample_photo",
    )

    photo_id = f"actual_{os.urandom(6).hex()}"
    photo_entry = await _process_and_upload_photo(
        content=content,
        safe_name=f"actual_{safe_name}",
        folder_id=f"{sid}/actual",
        photo_id=photo_id,
        is_primary=True,
        caption="Actual Developed & Approved Sample",
    )
    actual_url = photo_entry.get("url") or photo_entry.get("display_url") or ""

    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$set": {
                "actual_developed_photo": photo_entry,
                "actual_developed_photo_url": actual_url,
                "updated_at": now_iso(),
            }
        },
    )
    return {
        "ok": True,
        "actual_photo": photo_entry,
        "actual_photo_url": actual_url,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. TRANSFER TO STYLE MASTER (Auto-generates BOM Items & Labor Operations)
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_next_style_code(db, profile: str = "flat") -> str:
    """Auto-generate the next unique Official ERP Style Code (e.g. SSK-2026-F001 or SSK-2026-H001)."""
    year = datetime.now(timezone.utc).year
    prefix_char = "H" if (profile or "").lower() == "heeled" else "F"
    base_prefix = f"SSK-{year}-{prefix_char}"
    regex = f"^SSK-{year}-[A-Z]?(\\d+)$"
    existing = await db.styles.find(
        {"code": {"$regex": f"^SSK-{year}-"}},
        {"code": 1},
    ).to_list(None)
    max_num = 0
    for doc in existing:
        c = str(doc.get("code") or "")
        m = re.match(regex, c)
        if m:
            try:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    next_num = max_num + 1
    candidate = f"{base_prefix}{next_num:03d}"
    while await db.styles.find_one({"code": candidate}, {"_id": 1}):
        next_num += 1
        candidate = f"{base_prefix}{next_num:03d}"
    return candidate


@sampling_router.get("/{sid}/next-style-code")
async def get_next_style_code_for_sample(sid: str, request: Request):
    """Return the auto-allotted Official ERP Style Code for a sample transfer."""
    await _get_user(request)
    db = get_db(request)
    sample = await db.samples.find_one({"_id": oid(sid)}, {"profile": 1})
    if not sample:
        raise HTTPException(404, "Sample not found")
    code = await _generate_next_style_code(db, sample.get("profile") or "flat")
    return {"ok": True, "style_code": code}


@sampling_router.post("/{sid}/transfer-to-style")
async def transfer_sample_to_style(
    sid: str,
    payload: TransferToStyleIn,
    request: Request,
):
    """Transfer an approved sample into the official Style Master.
    - Official ERP Style Code is automatically allotted if not provided.
    - Technical specs & calibrated BOM yields (pair/mtr) are imported.
    - Labor & karigar wages are calculated at the Planning stage (not at transfer).
    """
    u = await _get_user(request)
    require_roles("admin", "manager")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    if sample.get("status") == "transferred_to_style":
        raise HTTPException(400, f"Sample {sample.get('temp_code')} was already transferred to style '{sample.get('transferred_style_code')}'")

    if payload.style_code and payload.style_code.strip():
        style_code = payload.style_code.strip().upper()
    else:
        style_code = await _generate_next_style_code(db, sample.get("profile") or "flat")
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

    # Check if a calibrated yield calculation exists on this sample:
    sample_yield = sample.get("yield_spec") or {}
    calc_consumption = sample_yield.get("consumption_per_pair")
    calc_yield_per_unit = sample_yield.get("yield_per_unit")
    calc_unit = sample_yield.get("consumption_unit", "meter" if sample_yield.get("material_type") == "roll" else "sheet")
    calc_waste = sample_yield.get("waste_pct", 5.0)

    # 1A. Upper Materials (Supports 1, 2, 3+ distinct upper materials using calibrated material_breakdown)
    upper_materials = upper_spec.get("materials") or []
    mat_breakdowns = sample_yield.get("material_breakdown") or []
    if upper_materials:
        for idx, um in enumerate(upper_materials):
            mat_name = um.get("material_name") or "Upper Material"
            mat_id = um.get("material_id") or ""
            placement = um.get("placement") or ("Primary" if idx == 0 else "Secondary")

            # Match this material in calibrated material_breakdown
            matched_mb = next(
                (
                    mb for mb in mat_breakdowns
                    if not mb.get("is_lining") and not mb.get("is_canvas") and (
                        (mat_id and mb.get("material_id") == mat_id) or
                        (mat_name and mb.get("material_name") == mat_name) or
                        (placement and mb.get("placement") == placement)
                    )
                ),
                None,
            )

            override_ypu = yields.get(f"upper_mat_{idx}")
            if override_ypu and float(override_ypu) > 0:
                ypu = float(override_ypu)
                qty = 1.0
                unit_str = matched_mb.get("consumption_unit") or calc_unit if matched_mb else "meter"
                waste_val = 0.0
            elif matched_mb and float(matched_mb.get("consumption_per_pair") or 0) > 0:
                ypu = float(matched_mb.get("yield_per_unit") or round(1.0 / float(matched_mb["consumption_per_pair"]), 2))
                qty = 1.0
                unit_str = matched_mb.get("consumption_unit") or calc_unit
                waste_val = 0.0
            elif idx == 0 and calc_consumption and float(calc_consumption) > 0:
                ypu = float(calc_yield_per_unit) if calc_yield_per_unit else round(1.0 / float(calc_consumption), 2)
                qty = 1.0
                unit_str = calc_unit
                waste_val = 0.0
            else:
                ypu = float(yields.get("upper_top", 15.0) if idx == 0 else 25.0)
                if ypu <= 0:
                    ypu = 15.0
                qty = 1.0
                unit_str = "meter"
                waste_val = 0.0

            bom_items.append({
                "line_id": os.urandom(4).hex(),
                "material_id": mat_id or sample_yield.get("material_id") or "",
                "material_name": f"{mat_name} ({placement})",
                "material_code": um.get("material_code") or "",
                "unit": unit_str,
                "rate": 0.0,
                "quantity": qty,
                "yield_per_unit": ypu,
                "waste_pct": waste_val,
                "section": "Upper",
                "component": "upper",
                "color": um.get("color_to_develop") or "",
            })
    elif upper_spec.get("upper_top_material_name") or upper_spec.get("upper_top_material_id") or sample_yield.get("material_name"):
        if calc_consumption and float(calc_consumption) > 0:
            ypu = float(calc_yield_per_unit) if calc_yield_per_unit else round(1.0 / float(calc_consumption), 2)
            qty = 1.0
            unit_str = calc_unit
            waste_val = 0.0
        else:
            ypu = float(yields.get("upper_top", 15.0))
            if ypu <= 0:
                ypu = 15.0
            qty = 1.0
            unit_str = "meter"
            waste_val = 0.0

        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": upper_spec.get("upper_top_material_id") or sample_yield.get("material_id") or "",
            "material_name": upper_spec.get("upper_top_material_name") or sample_yield.get("material_name") or "Upper Material",
            "material_code": upper_spec.get("upper_top_material_code") or "",
            "unit": unit_str,
            "rate": 0.0,
            "quantity": qty,
            "yield_per_unit": ypu,
            "waste_pct": waste_val,
            "section": "Upper",
            "component": "upper",
            "color": upper_spec.get("upper_color_to_develop") or "",
        })

    # 1A-2. Standard Folded Laces & Unfolded Strips
    sample_strips = sample_yield.get("standard_strips") or sample.get("standard_strips") or []
    for st in sample_strips:
        is_unfolded = str(st.get("strip_type") or "folded").lower() == "unfolded"
        cut_info = f"{st.get('cut_width_mm')}mm"
        folded_info = st.get("folded_width_label") or f"{st.get('folded_width_mm')}mm"
        orient_label = "Cross-cut across width" if st.get("cut_orientation") == "across_width" else "Slitted along length"
        strip_name = st.get("name") or (f"Unfolded Strip {cut_info}" if is_unfolded else f"Folded Lace {folded_info}")
        lanes_info = f"{st.get('lanes_across_roll')} {'cuts' if st.get('cut_orientation') == 'across_width' else 'lanes'}" if st.get("lanes_across_roll") else ""
        laces_per_m = f"{st.get('laces_yield_per_meter')} {'strips' if is_unfolded else 'laces'}/m" if st.get("laces_yield_per_meter") else ""
        mat_dim_info = ""
        if st.get("material_width"):
            mat_dim_info = f"Mat: {st.get('material_width')}{st.get('material_width_unit', 'in')}"
            if st.get("material_length"):
                mat_dim_info += f" × {st.get('material_length')}{st.get('material_length_unit', 'm')}"
        notes_parts = [f"Unfolded (Width {cut_info}, {orient_label})"] if is_unfolded else [f"Cut Width: {cut_info} (2x Folded {folded_info}, {orient_label})"]
        if mat_dim_info: notes_parts.append(mat_dim_info)
        if lanes_info: notes_parts.append(lanes_info)
        if laces_per_m: notes_parts.append(laces_per_m)
        mat_disp_name = (
            f"{strip_name} (Unfolded Width {cut_info})"
            if is_unfolded
            else f"{strip_name} (Folded {folded_info}, Raw Cut {cut_info})"
        )
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": st.get("material_id") or "",
            "material_name": st.get("material_name") or mat_disp_name,
            "material_code": st.get("material_code") or "",
            "unit": st.get("consumption_unit", "meter"),
            "rate": float(st.get("material_rate") or 0.0),
            "quantity": float(st.get("consumption_per_pair") or 0.02),
            "yield_per_unit": float(st.get("yield_per_unit") or 50.0),
            "waste_pct": 5.0,
            "section": "Upper",
            "component": "unfolded_strip" if is_unfolded else "upper",
            "color": upper_spec.get("upper_color_to_develop") or "",
            "notes": " · ".join(notes_parts),
        })

    # 1B. Canvas Backing / Interlining
    canvas_name = upper_spec.get("canvas_material_name") or upper_spec.get("canvas_backing")
    if canvas_name or upper_spec.get("canvas_material_id"):
        c_bd = sample_yield.get("component_breakdown", {}).get("canvas_reinforcement", {})
        if c_bd.get("consumption_per_pair"):
            canvas_yield = float(c_bd.get("yield_per_unit") or round(1.0 / float(c_bd["consumption_per_pair"]), 2))
        else:
            canvas_yield = float(yields.get("canvas", 16.0))
            if canvas_yield <= 0:
                canvas_yield = 16.0
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": upper_spec.get("canvas_material_id") or "",
            "material_name": f"Canvas / Interlining: {canvas_name}" if canvas_name else "Canvas Backing",
            "material_code": upper_spec.get("canvas_material_code") or "CANVAS-BK",
            "unit": "meter",
            "rate": 0.0,
            "quantity": 1.0,
            "yield_per_unit": canvas_yield,
            "waste_pct": 0.0,
            "section": "Upper",
            "component": "upper",
            "color": "",
            "notes": "Calculated 2D yield for canvas reinforcement backing",
        })

    # 1C. Lining Material
    if upper_spec.get("lining_material_name") or upper_spec.get("lining_material_id"):
        l_bd = sample_yield.get("component_breakdown", {}).get("lining", {})
        if l_bd.get("consumption_per_pair"):
            lining_yield = float(l_bd.get("yield_per_unit") or round(1.0 / float(l_bd["consumption_per_pair"]), 2))
        else:
            lining_yield = float(yields.get("lining", 17.0))
            if lining_yield <= 0:
                lining_yield = 17.0
        bom_items.append({
            "line_id": os.urandom(4).hex(),
            "material_id": upper_spec.get("lining_material_id") or "",
            "material_name": upper_spec.get("lining_material_name") or "Footwear Lining",
            "material_code": upper_spec.get("lining_material_code") or "",
            "unit": "meter",
            "rate": 0.0,
            "quantity": 1.0,
            "yield_per_unit": lining_yield,
            "waste_pct": 0.0,
            "section": "Lining",
            "component": "upper",
            "color": "",
            "notes": "Calculated 2D yield for upper lining",
        })

    # 1D. Insole Base Board (Shank or Cellulose - with standard die-cut preset support)
    from services.yield_nesting_service import STANDARD_FACTORY_PRESETS
    base_board_label = "Cellulose Board" if insole_spec.get("base_board") == "cellulose_board" else "Paper Shank Board"
    std_presets = sample_yield.get("standard_presets") or STANDARD_FACTORY_PRESETS
    std_insole_preset = next((p for p in std_presets if "insole" in p.get("component_key", "")), None)
    if std_insole_preset and std_insole_preset.get("consumption_per_pair"):
        insole_qty = 1.0
        insole_ypu = float(std_insole_preset.get("yield_per_unit") or 26.0)
        insole_unit = std_insole_preset.get("consumption_unit", "sheet")
        insole_waste = 0.0
    else:
        insole_qty = float(yields.get("base_board", 1.0))
        insole_ypu = 1.0
        insole_unit = "pair"
        insole_waste = 0.0

    base_board_name = insole_spec.get("base_board_material_name") or base_board_label
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": insole_spec.get("base_board_material_id") or "",
        "material_name": f"Insole Base ({base_board_name})",
        "material_code": insole_spec.get("base_board_material_code") or "",
        "unit": insole_unit,
        "rate": 0.0,
        "quantity": insole_qty,
        "yield_per_unit": insole_ypu,
        "waste_pct": insole_waste,
        "section": "Insole",
        "component": "insole",
        "color": "",
    })

    # 1E. Cushioning Foam
    cushion_type = (insole_spec.get("cushioning_type") or "eva").upper()
    thickness = insole_spec.get("cushioning_thickness_mm") or "3mm"
    cushion_name = insole_spec.get("cushioning_material_name") or f"{cushion_type} {thickness}"
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": insole_spec.get("cushioning_material_id") or "",
        "material_name": f"Cushioning Foam ({cushion_name})",
        "material_code": insole_spec.get("cushioning_material_code") or "",
        "unit": "pair",
        "rate": 0.0,
        "quantity": float(yields.get("cushioning", 1.0)),
        "yield_per_unit": 1.0,
        "waste_pct": 0.0,
        "section": "Insole",
        "component": "insole",
        "color": "",
    })

    # 1F. Insole Covering (Socks / Bottom Covering - with standard preset support)
    socks_label = insole_spec.get("socks_material_name") if insole_spec.get("socks_covering_type") == "custom" else f"Matching Socks ({upper_spec.get('upper_color_to_develop') or 'Upper Match'})"
    std_socks_preset = next((p for p in std_presets if "socks" in p.get("component_key", "") or "bottom" in p.get("component_key", "")), None)
    if std_socks_preset and std_socks_preset.get("consumption_per_pair"):
        socks_qty = 1.0
        socks_ypu = float(std_socks_preset.get("yield_per_unit") or 8.0)
        socks_unit = std_socks_preset.get("consumption_unit", "meter")
        socks_waste = 0.0
    else:
        socks_ypu = float(yields.get("socks_covering", 8.0))
        if socks_ypu <= 0:
            socks_ypu = 8.0
        socks_qty = 1.0
        socks_unit = "meter"
        socks_waste = 0.0

    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": insole_spec.get("socks_material_id") or "",
        "material_name": socks_label or "Socks Covering Material",
        "material_code": insole_spec.get("socks_material_code") or "",
        "unit": socks_unit,
        "rate": 0.0,
        "quantity": socks_qty,
        "yield_per_unit": socks_ypu,
        "waste_pct": socks_waste,
        "section": "Insole",
        "component": "insole",
        "color": insole_spec.get("socks_color") or upper_spec.get("upper_color_to_develop") or "",
    })

    # 1G. Outsole Material
    sole_mat = sole_spec.get("sole_material_name") or sole_spec.get("sole_material") or "TPR"
    mould = sole_spec.get("mould_name") or sole_spec.get("sole_shape") or ""
    bom_items.append({
        "line_id": os.urandom(4).hex(),
        "material_id": sole_spec.get("sole_material_id") or "",
        "material_name": f"Outsole: {sole_mat} ({mould or 'Standard'})",
        "material_code": sole_spec.get("sole_material_code") or "",
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

    # 2. Labor Operations (Calculated at Planning stage, not during Sample-to-Style transfer)
    labor_items: List[Dict[str, Any]] = []
    if rates:
        cutting_op = upper_spec.get("cutting_operation") or "die_cut"
        labor_items.append({
            "name": f"Upper Cutting ({cutting_op.replace('_', ' ').title()})",
            "rate": float(rates.get("cutting", 12.0)),
            "component": "upper",
            "is_outside": False,
            "vendor": None,
            "notes": "Die cutting / folding operation from sampling tech pack",
        })
        if upper_spec.get("stitching_operation") != "no_stitching":
            labor_items.append({
                "name": "Upper Stitching & Assembly",
                "rate": float(rates.get("stitching", 25.0)),
                "component": "upper",
                "is_outside": False,
                "vendor": None,
                "notes": "Upper sewing & lining attachment",
            })
        if upper_spec.get("edge_treatment") == "edge_coloring":
            labor_items.append({
                "name": "Upper Edge Coloring & Treatment",
                "rate": float(rates.get("edge_coloring", 8.0)),
                "component": "upper",
                "is_outside": False,
                "vendor": None,
                "notes": "Edge coating / coloring specified in sample pack",
            })
        labor_items.append({
            "name": f"Insole Board & Foam Assembly ({thickness})",
            "rate": float(rates.get("insole_making", 10.0)),
            "component": "bottom",
            "is_outside": False,
            "vendor": None,
            "notes": f"Base board ({base_board_label}) + {cushion_type} foam bonding",
        })
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

    # Actual developed sample image ONLY (never copy inspiration photos to Style Master!)
    actual_photo_obj = payload.actual_photo or sample.get("actual_developed_photo") or {}
    actual_image_url = (
        payload.actual_photo_url
        or actual_photo_obj.get("url")
        or sample.get("actual_developed_photo_url")
        or ""
    )
    actual_display_url = actual_photo_obj.get("display_url") or actual_image_url
    actual_thumb_url = actual_photo_obj.get("thumbnail_url") or actual_image_url

    # Insole mould & sole mould names
    insole_mould = insole_spec.get("insole_style_code_shape") if sample.get("profile") == "heeled" else insole_spec.get("flat_mould_name_shape")
    sole_mould = sole_spec.get("mould_name")

    # Construct the Style Document
    style_doc = {
        "code": style_code,
        "name": payload.name.strip() if payload.name and payload.name.strip() else sample.get("sample_name", "Footwear Style"),
        "category": payload.category or sample.get("category", "Footwear"),
        "footwear_type": "heel" if sample.get("profile") == "heeled" else "flat",
        "image_url": actual_image_url,
        "image_display_url": actual_display_url,
        "image_thumbnail_url": actual_thumb_url,
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
        "linked_pattern_code": sample.get("linked_pattern_code") or f"PAT-{sample.get('temp_code') or sid[:8]}",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    try:
        res = await db.styles.insert_one(style_doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"Style code '{style_code}' already exists in Style Master")

    created_style_id = str(res.inserted_id)

    # Update sample record with transition info, actual photo, and timeline milestone
    sample_set_doc: Dict[str, Any] = {
        "status": "transferred_to_style",
        "transferred_style_id": created_style_id,
        "transferred_style_code": style_code,
        "transferred_at": now_iso(),
        "updated_at": now_iso(),
    }
    if actual_image_url:
        sample_set_doc["actual_developed_photo_url"] = actual_image_url
    if actual_photo_obj:
        sample_set_doc["actual_developed_photo"] = actual_photo_obj

    transfer_event = _make_timeline_event(
        status="transferred_to_style",
        label=f"Transferred to Style Master ({style_code})",
        actor=u.get("email", ""),
    )
    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$set": sample_set_doc,
            "$push": {"timeline": transfer_event},
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

    # Auto-save Scanned Pattern to Digital Style Folder (Folder 03 Upper Patterns) and PLM Library
    if sample.get("pattern_scan_url") or sample.get("pattern_pieces") or sample.get("yield_spec"):
        try:
            plm_pat_doc = {
                "style_id": created_style_id,
                "style_code": style_code,
                "folder_code": "03",
                "folder_name": "03 Upper Patterns",
                "document_name": f"A4 Pattern Master Scan ({sample.get('sample_name')})",
                "document_type": "pattern",
                "pattern_category": "Upper Pattern",
                "current_version": 1,
                "url": sample.get("pattern_scan_url") or "",
                "thumbnail_url": sample.get("pattern_scan_url") or "",
                "preview_url": sample.get("pattern_scan_url") or "",
                "pattern_pieces": sample.get("pattern_pieces") or [],
                "standard_strips": sample.get("standard_strips") or [],
                "yield_spec": sample.get("yield_spec") or {},
                "status": "approved",
                "tags": ["sampling_digitized_pattern", "upper_pattern", style_code],
                "uploaded_by": u.get("name") or u.get("email") or "Sampling Master",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            res_plm = await db.plm_documents.insert_one(plm_pat_doc)
            pat_lib_entry = {
                "pattern_code": sample.get("linked_pattern_code") or f"PAT-{style_code}",
                "pattern_name": f"{sample.get('sample_name')} Pattern Master",
                "category": "Upper Pattern",
                "style_id": created_style_id,
                "style_code": style_code,
                "sample_id": sid,
                "sample_code": sample.get("temp_code"),
                "document_id": str(res_plm.inserted_id),
                "pattern_pieces": sample.get("pattern_pieces") or [],
                "standard_strips": sample.get("standard_strips") or [],
                "yield_spec": sample.get("yield_spec") or {},
                "scan_url": sample.get("pattern_scan_url") or "",
                "updated_at": now_iso(),
            }
            await db.plm_patterns.update_one(
                {"sample_id": sid},
                {"$set": pat_lib_entry},
                upsert=True
            )
        except Exception as plm_err:
            logger.warning(f"Failed to auto-save pattern to digital style folder: {plm_err}")

    style_doc["id"] = created_style_id
    style_doc.pop("_id", None)

    updated_sample = await db.samples.find_one({"_id": oid(sid)})
    return {
        "ok": True,
        "message": f"Sample {sample.get('temp_code')} successfully transferred to Style Master as {style_code}",
        "style": stringify(style_doc),
        "sample": stringify(updated_sample),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. A4 PATTERN SCANNING, COMPUTER VISION CALIBRATION & 2D YIELD ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@sampling_router.post("/{sid}/pattern-scan")
async def scan_sample_pattern(
    sid: str,
    request: Request,
    file: UploadFile = File(...),
    threshold: Optional[int] = Query(None),
    min_area_sqcm: float = Query(2.0),
    background_mode: str = Query("dark", description="dark (black bed with light pattern), light, or auto"),
    component_category: str = Query("upper", description="upper, lining, or canvas"),
):
    """Scan and calibrate an A4 pattern image for true 1:1 scale contour and surface area."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    # Business Rule: Pattern scanning & yield calculation unlock after sample is marked 'Sample Ready'
    sample_status = sample.get("status") or "draft"
    if sample_status in ["draft", "in_sampling"]:
        raise HTTPException(
            400,
            f"Pattern scan and yield calculation are locked. They unlock after sample is marked as 'Sample Ready' (current status: '{sample_status}')."
        )

    content, safe_name = await validate_uploaded_file(
        file=file,
        allowed_extensions={"jpg", "jpeg", "png", "webp"},
        max_bytes=MAX_IMAGE_UPLOAD_BYTES,
        category_label="pattern_scan",
    )

    # Extract pattern pieces using computer vision with dark background support
    try:
        scan_result = extract_patterns_from_image_bytes(
            image_bytes=content,
            min_area_sqcm=min_area_sqcm,
            threshold_override=threshold,
            background_mode=background_mode,
        )
    except Exception as cv_err:
        logger.error(f"Pattern contour extraction failed: {cv_err}")
        raise HTTPException(400, f"Failed to extract pattern contours: {str(cv_err)}")

    # Upload scanned pattern file to storage (ImageKit or local)
    comp_norm = component_category.lower().strip()
    caption_label = (
        "A4 Lining Pattern Scan" if comp_norm == "lining"
        else "A4 Canvas Backing Scan" if comp_norm in ["canvas", "canvas_backing"]
        else "A4 Upper Pattern Scan"
    )
    photo_id = f"pat_{comp_norm}_{os.urandom(6).hex()}"
    photo_entry = await _process_and_upload_photo(
        content=content,
        safe_name=f"pattern_{comp_norm}_{safe_name}",
        folder_id=f"{sid}/patterns",
        photo_id=photo_id,
        is_primary=False,
        caption=caption_label,
    )

    pattern_scan_url = photo_entry.get("url") or photo_entry.get("display_url") or ""
    raw_pieces = scan_result.get("pattern_pieces") or []
    u_spec = sample.get("upper_spec") or {}

    # Tag scanned pieces with specific component metadata
    new_pieces = []
    for idx, p in enumerate(raw_pieces):
        p_dict = dict(p)
        if comp_norm == "lining":
            p_dict["component"] = "lining"
            p_dict["placement"] = "Upper Lining"
            p_dict["color"] = "#10b981"
            p_dict["piece_name"] = f"Lining Piece {idx + 1}"
            p_dict["material_name"] = u_spec.get("lining_material_name") or u_spec.get("lining") or "Lining Material"
            p_dict["material_id"] = u_spec.get("lining_material_id")
        elif comp_norm in ["canvas", "canvas_backing"]:
            p_dict["component"] = "canvas_backing"
            p_dict["placement"] = "Canvas Reinforcement"
            p_dict["color"] = "#f59e0b"
            p_dict["piece_name"] = f"Canvas Piece {idx + 1}"
            p_dict["material_name"] = u_spec.get("canvas_backing") or u_spec.get("canvas") or "Canvas Reinforcement"
        else:
            p_dict["component"] = "upper"
            p_dict["placement"] = "Upper"
        new_pieces.append(p_dict)

    # Separate & upload individual cropped piece images to digital folder
    piece_crops = extract_piece_images_from_bytes(content, new_pieces)
    piece_folder_entries = []
    for idx, p_dict in enumerate(new_pieces):
        pid = p_dict.get("piece_id")
        crop_bytes = piece_crops.get(pid)
        if crop_bytes:
            safe_pname = re.sub(r"[^a-zA-Z0-9_-]+", "_", p_dict.get("piece_name") or f"piece_{idx + 1}").strip("_")
            piece_photo_id = f"piece_{comp_norm}_{idx + 1}_{os.urandom(4).hex()}"
            try:
                p_photo = await _process_and_upload_photo(
                    content=crop_bytes,
                    safe_name=f"piece_{idx + 1}_{safe_pname}.jpg",
                    folder_id=f"{sid}/patterns/pieces",
                    photo_id=piece_photo_id,
                    is_primary=False,
                    caption=f"Piece {idx + 1}: {p_dict.get('piece_name')}",
                )
                p_dict["piece_photo_url"] = p_photo.get("display_url") or p_photo.get("url") or ""
                p_dict["piece_thumbnail_url"] = p_photo.get("thumbnail_url") or p_dict["piece_photo_url"]
                p_dict["piece_photo_id"] = piece_photo_id
                p_photo["piece_id"] = pid
                p_photo["piece_name"] = p_dict.get("piece_name")
                p_photo["component"] = p_dict.get("component")
                piece_folder_entries.append(p_photo)
            except Exception as up_err:
                logger.warning(f"Failed to upload separated piece image for {pid}: {up_err}")

    # Merge with existing pattern pieces: preserve other components
    existing_pieces = sample.get("pattern_pieces") or []
    if comp_norm == "lining":
        merged_pieces = [p for p in existing_pieces if p.get("component") != "lining"] + new_pieces
    elif comp_norm in ["canvas", "canvas_backing"]:
        merged_pieces = [p for p in existing_pieces if p.get("component") not in ["canvas", "canvas_backing"]] + new_pieces
    else:
        merged_pieces = new_pieces + [p for p in existing_pieces if p.get("component") in ["lining", "canvas", "canvas_backing"]]

    # Merge separated piece photos in digital folder
    existing_piece_photos = sample.get("pattern_piece_photos") or []
    if comp_norm == "lining":
        merged_piece_photos = [ph for ph in existing_piece_photos if ph.get("component") != "lining"] + piece_folder_entries
    elif comp_norm in ["canvas", "canvas_backing"]:
        merged_piece_photos = [ph for ph in existing_piece_photos if ph.get("component") not in ["canvas", "canvas_backing"]] + piece_folder_entries
    else:
        merged_piece_photos = piece_folder_entries + [ph for ph in existing_piece_photos if ph.get("component") in ["lining", "canvas", "canvas_backing"]]

    standard_strips = sample.get("standard_strips") or []

    mat_ids = [
        u_spec.get("upper_top_material_id"),
        u_spec.get("lining_material_id"),
        u_spec.get("canvas_material_id"),
        *[m.get("material_id") for m in (u_spec.get("materials") or [])],
        *[p.get("material_id") for p in merged_pieces],
    ]
    materials_info = await _fetch_materials_info(db, mat_ids)

    # Calculate nesting simulation across all components
    initial_yield = simulate_nesting(
        pieces=merged_pieces,
        material_type="roll",
        roll_width_inches=54.0,
        standard_strips=standard_strips,
        upper_spec=u_spec,
        lining_material_id=u_spec.get("lining_material_id"),
        lining_material_name=u_spec.get("lining_material_name"),
        lining_material_code=u_spec.get("lining_material_code"),
        canvas_backing=u_spec.get("canvas_material_name") or u_spec.get("canvas_backing") or u_spec.get("canvas"),
        materials_info=materials_info,
    )

    pat_code = sample.get("linked_pattern_code") or f"PAT-{sample.get('temp_code') or sid[:8]}"

    update_doc = {
        "pattern_scan_url": pattern_scan_url if comp_norm == "upper" else sample.get("pattern_scan_url", pattern_scan_url),
        "pattern_pieces": merged_pieces,
        "pattern_piece_photos": merged_piece_photos,
        "standard_strips": standard_strips,
        "linked_pattern_code": pat_code,
        "yield_spec": initial_yield,
        "updated_at": now_iso(),
    }
    if comp_norm == "lining":
        update_doc["lining_scan_url"] = pattern_scan_url
        update_doc["lining_scan_photo"] = photo_entry
    elif comp_norm in ["canvas", "canvas_backing"]:
        update_doc["canvas_scan_url"] = pattern_scan_url
        update_doc["canvas_scan_photo"] = photo_entry
    else:
        update_doc["pattern_scan_photo"] = photo_entry

    await db.samples.update_one(
        {"_id": oid(sid)},
        {"$set": update_doc}
    )

    # Save to central Pattern Manager library (db.plm_patterns)
    try:
        pat_lib_entry = {
            "pattern_code": pat_code,
            "pattern_name": f"{sample.get('sample_name')} Pattern Master",
            "category": "Upper Pattern",
            "sample_id": sid,
            "sample_code": sample.get("temp_code"),
            "style_id": sample.get("transferred_style_id"),
            "style_code": sample.get("transferred_style_code"),
            "pattern_pieces": merged_pieces,
            "standard_strips": standard_strips,
            "yield_spec": initial_yield,
            "scan_url": pattern_scan_url,
            "calibration": scan_result.get("calibration"),
            "total_net_area_sqcm": scan_result.get("total_net_area_sqcm", 0.0),
            "updated_at": now_iso(),
        }
        await db.plm_patterns.update_one(
            {"pattern_code": pat_code},
            {"$set": pat_lib_entry},
            upsert=True
        )
    except Exception:
        pass

    # Save to PLM digital folder (03 Upper, 03B Lining, 03C Canvas)
    try:
        folder_code = "03B" if comp_norm == "lining" else ("03C" if comp_norm in ["canvas", "canvas_backing"] else "03")
        folder_name = "03B Lining Patterns" if comp_norm == "lining" else ("03C Canvas & Reinforcements" if comp_norm in ["canvas", "canvas_backing"] else "03 Upper Patterns")
        style_code = sample.get("transferred_style_code") or sample.get("temp_code") or sid[:8]
        await db.plm_documents.update_one(
            {"sample_id": sid, "folder_code": folder_code},
            {"$set": {
                "sample_id": sid,
                "style_code": style_code,
                "folder_code": folder_code,
                "folder_name": folder_name,
                "document_name": f"{folder_name} ({sample.get('sample_name')})",
                "document_type": "pattern",
                "scan_url": pattern_scan_url,
                "pattern_pieces": new_pieces,
                "status": "approved",
                "uploaded_by": u.get("name") or u.get("email") or "Sampling Master",
                "updated_at": now_iso(),
            }},
            upsert=True
        )
    except Exception:
        pass

    return {
        "ok": True,
        "status": "success",
        "sample_id": sid,
        "component_category": comp_norm,
        "calibration": scan_result.get("calibration"),
        "detected_pieces_count": len(new_pieces),
        "total_pieces_count": len(merged_pieces),
        "pattern_pieces": merged_pieces,
        "yield_spec": initial_yield,
        "scan_url": pattern_scan_url,
    }


@sampling_router.post("/{sid}/save-pattern-pieces")
async def save_sample_pattern_pieces(
    sid: str,
    request: Request,
    payload: Dict[str, Any],
):
    """Save user-mapped pattern pieces separately by component into sample and digital folders."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    pieces = payload.get("pieces") or []
    strips = payload.get("standard_strips") or sample.get("standard_strips") or []
    u_spec = sample.get("upper_spec") or {}

    updated_yield = simulate_nesting(
        pieces=pieces,
        material_type=sample.get("yield_spec", {}).get("material_type", "roll") if sample.get("yield_spec") else "roll",
        roll_width_inches=sample.get("yield_spec", {}).get("roll_width_inches", 54.0) if sample.get("yield_spec") else 54.0,
        standard_strips=strips,
        upper_spec=u_spec,
    )

    await db.samples.update_one(
        {"_id": oid(sid)},
        {"$set": {
            "pattern_pieces": pieces,
            "standard_strips": strips,
            "yield_spec": updated_yield,
            "updated_at": now_iso(),
        }}
    )

    # Save separately to PLM digital folders
    style_code = sample.get("transferred_style_code") or sample.get("temp_code") or sid[:8]
    for comp_norm, f_code, f_name in [
        ("upper", "03", "03 Upper Patterns"),
        ("lining", "03B", "03B Lining Patterns"),
        ("canvas_backing", "03C", "03C Canvas & Reinforcements"),
    ]:
        comp_pieces = [p for p in pieces if (p.get("component") or "upper") == comp_norm or (comp_norm == "canvas_backing" and p.get("component") == "canvas")]
        if comp_pieces:
            try:
                await db.plm_documents.update_one(
                    {"sample_id": sid, "folder_code": f_code},
                    {"$set": {
                        "sample_id": sid,
                        "style_code": style_code,
                        "folder_code": f_code,
                        "folder_name": f_name,
                        "document_name": f"{f_name} ({sample.get('sample_name')})",
                        "document_type": "pattern",
                        "pattern_pieces": comp_pieces,
                        "status": "approved",
                        "uploaded_by": u.get("name") or u.get("email") or "Sampling Master",
                        "updated_at": now_iso(),
                    }},
                    upsert=True
                )
            except Exception:
                pass

    return {
        "status": "success",
        "message": "Pattern pieces and component mappings saved to digital folders",
        "pieces_count": len(pieces),
        "yield_spec": updated_yield,
    }


@sampling_router.post("/{sid}/calculate-yield")
async def calculate_sample_yield(
    sid: str,
    payload: CalculateYieldIn,
    request: Request,
):
    """Simulate 2D nesting across roll or sheet raw materials, folded laces, and standard presets."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    # Business Rule: Yield calculation is active only after sample is marked as 'Sample Ready' (or approved / transferred)
    sample_status = sample.get("status") or "draft"
    if sample_status in ["draft", "in_sampling"]:
        raise HTTPException(
            400,
            f"Yield calculation is locked. It unlocks after sample is marked as 'Sample Ready' (current status: '{sample_status}')."
        )

    # Use pieces passed in payload, or fallback to saved pattern_pieces on sample
    pieces_input = payload.pieces
    if pieces_input is None:
        pieces_input = sample.get("pattern_pieces") or []

    pieces_data = [
        p.model_dump() if hasattr(p, "model_dump") else (p.dict() if hasattr(p, "dict") else p)
        for p in pieces_input
    ]

    # Standard linear folded laces / strips (Formula: Cut Width = 2 * Folded Width)
    strips_input = payload.standard_strips
    if strips_input is None:
        strips_input = sample.get("standard_strips") or []

    strips_data = [
        s.model_dump() if hasattr(s, "model_dump") else (s.dict() if hasattr(s, "dict") else s)
        for s in strips_input
    ]

    # Standard presets (die-cut insole board, cushioning, socks covering)
    presets_input = payload.standard_presets
    if presets_input is None:
        presets_input = (sample.get("yield_spec") or {}).get("standard_presets") or []

    if not pieces_data and not strips_data:
        raise HTTPException(400, "No pattern pieces or standard lace components available to calculate yield.")

    eff_upper_spec = payload.upper_spec or sample.get("upper_spec") or {}
    mat_ids = [
        payload.material_id,
        payload.lining_material_id,
        eff_upper_spec.get("upper_top_material_id"),
        eff_upper_spec.get("lining_material_id"),
        eff_upper_spec.get("canvas_material_id"),
        *[m.get("material_id") for m in (eff_upper_spec.get("materials") or [])],
        *[p.get("material_id") for p in pieces_data],
    ]
    materials_info = await _fetch_materials_info(db, mat_ids)

    yield_res = simulate_nesting(
        pieces=pieces_data,
        material_type=payload.material_type,
        roll_width_inches=payload.roll_width_inches or 54.0,
        custom_roll_width_mm=payload.custom_roll_width_mm,
        sheet_length_mm=payload.sheet_length_mm,
        sheet_width_mm=payload.sheet_width_mm,
        selvage_margin_mm=payload.selvage_margin_mm or 20.0,
        kerf_spacing_mm=payload.kerf_spacing_mm or 3.0,
        waste_allowance_pct=payload.waste_allowance_pct or 5.0,
        standard_strips=strips_data,
        standard_presets=presets_input,
        cutting_direction=payload.cutting_direction or "length_up",
        roll_length_meters=payload.roll_length_meters or 1.0,
        expected_pieces_count=payload.expected_pieces_count,
        measurement_unit=payload.measurement_unit or "mm",
        upper_spec=eff_upper_spec,
        lining_material_id=payload.lining_material_id or eff_upper_spec.get("lining_material_id"),
        lining_material_name=payload.lining_material_name or eff_upper_spec.get("lining_material_name"),
        lining_material_code=payload.lining_material_code or eff_upper_spec.get("lining_material_code"),
        canvas_backing=payload.canvas_backing or eff_upper_spec.get("canvas_material_name") or eff_upper_spec.get("canvas_backing"),
        materials_info=materials_info,
    )

    if payload.material_id:
        yield_res["material_id"] = payload.material_id
    if payload.material_name:
        yield_res["material_name"] = payload.material_name

    yield_res["calculated_at"] = now_iso()

    # Save to sample document
    await db.samples.update_one(
        {"_id": oid(sid)},
        {
            "$set": {
                "pattern_pieces": pieces_data,
                "standard_strips": yield_res.get("standard_strips", strips_data),
                "yield_spec": yield_res,
                "updated_at": now_iso(),
            }
        }
    )

    # Sync to PLM pattern library
    pat_code = sample.get("linked_pattern_code") or f"PAT-{sample.get('temp_code') or sid[:8]}"
    try:
        await db.plm_patterns.update_one(
            {"pattern_code": pat_code},
            {
                "$set": {
                    "pattern_pieces": pieces_data,
                    "standard_strips": yield_res.get("standard_strips", strips_data),
                    "yield_spec": yield_res,
                    "updated_at": now_iso(),
                }
            }
        )
    except Exception:
        pass

    updated = await db.samples.find_one({"_id": oid(sid)})
    return {
        "ok": True,
        "yield_spec": yield_res,
        "standard_strips": yield_res.get("standard_strips", strips_data),
        "sample": stringify(updated),
    }


@sampling_router.post("/{sid}/import-pattern")
async def import_pattern_to_sample(sid: str, payload: ImportPatternIn, request: Request):
    """Re-use an existing scanned pattern from the library into this sample."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    target_pat = None
    if payload.pattern_id:
        try:
            target_pat = await db.plm_patterns.find_one({"_id": oid(payload.pattern_id)})
        except Exception:
            pass
    if not target_pat and payload.pattern_code:
        target_pat = await db.plm_patterns.find_one({"pattern_code": payload.pattern_code})

    if not target_pat:
        raise HTTPException(404, "Target pattern not found in library")

    # Copy pattern pieces, standard strips, yield spec, and scan url
    update_data = {
        "pattern_pieces": target_pat.get("pattern_pieces") or [],
        "standard_strips": target_pat.get("standard_strips") or [],
        "yield_spec": target_pat.get("yield_spec") or {},
        "pattern_scan_url": target_pat.get("scan_url") or "",
        "linked_pattern_code": target_pat.get("pattern_code") or "",
        "updated_at": now_iso(),
    }

    await db.samples.update_one({"_id": oid(sid)}, {"$set": update_data})
    updated = await db.samples.find_one({"_id": oid(sid)})
    return {
        "ok": True,
        "message": f"Successfully imported pattern {target_pat.get('pattern_code')} into sample {sample.get('temp_code')}",
        "sample": stringify(updated),
        "imported_pattern": stringify(target_pat),
    }


@sampling_router.post("/{sid}/save-to-library")
async def save_sample_pattern_to_library(sid: str, payload: SaveToLibraryIn, request: Request):
    """Save or name the current sample's pattern into the reusable pattern library."""
    u = await _get_user(request)
    require_roles("admin", "manager", "production")(u)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    pat_code = payload.pattern_code or sample.get("linked_pattern_code") or f"PAT-{sample.get('temp_code') or sid[:8]}"
    pat_doc = {
        "pattern_code": pat_code,
        "pattern_name": payload.pattern_name.strip(),
        "category": payload.category or "Upper Pattern",
        "sample_id": sid,
        "sample_code": sample.get("temp_code"),
        "style_id": sample.get("transferred_style_id"),
        "style_code": sample.get("transferred_style_code"),
        "pattern_pieces": sample.get("pattern_pieces") or [],
        "standard_strips": sample.get("standard_strips") or [],
        "yield_spec": sample.get("yield_spec") or {},
        "scan_url": sample.get("pattern_scan_url") or "",
        "updated_at": now_iso(),
    }

    await db.plm_patterns.update_one(
        {"pattern_code": pat_code},
        {"$set": pat_doc},
        upsert=True
    )

    await db.samples.update_one(
        {"_id": oid(sid)},
        {"$set": {"linked_pattern_code": pat_code, "updated_at": now_iso()}}
    )

    return {
        "ok": True,
        "message": f"Pattern successfully saved to library as '{pat_code}'",
        "pattern": stringify(pat_doc),
    }


@sampling_router.get("/{sid}/yield-spec")
async def get_sample_yield_spec(sid: str, request: Request):
    """Retrieve saved pattern scan pieces and yield calculation for a sample."""
    u = await _get_user(request)
    db = get_db(request)

    sample = await db.samples.find_one({"_id": oid(sid)})
    if not sample:
        raise HTTPException(404, "Sample not found")

    return {
        "ok": True,
        "pattern_scan_url": sample.get("pattern_scan_url"),
        "pattern_pieces": sample.get("pattern_pieces") or [],
        "standard_strips": sample.get("standard_strips") or [],
        "linked_pattern_code": sample.get("linked_pattern_code"),
        "yield_spec": sample.get("yield_spec") or None,
    }

