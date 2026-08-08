"""PLM (Product Lifecycle Management) & Digital Style Folder Routes."""
import re
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from bson import ObjectId
from datetime import datetime, timezone

from models.plm import (
    DEFAULT_PLM_FOLDERS,
    PATTERN_CATEGORIES,
    TOOLING_CATEGORIES,
    PLMDocumentIn,
    PLMPatternIn,
    PLMToolingIn,
    DocumentVersion,
    ScanningMetadata,
)

plm_router = APIRouter(prefix="/api/plm", tags=["PLM & Style Engineering"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify(doc: dict) -> dict:
    if not doc:
        return {}
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


async def _get_user(request: Request):
    from auth import get_current_user
    return await get_current_user(request)


async def log_plm_audit(db, action: str, style_code: str, user_email: str, details: str, doc_id: str = None, prev_ver: str = None, curr_ver: str = None, ip: str = "127.0.0.1"):
    audit_entry = {
        "action": action,
        "style_code": style_code,
        "doc_id": doc_id,
        "previous_version": prev_ver,
        "current_version": curr_ver,
        "user": user_email,
        "ip_address": ip,
        "details": details,
        "timestamp": now_iso(),
    }
    await db.plm_audit_log.insert_one(audit_entry)


# ---------- FOLDERS ----------

@plm_router.get("/styles/{style_id}/folders")
async def get_or_create_style_folders(style_id: str, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    # Validate style exists
    try:
        s_oid = ObjectId(style_id)
    except Exception:
        s_oid = None

    style = None
    if s_oid:
        style = await db.styles.find_one({"_id": s_oid})
    if not style:
        style = await db.styles.find_one({"code": style_id})
    if not style:
        raise HTTPException(404, f"Style '{style_id}' not found")

    sid_str = str(style["_id"])
    s_code = style.get("code", "")

    folder_doc = await db.style_folders.find_one({"style_id": sid_str})
    if not folder_doc:
        folder_doc = {
            "style_id": sid_str,
            "style_code": s_code,
            "folders": DEFAULT_PLM_FOLDERS,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        res = await db.style_folders.insert_one(folder_doc)
        folder_doc["_id"] = res.inserted_id

    # Compute document counts per folder
    docs_cursor = db.plm_documents.find({"style_id": sid_str, "status": {"$ne": "archived"}})
    docs = await docs_cursor.to_list(1000)

    counts_by_code = {}
    for d in docs:
        fc = d.get("folder_code", "01")
        counts_by_code[fc] = counts_by_code.get(fc, 0) + 1

    res_folders = []
    for f in folder_doc.get("folders", DEFAULT_PLM_FOLDERS):
        f_copy = dict(f)
        f_copy["file_count"] = counts_by_code.get(f_copy["code"], 0)
        res_folders.append(f_copy)

    out = stringify(folder_doc)
    out["folders"] = res_folders
    out["style_name"] = style.get("name", "")
    out["style_image"] = style.get("image_url", "")
    return out


# ---------- DOCUMENTS ----------

@plm_router.get("/styles/{style_id}/documents")
async def list_style_documents(
    style_id: str,
    request: Request,
    folder_code: Optional[str] = None,
    document_type: Optional[str] = None,
    search: Optional[str] = None,
):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        s_oid = ObjectId(style_id)
    except Exception:
        s_oid = None

    style = None
    if s_oid:
        style = await db.styles.find_one({"_id": s_oid})
    if not style:
        style = await db.styles.find_one({"code": style_id})
    if not style:
        raise HTTPException(404, f"Style '{style_id}' not found")

    query = {"style_id": str(style["_id"]), "status": {"$ne": "archived"}}
    if folder_code:
        query["folder_code"] = folder_code
    if document_type:
        query["document_type"] = document_type
    if search:
        query["$or"] = [
            {"document_name": {"$regex": re.escape(search), "$options": "i"}},
            {"file_name": {"$regex": re.escape(search), "$options": "i"}},
            {"tags": {"$regex": re.escape(search), "$options": "i"}},
        ]

    docs = await db.plm_documents.find(query).sort("updated_at", -1).to_list(1000)
    return [stringify(d) for d in docs]


@plm_router.post("/styles/{style_id}/documents/upload")
async def upload_plm_document(style_id: str, payload: PLMDocumentIn, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        s_oid = ObjectId(style_id)
    except Exception:
        s_oid = None

    style = None
    if s_oid:
        style = await db.styles.find_one({"_id": s_oid})
    if not style:
        style = await db.styles.find_one({"code": style_id})
    if not style:
        raise HTTPException(404, f"Style '{style_id}' not found")

    sid_str = str(style["_id"])
    s_code = style.get("code", "")

    v1 = DocumentVersion(
        version=1,
        file_name=payload.file_name,
        file_type=payload.file_type,
        file_size=payload.file_size,
        url=payload.url,
        thumbnail_url=payload.thumbnail_url or payload.url,
        preview_url=payload.preview_url or payload.url,
        imagekit_file_id=payload.imagekit_file_id,
        width=payload.width,
        height=payload.height,
        checksum=payload.checksum,
        uploaded_by=u.get("name") or u.get("email") or "User",
        uploaded_at=now_iso(),
        remarks=payload.remarks or "Initial upload v1",
    )

    doc = {
        "style_id": sid_str,
        "style_code": s_code,
        "folder_code": payload.folder_code,
        "folder_name": payload.folder_name,
        "document_name": payload.document_name,
        "document_type": payload.document_type,
        "pattern_category": payload.pattern_category,
        "current_version": 1,
        "url": payload.url,
        "thumbnail_url": payload.thumbnail_url or payload.url,
        "preview_url": payload.preview_url or payload.url,
        "file_name": payload.file_name,
        "file_type": payload.file_type,
        "file_size": payload.file_size,
        "imagekit_file_id": payload.imagekit_file_id,
        "scanning_metadata": payload.scanning_metadata.model_dump() if payload.scanning_metadata else {},
        "tags": payload.tags,
        "versions": [v1.model_dump()],
        "status": "approved",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    res = await db.plm_documents.insert_one(doc)
    doc_id = str(res.inserted_id)

    # If it's a pattern, create entry in plm_patterns
    if payload.pattern_category or "Pattern" in payload.folder_name:
        pat_doc = {
            "style_id": sid_str,
            "style_code": s_code,
            "pattern_name": payload.document_name,
            "category": payload.pattern_category or "Upper Pattern",
            "document_id": doc_id,
            "version": 1,
            "grading_sizes": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        await db.plm_patterns.insert_one(pat_doc)

    await log_plm_audit(
        db, "upload", s_code, u["email"],
        f"Uploaded '{payload.document_name}' v1 into {payload.folder_name}",
        doc_id=doc_id, curr_ver="1"
    )

    doc["id"] = doc_id
    doc.pop("_id", None)
    return stringify(doc)


@plm_router.post("/styles/{style_id}/documents/{doc_id}/replace")
async def replace_plm_document_version(style_id: str, doc_id: str, payload: dict, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        d_oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(400, "Invalid document ID")

    existing = await db.plm_documents.find_one({"_id": d_oid})
    if not existing:
        raise HTTPException(404, "Document not found")

    new_ver = existing.get("current_version", 1) + 1
    v_new = DocumentVersion(
        version=new_ver,
        file_name=payload.get("file_name", existing["file_name"]),
        file_type=payload.get("file_type", existing["file_type"]),
        file_size=payload.get("file_size", existing.get("file_size", 0)),
        url=payload.get("url", existing["url"]),
        thumbnail_url=payload.get("thumbnail_url") or payload.get("url") or existing.get("thumbnail_url"),
        preview_url=payload.get("preview_url") or payload.get("url") or existing.get("preview_url"),
        imagekit_file_id=payload.get("imagekit_file_id"),
        width=payload.get("width"),
        height=payload.get("height"),
        checksum=payload.get("checksum"),
        uploaded_by=u.get("name") or u.get("email") or "User",
        uploaded_at=now_iso(),
        remarks=payload.get("remarks", f"Replaced with version v{new_ver}"),
    )

    versions = existing.get("versions", [])
    versions.append(v_new.model_dump())

    update_doc = {
        "current_version": new_ver,
        "url": v_new.url,
        "thumbnail_url": v_new.thumbnail_url,
        "preview_url": v_new.preview_url,
        "file_name": v_new.file_name,
        "file_type": v_new.file_type,
        "file_size": v_new.file_size,
        "imagekit_file_id": v_new.imagekit_file_id,
        "versions": versions,
        "updated_at": now_iso(),
    }

    await db.plm_documents.update_one({"_id": d_oid}, {"$set": update_doc})

    await log_plm_audit(
        db, "replace", existing.get("style_code", ""), u["email"],
        f"Replaced '{existing.get('document_name')}' with version v{new_ver}",
        doc_id=doc_id, prev_ver=str(new_ver - 1), curr_ver=str(new_ver)
    )

    updated = await db.plm_documents.find_one({"_id": d_oid})
    return stringify(updated)


@plm_router.post("/styles/{style_id}/documents/{doc_id}/rollback")
async def rollback_plm_document_version(style_id: str, doc_id: str, target_version: int, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        d_oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(400, "Invalid document ID")

    existing = await db.plm_documents.find_one({"_id": d_oid})
    if not existing:
        raise HTTPException(404, "Document not found")

    versions = existing.get("versions", [])
    target = next((v for v in versions if v.get("version") == target_version), None)
    if not target:
        raise HTTPException(404, f"Version {target_version} not found in history")

    prev_v = existing.get("current_version", 1)
    update_doc = {
        "current_version": target_version,
        "url": target["url"],
        "thumbnail_url": target.get("thumbnail_url") or target["url"],
        "preview_url": target.get("preview_url") or target["url"],
        "file_name": target["file_name"],
        "file_type": target.get("file_type", "application/pdf"),
        "file_size": target.get("file_size", 0),
        "imagekit_file_id": target.get("imagekit_file_id"),
        "updated_at": now_iso(),
    }

    await db.plm_documents.update_one({"_id": d_oid}, {"$set": update_doc})

    await log_plm_audit(
        db, "rollback", existing.get("style_code", ""), u["email"],
        f"Rolled back '{existing.get('document_name')}' to version v{target_version}",
        doc_id=doc_id, prev_ver=str(prev_v), curr_ver=str(target_version)
    )

    updated = await db.plm_documents.find_one({"_id": d_oid})
    return stringify(updated)


@plm_router.delete("/styles/{style_id}/documents/{doc_id}")
async def delete_plm_document(style_id: str, doc_id: str, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        d_oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(400, "Invalid document ID")

    existing = await db.plm_documents.find_one({"_id": d_oid})
    if not existing:
        raise HTTPException(404, "Document not found")

    await db.plm_documents.update_one({"_id": d_oid}, {"$set": {"status": "archived", "updated_at": now_iso()}})

    await log_plm_audit(
        db, "delete", existing.get("style_code", ""), u["email"],
        f"Archived document '{existing.get('document_name')}'",
        doc_id=doc_id, prev_ver=str(existing.get("current_version", 1))
    )
    return {"status": "success", "message": "Document archived"}


# ---------- PATTERNS & DIGITIZING ----------

@plm_router.get("/patterns")
async def list_patterns(request: Request, category: Optional[str] = None, style_code: Optional[str] = None):
    u = await _get_user(request)
    db = request.app.mongodb

    q = {}
    if category:
        q["category"] = category
    if style_code:
        q["style_code"] = style_code

    docs = await db.plm_patterns.find(q).sort("created_at", -1).to_list(1000)
    return [stringify(d) for d in docs]


@plm_router.post("/patterns")
async def create_pattern(payload: PLMPatternIn, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()

    res = await db.plm_patterns.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)

    await log_plm_audit(
        db, "upload", payload.style_code, u["email"],
        f"Created pattern '{payload.pattern_name}' ({payload.category})"
    )
    return stringify(doc)


@plm_router.post("/patterns/scan")
async def scan_and_digitize_pattern(payload: dict, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    # Digital Pattern Scan Processing Simulation / Metadata record
    scanning_meta = ScanningMetadata(
        dpi=payload.get("dpi", 300),
        auto_crop=payload.get("auto_crop", True),
        deskew=payload.get("deskew", True),
        background_cleaned=payload.get("background_cleaned", True),
        ocr_ready=payload.get("ocr_ready", True),
        format=payload.get("format", "pdf"),
    )

    doc_in = PLMDocumentIn(
        style_id=payload.get("style_id", ""),
        style_code=payload.get("style_code", ""),
        folder_code=payload.get("folder_code", "03"),
        folder_name=payload.get("folder_name", "03 Upper Patterns"),
        document_name=payload.get("document_name", "Digitized Pattern Scan"),
        document_type="pattern",
        pattern_category=payload.get("category", "Upper Pattern"),
        file_name=payload.get("file_name", "scan.pdf"),
        file_type=payload.get("file_type", "application/pdf"),
        file_size=payload.get("file_size", 1024500),
        url=payload.get("url", ""),
        thumbnail_url=payload.get("thumbnail_url"),
        scanning_metadata=scanning_meta,
        remarks=payload.get("remarks", "Scanned & Digitized via Pattern Scanner"),
    )

    result = await upload_plm_document(payload.get("style_id"), doc_in, request)

    await log_plm_audit(
        db, "upload", payload.get("style_code", ""), u["email"],
        f"Digitized pattern scan '{doc_in.document_name}' ({scanning_meta.dpi} DPI, deskewed & cleaned)"
    )

    return {
        "status": "success",
        "message": f"Pattern digitized at {scanning_meta.dpi} DPI with background cleaning & auto-deskew.",
        "document": result,
    }


# ---------- TOOLING LIBRARY & SOLE MOULDS ----------

@plm_router.get("/tooling")
async def list_tooling(request: Request, category: Optional[str] = None, vendor: Optional[str] = None):
    u = await _get_user(request)
    db = request.app.mongodb

    q = {}
    if category:
        q["tool_category"] = category
    if vendor:
        q["vendor"] = {"$regex": re.escape(vendor), "$options": "i"}

    docs = await db.plm_tooling.find(q).sort("tool_code", 1).to_list(1000)
    return [stringify(d) for d in docs]


@plm_router.post("/tooling")
async def create_tooling(payload: PLMToolingIn, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    doc = payload.model_dump()
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()

    try:
        res = await db.plm_tooling.insert_one(doc)
    except Exception as e:
        raise HTTPException(400, f"Error creating tooling entry: {str(e)}")

    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)

    await log_plm_audit(
        db, "upload", "GLOBAL", u["email"],
        f"Created Tooling entry {payload.tool_code} — {payload.tool_name} ({payload.tool_category})"
    )
    return stringify(doc)


@plm_router.get("/tooling/{tool_id}")
async def get_tooling_details(tool_id: str, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        t_oid = ObjectId(tool_id)
        doc = await db.plm_tooling.find_one({"_id": t_oid})
    except Exception:
        doc = await db.plm_tooling.find_one({"tool_code": tool_id})

    if not doc:
        raise HTTPException(404, "Tooling entry not found")
    return stringify(doc)


@plm_router.put("/tooling/{tool_id}")
async def update_tooling(tool_id: str, payload: dict, request: Request):
    u = await _get_user(request)
    db = request.app.mongodb

    try:
        t_oid = ObjectId(tool_id)
    except Exception:
        raise HTTPException(400, "Invalid tool ID")

    payload["updated_at"] = now_iso()
    await db.plm_tooling.update_one({"_id": t_oid}, {"$set": payload})

    doc = await db.plm_tooling.find_one({"_id": t_oid})
    await log_plm_audit(
        db, "replace", "GLOBAL", u["email"],
        f"Updated Tooling details for {doc.get('tool_code')}"
    )
    return stringify(doc)


@plm_router.get("/sole-moulds/by-material/{material_code}")
async def get_sole_mould_by_material(material_code: str, request: Request):
    """Auto-Linking: When a Sole material is selected in BOM, fetch its linked Sole Mould details."""
    u = await _get_user(request)
    db = request.app.mongodb

    mould = await db.plm_tooling.find_one({
        "tool_category": "Sole Mould",
        "$or": [
            {"material_code": material_code},
            {"tool_code": material_code},
        ]
    })
    if not mould:
        # Fallback to search in materials master
        mat = await db.materials.find_one({"code": material_code})
        if mat and mat.get("mould_code"):
            mould = await db.plm_tooling.find_one({"tool_code": mat.get("mould_code")})

    if not mould:
        return {"found": False, "material_code": material_code, "message": "No specific Sole Mould linked yet"}

    return {
        "found": True,
        "mould": stringify(mould),
        "drawing_url": mould.get("drawing_url"),
        "image_url": mould.get("image_url"),
        "compatible_styles": mould.get("compatible_styles", []),
        "compatible_sizes": mould.get("compatible_sizes", []),
    }


@plm_router.post("/tooling/link-pattern")
async def link_tooling_to_pattern(payload: dict, request: Request):
    """Maintain many-to-many relationships between Patterns and Cutting Dies/Tools."""
    u = await _get_user(request)
    db = request.app.mongodb

    pattern_id = payload.get("pattern_id")
    tool_code = payload.get("tool_code")

    if not pattern_id or not tool_code:
        raise HTTPException(400, "pattern_id and tool_code required")

    await db.plm_patterns.update_one(
        {"_id": ObjectId(pattern_id)},
        {"$addToSet": {"linked_dies": tool_code}, "$set": {"updated_at": now_iso()}}
    )
    await db.plm_tooling.update_one(
        {"tool_code": tool_code},
        {"$addToSet": {"linked_patterns": pattern_id}, "$set": {"updated_at": now_iso()}}
    )

    await log_plm_audit(
        db, "replace", "GLOBAL", u["email"],
        f"Linked Pattern {pattern_id} with Cutting Die / Tool {tool_code}"
    )

    return {"status": "success", "message": f"Linked Pattern {pattern_id} with Tool {tool_code}"}


# ---------- GLOBAL SEARCH & AUDIT LOG ----------

@plm_router.get("/search")
async def global_plm_search(q: str = Query(..., min_length=1), request: Request = None):
    u = await _get_user(request)
    db = request.app.mongodb

    regex = {"$regex": re.escape(q), "$options": "i"}

    # Search Styles
    styles = await db.styles.find({
        "$or": [{"code": regex}, {"name": regex}, {"category": regex}]
    }).limit(10).to_list(10)

    # Search Documents
    docs = await db.plm_documents.find({
        "status": {"$ne": "archived"},
        "$or": [
            {"style_code": regex}, {"document_name": regex}, {"file_name": regex},
            {"folder_name": regex}, {"tags": regex}
        ]
    }).limit(20).to_list(20)

    # Search Tooling
    tools = await db.plm_tooling.find({
        "$or": [
            {"tool_code": regex}, {"tool_name": regex}, {"vendor": regex},
            {"material_code": regex}, {"compatible_styles": regex}
        ]
    }).limit(15).to_list(15)

    # Search Patterns
    patterns = await db.plm_patterns.find({
        "$or": [{"pattern_name": regex}, {"style_code": regex}, {"category": regex}]
    }).limit(15).to_list(15)

    return {
        "query": q,
        "styles": [stringify(s) for s in styles],
        "documents": [stringify(d) for d in docs],
        "tooling": [stringify(t) for t in tools],
        "patterns": [stringify(p) for p in patterns],
    }


@plm_router.get("/audit-log")
async def get_plm_audit_log(request: Request, style_code: Optional[str] = None, limit: int = 200):
    u = await _get_user(request)
    db = request.app.mongodb

    query = {}
    if style_code:
        query["style_code"] = style_code

    logs = await db.plm_audit_log.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
    return [stringify(l) for l in logs]
